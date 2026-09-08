# Canonical tool ownership and Astrid integration

Status: repository investigation complete; initial upstream CLI consolidation
implemented and reviewed. See `PLAN.md` for completed and remaining tasks;
the personal launcher and Astrid discovery are not yet switched.

The user rejected a design built around two integration levels. The evidence
documents are exploratory findings; this decision supersedes their proposals
for parallel CLI and semantic capability families.

## Decision

Keep each tool's behavior in its owning repository. Astrid consumes that
repository's supported interface through its existing external-pack execution
path. An adapter contains invocation and result mapping, not another
implementation of the tool's features. Use one integration contract rather
than a separate framework for direct tools and shims.

For Hivemind, consolidate the complete interface in `banodoco/hivemind`.
Today that repository supplies seven executors and `hivemind-search`; the
broader `hivemind` command is maintained separately in `poms_skills`. Preserve
its features by moving their ownership into Hivemind, reconciling overlapping
query code with the repository implementation, and making existing entrypoints
delegate to the same code. Do not copy either implementation into Astrid.

Astrid should provision and admit that external source pack at a known
revision, using the existing default-packs plan. Its runtime remains the owner
of tasks, runs, cancellation, provenance, logs and output artifacts. Knowledge
reads can be workspace-scoped; project work uses an explicit project or the
persisted selection.

## Implementation sequence

1. Consolidate Hivemind's CLI features and tests in its upstream repository;
   document its public commands and preserve existing callers with delegating
   entrypoints where needed.
2. Put the thin Astrid integration in that owning source/distribution, using
   existing external executor contracts.
3. Complete verified external-pack provisioning in Astrid and remove the
   copied Hivemind implementation from the active discovery path.
4. Verify the same representative commands standalone and through Astrid,
   including full-message/context retrieval, paging, failures, cancellation,
   workspace scope and runtime artifact retrieval.

Only extend core contracts when these tests demonstrate a concrete missing
capability. Do not introduce another tool registry, installer database, query
implementation, or speculative integration hierarchy.

## Evidence

- `evidence/hivemind-inventory.md`
- `evidence/hivemind-cli-ergonomics.md`
- `evidence/runtime-contracts.md`
- `../astrid-default-packs-and-skills/PLAN.md` (existing source ownership and
  provisioning plan; explicitly not yet certified as implemented)
