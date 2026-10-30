# PhoneUse Local

**Give your AI agent a real iPhone, right on your desk.**

Open-source tools for controlling a USB-connected iPhone from your Mac: a local web interface,
live screen preview, natural-language prompts, REST API, and MCP server.

Built by [PhoneUse](https://phoneuse.com/?utm_source=github&utm_medium=readme&utm_campaign=phoneuse-local).
Want phones without managing hardware on your desk? [Explore PhoneUse →](https://phoneuse.com/?utm_source=github&utm_medium=readme_cta&utm_campaign=phoneuse-local)

> Experimental developer preview. Bring your own Mac, iPhone, Apple signing setup, and model access.
> This project uses WebDriverAgent. It is separate from the hosted PhoneUse platform and does not
> include hosted phones, production infrastructure, or a guarantee that every app can be automated.

## What you can do

- Enter a prompt in a browser and watch the phone respond.
- Open apps, inspect accessibility elements, tap, type, and scroll.
- Watch live video through WDA's compatible stream; optional native macOS capture is available.
- Use the authenticated REST API or connect an MCP client.
- Stop agent tasks and inspect their results. Clear the displayed conversation independently of local execution records.

Start with a reversible prompt: **“Open Safari and describe the current screen. Do not submit anything.”**
Accessibility support varies by app. A task marked finished is a model-reported result; verify important outcomes on the device.

## Requirements

- macOS with full Xcode and an iOS version supported by that Xcode installation.
- A USB-connected iPhone that you own or are authorized to control, unlocked and trusted by this Mac.
- Developer Mode and a legitimately signed Appium WebDriverAgentRunner.
- Python 3.13, Node.js 24+, npm, and Git.
- Codex CLI installed and signed in for natural-language tasks. Model access and usage limits belong to your account.
  This integration was exercised with Codex CLI 0.154.0; its structured-output flags may change.

No jailbreak, pre-signed IPA, Apple developer image, or credential is bundled.

## Quick start

Download or clone this repository, then run commands from its root:

```sh
./"Install PhoneUse.command"
```

1. Follow [iPhone setup](platform/docs/SETUP.md) to sign and run WebDriverAgent on **your** phone.
2. In one terminal, start the local API:

   ```sh
   ./platform/start-api.sh
   ```

3. In a second terminal, launch the website:

   ```sh
   ./"Start PhoneUse.command"
   ```

The launcher opens **http://localhost:3109/demo** and supplies the newly generated local API token.
Keep the API terminal open. The frontend runs as a background process, with logs in `platform/.state/recording-web.log`.
The launcher opens an existing service on these ports if one is already running; stop your old local Studio first if you intend to run this checkout.

Sign into Codex with `codex login` before submitting prompts. If the API cannot find it, launch the API with
`QUNKONG_CODEX_BIN` set to the absolute path returned by `command -v codex`.
Optionally set `QUNKONG_CODEX_MODEL` to a model available to your account; otherwise the CLI selects its default.

**Send is disabled?** The selected phone must report `automation: ready`. Unlock the phone and run
WebDriverAgentRunner's tests in Xcode. Live video alone does not prove that control is connected.

## How it works

```text
Browser at localhost:3109 ── authenticated HTTP / WebSocket ── Local Python API :8765
                                                              ├─ Codex CLI → next action
                                                              ├─ USB → WebDriverAgent → iPhone
                                                              └─ WDA MJPEG → live preview
```

Prompt execution uses accessibility observations. It can fail when apps omit accessible elements;
this is not a general vision agent. The agent is instructed to hand off purchases, credentials,
messages and other consequential operations; those instructions are not a security sandbox.
The raw API and manual controls can perform real actions. Supervise use on personal devices.

## API and MCP

Interactive API docs: **http://127.0.0.1:8765/docs** while the API is running.
Credentials are generated locally at `platform/.state/admin-token`. Do not share them or paste them into issues.
For MCP, see [integration instructions](docs/INTEGRATIONS.md).

## Privacy and local data

The server listens only on loopback. PhoneUse links are ordinary outbound links, with campaign tags;
they do not transfer phone data. The local prompt agent sends task text and phone accessibility data
to the model provider through your Codex login. This is **not fully offline inference**.

Local state includes API tokens, device inventory, task histories, logs and uploaded assets.
It lives in the ignored `platform/.state/` directory. “Clear chat” hides completed tasks in the UI;
it does not erase execution records. Never publish this directory or your Mac's pairing/signing files.
See [SECURITY.md](SECURITY.md).

## Develop

```sh
# Backend tests; use disposable state, never your live phone configuration.
export QUNKONG_STATE_DIR="$(mktemp -d)"
(cd platform && ../.venv/bin/python -m pytest tests -q)
(cd platform/web && npm run typecheck && npm run build)
python3 scripts/check-public-tree.py
```

| Directory | Contents |
| --- | --- |
| `platform/backend` | API, USB device control, agent, MCP and streaming |
| `platform/web` | Local web UI |
| `platform/native` | Optional macOS capture helpers |
| `platform/tests` | Device-free Python tests |
| `docs` | Architecture, integration and release notes |

Some advanced operator screens and runtime errors are still in Chinese. Historical Calendar/Maps
fixture code remains for regression tests; its personal assets and recipient configuration are not distributed.
See [CONTRIBUTING.md](CONTRIBUTING.md) to help improve setup, reliability and accessibility support.

## Local or hosted?

Use this repo when you want to experiment with your own iPhone and manage its signing and USB connection.
For the hosted product, visit [phoneuse.com](https://phoneuse.com/?utm_source=github&utm_medium=readme_footer&utm_campaign=phoneuse-local)
and [PhoneUse documentation](https://docs.phoneuse.com/). These are separate deployments and credentials.

## License

MIT for the project source. Dependencies retain their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
PhoneUse branding does not grant endorsement of third-party forks.
