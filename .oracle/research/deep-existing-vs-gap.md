# Deep existing-vs-gap audit: canonical-pack beta

Audit target: current canonical worktree at
`7ac50c12e8e4d90988fee603ffdb9896e5628792` (same product tree as the captured
base). This is a read-only product audit. The current run has changed only
`.oracle` planning/research artifacts; it has not changed `astrid/`, `tests/`,
`docs/`, packaging, or product commits.

## Bottom line

Astrid already has a substantial, tested capability-pack and database substrate.
The canonical-pack beta is not present: there is no v2 canonical object/catalog,
database declarations still live in a second `schema-pack.yaml` authority,
database composition is still a fixed three-pack list, and operational
consumers rebuild that registry independently. The remaining work is a
cross-cutting authority/convergence cutover, not a greenfield rewrite.

## Reusable capability-pack substrate

- `PackDefinition` is an immutable normalized capability manifest value with
  identity, paths, content, agent metadata, status/visibility, aliases,
  permissions, extensions, and taxonomy
  (`astrid/core/pack/definition.py:31-53`).
- `load_pack_manifest()` validates folder/ID agreement and normalizes the
  current manifest, while still defaulting missing identity/version and
  accepting the legacy flat form (`astrid/core/pack/loader.py:110-152,
  193-216`). `discover_packs()` deterministically scans manifests and rejects
  duplicate IDs (`loader.py:84-107`).
- Layered discovery already has a reusable frozen metadata shape and ordering
  across source, local, extra, environment, and installed roots
  (`astrid/core/pack/discovery.py:39-107`). External roots are isolated per
  manifest rather than taking down valid neighbors (`discovery.py:127-200`).
- Typed capability registries, search/inspect, entrypoint guarding, pack
  validation/layout checks, and provenance are present under
  `astrid/core/pack/`.
- Install/trust/revision infrastructure is real and reusable: `InstallRecord`,
  active symlinks, revision directories, staging and per-pack locks, active
  records, install/inactive/remove operations, and rollback are implemented in
  `astrid/core/pack/store.py:45-239,275-414`; trust summary/confirmation lives
  in `install_trust.py`; aliases/forks/overrides have dedicated resolvers and
  stores. These mechanisms currently describe capability packs, not database
  schema admission.
- Inventory at this HEAD: 24 direct `astrid/packs` directories, 19 ordinary
  `pack.yaml` manifests, 64 executor manifests, 12 orchestrator manifests, 10
  element manifests, and 19 `SKILL.md` files (18 product skills plus `_core`).
  All ordinary manifests are v1-era capability manifests; `_core` has no
  manifest.

## Reusable database/migration substrate

- `SchemaPackManifest` is immutable and strictly validates an exact 11-field
  `schema-pack.yaml` contract, including migration descriptors, vocabulary,
  repositories, conformance, and mounts
  (`astrid/core/schema_packs/manifest.py:40-59,114-138,407-421`).
- `SchemaPackRegistry` performs atomic collision checks and freezes deterministic
  projections of packs, tables, migrations, stream/event/command vocabulary,
  repositories, and mounts (`astrid/core/schema_packs/registry.py:129-202`).
- The migration runner already provides pack-relative resource reads, exact-byte
  checksums, dependency/cycle ordering, too-new/name/checksum drift refusal,
  non-mutating probes, and transactional forward application
  (`astrid/core/migrations/runner.py:113-201` plus its applied-state checks).
  `open_database()` probes before writes, never migrates read-only opens, and
  applies pending migrations only for writable opens
  (`astrid/core/store/database.py:67-98`).
- `DatabaseWriter` owns one SQLite connection/thread and rejects unsafe nested
  submission (`astrid/core/store/writer.py:285-348`); repositories, services,
  event/receipt, unit-of-work, conformance, and single-writer tests are already
  established.
- Existing data-bearing features are substantive, not stubs: timeline, shots,
  references, and Runaway each have migrations/repositories or related product
  behavior. There are four SQL migration trees under the four schema-pack
  directories.

## Reusable application/operational surfaces

- Standard application composition acquires the owner lock, opens exactly one
  writer, and wires typed project/timeline/shots/references/tasks/media/runs/
  evidence repositories (`astrid/application.py:287-356`).
- SDK invocation can propagate an explicitly supplied schema registry through
  execution; its default still reconstructs the standard registry
  (`astrid/sdk/invocation.py:850-874`). `schema_registry_context` provides a
  scoped registry for nested reads (`astrid/core/kernel/read.py:46-71`).
- Doctor validates schema versions through a standard registry
  (`astrid/core/doctor.py:636-650`). Backup restore validation does the same
  (`astrid/core/backup/operations.py:1288-1296`), and managed-media reads
  rebuild it too (`astrid/core/rendering/assets.py:138-146`).
- Backup/restore itself is mature: staged validation, online SQLite backup,
  external-media snapshots, journaling, crash recovery, and atomic publication
  are implemented in `astrid/core/backup/operations.py`.
- Focused verification run in this audit:
  `python3 -m pytest -q tests/v10/test_catalog_migrations.py
  tests/v10/test_reference_repository.py tests/sdk/test_references.py
  tests/v10/test_doctor.py tests/v10/test_backup_restore.py
  tests/v10/test_backup_external_portability.py
  tests/v10/test_standard_application.py` → **118 passed in 38.28s**.

## Precise missing canonical-v2 cutover

1. **Canonical model and authority.** Add a strict v2 `pack.yaml` model/parser
   (the named `CanonicalPack`) that parses, normalizes, validates, and retains
   capability plus optional database declarations exactly once. Add the
   immutable bundled catalog/resource inventory and make validation, trust,
   search, capability registries, and database projection consume it. Current
   code has no `CanonicalPack`, `PackCatalog`, or catalog snapshot
   implementation; current loader behavior is intentionally permissive.

2. **Manifest conversion.** Convert the 22 product packs in the beta target
   (the ordinary capability set after removing deprecated `builtin`, plus the
   four data-bearing packs) to canonical v2 manifests. Move timeline, shots,
   references, and Runaway's existing database declarations into their owning
   `pack.yaml`; preserve existing SQL/repository/vocabulary/conformance
   semantics. `_core` needs an explicit system-pack treatment if retained.

3. **Database projection.** Derive the frozen schema/migration registry from
   trusted bundled canonical manifests, resolving migration resources relative
   to each owner pack and enforcing declared dependency semantics. Include
   Runaway by manifest selection rather than by another special case. Remove
   the two fixed `STANDARD_SCHEMA_PACKS = ("timeline", "shots", "references")`
   builders (`astrid/packs/__init__.py:68-110` and
   `astrid/core/schema_packs/standard.py:27-45`) after their useful collision
   and ordering algorithms are projected into the new catalog path.

4. **Consumer convergence.** Rewire application composition, SDK invocation,
   kernel read helpers, doctor, backup/restore, and managed-media reads to use
   the same catalog-derived database projection. Today each can fall back to
   `build_standard_registry()` independently; concrete examples are
   `application.py:315-316`, `doctor.py:636-642`, `backup/operations.py:1288-1292`,
   `sdk/invocation.py:868-874`, and `rendering/assets.py:143-146`.

5. **Packaging/resource closure.** Make source and installed-wheel validation
   prove every v2 manifest, migration, executable/runtime module, skill and
   declared resource is present and owner-confined. Current packaging explicitly
   packages the old three schema manifests/migrations and excludes skills and
   authoring paths (`pyproject.toml:66-125`); it has no canonical resource
   inventory audit. The wheel build remains unverified in this environment
   because Python lacks the `build` module.

6. **Hard deletion and final-state tests.** Delete the four
   `schema-pack.yaml` authorities, the separate `astrid/core/schema_packs/`
   identity/parser and duplicate builders after migration, plus stale tests/docs
   that assert the dual system. Remove fixed-list consumers and update pack
   documentation/skills. Do not infer this from docs: current code and tests
   still directly import `load_schema_pack_manifest`, mention
   `schema-pack.yaml`, and assert the three-pack tuple (for example
   `tests/v10/test_registry.py:163-203`, `tests/v10/test_m8_packaging.py:46-53,
   216-220`, and `tests/test_runaway_transitions.py:16-38`).

## Scope boundary

Existing install/trust/revision, capability discovery, typed repositories,
migration correctness, writer ownership, doctor, backup/restore, and product
behavior should be retained and projected—not rebuilt. The old broad
packification aspiration (moving every generation adapter, experiment, RunPod,
Reigh, and worker implementation out of `core`) is not evidence of canonical-v2
work having landed and is not required to claim the current five-seam beta
cutover. The current base still exposes those as existing product surfaces;
canonicalization should first close the single manifest/catalog/database
authority described above.

