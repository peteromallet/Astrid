# Current project scope — CPU/fake/offline only

Authority: the user's 2026-09-21 clarification changes the zipped projects so
they build the implementation and finish CPU/fake/offline validation first.
Live GPU/RunPod testing happens afterwards as a separate post-handoff activity.
This amendment governs P0–P11, Q, H, all exported runs, briefs, criteria, review
inputs, guides and recovery instructions in this packet. It overrides older
live-test requirements without deleting their strategic purpose or historical
evidence. It does not activate implementation under this packaging-only mandate.

## Current executable work and acceptance

When implementation is authorized, build the requested software, schemas,
adapters, launch/bootstrap code, manifests, migration support and test harnesses.
Validate with CPU-only unit/integration tests, local fixture processes, fake
provider/native-engine clients, synthetic media and offline cross-repository
journeys. Test task submission, lineage, artifact retrieval/publication, shot
association/selection, restart, cancellation, fencing and rollback through those
fixtures. Implementing a RunPod path remains in scope; invoking a real provider
or hardware path does not.

Source and CPU dependency retrieval are separate setup operations. Build/test
execution must deny outbound network, expose no GPU, use no provider credential
and perform no model downloads or CUDA environment bootstrap. Use a local CPU
dependency closure. A missing local dependency is a setup gap; it is not a reason
to switch to a GPU runtime. Inspect fixtures before execution and select only
the offline suites. A dry-run that queries RunPod is a live provider call and
is excluded too.

Current completion is `CPU_COMPLETE / GPU_UNQUALIFIED` after implementation,
required offline evidence and the existing review stages pass. This is a scope
definition, not a claim that those projects are already complete. No current
acceptance criterion requires a real pod, model residency, GPU output, hardware
performance measurement, provider credentials or GPU budget. Existing failures
in CPU correctness remain blockers; live checks have status
`DEFERRED_POST_HANDOFF` and cannot hold current completion. Preserve source
identity requirements, unaffected evidence, roles, budgets and spent counters.

## Mapping of older controls to current acceptance

| Project/control family | Current executable proof | Moved to separate gate L |
|---|---|---|
| P0 / runpod-managed-generation, C-G0–C-G4 | Full producer → fake transport → independent verification → publication journey, exact source tuple and readable fixture after simulated remote removal | Actual generated video, remote custody ending and live publication readability |
| P1–P4 / gpu-engine-task-path, gpu-executor-residency, wan2gp-engine-followup, prior vibecomfy-engine-task | A–D/A–E protocol and lifecycle fixtures; device exclusion, retention keys, release ordering, durable fake worker, output rebinding and V→W→V process handoff | CUDA execution, native loaded-weight residency/release, real VRAM, local GPU and RunPod matrix |
| P5 / canonical-runpod-vibecomfy-jobs and astrid-runpod-task-queue | C1–C8 and queue criteria exercised with fake provider, fake server and local runtime; disconnect/deadline, containment, attempts, diagnostics and leave_running policy | Real queued pod jobs, remote worker connectivity, disconnect survival on provider infrastructure and actual teardown |
| P6 / h3-cuda13-golden-template, vibecomfy-dependency-contract, vibecomfy-runtime-dependency-contract | Source/CPU wheel locks, build recipes, manifest/schema/hash validation, small model-file fixtures, provider-fault simulations and offline reconstruction of supported CPU components | CUDA/native dependency qualification, real model staging, GPU image build/run requiring hardware, two fresh-pod proofs, D14 live evidence, SLO/capacity measurements and production profile promotion |
| P7 / worker migration | Caller inventory, migration implementation, CPU/fake parity, recovery/rollback rehearsal and documented retirement conditions | Production routing cutover, real caller parity and deletion/retirement of operational workers |
| P8–P11 / shot-generation-timeline and shot-composition-unification | Runtime persistence, frozen inputs, CAS selection, fake two-segment generation, project/shot association, restart/retry and upstream invalidation | Creative pilot and real generated-media acceptance |
| Q / F3 | Integrated CPU/fake/offline matrix against exact source composition | All native GPU/provider qualification |
| H | Portable documents, exact pins, integrity/links, safe extraction and offline packet checks | Waiting for live qualification or purchasing capacity to validate the handoff |

For mixed task/criterion IDs, retain the CPU implementation and fixture clauses
under the original ID and transfer only the live clause to L. For live-only tasks
(for example lifecycle T7's native matrix, golden T5 and dependency D14), their
hardware execution is removed from current task completion; implementing their
offline fixtures remains useful current work. Closeout uses fake cleanup and
durable local evidence. Production promotion/retirement stays deferred; do not
replace missing hardware proof with a fake PASS for a production claim.

Each exported run/source document includes a scope notice. Its older body is
retained as traceable design/history, not permission to execute live commands.
Reviewers apply this amendment even when historical criteria say “required”,
“full acceptance”, “not optional”, “authorized pod” or “must run live”. Config
comments repeat the boundary; model/stage/budget values remain unchanged.

See [validation](validation.md) for the default path and
[post-handoff gate L](POST-HANDOFF-GPU-GATE.md) for the retained strategic proof.
