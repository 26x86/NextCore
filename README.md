# NextCore

**Current Status:** Engineering preview, updated 19 September 2026. macOS 27 boot, a functioning guest Metal driver, physical installation and Recovery/DFU completion are **not verified**. No real Intel Mac model is qualified for this preview.

**Target State:** Working macOS 27 on supported real Intel Macs through NextCore, functional Metal without a performance promise, and a separate EFI NextCore Installation Utility.

- [Official documentation](https://26x86.github.io/)
- [Detailed development progress](https://26x86.github.io/progress/)
- [Downloads and capability limits](https://26x86.github.io/downloads/)
- [19 September engineering preview](https://github.com/26x86/NextCore/releases/tag/engineering-preview-20260919)

## Installation utility preview

The preview ISO and EFI package contain the default release-policy utility. They contain no macOS installer or Apple firmware. The current utility provides read-only planning and partition inspection for development; installation writes and boot-entry changes are unavailable. Unsupported platforms and virtual machines are refused by the default policy. Release admission remains blocked pending independent physical qualification; SMBIOS strings are not authenticity proof.

Read-only GPT inspection was exercised separately in an internal VM research profile against disposable 512-byte and 4096-byte sector images. Those checks do not qualify the downloadable default-policy build for physical installation. Host image-transaction tests do not establish EFI installation.

Verify the downloaded artifacts against `MANIFEST.sha256`. The ISO and EFI ZIP include `LICENSES.txt` with project/dependency notices and exact third-party covered-source access instructions. `release.json` records immutable build provenance and explicitly false acceptance flags.

## Public distribution boundary

This repository distributes reviewed binaries, hashes and user documentation. Original implementation source, private research, raw restore evidence, signing material and Apple assets are not included. The old `bin/` picker and generator profiles are historical engineering material; they are not a supported release and do not inherit the preview's admission policy. See [legacy tooling](LEGACY_TOOLING.md) for that archive only.

## Notices

This product includes software developed by Dortania, OpenCore Legacy Patcher contributors, and the 26x86 project.

See [the project license](LICENSE.txt) and the distribution's `LICENSES.txt`. NextCore is not affiliated with or endorsed by Apple.
