# Local agent navigation flow

The chat uses the program executor. The model chooses task steps; Python resolves
current targets, executes each mutation once, and returns the resulting accessibility
page. Live video is a separate viewer stream. Screenshot model input is opt-in.

## Screen observations

Screen observations scan the entire XML tree and select complete records within a
20,000-character budget. They no longer cut off a prefix of the tree. Selection removes
repeated aggregate container descriptions, duplicate records, explicit hidden subtrees,
and input descendants. Secure-field values are omitted. Ordinary field values remain
available for observation; controller verification still reads the exact field value.

Candidates are ranked using the current task, control type, enabled state, and viewport
intersection, with selection balanced across viewport bands. At most 10% of the budget
is spent on geometrically offscreen records when viewport bounds are available. Actual
visibility is still checked before clicking: bounds alone cannot prove visibility.
Long individual labels are marked `text_clipped`, so they cannot be mistaken for exact
selectors. Metadata reports node counts, omitted categories, selection method, and
whether candidate records exceeded the budget. Unselected facts are not completion evidence.

Native target references are also ranked using task relevance before the 32-target cap,
so a relevant late-tree control is not discarded simply because other matches came first.

## Native targeting

A step can use `query` for a label, or a structured `target` with `identifier`, `label`,
`type`/`types`, and `within` (a container selector). Native predicate matching is the
structured default; `strategy: "class_chain"` is also available. The host compiles
and escapes selectors, using the official WDA strategy names. Label-only lookup tries
accessibility ID, then name/label predicates on an exact-name miss. Input queries
filter by editable control types before checking candidates. No XPath is used.

Containers and final eligible targets must be unique. Failure reasons distinguish
missing/ambiguous containers, missing targets, ambiguous targets, hidden/disabled
controls, unsupported input types, and stale references. Ordinary missing targets
return immediately; only `wait_target` polls for asynchronous appearance.

An explicit editor selector remains a constraint after focusing a search control.
The editor must still resolve uniquely, and any reported active editor must match
its handle; otherwise the program replans without filling or submitting a different field.

Tasks temporarily request enriched element responses from WDA when the installed
build advertises the necessary settings. Metadata includes type, accessibility name,
label, bounds, displayed and enabled state, never input values. This removes redundant
state/rectangle requests, while the final click still rechecks displayed/enabled
immediately before tapping. Settings are restored on cleanup; idle checks and snapshot
depth are not changed.

`read_page` adds a single native discovery request to return up to 32 visible/enabled
control references. A `target: {ref: "..."}` reuses a handle only within its issuing
task/revision and while a fresh semantic page still matches. Mutations invalidate all
references. Historical target inventories are retired with historical trees.

## Local search and input

- `focus_search(query/target, editor?)` first tries an editable field. Otherwise it
  taps the uniquely resolved search/address control once, then prefers XCTest's actual
  active editor. If necessary, it resolves a unique search/text/multiline editor.
  `editor` can identify the intended editor explicitly.
- `fill_field(query/target,text)` replaces an ordinary text/search/multiline field
  once, using its WDA handle, and verifies its value. Text remains single-line so
  embedded Return/control characters cannot submit implicitly. Masked secure fields
  are unsupported and are not read. Field labels do not impose sensitive-action blocks.
- `submit_search(query/target,text,expected)` rechecks the current field value and
  only submits search/address fields. It sends Return once and waits for changed page
  content containing `expected`. Input values and keyboard content are excluded from
  destination evidence. Expected text already present prevents submission.
- `search(query/target,text,expected,editor?)` combines focus, fill, submit, and result
  verification locally, avoiding separate model turns for these mechanical operations.

Global text typing is unavailable to the program agent. Browser destination evidence
must come from rendered page content rather than an address-bar value. The model must
inspect the actual destination/results before claiming completion.

## Visual fallback

`visual_fallback` defaults to false. The composer leaves it disabled; API clients can
explicitly enable it to share screen images with the configured model. Enabling this
option does not enable native capture; the fallback uses WDA screenshots.

On a recoverable native targeting failure, an enabled task captures a full-screen
image and returns its observation ID and pixel dimensions. PNG bytes remain in memory,
except for a mode-0600 image file inside the ephemeral CLI request directory. That file
is removed when the request ends. Images do not enter task records, action metrics, or
chat history. The model receives the screenshot with its next decision via `--image`.

`visual_tap(observation_id,box,expected)` uses a normalized full-screen bounding box
`[left,top,right,bottom]`. It checks age (45 seconds), viewport dimensions, orientation,
and a native layout signature against a fresh observation before one tap. Screenshot
and viewport aspect ratios must agree; cropped or rotated mismatches are rejected.
The intended target region and a surrounding guard band (at least 12 logical points or
1.5% of the viewport on each axis) are compared between captures. The check permits small
rendering noise (at most 1% of pixels differing by over 24 luminance levels, and mean RGB
difference at most 3/255). Animation elsewhere can change without invalidating the tap,
provided native labels/bounds, orientation and viewport geometry remain unchanged.
Changes in the target region, scrolling or layout changes reject the tap. These checks
cannot guarantee that the screen will not change after the final observation.

Use `verify: "editor"` for search/address focus. It verifies a supported active editor
and returns a current target reference; page text need not change. Otherwise supply new
expected page text. An attempted tap without verified outcome returns `uncertain` and
cannot be replayed automatically. An expired/changed observation returns `needs_replan`.

## Outcomes, permissions, and recovery

- `completed`: program steps finished; the overall task may remain unfinished.
- `needs_replan`: a precondition was unmet or a visual observation expired/changed.
- `uncertain`: a mutation was attempted but its result was not verified; stop without replay.
- Transport failures also stop without replay, even if the device may have acted already.

After the initial failure plus two unsuccessful recovery plans, the runner performs a
fresh blockage review instead of immediately accepting a screen-wide blockage claim.
A model-reported `blocked` result also gets this review after an observed program step.
The review supplies a fresh selected screen, ranked eligible native references where
supported, and a screenshot only when the task opted in. Its guidance distinguishes an
unavailable target from evidence of an obstructing overlay and preserves task constraints.

An unchanged screen gets only one review. If the next attempted plan still produces no
verified progress, the runner stops; repeated blocked answers do not loop. Across changing
screens, at most three reviews are allowed per task, in addition to the existing overall
budgets. Changed page content or verified fill resets the no-progress counter. Old review
screen trees are retired together with ordinary historical observations once task notes exist.
App launches must use the installed-app inventory. Consequential actions require explicit
current-task authorization; screen content and previous tasks cannot authorize new ones.
Device permissions, leases, cancellation, a 600-second deadline, a default 100-decision
limit, and token budgets still apply.

## Context and speed measurement

The model maintains task notes with observed facts and completed and remaining subgoals.
When notes are present, two recent trees remain in full; older trees are replaced by
bounded, literal static-text excerpts (at most 2,000 characters per page and 12,000 total).
These excerpts and notes can omit relevant facts, are untrusted screen data, and cannot
be used as current target references. The model must revisit a page if needed. Relevant
app metadata is also retained.

At completion the Codex decision includes a model-generated subgoal checklist and literal
screen quotes. The runner checks that each listed completed subgoal has quotes present in
an actual observation. It allows one correction attempt if a quote is absent; a second
failure yields `unverified_result`. A match establishes quote provenance only: the runner
does not prove the checklist covers the user's entire request or that interpretations,
calculations, or visual-only facts are correct. The UI labels an accepted answer “Result
reported,” not independently verified completion. Screenshot-only evidence cannot pass
the text quote check, and such work may therefore be reported as partial or unverified.

The model defaults to low reasoning effort; `PHONEUSE_CODEX_REASONING_EFFORT` can select
medium or high. CLI requests remain ephemeral.

For a repeatable read-only comparison, run the synthetic outing evaluation from `platform`:

```sh
PHONEUSE_STATE_DIR=/tmp/phoneuse-eval ../.venv/bin/python -m evals.outing
```

It uses the local Codex login and provider usage, but no phone or personal data. It prints
aggregate timings, usage and heuristic scenario checks; it does not save task history or
screenshots. The checks do not understand arbitrary prose, so review failures and answers
when interpreting results. Run multiple samples before drawing performance conclusions.
The evaluation currently measures the existing ephemeral CLI path only. A persistent
app-server comparison would need equivalent tool disabling, cancellation, schema,
screenshot, isolation, and no-session-file guarantees before it can safely use real
phone observations; it is not enabled by this change.

Task progress includes aggregate WDA request counts/durations by lookup, observation,
state, mutation, and screenshot, and model prompt preparation, process spawn, response
wait, and prompt bytes. These metrics contain no routes, selectors, device identifiers,
field values, or images. Response wait includes CLI initialization beyond process spawn,
provider/network time, and inference; it is not a pure model-inference measurement.

## Validation

Run backend tests from `platform` with `PHONEUSE_STATE_DIR` pointing to a temporary
directory. Tests use synthetic UI/WDA fixtures and mocked model processes, never live
phones, messages, or purchases. They cover duplicate labels, scoped selectors, escaped
labels, current/stale handles, focus transitions, multiline/secure fields, delayed pages,
uncertain outcomes, late-tree selection, viewport balancing, false blockage recovery,
unrelated animations versus changed target regions, screenshot scale/rotation/change/expiry, settings cleanup, aggregate
telemetry, and private temporary image cleanup.

Synthetic comparisons show eight versus five WDA requests for one click including its
final observation, and four versus two model turns for a fixed search scenario.
These are request/turn counts, not live-device latency or shopping-success claims.
Any live navigation validation is a separate supervised run.

Safari DOM automation remains optional and unimplemented: raw WDA does not expose a web
DOM. Appium's standard WebKit debugger path additionally requires inspection access.
Third-party web views are not necessarily inspectable; the alternative native WebKit
Automation session is currently simulator-only. Do not enable inspection automatically.

## Bounded phone skills

Navigation-result verification uses native accessibility observations even in OCR
mode, so input values and keyboard text cannot serve as destination evidence.
If native evidence becomes unavailable after submission or a tap, the result is
uncertain and the action is not repeated.

`run_skill` invokes a registered local routine through a restricted observation,
resolution and click context. Skills return `completed`, `needs_replan`, or
`uncertain` and a fresh page; an uncertain mutation must never be replayed.
Skill observations use native accessibility roles and completeness metadata,
independently of the primary OCR screen mode. An unavailable native observation
cannot authorize a click or establish that a prompt disappeared.
`dismiss_cookie_prompt` handles a single uniquely identified essential-only or
reject choice on a complete accessibility observation. It taps once and verifies
that cookie text is absent from a complete subsequent observation. It does not
operate settings or use visual recognition. Register future routines in
`backend/phone_skills`, with preconditions, action limits, verification and tests.
