# Apple iPhone Mirroring implementation plan

Status: proposed integration; not implemented in this checkout.

This branch contains [standalone feasibility probes](../experiments/mirroring/README.md).
It does not contain a managed Mirroring helper package, Python transport, binding API,
Mirroring viewer integration, or manual typing panel. Manual ASCII append and autonomous
Mirroring control are planned capabilities, not available PhoneUse features.
This plan concerns PhoneUse Local, separate from the hosted PhoneUse service.

## Current scope

The checked-in probes explore window inspection, capture, pointer routing, scrolling,
and developer-connection HID operations. They are explicitly invoked experiments,
not production request handlers. Their presence does not establish successful phone
input, reliable device association, independent desktop input, or release readiness.
No live-task records, screenshots, private identifiers, or measured run histories are
included here. Existing PhoneUse USB/WDA behavior remains separate.

## Proposed architecture

Introduce an opt-in `mirroring` transport alongside the existing USB/WDA path. Keep
API authentication, leases, task reservations, physical-device serialization, and audit
orchestration in Python. A managed native helper would own window and developer-connection
operations through bounded private stdin/stdout IPC, without a new network listener.
The model must never choose a PID, window identifier, executable, service, or raw HID bytes.

Create the helper package, transport adapter, binding endpoints, and capability-aware
UI together. Do not add a documentation-only feature flag or advertise unsupported tools.
Any reused protocol implementation needs pinned provenance, license review, and compatible
platform validation. Only official WebDriverAgent sources may supply WDA components.

## Binding and observation requirements

- Associate the intended physical phone, active mirrored display, and Mac window
  unambiguously with explicit user confirmation; reject multiple candidates.
- Keep private device/window/display identifiers and bindings in memory. Share the
  physical phone's authorization, lease, reservation, and serialization boundaries.
- Bind observations to a frame ID, binding epoch, geometry revision, and short lifetime.
  Invalidate pending input on reconnect, resize, move, permission loss, or session change.
- Calibrate the phone viewport rather than reusing whole-window probe coordinates.
  Normalize actions to the phone image and reject unsupported orientation or geometry.
- Keep capture opt-in, including native capture. Local capture does not authorize
  screenshot transmission to a model; retain a separate explicit choice for that.
- Treat OCR words and icons as visual candidates, not native roles or proof of focus.
  Do not silently switch to another phone, capture method, or WDA after failure.

## Action and typing requirements

Start with explicitly supported observation and pointer capabilities. Add bounded
scrolling and Home only with transport-specific implementation and validation. A dispatch
acknowledgment is not proof of navigation. Return observed, unverified, refused, or unknown
outcomes distinctly, and never automatically replay an uncertain mutation.

Manual ASCII append is a later, separate opt-in milestone. A proposed first version
would accept a short printable US ASCII string into a user-prepared ordinary field,
with no clear/replace, clipboard, Return, or implicit submission. Validate the entire
request before dispatch and check cancellation, binding, and lease deadlines between
reports. Key-release cleanup must remain bound to the original session.

Agent typing requires an additional gate: fresh identification of the intended ordinary
field, secure-field refusal, reliable focus verification, and exact outcome verification.
OCR or a coordinate click alone cannot establish those conditions. Keep autonomous text
entry unavailable until that gate is implemented and validated.

## Implementation and release gates

1. Define the transport contract and preserve existing WDA behavior.
2. Package the native helper with bounded IPC, cancellation, deadlines, and sanitized errors.
3. Implement consent, association, calibration, binding lifecycle, and coherent frames.
4. Add capability-driven API, MCP, agent, viewer, and setup integration together.
5. Add manual typing only after its separate field/layout and outcome gates pass.
6. Validate before documenting any integrated feature as available.

Automated tests must use synthetic fixtures and temporary `PHONEUSE_STATE_DIR` storage
from `platform`. Cover authorization, unsupported actions, stale identities, malformed
IPC, helper failure, lease expiry, cancellation, and unknown outcomes without replay.
Live acceptance is a separate explicitly authorized activity. It must assess device
association, actual input delivery, concurrent desktop use, covered/minimized windows,
geometry changes, permissions, pause/reconnect, and cancellation. No latency or reliability
claim is established by the source code or this plan.

Rollback must disable the feature, stop the helper, invalidate pending input and bindings,
and release capture resources while leaving USB/WDA operation intact. Keep the integration
opt-in until its release gates pass.
