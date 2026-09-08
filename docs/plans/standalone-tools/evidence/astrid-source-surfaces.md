# Astrid source surfaces for external Hivemind provisioning

Read-only Luna mapping of the Astrid checkout at HEAD
`0c852b7748f9f519413ec96f037b04b3d90e70a2a`, with substantial pre-existing
dirty changes. No product code, runtime, or tests were changed for this report.
The canonical Hivemind CLI is handed off at branch commit
`52e6e357aeba15861b6237b2fa6dd48af2e0a607`; Astrid must consume that external
source after H3, rather than reimplementing it.

## Current source and manifest authority

`astrid/core/pack/loader.py:27-57` defines the in-tree packs root and scans
child directories for `pack.yaml`. `load_pack_manifest()` at lines 60-91
admits only canonical `pack.yaml`, calls the strict canonical validator, and
projects v2 fields into `PackDefinition`. `pack_manifest_path()` at lines
123-133 fails closed when only legacy manifest names exist.

`astrid/core/pack/canonical.py:38-44, 340-354` owns the v2 schema path, safe
identifier/path rules, YAML duplicate-key handling, and external-source enum.
The validator also computes resource handles/digests and provenance; the
resulting `CanonicalPackEntry` exposes source, root, manifest and resources
(`canonical.py:299-337`). This is the admission seam for Hivemind's upgraded
manifest, not a place to add Astrid project metadata.

`astrid/core/pack/discovery.py:41-43, 107-153` provides canonical read-only
discovery for local/extra/env roots. The broader `discover_pack_metadata()` at
lines 160-280 layers source, local, extra and `ASTRID_PACKS_PATH` roots,
deduplicates external roots and isolates broken external manifests. Its
`DiscoveredPack` carries the pack definition, source kind, priority and skill
roots (`:46-87`). This is the smallest shared inventory seam: add managed
verified roots as an existing source kind or an equivalent inventory input,
then pass that same result to all consumers. Do not create a second registry.

The current source scan is observational. It does not acquire or materialize
packs. The default-packs plan's proposed XDG managed checkout/state layout and
staged activation remain proposals, not implemented behavior.

## Consumers that must share the resolved root

`astrid/sdk/discovery.py:22-130` forwards `project_root` and
`extra_pack_roots` into executor, orchestrator and element registries, and
`_discover_pack_inventory()` calls shared `discover_pack_metadata()`. The
registry loaders are therefore existing consumers of a future managed-root
inventory.

`astrid/skills/discovery.py:130-209` currently adds only source-tree skills
plus discovered `extra` and `installed` kinds. Its docstring and filter still
use the old `installed` label, while core discovery emits `env` (`core/pack/
discovery.py:41-43`). That is an actual bridge mismatch to fix when provisioning
is implemented. `list_skills()` also has an explicit `packs_dir` compatibility
path that intentionally bypasses shared discovery (`skills/discovery.py:205-209`).

`astrid/skills/__init__.py:19-62` contains dirty prototype default selection:
it reads manifests and hardcodes `pack.id == "hivemind"` as a compatibility
default. This is implementation drift, not an authority. Setup should provide
the active installed inventory; skills should consume descriptors and preserve
per-harness opt-outs. `astrid/skills/registry.py:41-94,133-168` renders the
managed registry from `list_skills()` and writes the current target file, so a
future writable composed view must become its target rather than a source-tree
write.

`astrid/skills/harnesses/base.py:37-83,109-175` owns per-harness install,
verification and symlink safety. The adapters are reusable for a composed
skill view; `is_ours()`/orphan pruning deliberately touch only Astrid-owned
links. Do not delete personal or foreign skills during migration.

## Host root identity and dependency bootstrap

`astrid/sdk/host_bootstrap.py:309-345` validates the runtime worker handoff,
source checkout safety and pack root. `:335-377` derives source digest and
runtime identity through a worker health check. `:394-427` includes Python
executable, endpoint, source checkout, source digest, runtime instance/epoch,
schema digest, credential and support paths in reuse identity. This already
prevents a stale host from silently serving another source revision.

The launch boundary at `host_bootstrap.py:440-464` passes the source pack root
and checkout explicitly, removes ambient `ASTRID_PACKS_PATH`, and constructs
`PYTHONPATH` from the selected checkout plus dependency site-packages. The
render dependency helper at `:148-200` carries explicitly supplied Python
dependency roots and resolves Node/Remotion/timeline-schema dependencies from
the selected source. This is the correct runtime reuse point; avoid a new
pack manager or ambient-path shortcut.

`astrid/sdk/autobootstrap.py:75-125` owns the neutral launcher invocation,
bounded timeout, JSON result validation and runtime identity checks. It does
not provision packs. `ensure_pack_host()` is reached only when the launcher
returns worker credential/source-checkout handoff fields (`autobootstrap.py:
187-193`). A provisioning implementation must therefore make the launcher or
its persisted source profile provide the verified selected root; it should not
reconstruct that profile inside Astrid.

## What is implemented versus proposed

Implemented and reusable: strict v2 validation, read-only layered discovery,
registry loading from explicit roots, skill discovery/link safety, host source
checkout digest/reuse identity, dependency-path filtering, and neutral-runtime
handoff validation.

Dirty or plan-only: default Hivemind acquisition, immutable source pin
activation, XDG source inventory, offline/check/disable/restore setup commands,
writable composed skill views, and passing a managed root through the neutral
launcher. The existing `astrid/packs/hivemind/` tree and `tests/packs/hivemind/`
are dirty bundled copies; they are evidence/prototype material, not proof that
external Hivemind provisioning works.

The proposed default-packs API and storage contract are in
`docs/plans/astrid-default-packs-and-skills/PLAN.md` (planning complete,
implementation uncertified). The standalone-tools plan's A1-A3/V1 sequence
depends on H3 in upstream Hivemind; H3 is not ready for Astrid integration.

## Smallest future changes and acceptance evidence

1. Add a setup-owned declaration/installer that stages and validates the
   reviewed Hivemind revision into the planned managed root/state layout,
   preserving the previous active revision on failure.
2. Extend the existing discovery input/inventory so SDK registries, skills and
   host bootstrap receive the same root, source kind and revision identity.
3. Correct the skills source-kind bridge and compose a writable harness view;
   keep source-pack instructions linked, not copied.
4. Make the launcher/source profile carry the selected root; include its
   identity in host reuse checks already present above.

Later acceptance should cover online provisioning, offline reuse, failed-update
rollback, duplicate-ID precedence, read-only discovery, source-digest host
restart, installed-wheel skill resources, and standalone-versus-Astrid Hivemind
argv/output/exit parity. Tests must use fixtures and must not write to the
Hivemind corpus. No implementation or test run was performed for this report.

## Planning-run policy

The existing run record is
`.otto/runs/astrid-default-packs-and-skills/run.yaml`: `planning_only`, Luna
coordinator/normal reviewers, Sol xhard roles, Astra oracle/final reviewer,
oracle `max_calls: 3`, and no executable review stages. This report preserves
that policy; it does not authorize delivery or runtime work.
