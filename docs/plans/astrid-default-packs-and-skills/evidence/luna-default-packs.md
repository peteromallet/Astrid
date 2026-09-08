# Astrid default-pack provisioning plan (Sol)

## Recommendation

Use a **managed, pinned source checkout/materialization owned by the generic
setup layer**, with Astrid consuming its resulting pack root through one shared
pack-root resolver. Do not vendor Hivemind into the Astrid wheel and do not
make the Hivemind Python wheel/console entry point the pack boundary.

The generic setup/default-source manifest should describe Hivemind as a
default component with:

* canonical repository URL and an immutable commit SHA (never a branch/tag);
* expected pack id/version and the Hivemind pack subtree path;
* expected `pack.yaml` schema version (v2) and a digest of the normalized
  manifest/tree or release archive;
* the materialized pack root and source revision in the installed source
  profile.

Setup fetches the pinned revision once and materializes it into a managed
pack store. After successful installation, discovery is fully offline. A
transactional replacement of the materialized revision handles upgrades;
uninstall removes only the managed Hivemind component and its registry record.
User-supplied roots remain separate and are never deleted by default-pack
operations.

This keeps source provenance and review in the canonical Hivemind repository,
supports future default packs with the same mechanism, and gives the generic
setup/runtime owner the lifecycle it already owns. Astrid remains a consumer
of a filesystem pack root, which matches the existing discovery contract.

## Evidence and current boundaries

* `Astrid/astrid/core/pack/discovery.py` has ordered `source`, `local`,
  `extra`, and `env` layers. `extra_pack_roots` and `ASTRID_PACKS_PATH` are
  read-only discovery inputs; there is no acquisition, install, update, or
  uninstall store.
* `Astrid/astrid/core/pack/loader.py` admits only a regular `pack.yaml` through
  `validate_canonical_pack`; malformed external packs are skipped by the
  external scan. The installed package computes its source root from
  `Path(__file__)`, so source checkout and wheel paths differ unless the
  resolver explicitly handles both.
* `Astrid/astrid/sdk/discovery.py` passes the same explicit extra roots into
  executor/orchestrator/element registries, but does not resolve a managed
  default store. The pack CLI independently builds `packs_root()` plus
  `--pack-root`/`ASTRID_PACKS_PATH`; this is a source-root consistency seam.
* Astrid HEAD has no `astrid/packs/hivemind` tree. The dirty worktree has an
  uncommitted Hivemind bundle, but that is not HEAD evidence and must not be
  treated as the implementation baseline.
* The canonical external Hivemind checkout is currently at
  `abe41fdf72df3bbcfe45087eae64ccf50a1bb809` (working tree has untracked
  files). Its `pack.yaml` is `schema_version: 1` and includes v1-era fields
  such as `install_tier`, while Astrid's strict v2 canonical validator requires
  `schema_version: 2` and rejects unknown fields. The checkout therefore needs
  an upstream v2 manifest/release (preferred) before it can be admitted. Do
  not assume that `install_tier` is valid in v2 merely because current dirty
  Astrid skill code uses it as a taxonomy projection.
* Astrid's skill state has default-pack opt-out machinery in the dirty bundle,
  but that is harness skill-link lifecycle, not runtime pack acquisition. It
  should not be reused as the source of truth for pack installation.

## Why the alternatives lose

### Pinned checkout via generic setup (recommended)

Pros: offline after setup; immutable and auditable revision; preserves the
external repository's ownership; supports atomic upgrades and explicit
uninstall; can share one store with future defaults; no runtime dependency
import hacks. The materialized root is directly consumable by existing
discovery and generic-host execution.

Costs: requires a small setup/store registry and a canonical root resolver;
the generic setup layer must expose the installed root to Astrid and must
verify the pinned tree before activation. It also requires Hivemind to publish
a strict v2 pack manifest and stable pack layout.

### Separate Hivemind wheel/entry point

This is attractive for Python dependency management, but a console script is
not a pack root and would force CLI/SDK/runtime to invent different import and
subprocess paths. A normal wheel install is not offline unless the wheel is
already bundled in a wheelhouse, and pip's dependency resolution weakens the
single immutable source pin unless a lock plus artifact digest is added. It
also makes uninstall/upgrade a Python-environment operation rather than a
pack lifecycle operation. It can remain an optional distribution artifact
later, but should not be the default-pack contract.

### Vendoring into Astrid

This gives the simplest cold install and source/wheel parity if every Hivemind
file is copied into `astrid/packs/hivemind`, but duplicates ownership, turns
Hivemind updates into Astrid releases, makes explicit uninstall meaningless,
and prevents users from selecting an independently pinned Hivemind revision.
It also creates a high-risk path for the current dirty bundle to be mistaken
for canonical source. Vendoring is reasonable only if the project deliberately
declares Hivemind part of Astrid's first-party release, which is contrary to
the external-pack requirement.

## Concrete implementation seams

1. **Generic setup source/default manifest (owner: setup/runtime repository).**
   Add a versioned default-pack entry, for example `packs.hivemind`, with
   `source_url`, `revision`, `pack_subpath`, `pack_id`, `pack_version`,
   `manifest_sha256`, and optional full-tree/archive digest. The setup
   transaction clones/fetches into a staging directory, checks detached HEAD,
   validates the expected manifest and digest, then atomically renames the
   revision into the managed store. Persist active component metadata in the
   source profile, including absolute root and revision/digest.

2. **Managed store lifecycle (owner: generic setup).** Add explicit commands
   or API operations equivalent to `packs install hivemind`, `packs update
   hivemind`, and `packs uninstall hivemind` (exact CLI spelling can follow
   the setup owner's existing command family). Install/update must be
   idempotent and leave the prior active revision intact on failure. Uninstall
   must refuse or require an explicit flag when the component is a configured
   default, then remove only the managed component and source-profile entry.
   Do not mutate `ASTRID_PACKS_PATH` roots or project-local packs.

3. **One Astrid root resolver (owner: `astrid.core.pack`).** Add a small
   resolver/config seam (likely `core/pack/roots.py`) that returns ordered
   roots for a given process: wheel/source `packs_root()`, managed default
   roots from the setup source profile, project-local root, explicit
   `extra_pack_roots`, and `ASTRID_PACKS_PATH`. Keep provenance labels and
   precedence explicit; reject duplicate active IDs deterministically rather
   than letting each caller choose a different winner. If no setup profile is
   available, preserve current behavior and continue with source plus explicit
   roots.

4. **Route every consumer through that resolver.** Refactor
   `discover_pack_metadata`/canonical discovery, SDK registry loading,
   `astrid.core.pack.cli` list/status/inspect/search, element/render registries,
   and skill discovery to use the same resolved roots. The runtime generic host
   must receive the resolved pack root/provenance in the invocation context so
   it executes the exact pack the CLI/SDK selected. Keep `extra_pack_roots` and
   `ASTRID_PACKS_PATH` as user extension inputs, with explicit roots taking
   their documented precedence over managed defaults only when the policy says
   so; never silently shadow a managed id.

5. **Canonical Hivemind admission.** Upgrade the external checkout's
   `pack.yaml` to v2 in Hivemind (or publish a v2 adapter release). It must use
   only fields accepted by `Astrid/astrid/core/pack/schemas/v2/pack.json`, have
   safe relative content paths, and declare the actual capabilities and
   permissions. Astrid should not silently translate v1 manifests at install
   time; that would make provenance and validation non-reproducible.

6. **SDK/CLI API shape.** Keep discovery APIs pure/read-only. Add a separate
   setup-backed pack lifecycle API/command; do not revive the retired
   `astrid.core.pack.install*` modules or add a ninth product gateway family.
   The lifecycle command can report `available`, `installed`, `active_root`,
   `revision`, `digest`, and `validation` in JSON. `sdk.discover()` should
   expose source kind and revision/digest provenance for Hivemind.

## Acceptance tests

Use isolated temporary homes/stores and a tiny local Git fixture (no network)
to make the lifecycle deterministic.

1. Fresh install from a pinned commit materializes Hivemind, validates v2 and
   its digest, and then succeeds with network disabled; a new process discovers
   and invokes `hivemind.search` from the managed root.
2. The same fixture proves source checkout, installed wheel, CLI `list/status`,
   SDK `discover/get_capability`, element/render registry loading, and generic
   host execution all report the same pack root, revision, and capability set.
3. A changed commit or manifest/tree digest fails closed before activation;
   an interrupted update leaves the old active revision runnable.
4. Update stages revision N+1, atomically activates it, and reports old/new
   provenance. Re-running update is a no-op. An incompatible v1 manifest is
   rejected with a migration/actionable error and never discovered.
5. Explicit uninstall removes the managed Hivemind entry/root and subsequent
   discovery omits it while Astrid core still works. User extra roots and
   `ASTRID_PACKS_PATH` packs survive unchanged. Reinstall restores the exact
   pinned revision offline if the cached materialization remains available.
6. A user extra pack with a distinct id remains discoverable; duplicate IDs
   across managed/default, explicit, env, and source roots follow one tested
   precedence/error policy consistently in CLI, SDK, and runtime.
7. Wheel smoke test installs Astrid without the Hivemind checkout present, then
   verifies managed-root discovery only when setup provisioned it; no import
   fallback reaches a developer checkout.
8. Security/provenance tests reject symlinked pack paths, unpinned revisions,
   dirty source snapshots (if setup accepts local sources), and tree changes
   after activation; inspect output includes declared permissions and exact
   source digest.

## Open decisions before implementation

* Confirm the generic setup owner and its actual default-source manifest/API;
  no such manifest was found in the Astrid HEAD tree, so exact filenames and
  command names cannot be asserted here.
* Choose whether the managed store is under the neutral runtime support root
  or an Astrid-specific user-data root. The source profile must be the single
  persisted authority either way.
* Decide whether uninstall deletes bytes immediately or keeps content in a
  content-addressed cache for offline reinstall; registry deactivation must be
  immediate in both cases.
* Obtain/pin an upstream Hivemind v2 manifest/release and record its commit
  plus digest. The current checkout's v1 manifest is a hard admission blocker.
* Define duplicate-ID policy explicitly (recommended: managed default cannot
  be shadowed silently; user override requires an explicit opt-in flag and is
  shown in provenance).

## Scope guard

This memo is planning only. No Astrid source, Hivemind checkout, packaging,
runtime, or installation state was changed.
