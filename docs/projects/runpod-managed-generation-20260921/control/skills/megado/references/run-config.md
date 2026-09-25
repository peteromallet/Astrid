# Run configuration semantics

`templates/run.yaml` supplies the default responsibility slots, independently replaceable model/reasoning bindings and available stage slots. It is a coordinator-readable contract, not an implemented scheduler/launcher. Copy it into the run, apply explicit user overrides, choose stages using the guide below and replace/delete placeholder triggers before dispatch. Link it from agent_goal.md as the single declaration. Do not ask for choices already set by defaults or the user; resolve unavailable models without silently substituting. Existing explicit run policies remain authoritative.

## Default roles and budgets

- Default model bindings: `coordinator` and `reviewer_normal` use GPT-5.6 Luna at medium reasoning; `worker_normal` uses GPT-5.6 Luna at high reasoning; `worker_xhard`, `reviewer_xhard` and `oracle` use GPT-5.6 Sol at high reasoning; `final_reviewer` uses GPT-6 Astra at medium reasoning. These are replaceable bindings, not role definitions; reviewers remain separate agents from implementers.
- Oracle: at most three calls, used only for actual judgment requests.
- Intermediate review: at most two rounds per selected stage (initial check plus correction verification).
- Final holistic review: at most three rounds (initial integrated review plus up to two correction verifications).

These are maxima, not work to fill. Stop each stage when required checks pass and no blockers remain. XHARD review replaces the normal reviewer for a justified hard review question within the same stage/budget; it is not an automatic extra stage. The oracle settles uncertain escalation within its call budget.

## Choosing review stages: a practical proxy

| Work shape | Intermediate stages | Default maximum review calls |
| --- | --- | --- |
| Localized change with a clear contract and cheap end-to-end proof | None; the final reviewer stage covers completion and strategy | 3 |
| A change crossing a meaningful producer/consumer or schema/API boundary | One Luna stage once the contract works, before substantial dependents build on it | 2 + 3 = 5 |
| Multiple distinct integration risks or a foundational migration followed by downstream integration | Two Luna stages: foundation, then integrated behavior before final completion | 2 + 2 + 3 = 7 |

Select the smallest applicable shape by coupling and cost of late discovery, not importance, elapsed days or the number of tasks. Each intermediate stage needs one sentence naming the wrong assumption it could catch before dependent work compounds it. Merge stages testing the same question. If a second stage would see essentially the final candidate and same evidence, let the final review cover it. Factual exploration and ordinary tests do not consume review calls and cannot issue hidden review verdicts.

Stage counts/caps are fixed when adopted. New risk calls for a decision, not automatically more stages: use a remaining stage or replace its scope without replenishing spent calls; additional budget needs user authorization. A required pre-operation validation remains necessary even without an extra model review. Planning-only work schedules no executable reviews. Microdo normally keeps one final stage and its single correction limit (at most two final rounds), unless the user explicitly changes its one-pass policy; the Megado three-round default does not silently override that narrower mode.

## Field semantics

- `mode`: planning_only or delivery. Planning-only never dispatches executable review stages. Changing a field cannot grant implementation or deployment authority.
- `roles`: the responsibility slots `coordinator`, `worker_normal`, `worker_xhard`, `reviewer_normal`, `reviewer_xhard`, `oracle` and `final_reviewer`, each with an independently replaceable model and reasoning binding. Reasoning applies only where supported by the selected runtime; resolve unsupported settings before invoking rather than silently substituting. A role is a responsibility, not a model identity: several slots may name the same model, and reviewer agents remain independent of workers even when their bindings match.
- `oracle.max_calls`: total oracle invocations for this run, including initial direction, diagnosis and follow-up decisions. Reuse existing rulings without a call when sufficient. Do not ask the oracle at every PASS. Invoking a designated oracle model consumes this budget even if the answer is inconclusive; budget exhaustion never transfers authority to the coordinator.
- `review_stages`: ordered named review boundaries. `after` references an actual task/checkpoint or all-required-work-and-tests. `reviewer_role` resolves through roles. `lens` is completion, strategic, or completion_and_strategy. `max_rounds` is the total invocation cap for that stage, including correction reviews—not the number of required passes. Each stage is a gate for its dependent work.

Selecting both intermediate slots and the final stage, with caps 2, 2 and 3, allows at most seven review calls, stopping early at each passed gate. Oracle calls are separate. There is no extra implicit final review, and changing classification/model/checkpoint names does not replenish counts. If an oracle commissions review, charge the oracle call and the review invocation to their respective budgets. A model invocation cannot evade a cap by being relabelled advice. Pure factual workers do not adjudicate or issue hidden certification verdicts.

Before dispatch, check unique stage IDs, valid role references/models, positive integer caps, meaningful task triggers, final-stage scope and consistency with user authorization. Do not start a coordinator expecting an unavailable model or a placeholder trigger. Record consumed counts and last candidate/evidence identity in existing status notes before invoking; record results afterward. Keep counters durable through crashes/restarts. If a process might have been invoked but its result is lost, recover evidence or conservatively charge it rather than assume a free retry.

Coordinator loop: dispatch ready work → run prescribed checks → invoke a ready review stage → advance on uncontested PASS with required tests passing, or route clear in-scope defects to correction. Escalate disagreement, architecture/scope/authority changes, unclear XHARD routing or attempted exceptions using the oracle request template. Fix before the next review round. At a cap, continue only independent or already authorized correction work; do not cross the unresolved gate, dismiss a finding, weaken a test or launch an extra call. User approval is needed to enlarge a fixed budget or authority; an oracle recommendation cannot grant it.

For final-only runs, declare just that stage and retain ordinary tests/integration checks. For Microdo, keep its one-pass/correction limit unless the user explicitly changes it; the shared role defaults do not override it. For an explicitly host-as-oracle run, record the actual host model in the oracle role and state that assignment in the goal; do not pretend a separate model ran. Existing run choices remain authoritative until changed, even when the skill default evolves.

Review packets: each adopted stage declares `scope_tasks`, `criteria` and `criteria_source` referring to real task/implementation-criterion IDs before execution. See [review-packets.md](review-packets.md) for the fixed assembly and reviewer questions; no new review objective is inferred from model choice.
