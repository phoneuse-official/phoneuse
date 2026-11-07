# Set up your iPhone

## 1. Install and sign official WebDriverAgent

Install full Xcode from Apple. Connect your iPhone, unlock it, and accept the trust prompt yourself.
Enable Developer Mode in iPhone Settings and complete the required restart and confirmation.
On the unlocked iPhone, also enable **Settings → Developer → Enable UI Automation**. If the
setting is enabled after WDA starts, restart the WDA test runner so it receives a fresh session.
An authorization error can also mean the existing session needs restarting; it does not prove
the setting is disabled.

Obtain WebDriverAgent from the official [Appium repository](https://github.com/appium/WebDriverAgent).
Follow [Appium real-device setup](https://appium.github.io/appium-xcuitest-driver/latest/preparation/real-device-config/).
Open `WebDriverAgent.xcodeproj`, select the `WebDriverAgentRunner` target and your own signing team,
choose a unique bundle identifier, select your physical iPhone, and run **Product → Test (⌘U)**.
Keep this test running. Resolve signing, trust and Xcode/iOS compatibility errors before continuing.
Personal-team profiles can expire; renew them through Xcode. This repository does not bypass signing.

## 2. Start the local API and verify

From the repo root, run `./platform/start-api.sh`. Open the website through `Start PhoneUse.command`.
Select the attached iPhone. Check both fresh live video and `automation: ready` before sending a prompt.
A display of the last frame is not proof of a healthy control connection.

If pairing needs attention, run `.venv/bin/python platform/pair-device.py YOUR_DEVICE_UDID`.
Find your own device identifier in Xcode; never copy one from a screenshot or issue.

An alternative to keeping Xcode tests running is:

```sh
.venv/bin/python platform/start-wda.py YOUR_DEVICE_UDID --bundle-id YOUR_SIGNED_RUNNER_ID.xctrunner
```

Use the actual installed runner bundle ID. This launcher requires compatible Apple developer support
installed by Xcode; no developer images are shipped here. Do not start it while Xcode already owns an active runner.
For optional recovery, `PHONEUSE_WDA_BUNDLE_ID` must be set in the API process environment to the same
runner ID before enabling recovery. Otherwise recovery uses Appium's default bundle ID and may fail.
Recovery restarts only a runner it manages. If an externally managed runner is reachable but cannot
capture the screen, restart its test session in the tool that launched it. Recovery waits until the
phone is idle and does not replay a task's last action.
Never replay an uncertain purchase or message after a disconnect; check the app first.

## 3. Video

WDA MJPEG is used when available. If its USB stream is unavailable, the preview automatically polls
WebDriverAgent screenshots over the existing USB connection at a lower frame rate. This avoids
requiring a separate capture-device mapping for a working preview.
Optional native capture can be built with `.venv/bin/python platform/build-native.py`.
The helper `platform/.state/bin/probe-capture` lists local capture IDs. Bind only the verified device
in `platform/.state/native-capture.json` as a JSON mapping from its UDID to its capture ID.
Native capture can change the USB capture mode on some setups. If control drops, remove that mapping,
close all preview tabs, wait for capture to release, restart WDA, and reopen the preview.

## Troubleshooting

- **Send disabled:** verify phone unlocked, selected device correct, and WDA running.
- **Invalid session after restart:** refresh observation/reconnect; do not blindly retry a write action.
- **Video paused:** return to the foreground browser tab; the UI pauses background video.
- **Model error:** verify `codex login status`, CLI availability and account quota.
- **Port already in use:** another checkout or an older install may own 8765/3109. Check with
  `lsof -nP -iTCP:8765 -sTCP:LISTEN`, stop that copy yourself, then start this one. Do not run two installations on the same ports.
- **Agent cannot find a visible button:** some apps omit accessibility elements. Use manual control or another task.

## Optional login service

`platform/manage-node-service.py install` registers the current checkout as a macOS login service.
It registers the service `com.phoneuse.local-node`, so inspect `status` before using it. An older
`local.qunkong.iphone-node` service is removed only when it runs this same checkout.
Use `remove` to unregister it. Foreground startup is recommended for first-time setup.
