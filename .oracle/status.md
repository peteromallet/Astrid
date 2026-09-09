# Status — canonical pack beta

- Clarity/reconciliation: **COMPLETE**
- Execution contract: **FROZEN**
- Huge-run policy: **active — 4–6 engineer-weeks**
- Existing Astrid package/product foundation: **substantial and mostly built**
- Canonical-v2 implementation batches: **NOT STARTED — 0/5**
- Frozen final criteria: **0/15**
- Product files changed by this run: **zero**
- Base/current HEAD: `7ac50c12e8e4d90988fee603ffdb9896e5628792`
- Branch: `megado/canonical-pack-beta`
- Worktree:
  `/Users/peteromalley/Documents/reigh-workspace/Astrid-canonical-pack-beta`
- Remaining estimate: **4–6 engineer-weeks** for one senior engineer
- Local execution preflight: **PASS but superseded by cloud venue** — approved
  VibeComfy cache removed; 3.5 GiB free; temp-file and isolated-venv probes
  pass. No further laptop cache deletion is needed for this project.
- Cloud execution preflight: **IN PROGRESS** — 236 GiB free, 16 CPUs, 27 GiB
  available RAM; durable AgentBox operation registered; isolated transfer,
  container, model/tooling, and baseline probes remain.
- Goal state: **ACTIVE**
- Current Megado phase: **cloud bootstrap before Phase 5**
- Active batch: **E0.3–E0.4, then B1**
- Model routing: **Sol owns the Megado run and gate decisions; Luna performs
  normal bounded work and independent reviews; a separate Sol call supplies
  each oracle disposition; no `[XHARD]` task currently justified**
- Fresh pre-execution review: **will run on the transferred cloud identities**
- Review cadence: **three independent Luna passes plus one Sol disposition per
  batch; cumulative gates after B3 and B4**

## What “mostly done” means

Most underlying functionality was already implemented before this run:

- 18 of the 22 target product directories already have v1 capability-pack
  manifests;
- all 64 executors, 12 orchestrators, and 10 elements are already discovered
  from domain packs;
- 17 of 22 product packs already have direct skills (`_core` has its separate
  guidance skill); and
- timeline, shots, references, and Runaway already have real SQLite migrations,
  repositories, product behavior, and operational support. The migration
  engine, writer/UoW, SDK wiring, doctor, and backup/restore also exist.

What is not done is the new canonical-authority cutover: there is no active v2
catalog, the four database slices still use separate `schema-pack.yaml`, three
fixed default-composition authorities remain, eight builder/reader consumers
have not converged, five direct product-pack skills are missing, and wheel
closure has not been proved. Therefore the existing foundation is mostly built
while the specifically requested v2 cutover remains 0/5 and 0/15.

## Execution authority

1. `.oracle/agent_goal.md` — frozen scope and 15 exact done criteria.
2. `.oracle/northstar.md` — durable end state.
3. `.oracle/implementation-ledger.md` — verified current state and history.
4. `.oracle/tasklist.md` — exact executable items and gates.
5. `.oracle/plan.md` — concise five-batch sequence.

The former 2,317-line plan is archived at
`.oracle/prior-runs/canonical-pack-overgrown-plan.md` and is non-executable.
The storyboard `evidence/final-matrix.md`, top-level batch check-ins,
`briefs/pre-exec-review.md`, and `execution.log` are also historical residue,
not evidence that this canonical-pack product cutover ran.

## Correct next action

Finish E0.3–E0.4 on the agentbox, run the fresh pre-execution review there,
then execute B1 against isolated fixture roots and B2–B4 as one unshipped
atomic cutover. Before activation only legacy
authority is active; afterward only strict v2 is active. B5 verifies source/
wheel/resource/docs/test closure and final independent review. Do not resume
broad planning.

The local environment currently lacks the Python `build` module. B5 contains
an explicit isolated build-tool preflight; this does not waive wheel proof.

The separately requested pack-aware `astrid update` command has not started.
It follows this cutover and must preserve user edits and pack-applied database
migrations, using Luna for normal execution and Sol for planning/oracle or
exceptional work.
