# NextCore

**Current Status:** NextCore 1.3.0 is a research preview, updated 2 October 2026. The current normal EFI, separate installation utility, research runtime, ISO and verified archives are built from one immutable main revision. Interactive Recovery utilities, installed GUI operation, macOS 27 operation, Metal, physical installation and hardware qualification remain unverified for these artifacts.

**Target State:** Direct EFI boot on supported Intel systems, a simple Computer → Prepare → Review setup flow with GUI, TUI and CLI access, an interactive Recovery environment and an installed desktop. No intermediate Linux guest is part of the shipped boot path.

- [Download NextCore 1.3.0](https://github.com/26x86/NextCore/releases/tag/v1.3.0)
- [Current support files](https://26x86.crevision.kr/nextcore-support/catalog.json)
- [Official documentation](https://26x86.github.io/)
- [Development progress](https://26x86.github.io/progress/)

## Version 1.3 files

`BOOTX64.EFI` is the normal x86 UEFI application. `NXINSTALL.EFI` is the separate read-only installation utility. `nextcore-installation-research.iso` contains the research utility and its separate runtime; it is not a macOS installer. `NXARMJIT.efi` is the research runtime, not the normal firmware boot entry.

`nextcore-direct-efi.zip` groups the normal EFI configuration, installation utility, ISO and notices. `prebuiltefi.zip` contains the normal EFI, research runtime, configuration, source manifest and notices. Individual files, source receipts and archive verification receipts are also available in the release.

Verify downloads against `SHA256SUMS`. `release.json` records the exact compiled private monorepo revision separately from this public repository's main/tag revision, file sizes, SHA-256 digests and explicit acceptance limits. The recorded source receipts are build metadata, not a third-party source attestation.

The research installation utility supports read-only inspection and planning. Installation writes and firmware boot-entry changes are unavailable. It does not establish physical installation or support for a particular machine. Earlier macOS 26 launchd/WindowServer observations belong to their original inputs and binaries, and do not qualify the newly built 1.3 set.

## Public distribution boundary

This repository distributes reviewed binaries, hashes and user documentation. The exact consolidated implementation source is in the private NextCore-Stuff repository; public component repositories are separate historical/module sources and are not interchangeable pins for this release. Original Apple media, signing material, SMC secrets and raw execution evidence are not included.

The old `bin/` picker and generator profiles are preserved historical material. Use the versioned 1.3 release assets for this research preview. See [legacy tooling](LEGACY_TOOLING.md) for the archive.

GitHub-hosted source checks could not run because of the account billing/spending restriction. Local checks and artifact verification are recorded separately; hosted CI is not reported as passed. The generic host workspace test also encountered a UEFI/host panic-handler conflict before running tests; focused host validation is recorded in the release manifest.

## Notices

See [the project license](LICENSE.txt) and the distribution's complete `LICENSES.txt` for project/dependency notices and covered-source access information. NextCore is not affiliated with or endorsed by Apple.
