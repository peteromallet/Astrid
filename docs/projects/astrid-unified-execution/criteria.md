# Frozen criteria C01–C16

Read-only planning criteria copied from the original custody goal. These are
acceptance definitions, not evidence that implementation or tests ran. Final
acceptance requires the complete frozen composition and the evidence classes
specified by the authoritative v3 plan.

- **C01 — Sole authority:** all supported tasks use Runtime admission, fenced
  claim, heartbeat, cancellation, CAS publication, and settlement; no second
  durable task truth exists.
- **C02 — Sole launch path:** the supported Worker profile launches and
  supervises exactly one `GenericPackHost`; Worker owns no task loop/client.
- **C03 — Wan coverage:** every retained supported Wan/WGP route maps to typed
  Astrid pack capability semantics; zero supported native-Worker WGP routes
  remain.
- **C04 — Vibe coverage:** every retained supported VibeComfy route maps to
  typed Astrid pack capability semantics on both required profiles; zero
  supported Worker-Vibe routes remain.
- **C05 — Producer cutover:** every retained Astrid/Reigh producer creates the
  canonical runtime capability task; no supported producer creates a legacy
  Worker task.
- **C06 — Neutral Worker:** Worker contains only the thin launcher,
  environment/model readiness, telemetry, process prerequisites, and consumed
  neutral utilities.
- **C07 — Identity/readiness:** portable capability identity excludes machine
  paths while host readiness verifies exact interpreter, engine/node/model
  bytes, GPU/VRAM, scratch, ports, and roots before claim.
- **C08 — Warm equivalence:** cold and warm executions are behaviorally
  equivalent; incompatible identity/resource state prevents reuse; losing
  warmth is harmless.
- **C09 — Lifecycle:** cancellation, lease loss, runtime epoch change, crash,
  drain, and restart cannot publish or settle stale work and leave no orphaned
  owned process/queue entry.
- **C10 — Artifact custody:** large outputs stage, hash, validate, promote to
  runtime CAS, and settle exactly once under the live fence.
- **C11 — Zero legacy path:** legacy routers, template selectors, backend
  flags, Supabase task authority, direct engine entrypoints, and compatibility
  fallbacks are deleted from supported source/reachability; forbidden scans
  and dependency closure pass.
- **C12 — GPU proof:** one real Wan2GP task and VibeComfy `pip_embedded` plus
  `checkout_server` tasks execute through the canonical Worker-launched path,
  including warm reuse and cancellation evidence.
- **C13 — Route completeness:** one finite census gives every baseline route a
  migrated or removed disposition and ends with zero retained legacy owners.
- **C14 — Integrated journey:** one immutable multi-repository composition
  passes cold launch, task admission, claim, execution, progress, CAS output,
  exact settlement, second compatible warm task, cancel, independent restart,
  interrupted-attempt recovery, and forbidden-path proof.
- **C15 — Regression safety:** affected Astrid, Runtime, Worker, and required
  Reigh producer suites pass; unrelated Stage1 authority remains intact.
- **C16 — Simplicity/alignment:** final reviewers confirm the North Star is
  advanced without a parallel abstraction, shim, hidden fallback, or
  ceremonial machinery.
