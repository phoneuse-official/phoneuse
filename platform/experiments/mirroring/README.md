# iPhone Mirroring feasibility probes

Status: standalone experiments only. This checkout has no packaged production Mirroring
helper, Python transport, binding API, integrated viewer, or manual typing panel.
The [implementation plan](../../docs/IPHONE-MIRRORING-IMPLEMENTATION-PLAN.md) describes
proposed work, not an available opt-in feature. These probes concern PhoneUse Local,
not the hosted PhoneUse service.

## Included tools

- `probe.swift` and `run.sh`: window inspection, permission diagnostics, capture, and
  explicitly requested input probes.
- `scroll_route.swift` and `run-scroll.sh`: isolated window-addressed scroll routing.
- `keyboard_receiver.swift`: a disposable Mac-side receiver for controlled input checks.
- `direct_probe.py` and `coredevice_hid_probe.swift`: developer-connection protocol probes.
- `build-direct-hid.sh`: builds against an explicitly supplied external checkout after
  checking its pinned revision. That checkout and its built executable are not bundled.

Do not invoke these scripts from production API handlers. No transport capability,
phone/window association, successful input delivery, or non-interference guarantee follows
from a probe compiling or returning a dispatch acknowledgment. Private APIs and
undocumented fields require separate compatibility and acceptance work.

## Explicit invocation

From the repository root, read-only entry points include:

```sh
sh platform/experiments/mirroring/run.sh status
sh platform/experiments/mirroring/run.sh inspect
```

The runner builds into a temporary directory. Window inspection may require macOS
permissions. Permission requests are separate explicit commands; the application does
not grant permissions, connect a phone, change trust, or enable Developer Mode for you.
Capture is a separate opt-in operation. Do not publish captured images or identifiers.

Input probes require explicit invocation and the script's confirmation flags. Inspect
the current script before running it, use disposable content, and verify the intended
phone and coordinates. Probe coordinates may describe the whole Mac window, including
chrome, and must not be reused as normalized phone-image coordinates in a future API.
Never retry an uncertain mutation automatically.

## Validation boundary

Use synthetic fixtures for automated tests. Any live acceptance must be separately
authorized and must independently check actual phone changes, desktop focus/pointer
interference, keyboard cross-delivery, permission failures, geometry changes, and
reconnection. Capture freshness and dispatch acceptance do not prove task completion.

Keep screenshots, device identifiers, pairing/signing assets, private state, input
contents, and live-task histories out of version control. This document intentionally
contains no recorded experiment runs or claims of integrated transport validation.
Manual ASCII append and agent typing remain proposed integration work.
