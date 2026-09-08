# Canonical Hivemind integration plan review

Read-only review of the current Astrid worktree, the existing standalone-tool
decision, and `docs/plans/astrid-default-packs-and-skills/PLAN.md`. The plan
below uses one repo-owned Hivemind interface and one Astrid external-pack
integration path.

## Canonical ownership

`/Users/peteromalley/Documents/banodoco-workspace/hivemind` is the source of
truth. The current upstream checkout is recorded at
`abe41fdf72df3bbcfe45087eae64ccf50a1bb809`; its `pack.yaml` is still schema v1
and therefore cannot be admitted by Astrid's strict v2 validator. Upstream
must first land the consolidated CLI/features and a v2 pack manifest. Astrid
must pin that resulting revision. The personal
`/Users/peteromalley/Documents/poms_skills/hivemind` CLI remains a delegating
launcher or compatibility entrypoint; it is not an Astrid source.

The dirty `Astrid/astrid/packs/hivemind/` tree is a duplicate implementation.
It must not become the integration source. After upstream's v2 pack is
available, remove it from the active discovery path and retain only tests or
documentation that assert the external pack contract.

## One implementation sequence

1. **Upstream prerequisite.** In the Hivemind repository, consolidate the
   personal CLI's commands into the maintained package, reconcile overlapping
   search behavior, add tests for paging/full context/errors, and expose the
   supported entrypoint(s) from that repository. Convert `pack.yaml` to the
   current v2 schema without changing effect/credential semantics. Record the
   immutable revision and manifest/tree digest.

2. **Astrid source setup.** Implement the existing default-packs plan: acquire
   the pinned Hivemind revision into the managed source store, validate the v2
   manifest/tree before activation, persist pack id/root/revision/digest, and
   keep setup/discovery separate. No Astrid code should import Hivemind modules
   from a developer checkout or personal skill directory.

3. **Shared discovery and host handoff.** Resolve managed roots, explicit
   extra roots, and source roots through the existing pack discovery seam. Pass
   the selected root and revision identity into `ensure_pack_host`; the CLI,
   SDK, skill links, registry, and generic host must see the same selected
   pack. Keep the current source/digest admission fence.

4. **Remove the duplicate.** Delete the dirty copied Hivemind pack and its
   bundle-specific preflight/ledger shortcuts after the external fixture is
   admitted. Rewrite `tests/packs/hivemind/` to invoke the pinned external
   pack or a local Git fixture, never `astrid.packs.hivemind` imports.

5. **Workspace scope.** Replace the current hardcoded optional-capability list
   in `astrid/sdk/invocation.py` with generic capability metadata such as
   `project_scope: required|optional|none`. Hivemind read operations declare
   `optional` and may run with a stable workspace/system scope when no project
   is selected; a supplied project remains attached. Write/ingest operations
   require the declared credential/effect admission and preserve project
   association when present.

## Existing runtime contract to reuse

Hivemind's current external executors already use `executor.yaml` command
templates and write machine-readable files such as `results.json` or
`result.json`. Astrid's generic host can materialize inputs, run the declared
argv, capture stdout/stderr, collect declared output paths, publish output
files as managed artifacts, and return the normal task/run receipt. Preserve
the raw JSON file as the primary artifact and keep human summaries on stderr.
Do not create another tool registry, task lifecycle, or output format.

The runtime already provides task/run identity, project_id, idempotency,
lease/fence heartbeats, status, cancel routes, process-group termination,
source/capability digests, network policy/broker, and CAS output publication.
Cancellation is cooperative at the host boundary: a cancel request is observed
by the heartbeat/status pump and terminates the child process group. A tool
cannot undo a remote POST already accepted; effectful Hivemind operations must
therefore retain their existing dry-run/write admission semantics.

Current limitations that acceptance tests must expose rather than paper over:

- generic host execution is pack-discovery based; the managed root handoff is
  not yet complete;
- the upstream v1 manifest is rejected until migrated to v2;
- stdout is diagnostic/result transport, while durable artifacts come from
  declared files; arbitrary stdout must not be inferred as a file artifact;
- failed attempts retain failure diagnostics/status, but outputs are only
  durably published when the runtime settlement path accepts them;
- no claim of cancellation can guarantee stopping a provider-side request
  after network submission.

## Concrete Astrid files/tasks

- `astrid/core/pack/discovery.py`, `astrid/sdk/discovery.py`: one managed-root
  resolver and consistent provenance/precedence.
- `astrid/sdk/host_bootstrap.py`: pass the selected external pack root and
  revision identity into host construction/reuse checks.
- `astrid/core/execution/generic_host.py`: preserve source fencing and use the
  selected root; remove Hivemind-only bundle shortcuts.
- `astrid/skills/{__init__.py,registry.py,state.py}`: consume the shared
  installed-pack inventory; remove `pack.id == "hivemind"` default logic.
- `astrid/sdk/invocation.py`: generic `project_scope`; keep runtime task/run
  records for workspace-scoped reads.
- `astrid/packs/hivemind/**`: remove from active discovery after external v2
  validation; do not port its domain code.
- `tests/packs/hivemind/`, `tests/integrations/`, and setup/skill tests: use a
  local pinned Git fixture and assert identical CLI/SDK/host provenance,
  JSON/file outputs, paging, failures, cancellation, workspace scope, and
  effect admission.

## Gate before Astrid implementation

Do not build against the current upstream head as though it were usable: the
v1 manifest is a hard prerequisite failure. First obtain the upstream
consolidated revision and v2 manifest, then point Astrid's default declaration
at that immutable revision. Until then, the current dirty Astrid Hivemind
bundle is evidence of the integration target, not a canonical implementation.

