# Security and privacy

PhoneUse Local is a local developer preview, not a hardened multi-user service.

## Reporting a vulnerability

Please report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Do not open a public issue or post exploit details. If that button is not
available, contact us through [phoneuse.com](https://phoneuse.com/?utm_source=github&utm_medium=security&utm_campaign=phoneuse-local)
and ask for a private channel. We do not promise a response time yet.

## How the local API is protected

- The API and the web UI listen only on `127.0.0.1`. Public exposure is not supported.
- Every request needs an API key. The administrator key is created on first start in `platform/.state/admin-token`
  and grants full phone control and access to stored files. Treat it like a password.
- Browser requests from other websites are rejected by an origin check.
- After a successful connection, the web UI saves the key in this browser's local storage so it reconnects
  automatically. Any page served from `http://localhost:3109` can read that storage, so do not run other local
  web apps on that port. A rejected key is removed automatically; private browsing or clearing site data
  removes it too.
- Screen contents are untrusted input. The agent is told to follow only your current task and never to take
  instructions from the screen or from earlier tasks. It will send messages, make purchases, delete data or
  change settings when your task explicitly asks for it, and it can type into ordinary fields such as email or
  username. Masked password fields are not supported. These are model instructions, not a security
  sandbox: supervise real-device use and stop a task that goes wrong.

## Your data

Runtime state stays under `platform/.state` (or `PHONEUSE_STATE_DIR`): API keys (as hashes, plus the
administrator key file), device inventory, task history, logs and uploaded files. Prompts and screen data are
sent to the model provider you configured through Codex:

- By default the agent takes a screenshot and reads its text on your Mac with Apple's Vision framework. The
  recognized text and its position are sent; the image is not.
- Accessibility data (control names, labels and field values, never masked password values) is also sent,
  for example for typing, for checking results, with "Accessibility only", or when OCR finds nothing.
- Screenshots are sent only if you tick "Use screenshots if controls cannot be found" (or set
  `visual_fallback` in the API).

"Clear chat" only hides completed tasks; it is not secure erasure.

Do not attach keys, pairing records, signing certificates, contacts, private screenshots or raw task history
to public issues. Redact examples and use synthetic identifiers.
