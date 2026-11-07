# Amazon app skill training experiment

## Objective and scope

Make repeated Amazon product research faster while preserving task accuracy. The pilot covers searching for products, comparing their observed pros and cons, and ranking them against a goal supplied in the current task. It does not purchase products or change account settings. A ranking must explain the criteria, evidence and tradeoffs; sponsored placement, search order and ratings alone do not establish suitability. Distinguish seller claims from independently established facts, report missing or conflicting information, and avoid inferring a con from missing data.

This is a proposed experiment, not an implemented feature. No demonstrations have been collected, Amazon skills verified, or selector trained. The general agent remains the default and fallback. PhoneUse Local stays separate from the hosted PhoneUse service.

## Current starting point

`phone_program` already supports bounded programs of up to eight steps, including search with verified input and result checks. Registered skills currently include cookie dismissal; skill selection is constrained by the `Step` schema. The existing program distinguishes `needs_replan` from an `uncertain` mutation, and timing metrics aggregate device calls without recording their contents. Use these capabilities as the baseline rather than adding a second execution path. Native accessibility and OCR have different evidence and transport limitations; measure both only where available and keep native capture opt-in.

## Pilot workflows

1. **Search:** From an observed Amazon screen, locate the search control, enter the user-provided query and verify a results page. A successful search does not prove the products meet the user's goal.
2. **Inspect a product:** From observed results, open the product the current task selects and verify its detail page. Do not hard-code a product or assume the first result is best.
3. **Collect comparison evidence:** Read task-relevant visible product details for each candidate, keeping product identity and observed source associated with each claim. Capture price or availability only as observed at the time; distinguish missing facts from negative attributes. Scroll or re-observe when needed.
4. **Compare and rank:** The general reasoning agent uses the collected evidence and the user's criteria to produce pros, cons and a reasoned ranking. This is an evidence-based task, not a predetermined navigation macro. If the goal or necessary evidence is missing, say so and qualify the result.

The exact screen identifiers and skill boundaries require a real demonstration. They must not be guessed from app branding or trained examples. Screen changes, localized labels, sponsored results, variants, loading states and overlays are expected.

## Demonstrations and privacy

Start recording only after explicit, per-session opt-in identifying the Amazon app, what will be collected, and how to stop and delete it. Provide visible recording status and a stop control. Stopping ends capture immediately; deletion removes the local session and derived training examples, and marks any model trained on those examples for retraining or removal. Establish a retention period before collection; default to deletion rather than indefinite retention. No passive background capture.

Collect a demonstration in memory first and require review before saving. Persist a minimal, versioned representation: a random session identifier, app version or coarse version category, approved screen category, reviewed action/skill category, precondition and outcome category. Use a reviewed allowlist of static control labels only when essential; never assume arbitrary accessibility text is safe. Do not persist screenshots, raw trees, product searches, product names, prices, user goals, account details, input values, device identifiers, contacts, or full task history as training data. Product evidence needed for the active answer remains ephemeral and follows the existing task data policy. A categorical record may still be sensitive; store it in `PHONEUSE_STATE_DIR` with private permissions, keep it out of git, and provide inspection and deletion. Do not commit state, datasets, model weights or derived traces.

Review sanitized records and their labels before training. Automated redaction is not a guarantee: reject unknown fields and free text by default, test with synthetic secrets and personal data, and block saving if review or sanitization fails. Log aggregate counts only. Do not transmit recordings or examples to a remote training service without a separate explicit choice that identifies the provider and data sent.

## Execution and fallback contract

Each eventual skill is a bounded, registered routine with a documented task authorization, app and screen preconditions, unique fresh targets, expected outcomes, and tests. The selector recommends a registered skill; it cannot supply executable code, authorize actions, or override current task constraints. Validate the app and current screen independently before executing. Use locally verified operations already supported by `phone_program`; batch predictable actions only when each action's own preconditions and results are checked. A model must not guess coordinates or reuse stale handles.

If the app, screen, target or selection is uncertain before an action, abstain and return a fresh observation to the general agent. If an action may have occurred but its outcome is unverified, stop with `uncertain`; do not automatically replay it or let the fallback repeat it. Preserve the existing behavior for unavailable native accessibility or OCR, and use visual fallback only when explicitly enabled. Comparison and ranking never bypass evidence collection just because a selector is confident.

## Phased implementation

1. **Baseline and demonstration:** Connect the opted-in iPhone and select a concrete search and goal. Measure the current general agent from comparable starting states. Observe a small set of successful and unsuccessful Amazon sessions, review sanitized records, and document actual controls and screen transitions. No training yet.
2. **Verified skills:** Implement a small set of reusable navigation routines only where real observations support reliable preconditions and postconditions. Add tests for duplicate, absent, disabled or stale targets, overlays, incomplete observations and uncertain outcomes. Keep evidence gathering and ranking in the general agent. Compare skills with the baseline before introducing a model.
3. **Selector baseline:** Implement a deterministic mapping from reviewed task and screen categories to eligible skills, with abstention. This establishes whether learning is needed at all. Evaluate the mapping without executing its recommendations first.
4. **Small-model experiment:** If enough reviewed examples cover the relevant states, fine-tune a small classifier or language model to choose among registered skills and an abstain option. Choose a model and training method only after measuring data volume and available hardware. Do not train from scratch. Train and evaluate offline; model output is advisory and subject to the same independent guards as the rules baseline. Store artifacts only in the private state directory.
5. **Shadow and limited opt-in trial:** First compare recommendations to the current agent without executing them. Then, only after the gates below pass, allow explicitly enabled skill execution with fallback. Keep the general agent available and make disabling the experiment immediate.

## Evaluation and decision gates

Before collecting evaluation data, define a fixed set of search, comparison and ranking tasks across multiple product categories and starting states. Include ambiguous targets, missing facts, loading, overlays, app changes, and unsupported screens. Use the same task definitions and comparable conditions for the existing agent, deterministic selector, and trained selector. Randomize run order where practical; repeat runs and report sample sizes and variability. Split by demonstration session before training, and hold out whole tasks or product categories and changed app states to limit leakage. Never use evaluation sessions to tune the model or thresholds.

Track end-to-end task completion, incorrect or unauthorized actions, evidence-supported claims, ranking agreement with the stated criteria, abstentions and recovery outcomes. Also measure elapsed time, model calls, screen reads, device calls and their timings. Compare screenshot/OCR and accessibility modes separately rather than attributing transport differences to the model. Use the existing aggregate timing buckets and extend them without storing screen content. A comparison succeeds only when the requested candidates and criteria are addressed and material claims are supported; partial evidence is reported as partial, not success.

Initial proposed gates, to be agreed before evaluation: zero unauthorized or replayed uncertain actions; no regression in task completion or evidence support versus the baseline; and a meaningful median time reduction, with a target of 20% on repeated comparable tasks. Report tail latency as well as the median. These are pilot targets, not statistical guarantees: a small number of runs cannot establish safety or generalization. If data is insufficient, results regress, the app changes, or selectors cannot reliably abstain, remain in shadow mode or fall back to the general agent. Fine-tuning is justified only if it improves on the deterministic selector enough to offset its added complexity.

## Next inputs

Choose a concrete example query, product category and ranking goal, then connect the iPhone with Amazon ready. Agree on recording consent and retention before the first demonstration. The first run should establish actual screen behavior and baseline timings, not assume an app layout or promise human-speed performance.
