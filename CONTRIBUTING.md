# Contributing

Small, focused pull requests are welcome. Explain the problem, change and validation.
Start with the development commands in README.md. Backend tests must use disposable state.
Do not run device actions in CI. For physical-device changes, describe the iOS/Xcode versions,
behavior observed, and any untested cases without including device identifiers or screenshots of private data.

Good first contributions: English operator UI, setup diagnostics, keyboard accessibility,
safer recovery, and regressions using synthetic screen fixtures.
Do not commit credentials, real contacts, private logs, signed apps or Apple support images.
Run `python3 scripts/check-public-tree.py` before proposing a release.
Contributions are provided under the repository's MIT license. Keep dependency notices intact.
