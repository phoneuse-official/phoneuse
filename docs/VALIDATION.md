# Release preparation validation

Checked locally on 2026-10-30, on the source-only public checkout.

- Fresh Python 3.13 virtual environment installed the pinned requirements successfully.
- `pip check`: no broken requirements.
- Backend tests: 39 passed, with temporary runtime state.
- Clean-state API smoke: OpenAPI available, unauthenticated tasks rejected, authenticated task list empty.
- Web TypeScript check and production build passed.
- Production HTTP smoke on an isolated loopback port rendered `/demo`, PhoneUse Local branding and the outbound PhoneUse link.
- `npm audit`: zero known vulnerabilities at check time.
- `pip-audit` on the pinned requirements: zero known vulnerabilities at check time.
- Public source tree scan: no findings in checked paths/patterns. This is not a guarantee against all possible sensitive data.
- Shell syntax and Python compilation checks passed.

The tests did not operate a physical phone, submit a real model task, verify signing on a fresh Mac,
or run GitHub-hosted CI. Those remain release acceptance checks. The source is packaged as an
experimental developer preview; no universal installation or production reliability claim is made.
The original working Studio installation was not modified during preparation.

The web stack was updated to patched Next.js, React, Vinext and Vite releases. A narrow Satori/fflate
override removes a known transitive advisory. Python pins were updated for certifi, OpenTelemetry API,
Pillow, PyJWT and urllib3. Audit results can change as new advisories are published.
