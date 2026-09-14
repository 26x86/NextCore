#!/usr/bin/env python3
"""Build a ready-to-copy OpenCore + NextCore EFI folder.

Layout produced under ``<out>/EFI``:

    EFI/BOOT/BOOTX64.EFI          OpenCore RELEASE BOOTx64.efi
    EFI/OC/OpenCore.efi           OpenCore RELEASE
    EFI/OC/Drivers/*.efi          drivers listed in the profile (OpenRuntime, OpenHfsPlus, ...)
    EFI/OC/Tools/*.efi            tools listed in the profile (OpenShell, ...)
    EFI/OC/config.plist           generated from the official Sample.plist + profile
    EFI/NEXTCORE/BOOTX64.EFI      NextCore picker from ``bin/`` (hash-checked)

OpenCore is downloaded from the official GitHub release (pinned version + SHA-256)
and cached under ``cache/``. Nothing is written outside ``<out>`` and ``cache/``.
Only the Python standard library is required (3.9+).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import platform
import plistlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = ROOT / "bin"
PROFILES_DIR = ROOT / "profiles"
CACHE_DIR = ROOT / "cache"

NEXTCORE_REL = "NEXTCORE/BOOTX64.EFI"

# Pinned OpenCore RELEASE archives (official acidanthera/OpenCorePkg GitHub releases).
OPENCORE_RELEASES = {
    "1.0.7": {
        "url": "https://github.com/acidanthera/OpenCorePkg/releases/download/1.0.7/OpenCore-1.0.7-RELEASE.zip",
        "sha256": "2ffab6ebf58c7aefb0bcb3a1a385d207746823d6dd87d44bd666e1286939943e",
    },
}
DEFAULT_OPENCORE = "1.0.7"


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def log(message: str) -> None:
    print(f"[make_efi] {message}", flush=True)


# --------------------------------------------------------------------------- inputs

def load_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, relative = line.partition("  ")
        entries[relative.strip()] = digest.strip().lower()
    return entries


def verify_nextcore_binary() -> Path:
    manifest = load_manifest(BIN_DIR / "MANIFEST.sha256")
    expected = manifest.get(NEXTCORE_REL)
    if not expected:
        raise BuildError(f"bin/MANIFEST.sha256 has no entry for {NEXTCORE_REL}")
    path = BIN_DIR / NEXTCORE_REL
    if not path.is_file():
        raise BuildError(f"missing NextCore binary: {path}")
    actual = sha256_file(path)
    if actual != expected:
        raise BuildError(f"NextCore binary hash mismatch: expected {expected}, got {actual}")
    log(f"NextCore {NEXTCORE_REL} ok ({path.stat().st_size} bytes, sha256 {actual[:16]}...)")
    return path


def load_profile(name_or_path: str) -> dict:
    candidate = Path(name_or_path)
    if not candidate.is_file():
        candidate = PROFILES_DIR / f"{name_or_path}.json"
    if not candidate.is_file():
        available = ", ".join(sorted(p.stem for p in PROFILES_DIR.glob("*.json")))
        raise BuildError(f"unknown profile {name_or_path!r}; available: {available}")
    profile = json.loads(candidate.read_text(encoding="utf-8"))
    for key in ("name", "set", "drivers", "tools"):
        if key not in profile:
            raise BuildError(f"profile {candidate} missing key {key!r}")
    return profile


# --------------------------------------------------------------------------- OpenCore

def fetch_opencore(version: str, local_zip: Path | None) -> Path:
    """Return the extracted OpenCore release directory for ``version``."""
    pin = OPENCORE_RELEASES.get(version)
    if pin is None:
        raise BuildError(f"OpenCore {version} is not pinned; known: {', '.join(OPENCORE_RELEASES)}")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = CACHE_DIR / f"OpenCore-{version}-RELEASE.zip"
    extract_dir = CACHE_DIR / f"opencore-{version}"

    if local_zip is not None:
        shutil.copy2(local_zip, zip_path)
    if not zip_path.is_file():
        log(f"downloading {pin['url']}")
        with urllib.request.urlopen(pin["url"], timeout=120) as response, zip_path.open("wb") as handle:
            shutil.copyfileobj(response, handle)

    actual = sha256_file(zip_path)
    if actual != pin["sha256"]:
        zip_path.unlink(missing_ok=True)
        raise BuildError(f"OpenCore {version} archive hash mismatch: expected {pin['sha256']}, got {actual}")
    log(f"OpenCore {version} archive ok (sha256 {actual[:16]}...)")

    marker = extract_dir / ".extracted"
    if not marker.is_file():
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True)
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.infolist():
                target = (extract_dir / member.filename).resolve()
                if not str(target).startswith(str(extract_dir.resolve())):
                    raise BuildError(f"unsafe path in archive: {member.filename}")
            archive.extractall(extract_dir)
        marker.write_text(actual + "\n", encoding="utf-8")
    return extract_dir


def ocvalidate_binary(release_dir: Path) -> Path | None:
    utilities = release_dir / "Utilities" / "ocvalidate"
    system = platform.system()
    if system == "Windows":
        candidate = utilities / "ocvalidate.exe"
    elif system == "Linux":
        candidate = utilities / "ocvalidate.linux"
    elif system == "Darwin":
        candidate = utilities / "ocvalidate"
    else:
        return None
    return candidate if candidate.is_file() else None


# --------------------------------------------------------------------------- config

def decode_value(value):
    """Convert JSON profile values into plist values (``{"$data": base64}`` -> bytes)."""
    if isinstance(value, dict):
        if set(value) == {"$data"}:
            return base64.b64decode(value["$data"])
        return {key: decode_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_value(item) for item in value]
    return value


def set_path(config: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    node = config
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value


def build_config(sample: Path, profile: dict, overrides: dict[str, object]) -> dict:
    with sample.open("rb") as handle:
        config = plistlib.load(handle)

    for key in [k for k in config if str(k).startswith("#WARNING")]:
        del config[key]
    config["#NOTE"] = profile.get("note", f"NextCore profile {profile['name']}")

    for dotted, value in profile["set"].items():
        set_path(config, dotted, decode_value(value))

    config["UEFI"]["Drivers"] = [
        {
            "Arguments": "",
            "Comment": driver.get("Comment", ""),
            "Enabled": True,
            "LoadEarly": False,
            "Path": driver["Path"],
        }
        for driver in profile["drivers"]
    ]

    for dotted, value in overrides.items():
        set_path(config, dotted, value)

    return config


def smbios_overrides(args: argparse.Namespace) -> dict[str, object]:
    overrides: dict[str, object] = {}
    if args.product_name:
        overrides["PlatformInfo.Generic.SystemProductName"] = args.product_name
    if args.serial:
        overrides["PlatformInfo.Generic.SystemSerialNumber"] = args.serial
    if args.mlb:
        overrides["PlatformInfo.Generic.MLB"] = args.mlb
    if args.uuid:
        overrides["PlatformInfo.Generic.SystemUUID"] = args.uuid
    if args.rom:
        rom = bytes.fromhex(args.rom.replace(":", ""))
        if len(rom) != 6:
            raise BuildError("--rom must be 6 bytes of hex (e.g. 112233445566)")
        overrides["PlatformInfo.Generic.ROM"] = rom
    return overrides


# --------------------------------------------------------------------------- assemble

def copy_file(source: Path, target: Path) -> None:
    if not source.is_file():
        raise BuildError(f"missing input file: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def assemble(out: Path, release_dir: Path, profile: dict, config: dict, nextcore: Path) -> list[Path]:
    efi = out / "EFI"
    oc_src = release_dir / "X64" / "EFI"

    copy_file(oc_src / "BOOT" / "BOOTx64.efi", efi / "BOOT" / "BOOTX64.EFI")
    copy_file(oc_src / "OC" / "OpenCore.efi", efi / "OC" / "OpenCore.efi")
    for driver in profile["drivers"]:
        copy_file(oc_src / "OC" / "Drivers" / driver["Path"], efi / "OC" / "Drivers" / driver["Path"])
    for tool in profile["tools"]:
        copy_file(oc_src / "OC" / "Tools" / tool["Path"], efi / "OC" / "Tools" / tool["Path"])
    copy_file(nextcore, efi / "NEXTCORE" / "BOOTX64.EFI")

    config_path = efi / "OC" / "config.plist"
    with config_path.open("wb") as handle:
        plistlib.dump(config, handle, fmt=plistlib.FMT_XML, sort_keys=False)

    return sorted(path for path in efi.rglob("*") if path.is_file())


def validate(release_dir: Path, config_path: Path, skip: bool) -> str:
    binary = ocvalidate_binary(release_dir)
    if skip:
        log("ocvalidate skipped (--skip-validate)")
        return "skipped"
    if binary is None:
        log("ocvalidate not available for this host; skipping")
        return "unavailable"
    if platform.system() != "Windows":
        binary.chmod(binary.stat().st_mode | 0o111)
    result = subprocess.run([str(binary), str(config_path)], capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise BuildError(f"ocvalidate reported problems (exit {result.returncode})")
    log("ocvalidate passed")
    return "passed"


def write_receipt(out: Path, files: list[Path], *, profile: dict, version: str, validation: str,
                  placeholders: bool) -> None:
    manifest_lines = [f"{sha256_file(path)}  {path.relative_to(out).as_posix()}" for path in files]
    (out / "MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")

    release_meta = json.loads((BIN_DIR / "release.json").read_text(encoding="utf-8"))
    receipt = {
        "schema": "nextcore.efi-tree/1",
        "generated_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "profile": profile["name"],
        "opencore_version": version,
        "nextcore_version": release_meta.get("version"),
        "ocvalidate": validation,
        "smbios_placeholders": placeholders,
        "macos_boot_verified": False,
        "files": {path.relative_to(out).as_posix(): sha256_file(path) for path in files},
    }
    (out / "efi-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- main

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", default="generic-x64", help="profile name under profiles/ or a JSON path")
    parser.add_argument("--out", type=Path, default=ROOT / "out", help="output directory (default: ./out)")
    parser.add_argument("--opencore-version", default=DEFAULT_OPENCORE, choices=sorted(OPENCORE_RELEASES))
    parser.add_argument("--opencore-zip", type=Path, help="use a local OpenCore-<ver>-RELEASE.zip instead of downloading")
    parser.add_argument("--product-name", help="PlatformInfo.Generic.SystemProductName override")
    parser.add_argument("--serial", help="PlatformInfo.Generic.SystemSerialNumber")
    parser.add_argument("--mlb", help="PlatformInfo.Generic.MLB")
    parser.add_argument("--uuid", help="PlatformInfo.Generic.SystemUUID")
    parser.add_argument("--rom", help="PlatformInfo.Generic.ROM as 12 hex digits")
    parser.add_argument("--skip-validate", action="store_true", help="do not run ocvalidate")
    parser.add_argument("--force", action="store_true", help="replace an existing output directory")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out = args.out.resolve()

    if out.exists():
        if not args.force:
            raise BuildError(f"output exists: {out} (use --force to replace)")
        shutil.rmtree(out)
    out.mkdir(parents=True)

    nextcore = verify_nextcore_binary()
    profile = load_profile(args.profile)
    release_dir = fetch_opencore(args.opencore_version, args.opencore_zip)

    overrides = smbios_overrides(args)
    config = build_config(release_dir / "Docs" / "Sample.plist", profile, overrides)
    files = assemble(out, release_dir, profile, config, nextcore)
    validation = validate(release_dir, out / "EFI" / "OC" / "config.plist", args.skip_validate)

    generic = config["PlatformInfo"]["Generic"]
    placeholders = "REPLACE_WITH" in str(generic.get("SystemSerialNumber", "")) or \
        "REPLACE_WITH" in str(generic.get("MLB", ""))
    write_receipt(out, files, profile=profile, version=args.opencore_version,
                  validation=validation, placeholders=placeholders)

    log(f"EFI tree written to {out / 'EFI'}")
    for path in files:
        log(f"  {path.relative_to(out).as_posix()}  {sha256_file(path)[:16]}...")
    if placeholders:
        log("WARNING: SMBIOS serial/MLB/UUID are placeholders; pass --serial/--mlb/--uuid before booting macOS.")
    log("Booting to the picker is not a macOS boot; macos_boot_verified stays false.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BuildError as error:
        print(f"[make_efi] error: {error}", file=sys.stderr)
        raise SystemExit(2)
