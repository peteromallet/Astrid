# Acceptance and evidence index

Current acceptance is [CPU/fake/offline only](../execution-scope.md). Historical
live criteria in linked evidence are preserved for traceability but moved to
[gate L](../POST-HANDOFF-GPU-GATE.md); they are not current project blockers.

| Scope | Evidence and state | Remaining current-project gate |
|---|---|---|
| A / P0 C-G0–C-G4 | [Acceptance ledger](../control/runs/runpod-managed-generation-20260921/acceptance-ledger.md), [final review](../control/runs/runpod-managed-generation-20260921/reviews/final-integrated-review.md): recorded deterministic approval | Exact final-SHA binding to CPU/fake acceptance; live output moved to L |
| P1–P4 lifecycle | [Successor plan/status](../control/runs/gpu-engine-task-path-20260920/status.md), [residency decisions](../control/runs/gpu-executor-residency-20260920/status.md), [Wan successor](../control/runs/wan2gp-engine-followup-20260920/status.md) | Planning-only successor; fake native protocol, A–D and engine handoff proof |
| VibeComfy prior scope | [Closure and transferred gates](../control/runs/vibecomfy-engine-task-20260920/status.md) | User-directed closure, not RunPod A/B/C or residency acceptance |
| P5 jobs | [Canonical jobs plan](../control/runs/canonical-runpod-vibecomfy-jobs-20260921/plan.md) C1–C8 | Planning-only, no delivery inferred |
| P6 distribution | [Golden-template status](../control/runs/h3-cuda13-golden-template-20260918/status.md), [dependency contract](../control/runs/vibecomfy-runtime-dependency-contract-20260917/status.md) | CPU-verifiable release recipes, manifests and offline distribution fixtures; GPU reproduction in L |
| P7 migration | [Repository lock](../repo-lock.json), [ownership/gates](../program-map.md) | Unavailable orchestrator pin, dirty caller state, inventory and offline parity/rollback; operational retirement in L |
| P8–P11 shots | [Shot goal](../control/runs/shot-generation-timeline-20260915/agent_goal.md), [tasks](../control/runs/shot-generation-timeline-20260915/tasklist.md), [design](../control/source-docs/Astrid/docs/plans/shot-generation-timeline.md) | Planning-only; Runtime authority, frozen inputs, atomic selection and restart journey |
| Q | [Validation instructions](../validation.md) | Integrated exact-candidate CPU/fake/offline qualification only |
| H | [Source fetch report](source-fetch-report.json), [packet validation](packet-validation.json), [manifest](../manifest.json), [provenance](../control-provenance.json) | Final refresh after required acceptance and publication decisions |

Each exported control record is indexed with original source HEAD/path/state,
Git blob where available, original SHA-256 and sanitized export SHA-256 in
control-provenance.json. SHA256SUMS covers the final packet bytes. The archive
digest and final extraction/rebuild receipt live beside the ZIP, outside Git.

Budget preservation examples: lifecycle successor records oracle 1/3; residency
records 3/3; golden-template records 3/3; shot planning critique records 1/1.
The prior VibeComfy engine review budget is exhausted. Project A's exported
stages cap generalized handoff at two rounds and final integrated at three;
their exact consumed totals are not fully reconstructed here. Read each run's
full status/configuration, preserve chronology and recover ambiguity before any
new invocation. This packaging pass invoked no reviewer or oracle and added no
execution review stage.

Missing/raw artifacts are listed in [omissions](omissions.md). A linked omission
record is an honest gap, not replacement proof. Current provider liveness,
remaining spend and historical raw receipt completeness were not rechecked.
