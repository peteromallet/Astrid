# Canonical timeline continuation-to-render amendment

Status: implementation complete on current Astrid `main`; awaiting final integrated review and scoped publication.

This is the blocking orchestration amendment to
[`canonical-timeline-feature-ports.md`](canonical-timeline-feature-ports.md). It
executes directly in `/Users/peteromalley/Documents/reigh-workspace/Astrid` on
branch `main`, currently based at `8150c3b70887495f0fae4a55c1ac70085a900550`.
Historical branches are source evidence only. The four protected dirty payloads
and `Astrid-oracle/.agentbox/astrid.env` remain untouched.

Astra sized this work at **2–4 focused engineering days**. Packages A–D are now implemented; the final gate is the remaining publication step. A quick helper would
only demonstrate a happy path and would leave the durable workflow incomplete.
The existing `rendering.render` executor remains the renderer; this amendment adds
the missing runtime-owned authoring and publication seam.

## Outcome

Two existing child tasks can finish in any order. The runtime durably resolves
those outputs, a registered authoring continuation creates a canonical timeline
revision with deterministic clips and registry entries, and the existing public
`rendering.render` route renders that frozen revision. The runtime returns the
ordinary output object, manifest, and receipt and can recover after a crash at
either the timeline-save or render-admission boundary.

## Work packages

### A. Registered authoring continuation (0.5–1 day, normal)

- Add a real executor/capability manifest, preferably
  `astrid/packs/rendering/executors/assemble_timeline/{executor.yaml,run.py}`.
- Accept only the bounded two-child continuation shape: two fenced
  `task.succeeded` edges and `ordered_cas_inputs` aggregation.
- Consume `resolved_children`, selecting one explicitly identified primary visual
  per child. Preserve duplicate object references as distinct clips.
- Derive stable clip IDs from continuation identity and child ordinal; reject
  ambiguous outputs, unsupported media, malformed descriptors, and unsupported
  graph families.
- Keep mutation and lifecycle in the runtime; the executor supplies a typed
  authoring proposal and uses no local database, scheduler, or polling loop.

### B. Fenced publication and recovery (1–1.5 days, xhard)

- Extend the owning runtime protocol/store/service as required for a task-fenced
  publication checkpoint linking authoring task, saved timeline revision, and
  render task/run.
- Persist the frozen prepared request before relying on replay.
- Ensure crash recovery, duplicate replay, cancellation, stale leases, and
  changed-payload idempotency cannot create a second timeline mutation or render.
- Regenerate and repin Astrid’s client only if the protocol changes; prove exact
  source/client byte equality again.

### C. Canonical save and public render linkage (0.5 day, normal; overlaps B)

- Use `RemoteTimelines.save` with expected-version CAS.
- Use the version returned by the save response when invoking
  `AstridClient.invoke_result("rendering.render")`.
- Reuse normal render preflight, materialization, manifest harvesting, output
  publication, and receipt retrieval.
- Fail closed if the save response has no authoritative version.

### D. Runtime-backed acceptance proof (0.5–1 day, xhard)

Create a fresh disposable RuntimeDaemon integration test with local media fixtures
that proves:

1. two children finish out of order;
2. the authoring continuation becomes claimable exactly once;
3. canonical timeline version advances through expected-version CAS;
4. the existing renderer produces the final MP4 and universal manifest;
5. the ordinary runtime APIs return the final output and receipt;
6. duplicate admission, restart, retry/cancel fencing, pagination, repeated object
   references, and an edit between save and render are handled safely.

## Dependencies and stop conditions

A depends on the current continuation contract. B owns any cross-repository
protocol change. C depends on A and B. D runs after A–C and is the final review
packet. Stop and return to Astra if trusted `resolved_children` cannot reach the
authoring executor, publication cannot be fenced by the runtime, or the renderer
would need a second timeline authority. Do not broaden this amendment into all
historical generation families.

## Review and publication

Use the amendment control run in
`.otto/runs/canonical-timeline-feature-ports-amendment/`. The final integrated
review must return PASS against the evidence above before any Astrid commit or
`origin/main` push. The runtime provenance branch may remain published; no
historical cleanup is part of this amendment.
