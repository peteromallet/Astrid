# Canonical timeline feature ports

Status: implementation complete on local Astrid `main`; amendment packages A–D passed Astra integrated review and are ready for the scoped `main` commit/push.

Megado delivery status (2026-09-09): managed-media replacement, transparent PNG layers, bounded two-child continuation, exact generated-client provenance, and direct public render receipts are implemented. The owning runtime is pinned at `afccb430e2a983c968b6a8a96fd630ba3a6262fc`; Astrid vendors the byte-identical generated client and records its source commit, client hash, and schema digest. A fresh public replacement render passed with the unshimmed runtime envelope. No pack-local timeline database or scheduler was introduced.

The implementation remains in the current Astrid `main` checkout until final review and the final scoped commit. The continuation amendment will also execute directly on this checkout, with no separate worktree or historical cherry-pick. Unrelated dirty scenario/evaluation payloads remain untouched:

- `judged_assessment_summary.md`
- `workflow_scenarios_master.json`
- `eval_100_stratified.json`
- `eval_100_stratified.md`

The source evidence, Astra rulings, and test results are in `.otto/runs/canonical-timeline-feature-ports/evidence/`. The local control state is ignored by Git and records custody, role assignments, and review gates.

The orchestration completion work is specified in the [continuation-to-render amendment](canonical-timeline-continuation-render-amendment.md), with its own tasklist and control run. It is complete on this same current `main` checkout; Astra’s final gate passed after the real daemon-backed host/render proof.

## Desired result

An Astrid user can edit a canonical timeline by replacing the managed media in one
explicit clip, add a constrained transparent PNG layer, and run a small durable
multi-step generation-and-stitch workflow. Timeline documents, managed media,
versions, tasks, retries, rendering and receipts remain owned by the runtime.
Packs provide typed behavior and render plans; they do not create a second timeline
database or scheduler.

## Work packages

### 1. Managed-media replacement

Port the behavior from the historical timeline CLI/SDK into the current seams:

- `astrid/sdk/remote.py::RemoteTimelines`
- `astrid/sdk/workspace_client.py`
- the generated workspace client, only through its pinned source/regeneration path
- `astrid/packs/timeline/cli.py`

Add a narrow runtime semantic mutation that resolves one explicit clip, verifies
project and managed-media ownership, changes the canonical clip/registry reference,
applies an explicit `preserve-duration` or `ripple` policy, and performs one atomic
expected-version write. A client-side transformation is acceptable only if retries
remain snapshot-safe and semantically idempotent; otherwise add the operation to the
owning runtime and regenerate the client.

Required decisions before implementation:

- exact behavior when replacement media is shorter or longer;
- which tracks and clips ripple, including overlaps;
- whether shot targeting is supported initially (explicit clip targeting is the
  first milestone);
- preservation of unrelated clip IDs, text, audio, effects and metadata.

Acceptance evidence: stale-version rejection, same-key replay after a later edit,
changed-payload key conflict, cross-project media rejection, trim/rate/duration
validation, preserve-duration and ripple behavior, and a before/after render through
the public timeline route.

### 2. Transparent PNG layers

Port the constrained behavior from the historical FFmpeg backend into the current
renderer and support seams:

- `astrid/packs/rendering/backends/ffmpeg/command.py`
- `astrid/packs/rendering/backends/ffmpeg/support.py`
- `astrid/packs/rendering/backends/ffmpeg/renderer.yaml`
- `astrid/packs/rendering/backends/ffmpeg/run.py`

Represent a layer as an ordinary managed-media clip on a visual track with an
explicit positive interval. Keep runtime-owned object identity and the current
visual-track ordering rule. The first supported subset is canvas-sized PNG with
verified alpha and normal canonical layer order; do not add arbitrary transforms or
a PNG-specific timeline schema.

Acceptance evidence: a real short FFmpeg render with pixel checks before, during and
after the overlay; two-layer ordering; alpha, duration and frame-boundary checks;
rejection of no-alpha and unsupported geometry/encoding; audio retention; and no
regression in existing text overlays. Update the rendering skill and timeline
cookbook with one canonical example and the limits.

### 3. Runtime orchestration and stitching

Treat commits `789edeca` and `f614d6d7` as design evidence, not mergeable code.
The reviewed typed handoff/finalizer contract is now ported into the current Astrid
seams and delegates lifecycle to the owning runtime continuation kernel.

Start with a compatibility spike against the current runtime:

1. Admit two existing child capabilities.
2. Let them finish out of order and aggregate outputs in declared order.
3. Author or update a canonical timeline using those outputs.
4. Invoke the existing public `rendering.render` path with a version-pinned
   snapshot.
5. Retrieve the final output and receipt through ordinary run APIs.

Use existing runtime dependency/continuation primitives if they exist. If they do
not, add the smallest durable dependency/wait primitive in the owning runtime,
regenerate the pinned client, then add the Astrid wiring. Do not use a pack-local
database, a one-shot event poll, or a blocking loop. Prove duplicate admission,
restart/resume, partial failure, cancellation, retry fencing, paginated event/task
reads, ordered output identity and canonical version pinning.

The compatibility spike and owning-runtime prerequisite are complete. The Astrid
contract emits root/child/stitch admissions with declared ordering and dependency
metadata; the runtime continuation suite proves durable waiting, restart/resume,
retry/cancel fencing, and pagination. The finalizer feeds ordered CAS inputs to
the public `rendering.render` route. A paid live generation is outside this local
validation and is recorded as such in the evidence.

## Execution order and ownership

Executed through the Megado delivery run with three parallel implementation lanes plus one coordinator. Detailed [tasklist](../../.otto/runs/canonical-timeline-feature-ports/tasklist.md), dispatch briefs, and evidence remain in the ignored local control directory.

1. Preserve selected historical dirty payloads once and capture protected-file
   hashes. Replacement and orchestration read-only discovery may start in parallel.
2. Lane A settles replacement semantics and implements managed-media replacement;
   lane B implements PNG layers; lane C independently investigates runtime support
   and implements the minimal orchestration path. Only actual dependencies wait.
3. Assign disjoint files to each worker. Shared runtime/SDK modules, generated
   clients, manifests and lockfiles have one writer at a time. Each lane owns its
   focused tests and supplies documentation examples to the integration owner.
4. Review the replacement runtime boundary before dependent work builds on it.
   Independent PNG/orchestration work continues. Freeze affected writers while
   collecting test or review evidence.
5. One integration worker consolidates shared documentation, including timeline
   skills, and runs the affected suite and integrated current-runtime scenario.
   Final review checks the complete accepted feature set.
6. After final PASS, freeze writers and integrate/commit only reviewed owned paths
   into local main; record exact SHAs, dependency provenance, evidence identity and
   protected-file hashes. This is task T8, the final main integration checkpoint.
7. Push the runtime provenance branch, then push the reviewed Astrid commit to
   `origin/main` and verify the remote SHA.
8. Perform scoped historical cleanup only after those commits are reachable from
   main and fresh archival/ref/active-use checks pass.

Future execution stays in the current local main checkout, without a separate
worktree. Because workers already edit main, the final merge step is consolidation
and scoped commits, not a branch merge. The coordinator exclusively owns staging
and Git ref operations; unrelated dirty work stays untouched. GitHub push is the final publication step after the integrated review; production
deployment is outside this plan.

## Cleanup after acceptance

After the accepted commits are reachable from `main` and the dirty payloads have a
verified archive, delete the rejected historical feature branches and worktrees:

- GPU direct-image/media snapshots;
- VACE/LTX/Wan historical snapshots unless a focused safety fix was actually ported;
- broad zero-shim/final architecture branches;
- stale canonical-v2/generation-bridge identities whose behavior is already on
  `main`.

Keep the generation worktree until both editing ports are accepted or its selected
feature diffs are independently archived. Keep active Hivemind, handover, resident-
oracle, runtime and dirty authored work protected. Recheck live GitHub refs by exact
SHA before any remote deletion; cached `origin/*` refs are not proof.

## Estimate and stop conditions

Managed-media replacement: roughly 2–4 focused engineering days. PNG layers:
roughly 1–2 days. The orchestration spike: 1–2 days; a full runtime dependency
extension may add several days and belongs to the runtime owner. The main uncertainty
is whether the pinned runtime already supports durable dependency continuation.

Stop and adjudicate if the runtime contract cannot provide atomic timeline mutation,
semantic retry identity, or durable orchestration continuation without introducing a
second authority. Do not merge the historical branches to avoid answering those
questions.
