---
name: pack-builder
description: "Design and implement reusable Astrid packs and capabilities. Use when deciding whether a missing idea belongs in an existing executor, a new executor, an orchestrator, a visual element, or a timeline rendering extension, and when authoring the corresponding manifests and entrypoints."
metadata:
  short-description: "Build reusable Astrid extension packs"
---

# Pack Builder

Use this skill when a maker wants to turn a repeatable capability into an
Astrid extension. Start from the existing catalog and compose what is already
available. A pack is a distribution and namespace boundary for executable
capabilities; it is not a database schema, a second project store, or a new
gateway command.

The detailed contracts are maintained in these authoritative guides:

- [Creating Astrid Packs](../../../../../docs/packs/creating-packs.md) — pack
  layout, manifests, permissions, aliases, validation, and rendering
  extensions.
- [Creating Tools](../../../../../docs/guides/creating-tools.md) — the decision
  rule for composing existing capabilities and choosing an executor,
  orchestrator, element, library, or rendering extension.
- [Pack Contract](../../../../../docs/packs/contract.md) and
  [Pack Taxonomy](../../../../../docs/packs/pack-taxonomy.md) — identity,
  ownership, enablement, maturity, and trust metadata.
- [Discovery for Agents](../../../../../docs/guides/discovery-for-agents.md) —
  the manifest-backed SDK discovery surface.
- [SDK reference](../../../../../docs/reference/sdk.md) — invocation and
  rendering APIs.
- [Capability reference](../references/capabilities.md) — generated inventory
  for quick orientation; when executor, orchestrator, or element manifests
  change, regenerate it with
  [`scripts/gen_capability_index.py`](../../../../../scripts/gen_capability_index.py).
- [Rendering skill](../../../rendering/skill/SKILL.md) — combined timeline and
  rendering work, including the stable render facade and visual escape hatches.

Read only the linked guide needed for the current choice. Do not copy its
schemas or command catalog into this skill; those documents are the source of
truth.

## Choose the extension shape

Use this decision map when an idea is underspecified:

1. **Existing capability** — discover and inspect the catalog with
   `astrid.sdk.discover()` and `astrid.sdk.get_capability(...)`. If existing
   executors can be wired to satisfy the request, add no new implementation.
2. **Executor** — one concrete, independently runnable unit of work: one
   transformation, network call, inspection, import, generation, or artifact
   conversion. Keep its input/output contract narrow and put retry policy and
   branching in a caller.
3. **Orchestrator** — a reusable multi-step workflow that coordinates
   executors and other orchestrators. Executors must not call orchestrators.
4. **Element** — a reusable visual building block consumed by a timeline:
   an effect, animation, or transition. Put editable visual behavior in the
   element system rather than hiding it inside an executor.
5. **Renderer, planner, or finalizer** — only when extending the protocol-v1
   timeline rendering backend. These are rendering extension manifests, not
   public executor kinds. Keep `rendering.render` as the public facade and
   hand off combined timeline/rendering questions to the
   [rendering skill](../../../rendering/skill/SKILL.md).
6. **Shared library** — only for code with no public runtime of its own. Keep
   reusable helpers with the owning pack or component unless the change is
   clearly a shared core concern.

For a one-off experiment, keep scratch output under a run directory and do
not create a discoverable capability until the behavior is reusable.

## Build a pack

For a new reusable pack, follow the supported authoring path in
[Creating Astrid Packs](../../../../../docs/packs/creating-packs.md):

1. Scaffold the pack with the pack CLI's `new` operation.
2. Declare the pack identity, taxonomy, content roots, agent guidance,
   permissions, and documentation in `pack.yaml`.
3. Add each executor under `executors/<slug>/` with its
   `executor.yaml`, `run.py`, and staging notes. Add orchestrators under
   `orchestrators/<slug>/` with the corresponding orchestrator manifest and
   entrypoint. Add elements under the canonical element root with their
   `element.yaml` and implementation files.
4. Reuse existing SDK capabilities through `astrid.sdk.invoke(...)`; do not
   open the runtime database, create a local state authority, or invoke
   `run.py` directly.
5. Validate the complete pack with the pack validator before treating it as
   discoverable. Static validation checks manifests, roots, docs, and
   entrypoints; it does not execute pack code or install dependencies.
6. Expose the reusable behavior in the pack's `skill/SKILL.md` and keep its
   guidance focused on when to use the pack and its normal entrypoints.

Use the manifest schemas and templates linked by the pack guide instead of
inventing fields. Declare network, files, subprocesses, environment, GPU,
and external-service needs in the pack permissions; declare specific secret
environment variables on the component manifest that reads them. Permission
metadata is disclosure-only in the current contract.

## Implementation invariants

- Discover capabilities through the SDK and manifests. Do not guess ids from
  source-tree names.
- Every invocation has an explicit capability `kind`; executor and
  orchestrator ids are qualified by their owning pack.
- Durable projects, media, timelines, tasks, runs, receipts, and events belong
  to the workspace runtime. Attempt-local files are delivery artifacts, not a
  parallel ledger.
- Keep executor work atomic and inspectable. Workflow shape, retries,
  conditional branches, and child calls belong in orchestrators.
- Register aliases on the pack that owns the canonical capability. Do not
  create shadow sources or compatibility sidecars.
- For elements, preserve the owning pack's element kind and manifest contract;
  an element is selected by the timeline and rendered through the normal
  rendering path.
- For rendering extensions, use the pack's `extensions.rendering` manifests
  and the protocol-v1 authoring path. Do not add a renderer branch to the
  facade or ask callers to import a backend module.
- Do not add a schema pack, SQL migration, local schema registry, or new
  top-level gateway family as part of capability authoring.

## Verify the result

Before handoff, confirm that the pack's manifest and every component pass the
static validator, that all declared paths stay inside the pack, and that a
cold agent can discover and inspect the capability from the SDK. Run a smoke
invocation only when the requested change includes runtime behavior and the
required runtime/dependencies are available. For renderer extensions, use the
renderer-specific validation and smoke path in the [pack guide](../../../../../docs/packs/creating-packs.md)
and its linked render-backend contract.
