# PhoneUse Local

Python backend: `platform/backend`. React UI: `platform/web`.
Run backend tests from `platform`; use `PHONEUSE_STATE_DIR` pointing to a temporary directory.
Keep API and UI bound to loopback. Never commit `.state`, tokens, signing assets,
pairing records, device identifiers, screenshots, personal contacts or task history.
Use only official WebDriverAgent sources. Keep native capture opt-in.
Do not change a live device, send messages, or make purchases as part of automated tests.
Preserve the distinction between this local project and the hosted PhoneUse service.
