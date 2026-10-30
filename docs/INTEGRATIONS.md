# Integrations

The local API runs at `http://127.0.0.1:8765`. Read its OpenAPI schema at `/openapi.json`.
Authenticated requests use `Authorization: Bearer <local token>`.
Do not point a remote browser at this server or expose it through a public tunnel.

## MCP over stdio

Start the API, then configure your MCP client to launch the absolute path to
`platform/start-mcp.sh` from this checkout. Inspect `platform/backend/mcp_server.py` for tools.
The wrapper reads the locally generated token file by default. You may override it with
`QUNKONG_TOKEN_FILE` or `QUNKONG_API_KEY`, and set `QUNKONG_API_URL` (default loopback).
Keep overrides in private client configuration; never commit credentials.
MCP exposes manual device operations and does not require the Codex prompt executor.

## Local credentials

The API creates a random administrator token on first start in `platform/.state/admin-token`.
The launcher reads it and opens the local UI with a URL fragment, which the UI removes immediately.
Do not copy or share that initial URL. The UI stores the token in browser session storage.
