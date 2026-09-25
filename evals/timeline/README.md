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
  `evals.timeline.fixture_manifest` remains an optional fixture diagnostic; it
  is not a prerequisite or admission gate for the local loop below.
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
credential and selected-case fixture package. The local worker boundary makes
the selected case package, public Astrid product package/docs, and the
explicitly supplied disposable credential visible; canonical roots,
evaluator/coordinator evidence, sibling cases, and Runtime backing stores are
denied. This is filesystem confinement for the worker launch, not a claim of
full network isolation, and outcome judging remains external to the worker.
Never give the evaluated agent canonical project credentials. Abort setup if the source head differs from the pinned
`last_proved_source_head` until the fixture source is deliberately re-approved.

For a rerun, seed each case from the same frozen semantic baseline. A new attempt
gets new deterministic identities; retrying the same request in one attempt
reuses its idempotency key. Keep old attempts for diagnosis. Reset by seeding a
fresh case timeline or realm; if a visible revert is needed, publish the baseline
as a new test head. Do not restore database files, move head pointers, or edit the
canonical Astrid intro.

## Discovery, execution, and safety

For an existing timeline, the agent-facing golden path is owned by
`astrid/packs/video_editing/skill/SKILL.md` (installed view:
`packs/video_editing/SKILL.md`): open/pin → inspect the exact target → choose
text, visual/input, or media evidence → edit a detached candidate → validate
and diff → render only when pixel/playback evidence is needed → publish →
reopen and read back. `astrid/packs/rendering/skill/SKILL.md` is the downstream
render/playback evidence compatibility route. The coordinator attributes
worker JSON/protocol health separately from semantic outcome, which is judged
from independent before/after/readback and render/playback artifacts.

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

Fixture, checker, artifact-runner, public-target-locator, and independent
readback contracts have focused tests. A real disposable AgentBox A01 canary
proved the isolation boundary and then exposed a genuine agent failure: Luna
published a new head but edited a different shot while reporting success. That
attempt is retained as failed evidence and its disposable workspace is
quarantined. The follow-up gate is to rerun A01 with the locator/readback path,
then proceed to the one-loop suite only if the independent grader catches the
wrong-shot case and accepts the correct-shot case. No canonical project or
timeline was mutated.

## Local loop

`evals.timeline.local_loop` is the single local case-launch command. It runs
selected cases sequentially, with a fresh OMP process and workspace per case.
Fixture readiness and the older admission rehearsal do not gate a launch.
Each executed case is wrapped in the enforced macOS worker filesystem boundary:
the selected `work/project/` package, public product docs, and result capture
are available, while coordinator/evaluator/sibling/canonical/runtime-storage
paths are denied; only the disposable credential file is re-opened from its
denied store. If that boundary cannot be constructed, the worker is not
launched. The loop records OMP output and the worker's `result.json`, but does
not score the answer; semantic outcome judging remains external and a human
review is still required.

From `Astrid/`, run:

```sh
PYTHONPATH=. ./.venv/bin/python -m evals.timeline.local_loop \
  --attempt-root ../.otto/runs/timeline-text-inspection-20260922/attempts/local-loop-<timestamp> \
  --execute \
  --model openai-codex/gpt-5.6-luna
```

Without `--execute`, the command writes a no-model attempt plan. Use repeated
`--case <id>` options to select cases and `--timeout-seconds` to override each
case timeout. A successful OMP exit is recorded as `completed` only when its
workspace contains a valid `result.json`; process failures and timeouts remain
in the attempt evidence, and the loop continues to the next selected case.
OMP's JSON trace and stderr log are stored beside each case workspace. The
loop never retries a case or overwrites an existing attempt record.

## Historical native launcher and admission evidence

The following admission rehearsal, `luna_native`, and evidence-collector notes
describe older runs and integrations. They remain available for those
consumers, but they are not prerequisites or part of the local-loop launch
path.

### No-model admission rehearsal and generic evidence

The older `python -m evals.timeline.admission_rehearsal` command took an
explicit `--output-root`, materialized offline entrypoints in a temporary
directory, and emitted one row for every case. A missing action target receipt
or edit route was `blocked-essential-input`; playback-only limitations (such
as L10) were recorded as `diagnostic-only` when the offline/decode path
remained available. This result does not gate `local_loop`.

That command preserved its JSON/Markdown evidence when the requested scored
scope was blocked, and exited with status `2` whenever any row was
`blocked-essential-input`. That status describes the old admission workflow,
not a requirement for local-loop launches.

`evals.timeline.evidence_collector` is the projection-neutral coordinator
collector. It retains the actual worker transcript/final response and brief
fingerprints, requires host confirmation that the worker and descendants are
stopped and cannot write, then reads the committed Runtime closure through a
host reader. The closure's actual pinned shot/internal dependencies are the
authority, including newly created or duplicated shots. Runtime realm
retirement happens only after `after.json` is written. Worker-authored
`before`/`after`/closure claims are rejected rather than promoted to evidence.

`evals.timeline.luna_native` is the thin one-loop OMP adapter. It creates a new
attempt root, gives each case only its public brief plus the supplied fixture
entry point, and invokes one bounded fresh context for every `fixture_ready`
case, sequentially. The authoritative mode is local-disposable: each brief
contains an explicit `case_folder` and `runtime_project_id`, and the launcher
uses a local subprocess with no AgentBox/X1/container/network/credential or
host-teardown prerequisite. A native launch uses `--no-session`, the explicit
model `openai-codex/gpt-5.6-luna`, and `--print`; timeout cleanup kills the
worker process group and stdout/stderr are retained in `trace.jsonl`. The old
typed host-boundary path remains available only as an explicit compatibility
mode (`--execution-mode host-boundary`). Fixture-blocked cases still get their
own `attempt.json`, `trace.jsonl`, and `result.json`.
`checks.json` is written only after that case's OMP process exits and is never
included in its brief. The resulting tree is graded through
`aggregate_attempt`. `--fixture-only` exists solely for fake-adapter smoke
tests and must not be used for a model evaluation.

For a live seeded case, the coordinator also places a public `target.json`
containing the disposable endpoint, server-assigned IDs, and a semantic target
locator (for example, A01's opening occurrence and `shot_b01`). It never
contains the replacement answer or hidden checks. The launcher reads that
locator before the model starts and again after it exits by following the
current parent head and its pinned shot/internal revisions. It writes private
`before.json`/`after.json` snapshots only after the model exits, and A01's
hidden checks grade the exact active media plus protected timing, voice, and
overlay fields. An agent's `result.json` or publication receipt cannot by
itself make the case pass.

The target is supplied through a coordinator-owned preparation root, passed as
`--prepared-targets-root`. The launcher copies only
`<root>/<case-id>/target.json` into the fresh case directory after validating
that the root, case directory, and file are regular non-symlink paths. A live
A01 run without this explicit target is recorded as `setup_failed` and does
not start OMP. Independent pre-readback failures (including stale heads,
missing protected roles, or an unreadable disposable realm) are also
fail-closed; the model is never launched against an unverified target.

Older `luna_native` invocations may appear in archived run evidence. For new
local case launches, use the `local_loop` command above. Its default per-case
timeout is 600 seconds (10 minutes); pass `--timeout-seconds` only when a
different bound is intentional.
