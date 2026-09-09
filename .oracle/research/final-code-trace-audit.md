# Final code-trace audit (base `7ac50c12`)

Audit scope: current checkout product code, manifests, package rules, tests,
`.oracle/implementation-ledger.md`, and `.oracle/tasklist.md`. No product files
were modified.

## Bottom line

The ledger/tasklist's central conclusion is correct: this worktree is a
pre-cutover baseline. `HEAD` is
`7ac50c12e8e4d90988fee603ffdb9896e5628792`, and both
`git diff --name-only HEAD -- astrid tests docs pyproject.toml scripts` and
product-path status are empty. No canonical-v2 implementation, converted
manifest, catalog, product test, implementation commit, push, or release is
present.

The principal correction is authority accounting: the ledger says there are
two fixed standard-registry authorities, but the source has three fixed
pack-id authorities. In addition to the two `STANDARD_SCHEMA_PACKS` tuples,
`astrid/core/cli/domain_product.py:104` defines `_STANDARD_PACK_DIRS` and
`read_manifest_cli_mounts()` rereads the three `schema-pack.yaml` files. The
cutover must remove/repoint this third authority as well. The tasklist's broad
B4.4/B4.5 wording covers the mount reader, but B3.5's “both” is incomplete.

## Quantitative claims checked

All counts below were recomputed from the current tree:

| Claim | Result | Evidence |
|---|---:|---|
| Direct `astrid/packs` directories | 24 | `find astrid/packs -mindepth 1 -maxdepth 1 -type d` |
| v1 `pack.yaml` manifests | 19 | all parse with `schema_version: 1` |
| schema-only manifests | 4 | `references`, `runaway`, `shots`, `timeline` |
| Target retained product packs | 22 | 18 capability manifests after deleting `builtin` + 4 data packs; `_core` excluded as guidance |
| Executors / orchestrators / elements | 64 / 12 / 10 | manifest-file census; per-pack counts agree with the ledger |
| Element kinds | 3 | `animation`, `effect`, `transition` |
| Generation backends / features / modes | 4 / 29 / 14 | four built-in backend descriptors; feature/mode unions in `model_catalog.taxonomy` |
| Deprecated aliases / `builtin.*` aliases | 59 / 49 | YAML parse of all 19 manifests |
| Direct product-pack skills | 17 of 22 | 19 total `SKILL.md` files includes `_core` and one generation component skill |

The generation wording should be tightened: the four backends are currently
built-in taxonomy/adapter descriptors (`astrid/core/generation/backends/registry.py`),
not four entries discovered from `generation/pack.yaml` (that manifest has no
`extensions` block). The numeric claim is right; “source discovery exposes” is
potentially misleading.

The data-pack claims also match the manifests: timeline owns one table and
five event/command kinds; shots owns two tables, one stream, and four
event/command kinds; references owns three tables, one stream, seven events,
seven commands, `ReferenceRepository`, and the `media references` mount;
runaway owns one table, one command, and no stream/events/CLI mount. The four
schema manifests are still separate from ordinary capability manifests.

## Existing implementation verified at the base

The following are real reusable product behavior, not merely documentation:

- `PackDefinition` is a frozen dataclass carrying identity, root/manifest paths,
  content/agent metadata, aliases, permissions, extensions, and taxonomy.
  Its nested dict fields are not deeply immutable, so B1.2 still needs a
  genuinely immutable canonical object. Discovery has source/local/extra/env/
  installed layers and provenance.
- Typed executor, orchestrator, element, rendering, generation, skill/search,
  and agent-index projections exist. Capability validation, layout/scaffolding,
  entrypoint guards, aliases, forks, overrides, and the pack CLI exist.
- Capability install/update/rollback/uninstall has per-pack locks, revision
  directories, active symlinks, pinned Git SHA support, and trust summaries
  (`astrid/core/pack/install_*.py`, `store.py`). This machinery is inherited,
  not canonicalized by this run.
- The strict immutable `SchemaPackManifest` and frozen collision registry cover
  pack/table/migration/vocabulary/repository/mount collisions. The migration
  runner provides dependency ordering/cycle rejection, checksums, drift and
  too-new refusal, read-only probes, and per-migration transactions. The
  existing runner still resolves non-core migration bytes from the hard-coded
  `astrid/packs/<id>` root (`astrid/core/migrations/runner.py:114-136`), and it
  parses but does not enforce dependency minimum migration heads.
- `DatabaseWriter`, `UnitOfWork`, repositories, events, receipts, hash chains,
  conformance, application composition, SDK registry propagation, doctor, and
  backup/restore behavior are present. The default composition is exactly
  `timeline`, `shots`, `references`; Runaway is intentionally excluded and is
  only available through an explicit extended registry (verified by
  `tests/v10/test_registry.py` and `tests/sdk/test_extended_composition.py`).
- Package data explicitly includes the old three schema manifests/migration
  trees and capability runtime data, while setuptools excludes `skill/` trees
  (`pyproject.toml:79-125`). A clean wheel closure for the canonical resources
  is therefore still missing.

## Consumer and legacy-authority trace

There are two fixed `STANDARD_SCHEMA_PACKS` definitions:

- `astrid/packs/__init__.py:68,99-105`
- `astrid/core/schema_packs/standard.py:27,31-43`

There is also the third fixed `_STANDARD_PACK_DIRS`/manifest reader noted
above. Active consumers independently call a standard builder at:

1. `astrid/application.py:315-316`
2. `astrid/sdk/invocation.py:868-871`
3. `astrid/core/kernel/read.py:50-52`
4. `astrid/core/timeline/_edit_helpers.py:69-71`
5. `astrid/core/doctor.py:637-640`
6. `astrid/core/backup/operations.py:1288-1291`
7. `astrid/core/rendering/assets.py:143-146`

Additionally, `astrid/core/cli/domain_product.py:154-171` directly parses
schema manifests for static CLI mounts. The ledger's prose names only
application/SDK/doctor/restore/media and omits kernel reads and timeline edit
helpers; tasklist B4.3 does name those paths, but the audit/evidence should
use the complete seven-call-site plus one-direct-reader inventory above.

The current loader is demonstrably permissive: `astrid/core/pack/loader.py`
accepts the `PACK_MANIFEST_NAMES` alternatives, defaults identity/status and
other fields, and retains the flat-parser fallback. No
`CanonicalPack`/`PackCatalog`/`BundledCatalog`/`CatalogSnapshot` implementation
exists in `astrid/core/pack`, schema-pack code, product code, or tests. The
`schema_version: 2` hits elsewhere are model-catalog/provenance contracts,
not pack-manifest v2.

## Test and packaging verification

Re-ran the ledger's broadest focused command:

```text
python3 -m pytest -q tests/v10/test_registry.py \
  tests/v10/test_catalog_migrations.py tests/v10/test_standard_application.py \
  tests/v10/test_doctor.py tests/v10/test_backup_restore.py \
  tests/v10/test_reference_repository.py tests/sdk/test_references.py
```

Result: **179 passed in 31.24s**. The seven-file independent subset recorded
in the earlier audit also remains reproducible at **118 passed**. This proves
the inherited substrate only; it is not post-cutover evidence. `python3 -c 'import build'`
fails with `ModuleNotFoundError`, so wheel closure/smoke tests remain unrun for
an environment reason.

## Exact remaining delta and corrections to carry forward

The B1-B5 sequence is directionally complete and correctly marks all product
batches `[ ]`. The implementation delta is:

1. Add one strict immutable v2 pack object and bundled catalog; reject v1,
   flat, `pack.yml`, and `pack.json` forms.
2. Convert 18 capability manifests and merge database declarations into v2
   manifests for timeline, shots, references, and Runaway; delete `builtin`
   and all 59 aliases; add the five missing direct skills and canonical docs/
   `_core` census.
3. Project database declarations through the existing collision/migration
   engine, carry owner-relative migration resources, and either enforce
   dependency minimum heads or remove that accepted grammar. Preserve
   `schema_migrations`, existing SQL/repositories, three-pack default behavior,
   and explicit non-default Runaway composition.
4. Rewire all seven builder consumers plus `domain_product`'s direct mount
   reader to one catalog-derived projection. Specifically amend B3.5 to say
   “remove both `STANDARD_SCHEMA_PACKS` authorities and the separate
   `_STANDARD_PACK_DIRS` mount authority.”
5. Delete the four schema manifests and separate schema-pack authority after
   migration/collision types are moved behind the canonical projection; close
   source/wheel package data for 22 manifests, four migration trees, runtime
   resources, and 22 pack skills/docs; then run focused, wheel, full-suite, and
   final evidence/review gates.

Therefore the ledger's `0/15` final criteria and `0/5` product batches are
supported. The material corrections are the third fixed authority, complete
consumer inventory, precise description of the four generation backends, and
the shallow (rather than deep) immutability of `PackDefinition`. No claim of
canonical-v2 product completion is supported by the current code.
