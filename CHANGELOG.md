# Changelog

All notable changes are listed here. This project is an experimental developer preview; versions before
1.0 may change without notice.

## Unreleased

- **Behavior change:** the agent now sends messages, makes purchases, deletes data or changes settings when
  the current task explicitly asks for it, and can type into ordinary email or username fields. Earlier
  versions always stopped for a person. Masked password fields remain unsupported.
- Prompt tasks read the screen with on-device OCR first, with accessibility as fallback. The chat can switch
  to "Accessibility only".
- Optional screenshot fallback (off by default) sends screen images to the model when controls cannot be found.
- The web UI remembers the local API key in browser storage after a successful connection.
- The chat shows elapsed time, model decisions, phone actions and recovery guidance for failed steps.
- A finished answer must quote text observed on screen; otherwise it is marked "Needs review".
  Accepted answers are labeled "Result reported".
- Tasks allow up to 100 model decisions and 10 minutes (previously 30 decisions and 5 minutes).
- New setting `PHONEUSE_CODEX_REASONING_EFFORT` (`low` by default).
- A bounded routine for dismissing cookie prompts, and a synthetic evaluation (`python -m evals.outing`).
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
