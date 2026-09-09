# Sol judgment — canonical-pack beta gap at `7ac50c12`

Date: 2026-08-31  
Reviewed revision: `7ac50c12e8e4d90988fee603ffdb9896e5628792`  
Authoritative target: `/Users/peteromalley/Documents/reigh-workspace/Astrid/.oracle/prep/canonical-pack-beta/plan.md`  
Compared planning artifact: `.oracle/plan.md` (2,317 lines)

## Verdict

No canonical-pack beta implementation has landed at this HEAD. Relative to the
merge base with `main` (`44bfda77fccafd6170711a2208f7b15a0be959ca`), every committed
change is under `remotion/` and concerns fonts/package data; there are no changes
under `astrid/`, `tests/`, `docs/`, `scripts/`, or `pyproject.toml`. Those product
paths are also clean in the worktree.

What exists is the substantial pre-beta substrate described by the reduced plan:
a v1 capability-pack system, a strict and well-tested but separate schema-pack
system, the real timeline/shots/references/runaway persistence slices, safe SQLite
migrations, typed services, and old wheel/doctor/backup/restore coverage. The beta
work is therefore a consolidation and hard cut, not a greenfield build—but none of
the consolidation has started.

The 2,317-line `.oracle/plan.md` must not be executed as written. It expands the
reduced target into a redesign of installed-pack records, revision immutability,
capture-time admission, operation snapshots, Python-origin policing, exhaustive
source classification, mandatory documentation coverage, new inspect behavior,
and elaborate evidence machinery. The user explicitly rejected this lifecycle /
marketplace-adjacent expansion. It also contradicts the reduced contract in two
material places: it mandates integer `schema_version: 2` instead of the reduced
plan's accepted `"2"`, and it omits `database.default_enabled` while selecting
every bundled database contribution into an unconditional four-pack standard.

The smallest correct execution is the five-seam cut described at the end of this
report. In particular, preserve the current default database behavior by marking
`timeline`, `shots`, and `references` default-enabled and `runaway` non-default,
unless a separate product decision explicitly changes that behavior. The reduced
plan provides the opt-in mechanism; the current product and its tests deliberately
exclude `runaway` from the standard composition.

## Scope anchor from the reduced plan

The reduced end state is precise enough to decide scope:

- One `pack.yaml` v2 is parsed once into one complete immutable canonical object
  and projected into the existing typed capability and schema registries
  (reduced plan lines 12–34, 219–245).
- Standard database composition is fixed by bundled manifests that explicitly opt
  in through `database.default_enabled`; `schema_migrations` remains the only
  applied-state record and there is no project composition lock (lines 36–44,
  113–174, 268–292).
- Existing external installed capability packs may remain on their current
  discovery path; external `database` is simply rejected (lines 247–266).
- Application, SDK/read probes, doctor, backup, restore, and wheel validation must
  share the same bundled database projection (lines 294–310).
- No lifecycle, project activation, dynamic database packs, marketplace, dynamic
  factories, or compatibility period is required (lines 312–324, 337–353,
  482–500).

That scope is narrower than the worktree plan and should control execution.

## What is already implemented and should be reused

### 1. Capability-pack substrate — implemented, but still v1 and not canonical

- `PackDefinition` is a frozen dataclass carrying identity, manifest/root paths,
  metadata, content, agent, aliases, permissions, extensions, and taxonomy
  (`astrid/core/pack/definition.py:12-53`). It is not the required complete
  immutable authority: several fields are mutable dictionaries, it has no
  database contribution, and provenance is added elsewhere.
- Shared discovery already covers source, local, explicit extra, environment, and
  installed sources with `DiscoveredPack.source_kind`
  (`astrid/core/pack/discovery.py:39-94`, `211-259`). Typed executor,
  orchestrator, element, rendering, generation, and skill consumers already use
  this substrate.
- Aliases, forks, overrides, validation, installation, update, rollback,
  uninstall, revision storage, and trust inspection already exist. This is a
  reason to leave the external capability lifecycle alone, not to redesign it.
- First-party pack validation and tests are extensive. The focused old-system
  capability/discovery/doctor/backup lane completed with `173 passed, 20 subtests
  passed`.

The loader and validator are currently different authorities:

- Runtime manifest discovery accepts `pack.yaml`, `pack.yml`, and `pack.json`
  (`astrid/core/pack/_common.py:16-19`).
- Runtime loading accepts schema-less manifests, defaults `name` and `version`,
  and has a legacy flat-YAML fallback (`astrid/core/pack/loader.py:110-152`,
  `184-240`). Tests intentionally assert those defaults
  (`tests/packs/test_pack_yaml_schema.py:28-49`, `1768-1788`).
- Static validation knows only schema version 1 and requires schema validation
  through a separate path (`astrid/core/pack/validate.py:66-105`, `257-297`).

This exactly confirms the reduced plan's “complete and centralize” gap.

### 2. Database/schema substrate — implemented and strong

- The separate schema manifest parser is strict and immutable. It requires an
  exact 11-field shape, validates namespaced vocabulary, migration/table claims,
  dependency grammar, repositories, conformance, and mounts
  (`astrid/core/schema_packs/manifest.py:34-78`, `104-138`, `369-404`).
- `SchemaPackRegistry` provides deterministic, atomic collision rejection for
  pack IDs, tables, migrations, vocabulary, repositories, CLI mounts, and bridge
  mounts, then freezes sorted views (`astrid/core/schema_packs/registry.py:53-120`,
  `129-202`, `221-316`).
- The migration runner provides dependency ordering, cycle and missing-dependency
  rejection, exact-byte checksums, read-only incompatibility/drift probing, and
  one transaction per migration (`astrid/core/migrations/runner.py:146-201`,
  `233-322`, `387-457`).
- `open_database` probes before write, preserves read-only non-mutation, applies
  PRAGMAs and pending migrations, and `DatabaseWriter` owns one writer thread
  (`astrid/core/store/database.py:67-98`,
  `astrid/core/store/writer.py:285-328`). `UnitOfWork`, typed repositories,
  events, receipts, and conformance tests are already present.
- The old registry/catalog floor is green: `tests/v10/test_registry.py` plus
  `tests/v10/test_catalog_migrations.py` completed with `105 passed`.

Two material database gaps remain inside this otherwise reusable code:

- A dependency's parsed minimum version is ignored. Ordering checks only that
  `dependency.pack` exists, then traverses the graph; it never compares
  `dependency.version` to the dependency's available migration head
  (`astrid/core/migrations/runner.py:158-176`). The reduced plan explicitly says
  to enforce the minimum or remove the grammar.
- Migration resources are re-derived from the pack ID and a hard-coded package
  layout (`astrid/core/migrations/runner.py:113-138`). They do not carry the
  canonical owner's resolved root/path.

### 3. The four product slices — semantics already implemented

- `timeline`, `shots`, `references`, and `runaway` each have real migration SQL,
  repository code, and a strict `schema-pack.yaml`.
- `timeline`, `shots`, and `references` have the declared CLI/SDK/repository and
  conformance surfaces used by the standard application.
- `references` already owns its three real tables and complete command/event
  vocabulary in `astrid/packs/references/schema-pack.yaml:17-59`; its repository,
  SDK, CLI, lifecycle, media, link, and conformance suites are present. No
  references data-model rewrite is needed.
- `runaway` already owns `runaway_transitions`, `runaway.create`, and
  `RunawayRepository` in `astrid/packs/runaway/schema-pack.yaml:15-35`. It has no
  invented stream/event/CLI/SDK/bridge surface, and none should be added.

The outstanding change is custody: these four directories still have only
`schema-pack.yaml`, not canonical `pack.yaml` v2.

### 4. SDK and operational safety floors — implemented, but from duplicate builders

- `compose_standard_application` accepts an injected frozen registry and otherwise
  builds the old standard registry (`astrid/application.py:287-338`).
- A bound `AstridClient` correctly propagates the exact registry into later invoke
  calls (`astrid/sdk/client.py:199-218`). Preserve this behavior.
- Read helpers can accept or context-bind a registry
  (`astrid/core/kernel/read.py:32-71`).
- Doctor and restore both perform compatibility probing, and backup uses SQLite's
  online backup API and records actual `schema_migrations`
  (`astrid/core/doctor.py:636-680`,
  `astrid/core/backup/operations.py:334-375`, `1253-1296`).
- Existing wheel tests already build/install outside the checkout and verify the
  eight-family CLI plus old migration resources
  (`tests/v10/test_m8_packaging.py:98-188`, `191-271`).

These are behavior floors, not canonical convergence. Doctor, restore, standalone
SDK invocation, rendering reads, and kernel reads independently call the legacy
standard builder. Backup creation reads actual applied rows without first taking
the same expected canonical projection.

## What remains to reach the reduced beta end state

| Reduced acceptance claim | HEAD status | Concrete remaining work |
|---|---|---|
| One v2 manifest grammar | Missing | Add the strict v2 schema/semantic loader; accept only `pack.yaml` with the frozen v2 representation; delete alternate/schema-less/defaulting paths at the hard cut. |
| One complete normalized authority | Partial substrate only | Evolve the pack model into one immutable consumer-facing canonical object containing provenance/root/manifest/resource and optional database declarations; make validation and projections consume it without reopening YAML. |
| Bundled catalog | Missing | Deterministically discover/validate every bundled canonical manifest once, retain provenance, enforce unique IDs/confinement, and expose narrow typed projections. Do not fold dynamic installed lifecycle into it. |
| Four database packs are ordinary packs | Missing | Merge each of the four `schema-pack.yaml` declarations into its v2 `pack.yaml`, preserving SQL bytes and semantics. |
| All bundled manifests are v2 | Missing | Current census is 19 `pack.yaml`, all schema version 1, plus four schema-only pack directories. Delete the empty `builtin` shim pack and deprecated alias shims; convert the remaining 18 capability manifests plus the four data packs, yielding 22 retained packs. |
| Standard composition is derived | Missing | Delete both explicit `STANDARD_SCHEMA_PACKS` tuples and derive the registry from bundled `database.default_enabled` declarations. |
| Database projection reuses current guarantees | Partial | Project canonical declarations into the current collision/migration engine, carry resolved owner roots, and enforce/remove minimum dependency versions. |
| External database packs are rejected | Missing | Current runtime loading does not own a `database` field and can ignore unknown top-level data; add provenance-aware whole-pack rejection before any external SQL/resource use. Leave external capability discovery/lifecycle otherwise unchanged. |
| Operational consumers agree | Missing | Thread one bundled catalog/database projection through application, bridge, standalone SDK, kernel/read helpers, rendering reads, doctor, backup creation, and restore. Remove raw schema-manifest rereads such as `read_manifest_cli_mounts()` (`astrid/core/cli/domain_product.py:154-174`). Keep static typed service/CLI factories. |
| Wheel/resource closure | Partial old proof | Package every v2 manifest and each declared SQL resource, including runaway's SQL. Current explicit package data and wheel expectations name only timeline/shots/references (`pyproject.toml:109-118`; `tests/v10/test_m8_packaging.py:46-60`, `207-220`). |
| No compatibility residue | Missing | Delete all four `schema-pack.yaml`, the separate schema manifest/model/standard builders, v1/flat/alternate manifest forms, fixed lists, shim aliases, and compatibility-anchored tests/docs after consumers move. Retain useful registry/migration algorithms under canonical database projection ownership. |

### Current fixed-composition evidence

There are two duplicate old standard builders:

- `astrid/core/schema_packs/standard.py:27-45`
- `astrid/packs/__init__.py:68-110`

Both hard-code `("timeline", "shots", "references")`. Tests explicitly require
that behavior and require `runaway` to remain outside the standard registry
(`tests/v10/test_registry.py:150-181`). This is why the reduced plan's
`default_enabled` bit matters: deriving a catalog must not silently turn every
database declaration into default composition.

### Existing stale tests that execution must replace

- `tests/v10/test_pack_factoring.py:82-95` claims the repository contains exactly
  three `schema-pack.yaml` files. It already fails because `runaway` is the fourth.
  Focused result: `1 failed`.
- `tests/test_runaway_transitions.py` still reads
  `projects/runaway-piano-colour-demo/deliverables/timing-manifest.json`, which is
  absent. Focused old registry/catalog/runaway result: `110 passed, 3 failed`; the
  three failures are `test_prompts_deterministic_and_sample`,
  `test_roundtrip_timing_manifest_to_kernel`, and `test_old_files_not_deleted`.
  Replace these historical-content assertions with a bounded `tmp_path` fixture;
  do not restore or package the missing demo.
- Old registry and packaging tests assert the fixed tuple, old manifests, and old
  wheel resources. Replace them with final-state assertions rather than carrying
  compatibility expectations.

## Stale or incorrect claims in `.oracle/plan.md`

### A. Direct contradictions of the reduced target

1. **Installed lifecycle redesign is out of scope.** Worktree plan lines 34–39,
   646–916, 1639–1668, 1791–1799, and 2186 specify strict install-record v2,
   immutable revision inventories, activation/rollback/invalidation freezing,
   capture-time admission, Python origin confinement, and pre-use handle checks.
   The reduced plan says existing external installed capabilities may stay on the
   existing path and explicitly defers lifecycle/activation design. Worktree line
   43 says “no lifecycle machinery” while the preceding and following requirements
   define exactly that machinery.

2. **The exact schema-version type is wrong relative to the controlling plan.**
   Worktree lines 26 and 80 require integer `2`; reduced plan lines 113–115 and
   241–245 accept `schema_version: "2"`. Contract work may deliberately revisit
   the type, but the 2,317-line artifact cannot call its integer choice settled
   while claiming to implement that reduced end state.

3. **`database.default_enabled` was dropped.** The reduced example and outcome
   make default composition an explicit opt-in (lines 36–38 and 130–134).
   Worktree lines 345–400 define a database contribution without the field, and
   lines 31, 1212–1283, and 1722–1727 select every bundled database pack and call
   a four-pack standard the expected result. That changes current product behavior
   and removes the reduced plan's composition selector.

4. **The canonical object is over-split.** Reduced lines 221–239 require one
   complete consumer-facing canonical object retaining source kind, root, manifest
   path, provenance, resources, capabilities, and database data. Worktree lines
   405–446 instead make `PackDefinition` deliberately omit root/source/manifest
   and wrap it in `CatalogEntry`/`CatalogProvenance`/handles. Internal value types
   are fine, but consumers still need one complete canonical entry; the split must
   not recreate multiple identity authorities.

### B. Scope expansion that should be removed

5. **Dynamic candidate/snapshot lifetime expansion.** Worktree lines 599–627 and
   861–916 redefine local/extra/environment/installed precedence and impose one
   snapshot lifetime on every CLI/SDK/client/serve/doctor/backup/install operation.
   The reduced beta needs a bundled catalog and may leave external capability
   discovery on its current path. Only the external-DB rejection boundary is
   necessary.

6. **Exhaustive file/Python ownership system.** Worktree lines 918–1209 and
   1670–1704 add `authoring_only`, whole-tree non-Python classification, complete
   Python ownership, source/wheel module-set parity, and mandatory structured docs
   for all 22 packs. The reduced plan asks for declared resource closure sufficient
   to validate/package manifests and migrations, not a repository-wide ownership
   type system. A narrow resource inventory for declared runtime resources is
   enough.

7. **New inspect and expanded doctor product surface.** Worktree lines 1799–1804
   require a new `python3 -m astrid.core.pack.cli inspect` DTO and broad doctor
   audits. The reduced end state requires existing consumers to share projections;
   it does not require a new command or turn doctor into a pack inventory scanner.

8. **Evidence bureaucracy is not product work.** Worktree sections X–XIII and
   WP5–WP6 require one special wheel build, one exact Runaway execution, a custom
   installed harness, fifteen-row schema/digest matrix, plan-digest binding, and
   numerous receipts. The reduced acceptance needs a clean-wheel smoke test,
   focused tests, broad tests, and cumulative review. The exact-run/count/digest
   regime adds scripts and contracts that do not advance the canonical pack
   abstraction.

9. **The estimate reflects the rejected expansion.** Worktree lines 13–19 estimate
   6.2–8.7 engineer-weeks; the reduced plan estimates 4–6. The added 2+ weeks are
   visible in strict installed admission, exhaustive ownership/docs, new inspect,
   and evidence systems and should be removed, not executed.

### C. Claims worth retaining

The large plan is not wholly unusable. Keep these conclusions:

- Delete the empty `builtin` namespace and deprecated alias shims. Current census
  finds 49 `builtin.*` aliases and 59 deprecated alias declarations; the user
  explicitly rejected shims.
- Retain exactly the 22 real product pack directories plus irreducible `_core`
  guidance after deleting `builtin`.
- Convert all four data-bearing packs without changing SQL or product semantics.
- Keep the catalog out of service-location/runtime-factory responsibilities.
- Reject external `database` before reading SQL.
- Preserve existing typed registries, static service/CLI/bridge wiring,
  `DatabaseWriter`, `UnitOfWork`, migration safety, and SDK registry propagation.
- Replace the absent Runaway demo dependency with a deterministic temporary
  fixture; do not restore or package the demo.
- Prove source and wheel manifest/migration closure and then hard-delete the old
  schema-pack and v1 authorities.

## Smallest correct next execution sequence

### 1. Freeze only the reduced v2 contract and bundled catalog seam

- Replace the worktree plan as execution authority with the 513-line reduced
  plan (plus this gap judgment); do not carry forward its installed-admission,
  ownership-ledger, inspect, or evidence work packages.
- Evolve the existing pack model/loader rather than introducing a parallel pack
  system. Produce one immutable consumer-facing `CanonicalPack`/catalog entry.
- Freeze `schema_version`, exact v2 fields, `database.default_enabled`, dependency
  semantics, pack-relative resource confinement, and provenance-derived bundled
  trust.
- Add only three golden forms (capability-only, database-only, combined) plus
  invalid legacy/external-database cases.
- Keep external capability discovery/install records unchanged beyond consuming
  the canonical capability definition where necessary.

Gate: one parse/normalize/validate path; only v2 `pack.yaml`; external `database`
fails; no lifecycle additions.

### 2. Convert bundled manifests mechanically

- Delete `builtin` and all deprecated compatibility aliases.
- Convert the remaining 18 capability `pack.yaml` files to v2.
- Add v2 `pack.yaml` to `timeline`, `shots`, `references`, and `runaway`, merging
  their current database declarations byte-for-byte/semantics-for-semantics.
- Set explicit default composition flags to preserve behavior:
  `timeline=true`, `shots=true`, `references=true`, `runaway=false`.
- Add manifest and owner-relative migration-resolution tests. Do not add docs or
  classify unrelated source files unless a declared runtime resource actually
  needs it.

Gate: 22 bundled product packs load through the one catalog; all four database
packs are ordinary canonical packs; each SQL path is confined to its owner.

### 3. Project canonical database declarations into the existing engine

- Reuse the registry's collision logic and migration runner; remove only the
  schema-pack identity/parsing layer.
- Carry owning canonical pack/root/resource identity on each registered migration
  instead of rebuilding `astrid/packs/<id>`.
- Enforce dependency minimum migration heads (or simplify the frozen grammar).
- Derive the standard registry from `default_enabled` bundled entries and delete
  both fixed tuples/builders.
- Keep `schema_migrations` as the sole applied-state record; add no lock or pack
  revision state.

Gate: fresh three-default-pack DB, existing DB reopen, explicit runaway-extended
DB, read-only pending behavior, checksum/name drift, rollback, collision, and
dependency tests.

### 4. Converge the real consumers

- Construct the bundled catalog/database projection once at the top-level
  application/operation seam and pass its typed projection to application,
  bridge, standalone SDK, client, kernel/read helpers, rendering reads, doctor,
  backup creation, and restore.
- Preserve the current `AstridClient` registry propagation and static typed
  repository/service/CLI/bridge factories.
- Replace `read_manifest_cli_mounts()` raw YAML reads with the catalog projection,
  but do not make mounts dynamic.
- Make backup creation validate against and record the same expected projection;
  make restore probe the same projection without rebuilding it internally.

Gate: application, SDK/read, doctor, backup, and restore compare equal expected
composition and retain existing safety semantics.

### 5. Hard-delete legacy authority, repair stale tests, and prove the wheel

- Delete all four `schema-pack.yaml`, the separate schema manifest/model/standard
  builder, v1/flat/alternate pack loading, duplicate lists, and tests/docs that
  make those forms authoritative. Retain/move useful registry algorithms.
- Replace the already-failing factoring assertion and the three historical
  Runaway-demo tests with final-state/catalog and temporary-fixture tests.
- Generate or verify ordinary package data for every canonical manifest and every
  declared migration, including runaway SQL.
- Run focused pack/database/consumer tests, a clean outside-checkout wheel smoke,
  then the broad suite once. No custom evidence framework is needed.

Gate: no active schema-pack/v1/fixed-list authority remains; source and installed
wheel load all 22 canonical manifests, resolve all declared migrations, preserve
the three-pack default composition, and can explicitly compose runaway.

## Final decision

Proceed, but discard the current `.oracle/plan.md` as an execution plan. The next
code work should begin with the narrow v2 contract/catalog seam, not installed
record v2 or audit tooling. The reusable substrate is already strong enough that
the reduced five-seam hard cut is credible. The critical scope controls are:

1. bundled catalog only;
2. explicit `default_enabled` fixed composition;
3. external DB rejection without external lifecycle redesign;
4. static typed factories retained;
5. no shims, locks, marketplace, exhaustive ownership system, new inspect command,
   or bespoke evidence platform.

