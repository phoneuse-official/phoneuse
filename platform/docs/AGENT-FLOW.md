# Local agent navigation flow

The chat uses the program executor. The model plans navigation; Python resolves targets,
checks their state, executes each mutation once, and returns the resulting accessibility page.
The live video remains a separate viewer stream and is not model input.

## Field entry and search

1. Observe a field's accessibility name. `fill_field(query, text)` resolves one visible,
   enabled input. Duplicate text labels are filtered out by element type; multiple
   eligible inputs remain an ambiguity and are not changed. At most twelve matches
   are inspected. Only ordinary single-line text and search fields are eligible.
2. The controller taps, clears, and enters text using the same WDA element handle, then
   checks its value. Secure inputs and credential/payment labels are rejected before
   their values are read. Field placeholders do not count as verified text.
3. `submit_search(query, text, expected)` resolves the field again and verifies the value.
   Submission is restricted to search or address fields. It sends Return to that element
   once, then polls read-only observations for a changed page containing `expected`.
   Input values, keyboard content, geometry, and enabled-state changes are excluded from
   navigation evidence. A changed page is step evidence, not proof of task completion.
   Expected text already present before submission triggers replanning without submitting.
   Browser destinations need a rendered heading or title; an address-bar value alone
   cannot verify navigation.
4. The model must inspect the returned page before claiming the user's result.

Global text typing is unavailable to the program agent. The raw/manual API remains a
separate interface with its existing capabilities; these guards are not a general
security sandbox for purchases or other consequential operations.

## Outcomes and recovery

- `completed`: the local step's condition was verified; the overall task may remain unfinished.
- `needs_replan`: a target or value precondition was unmet. No uncertain mutation is replayed.
  The model receives a fresh page and a reason and can choose a corrective plan.
- `uncertain`: entry or submission was attempted, but its effect was not verified. The task
  stops and the agent cannot repeat that mutation automatically.
- Transport exceptions stop execution without replay, including when the phone may have
  completed an action before the connection failed.

Three consecutive unsuccessful observations/plans (the initial failure plus two recovery
attempts) stop the task. A changed page or verified fill resets this count, including
when a later step in the same program needs replanning.
App launches are checked against the installed-app inventory before executing any program
mutations, so a guessed app ID returns a recoverable planning error.
Device permissions, leases, cancellation, the existing 300-second deadline, step limits,
and token limits still apply.

## Context

The structured model decision includes a bounded `task_notes` notebook for the task goal,
verified facts from earlier screens, completed subgoals, and uncertainties. Once notes exist,
the model prompt keeps the latest two screen trees plus all action/result records and notes.
Without notes, old trees remain available. Relevant installed-app IDs are retained after
initial discovery; unrelated app metadata is omitted from subsequent prompts. Notes and
screen values are not added to action metrics or persisted as new execution logs.

## Validation

Run device-free backend tests from `platform` with `QUNKONG_STATE_DIR` set to a temporary
directory. Test field replacement, wrong focus/value, placeholder values, credential and
secure inputs, stale handles, duplicate/missing targets, delayed pages, uncertain
submissions, transport failures, recovery limits, and context fact retention.
Any live navigation check is a separate supervised run, never an automated test.
