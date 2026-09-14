# NextCore

Userland tooling for the NextCore boot picker: a prebuilt EFI binary, an **EFI folder
generator**, and a **USB creator**. Nothing here requires a toolchain — Python 3.9+ and,
on Windows, PowerShell 5.1+.

This repository is deliberately small. It contains **only** what an end user needs to put
NextCore on a USB stick behind OpenCore. Source code, research notes, probes and validation
harnesses live in a separate private repository and are not published here.

```text
bin/NEXTCORE/BOOTX64.EFI   NextCore picker (x86_64 UEFI application)
bin/MANIFEST.sha256        hash of the shipped binary
bin/release.json           version, build features, evidence status
tools/make_efi.py          EFI folder generator (OpenCore + NextCore + config.plist)
tools/make-usb.ps1         USB creator for Windows
profiles/*.json            hardware profiles consumed by make_efi.py
```

## What it produces

`tools/make_efi.py` downloads the pinned **official OpenCore RELEASE** (SHA-256 checked,
cached under `cache/`), generates `config.plist` from OpenCore's own `Docs/Sample.plist`
plus a profile, validates it with `ocvalidate`, and assembles:

```text
EFI/BOOT/BOOTX64.EFI        OpenCore BOOTx64.efi
EFI/OC/OpenCore.efi
EFI/OC/Drivers/OpenRuntime.efi
EFI/OC/Drivers/OpenHfsPlus.efi
EFI/OC/Tools/OpenShell.efi
EFI/OC/config.plist         generated + ocvalidate-clean
EFI/NEXTCORE/BOOTX64.EFI    NextCore picker (hash-checked against bin/MANIFEST.sha256)
```

Boot flow: firmware → OpenCore picker → **NextCore Picker** entry (UEFI Shell is the second
entry). OpenCore binaries are never redistributed from this repo; they are fetched from
[acidanthera/OpenCorePkg](https://github.com/acidanthera/OpenCorePkg/releases) at build time.

## Quick start

### 1. Generate the EFI folder

```sh
python tools/make_efi.py --profile generic-x64 --out out/generic-x64
# or a hardware-specific profile
python tools/make_efi.py --profile 15igl7 --out out/15igl7
```

Set real SMBIOS values before booting macOS (placeholders are written otherwise):

```sh
python tools/make_efi.py --profile 15igl7 --out out/15igl7 \
  --serial C02XXXXXXXXX --mlb C02XXXXXXXXXXXXXX \
  --uuid 12345678-1234-1234-1234-123456789ABC --rom 112233445566
```

Outputs: `out/<profile>/EFI/`, `MANIFEST.sha256`, `efi-receipt.json`.

### 2a. Write a USB stick (Windows)

Run from an elevated PowerShell:

```powershell
.\tools\make-usb.ps1 -List                              # find the disk number
.\tools\make-usb.ps1 -Profile 15igl7 -DiskNumber 2 -Force   # ERASES disk 2
```

Creates GPT → 512 MiB FAT32 ESP (`NEXTCORE`) + exFAT data partition, copies the EFI tree,
and re-hashes every file on the stick against `MANIFEST.sha256`. Refuses boot/system disks
and non-USB disks.

To refresh an existing FAT32 ESP without repartitioning:

```powershell
.\tools\make-usb.ps1 -EfiDir .\out\15igl7 -EspRoot D:\
```

### 2b. macOS / Linux

Format the stick GPT with a FAT32 EFI System Partition (macOS: `diskutil eraseDisk FAT32
NEXTCORE GPT diskN`; Linux: `sgdisk` + `mkfs.vfat -F32`), then copy `out/<profile>/EFI` to
the root of that partition and check hashes with `sha256sum -c MANIFEST.sha256` from the
partition root.

### 3. Boot

Disable Secure Boot, boot the USB in UEFI mode, choose **NextCore Picker** in OpenCore.

## Profiles

| Profile | Target | Notes |
| --- | --- | --- |
| `generic-x64` | any x86_64 UEFI machine | Sample.plist quirk defaults, no ACPI, no kexts, `iMacPro1,1` placeholder |
| `15igl7` | Lenovo IdeaPad 1 15IGL7 (Gemini Lake, UHD 600/605) | 1366x768 text renderer, USB ownership quirks, iGPU framebuffer hint, no kexts (no AVX2) |

A profile is a JSON file: `set` is a map of dotted plist paths to values (`{"$data": "<base64>"}`
for `<data>`), `drivers`/`tools` list files taken from the OpenCore release. Copy one and
edit it; `make_efi.py --profile path/to/file.json` accepts a path.

## Verify what you got

```sh
cd bin && sha256sum -c MANIFEST.sha256
```

`bin/release.json` records the binary's SHA-256, target (`x86_64-unknown-uefi`), build
features (`apfs-jumpstart`, `console-control`) and the evidence status.

## What this is not

- **Not a macOS boot claim.** `macos_boot_verified` is `false` in every receipt this repo
  writes. Reaching the NextCore picker proves firmware load and OpenCore chain-load, nothing
  more.
- **Not installer media.** The exFAT data partition is plain storage. A `BaseSystem.dmg`
  copied there is not bootable Recovery; real Recovery/installer volumes must be created on
  macOS (`createinstallmedia`).
- **Not a supported-hardware list.** The `15igl7` profile documents a machine that lacks AVX2
  and has no macOS graphics driver; it exists to reach the picker, not to run macOS.
- **No Apple assets, no source.** Only project-built EFI and OpenCore release files are used.

## License

See `LICENSE.txt`. Binary redistribution is permitted under the listed conditions.
OpenCore is © Acidanthera, BSD-3-Clause, downloaded from its official releases.
