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
- Screen contents are untrusted input. The agent is told to hand off purchases, credentials and messages, but
  model instructions cannot prevent every harmful action. Supervise real-device use.

## Your data

Runtime state stays under `platform/.state` (or `PHONEUSE_STATE_DIR`): API keys (as hashes, plus the
administrator key file), device inventory, task history, logs and uploaded files. Prompts and accessibility
data are sent to the model provider you configured through Codex. "Clear chat" only hides completed tasks;
it is not secure erasure.

Do not attach keys, pairing records, signing certificates, contacts, private screenshots or raw task history
to public issues. Redact examples and use synthetic identifiers.
