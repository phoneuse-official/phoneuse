# PhoneUse Local

[![Checks](https://github.com/phoneuse-official/phoneuse/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/phoneuse-official/phoneuse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Give your AI agent a real iPhone, right on your desk.**

Open-source tools for controlling a USB-connected iPhone from your Mac: a local web interface,
live screen preview, natural-language prompts, REST API, and MCP server.

<table>
  <tr>
    <td align="center" width="33%"><a href="https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/07%20-%20Google%20Maps%20Starbucks%20Share%20-%20PhoneUse%20launch.mp4"><img src="https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/readme-maps.gif" width="240" alt="PhoneUse finds a Starbucks in Google Maps"></a><br><sub>Google Maps: find a Starbucks</sub></td>
    <td align="center" width="33%"><a href="https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/17%20-%20DoorDash%20Order%20and%20Text%20Update%20-%20PhoneUse%20launch.mp4"><img src="https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/readme-doordash.gif" width="240" alt="PhoneUse orders Diet Coke on DoorDash"></a><br><sub>DoorDash: order Diet Coke</sub></td>
    <td align="center" width="33%"><a href="https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/09%20-%20GEICO%20Renters%20Quote%20Setup%20-%20PhoneUse%20launch.mp4"><img src="https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/readme-geico.gif" width="240" alt="PhoneUse starts a GEICO renters quote"></a><br><sub>GEICO: start a renters quote</sub></td>
  </tr>
</table>

**[▶ Watch the 50-second demo](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/PhoneUse%20-%20Twitter%20Launch%20-%2050s.mp4)** · Click any clip above to watch it in full · [More demos](#demo-videos)

Built by [PhoneUse](https://phoneuse.com/?utm_source=github&utm_medium=readme&utm_campaign=phoneuse-local).
Want phones without managing hardware on your desk? [Explore PhoneUse →](https://phoneuse.com/?utm_source=github&utm_medium=readme_cta&utm_campaign=phoneuse-local)

> Experimental developer preview. Bring your own Mac, iPhone, Apple signing setup, and model access.
> This project uses WebDriverAgent. It is separate from the hosted PhoneUse platform and does not
> include hosted phones, production infrastructure, or a guarantee that every app can be automated.

## What you can do

- Type a prompt in your browser and watch the phone do it.
- Open apps, read what is on the screen, tap, type, and scroll.
- Watch live video of the phone screen. Optional native macOS capture is available.
- Control the phone from your own code (REST API) or from your AI agent (MCP).
- Stop a running task at any time, and keep separate chats in the history sidebar.

Start with a reversible prompt: **“Open Safari and describe the current screen. Do not submit anything.”**
Accessibility support varies by app. A task marked finished is a model-reported result; verify important outcomes on the device.

## Demo videos

Recorded on a real iPhone with PhoneUse Local. The prompt panel on the left is added for the video, and clips are trimmed for length.
Click **▶ Watch** to play a video in your browser.

| App | What PhoneUse does | Video |
| --- | --- | --- |
| **Overview** | The 50-second launch demo. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/PhoneUse%20-%20Twitter%20Launch%20-%2050s.mp4) |
| **TikTok** | Browses the TikTok feed. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/02%20-%20TikTok%20Feed%20Browsing%20-%20PhoneUse%20launch.mp4) |
| **Instagram** | Watches Instagram Reels. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/03%20-%20Instagram%20Reels%20-%20PhoneUse%20launch.mp4) |
| **Telegram** | Sends a “good morning” message. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/05%20-%20Telegram%20Good%20Morning%20-%20PhoneUse%20launch.mp4) |
| **Google Maps** | Finds a Starbucks and shares it. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/07%20-%20Google%20Maps%20Starbucks%20Share%20-%20PhoneUse%20launch.mp4) |
| **GEICO** | Sets up a renters insurance quote. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/09%20-%20GEICO%20Renters%20Quote%20Setup%20-%20PhoneUse%20launch.mp4) |
| **Reddit** | Browses Reddit and leaves a comment. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/15%20-%20Reddit%20Browsing%20and%20Comment%20-%20PhoneUse%20launch.mp4) |
| **Amazon** | Reviews a Diet Coke order. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/16%20-%20Amazon%20Diet%20Coke%20Order%20Review%20-%20PhoneUse%20launch.mp4) |
| **DoorDash** | Places an order and texts an update. | [▶ Watch](https://pub-b1e2c1245ef644aa89f7c5da08db4154.r2.dev/17%20-%20DoorDash%20Order%20and%20Text%20Update%20-%20PhoneUse%20launch.mp4) |

> **Some of these demos send a message, post a comment or place an order.** Those are real actions on a real phone.
> Watch the phone while a task runs, and start with the read-only prompts in [docs/DEMOS.md](docs/DEMOS.md).

## Requirements

- macOS with full Xcode and an iOS version supported by that Xcode installation.
- A USB-connected iPhone that you own or are authorized to control, unlocked and trusted by this Mac.
- Developer Mode and a legitimately signed Appium WebDriverAgentRunner.
- Python 3.13, Node.js 24+, npm, and Git.
- Codex CLI installed and signed in for natural-language tasks. Model access and usage limits belong to your account.
  This integration was exercised with Codex CLI 0.154.0; its structured-output flags may change.

No jailbreak, pre-signed IPA, Apple developer image, or credential is bundled.

## Get the phone screen showing

Five steps take you from a fresh checkout to live video in the local web app.
Apple requires the WebDriverAgent (WDA) signing and Developer Mode steps; PhoneUse cannot skip them.

### 1. Install PhoneUse on the Mac

Download or clone this repository, open Terminal in the repository folder, and run the installer once:

```sh
./"Install PhoneUse.command"
```

It creates the Python environment, installs the locked backend dependencies, and builds the web app.
If it reports a missing tool, install the version listed in [Requirements](#requirements) and run it again.

### 2. Prepare the iPhone and start WebDriverAgent

1. Connect the iPhone to the Mac with USB, unlock it, and tap **Trust This Computer** if asked. Keep it unlocked during setup.
2. On the iPhone, turn on **Settings → Privacy & Security → Developer Mode**. Restart when asked, then confirm Developer Mode after the restart.
3. Get WebDriverAgent only from the official [Appium WebDriverAgent repository](https://github.com/appium/WebDriverAgent) and follow Appium's [real-device setup](https://appium.github.io/appium-xcuitest-driver/latest/preparation/real-device-config/).
4. Open `WebDriverAgent.xcodeproj` in Xcode. Select the `WebDriverAgentRunner` target, choose your Apple signing team, set a unique bundle identifier if Xcode asks for one, and select your iPhone as the run destination.
5. Run **Product → Test** (⌘U). Fix any signing, trust, or iOS version errors Xcode shows, and **keep the test running**. PhoneUse needs WDA running on the phone for live video and phone control.

See [the full iPhone setup and troubleshooting guide](platform/docs/SETUP.md) for pairing and the optional `start-wda.py` launcher. Do not start that launcher while Xcode is already running WDA.

### 3. Start the local API

In a Terminal window in the repository folder, run:

```sh
./platform/start-api.sh
```

Leave this window open. Check that the API is up by opening **http://127.0.0.1:8765/health**; it should show `"ok":true`.

### 4. Open the PhoneUse page

In a second Terminal window in the repository folder, run:

```sh
./"Start PhoneUse.command"
```

This opens **http://localhost:3109/** and connects the page to the API for you (see [Why is there an API key?](#why-is-there-an-api-key)).
The web app keeps running in the background; its log is `platform/.state/recording-web.log`.

If the page shows **Connect to your workspace** and asks for a key, close the tab and run `Start PhoneUse.command` again.

### 5. Select the phone and confirm live video

1. Find the **Your iPhone** panel on the right. In a narrow window, click **Phone screen** in the top bar.
2. Choose your phone in the phone menu under **Your iPhone**. Until a phone is found, the menu says **Waiting for a phone**.
3. Wait for the live screen. Make sure the picture is moving, not a dimmed still frame. A still frame is not a live connection.
4. Check the badge next to **Your iPhone**:
   - **Ready**: you can send tasks.
   - **View only**: video works, but phone control does not. WDA is not running or not reachable; go back to step 2.
5. If the screen does not appear, click the round-arrow button next to the phone menu (**Reconnect screen**) once.

### Turn on natural-language tasks

You do not need Codex just to see the screen. To send prompts, sign in once:

```sh
codex login
```

If the API cannot find the Codex CLI, stop the API and start it again like this:

```sh
PHONEUSE_CODEX_BIN="$(command -v codex)" ./platform/start-api.sh
```

To choose a model, also set `PHONEUSE_CODEX_MODEL` to a model your account can use.

### Optional: start the API automatically at login

```sh
.venv/bin/python platform/manage-node-service.py install
```

This adds a macOS login service named `com.phoneuse.local-node`. It starts the API when you log in and restarts it if it stops.
`Start PhoneUse.command` also starts this service if the API is not running.
Use `status` to check it and `remove` to turn it off; removing it does not delete your apps, tasks or files.
For first-time setup, run the API in Terminal (step 3) instead, so you can see its output.

## Troubleshooting

| What you see | What it means | What to do |
| --- | --- | --- |
| **“Waiting for live phone video. Reconnecting…”** | The page is not getting fresh frames. | Check the [health link](#3-start-the-local-api), select the online phone, keep the browser tab in front, and confirm WDA is still running in Xcode. Then click **Reconnect screen**. |
| **“Phone control is offline…”**, the **View only** badge, or **“Device port not open”** | The Mac can see the phone over USB, but WDA is not running or not reachable. The USB cable alone is not enough. | Repeat [step 2](#2-prepare-the-iphone-and-start-webdriveragent) and keep the WDA test running in Xcode. |
| **“Connection released. Click Reconnect screen.”** | The page's hold on the phone ended. | Click **Reconnect screen**. |
| The phone menu says **Waiting for a phone**, or the phone is marked **Offline** | The phone is locked, not trusted, or not connected. | Unlock it, confirm it trusts this Mac, reconnect USB, and wait a few seconds. |
| **Connect to your workspace** (asks for a key) | The page was opened directly, without the key. | Close the tab and run `Start PhoneUse.command`. |
| **“API is unavailable…”** when starting the page | The API is not running. | Start it with `./platform/start-api.sh` ([step 3](#3-start-the-local-api)), or install the [login service](#optional-start-the-api-automatically-at-login). |
| The page shows a different checkout, or the API reports a port conflict | Ports 8765 (API) and 3109 (web) are fixed. Another PhoneUse install already using 8765 blocks this one, and the launcher connects to whatever is already running on those ports. | See what is using the port with `lsof -nP -iTCP:8765 -sTCP:LISTEN`. Stop that copy yourself, then restart the API and the page. |
| Prompts fail with a Codex error | The Codex CLI is not signed in, not found, or out of quota. | Run `codex login status`, then see [Turn on natural-language tasks](#turn-on-natural-language-tasks). |

Where to look: API output is in the Terminal running `start-api.sh`; web app errors are in `platform/.state/recording-web.log`.
More help: [iPhone setup guide](platform/docs/SETUP.md#troubleshooting).

## Why is there an API key?

The local API can tap, type, install and remove apps, and read the phone's screen. Anything that can reach it could control your phone.

- **Other websites** are already blocked. The API only accepts browser requests from the PhoneUse page and its own docs page (an origin check).
- **Other programs on your Mac** (scripts, a bad npm or pip package, another user account on the same Mac) do not go through a browser, so the origin check cannot stop them. The key does.

You normally never type the key. The API creates it the first time it starts and saves it in `platform/.state/admin-token`, readable only by your user account.
`Start PhoneUse.command` reads that file and passes the key to the page, which keeps it only for that browser session.
You only see the key screen if you open `http://localhost:3109` directly. Never paste the key into issues or chats.

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

- **REST API:** interactive docs at **http://127.0.0.1:8765/docs** while the API is running. Every request needs `Authorization: Bearer <key>`.
- **MCP:** start the API, then set your MCP client to run the absolute path of `platform/start-mcp.sh` from this checkout. It reads the local key for you. MCP gives your agent the manual phone controls (list phones, screenshots, on-screen elements, tap, type, apps) and does not need Codex.
- **Client setup:** [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) has ready-to-copy MCP configs for Claude Code, Claude Desktop, Cursor and Codex, plus REST examples.
- **A separate key for a script:** `create-key.py` makes a key limited to the phones you name and prints it once:
  `(cd platform && ../.venv/bin/python create-key.py --name my-script --device YOUR_DEVICE_UDID)`

The key file is created locally at `platform/.state/admin-token`. Do not share it or paste it into issues.

### Settings

All settings are optional environment variables.

| Setting | Used by | What it does |
| --- | --- | --- |
| `PHONEUSE_CODEX_BIN` | API | Full path to the Codex CLI, if the API cannot find it. |
| `PHONEUSE_CODEX_MODEL` | API | Codex model to use. It must be available to your account. |
| `PHONEUSE_STATE_DIR` | API, MCP | Folder for keys, history and logs. Default `platform/.state`. Mainly for tests. |
| `PHONEUSE_WDA_BUNDLE_ID` | API, `start-wda.py` | Bundle ID of your signed WebDriverAgent runner. See the [iPhone setup guide](platform/docs/SETUP.md). |
| `PHONEUSE_API_URL` | MCP | API address. Default `http://127.0.0.1:8765`. |
| `PHONEUSE_TOKEN_FILE` | MCP | File that holds the key. Default `admin-token` in the state folder. |
| `PHONEUSE_API_KEY` | MCP | The key itself, instead of the file. |
| `PHONEUSE_AI_API_KEY` | `backend/ai_runner.py` | Model key for the experimental command-line runner only. The web app does not use it. |

Keep keys in private client configuration; never commit them. More examples: [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md).

## Privacy and local data

The server listens only on loopback. PhoneUse links are ordinary outbound links, with campaign tags;
they do not transfer phone data. The local prompt agent sends task text and phone accessibility data
to the model provider through your Codex login. This is **not fully offline inference**.

Local state includes API tokens, device inventory, task histories, logs and uploaded assets.
It lives in the ignored `platform/.state/` directory. Chat history is saved in your browser:
deleting a chat removes it from that browser only, and the API keeps its task records.
Never publish this directory or your Mac's pairing/signing files. See [SECURITY.md](SECURITY.md).

## Develop

```sh
# Backend tests; use disposable state, never your live phone configuration.
export PHONEUSE_STATE_DIR="$(mktemp -d)"
(cd platform && ../.venv/bin/python -m pytest tests -q)
(cd platform/web && npm run typecheck && npm test && npm run build)
python3 scripts/check-public-tree.py
```

| Directory | Contents |
| --- | --- |
| `platform/backend` | API, USB device control, agent, MCP and streaming |
| `platform/web` | Local web UI |
| `platform/native` | Optional macOS capture helpers |
| `platform/tests` | Device-free Python tests |
| `docs` | Integration, demo, release and validation notes |

Historical Calendar/Maps fixture code remains for regression tests; its personal assets and recipient configuration are not distributed.
Do not commit videos or screenshots: `scripts/check-public-tree.py` rejects them. Demo videos are hosted outside the repository and linked ([docs/DEMOS.md](docs/DEMOS.md)).
See [CONTRIBUTING.md](CONTRIBUTING.md) to help improve setup, reliability and accessibility support.

## Local or hosted?

Use this repo when you want to experiment with your own iPhone and manage its signing and USB connection.
For the hosted product, visit [phoneuse.com](https://phoneuse.com/?utm_source=github&utm_medium=readme_footer&utm_campaign=phoneuse-local)
and [PhoneUse documentation](https://docs.phoneuse.com/). These are separate deployments and credentials.

## License

MIT for the project source. Dependencies retain their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
PhoneUse branding does not grant endorsement of third-party forks.
