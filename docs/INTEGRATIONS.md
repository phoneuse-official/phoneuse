# Integrations

PhoneUse Local exposes one authenticated API on `http://127.0.0.1:8765`. The web UI, the MCP server
and your own scripts all use it. Start the API first (`./platform/start-api.sh`).

Never point a remote browser at this server or expose it through a public tunnel.

## Local credentials

On first start the API creates a random administrator key in `platform/.state/admin-token`
(or `$PHONEUSE_STATE_DIR/admin-token`). Every request must send it as `Authorization: Bearer <key>`.

The key exists because the API can tap, type, install apps and read the screen. Without it, any
program running on your Mac could control the phone. Browsers are also limited by an origin check,
so other websites cannot call the API.

`Start PhoneUse.command` reads the key and opens the UI with it in the URL fragment; the page removes
the fragment immediately. After the key works, the page saves it in the browser's local storage so it
reconnects automatically later. Do not copy or share that first URL. See [SECURITY.md](../SECURITY.md)
for what saving the key in the browser means.

To give a script or agent its own key, limited to one phone and with an expiry:

```sh
cd platform
../.venv/bin/python create-key.py --name my-script --device YOUR_DEVICE_UDID \
  --expires-at 2026-12-31T00:00:00+00:00
```

The key is printed once. Keys are stored only as SHA-256 hashes.

## MCP

The MCP server runs over stdio and calls the local API, so the API must be running.
Configure your MCP client to launch the absolute path to `platform/start-mcp.sh` in your checkout.
The wrapper reads the local administrator key file by default.

Claude Code:

```sh
claude mcp add phoneuse-local -- /ABSOLUTE/PATH/TO/phoneuse/platform/start-mcp.sh
```

Claude Desktop (`claude_desktop_config.json`) or Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "phoneuse-local": {
      "command": "/ABSOLUTE/PATH/TO/phoneuse/platform/start-mcp.sh"
    }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.phoneuse-local]
command = "/ABSOLUTE/PATH/TO/phoneuse/platform/start-mcp.sh"
```

Optional environment variables for the wrapper:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PHONEUSE_API_KEY` | unset | Use this key instead of reading a file. |
| `PHONEUSE_TOKEN_FILE` | `platform/.state/admin-token` | Key file to read. |
| `PHONEUSE_API_URL` | `http://127.0.0.1:8765` | Local API address. |

Keep overrides in private client configuration; never commit keys.

The tools are defined in `platform/backend/mcp_server.py`. A typical agent loop is
`list_devices` → `acquire_device` → `screenshot` / `page_source` → `device_action` → `release_device`.
MCP exposes manual device operations and does not need the Codex prompt executor.

## REST

Interactive docs: `http://127.0.0.1:8765/docs`. Schema: `/openapi.json`.
Coordinates are fractions of the screen from 0 to 1.

```sh
API=http://127.0.0.1:8765
KEY="$(cat platform/.state/admin-token)"

# List phones and pick one id from the response.
curl -s -H "Authorization: Bearer $KEY" $API/api/devices
DEVICE=YOUR_DEVICE_UDID

# Hold the phone for five minutes.
curl -s -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"seconds":300}' $API/api/devices/$DEVICE/lease

# Look, then act.
curl -s -H "Authorization: Bearer $KEY" $API/api/devices/$DEVICE/screenshot -o screen.png
curl -s -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"action":"home"}' $API/api/devices/$DEVICE/actions
curl -s -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d '{"action":"tap","x":0.5,"y":0.5}' $API/api/devices/$DEVICE/actions

# Give the phone back.
curl -s -X DELETE -H "Authorization: Bearer $KEY" $API/api/devices/$DEVICE/lease
```

`GET /api/capabilities` lists every supported action. A successful action only means the command
reached the phone; take a new screenshot or page source to confirm the result.

`POST /api/ai/tasks` runs a prompt task, the same as the chat. It needs the Codex CLI.

```sh
curl -s -X POST -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' \
  -d "{\"device_id\":\"$DEVICE\",\"task\":\"Open Settings and read the iOS version\"}" $API/api/ai/tasks
```

Optional fields: `screen_mode` is `"ocr"` (default: on-device text recognition first, accessibility as
fallback) or `"accessibility"`; `visual_fallback` (default `false`) sends screenshots to the model when
controls cannot be found; `max_steps` caps model decisions (1 to 100, default 100). Poll
`GET /api/ai/tasks/{id}` for progress and the result; `POST /api/ai/tasks/{id}/cancel` stops it.

## Settings

| Variable | Used by | Purpose |
| --- | --- | --- |
| `PHONEUSE_STATE_DIR` | API, tests | Where keys, the database, logs and uploads live. Default `platform/.state`. |
| `PHONEUSE_CODEX_BIN` | API | Absolute path to the Codex CLI if it is not on the API's `PATH`. |
| `PHONEUSE_CODEX_MODEL` | API | Model name passed to Codex for prompt tasks. |
| `PHONEUSE_CODEX_REASONING_EFFORT` | API | `low` (default), `medium` or `high` reasoning for prompt tasks. |
| `PHONEUSE_WDA_BUNDLE_ID` | API, `start-wda.py` | Bundle ID of your signed WebDriverAgent runner. |

Older `QUNKONG_*` names are still read as a fallback.
