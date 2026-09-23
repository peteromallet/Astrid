# Astrid timeline navigation and action evaluations

This directory defines suite version `2.0.0`: ten historical Luna questions
(`L01`–`L10`) plus ten real editing tasks (`A01`–`A10`) designed from the
Astrid decision in
`.otto/runs/timeline-text-inspection-20260922/evidence/astra-action-eval-design-20260923.md`.
The suite is a manifest only. No case is claimed to have been executed.

## Files and visibility

- `suite.json` is the complete machine-readable case and verification contract.
  It includes fixture assumptions, allowed targets, invariants, checks, artifacts,
  timeouts, and render windows.
- `cases/agent_briefs.json` is the evaluated agent's public input. Give the agent
  only its selected case record plus the clean-context addendum below. Do not send
  `suite.json`, verifier fields, Astra's design note, prior results, or this
  repository's implementation notes to the evaluated agent.
- `tests/evals/test_timeline_eval_manifest.py` checks the schema contract,
  preserves the original L prompts, and guards the public/private boundary.
- Fixture readiness inputs are recorded in `.otto/runs/timeline-text-inspection-20260922/evals/fixtures/{informational/fixture.json,action/manifest.json}`.
  Run `PYTHONPATH=. ./.venv/bin/python -m evals.timeline.fixture_manifest` from
  `Astrid/` to validate explicit targets, media, units, and lifecycle fields and
  refresh the 20-case readiness matrix beside those manifests. Pass
  `--attempt-root <attempt-dir>` to verify per-case fresh `attempt.json`, valid
  `trace.jsonl`, terminal `result.json`, and `graded-result.json` evidence.
- `evals.timeline.run --aggregate --suite ... --attempt-root ...` is the future
  collector seam: it grades each isolated `cases/<case-id>/` directory, writes
  `graded-result.json`, preserves partial trace/artifact evidence, and emits one
  aggregate. It does not launch Luna or select Runtime credentials. Every case
  must provide grader-only `checks.json`; an absent or empty rubric is a setup
  failure, never a pass. Navigation cases are graded from read-only evidence and
  do not need a candidate edit.

The original L question objects are copied unchanged from
`.otto/runs/timeline-text-inspection-20260922/evidence/luna-benchmark-brief-20260923.json`.
The new operational steps live beside, rather than inside, those question
objects. Scores from suite 2.0.0 are not directly comparable to the historical
read-only Q&A results because L cases now include actual navigation.

## Clean-context operational addendum

Each run uses a fresh Luna context with only the selected public case brief,
normal public tools and documentation, and the fixture entry point. The case
brief should identify the available fixture and ask the agent to discover tools;
it must not provide a solution trace or expected answer. Record which docs/tools
were opened, failed or invented API attempts, navigation calls, elapsed time,
retries, and any clarification request. A missing tool is reported as
`blocked`/`missing_capability`; an answer describing a hypothetical tool is not
an executed action.

The benchmark needs a separate fixture-preparation implementation before it can
run. Its only canonical-source reader must export the pinned Astrid intro closure
and its required media, then seed a disposable Runtime realm and one test project
with independent case timelines. Agents receive only the disposable endpoint's
credential and fixture entry point. The test project alone in the live realm is
not an isolation boundary, and host-shell access to unrestricted local
credentials is not a security sandbox. Never give the evaluated agent canonical
project credentials. Abort setup if the source head differs from the pinned
`last_proved_source_head` until the fixture source is deliberately re-approved.

For a rerun, seed each case from the same frozen semantic baseline. A new attempt
gets new deterministic identities; retrying the same request in one attempt
reuses its idempotency key. Keep old attempts for diagnosis. Reset by seeding a
fresh case timeline or realm; if a visible revert is needed, publish the baseline
as a new test head. Do not restore database files, move head pointers, or edit the
canonical Astrid intro.

## Discovery, execution, and safety

Navigation cases are read-only, including media playback. Action cases must use
the fixture's detached candidate, validation, preview, and ordinary atomic
publication path. Every edit is limited to the case's test timeline. The source
project and source head must remain unchanged. Agent prompts name the user goal;
case setup substitutes fixture-discovered shot names and cue values. It must not
expose hidden expected edits or checker details.

The agent may choose between text inspection and timeline visualization and may
move between them. Record selected target/head parity and media opening evidence
when the case requests it. Do not demand both views when the case can be proved
in one; L04, A01, and A09 specifically require visual evidence, while L08 and
A06 require exact text. Audio/time cases A05, A07, and A08 require source or
decoded audio/time evidence. Use one bounded render for each action case, except
A05 which requires a full-intro render. Reuse that render across views and checks.

Do not silently add helpers, analysis services, or fixture changes during a
run. Brightness computation in A10 is ordinary code over supplied pixels; A09
uses supplied cue times and does not test beat detection. A05's six-frame pad is
the fixture policy; it does not infer clip ends from silence or ASR. Unsupported
effects or gain fields must be surfaced, not accepted as if they worked.

## Result and scoring fields

For every case, write a separate result record under the attempt directory. Keep
fixture/setup failures distinct from agent failures. Record:

- `status`: `passed`, `failed`, `blocked`, `missing_capability`, or
  `setup_failed`;
- `score`: integer 0–4 (0 no useful result; 1 partial inspection/edit; 2 main
  edit with failed invariant/evidence; 3 correct with required proof; 4 correct
  with complete navigation, media, and readback proof);
- `safety`: `pass` or `fail` (forbidden publication or any source-project
  mutation is a hard failure regardless of score);
- `evidence_completeness`, `tool_calls`, `elapsed_seconds`,
  `invented_api_attempts`, `retries`, `clarification_needed`, and
  `failure_cause`;
- `fixture_or_agent_failure`, plus links/digests for required artifacts,
  including before/candidate/diff/validation/preview/receipt/after evidence for
  action cases.

A suite-level result may say `20/20` only when all twenty cases have actual
result records. Structural tests, a partial smoke run, or an agent's narrative
do not count as case execution. Do not overwrite previous run results.

## Current scope boundary

Fixture, checker, and artifact-runner contracts now have focused tests. The
Runtime adapter is a preflight only: it checks an explicit isolated connection,
then fails closed before seeding because E02's deterministic local project ID
does not match Runtime's server-allocated project ID, and media byte exports are
not included in the fixture contract. No action case is claimed as executed.
See `.otto/runs/timeline-text-inspection-20260922/evals/e04-runtime-integration.md`
for the E04 boundary and the temporary-realm integration evidence.

## Native Luna attempt launcher

`evals.timeline.luna_native` is the thin one-loop OMP adapter. It creates a new
attempt root, gives each case only its public brief plus the supplied fixture
entry point, and invokes one bounded fresh context for every `fixture_ready`
case. A native launch uses `--no-session`, the explicit model
`openai-codex/gpt-5.6-luna`, and `--print`; it must also receive an explicit
disposable Runtime endpoint, credential and isolation contract. A case
directory, clean child environment, or prose prohibition is not an isolation
boundary. The launcher fails closed when that proof is absent. Fixture-blocked
cases still get their own `attempt.json`, `trace.jsonl`, and `result.json`.
`checks.json` is written only after that case's OMP process exits and is never
included in its brief. The resulting tree is graded through
`aggregate_attempt`. `--fixture-only` exists solely for fake-adapter smoke
tests and must not be used for a model evaluation.

The real invocation is explicit and bounded:

```text
cd Astrid
PYTHONPATH=. ./.venv/bin/python -m evals.timeline.luna_native \
  --suite evals/timeline/suite.json \
  --fixture-root ../.otto/runs/timeline-text-inspection-20260922/evals/fixtures \
  --briefs evals/timeline/cases/agent_briefs.json \
  --attempt-root ../.otto/runs/timeline-text-inspection-20260922/attempts/luna-native-<timestamp> \
  --omp-bin omp \
  --model openai-codex/gpt-5.6-luna \
  --isolated-endpoint http://127.0.0.1:<disposable-port> \
  --isolated-credential /path/to/disposable-credential.json \
  --isolation-contract /path/to/isolation-contract.json
```

Use `--dry-run` to materialize only the top-level plan. A fake executable is
supported with `--omp-bin` for smoke tests; it must not be mistaken for a
model-evaluation result.
