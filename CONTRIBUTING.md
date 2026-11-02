# Contributing

Thanks for helping. Small, focused pull requests are welcome. Explain the problem, the change and
how you checked it. For larger changes, open an issue first so we can agree on the approach.

## Set up

Follow the install steps in [README.md](README.md). You do not need an iPhone to work on most of the
code: the tests and the web build run without one.

## Checks

Run these from the repository root before opening a pull request. CI runs the same checks.

```sh
export PHONEUSE_STATE_DIR="$(mktemp -d)"   # disposable state; never your real one
(cd platform && ../.venv/bin/python -m pytest tests -q)
(cd platform/web && npm run typecheck && npm test && npm run build)
python3 scripts/check-public-tree.py
```

## Rules

- Backend tests must use disposable state and synthetic screen fixtures.
- Do not run device actions in CI or in automated tests. Never send messages or make purchases while testing.
- For physical-device changes, describe the macOS, Xcode and iOS versions, what you observed, and what you
  did not test. Leave out device identifiers and screenshots of private data.
- Keep the API and UI bound to loopback.
- Do not commit credentials, `.state` files, real contacts, private logs, signed apps or Apple support images.
- User-facing text and errors are in English.

## Good first contributions

Setup diagnostics, keyboard accessibility, safer recovery, clearer error messages, and regression tests that
use synthetic screen fixtures.

## License

Contributions are provided under the repository's [MIT license](LICENSE). Keep dependency notices intact.
By taking part you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
