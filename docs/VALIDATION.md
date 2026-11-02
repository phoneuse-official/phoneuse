# Release validation

## 2026-11-02 — launch preparation

Checked on macOS with Python 3.13 and Node.js 24, from a clean checkout.

- `Install PhoneUse.command` created the virtual environment, installed pinned requirements and built the web app.
- Backend tests: 92 passed, with temporary runtime state.
- Web: type check, 6 unit tests and production build passed.
- `pip-audit` on the pinned requirements: no known vulnerabilities.
- `npm audit --audit-level=moderate`: passed. Three low-severity advisories remain in the shadcn CLI's
  `deepmerge`, which has no patched release; the CLI is not used at runtime.
- Public-tree scan: 0 findings. This is not a guarantee against all sensitive data.
- Clean-state API smoke test: `/health` and `/docs` served, unauthenticated requests rejected (401),
  requests from other origins rejected (403), authenticated device list returned.
- The web UI rendered its connect screen.

Not tested: a physical iPhone, a real model task, signing on a fresh Mac. These remain release acceptance
checks before the launch is announced.

## 2026-10-30 — first public preview

Backend tests (39 at the time), web type check and build, `npm audit`, `pip-audit`, the public-tree scan and a
clean-state API smoke test passed. No physical phone or model task was exercised.
