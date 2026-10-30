# Security and privacy

This is a local developer preview, not a hardened multi-tenant service.
The administrator token grants access to phone control and locally stored assets. Keep the API and UI
on loopback; no public exposure is supported. Review task requests and supervise real-device actions.
Treat screen contents as untrusted input. Model instructions alone cannot prevent every harmful action.

Do not attach tokens, pairing records, signing certificates, contacts, private screenshots or raw task
histories to public issues. Redact reproduction examples and use synthetic identifiers.
Report vulnerabilities through GitHub private vulnerability reporting once enabled for this repository.
Until then, request a private reporting channel through the official PhoneUse website without disclosing
exploit details publicly. This project does not currently promise a response SLA.

Runtime state stays under `platform/.state` by default. Prompts and accessibility data are sent to the
configured model provider. Clearing chat only hides completed tasks; it is not secure data erasure.
