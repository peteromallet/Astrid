# P0–P11, Q and H: project DAG and exclusive ownership

This is a newly consolidated dispatch map for the requested whole program.
No existing saved P0–P11/F0–F3 map was found in the inspected control roots.
It reconciles the exported plans without claiming prior adoption, product
completion, or delivery authority. P IDs below are program IDs; similarly named
tasks inside an individual run retain their original meaning.

| ID | Outcome / owner | Inputs and checkpoint | Exclusive implementation surface | Required proof |
|---|---|---|---|---|
| P0 / A | Managed result producer → opaque transport → Astrid verify/publish | Existing G0–G4; F0 | A integration owner: result profile, VibeComfy result emission, lifecycle scoped shipping, Astrid managed-result consumer | C-G0–C-G4 CPU/fake evidence; exact reviewed refs; live clause removed |
| P1 | Host bootstrap/readiness | F0, P6 profile; fixture work can precede P6 | Host owner: Astrid SDK host bootstrap and RunPod host-start/ready binding | Exact process/runtime/pod/device identity, restart/stale readiness, no accidental termination |
| P2 | Session/device authority | F0; publishes lifecycle half of F1 | Session owner: ManagedToolSession, GenericHost dispatch/retention seam, device exclusion | Single owner, invocation fences, A–D ordering, release-before-replacement, quarantine |
| P3 | VibeComfy lifecycle adapter | P2/F1; P1 for target integration | Vibe owner: Astrid VibeComfy backend; reserved VibeComfy session/prepared extension | Same-set retention, whole-set change, owned server readiness/cancel, local process and fake RunPod evidence |
| P4 | Wan2GP lifecycle adapter | P2/F1; P6 native lock | Wan owner: Astrid Wan2GP compiler/persistent/driver; pinned native Wan2GP API bridge | Durable fake native process, truthful protocol output rebind/observe/close, complete asset key, round-trip engine handoff |
| P5 | Canonical remote jobs | F0; P1/P3 interfaces; P6 profile | Jobs owner: lifecycle job schema/facade/runner; Astrid runpod.exec schema/delegation | C1–C8 in canonical jobs plan; deadline survives disconnect, exact root/custody, failure diagnostics, leave_running |
| P6 | Prebuild/distribution | Source/dependency census; parallel with P1/P2 | Release owner: lifecycle prebuilt/profile and release manifests; reigh-worker build packaging | CPU-verifiable build recipes/digests, offline wheel/source fixtures, model manifest schema and pin validation; hardware reproduction deferred |
| P7 | Caller migration and evidence-gated retirement | Inventory may start now; code integration waits F2/Q; production cutover deferred to L | Migration owner: reigh-worker callers and orchestrator routing/deployment references | Complete caller inventory, CPU/fake managed-path parity, stranded-task recovery and rollback fixtures; retirement deferred |
| P8 | Runtime shot persistence | F0 source census; publishes shot half of F1 | Runtime owner: shot binding/schema/API, CAS, request snapshots, migrations | Typed bounds/roles/media identity, atomic updates, restart/archive/recovery; no pack-local store |
| P9 | Shot input preparation | P8/F1; P3/P5 consumption contract | Input owner: Astrid shot intent/prompt compiler/materializer and H3 adapter | Exact managed media, anchors/video spans/audio, frozen recipe/prompt heads, capability preflight, no dropped roles |
| P10 | Take selection/placement | P8/F1 | Playback owner: Astrid selection/child timeline projection; Runtime writes only through P8 owner | Candidate isolation, one canonical selection, atomic rollback, overlays/audio/timing preserved, concurrent edits |
| P11 | Shot-generation orchestration | P9/P10, P0, F2; P5 if remote | Orchestration owner: Astrid shot coordinator; Runtime queue/approval edits through P8 owner | Fake two-segment chain, approval stop, restart, retry identity, predecessor invalidation, creative pilot deferred to L |
| Q | Qualification stream | Incremental fixtures throughout; F2 → F3 | Q owner: qualification fixtures/evidence only, product fixes assigned back to owner | Cross-repo CPU/fake/offline journey at exact composition; live/native GPU proof excluded |
| H | Portable handoff stream | Parallel now; final refresh after Q/F3 | H owner: this packet only | Closure, exact pins, public retrieval, safe extraction/hashes, readiness and delivery message |

Authoritative scope inputs: [A](control/runs/runpod-managed-generation-20260921/plan.md),
[lifecycle successor](control/runs/gpu-engine-task-path-20260920/plan.md),
[residency decisions](control/runs/gpu-executor-residency-20260920/plan.md),
[Wan parity](control/runs/wan2gp-engine-followup-20260920/plan.md),
[canonical jobs](control/runs/canonical-runpod-vibecomfy-jobs-20260921/plan.md),
[release/prebuild](control/runs/h3-cuda13-golden-template-20260918/plan.md),
[shot generation](control/runs/shot-generation-timeline-20260915/plan.md),
[shot contract](control/source-docs/Astrid/docs/plans/shot-generation-timeline.md).

## Current acceptance scope

Every proof in this map uses CPU/fake/offline evidence under
[the scope amendment](execution-scope.md). Runtime, device, pod and model identities
are fixture identities during validation. Live observations and deployment
promotion belong solely to [deferred gate L](POST-HANDOFF-GPU-GATE.md).

## F0–F3 interface checkpoints

- **F0 — source and result boundary:** P0 neutral contract and complete locked
  producer/transport/consumer tuple, acceptance gaps and active ownership known.
  This packet records the contract; exact acceptance-to-SHA binding remains pending.
- **F1 — lifecycle and shot interfaces:** P2 freezes invocation versus session/
  device identity, adapter methods and cleanup evidence; P8 freezes typed shot
  intent, immutable request identity and CAS selection. These two halves advance
  independently; consumers wait only on the half they require.
- **F2 — integration composition:** pinned host/adapters/jobs/release and
  shot-input/selection composition; CPU fixtures and cross-repository negative
  cases pass. GPU target qualification is outside the current projects.
- **F3 — offline implementation acceptance and handoff:** Q produces source-bound
  CPU/fake evidence, P7 supplies migration code and offline rollback evidence,
  and H refreshes provenance/refs and CPU clean-machine validation. This closes
  current implementation scope when its criteria pass. Record `GPU_UNQUALIFIED`;
  no live gate, production cutover or retirement is part of F3.

Checkpoints bind interfaces and evidence; they add no hidden model-review rounds.
Use the stages already in each owning run's configuration.

## Concurrency and critical path

After F0, P1/P2/P6/P8 and P7's read-only inventory can proceed concurrently.
P3/P4 consume P2's F1; P9/P10 consume P8's F1. P5 joins P1/P3/P6. P11 joins
P9/P10 and the CPU/fake-validated generation path. Q follows each useful integration;
H can refresh controls throughout, with one final sealed snapshot.

The likely critical paths are P2 → P4 → fake bidirectional handoff/Q → P7 migration readiness,
and P8 → P9/P10 → P11 → Q. P6 → P1/P5 can dominate if release pins or native
CPU build preparation cannot be reproduced. Live capacity/credentials are
prerequisites only for deferred L and must not delay these projects.

Consolidated planning forecast: **10–20 working days of elapsed delivery time**
with 4–6 independent implementation slots plus one manager and shared Q owner,
once delivery authority and exact CPU dependencies are ready. This is
a new scheduling estimate, not measured agent throughput or a commitment. The
underlying plans estimate 5–10 focused days for lifecycle, 8–14 for canonical
jobs, and 3–5 for the narrowed shot proposal; overlap prevents simply summing
them. Reserve another 1–2 days for final integration/packet refresh within the
range; external waits, unresolved contract decisions or unavailable models can
extend it. This original estimate included live qualification; re-estimate CPU-only scope
after F1 using actual task durations and track L effort separately.

## Collision rules

GenericHost and ManagedToolSession have one P2 writer. P1/P3/P4 propose patches
through P2 there. Runtime schema/API/queue files have one P8 writer; P10/P11
request changes through P8. Astrid RunPod `_common.py` has one P5 writer; P1
provides host-bootstrap changes to that owner. VibeComfy session/prepared has
one P3 writer; P5/P6 provide requirements, not concurrent edits. Lifecycle
shipping belongs to P0 until A refresh closes, then transfers explicitly to P5.
Release manifests/build files belong to P6, caller migration to P7. Shared tests
follow the corresponding source owner; Q owns only separate qualification tests.
Reserve concrete file paths in each dispatch; broad directory labels above are
the starting allocation, not permission to edit all files in them.
