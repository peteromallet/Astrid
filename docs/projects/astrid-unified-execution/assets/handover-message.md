# Copy-paste receiving-agent message

Continue the **Astrid unified execution** Megado project in planning-only mode.
The project is hosted in public `https://github.com/peteromallet/Astrid.git`,
handover branch `handover/astrid-unified-execution-20260909`, based on `main`
source SHA `8150c3b70887495f0fae4a55c1ac70085a900550`.
The control root is `docs/projects/astrid-unified-execution/`.

Use a fresh parent directory and do not overwrite an existing checkout:

```sh
test ! -e astrid-unified-execution &&
git clone --single-branch --branch handover/astrid-unified-execution-20260909 https://github.com/peteromallet/Astrid.git astrid-unified-execution &&
git -C astrid-unified-execution rev-parse HEAD
```

Read the control root's `START-HERE.md`, `authorization.md`, `run.yaml`,
`agent_goal.md`, `northstar.md`, `plan.md`, `tasklist.json`, `criteria.md`,
`status.md`, `provenance.md`, and `dependencies.md`.
Read the canonical Megado and handover skills at exact public skills SHA
`1219b3183dde29e4b74681690c4a2351bed3cab3`; use the non-overwriting clone
commands or exact-commit direct-read links in `dependencies.md`.

The sole execution authority is `authority/UNIFIED-PLAN-v3.md`, SHA-256
`0772f5ac5196b7c0e28d19c1d636f18c26a3cc8c550f9f1a09bd9a4e2ddb7dc0`.
Its ratified architecture and ledger ruling are settled. The state is planning
complete, delivery not initialized: 22 historically accepted scoped closures,
one reopened HC-04 obligation, and 22 open rows. No pending row closes by
discovered evidence. Historical Fire-19 passes are not production acceptance.

The intended delivery outcome is reliable canonical task execution across
Wan2GP, VibeComfy embedded, and VibeComfy checkout, with Runtime as the sole
durable authority, session ownership and lifecycle fencing, evidence-backed
warm reuse, producer migration and legacy deletion, final frozen CPU and
RunPod proof, and 45/45 acceptance or an honest terminal with cleanup evidence.
This spans the repositories named in the dependency/provenance records; the
handover's Astrid base is not an instruction to replace the plan's source pins.

Preserve all role/model/reasoning bindings from `run.yaml` and verify each is
available on your host. Use native independent agent contexts; never silently
substitute a model or let an implementer review itself. Delegate bounded
investigation and implementation to the configured workers; the coordinator
maintains custody, briefs and state, and routes consequential judgment to the
configured oracle. This instruction does not authorize implementation now.

The current configured review stages are empty because mode is planning-only.
The future P1/P2 independent reviews, CR2 before final freeze, conditional CR3
delta review, and final independent review remain prescribed requirements.
Do not dispatch them from planning records, invent passing candidate packets,
or reset spent rounds when execution is later configured. The oracle cap is
three with inherited consumption unknown. Recorded historical counts are one
planner revision, three critics, and one affected-delta PASS; total review
consumption is unresolved. `run.yaml` is the single budget declaration.

The provider cap remains USD 6 aggregate, with 19 historical fires and unknown
spend/attempt balance; maximum two live attempts per engine/profile cluster,
three hours per pod, 4 GiB local free-space floor, and 2 GiB generated evidence
cap. No new GPU fire until historical allowance and reserved final-run capacity
are reconciled. Retain the one-owned-pod limit, no model downloads, every-exit
cleanup, and provider-observed absence requirement from the authority.

P0 prerequisites include usable Runtime source custody, bounded backend
recovery or reconstruction, offline preservation of all four recovered tips,
historical receipt/budget recovery, exact dependency/configuration identities,
and local capacity. Raw archives and receipts were omitted from this public
planning closure; their absence is an explicit evidence gap, not a waiver.
CPU planning can proceed while live allowance remains unknown.

**Finish instruction:** validate and report the planning handover and remaining
execution prerequisites, then stop. Do not execute product work, create an
implementation PR, merge, deploy, cut over, increase budgets, or claim live
acceptance. A later delivery instruction must be recorded in the single
`run.yaml` before authorized execution proceeds; it does not erase existing
roles, gates, counters, or stop conditions.
