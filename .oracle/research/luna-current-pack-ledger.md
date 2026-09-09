# Current canonical-pack beta ledger

Audit target: `7ac50c12e8e4d90988fee603ffdb9896e5628792` in the canonical-pack
worktree. Compared with the five reduced beta batches in
`/Users/peteromalley/Documents/reigh-workspace/Astrid/.oracle/prep/canonical-pack-beta/plan.md`,
and the in-scope contract/consumer/deletion requirements in `.oracle/plan.md`.
This is read-only product evidence; per-project lock/lifecycle/marketplace and
the installed-revision admission machinery are outside this ledger.

## Executive finding

The current checkout has a mature, tested product/database substrate, but no
canonical v2 cutover. Capability packs are still a separate permissive v1
`pack.yaml` system, while database packs are a second strict
`schema-pack.yaml` system. The main reusable work is the existing immutable
schema-pack registry/migration runner, typed repositories/conformance, and
operational safety. The beta's defining work—one v2 parsed object/catalog and
all consumers projected from it—remains absent.

## Five-batch ledger

### Batch 1 — freeze v2 contract and canonical object: **partial / reusable substrate**

**Fully implemented/reusable**

- `PackDefinition` is immutable and carries identity, paths, capability content,
  aliases, permissions, extensions, and taxonomy (`astrid/core/pack/definition.py:31-53`).
- The capability path has shared YAML/JSON parsing and v1 JSON-schema validation;
  strict field checks and normalized permission/extension handling are covered
  by `tests/packs/test_pack_yaml_schema.py`.
- The database side already has a separate immutable `SchemaPackManifest` and
  strict exact-11-field validation, including migration descriptors, ownership,
  vocabulary, and mounts (`astrid/core/schema_packs/manifest.py:34-59,104-130,369-421`).

**Partial/reusable toward beta**

- `astrid/core/pack/discovery.py` centralizes layered capability discovery, but
  it returns `PackDefinition` values and is not a process-lifetime bundled
  canonical catalog.
- The schema-pack registry already provides deterministic collision checks and
  frozen projections (`astrid/core/schema_packs/registry.py:129-202`), useful
  algorithms to retain rather than replace.

**Absent**

- No v2 pack schema/model/parser, no `CanonicalPack`, no bundled catalog or
  resource inventory, and no one parse/normalize/validate path shared by
  validation, registries, search, and database projection. `rg` finds no
  `CanonicalPack`, `BundledCatalog`, or `CatalogSnapshot` implementation.
- All 19 capability manifests present at this HEAD declare `schema_version: 1`;
  the loader defaults missing identity/version and explicitly keeps legacy flat
  parsing (`astrid/core/pack/loader.py:110-152,193-216`). The v2 hard-cut
  reject rules and external-database rejection therefore do not exist.

### Batch 2 — convert bundled data-bearing packs: **product slice implemented; conversion absent**

**Fully implemented/reusable**

- `timeline`, `shots`, and `references` have migrations, repositories, CLI
  mounts, event/command vocabulary, and declared conformance. Pack-owned
  conformance implementations exist for `shots` and `references`; timeline
  command specs remain in the core conformance kit. The references SDK/repository
  and schema preservation tests pass (`79 passed` in
  `tests/v10/test_catalog_migrations.py`, `tests/v10/test_reference_repository.py`,
  and `tests/sdk/test_references.py`).
- `runaway` has a migration, typed repository, prompt helpers, and real
  kernel-integrated behavior (`astrid/packs/runaway/{repository.py, migrations/0001_initial.sql}`);
  29 transition tests passed, with 26 subtests.

**Partial/reusable toward beta**

- Existing pack directories are nearly the intended owners and their SQL bytes,
  repository semantics, and conformance declarations can be carried into a
  combined manifest without a data-model rewrite.
- The tree already has the intended product count ingredients: 24 direct
  directories including `_core`, 19 `pack.yaml` directories, and four separate
  schema-pack directories. After deleting `builtin`, that is the planned 22
  product-pack set.

**Absent**

- None of `timeline`, `shots`, `references`, or `runaway` has `pack.yaml`; each
  has only `schema-pack.yaml` (for example `astrid/packs/references/schema-pack.yaml:1-13`).
  They are not ordinary canonical bundled packs and are invisible to ordinary
  capability discovery.
- The historical `projects/runaway-piano-colour-demo` timing manifest is absent;
  `tests/test_runaway_transitions.py` has three failures at the fixed path.
  This is expected preservation evidence, not a request to restore it: the prep
  plan explicitly says the historical demo remains absent and a generated
  temporary fixture is the replacement gate. That generated canonical fixture
  is not present in this checkout.

### Batch 3 — database projection and migration catalog: **migration substrate implemented; canonical projection absent**

**Fully implemented/reusable**

- `open_database` probes read-only before writes and applies pending migrations
  transactionally (`astrid/core/store/database.py:67-98`). The runner provides
  dependency ordering/cycle checks, exact-byte checksums, name/too-new drift
  refusal, and per-migration transactions (`astrid/core/migrations/runner.py:1-23,146-201,233-278,387-440`).
- Current catalog tests verify fresh 14+1+2+3 schemas, table ownership,
  topological rows, idempotent reopen, checksums, drift, and nonmutating probes
  (`tests/v10/test_catalog_migrations.py`); all of that selected catalog suite
  passed.

**Partial/reusable toward beta**

- The registry already projects tables, migrations, vocabulary, repositories,
  CLI mounts, and bridge mounts, but its inputs are only schema-pack manifests.
- Migration ordering is dependency-aware, but `topological_migration_order`
  checks only that a dependency pack is registered (`runner.py:158-164`); the
  declared minimum dependency version is not enforced.

**Absent**

- Standard composition is hard-coded to exactly three packs and reparses their
  `schema-pack.yaml` files in both `astrid/packs/__init__.py:68-110` and
  `astrid/core/schema_packs/standard.py:39-45`. `runaway` is not in the default
  database projection.
- Migration resource resolution is ID-based (`runner.py:113-138`) rather than
  carried by canonical owner-relative resource handles. No manifest-derived
  four-pack database projection, executed table-effect ownership audit, or
  canonical `schema_migrations` projection exists.

### Batch 4 — application and operational consumers: **product behavior implemented; convergence absent**

**Fully implemented/reusable**

- Standard application composition preserves one writer, typed repositories and
  services, and explicit registry propagation (`astrid/application.py:287-360`).
- Doctor, backup/restore, read probes, SDK invocation, CLI mounts, and bridge
  behavior are exercised by focused suites: `39 passed` across
  `tests/v10/test_doctor.py`, `test_backup_restore.py`,
  `test_backup_external_portability.py`, and `test_standard_application.py`.
- Long-lived SDK clients preserve an explicitly injected schema registry
  (`astrid/sdk/client.py:199-218`), a useful propagation seam.

**Partial/reusable toward beta**

- `schema_registry_context` can carry one caller-supplied registry through nested
  reads (`astrid/core/kernel/read.py:55-71`), but this is a registry context,
  not the planned immutable catalog snapshot shared by every consumer.
- The existing operational safety and typed service wiring should remain; the
  change needed is authority/source rewiring, not product semantics.

**Absent**

- Doctor reconstructs a fixed standard registry (`astrid/core/doctor.py:636-642`),
  restore validation does the same (`astrid/core/backup/operations.py:1288-1296`),
  and managed media reads also rebuild it (`astrid/core/rendering/assets.py:143-146`).
  Application composition likewise defaults to core + exactly three packs
  (`astrid/application.py:295-316`). These consumers do not agree through one
  canonical catalog/database projection.
- The focused extended-composition test demonstrates the current seam but is
  not green in this environment: `test_long_lived_client_invokes_with_extended_registry`
  fails because the executor cannot import the external
  `banodoco_timeline_schema` package. This is a runtime dependency failure, not
  evidence of canonical-pack implementation.

### Batch 5 — packaging, documentation, and hard deletion: **reusable packaging harness; beta closure absent**

**Fully implemented/reusable**

- Setuptools package-data declarations and an isolated installed-artifact
  harness exist (`pyproject.toml:66-133`; `scripts/reshape/installed_artifact.py`).
- The current packaging contract covers entry points, runtime modules, resource
  inclusion/exclusion, installed help, and migration refusal in
  `tests/v10/test_m8_packaging.py`; its two non-build tests passed.

**Partial/reusable toward beta**

- Package-data patterns already distinguish runtime data from authoring material,
  and the wheel harness can be adapted for declared v2 resources. Current
  patterns, however, explicitly package the three old schema manifests and
  migrations (`pyproject.toml:109-118`) and exclude all `skill/` paths
  (`pyproject.toml:79-84,91-95`), contrary to the beta's required bundled
  documentation closure.

**Absent**

- No v2 source/wheel resource-closure audit, canonical manifest audit, ownership
  audit, documentation coverage gate, or generated evidence matrix is present.
- Hard deletion has not happened: `builtin/pack.yaml` remains deprecated,
  four `schema-pack.yaml` files remain, `astrid/core/schema_packs/` remains, the
  duplicate `STANDARD_SCHEMA_PACKS = ("timeline", "shots", "references")`
  lists remain, and 49 `builtin.*` aliases are still present. Existing tests
  explicitly assert these old forms (for example
  `tests/v10/test_pack_factoring.py:82-95` and
  `tests/v10/test_m8_packaging.py:46-53,216-220`).
- Packaging could not be built in this environment: `tests/v10/test_m8_packaging.py`
  produced four fixture setup errors and one failure because Python reported
  `No module named build`. This leaves clean-wheel validation unverified; it
  does not change the source evidence above.

## Bottom line

Current HEAD is a strong pre-cutover baseline: database correctness,
repositories, conformance, application wiring, doctor, and backup/restore are
real and tested. None of the five batches reaches its canonical beta
checkpoint. Batches 1–3 lack the v2 authority/projection seam; Batch 4 still
rebuilds the fixed registry in consumers; Batch 5 still packages and tests the
legacy dual-manifest system and has not deleted it.
