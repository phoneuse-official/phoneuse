# Changelog

All notable changes are listed here. This project is an experimental developer preview; versions before
1.0 may change without notice.

## Unreleased

- Chat history in the sidebar, scoped to each API key.
- Guarded phone programs: verified field entry and search submission, with no automatic replay.
- Prompts submit on Enter; responsive phone preview; better setup guidance.
- All runtime messages, MCP tool descriptions and UI statuses are in English.
- Settings use the `PHONEUSE_` prefix (`PHONEUSE_STATE_DIR`, `PHONEUSE_API_KEY`, `PHONEUSE_TOKEN_FILE`,
  `PHONEUSE_API_URL`, `PHONEUSE_CODEX_BIN`, `PHONEUSE_CODEX_MODEL`, `PHONEUSE_AI_API_KEY`). The older
  `QUNKONG_` names still work.
- The optional login service is named `com.phoneuse.local-node`.
- The MCP server is named `phoneuse-local`.
- CI runs on every pull request: the public-tree scan, backend tests, dependency audits, web type check,
  web tests and web build.
- New community files: code of conduct, issue templates and Dependabot updates.

## 0.1.0 — 2026-10-30

First public developer preview: local web UI with live video, natural-language tasks through the Codex CLI,
authenticated REST API, MCP server and WDA recovery.
