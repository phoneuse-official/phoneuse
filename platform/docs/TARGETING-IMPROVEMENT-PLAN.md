# Faster, more reliable iPhone targeting

## Recommendation

Keep official WebDriverAgent (WDA). Add a local targeting layer that resolves intent
into a current element handle using structured selectors, falls back to screenshot
location when accessibility is incomplete, and verifies the result of each action.
Use the model to choose goals and interpret results; handle routine resolution and
execution locally. Implementation status and remaining optional integrations are listed below.

## Implementation status

Implemented native structured selectors and container scopes, current-page references,
enriched responses with settings restoration, immediate failure categories, active-editor
focus handling, a combined local search routine, opt-in screenshot grounding, one-shot
visual taps with page/editor verification, and aggregate WDA/model timing counters. Whole-tree task/viewport selection now
replaces prefix truncation, target inventories are ranked before capping, and bounded
fresh-screen reviews challenge premature blockage claims. Visual validation compares
the target region plus native layout instead of requiring the entire image to match.
See `AGENT-FLOW.md` for the current API and behavior.

Device-free comparisons verify eight versus five WDA requests for a click including its
result observation, and four versus two model turns for a fixed search scenario. Live
latency and reliability targets require separate supervised validation.

The optional Safari DOM route was evaluated against official documentation and remains
unimplemented because it requires an additional Appium/debugger integration and device
inspection access. Persistent model transport also remains an evaluation item: process
spawn and CLI response wait are now measured separately, without changing login/access
or introducing a new provider. No native capture or inspection settings were enabled.

## Baseline implementation limitations

1. `service.py` implements `find_elements` only through exact `accessibility id`.
   Visible labels can differ from identifiers; duplicate names cannot be scoped.
2. `phone_program.py` polls the same query until its timeout, including repeated
   state/input checks when the available evidence is unchanged.
3. A successful ordinary click path can require eight WDA requests: lookup;
   displayed/enabled/rect; displayed/enabled/click; and final source retrieval.
   Input paths repeat still more checks. A single backend call is not a single WDA call.
4. Source observations contain geometry but no executable element handles. The agent
   sees screen descriptions and must locate the target again.
5. Program mode has no screenshot-grounded tap action. Its allowed standalone actions
   are only swipe and active_app, although lower-level coordinate taps already exist.
6. Inputs support only ordinary single-line text/search fields. Some app controls need
   a tap to reveal the actual editor; multiline controls are not supported.
7. Each decision launches an ephemeral CLI process and reserializes history. Startup,
   prompt processing, and inference have not been timed independently.

## Phase 1: Fix native targeting and remove duplicate work

Priority: first implementation slice; no new automation framework required.

- Add a structured target: identifier, label, element type, container, and optional
  observed value. Prefer exact identifiers, then scoped predicates, then class chains.
  Compile selectors locally with correct escaping; do not accept arbitrary code.
- Use official WDA `predicate string` and `class chain` strategies. These are the raw
  WDA names; Appium's public `-ios ...` aliases must not be passed through unchanged.
- Return candidate handles plus type, name, label, bounds, and relevant state together
  where the installed WDA supports enriched element responses. Measure the cost of
  those attributes rather than assuming enrichment is always cheaper.
- Present task-local element references, tied to WDA session and observation revision.
  Reuse handles within that revision; invalidate on navigation, scrolling, keyboard
  transitions, session changes, or stale-handle errors. A reference is not a permanent ID.
- Add `click(target)` and `fill(target,text)` executor operations. Combine resolution,
  final target checks, mutation, and result observation without duplicate rect/state reads.
  Preserve the final check immediately before mutation; fewer requests are not atomicity.
- Return specific failure reasons: missing, ambiguous, hidden, disabled, unsupported
  input type, stale handle, or unexpected focus. Switch strategy on a definitive miss;
  reserve polling for controls expected to appear asynchronously.
- Add local focus handling: tap the observed search/address control, observe the editor
  transition, find the actual editable field, fill it, and verify the value. Do not keep
  treating the pre-focus button or container as an editable field.

## Phase 2: Add visual targeting as a fallback

- Use a fresh WDA screenshot with the accessibility candidates when native targeting
  fails. The model or local OCR proposes a bounding box for the intended control.
- Map screenshot pixels to logical screen coordinates using actual dimensions and
  orientation; account for crop/scale, browser chrome, keyboard, and viewport changes.
- Tap an interior point in the identified control once, then verify the expected focus
  or screen change. Avoid cached coordinates and blind repeated taps.
- Require a fresh observation when the screen changes between locating and executing.
  Do not assume that an element rectangle proves it is unobscured.
- Make screenshot model input an explicit task option because this sends screen pixels
  to the configured provider. Reuse WDA capture; keep native capture opt-in.
- Keep screen images and target evidence transient; do not commit or persist personal
  screens or task history in benchmark artifacts.

## Phase 3: Reduce model turns and improve recovery

- Introduce local skills such as focus_search, search, choose_size, and verify_cart.
  Each skill has observable preconditions and success conditions. Stop the chain and
  return fresh evidence when a step requires interpretation.
- Recover in this order: resolve a more precise native target; reveal/focus the editor;
  use visual targeting; switch a task-appropriate route. Do not repeat an identical
  lookup against unchanged evidence merely because the task remains unfinished.
- Measure CLI startup, prompt bytes, model response latency, lookup, state checks,
  mutation, and verification separately. Evaluate a supported persistent model
  transport after measuring startup overhead; do not assume process reuse alone
  eliminates inference latency or replace local account access without review.
- Keep compact verified task memory, selected current targets, and the latest relevant
  observation in the decision prompt. Preserve facts needed for final task verification.
- Do not globally turn off WDA idle checks or reduce snapshot depth to conceal missing
  targets. Benchmark per-setting changes and restore session settings after tasks.

## Phase 4: Optional Safari DOM path

For inspectable browser content, evaluate Appium's standard WebKit remote-debugger web
context. DOM selectors can target web inputs/buttons more precisely than a native
accessibility tree. Safari chrome still needs native or visual targeting.

This is an additional integration, not something raw WDA provides. Real-device Safari
requires Web Inspector; third-party WKWebViews must expose inspectability and cannot be
assumed accessible. Current Appium documentation marks the alternative
`mobile: startAutomationSession` route as simulator-only; do not use that route on the
physical phone. Do not make enabling inspection or switching accounts automatic.

## Validation and acceptance

Automated checks use mocks and synthetic UI fixtures, not a live phone. Cover duplicate
labels, identifier/label mismatch, stale handles, delayed editors, input type changes,
keyboard transitions, overlays, rotation, screenshot scaling, and uncertain mutations.

Collect aggregate timings and failure categories without text, identifiers, screenshots,
contacts, or task histories. Use synthetic search/address cases in fixtures.
Conduct any live checks separately under explicit supervision.

Proposed targets, to validate on the same phone and app versions:

- At least 95% correct target selection across a labeled synthetic fixture suite;
  ambiguous cases must be reported rather than counted as successful clicks.
- Reduce the common native click path from eight WDA requests to at most four, if
  enriched responses on the installed WDA make this possible without losing final checks.
- Native lookup plus click p50 below 1 second and p95 below 2 seconds, excluding
  application loading and model time. These are engineering goals, not measured results.
- At least 50% fewer model turns on a fixed navigation-only scenario versus baseline.
- Define task-specific observable success conditions before claiming completion.
  Never auto-replay an uncertain mutation.

## Sources

- Official WDA selector routes and raw strategy names:
  https://github.com/appium/WebDriverAgent/blob/master/WebDriverAgentLib/Commands/FBFindElementCommands.m
- Appium native selector guidance and performance ranking:
  https://github.com/appium/appium-xcuitest-driver/blob/master/docs/reference/locator-strategies.md
- Enriched element responses, snapshot depth, first-match and idle settings:
  https://github.com/appium/appium-xcuitest-driver/blob/master/docs/reference/settings.md
- Web context prerequisites and real-device limitations:
  https://appium.github.io/appium-xcuitest-driver/latest/guides/hybrid/
