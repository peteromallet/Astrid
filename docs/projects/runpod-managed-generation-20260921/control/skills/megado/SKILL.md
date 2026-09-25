---
name: megado
description: "Plan and deliver substantial work with explicit coordinator/oracle roles, cheap delegated exploration, normal-model implementation, and bounded evidence-based review. Use when the user requests Megado or a coordinated plan/execution run; supports planning-only work."
---

# Megado

**The coordinator runs the agreed process; the designated oracle owns consequential judgment. Use cheap agents to establish facts and challenge complexity. Deliver the smallest complete outcome that preserves required behavior. Test continuously, review proportionately, and add process only for a concrete risk.**

User instructions, including planning-only scope and review overrides, control the run. Do not turn a discussion of a desirable future capability into an implementation obligation. Do not require the user to override default role assignments to retain their chosen judgment owner.

## Choose the mode

- **Planning only:** inspect, explore and produce a concrete plan/tasklist with decisions, uncertainties, estimate and validation approach. Stop there. No execution tests, implementation worktree, deployment preparation, certification packet or independent contract review is required merely to plan.
- **Delivery:** plan enough to execute, implement in the source custody explicitly chosen at kickoff, test and integrate, review under the policy below, then sync only as authorized. Read [execution mechanics](references/execution.md) before source mutation or executable certification.
- **Unattended/cloud delivery:** also read [AgentBox handoff](references/agentbox.md) when a cloud handoff is actually needed. Do not load or perform cloud setup for ordinary planning.

For a plan-only source inspection, record the repository/ref and dirty state, use read-only access, and identify whether uncommitted material is included. A detached snapshot is optional when concurrent changes make the source ambiguous. Do not silently exclude authoritative dirty work. Use the run location and structure below for planning as well as delivery; do not create empty execution directories or stage/commit product source for planning.

## Run location and structure

For a new run, set `PROJECT_ROOT` to the invoking repository and `OTTO_DIR` to `$PROJECT_ROOT/.otto/runs/<run-id>/`. The directory is spelled `.otto`. Inspect existing runs first and resume the matching run rather than create a duplicate. Use another control root only when the user explicitly selects one; record it once. Keep architecture/product documents at their existing source paths and link them from the run.

The minimum setup structure is:

```text
.otto/runs/<run-id>/
  run.yaml          # sole model, stage and budget declaration
  northstar.md      # enduring direction
  agent_goal.md     # scope, authority and links
  plan.md           # approach, assumptions and estimate
  tasklist.md       # outcomes, dependencies, routes and proof
  status.md         # mode, counters, source identity and next action
```

Add source-state records, implementation criteria or a launch README only where useful. Create briefs, receipts and evidence directories when actual work produces them; planning-only setup needs no execution scaffolding. Report the canonical run path when handing off.

Control storage and source-branch custody are independent. Before any delivery
mutation, Megado must explicitly ask (or record the user's already-given choice):
work directly on the invoking repository's `main`, or create an isolated
worktree. If a worktree is chosen, it must be inside the relevant repository at
`<repo>/.otto/worktrees/<run-id>/`; never create the execution worktree beside
the repository, in a global pool, or in another checkout. If `main` is chosen,
source edits and tests happen in the invoking checkout and the run's control
artifacts still live under `<repo>/.otto/runs/<run-id>/`. Record the choice and
exact path in `agent_goal.md` and `status.md`, and do not silently switch
custody later. Git ignoring `.otto` is intentional local control storage, not a
reason to relocate it into tracked docs or force-add it. Preserve existing run
state when explicitly relocating a run, update live references, and leave only
one authoritative copy.

## Establish the minimum useful outcome

Before detailing tables, services or batches, write the answers in plain language:

1. What must work for the first useful outcome, and what existing behavior must remain?
2. What is explicitly required now, what can be removed/consolidated, and what is deferred?
3. Which users, data, consumers and deployment constraints actually exist?
4. Which correctness properties cannot be cut, and how can a small backend fixture or experiment demonstrate them?

Simplify implementation and process first; do not silently drop required behavior. Adapting existing search to a changed schema is not permission to redesign it or disable working paths. For an unused/early project, prefer a direct conversion with one relevant inventory/export/rehearsal over shims, dual writes and deprecation machinery—unless actual callers/data justify them. Few users is not permission to destroy data.

Judge every proposed new layer by a current requirement. Prefer a bounded concrete implementation over a generalized graph, workflow/policy engine, parser, storage service or framework. These are examples of scope to justify, not a blacklist. Retain real invariants such as exact revision identity, transactionality and authorization even when implementation is otherwise small.

Estimate the agreed scope in focused engineering days, name major uncertainty and distinguish agent elapsed time. If offering a cheaper milestone, state precisely what it excludes. An estimate, its upper bound, or a two-week threshold never automatically creates review gates.

## Roles and model policy

**Coordinator and oracle are separate responsibilities.** The coordinator runs the agreed process; the oracle owns consequential adjudication. “Host” names the session running the process, not automatic oracle authority. One agent may hold both responsibilities only when the run explicitly assigns both; do not silently transfer authority when delegating coordination. Role slots and model bindings are independent: Luna, Sol and Astra are default model bindings, not roles, and any binding may be replaced in run configuration without changing the responsibility contract.

| Role | Responsibility | Boundary |
| --- | --- | --- |
| Coordinator | Orchestrate the agreed process: draft briefs/plans, dispatch ready work, collect evidence, run prescribed checks and track stages/counters | Follow the mandate; escalate contested findings, design changes and exceptions |
| Worker | Implement the assigned outcome and report evidence | Propose alternatives; no silent scope changes |
| Reviewer | Verify completion against the assigned scope and evidence; when asked, assess strategic coherence | Report source-backed findings; never certify its own implementation or change scope |
| XHARD reviewer | Apply the reviewer responsibility to harder completion questions that justify the XHARD route | The route changes assignment, not authority or acceptance criteria |
| Final reviewer | Review the whole candidate for completion and strategic coherence | Report findings against the declared contract; recommendations do not automatically change scope |
| Oracle | Adjudicate consequential decisions and contested findings, settling direction and permitted exceptions | Remain within user authorization; never waive demonstrated failure or reset user budgets |

The coordinator may advance on required passing tests and an uncontested stage PASS, or route clear in-scope defects through the prescribed correction path. It must not dismiss a blocker, weaken an acceptance criterion, alter architecture, grant deployment authority or increase budgets on its own. It sends unresolved judgment to the configured oracle. Thus not every reviewer response requires a separate oracle call, and a cheap coordinator need not judge sophisticated disagreements.

**Normal/XHARD routes assignments, not authority.** Normal and XHARD are assignment classifications. Worker and reviewer model bindings are selected independently, and a final reviewer binding is independently replaceable. The default bindings are recorded in the run template; neither a model name nor a strategic lens makes work XHARD. Oracle has one configured slot, not a normal/XHARD hierarchy.

XHARD means irreducible sustained subtle reasoning with plausible non-local mistakes that ordinary checks may miss and that the normal model cannot reliably handle from a precise brief. Decompose and diagnose brief/tool/environment failures first. Size, duration, importance or one failure is insufficient. The coordinator requests oracle judgment if escalation classification itself is unclear.

**Declare the run once using [the run template](templates/run.yaml).** Copy it to `$OTTO_DIR/run.yaml`, apply its default role slots and model bindings and select meaningful stage triggers, honoring the user's instructions, and link it from agent_goal.md. It is the single model/stage/budget declaration; do not duplicate divergent settings in prose. Read [configuration semantics](references/run-config.md) before creating or changing it. Preserve the keys `coordinator`, `worker_normal`, `worker_xhard`, `reviewer_normal`, `reviewer_xhard`, `oracle` and `final_reviewer`; each key names a responsibility slot whose model/reasoning binding can be replaced independently. The default bindings are Luna medium for coordinator/normal reviewer, Luna high for the normal worker, Sol high for XHARD worker/XHARD reviewer/oracle, and Astra medium for final reviewer. Use these defaults when no override exists. Oracle budget defaults to three calls. Existing explicit run choices win; do not silently replace them with new defaults. No automatic switch of the current host model or running agents occurs by editing YAML.

The oracle is invoked for a concrete initial direction decision when not already settled, consequential new evidence, contested findings, uncertain escalation or exceptions. Routine dispatch, passing tests and uncontested completion within the mandate do not require reassurance calls. An oracle call is a decision request, not a disguised extra review.

## Durable direction and run state

Keep a succinct `northstar.md`: desirable end state, enduring properties and anti-patterns. Adopt an existing one where appropriate. Keep `agent_goal.md` linked to it: this run's objective, scope/non-goals, source, user authorization, selected models/review budget, acceptance scenarios, stop criteria and validation/resource limits appropriate to the mode. The North Star supplies direction, not additional authority.

The goal is the current agreed contract, not a reason to freeze a still-forming conversation. Direct user steering authorizes the corresponding update: record what changed and reconcile affected tasks without asking for the same approval again. Do not broaden scope yourself. If documents conflict, use the latest explicit instruction when it resolves the conflict; ask only for a genuine unresolved user decision.

For planning, a plan and tasklist plus concise goal/direction/status are enough. Put criteria, decisions and assumptions in these documents rather than generating a ledger of ledgers. Add `acceptance-ledger.md` for delivery where tracking integrated evidence is useful, not as an independent gate. Keep briefs/findings/receipts when agents run; reuse the run's existing evidence rather than repeating an inventory per reviewer. Execution custody and review identities are in the execution reference.

## Oracle decision requests

Use this lightweight exchange when a worker or delegated coordinator needs the designated oracle's judgment. It is not a new service, scheduled review or requirement to ask about routine work. Proceed under the current brief for ready tasks, prescribed tests and authorized correction patterns. Ask before consequential dependent work when evidence contradicts the plan, alternatives materially affect scope/interfaces/data/authority, findings conflict, or repeated failures undermine the approach. A coordinator may recommend; it cannot grant itself exceptions.

**Persistent oracle conversation:** Default to one resumable oracle conversation per coherent run when the runtime supports it. Bootstrap it with compact project background, the North Star, current goal and authority boundaries, and paths to the authoritative configuration, plan, status and prior decisions. Record its conversation/session identifier and resume mechanism in the existing run notes so a replacement coordinator can continue it. Resume that conversation for consequential follow-ups, supplying the specific decision, changes since the last exchange and exact evidence links instead of repeating the full project context. Routine status lookups and dispatch remain with the coordinator.

Before deciding, the oracle refreshes relevant current state and source/test identities from authoritative artifacts; conversation memory is not evidence that facts are still current. Keep rulings, reasons and return conditions in the existing run notes so the conversation is recoverable. If resumption is unavailable or context becomes unwieldy, start a replacement from those artifacts and a compact handover of unresolved questions and decision rationale. Across runs, carry forward relevant durable decisions and explicitly refresh the mandate rather than depend on one indefinitely growing conversation. Recovery or replacement preserves existing authority and budget counters.

Independent reviewers still use fresh conversations with the declared scope and evidence; the persistent oracle does not replace independent review. Each invoked oracle response, including a follow-up in the same conversation, consumes the existing oracle call budget. Persistence changes context delivery, not invocation triggers, authority or review policy.

Keep request and reply together under a stable decision ID in existing run notes (for example a section in status.md). Reuse that ID when revisiting the same question; link deeper evidence rather than paste transcripts.

**Request — answer five questions:**
1. What specific decision is needed?
2. Why cannot current instructions or an existing ruling settle it?
3. What new evidence matters? Link exact source/test identities and any prior ruling.
4. What do you recommend, and what is the main alternative/tradeoff?
5. What work is waiting, and how many times has this same decision returned?

If there is neither a concrete decision nor new evidence, apply the existing ruling instead of requesting reassurance. An uncovered decision may be raised the first time without an experiment; do not fabricate evidence to fill the template. Objective triggers (failed required checks, contract changes, conflicting findings, exhausted correction allowance) supplement self-reported uncertainty—a weaker coordinator may not know it is confused.

**Oracle reply — four fields:**
- Disposition: proceed / change approach / investigate / blocked.
- Decision and reason: concise, grounded in the goal and evidence.
- Next action: a concrete dispatch or bounded investigation; state affected scope. Every executable next action, including actions unrelated to a review correction, carries the outcome, acceptance evidence, dependency scope, and `normal`/`xhard` route to the corresponding `run.yaml` worker. An XHARD action includes its irreducible hard-question justification. “Investigate further” must name the uncertainty and evidence sought; unresolved difficulty is not an executable route.
- Return condition: what result or changed circumstance requires another decision; otherwise continue within the mandate.

The reply operates within user authorization; the oracle cannot grant missing deployment/scope authority. Pause only dependent work while a decision is unresolved. Continue independent work. Pause the whole run only if the uncertainty affects overall scope, authority or correctness. “Blocked” identifies the actual prerequisite, not mere discomfort.

**Loop rule:** if the same decision returns twice without new evidence or action, do not reconsider it a third time. Diagnose the coordination failure: ambiguous brief, insufficient mandate, unsuitable worker, tool/environment problem or an approach that needs narrowing. Choose a concrete repair, bounded experiment, decomposition or justified escalation. Ten consecutive checks without substantive progress is a coordination alarm, not diligence; the number of distinct useful decisions alone is not the problem. Preserve prior rulings and review counts. Every oracle interaction should unlock action or reduce a named uncertainty, and these requests must not disguise extra independent review rounds. Each invoked oracle response consumes the separate run.yaml oracle budget, including diagnosis calls. If exhausted, pause affected decisions and request the needed user direction/budget change; do not self-adjudicate or rename calls. If the oracle requests a review, that review also consumes the applicable stage budget.

## Delegation

> DELEGATION MANDATE — Delegate most investigation, implementation and validation to the selected workers. The coordinator writes mechanical briefs, dispatches ready work, collects evidence and maintains the agreed state. The oracle owns consequential design and adjudication; the coordinator follows its rulings and requests judgment for ambiguity or exceptions rather than deciding them silently. Workers may propose alternatives, not widen scope. Do not delegate merely to manufacture another verdict or force tiny coordination/document updates through a worker. Normal workers execute their task; reviewers and oracle advisers are leaves unless explicitly authorized to manage workers.

Include this mandate in execution-capable manager briefs, not in leaf worker/reviewer briefs. Give each dispatch the complete succinct North Star, applicable goal/task constraints, current source identity and required evidence. Record actual model, command/tool, source, brief/result paths and digests, timing and exit status without secrets. A plan-only read-only fact check does not need execution-capable permissions.

If the North Star or agreed goal changes, record the authoritative user instruction and updated digest; reconcile affected tasks and briefs before dispatch. Map changed criteria to their previous IDs and invalidate only affected evidence/approvals. Preserve unaffected results and existing review counters; do not silently give queued work a different contract. An adopted North Star records its source path and digest.

## Explore and form the plan

The coordinator drafts or adopts the plan and identifies uncertainties; the oracle settles unresolved consequential direction. Delegate narrow questions when the answer could change scope, implementation or proof. Good explorations locate the active dependency closure, distinguish facts from assumptions, identify reusable mechanisms and test whether an adjacent abstraction can disappear. Return conclusions with file/line evidence; keep bulk output outside the host context.

**Factual exploration is not a review round.** Additional cheap fact checks may be worthwhile after an initial fan-out; no arbitrary wave quota or new permission is needed within authorized time/cost/scope. Give each one a named unresolved question. Stop when another answer would not change a decision; do not run repeated general audits in pursuit of certainty. Expensive, live or mutating experiments still obey their authorization/budget.

The coordinator incorporates factual findings within the mandate and sends consequential choices to the oracle. Optional Sol/Grok planning advice is for a concrete difficult question; it is not a mandatory plan/revise/STABLE ceremony. No reserved empty phase and no requirement for a model to pronounce `STABLE`.

Actively pressure-test complexity while forming a substantial plan: ask normal-model explorers/critics to find unnecessary abstractions, duplicate mechanisms and handoffs, and propose concrete deletions, consolidation or reuse supported by source evidence. Do not use cheap agents only to confirm the proposed architecture. The oracle decides consequential scope cuts; the coordinator applies them while preserving required behavior.

Once coherent, use the smallest useful normal-model simplicity critique if it can improve a substantial plan. Ask what can be cut, merged, reused or deferred without losing the goal. This is discovery, not certification. Bound repeated whole-plan critiques to two rounds by default; later facts do not reset that cap. Local details become tasks or bounded spikes. Do not make a model critique mandatory for a straightforward update to an already agreed plan.

Freeze for execution when the coordinator can explain the complete path to the outcome, material architecture/authority decisions are resolved, and remaining implementation unknowns have an owner/test/spike. “No critic can find another idea” is not a stopping criterion. Optional discoveries go to deferred notes, not new blockers.

## Tasklist and execution

Tasks name their outcome, real dependencies, affected scope, model/classification and acceptance proof. Group at natural integration seams; labels do not create global barriers. The coordinator checks explicit goal/task/authorization agreement and sends ambiguous conflicts to the oracle; an extra independent pre-execution contract review is not the ordinary default.

Every executable assignment, including a correction dispatched after review, carries
the same compact contract: the concrete outcome, acceptance evidence, source and
dependency scope, and a route of `normal` or `xhard`. The route resolves through
`run.yaml` to `worker_normal` or `worker_xhard`; it is not a new role. An XHARD
assignment includes a brief justification naming the irreducible hard question and
why a precise normal-worker brief is insufficient. The coordinator records these
fields in the brief/receipt and dispatches to the corresponding configured worker.
This requirement applies to corrections as well as first-pass tasks; it does not
add a gate or an extra model call.

In planning-only mode, deliver the plan/tasklist, unresolved assumptions and estimate now. Do not proceed into the execution reference's setup or claim future tests have passed.

For delivery, use [execution mechanics](references/execution.md), dispatch unblocked work, run focused tests during implementation and converge around coherent source checkpoints. Only dependents of a failed invariant must wait. Batches/checkpoints are for integration and source identity, not automatic model-review gates. The oracle adjudicates material plan changes; user scope/authority cannot be expanded by an executor or reviewer.

## Review policy — one source of truth

Distinguish three activities: factual exploration resolves questions; tests establish behavior; model review independently challenges a candidate. They have different costs and need not share cadence.

Reviewers use two **lenses**, not separate authority hierarchies:

| Lens | Question | Routing |
| --- | --- | --- |
| Completion | Is the agreed work actually done and correct, with adequate executable evidence? | Usually normal (e.g. Luna); escalate only an irreducible hard question |
| Strategic | Is the approach coherent, appropriately simple and aligned with the agreed goal across components? | Often benefits from the designated judgment model; use XHARD routing when the reasoning warrants it or a user override specifies the model |

A strategic lens does not automatically make an assignment XHARD, nor authorize reopening settled product scope. A normal critic can expose unnecessary architecture. A strategic review cannot excuse a concrete functional failure. For each review, record only lens, question/scope, classification/model/reasoning, evidence and round budget; both lenses can share one integrated review when appropriate. No requirement to run two reviewers for every checkpoint.

**Review gates remain real.** The declared stage gate requires passing evidence and no unresolved blockers. The coordinator advances on uncontested results under that rule; the oracle adjudicates disputes and exceptions. At the run's chosen meaningful checkpoints, completion review establishes readiness; strategic review addresses consequential design/integration questions or the final whole. Accepted blockers hold affected dependents; unrelated work continues. Optional suggestions do not become requirements. A gate is a decision about required evidence, not an automatic stronger-model call. User-selected final-only arrangements take precedence over default checkpoint choices.


**Schedule comes from run.yaml.** A stage is a named checkpoint trigger and review scope; a round is one independent reviewer invocation within that stage. Each stage selects a reviewer role, lens and maximum rounds; the role's configured model binding is execution metadata. The list and its caps are authoritative; do not append a hidden default final review. Later rounds verify corrections and affected integration, stopping early when resolved.

When no policy is supplied, apply the scope/coupling guide in configuration semantics: zero, one or two intermediate stages plus a final integrated review, recording the selected boundaries and reason before dispatch. Normal intermediate stages allow up to two rounds each; the final reviewer stage allows up to three. Stop early on PASS. Select boundaries from dependencies and the cost of discovering errors late, not a calendar or file-count formula. Do not add a gate for every task or solely because of elapsed time. Honor explicit final-only policies. Planning-only mode dispatches no executable review stages. Ordinary tests and pre-operation validation continue regardless of review cadence.

A stage checks the complete scope named at its checkpoint, not just its final task. The final holistic lens covers overall completion and strategic coherence; it is a configured reviewer assignment, not another oracle hierarchy. The same model may hold multiple roles, but reviewer invocations remain independent of implementation context.

Every reviewer is an independent leaf, receives the frozen scope and candidate plus relevant evidence/oracle dispositions, and may not spawn reviewers or invent requirements. First review is integrated; correction rounds cover affected criteria and their dependencies, preserving unaffected approvals. No panels or repeated whole-project discovery after a demonstrated blocker. Use one source census per relevant candidate/path set, not one per reviewer.

Classify findings as `contract_violation`, `implementation_defect`, `required_evidence_gap`, `optional_improvement`, `out_of_scope` or `stale_or_repeated`. Only the first three can block. The coordinator routes clear in-scope findings under the mandate; the oracle verifies contested claims against source/tests and records an evidence-backed disposition. No automatic promotion of a reviewer's recommendation into authority.

For each finding, keep blocking classification separate from correction difficulty.
Only an actionable correction finding receives a recommended difficulty of `normal`
or `xhard`; optional, out-of-scope, stale, or otherwise unaccepted findings receive
no dispatch route. An unresolved or disputed difficulty is referred to the oracle,
then the executable next action receives a `normal` or `xhard` route. A clear normal
route goes to `worker_normal`; a clear XHARD route goes to `worker_xhard` with its
justification. The coordinator may route a genuinely hard correction directly to
XHARD. After two failed substantive correction cycles, require a root-cause
decision on the brief/tools, decomposition, bounded spike, or justified hard kernel;
do not silently repeat the same correction. Run affected tests before another
review. These routing records do not create a fixer role or review gate and do not
authorize resetting the review budget.
A review cap ends repetitive model reviewing, not responsibility for the outcome. At
the stage or total budget cap, request oracle diagnosis if its budget permits,
continue authorized corrective work/tests where useful, and surface a needed
budget/authority decision. The coordinator cannot bypass an unpassed required gate
or reset its budget. Do not launch an equivalent review under a new name, reset
counters, label failure PASS or hand back a solvable problem merely because reviews
are exhausted. If further independent certification is essential, report that gap
and seek only the needed review-budget change; never claim unreviewed corrections
received a pass. Explicit user round counts take precedence.

The cap applies across renaming/repackaging/checkpoints for the same review scope. Record counts and accepted findings once. Increase a fixed user budget only with their approval; when a new risk requires different scope, explain it rather than hide another review in a new name.

## Completion

Planning completion means the plan is coherent, scoped and ready to implement; report it as such. Delivery completion requires executable evidence for the agreed outcome, disposition of blocking findings and an honest summary of remaining limitations. Run the broad affected suite once on the final candidate; repeat only affected checks after changes. Frozen review mechanics and sync authorization are in the execution reference; do not infer deployment from a successful review.

## Review packet assembly

Use the [review packet template](templates/review-packet.md) and [artifact assembly rules](references/review-packets.md). Each declared stage names its task/criterion scope up front. Completion review checks actual implementation and proof; the final holistic lens also checks coherence, simplicity and North Star alignment. The coordinator fills the packet from exact artifacts instead of inventing the reviewer's goals. This adds no model call or review stage.

## Model invocations

Use available native subagents or the installed launchers; preserve the selected model and record the actual invocation. Tool permissions come from the environment and task, not from this skill. Read-only exploration/review stays read-only; a delegated manager needs network access if its launcher uses it. Never bypass an environment prohibition to match an example.

```bash
# Normal exploration: choose the declared model, grant only read/search tools.
PYENV_VERSION=3.11.11 python ~/.claude/skills/subagent-launcher/launch_hermes_agent.py \
  --model="codex:gpt-5.6-luna" --toolsets="file" \
  --query-file="$BRIEF" --project-dir="$SOURCE_DIR"
# Flash alternative: --model="deepseek:deepseek-v4-flash"
# Normal implementation adds terminal tools in the isolated execution worktree.
# For multiple independent briefs use fan.py, with the same declared model.

# Optional Sol advice; not a required planning phase. Seal stdin.
codex exec -C "$SOURCE_DIR" --sandbox read-only \
  -c model=gpt-5.6-sol -c model_reasoning_effort=high \
  "$(cat "$BRIEF")" </dev/null
# Optional Grok advice:
grok --cwd "$SOURCE_DIR" --prompt-file "$BRIEF" \
  -m grok-4.6 --reasoning-effort high --permission-mode plan
```

Set an invocation timeout with the launcher/process supervisor (normally at most 30 minutes), not a blocking wait that prevents host updates. For implementation, assign permissions appropriate to source mutation; for a manager, include delegation permissions only if it actually dispatches. For any reviewer, use the run's recorded model and reasoning, a frozen candidate and non-mutating access. The examples are invocation mechanics, not additional model gates.

## Operational gotchas

- Seal `codex exec` stdin with `</dev/null`; otherwise it can wait for input indefinitely.
- A user's existing model/role/review choices persist. The coordinator cannot silently assume oracle authority; oracle decisions never broaden user authorization.
- Preserve dirty local work. A worktree from HEAD does not include uncommitted files; identify which source is authoritative before executing.
- Keep run artifacts in the recorded control root and execution in its recorded worktree. Do not recompute the project root inside a nested checkout on resume.
- Source custody and test evidence prevent false completion; process liveness and reviewer approval alone do not prove the product works.
- Run capacity checks before expensive work. After ENOSPC or disk-I/O failure, fix capacity before retrying; do not repeatedly dispatch into the same failure.
- Reuse unchanged passing evidence. Fixes invalidate only affected criteria and their dependency closure, not the whole project.
- Report launches, findings, decisions, failures and completions. Keep no-change polling out of progress logs.
- Never infer merge, push, production mutation or deployment authority from the North Star, a review verdict or the word “sync.”

## Shared maintenance

Keep the **Roles and model policy**, **Oracle decision requests**, **Delegation**, **Model invocations**, and **Operational gotchas** blocks identical in Megado and Microdo. Their planning/review cadence is intentionally different; do not copy mode-specific gates between them. Maintain shared execution references consistently when changing custody/invocation mechanics. Do not append conflicting copies of the review policy to examples or cloud briefs.
