# PhoneUse Local

Give your AI agent a real iPhone, right on your desk.

Built by [PhoneUse](https://phoneuse.com/?utm_source=github&utm_medium=readme&utm_campaign=phoneuse-local).  
Want phones without managing hardware on your desk? [Explore PhoneUse →](https://phoneuse.com/?utm_source=github&utm_medium=readme_cta&utm_campaign=phoneuse-local)

## Requirements

- macOS with full Xcode and an iOS version supported by that Xcode installation.
- A USB-connected iPhone that you own or are authorized to control, unlocked and trusted by this Mac.
- Developer Mode and a legitimately signed Appium WebDriverAgentRunner.
- Python 3.13, Node.js 24+, npm, and Git.
- Codex CLI installed and signed in for natural-language tasks. Model access and usage limits belong to your account.
  This integration was exercised with Codex CLI 0.154.0; its structured-output flags may change.

No jailbreak, pre-signed IPA, Apple developer image, or credential is bundled.

## Get the phone screen showing

These steps take you from a fresh checkout to live video in the local web app. You need a Mac with full Xcode, Python 3.13, Node.js 24 or newer, npm, Git, and an iPhone you own or are authorized to use. WDA signing and developer-mode setup are required by Apple; PhoneUse cannot skip them.

### 1. Install PhoneUse on the Mac

Download or clone this repository, open Terminal, change to the repository root, and run the installer once:

```sh
./"Install PhoneUse.command"
```

It creates the Python environment, installs the locked backend dependencies, and builds the web app. If it reports a missing tool, install the required version listed above and rerun it.

### 2. Prepare the iPhone and start WebDriverAgent

1. Connect the iPhone to the Mac over USB, unlock it, and accept **Trust This Computer** if prompted. Keep it unlocked during setup.
2. On the iPhone, enable **Developer Mode** in **Settings → Privacy & Security → Developer Mode**, restart when prompted, and confirm Developer Mode after the restart.
3. Get WebDriverAgent only from the official [Appium WebDriverAgent repository](https://github.com/appium/WebDriverAgent) and follow Appium's [real-device setup](https://appium.github.io/appium-xcuitest-driver/latest/preparation/real-device-config/).
4. Open `WebDriverAgent.xcodeproj` in Xcode. Select the `WebDriverAgentRunner` target, choose your Apple signing team, set a unique bundle identifier if Xcode requires one, and select your physical iPhone as the run destination.
5. Run **Product → Test** (⌘U). Resolve any signing, trust, or iOS compatibility errors in Xcode, and keep the test running. PhoneUse needs WDA running on the phone for the live preview and phone control.

See [the full iPhone setup and troubleshooting guide](platform/docs/SETUP.md) for pairing and the optional `start-wda.py` launcher. Do not start that launcher while Xcode already owns an active WDA runner.

### 3. Start the local API

In a Terminal window at the repository root, run:

```sh
./platform/start-api.sh
```

Leave this Terminal window open. Confirm the API is responding by opening **http://127.0.0.1:8765/health**; it should return JSON containing `"ok":true`.

### 4. Open the PhoneUse screen

In a second Terminal window at the repository root, run:

```sh
./"Start PhoneUse.command"
```

This opens **http://localhost:3109/** and passes the local API key to the page automatically. Keep the API running. The web app runs in the background; its log is `platform/.state/recording-web.log`.

The browser remembers your local API key after a successful connection, including across tabs and browser restarts. Use the same browser and address (`http://localhost:3109/`) to reconnect automatically. Private browsing or clearing browser data removes the saved connection. If the page asks for an API key, reopen it once with `Start PhoneUse.command` so the local key is supplied. Rejected keys are removed from browser storage. If the API or page is already running on ports 8765 or 3109, the launcher may use that existing instance; stop the other local PhoneUse checkout before starting this one.

### 5. Select the phone and confirm live video

1. In the **PhoneUse Local** page, select the connected phone from the device menu on the right.
2. Wait for the live phone screen to appear. If it does not, click **Reconnect screen** once after confirming WDA is still running in Xcode.
3. Check that the image is updating, not just showing a dimmed last frame. A stale frame is not a live connection.

You do not need to sign into Codex just to view the screen. To use natural-language tasks after video works, run `codex login`. If the API cannot find the CLI, start it with `QUNKONG_CODEX_BIN` set to the absolute path returned by `command -v codex`. Optionally set `QUNKONG_CODEX_MODEL` to a model available to your account.

### If the screen still does not appear

- **“Waiting for live phone video. Reconnecting…”** means the page is not receiving fresh frames. Confirm the API health check above, select the online phone, make sure the page is in the foreground, and verify WDA is still running in Xcode. Then click **Reconnect screen**.
- **“Device port not open” / “automation: not running”** means the Mac can see the phone over USB, but WDA is not running or reachable on the phone. The USB cable alone is not enough: complete step 2 and keep the WDA test running.
- **Phone is missing or offline in the menu:** unlock it, confirm the iPhone trusts this Mac, reconnect USB, and wait for device discovery to refresh.
- **“automation: ready”** confirms the control service is ready. Live video and control status are shown separately, so check for a moving image as well before using the phone.
- If the API reports a port conflict or the page is showing another checkout, stop the other local instance before restarting the API and page. API output is in the Terminal where `start-api.sh` is running; web startup errors are in `platform/.state/recording-web.log`.

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

## Local or hosted?

Use this repo when you want to experiment with your own iPhone and manage its signing and cable connection.
For the hosted product, visit [phoneuse.com](https://phoneuse.com/?utm_source=github&utm_medium=readme_footer&utm_campaign=phoneuse-local)
and [PhoneUse documentation](https://docs.phoneuse.com/). These are separate deployments and credentials.

## License

MIT for the project source. Dependencies retain their own licenses; see [THIRD_PARTY.md](THIRD_PARTY.md).
PhoneUse branding does not grant endorsement of third-party forks.
