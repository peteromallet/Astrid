You are the Phase 3 plan reviser for the Astrid Megado run. Work read-only. Do not edit files, mutate state, create branches, or dispatch models.

Produce a COMPLETE replacement plan incorporating every accepted settled-plan Wave 5 correction while staying strictly inside the frozen agent goal and advancing the complete North Star. Preserve all still-valid Wave 1–4 contracts. Supersede Wave 4 pre-use InstalledPackStore state verification with the simpler capture-time admission semantics in the Wave 5 synthesis: a top-level operation snapshot freezes the admitted external revision and later store mutations affect the next operation; immediate pre-use checks cover only captured manifest/resources. Hard-cut install records to strict v2 with no old-record migration/default shim. Require every direct astrid/packs child except _core to be a loaded v2 pack, require docs for all 22 bundled packs, close Python ownership in the audit without treating Python as resources, and bind receipts to ordered selected provenance/migration/resource identities rather than a snapshot fingerprint. Retain separate stability receipts without naming a future receipt file. Bias toward elegance and simplicity; reject all anti-patterns. State whether new exploration or [XHARD] work is required. Return the complete executable replacement plan, not a patch and not STABLE.

## COMPLETE NORTH STAR

# North Star — one canonical Astrid pack

Astrid has one understandable pack concept. Every bundled product extension is
owned by one strict `pack.yaml`; a pack may contribute capabilities, SQLite
schema, agent documentation, or any combination. `timeline`, `shots`,
`references`, and `runaway` are ordinary bundled packs rather than a second
schema-pack species.

Opening a pack directory should reveal one authoritative declaration of its
identity, resources, custom capabilities, database ownership, migrations,
events, commands, CLI surface, and agent guidance. Runtime systems consume
typed projections of that declaration instead of independently rediscovering
or reinterpreting the pack. Every existing bundled customization is either
owned by a canonical pack or explicitly classified as irreducible kernel
behavior; nothing remains unclassified.

## Enduring principles

- One pack identity, manifest grammar, parser/validator, normalized definition,
  and bundled catalog.
- SQLite remains the per-project authority. Migration SQL owns columns,
  constraints, indexes, and transformations; YAML does not duplicate DDL.
- Reuse the strong machinery already present: typed registries, migration
  ordering/checksums/drift/transactions, `DatabaseWriter`, `UnitOfWork`,
  repositories, SDK behavior, and conformance tests.
- Bundled trusted packs may contribute database schema; external packs remain
  capability-only during beta.
- Every pack-relative resource is confined, discoverable, and present in the
  built wheel.
- Every user/agent-facing bundled pack ships structured agent documentation;
  the `_core` skill exposes a generated canonical pack census and routes agents
  to the owning pack documentation.
- With no users to migrate, cut directly to the final form and delete alternate
  authorities instead of maintaining shims.
- Keep beta scope proportionate: unify today's bundled system without
  prebuilding a marketplace or variable project-composition lifecycle.

## Anti-patterns

- Hiding the old schema-pack subsystem inside `pack.yaml` while retaining its
  parser, identity, discovery, or hard-coded standard list.
- Replacing useful typed registries with a giant universal service locator.
- Duplicating SQLite DDL or mutable runtime facts in YAML or skill prose.
- Per-project pack locks, enable/disable/purge state machines, dynamic database
  plugins, or migration ceremony without an observed beta need.
- Allowing external packs to execute SQL.
- Making the irreducible kernel dynamically unloadable for conceptual symmetry.
- Compatibility shims, dual reads, schema-less manifests, or legacy fallbacks.
- Declaring success while any bundled customization, documentation surface,
  operational consumer, or packaged resource bypasses canonical ownership.



## COMPLETE FROZEN GOAL

# Agent goal — canonical pack beta hard cut

Status: **frozen**.

[North Star](./northstar.md)

This run advances the North Star by replacing Astrid's split and partially
duplicated pack authorities with one complete canonical bundled-pack path,
covering all existing bundled custom functionality and its packaged agent
documentation without adding post-beta composition machinery.

## Objective

Implement the direct beta end state in which every bundled Astrid product pack
uses strict `pack.yaml` v2, every existing bundled customization is mapped to a
canonical pack or explicitly justified kernel owner, database-bearing packs
declare an optional `database` contribution, all existing typed systems consume
projections of one complete canonical definition, and every user/agent-facing
pack ships validated agent documentation discoverable from the `_core` skill.

Convert the four current schema packs (`timeline`, `shots`, `references`, and
`runaway`), derive standard database composition from bundled manifests, make
resources pack-relative and wheel-complete, rewire every relevant operational
consumer, expose useful inspection/doctor output, and delete obsolete manifest
forms and alternate authorities. Preserve existing feature semantics.

## Authoritative inputs and immutable source

- [North Star](./northstar.md).
- This frozen agent goal.
- Source ref: `7ac50c12e8e4d90988fee603ffdb9896e5628792`.
- Source branch at custody: `codex/live-ux-pre-phase-b-20260824`.
- Worktree branch: `megado/canonical-pack-beta`.
- [Custody baseline](./custody.md).
- Existing source and tests, except tests intentionally enforcing forms named
  for deletion below.

## Settled decisions

1. Exactly one canonical manifest filename: `pack.yaml`.
2. Schema version 2 is a hard cut. No `pack.yml`, `pack.json`, schema-less/flat
   YAML, or `schema-pack.yaml` compatibility.
3. A pack may contribute capabilities, SQLite schema, agent documentation, or
   a combination.
4. Database contribution is an optional `database` block; detailed DDL remains
   authoritative in migration SQL.
5. Migrations/resources resolve relative to the owning pack root/revision.
6. Parse/normalize/validate once into one complete immutable canonical object.
7. Existing typed registry/database mechanics remain subordinate projections.
8. Every existing bundled customization gets a canonical pack owner or an
   explicit kernel classification recorded in a coverage ledger.
9. Standard beta composition is derived from bundled manifests, not duplicated
   fixed tuples.
10. Existing `schema_migrations` remains the sole applied database-state record.
    No per-project composition lock in beta.
11. Standard writable open may continue applying trusted bundled migrations;
    read-only paths probe compatibility. No enable/disable/purge lifecycle.
12. External packs remain capability-only; external `database` declarations
    fail closed.
13. The irreducible kernel stays code; `_core` is not dynamically unloadable.
14. Static typed application/service/CLI/bridge wiring may remain where dynamic
    factories add no beta value, but ownership and documentation cannot bypass
    the canonical catalog.
15. Every user/agent-facing bundled pack has structured `AGENTS.md` or
    `skill/SKILL.md`; intentional opt-outs require a manifest reason and must be
    limited to non-user-facing internal utility packs.
16. The `_core` skill contains or links a generated canonical pack census.
17. `references` becomes the exemplar combined data/SDK/CLI/documentation pack
    without changing its three-table model or semantics.
18. Application, doctor, backup, restore, inspect, validation, and packaging
    consume the same canonical ownership/resource data.

## In scope

- V2 schema, complete canonical model, single loader/validator, deterministic
  bundled catalog, root confinement, and resource closure.
- Capability-only, database-only, and combined golden fixtures/scaffolds.
- Conversion of every bundled pack manifest and the four schema manifests.
- Database projection into existing collision/migration mechanics.
- Pack-relative migration/resource loading and enforced dependency semantics.
- One standard bundled composition path used by application, doctor, backup,
  restore, SDK/read probes, and package validation.
- Canonical customization coverage ledger and a zero-unclassified-surface gate.
- Pack inspection output in text and JSON for identity, source, capabilities,
  database ownership/head, agent docs, and resource closure.
- Doctor canonical pack census and migration status.
- Structured pack agent documentation, `_core` census/routing, and wheel
  inclusion/validation of declared skills and docs.
- CI gates for legacy authorities, path escapes, missing/undeclared resources,
  missing documentation, and clean-wheel closure.
- Focused documentation and end-to-end examples, with `references` as exemplar.
- Deletion of obsolete schema-pack and legacy manifest paths after cutover.

## Non-goals

- Per-project pack locks or variable project composition.
- Enable/disable/purge/database-aware uninstall lifecycle.
- Third-party database packs or arbitrary external SQL.
- Marketplace, sandbox, signing, dependency solver, remote activation, or UI.
- General dynamic repository/service/CLI/bridge factory framework.
- Moving every global model/LoRA/type/taxonomy or kernel primitive into packs
  unless source evidence shows it is existing pack-owned customization required
  by the zero-unclassified gate.
- Down migrations, data rollback, or compatibility shims.
- Merge to main, deployment, or promotion.

## Authorization

Authorized:

- create and mutate the dedicated worktree/branch above;
- run the full Megado plan/explore/revise/execute/oracle/validation process;
- invoke GPT-5.6 Luna and GPT-5.6 Sol under the declared routing policy;
- edit code, tests, docs, and run artifacts within goal scope;
- commit reviewed checkpoints;
- push the reviewed final branch to `origin` using explicit refspec
  `HEAD:refs/heads/megado/canonical-pack-beta`;
- open the completed worktree.

Not authorized:

- modify, clean, stage, or restore the original dirty checkout;
- merge, rebase onto a moving branch, deploy, promote, publish a release, or
  mutate any other worktree;
- switch pinned models without user approval;
- widen the frozen goal under cover of the North Star or review findings.

## Model policy

- Planner: GPT-5.6 Sol, high reasoning.
- Normal explorer/executor/sense-check work: **GPT-5.6 Luna**, user-selected.
- Oracle and exceptional `[XHARD]` work: **GPT-5.6 Sol**, user-selected.
- Automatic switching: not authorized.

Normal is presumed. Cross-cutting size or importance is not `[XHARD]` evidence.
Every proposed `[XHARD]` task must satisfy the skill's full exceptional test.

## Exact done criteria

1. Every bundled product pack loads from one v2 `pack.yaml` into the complete
   canonical object; no shipped `schema-pack.yaml` remains.
2. No active consumer independently reparses or reconstructs canonical pack
   identity; typed capability/database projections share the same catalog.
3. A reviewed coverage ledger maps every existing bundled custom surface to a
   canonical pack/projection or justified kernel owner, with none unclassified.
4. Standard database composition derives from bundled manifests with no
   duplicate `("timeline", "shots", "references")` authority.
5. `timeline`, `shots`, `references`, and `runaway` preserve migration,
   repository, event, command, CLI, SDK, and conformance behavior.
6. Migrations resolve from owner roots and preserve collision/order/checksum/
   drift/transaction guarantees; dependency declarations are enforced.
7. Application, SDK/read probes, doctor, backup, restore, inspect, and package
   validation agree on canonical ownership and expected composition.
8. Every user/agent-facing bundled pack has valid packaged agent docs; every
   opt-out is explicit and justified; `_core` exposes the canonical census.
9. Pack inspection and doctor expose useful canonical pack/database/resource/
   documentation state in stable text and JSON where applicable.
10. A clean wheel contains and can load every declared bundled resource,
    migration, skill, and agent document.
11. Legacy manifest/schema-pack parsers, standard builders, duplicate authority,
    and compatibility tests/docs are deleted or clearly historical/non-active.
12. External capability-only packs still work; external `database` fails closed.
13. Golden capability-only/database-only/combined examples validate.
14. Focused suites and full authoritative test suite pass, or any unrelated
    baseline failure is proven with reproducible before/after evidence.
15. Final evidence matrix maps every criterion to commands, artifacts, results,
    and independent reviewer disposition; final oracle review passes.

## Validation contract

The stable plan must discover exact project commands and may refine this list,
but final validation includes:

```bash
python3 -m pytest tests/packs tests/v10/test_catalog_migrations.py \
  tests/v10/test_m8_packaging.py tests/v10/test_pack_factoring.py \
  tests/v10/test_reference_repository.py tests/sdk/test_references.py \
  tests/sdk/test_extended_composition.py
python3 -m astrid doctor
python3 -m build
```

Also required: fresh and existing SQLite scenarios; checksum drift rejection;
complete `references` round trip; external capability success/database failure;
clean-wheel load/resource audit; agent-doc/census audit; pack inspect text/JSON;
and zero-legacy/zero-unclassified checks. One authoritative owner runs the full
suite and each expensive validation once.

## Stop and sync policy

- Stop for user reconciliation if the source ref, model policy, North Star,
  scope, or authorization must change.
- Treat implementation blockers as owned work until genuinely exhausted.
- Commit only paths reviewed at each checkpoint.
- Push only after the final evidence matrix and oracle gate pass.
- Never merge, deploy, or promote.



## COMPLETE CURRENT PLAN

# Phase 3 replacement plan — canonical pack beta hard cut

Status: **complete replacement issued; not STABLE**.

This document records the replacement plan’s issuance state only. Megado’s current phase remains owned by `.oracle/status.md`; exact Sol stability, if later granted, is recorded separately in a new immutable stability receipt bound to this plan’s digest. Plan content must not copy mutable orchestration state or retroactively claim stability.

This plan incorporates every accepted Wave 1–4 correction. Wave 4 adds only:

1. An immediate, fail-closed `InstalledPackStore` admission-state verification before installed capability execution, keyed by the snapshot’s captured revision and permission receipt.
2. A deterministic generated temporary-project Runaway round-trip fixture and final receipt.

It introduces no cache invalidation subsystem, rediscovery, retry, lock, trust service, historical demo restoration, or packaged demo asset.

## Determination

- Estimated effort: **5.9–8.2 engineer-weeks**, including cumulative review and rework.
- Huge run: **yes**.
- Difficulty: **5/5**.
- New exploration or research: **none required**.
- New `[XHARD]` implementation work: **none required**.
- Open planning questions: **none**.
- Execution order: immutable baseline → executable v2 contract/catalog → bundled conversion and resource closure → database hard cut → operational convergence → legacy deletion and packaging preparation → one-build validation and evidence closure.
- Runaway’s missing historical demo is neither restored nor packaged. Its preservation gate uses the generated temporary-project fixture defined in §VII.1.

## I. Mandate and boundaries

Implement one strict canonical pack system:

- Every retained bundled product pack is declared by exactly one `pack.yaml` with integer `schema_version: 2`.
- Delete the empty `builtin` product pack, leaving 22 retained product packs plus irreducible `_core` guidance.
- Convert `timeline`, `shots`, `references`, and `runaway` into ordinary packs with optional `database` contributions.
- Preserve typed registries, migration safety, repositories, `DatabaseWriter`, `UnitOfWork`, static application/service/CLI/bridge factories, SDK behavior, the eight-family gateway, and conformance semantics.
- Select standard database composition algorithmically from every trusted bundled catalog entry with `database`; the expected four-pack result is a fixture, never a runtime list.
- Derive bundled trust solely from loader provenance.
- Keep external packs capability-only. Reject an external manifest containing `database` as a whole before resolving its resources or reading SQL.
- Assign every bundled customization to a canonical pack or explicitly justified kernel owner.
- Package structured documentation for every user/agent-facing bundled pack.
- Add no per-project composition state, dependency solver, dynamic database plugin system, marketplace, lifecycle machinery, universal service locator, custom packaging backend, global snapshot fingerprint, cache invalidator, or recursive bundled rescan.
- Do not restore, reconstruct from custody, or package the missing `projects/runaway-piano-colour-demo` material. Generate the bounded Runaway test project only inside the test’s temporary root.

The North Star guides implementation but cannot widen the frozen goal.

# II. Exact v2 manifest contract

WP1 lands this contract as JSON Schema, immutable Python types, golden fixtures, and invalid fixtures before bundled conversion.

## 1. Lexical types

| Type | Exact rule |
|---|---|
| `PackId` | `^[a-z][a-z0-9_]*$` |
| `ReleaseVersion` | `^(0\|[1-9][0-9]*)\.(0\|[1-9][0-9]*)\.(0\|[1-9][0-9]*)$` |
| `LowerIdent` | `^[a-z][a-z0-9_]*$` |
| `QualifiedId` | `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` |
| `DottedVocabulary` | `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$` |
| `RepositoryId` | `^[A-Za-z_][A-Za-z0-9_]*$` |
| `MigrationName` | `^[a-z0-9][a-z0-9_-]*$` |
| `Keyword` | `^[a-z0-9][a-z0-9_-]*$` |
| `PythonModule` | `^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$` |
| `PythonClass` | `^[A-Za-z_][A-Za-z0-9_]*$` |
| `RelativePath` | Non-empty POSIX path; not absolute; no backslash, NUL, empty segment, `.` or `..`; every segment matches `[A-Za-z0-9._-]+` |
| `RelativeFile` | `RelativePath` resolving to one regular non-symlink file in environments where that resource class is admitted |
| `RelativeDir` | `RelativePath` resolving to one non-symlink directory in environments where that resource class is admitted |
| `NonBlankText` | String whose outer-trimmed value is non-empty |
| `EnvironmentName` | `^[A-Z][A-Z0-9_]*$` |

The executable schema uses ordinary regex alternation. YAML booleans never satisfy integer fields. Null is never accepted. Optional means absent.

## 2. Top-level fields

Every object uses `additionalProperties: false`, except the two explicitly scoped frozen-JSON maps.

| Field | Required | Type/default | Semantics |
|---|---:|---|---|
| `schema_version` | yes | integer exactly `2` | No numeric string, float, or boolean |
| `id` | yes | `PackId` | Must equal the logical owner-directory name supplied by discovery |
| `name` | yes | `NonBlankText` | Display name |
| `version` | yes | `ReleaseVersion` | Pack release only |
| `description` | no | string, default `""` | Descriptive only |
| `status` | no | `active\|experimental\|deprecated`, default `active` | `stub` is deleted |
| `visibility` | no | `visible\|hidden`, default `visible` | Discovery display behavior |
| `domain` | no | `general\|development\|editorial\|generation\|infrastructure\|integration\|media\|system`, default `general` | Descriptive taxonomy |
| `stability` | no | `stable\|experimental\|deprecated`, default `stable` | Descriptive taxonomy |
| `support` | no | `project\|core\|community`, default `project` | Descriptive taxonomy |
| `keywords` | no | unique `Keyword[]`, default `[]` | Search terms |
| `capabilities` | no | unique `LowerIdent[]`, default `[]` | Search/explanation tags only |
| `permissions` | no | `Permission[]`, default `[]` | Existing disclosure/admission mechanism |
| `content` | no | `ContentRoots`, default `{}` | Typed content roots |
| `extensions` | no | `Extensions`, default `{}` | Typed extension declarations |
| `aliases` | no | `Alias[]`, default `[]` | Live aliases only |
| `agent` | no | `AgentRouting`, default empty values | Descriptive routing |
| `documentation` | no | tagged `Documentation` | Required for bundled admission unless an accepted internal opt-out exists |
| `secrets` | no | `Secret[]`, default `[]` | Install/trust disclosure |
| `dependencies` | no | `RuntimeDependencies`, default empty lists | Runtime disclosure, not pack solving |
| `astrid_version` | no | `ReleaseVersion` | Minimum compatible Astrid release metadata |
| `database` | no | `DatabaseContribution` | Trusted bundled SQLite contribution |
| `resources` | no | `SupplementalResource[]`, default `[]` | Assets not reached through another declaration |
| `authoring_only` | no | `AuthoringExclusion[]`, default `[]` | Source-only, non-wheel classifications |

At least one of `content`, `extensions`, `documentation`, `database`, or `resources` must contribute a non-empty value.

Prohibit the v1 fields `origin`, `install_tier`, `pack_type`, `metadata`, and `docs`.

## 3. Nested shapes

### `content`

Each key is an optional `RelativeDir`:

```yaml
content:
  executors: executors
  orchestrators: orchestrators
  elements: elements
  schemas: schemas
  examples: examples
  docs: docs
```

There is no fallback tree scan. Executor, orchestrator, and element roots use existing typed component loaders. Schema, example, and documentation roots recursively classify their contents.

### `permissions`

```yaml
permissions:
  - id: subprocess
    reason: Runs ffmpeg.
    access: Optional access description.
    services: [service_name]
```

- Exact keys: `id`, `reason`, optional `access`, optional `services`.
- `id` is one of `project_files`, `network`, `subprocess`, `environment`, `accelerator`, or `external_services`.
- `reason` is required `NonBlankText`.
- `access`, when present, is `NonBlankText`.
- Services are trimmed, duplicate-free `NonBlankText`.
- Duplicate permission IDs reject.

### `aliases`

```yaml
aliases:
  - kind: executor
    alias: rendering.render_video
    canonical_id: rendering.render
```

- Exact keys: `kind`, `alias`, `canonical_id`.
- `kind` is `executor`, `orchestrator`, `renderer`, `planner`, or `finalizer`.
- Both IDs are distinct `QualifiedId` values whose pack prefix equals the declaring pack ID.
- Duplicate `(kind, alias)` rejects.
- `deprecated` and `deprecation_message` are prohibited.
- Delete all deprecated aliases, including the 49 `builtin.*` aliases and every remaining `external.*` or legacy alias.

V2 aliases cannot act as compatibility shims.

### `agent`

```yaml
agent:
  purpose: Optional prose.
  do_not_use_for: Optional prose.
  normal_entrypoints: [trimmed routing string]
  required_context: [owner-relative.md]
```

Only these keys exist. Optional prose and routing entries are `NonBlankText`. `required_context` values are `RelativeFile` resources. Only `normal_entrypoints` preserves declared order.

### `documentation`

Exactly one tagged shape:

```yaml
documentation:
  kind: skill
  path: skill/SKILL.md
```

```yaml
documentation:
  kind: agents
  path: AGENTS.md
```

```yaml
documentation:
  kind: none
  reason: Non-user-facing internal utility pack.
```

Rules:

- `skill` requires exactly `skill/SKILL.md`.
- `agents` requires exactly `AGENTS.md`.
- `none` permits only `kind` and a nonblank `reason`.
- Bundled admission rejects `none` unless the coverage ledger classifies the pack as a non-user-facing internal utility.
- All 22 retained product packs use `skill` or `agents`; there are no product-pack opt-outs.

### `secrets`

```yaml
secrets:
  - name: FAL_KEY
    required: true
    description: Optional prose.
```

Exact keys are `name`, optional boolean `required` defaulting to `false`, and optional `description`. Names are unique `EnvironmentName` values.

### `dependencies`

```yaml
dependencies:
  python: ["package>=1"]
  npm: ["package@1"]
  system: ["ffmpeg"]
```

Only `python`, `npm`, and `system` exist. Each is a duplicate-free list of trimmed `NonBlankText`. These are disclosures and do not participate in dependency solving.

### `resources`

```yaml
resources:
  - path: server/blender-render-api.service
    kind: service
```

Exact keys are `path` and `kind`. `kind` is:

- `runtime`
- `schema`
- `template`
- `documentation`
- `service`
- `data`

A path may name a file or directory. Directory expansion is recursive and lexical. A physical file may be reached by only one typed or supplemental declaration.

### `authoring_only`

```yaml
authoring_only:
  - path: executors/generate_image/golden
    kind: golden
    reason: Provider demonstration inputs; not required at runtime.
```

Exact keys are `path`, `kind`, and `reason`. `kind` is:

- `test`
- `golden`
- `development_fixture`
- `authoring_document`
- `build_output`
- `placeholder`

Normalization records immutable owner-relative declarations without requiring their presence.

Audit semantics:

- Source audit requires every declared path to exist, remain realpath-confined, contain no symlink, avoid declared-resource overlap, and have a nonblank reason.
- Wheel audit requires every declared path to be absent.
- Normal installed-wheel catalog loading does not resolve absent authoring-only paths.
- Authoring-only entries never enter `CatalogEntry.resources`.
- The normalized manifest definition, including authoring-only declarations, must be identical between source and wheel.
- Known runtime assets cannot be authoring-only.
- This is one grammar with environment-specific audits, not a second parser.

### `extensions`

All extension objects are strict. Optional lists and maps default empty. Optional labels and descriptions are `NonBlankText`.

```yaml
extensions:
  generation:
    backends:
      - id: backend_id
        label: Optional label
        module: python.module
        class: ClassName
        init_kwargs: {}
    features:
      - id: feature_id
        label: Optional label
        description: Optional description
    modes:
      - id: mode_id
        label: Optional label
        description: Optional description

  elements:
    kinds:
      - id: effects
        singular: Optional singular
        plural: Optional plural
        label: Optional label
        description: Optional description

  timeline:
    kinds:
      - catalog: transition
        id: cross_fade
        aliases: []
        default: false

  rendering:
    renderers: [backends/remotion/renderer.yaml]
    planners: [planners/layer_stack/planner.yaml]
    finalizers: [finalizers/ffmpeg/finalizer.yaml]

  schemas: {}

  artifact_types:
    types:
      - id: artifact_id
        aliases: []
        description: Optional description
```

Rules:

- Backend `id` is `LowerIdent`, `module` is `PythonModule`, `class` is `PythonClass`, and `init_kwargs` is frozen JSON.
- Feature, mode, element-kind, timeline-kind, and artifact IDs are `LowerIdent`.
- Timeline `catalog` is `transition`, `clip`, or `track`; aliases are unique `LowerIdent`; `default` is boolean.
- Rendering entries are unique `RelativeFile` resources and pass existing typed renderer/planner/finalizer validation.
- `extensions.schemas` is the second and final arbitrary frozen-JSON location.
- Artifact aliases are unique `LowerIdent`.
- Duplicate IDs within a family reject.
- Existing registry collision checks remain authoritative across packs.

### `database`

```yaml
database:
  depends_on:
    - pack: core
      min_migration: 1
  migrations:
    - version: 1
      name: initial
      path: migrations/0001_initial.sql
      tables: [timelines]
  stream_types: [timeline.timeline]
  event_kinds: [timeline.created]
  command_kinds: [timeline.create]
  repositories: [TimelineRepository]
  conformance: [replay]
  cli_mounts:
    timelines: timelines
  bridge_mounts: [timelines]
```

All nine fields are required, even when empty:

| Field | Type |
|---|---|
| `depends_on` | Unique `{pack: PackId, min_migration: positive integer}[]` |
| `migrations` | Non-empty `Migration[]` |
| `stream_types` | Unique `DottedVocabulary[]` |
| `event_kinds` | Unique `DottedVocabulary[]` |
| `command_kinds` | Unique `DottedVocabulary[]` |
| `repositories` | Unique `RepositoryId[]` |
| `conformance` | Unique `LowerIdent[]` |
| `cli_mounts` | Map from `LowerIdent` to one or more single-space-separated `LowerIdent` tokens |
| `bridge_mounts` | Unique `LowerIdent[]` |

Each migration contains exactly:

- Positive integer `version`, unique within the pack.
- Unique `MigrationName` `name`.
- Unique `RelativeFile` `path` ending in `.sql`.
- Non-empty unique `LowerIdent[]` `tables`.

Migration descriptors must appear in strictly increasing version order. A table has one owning pack globally. The migration first creating a table records ownership; later owner-pack migrations may alter it without reclaiming it. The four converted beta packs retain their current single initial migrations and SQL bytes.

YAML never contains columns, indexes, constraints, transformations, checksums, applied state, or a mutable head.

## 4. Normalization and immutable model

One parse produces a manifest-derived `PackDefinition` containing no root, source, trust, install state, manifest path, or raw mapping.

Normalization:

- Strip outer whitespace from prose and disclosure strings.
- Require identifiers in canonical case; never lowercase them silently.
- Convert paths to canonical POSIX-relative strings.
- Preserve declared order only for `agent.normal_entrypoints` and migrations.
- Require increasing migration order.
- Reject duplicates and lexically normalize set-like lists.
- Sort mapping keys.
- Recursively freeze arbitrary JSON only in `generation.backends[].init_kwargs` and `extensions.schemas`.
- Make definitions, nested declarations, catalog entries, provenance, resource handles, database projections, and snapshots frozen slot-based values.
- Serialize only normalized manifest data; roots and trust are never manifest fields.

```text
CatalogEntry
├── definition: PackDefinition
├── provenance: CatalogProvenance
├── manifest: ResourceHandle
├── resources: tuple[ResourceHandle, ...]
└── authoring_exclusions: tuple[AuthoringExclusion, ...]
```

Resource handles record owner-relative path, resolved root, file kind, size, and SHA-256. Authoring exclusions remain declarations rather than resource handles.

## 5. Required fixtures

Golden fixtures:

1. Capability-only with executor content, permission, documentation, and no database.
2. Database-only with complete database fields and documentation.
3. Combined references-style content/database/SDK/CLI/documentation declaration.

Invalid fixtures cover:

- Missing, string, float, boolean, or non-2 schema version.
- Alternate manifest filenames, schema-less YAML, flat parser input, arbitrary manifest paths, and `schema-pack.yaml`.
- Owner-directory/ID mismatch and invalid release versions.
- Every unknown top-level and nested field class.
- Every prohibited v1 field.
- Null optional values.
- Duplicate set-like values.
- Alias ownership violations and deprecated alias fields.
- Malformed permissions and documentation unions.
- Absolute, backslash, empty, traversal, symlink, missing, wrong-kind, or duplicate runtime paths.
- Supplemental/typed duplication.
- Source authoring-resource overlap or missing authoring path.
- Authoring-only paths present in a wheel.
- External `database`.
- Missing dependency, capability-only dependency, invalid minimum head, self-dependency, cycle, and duplicate dependency.
- Unordered/duplicate migrations, duplicate table ownership, and non-SQL paths.
- Provenance spoofing.
- Undeclared bundled non-Python files.
- Wheel-only/source-only runtime resources.
- Legacy-only and canonical-plus-legacy bundled directories.

# III. Catalog construction, provenance, admission, and lifetime

## 1. Bundled catalog discovery

Build one immutable `BundledCatalog` from the source or installed `astrid/packs` package root.

For every direct child directory, in lexical order:

1. Treat `_core` as the single explicit non-pack kernel guidance directory.
2. Inspect the child root for the exact basenames:
   - `pack.yaml`
   - `pack.yml`
   - `pack.json`
   - `schema-pack.yaml`
3. If any legacy basename is present, reject catalog construction, whether or not `pack.yaml` also exists.
4. If `pack.yaml` is absent and no legacy basename exists, classify the child as a non-pack directory and do not parse it. The coverage and exact-path gates separately prevent a bundled product extension from disappearing through this rule.
5. If `pack.yaml` exists, parse it once, enforce owner-directory/ID equality, normalize it, resolve admitted runtime resources, and construct its immutable entry.
6. Reject duplicate bundled IDs.
7. Cache this bundled catalog once for the process/package-root lifetime.

There is no sequencing path in which `pack.yml`, `pack.json`, or `schema-pack.yaml` can be ignored as an ordinary non-pack directory.

The bundled cache contains only declarations and resource handles. It contains no connection, repository, CLI parser, bridge, capability instance, service, or application object.

## 2. Root-independent provenance identity

Every parsed candidate receives an exact root-independent `provenance_identity`:

```text
SHA-256(
  UTF-8 canonical JSON {
    "schema": "astrid.pack_provenance.v1",
    "definition": <normalized PackDefinition>,
    "declared_paths": [
      {"path": <owner-relative POSIX path>, "role": <typed role>}
    ]
  }
)
```

Canonical JSON uses sorted keys, no insignificant whitespace, UTF-8, JSON booleans/null rules, and arrays already normalized by the manifest contract.

`declared_paths` includes every path directly declared by `content`, rendering extensions, database migrations, documentation, `agent.required_context`, supplemental resources, and authoring-only declarations. It does not contain absolute roots, checkout paths, installation paths, discovery order, provenance class, rejection diagnostics, or mutable installation state.

This identity is used as follows:

- Candidate correlation key: `<pack_id>@<provenance_identity>`.
- Source/wheel comparison requires equal identity plus the independent runtime-resource receipt comparison.
- Duplicate handling compares identity and, after resource resolution, exact resource receipts.
- Diagnostics use the same correlation key.
- External-database rejection can compute the identity after manifest normalization and before reading SQL or resolving resources.

Runtime-resource bytes are represented separately by sorted resource receipts. Two candidates with equal identity but differing resource receipts are not identical duplicates.

`CatalogProvenance` contains:

- Provenance class.
- `provenance_identity`.
- Optional diagnostic-only root/revision details.
- Installed admission disposition where applicable.

Manifest fields can never set or override provenance.

## 3. Dynamic candidate capture and precedence

Each top-level operation captures dynamic candidates once from:

1. Project-local packs.
2. Explicit extra roots in caller order.
3. `ASTRID_PACKS_PATH` roots in environment order.
4. Installed active revisions sorted by pack ID.

Within a root, sort candidates by pack ID and canonical manifest path.

Precedence is:

```text
bundled > local > explicit-extra > environment > installed
```

Duplicate policy:

- Bundled IDs are reserved and always win.
- Candidates with the same pack ID, provenance identity, and exact resource receipt deduplicate.
- Candidates with the same ID but different identity or resource receipt are losers recorded as `duplicate_id`, including winner and loser provenance.
- Any losing candidate contributes nothing.
- Invalid external discovery may be recorded while discovery continues, preserving current fault isolation.
- Direct validation or installation of a rejected candidate is a hard error.

Read-only discovery never creates `astrid/packs/local`; only an explicit create or fork operation may do so.

## 4. External database fail-closed boundary

After structural normalization and provenance assignment, any non-bundled candidate containing `database` is rejected as `external_database_forbidden`.

This happens before:

- Resource resolution.
- SQL reads.
- Migration projection.
- Capability or alias projection.
- Permission-based execution admission.
- Installation publication.

The entire candidate rejects; the database block is never silently stripped.

Tests cover local, explicit-extra, environment, Git-installed, and installed-revision candidates.

## 5. One external admission projection

`InstalledPackStore` remains the typed owner for installed revision state and is extended narrowly to emit the installed candidate’s immutable admission disposition and verify its captured admission binding at use time. The catalog does not create a separate trust service.

```text
ExternalAdmissionDisposition
├── inspectable: bool
├── executable: bool
├── reason_codes: tuple[str, ...]
├── active_revision_identity: optional str
├── validated_provenance_identity: optional str
└── accepted_permissions: frozen normalized permission receipt
```

For an installed entry, the captured admission key is exactly:

```text
(
  pack_id,
  active_revision_identity,
  validated_provenance_identity,
  accepted_permissions
)
```

`active_revision_identity` is the revision selected by `InstalledPackStore` when the operation snapshot is built. `accepted_permissions` is the exact normalized permission receipt accepted for that validated revision, including its existing store-owned receipt identity/version when one exists. These are captured facts, not mutable manifest fields.

Source policy:

| Source | Inspect | Capability execution | Database |
|---|---:|---:|---:|
| bundled | yes | yes | yes |
| local | yes | yes | no |
| explicit extra | yes | yes | no |
| environment | yes | no | no |
| installed | yes | only through the admission predicate and pre-use store verification below | no |

An installed candidate is initially executable only if all are true:

1. It is the active revision selected by `InstalledPackStore`.
2. The active revision’s validated provenance identity equals the captured candidate identity.
3. The current normalized permission disclosures are fully covered by the permission receipt accepted for that validated revision.
4. No permission is missing, newly added, or disclosure-mismatched.
5. The candidate has no `database` contribution.
6. The revision is in its existing valid/active state.

An installed pack with no declared permissions satisfies the permission predicate with an empty receipt. Missing or mismatched evidence produces inspect-only disposition with deterministic reason codes; it never falls back to executable.

The operation snapshot stores this observable disposition and its exact captured admission key. Executor, orchestrator, rendering, generation, SDK, and every other external capability consumer use that projection. They do not reparse manifests or implement another trust policy.

### Immediate installed pre-use admission-state verification

Immediately before each installed capability execution, after selection from the operation snapshot and before invoking any pack code, the execution coordinator calls the existing `InstalledPackStore` admission owner with the captured key. The store performs one narrow state read and verifies:

1. The captured revision is still the active revision for that pack.
2. That same revision remains valid and active.
3. Its store-recorded validated provenance identity still equals both the captured validated identity and the captured candidate’s provenance identity.
4. Its current accepted permission receipt is still the exact captured receipt.
5. That receipt still fully covers the immutable permission declaration in the captured candidate.
6. No revocation, invalidation, or admission-state replacement has occurred.

The check is keyed by the captured revision and permission receipt. It does not select another revision or reconstruct the candidate.

A changed disposition fails closed with deterministic `installed_admission_changed` diagnostics and specific reason codes such as inactive revision, invalid revision, active revision changed, provenance changed, permission receipt changed, permission revoked, or permission mismatch. The attempted capability does not execute and does not silently degrade into a different candidate. The snapshot remains usable for inspection.

A newly activated or newly admitted revision becomes visible only to a later top-level operation and its newly captured snapshot.

This verification adds:

- No candidate rediscovery.
- No manifest reparsing.
- No resource-tree rescan.
- No retry.
- No snapshot replacement.
- No per-project or per-operation lock.
- No new trust or admission service.
- No capability-specific policy.
- No general installed-state freshness framework.

Tests cover mutation between snapshot capture and execution: active-revision switch, invalidation, provenance replacement, receipt replacement, permission revocation/mismatch, unchanged success, and later-operation visibility of a newly activated revision.

## 6. Snapshot construction

```text
CatalogSnapshot
├── bundled_catalog
├── entries_by_id
├── ordered_entries
├── rejected_candidates
└── construction_context
```

There is deliberately:

- No `snapshot_fingerprint`.
- No hashing of rejected diagnostics.
- No global layer-order hash.
- No retry-on-change system.
- No general snapshot stale-handle scan.

`construction_context` is diagnostic-only and may retain local roots/order. It is excluded from semantic source/wheel comparison.

## 7. Lifetime and freshness contract

One snapshot governs:

- One CLI invocation.
- One standalone `sdk.discover`, `get_capability`, or `invoke` call.
- One `AstridClient.open()` lifetime.
- One standard application lifetime.
- One serve lifetime.
- One doctor run.
- One inspect command.
- One backup create or restore validation.
- One install validation/admission.
- One source or package audit.

Consumers cannot rescan or reconstruct a snapshot internally. Convenience APIs create one only at a top-level boundary. Registries accept the snapshot or a narrow typed projection.

Bundled lifetime:

- A bundled catalog is immutable for its process/package-root lifetime.
- Production performs no recursive rescan, cache invalidation, global fingerprint comparison, or broad bundled stale-handle verification.
- Changing bundled files in a source checkout or installed environment requires a new process/catalog lifetime.
- Tests that mutate fixtures explicitly end the old lifetime and construct a new catalog through the narrow test factory/cache-clear seam; this is not a production invalidation subsystem.
- Migration checksum verification remains part of the existing database safety contract, not catalog freshness machinery.

Dynamic external lifetime:

- Candidates are captured once per top-level operation.
- External manifest and resource handles retain their captured size/digest receipts.
- Immediately before a security-sensitive external use:
  - capability execution verifies the candidate manifest and resource handles consumed by the selected capability projection;
  - installed capability execution additionally performs the §III.5 `InstalledPackStore` admission-state verification against the captured revision and permission receipt;
  - installation admission verifies the manifest and all admitted resource handles before publication;
  - direct external resource validation verifies the handles it consumes.
- A manifest, resource, or installed-admission mismatch fails closed.
- The operation does not retry, rediscover, update the snapshot, select another revision, or admit a replacement candidate.
- Inspection-only operations that do not consume external executable resources do not perform broad reverification.

Filesystem changes become visible only in a later operation for dynamic external layers or a new bundled lifetime for bundled content. Installed admission-state changes can block use of a captured candidate immediately, but a replacement candidate becomes visible only in a later operation.

# IV. Bounded bundled-resource classification

## 1. Exact inventory exclusions

Walk each bundled source pack deterministically without following symlinks. Reject every symlink before applying any file classification or exclusion.

There is no generic “cache/build metadata” exclusion and no skipped directory subtree.

Python source is handled explicitly:

- Regular files ending exactly in `.py` are classified as Python source, excluded from package-data equality, and included in the targeted runtime-use audit.
- Other Python/runtime artifacts are not covered by this rule.

The only audit-noise allowlist is:

1. Any regular file whose exact basename is `.DS_Store`.
2. Any regular file whose owner-relative path matches exactly:

```regex
(?:^|/)__pycache__/[^/]+\.py[co]$
```

Matching is case-sensitive against canonical POSIX-relative paths.

Rules:

- No directory is skipped wholesale.
- A non-bytecode file under `__pycache__` is inventoried normally.
- `.pyc` or `.pyo` outside an immediate `__pycache__` directory is inventoried normally.
- `.gitignore`, `.gitkeep`, generated output, build directories, test data, editor metadata, requirements, services, templates, schemas, docs, fonts, and all other files are not implicitly excluded.
- Intentional source-only build/test/placeholder content must use `authoring_only`.
- Unexpected cache/build artifacts fail as undeclared or prohibited content; they cannot hide behind a broad exception.

Every remaining regular non-Python file must have exactly one classification:

- Typed runtime reachability.
- One supplemental runtime declaration.
- One authoring-only declaration.

Zero classifications is `undeclared_file`; multiple classifications is `duplicate_classification`.

## 2. Typed reachability

- Executor, orchestrator, and element roots use existing typed component validators rather than claiming whole directories blindly.
- Component manifests, schema-declared path fields, `STAGE.md`, declared assets, and declared schema/documentation routes create resource edges.
- Schema, example, and documentation content roots recursively classify directories.
- Renderer, planner, and finalizer declarations classify their manifests and typed path fields.
- Migration paths classify SQL.
- Documentation paths and `agent.required_context` classify documents.
- Supplemental directories recursively expand.
- Nested skills, requirements, templates, services, and other opaque assets must be reached through typed or supplemental declarations.
- Empty runtime-resource directories reject.
- Every physical file may be reached by exactly one declaration path.

## 3. Targeted runtime-use audit

Scan runtime Python files below bundled pack roots, excluding source paths classified as tests, golden inputs, development fixtures, or build outputs.

Recognize:

- `open`.
- `Path.open`, `read_text`, and `read_bytes`.
- `importlib.resources.files`, `open_text`, and `open_binary`.
- `pkgutil.get_data`.
- Simple literal `Path(__file__)` and `__file__` composition using `/`, `joinpath`, `with_name`, and `parent`.
- Existing executor requirements-file probing.
- Blender’s service-unit lookup.
- Existing typed component and rendering resource APIs.

Use only intra-module propagation of simple literal assignments. Do not attempt general static analysis of generated paths, project paths, user input, or network resources.

Every statically resolvable pack-relative runtime read must enter the runtime closure. A resolvable read outside the pack must move into its owner or resolve through a justified kernel-owned resource in the coverage ledger.

Migration SQL, component manifests, `STAGE.md`, `SKILL.md`, `requirements*.txt`, referenced schemas/templates, service files, and runtime assets cannot be authoring-only.

## 4. Source/wheel equality

Each audit emits sorted runtime-resource records:

```json
{
  "pack_id": "blender",
  "path": "server/blender-render-api.service",
  "kind": "service",
  "size": 1234,
  "sha256": "..."
}
```

Require equality of:

- Pack IDs.
- `provenance_identity`.
- Normalized manifest definitions, including authoring-only declarations.
- Runtime-resource paths, kinds, sizes, and hashes.
- Database declarations and derived heads.
- Documentation routes.
- Bundled provenance class.

Also require:

- Every source authoring-only path exists.
- No authoring-only path exists in the wheel.
- No undeclared non-Python bundled file exists in either environment.
- Absolute roots are never compared.

Use existing setuptools package-data support; add no packaging backend.

# V. Audit-only coverage ledger

Commit during implementation:

```text
docs/contracts/canonical-pack-coverage.json
scripts/canonical_pack_coverage.py
```

Commands:

```bash
python3 scripts/canonical_pack_coverage.py inventory \
  --root . \
  --output .oracle/evidence/canonical-pack/<boundary>/inventory.json

python3 scripts/canonical_pack_coverage.py check \
  --inventory .oracle/evidence/canonical-pack/<boundary>/inventory.json \
  --ledger docs/contracts/canonical-pack-coverage.json \
  --output .oracle/evidence/canonical-pack/<boundary>/check.json

python3 scripts/canonical_pack_coverage.py diff \
  --before .oracle/evidence/canonical-pack/<previous>/inventory.json \
  --after .oracle/evidence/canonical-pack/<boundary>/inventory.json \
  --output .oracle/evidence/canonical-pack/<boundary>/diff.json
```

Runtime never imports these artifacts.

Inventory inputs:

- Canonical bundled snapshot.
- Typed executor, orchestrator, element, renderer, planner, and finalizer projections.
- Canonical database projection.
- Runtime-resource closure.
- Structured documentation routes.
- Code-declared kernel migration, vocabulary, and repository constants.
- Exact AST inspection of application composition, SDK surfaces, product/operational CLI declarations, bridge mounts, doctor, backup, restore, inspect, package audit, and census generation.

Do not use the ledger to discover inventory and do not broadly grep arbitrary text.

Surface IDs:

```text
pack:<pack_id>
executor:<qualified_id>
orchestrator:<qualified_id>
element:<kind>/<id>
renderer:<qualified_id>
planner:<qualified_id>
finalizer:<qualified_id>
alias:<kind>:<qualified_id>
migration:<pack_id>/<integer>
table:<table>
stream_type:<dotted_name>
event_kind:<dotted_name>
command_kind:<dotted_name>
repository:<RepositoryId>
conformance:<pack_id>/<dimension>
cli_mount:<space-separated path>
sdk_surface:<stable service or method id>
bridge_mount:<token>
runtime_resource:<pack_id>/<relative path>
agent_document:<pack_id>/<relative path>
operational_consumer:<application|doctor|backup|restore|inspect|package|agent_census>
```

Sort rows by `(kind, surface_id)` and sort unique evidence and consumer fields.

Ledger rules:

- Schema is `astrid.canonical_pack_coverage.v1`.
- Disposition is `active` or `deleted`.
- An active owner is exactly `pack:<PackId>` or `kernel:<LowerIdent>`.
- Deleted rows have null owner, nonblank justification, immutable baseline evidence, and no consumers.
- Mechanically derived pack ownership cannot be overridden manually.
- Kernel ownership requires implementation evidence, test/contract evidence, justification, and proof that the surface cannot be represented by an existing pack declaration.
- Active rows require resolvable evidence and a consumer unless the row is itself an operational consumer.
- Consumer references resolve to active rows.
- `builtin` and deprecated aliases are deletion records.
- The 49 known `builtin.*` aliases are an exact baseline assertion; WP0 records all other deprecated aliases at the pinned source.

`check` fails on:

- `missing`
- `stale`
- `duplicate`
- `conflict`
- `deleted_still_active`
- `invalid_kernel_justification`
- `invalid_consumer`
- `unclassified`
- `undeclared_resource`
- `unexpected_owner`

Boundary diffs record added, removed, changed-owner, changed-evidence, changed-consumer, and changed-resource-digest sets. Every non-empty category requires review.

The immutable baseline inventory is evidence only, never runtime truth.

# VI. Database composition and migrations

## 1. Projection

Select:

- A synthetic code-owned `core` node at migration head 1.
- Every snapshot entry with bundled provenance and a `database` contribution.

No pack allowlist, standard tuple, expected-name branch, or schema-pack identity participates.

A synthetic trusted bundled database pack introduced in a test snapshot must enter composition without composition-code changes.

Each node contains ID, immutable declaration, owner resource handles, derived head, provenance, and existing collision projections.

## 2. Dependency semantics

For node `P`:

```text
head(P) = max(P.migrations[].version)
```

`depends_on: {pack: Q, min_migration: N}` means:

- `Q` is a selected database node or `core`.
- `head(Q) >= N`.
- All migrations of `Q` precede all migrations of `P`.
- It does not compare release versions or inspect applied project state.

Before database open, require:

- Every database pack has a direct or transitive path to `core`.
- No self-dependency.
- No duplicate dependency target.
- Every target has migrations.
- Each minimum is positive and no greater than the target head.
- The graph is acyclic.
- Existing table, migration identity/name, vocabulary, repository, CLI, bridge, and other collision checks pass.

## 3. Expected bundled fixture and ordering

The converted manifests are expected to project:

```text
core@1
├── references@1  requires core >= 1
├── runaway@1     requires core >= 1
├── shots@1       requires core >= 1
└── timeline@1    requires core >= 1
```

This is fixture evidence, not a composition authority.

Use deterministic Kahn sorting:

1. Edge `dependency → dependent`.
2. Seed a min-heap with zero-indegree nodes.
3. Heap key `(0 if id == "core" else 1, pack_id)`.
4. Pop, append, decrement dependents, and enqueue newly ready nodes.
5. On incomplete emission, return a deterministic lexical cycle.
6. Emit each node’s migrations in increasing integer version order.

Expected fresh fixture order:

```text
core/1
references/1
runaway/1
shots/1
timeline/1
```

For a database created under the former three-pack composition, retain existing `schema_migrations` rows and apply only missing `runaway/1`. Never rewrite or resequence applied rows.

## 4. Preserved guarantees

Preserve:

- Pack, integer version, and migration name.
- Existing SQL bytes.
- Owned tables.
- SHA-256 behavior.
- Name/checksum drift rejection.
- Too-new and unknown-pack refusal.
- Per-migration `BEGIN IMMEDIATE`.
- Atomic DDL/DML and migration-row recording.
- Read-only compatibility probing.
- `schema_migrations` as the sole applied-state record.

Replace `pack_resource_root(pack_id)` with registered owner resource handles. The migration runner cannot reconstruct `astrid/packs/<id>` paths.

Core remains explicit irreducible kernel behavior.

# VII. Documentation and behavior preservation

- All 22 retained product packs declare direct structured documentation.
- Add direct skills for blender, timeline, shots, references, and runaway.
- Repair media skill frontmatter.
- Package declared pack and nested component skills.
- Keep `_core` as a skill-only kernel shell without `pack.yaml`.
- Extend one generator so one snapshot produces both the capability index and canonical pack census.
- Census fields: ID, name, contribution categories, capability counts, database tables/head, documentation route, and ownership link.
- Exclude DDL and applied database state.
- Check mode fails on drift.
- Delete independent skill inventory and raw-directory reparsing.

Maintain a four-pack preservation matrix covering timeline, shots, references, and runaway across:

- Migrations.
- Repositories.
- Streams.
- Events.
- Commands.
- CLI.
- SDK.
- Bridge.
- Conformance.

Every cell receives baseline/final evidence or an explicit justified `N/A`.

For Runaway, the matrix must record:

- Migration: `runaway/1`, one owned `runaway_transitions` table.
- Repository: `RunawayRepository`.
- Command: `runaway.create`, including receipt replay/mismatch behavior.
- Conformance: `writer_ownership` and `crash_atomicity`.
- Streams: `N/A — Runaway declares no pack-owned stream type`.
- Events: `N/A — Runaway declares no pack-owned event kind`; kernel run/evidence events must not be mislabeled as Runaway-owned.
- CLI: `N/A — Runaway declares no CLI mount`.
- SDK: `N/A — Runaway has no dedicated public SDK facade`; standard `AstridClient` composition remains an operational-consumer proof, not invented pack API.
- Bridge: `N/A — Runaway declares no bridge mount`.

## 1. Deterministic Runaway temporary-project fixture and receipt

Replace every test dependency on the absent historical `projects/runaway-piano-colour-demo` tree with one generated fixture:

```text
tests/packs/test_runaway_canonical_roundtrip.py
fixture: generated_runaway_project
test: test_generated_temporary_project_round_trip
```

The fixture:

1. Creates a fresh pytest-owned temporary projects root outside all bundled pack roots.
2. Uses the fixed project slug `runaway-roundtrip` and stable logical project/run identifiers supplied by the fixture.
3. Uses fixed clock/input values or excludes nondeterministic timestamps from semantic comparison.
4. Creates a small fixed transition payload in test memory or beneath the temporary project only:
   - unique contiguous ordinals;
   - fixed start/duration values;
   - fixed nonblank prompts;
   - fixed metadata;
   - no external media or historical demo input.
5. Opens the database through the canonical standard application/snapshot path so the applied migration order is exactly:

```text
core/1
references/1
runaway/1
shots/1
timeline/1
```

6. Creates the kernel project and run through sanctioned application/repository seams.
7. Exercises every Runaway-owned surface that exists:
   - `RunawayRepository.create`;
   - ordered `list`, `show`, and ordinal lookup;
   - `runaway.create` command receipt;
   - identical idempotent replay;
   - mismatched replay rejection;
   - FK/writer ownership;
   - transaction/crash atomicity.
8. Reopens the same temporary project through the standard client/database path and proves the stored transitions and migration rows round-trip unchanged.
9. Records the explicit N/A reasons above for absent stream, event, CLI, dedicated SDK, and bridge surfaces.
10. Deletes the temporary root through normal pytest cleanup; it is never copied into the repository or wheel.

The fixture must not import, probe, restore, synthesize from, or assert the existence of:

```text
projects/runaway-piano-colour-demo
```

The old demo-dependent tests are either rewritten around this generated payload or deleted where they test only missing historical content. The Runaway prompt unit tests retain small in-memory deterministic cases without recreating the missing 566-transition demo.

The authoritative receipt path is:

```text
.oracle/evidence/canonical-pack/final/runaway-roundtrip.json
```

The receipt schema is `astrid.canonical_pack.runaway_roundtrip.v1` and records:

- Fixture/test identifier.
- `generated_temporary_project: true`.
- `historical_demo_restored: false`.
- `historical_demo_packaged: false`.
- Exact focused command and exit code.
- Source or installed-wheel execution mode and Astrid origin.
- Temporary root used for that run.
- Normalized fixed input and its SHA-256.
- Captured catalog/snapshot identity.
- Ordered applied migration rows and migration checksums.
- Project/run identifiers used.
- Repository create/list/show/ordinal results.
- Command receipt key and replay result.
- Mismatch-rejection result.
- Writer-ownership and crash-atomicity results.
- Explicit N/A surface reasons.
- Final row counts and semantic round-trip result.

The final evidence runner executes exactly:

```bash
ASTRID_RUNAWAY_RECEIPT="$PWD/.oracle/evidence/canonical-pack/final/runaway-roundtrip.json" \
python3 -m pytest -q \
  tests/packs/test_runaway_canonical_roundtrip.py::test_generated_temporary_project_round_trip
```

The test writes the receipt only when `ASTRID_RUNAWAY_RECEIPT` is supplied; ordinary test runs remain artifact-free. The final evidence command runs once. The full suite may later execute the test normally without rewriting the immutable receipt.

# VIII. Work packages

## WP0 — immutable baseline and ownership reconciliation

Estimate: **0.45–0.65 week**.

- Verify source `7ac50c12e8e4d90988fee603ffdb9896e5628792`.
- Capture 19 capability manifests, four schema manifests, `_core`, 64 executors, 12 orchestrators, 10 elements, eight rendering extensions, four database packs, and 18 existing skills.
- Record 23 current product directories, `builtin` deletion, and the final 22-pack expectation.
- Inventory every customization and initial owner.
- Record all deprecated aliases as intended deletions.
- Capture database ordering, migration identities/checksums, open behavior, repositories, vocabulary, CLI/SDK/bridge behavior, doctor, backup, restore, and wheel behavior.
- Seed the four-pack preservation matrix and 15-criterion evidence matrix.
- Record the exact source inventory allowlist from §IV.1; no executor may expand it without reopening the plan.
- Record the missing historical Runaway demo as absent baseline evidence and freeze the §VII.1 generated fixture as its only replacement gate.
- Explicitly forbid restoring or packaging that demo.
- Do not build a wheel or run the full suite.

Exit: every baseline surface is pack-owned, kernel-owned, intended deletion, or an explicitly justified Runaway N/A.

## WP1 — contract, immutable model, catalog, admission, and audit tools

Estimate: **1.2–1.6 weeks**. Depends on WP0.

Contract-freeze subgate:

- Land the exact v2 schema and immutable normalized types.
- Land golden and invalid fixtures.
- Land provenance identity, runtime-resource, authoring-exclusion, and external-admission types.
- Prove source versus installed-artifact authoring semantics.
- Prove the legacy-only and canonical-plus-legacy discovery failures.
- Pass schema and normalization tests.
- Obtain cumulative review before conversion.

Then:

- Evolve `PackDefinition`; do not create a parallel product model.
- Implement the sole v2 loader.
- Delete fallback parsing from the new path.
- Implement confined digest-carrying runtime-resource handles.
- Implement the process/package-lifetime `BundledCatalog`.
- Implement candidate capture and `CatalogSnapshot` without fingerprint machinery.
- Implement deterministic precedence, duplicates, provenance, and external-database rejection.
- Make `InstalledPackStore` emit the one installed admission projection and its captured revision/permission binding.
- Route all external capability projections through that disposition.
- Implement narrow pre-use external handle verification without retry.
- Add the immediate installed pre-use store verification from §III.5, keyed by the captured revision and permission receipt.
- Prove fail-closed behavior for active-revision switch, invalidation, provenance change, receipt replacement, permission revocation/mismatch, and unchanged success.
- Prove that a newly activated revision is invisible until a later operation snapshot.
- Make local pack creation emit strict capability-only v2.
- Implement the bounded source/wheel classifier and targeted AST audit.
- Implement coverage tooling.
- Adapt registries to accept snapshot projections.

Exit: the executable contract, catalog, lifetime, external admission, immediate installed-use fence, resource audit, and coverage tooling are fixture-proven.

## WP2 — bundled conversion, ownership, resources, and documentation

Estimate: **1.0–1.35 weeks**. Depends on WP1.

- Convert all 22 retained packs.
- Fold four schema manifests into `database`.
- Preserve migration bytes and behavior declarations.
- Make references the combined exemplar without changing its three-table model or semantics.
- Delete `builtin` and deprecated aliases.
- Add missing direct skills and repair media.
- Classify every bundled non-Python source file.
- Explicitly declare requirements, Blender’s service unit, templates, schemas, nested skills, fonts, SQL, and runtime assets.
- Move pack-owned cross-root assets to their owner; justify true kernel assets.
- Switch bundled discovery to v2.
- Regenerate capability/census output.
- Add the generated Runaway fixture without adding historical demo files or packaged fixture resources.

Boundary A:

- Generate inventory/check/diff.
- Prove exactly 22 product packs load.
- Prove no `schema-pack.yaml` or alternate pack manifest remains.
- Prove source resource classification and authoring exclusions.
- Prove the missing Runaway demo is absent from source and package-data inputs.
- Review contract, catalog lifetime, provenance identity, external admission, installed-use fence, documentation, resources, and ownership cumulatively.
- Resolve accepted findings before WP3.

## WP3 — database hard cut

Estimate: **1.0–1.4 weeks**. Depends on Boundary A.

- Extract reusable collision/migration algorithms from the schema-pack subsystem.
- Remove schema-pack identity from surviving types and diagnostics.
- Add synthetic core and catalog-derived database nodes.
- Implement exact dependency, head, graph, and ordering semantics.
- Enforce core reachability and collisions before open.
- Carry resource handles and provenance into migration execution.
- Delete fixed standard builders, tuples, and name-selection branches.
- Rewire writable and read-only paths to the operation snapshot.
- Test synthetic bundled database selection.
- Validate:
  - Fresh four-pack database.
  - Legacy three-pack writable upgrade.
  - Read-only pending runaway without mutation.
  - Existing four-pack no-op.
  - Collisions.
  - Missing/self/duplicate dependencies.
  - Cycles.
  - Minimum-head failures.
  - Checksum/name drift.
  - Transaction rollback.
  - Unknown/too-new applied rows.
  - Every external provenance class.
  - Generated Runaway temporary-project migration and reopen.

Boundary B:

- Generate inventory/check/diff.
- Regenerate the four-pack matrix, including explicit Runaway N/A reasons.
- Review ownership and persistence cumulatively.
- Resolve findings before WP4.

## WP4 — operational convergence

Estimate: **1.05–1.45 weeks**. Depends on Boundary B.

Thread one snapshot through:

- Application startup.
- `AstridClient`.
- Standalone SDK calls.
- Executor/orchestrator/element registries.
- Rendering and generation registries.
- Bridge composition.
- Helpers and read probes.
- Doctor.
- Backup.
- Restore.
- Install validation.
- Inspect.
- Census generation.

Preserve:

- `open_database(path, registry)` as the SQLite seam.
- `DatabaseWriter` and its exclusive-owner lock.
- `UnitOfWork`.
- Static repository/service/CLI/bridge factories.
- Backup/restore payload semantics.
- The eight-family CLI gateway and two nested mounts.

Raw database reads use the shared compatibility probe or an already-probed connection.

Every installed capability execution route must invoke the `InstalledPackStore` pre-use admission-state verification immediately before pack code. No executor, SDK facade, rendering path, or registry may bypass it or implement a second admission check.

`python3 -m astrid.core.pack.cli inspect <id> [--json]` exposes normalized identity, provenance class/identity, captured admission disposition where applicable, contribution categories, database dependencies/migrations/tables/head, documentation, runtime-resource closure, and relevant rejected/change diagnostics.

Inspect may report the snapshot’s captured installed disposition. It does not refresh that disposition merely to inspect. Execution-time store rejection is reported as a use failure, not silently rewritten into plan or snapshot state.

JSON uses a versioned envelope and sorted arrays; text renders from the same DTO.

Doctor reports canonical census, catalog/resource/documentation health, and expected/applied/pending migrations by owner without mutation.

Exit: operational consumers agree on one snapshot; none independently reparses, rescans, or re-evaluates installed trust, and every installed execution passes through the existing store-owned use-time fence.

## WP5 — deletion, final gates, and packaging preparation

Estimate: **0.8–1.15 weeks**. Depends on WP4.

Delete:

- All `schema-pack.yaml`.
- Schema-pack parser, model, discovery, builders, standard lists, and compatibility exports.
- V1 pack parsing and flat/schema-less loading.
- Alternate filename probes.
- Manifest-supplied trust handling.
- Raw identity readers.
- Independent pack/skill inventories.
- Deprecated aliases and compatibility tests/docs.
- Fixed database tuples and name-based selection.
- Legacy-format audit support.
- Snapshot fingerprint and general stale-snapshot machinery if any interim implementation introduced it.
- Historical Runaway-demo assertions and migration tests that depend only on absent demo content.

Retain exact gates for:

- Prohibited paths.
- Retired imports and parser symbols.
- Fixed composition tuples.
- Raw identity reconstruction.
- Independent rescans.
- Divergent external admission.
- Installed execution bypass of the store-owned pre-use check.
- Rediscovery/retry or replacement-revision selection inside that check.
- Coverage.
- Behavior matrix.
- Targeted resource use.
- Census drift.
- Source/wheel closure.
- Legacy-only bundled directories.
- Absence of `projects/runaway-piano-colour-demo` from package inputs and wheel contents.
- Presence and deterministic behavior of the generated Runaway fixture.

Packaging:

- Extend ordinary package-data patterns for every runtime-resource kind.
- Include all manifests, SQL, skills/docs, requirements, services, schemas, templates, fonts, and runtime assets.
- Exclude authoring-only paths.
- Do not include the generated Runaway fixture or any historical Runaway demo.
- Add no custom backend.
- Convert wheel-building tests into source contracts, mocked builder units, or consumers of `ASTRID_PREBUILT_WHEEL`.
- Add `InstalledArtifactHarness.from_wheel(path, ...)`.
- Ensure every current `build_once` callsite consumes the prebuilt wheel when set.
- Keep `build_once` only as optional developer convenience; authoritative validation cannot invoke it.

Boundary C:

- Generate inventory/check/diff.
- Run source package-data and authoring-exclusion checks without building.
- Regenerate the final matrix candidate.
- Review convergence, deletion, admission, installed-use fencing, Runaway fixture, documentation, resource classification, packaging, and build-call graph.
- Prove authoritative validation has exactly one build invocation.
- Resolve findings before WP6.

## WP6 — one-build validation and evidence closure

Estimate: **0.5–0.7 week**. Depends on Boundary C.

One authoritative owner runs:

```bash
python3 -m build --outdir .oracle/evidence/final-build
```

Require exactly one wheel, record its SHA-256, and set:

```bash
ASTRID_PREBUILT_WHEEL=<absolute-wheel-path>
```

No later command may invoke `python -m build`, `build_once`, `pip wheel`, or another source build.

Run the required focused suite:

```bash
python3 -m pytest tests/packs tests/v10/test_catalog_migrations.py \
  tests/v10/test_m8_packaging.py tests/v10/test_pack_factoring.py \
  tests/v10/test_reference_repository.py tests/sdk/test_references.py \
  tests/sdk/test_extended_composition.py
```

Run the deterministic Runaway receipt command exactly once:

```bash
ASTRID_RUNAWAY_RECEIPT="$PWD/.oracle/evidence/canonical-pack/final/runaway-roundtrip.json" \
python3 -m pytest -q \
  tests/packs/test_runaway_canonical_roundtrip.py::test_generated_temporary_project_round_trip
```

Run:

```bash
python3 -m astrid doctor
```

Using the same wheel, run all final contract scenarios:

- Installed bundled-catalog load.
- Source/wheel normalized-definition and provenance-identity comparison.
- Bidirectional runtime-resource audit.
- Source authoring-path presence and wheel authoring-path absence.
- Documentation and `_core` census audit.
- Fresh, upgraded, read-only-pending, and existing SQLite scenarios.
- External capability success and external database rejection across every source class.
- Installed active/validated/permission-accepted execution success.
- Installed inactive, unvalidated, identity-mismatched, and permission-mismatched inspect-only behavior at snapshot construction.
- Installed active-revision switch after capture fails at use.
- Installed invalidation after capture fails at use.
- Installed provenance or permission-receipt change after capture fails at use.
- Unchanged installed revision/receipt executes successfully.
- Newly activated installed revision appears only to a later operation snapshot.
- No installed pre-use failure triggers rediscovery, retry, snapshot replacement, or alternate revision execution.
- References round trip.
- Generated temporary-project Runaway round trip and its immutable receipt.
- Explicit proof that the historical Runaway demo was neither restored nor packaged.
- Backup/restore.
- Inspect text/JSON.
- Doctor/inspect non-mutation.
- Exact legacy gates.
- Zero-unclassified coverage.

Then run once:

```bash
python3 -m pytest
```

# IX. Executable clean-wheel isolation contract

The installed-artifact harness must:

1. Create a temporary virtual environment outside the repository checkout and outside every source pack root.
2. Install the single prebuilt wheel with no editable/source installation.
3. Launch the environment’s Python from a working directory outside the checkout.
4. Invoke Python with `-I -P`.
5. Set `PYTHONNOUSERSITE=1`.
6. Remove `PYTHONPATH` and other source-path injection variables.
7. Assert the repository checkout and source pack roots are absent from normalized `sys.path`.
8. Assert `astrid.__file__`, all imported Astrid module origins, catalog manifest origins, and `importlib.resources` origins lie beneath the isolated environment’s installed site-packages root.
9. Fail if any origin resolves beneath the checkout, source pack root, or another ambient Astrid installation.
10. Run installed catalog, docs/census, migration-resource, and closure checks only after these assertions pass.

The harness receipt records:

- Wheel path and SHA-256.
- Environment root.
- Python executable and flags.
- Working directory.
- Normalized `sys.path`.
- Astrid module origin.
- Every audited manifest/resource origin.
- Exit status.

A passing source import can never count as wheel evidence.

# X. Baseline-independence receipt contract

If the final full suite exposes an apparently unrelated failure, do not run a second baseline full suite and do not rebuild the wheel.

Reproduce only the focused failing scenario against the pinned source. The receipt must contain:

- Exact source revision:
  `7ac50c12e8e4d90988fee603ffdb9896e5628792`.
- Verification that the baseline tree contains that revision and no test-affecting edits.
- Final branch revision.
- OS, architecture, Python version, dependency/environment receipt, and relevant normalized environment variables.
- Exact focused command or node IDs.
- Working directory and projects-root/test-temporary-root configuration.
- Exit code.
- Full failure signature and relevant stdout/stderr for both baseline and final.
- A controlled before/after table showing the same focused scenario under the same environment.
- Explicit comparison of exception type, failed assertion, and normalized stack/failure signature.
- Confirmation that no baseline wheel build or baseline full suite occurred.

A failure may be classified as pre-existing only if the focused pinned-source run reproduces the materially same failure under the controlled environment. If it does not, criterion 14 remains failed and the implementation must be repaired.

The absent historical Runaway demo is already established baseline evidence, not a permitted baseline-failure waiver. Final Runaway acceptance comes only from the generated fixture and receipt.

# XI. Final artifacts

Final closure produces:

- One wheel and SHA-256.
- Installed isolation receipt containing that hash.
- Installed module/resource origin receipt.
- Coverage inventory/check/diff.
- Runtime-resource source/wheel comparison.
- Authoring-only source/wheel audit.
- Four-pack preservation matrix.
- Deterministic Runaway temporary-project round-trip receipt at `.oracle/evidence/canonical-pack/final/runaway-roundtrip.json`.
- Proof that the missing historical Runaway demo is absent from source additions and wheel contents.
- Fifteen-row evidence matrix.
- Focused and full-suite receipts.
- Doctor and inspect receipts.
- External admission matrix, including post-capture installed-state mutations and unchanged success.
- Exact legacy-gate receipt.
- Any baseline-independence receipts.
- Independent reviewer dispositions.

After all evidence passes:

- Obtain final Sol oracle review.
- Record any exact stability result only in the separate Megado stability receipt over this plan digest.
- Do not rewrite this plan to copy current orchestration state.
- Commit only reviewed paths.
- Push only `HEAD:refs/heads/megado/canonical-pack-beta`.
- Open the completed worktree.
- Do not merge, rebase, deploy, promote, or publish.

# XII. Review cadence

1. Contract-freeze subgate during WP1.
2. Boundary A after WP2.
3. Boundary B after WP3.
4. Boundary C after WP5.
5. Final review after WP6.

At A, B, C, and final:

- Generate one immutable coverage artifact set.
- Regenerate relevant matrices.
- Converge code, evidence, and status at one checkpoint.
- Run one cumulative independent review by default.
- Resolve accepted findings and obtain a fresh pass before continuing.

Focused local checks may run during implementation. Immutable cumulative artifacts are generated only at these boundaries.

The plan artifact, current run status, and stability judgment remain separate:

- This plan owns executable intent.
- `.oracle/status.md` owns the current Megado phase.
- A new immutable stability receipt owns any later stability judgment over this exact plan digest.

# XIII. Criterion traceability

| Criterion | Primary proof |
|---|---|
| 1. Strict v2 bundled packs | WP1–WP2, legacy discovery tests, A, WP5–WP6 |
| 2. No independent identity parsing | Catalog/snapshot invariant, WP4–WP6 |
| 3. Zero-unclassified ledger | WP0–WP2 and all boundaries |
| 4. Manifest-derived database composition | WP3 synthetic bundled-pack test |
| 5. Four-pack semantics preserved | Four-pack preservation matrix plus generated Runaway round-trip receipt |
| 6. Owner-relative migrations and safety | WP3 SQLite matrix and Runaway migration receipt |
| 7. Operational agreement | WP4, store-owned installed-use fence, Boundary C, final |
| 8. Structured docs and `_core` census | WP2, WP4–WP6 |
| 9. Inspect and doctor | WP4, Boundary C, final |
| 10. Clean-wheel closure | Isolated installed harness and source/wheel audit |
| 11. Legacy deletion | Catalog rejection plus exact path/import/AST gates |
| 12. External capability/database policy | Admission matrix, immediate installed-state checks, and fail-closed tests |
| 13. Golden forms | WP1 and final |
| 14. Focused/full validation | WP6 one-build flow, Runaway receipt, and baseline receipt contract |
| 15. Evidence matrix and oracle | WP6 final closure and separate stability receipt |

# XIV. Explicit North Star anti-pattern rejection

Every named anti-pattern is rejected:

- **No hidden schema-pack subsystem:** schema-pack identity, parser, discovery, builders, standard lists, compatibility exports, and shipped manifests are deleted—not embedded behind `pack.yaml`.
- **No universal service locator:** the catalog supplies immutable declarations and typed projections only; typed registries and static factories retain runtime construction ownership. The immediate installed-use fence is a method of the existing `InstalledPackStore`, not a new service.
- **No duplicated DDL or mutable facts:** YAML and skill prose contain no columns, constraints, indexes, transformations, checksums, applied rows, mutable heads, or copied installation stability state. Migration SQL and SQLite remain authoritative.
- **No project composition machinery:** no per-project pack locks, enable/disable/purge state machine, database-aware uninstall, dynamic database plugins, or speculative migration ceremony.
- **No external SQL:** every non-bundled `database` declaration rejects before resources or SQL are read.
- **No dynamically unloadable kernel:** synthetic `core` and `_core` remain irreducible code/guidance surfaces.
- **No compatibility forms:** no v1, alternate filename, schema-less manifest, legacy fallback, dual read, compatibility export, deprecated alias, or schema-pack path survives.
- **No premature success:** completion is impossible while any bundled customization, documentation surface, operational consumer, packaged resource, trust decision, installed-use check, or database projection bypasses canonical ownership.

Additional scope rejections:

- No fixed-composition disguise.
- No runtime coverage ledger.
- No manifest-supplied trust.
- No operation-internal discovery.
- No contribution from losing candidates.
- No global snapshot fingerprint.
- No rejected-diagnostic hash.
- No retry-on-change loop.
- No bundled cache invalidation subsystem.
- No recursive bundled rescan per operation.
- No general installed-state freshness framework.
- No admission-state lock.
- No alternate-revision selection after snapshot capture.
- No newly activated revision entering an existing operation.
- No second trust or admission service.
- No capability-specific permission policy.
- No perfect/general static analysis.
- No runtime asset hidden as authoring-only.
- No broad cache/build exclusion.
- No source-only path required in an installed wheel.
- No second parser or relaxed wheel grammar.
- No dependency solver, marketplace, signing, sandboxing, remote activation, or UI.
- No generalized dynamic factory framework.
- No custom packaging backend.
- No broad repository-wide regex scanner.
- No repeated wheel build or second baseline full suite.
- No repeated immutable boundary artifacts.
- No restoration, reconstruction, or packaging of the missing historical Runaway demo.
- No use of the absent demo as a final validation prerequisite or baseline waiver.
- No invented Runaway stream, event, CLI, SDK, or bridge surface.
- No expansion into unrelated models, LoRAs, taxonomies, or kernel primitives.
- No success with an active bypass, divergent external admission, stale installed execution authority, unclassified surface, missing documentation, undeclared resource, invalid authoring exclusion, source/wheel mismatch, source-contaminated wheel audit, or incomplete Runaway receipt.

This replacement advances the complete North Star strictly within the frozen goal. It requires **no new exploration lane** and **no `[XHARD]` work**.


## ACCEPTED WAVE 5 SYNTHESIS

# Settled-plan wave 5 synthesis

Plan SHA-256:
`b836dbab74395860486e6ebec980a66b8a150ff238c3d3a9393b0598f554f062`

## Accepted material changes

1. **Freeze installed admission at snapshot capture; remove the pre-use state
   recheck.** A check immediately followed by execution cannot prevent an
   interleaving mutation without holding a lock across pack code. That lock is
   disproportionate and risks deadlock. Instead, the existing store-owned
   admission projection validates and captures the active revision, canonical
   provenance, manifest digest, accepted permissions, and validity once while
   constructing the top-level operation snapshot. The snapshot may execute that
   selected revision for the operation lifetime; activation/rollback/
   invalidation changes affect the next operation. Immediate pre-use checks are
   limited to the captured manifest and consumed resource handles. No rescan,
   retry, lock, revocation service, or second trust owner is added.
2. **Hard-cut installed records to an exact v2 admission record.** New records
   persist record schema version 2, revision identity, canonical root-independent
   provenance identity, normalized manifest digest, normalized accepted
   permissions, and validation disposition. Remove raw-manifest trust reparsing
   and silent missing-field defaults from the active v2 path. Pre-v2/incomplete
   records fail closed with an explicit reinstall diagnostic; there is no
   migration, defaulting shim, or revalidation fallback. Golden external-pack
   tests install a fresh v2 record and prove capability execution; external
   `database` still rejects before resource/SQL access.
3. **Close bundled direct-child discovery.** Under packaged `astrid/packs`,
   every direct child directory except the irreducible `_core` guidance
   directory must contain exactly one strict v2 `pack.yaml` and load as a
   retained product pack. There is no generic bundled “non-pack directory” skip.
   The audit compares the sorted direct-child set, loaded catalog set, and
   expected retained count/names generated from that filesystem set; missing,
   extra, legacy-only, duplicate, or unloaded children fail.
4. **Remove bundled documentation opt-outs for this beta set.** All 22 retained
   bundled product packs are user/agent-facing and must declare valid packaged
   structured documentation. `documentation.kind: none` is invalid for bundled
   candidates, so admission never consults the audit-only coverage ledger. The
   frozen goal's opt-out allowance remains unused; no internal utility pack is
   retained as a product pack.
5. **Audit Python ownership without declaring Python as package data.** The
   coverage inventory enumerates every Python file/module below each bundled
   pack root and maps it to the owning pack plus a declared typed contribution
   module/subtree or an exact justified package-initialization role. Unreachable,
   multiply owned, or unclassified Python modules fail. Python remains governed
   by normal wheel module packaging and source/wheel import-origin proof, not by
   the non-Python resource grammar.
6. **Use concrete receipt identity, not a snapshot fingerprint.** Runaway and
   other operation receipts record the ordered selected provenance identities
   relevant to the operation, their pack/revision/version fields, and the exact
   migration/resource digests consumed. They do not serialize rejected
   candidates, layer order, or an invented whole-snapshot identity.

## Deduplication and dispositions

- The manifestless-child gap was independently reported by two critics and is
  one accepted correction.
- The undefined Runaway snapshot identity was independently reported by two
  critics and is resolved by item 6.
- The admission TOCTOU and incomplete installed-record findings are resolved
  together by items 1–2. This intentionally supersedes Wave 4's pre-use store
  state recheck based on new concurrency evidence; the capture-time admission
  authority remains single and fail-closed.
- No project lock, lock-across-execution, lifecycle system, immediate revocation
  service, dynamic plugin framework, compatibility record migration, or global
  snapshot fingerprint is accepted.
- No new research lane or `[XHARD]` work is required.

## North Star disposition

**Conditionally aligned.** The new evidence exposes residual closure and
admission ambiguity, but each has a narrow direct-cut resolution that makes the
system simpler. Sol must revise the complete plan, return exact `STABLE`, and a
fresh settled-plan wave must inspect the new snapshot.



===== RAW WAVE 5 CRITIC: .oracle/findings/settled5/authority-architecture.txt =====
**NOT CLEAN**

1. **P0 — Installed admission remains TOCTOU-unsafe.**  
   §III.5 performs a state read, then invokes pack code, while explicitly forbidding an admission-state lock. No invariant states that execution and revision mutation are serialized by the same existing mechanism. Current `astrid/core/pack/store.py:372-410` changes the active revision through multiple filesystem operations; the rollback caller locks only its own scope at `astrid/core/pack/install_local.py:972-975`. Interleaving is therefore possible:

   1. pre-use check observes revision A and passes;
   2. rollback/invalidation switches to B;
   3. execution invokes A.

   The required mutation tests appear to cover mutation before verification, not mutation between verification and invocation. This leaves criterion 12 and the “stale installed execution authority” anti-pattern unresolved. Investigate whether the existing per-pack install lock can safely cover the check-to-invocation interval; otherwise provide a proof of single-threaded mutation/use serialization. No new service is required, but the synchronization contract must be explicit.

2. **P1 — A bundled product can silently disappear.**  
   §III.1 step 4 classifies a direct child lacking `pack.yaml` and legacy basenames as a non-pack and skips it. The plan claims an “exact-path gate” compensates, but §V never defines that gate’s input, artifact, or failure rule. WP0’s captured directory count is not an executable invariant. Since coverage inventory begins from the canonical snapshot, an omitted manifest means the directory is absent from inventory too. A removed manifest or newly added product directory could pass the 22-pack gate while violating criteria 1 and 3. Require a pinned direct-child/product-root comparison with explicit `_core` handling.

3. **P1 — Documentation opt-out enforcement has contradictory authorities.**  
   §II says bundled admission rejects `documentation.kind: none` unless the coverage ledger classifies the pack as internal; §V says the ledger is audit-only and runtime never imports it. Thus the specified loader cannot enforce the stated exception without either a second hard-coded authority or weakening admission enforcement. Current 22-pack scope limits immediate impact, but the frozen grammar remains unresolved.

The Wave 1–4 accepted corrections, including the stability-receipt/header distinction and generated Runaway fixture, are not repeated objections. North Star alignment remains unproven until these boundaries are closed.
0

===== RAW WAVE 5 CRITIC: .oracle/findings/settled5/sequence-proof.txt =====
1. **P1 — Manifestless bundled directories can disappear without a final gate.**  
   §III.1 step 4 explicitly classifies a direct child lacking `pack.yaml` and legacy filenames as a non-pack and skips parsing it. The plan says “coverage and exact-path gates” prevent disappearance, but no exact-path contract or command is defined. §V’s inventory inputs begin with the canonical snapshot and projections, so an unmanifested product directory cannot enter that inventory. WP0’s 23-directory baseline is evidence, not a final invariant; WP2 only proves that 22 packs load. Add proof that every direct child of `astrid/packs` other than `_core` is either a loaded v2 pack or an explicitly approved non-pack. Otherwise criteria 1/3 and the North Star “nothing remains unclassified” claim are not closed.

2. **P2 — Python-source ownership is not closed by the resource audit.**  
   §IV.1 deliberately excludes all `.py` files from package-data equality and requires only a targeted runtime-use audit. The closed-world classification requirement that follows applies only to “every remaining regular non-Python file.” Therefore an additional Python module under a bundled pack can be shipped/importable without a manifest content declaration, coverage-ledger row, or authoring-only classification. WP0’s captured component counts and §V’s AST inspection do not explicitly enumerate all bundled Python files or prove that each is owned by a canonical component/pack or justified kernel surface. This leaves a possible bundled customization bypassing criterion 3 and the final North Star anti-pattern gate.

3. **P2 — Runaway receipt snapshot identity is underspecified.**  
   §VII.1 requires “captured catalog/snapshot identity,” but §III.6 explicitly prohibits `snapshot_fingerprint` and defines no replacement receipt field or serialization. `provenance_identity` identifies individual candidates, not the complete ordered snapshot, rejected-candidate set, or construction context. The receipt can therefore be internally valid without being reproducibly bound to the exact snapshot used for the migration proof. Define the receipt’s concrete snapshot identity fields or explicitly scope it to the ordered selected provenance identities.

All accepted Wave 1–4 dispositions, the remaining criteria, and the named North Star anti-patterns otherwise have explicit coverage; these are the remaining proof gaps.
0

===== RAW WAVE 5 CRITIC: .oracle/findings/settled5/simplicity-scope.txt =====
1. **P0 — undefined snapshot identity conflicts with the explicit no-fingerprint rule.**  
   §VII.1 requires the Runaway receipt to record a “captured catalog/snapshot identity”; §XI repeats that receipt as final evidence. However, §III.6 explicitly defines `CatalogSnapshot` without an identity and prohibits `snapshot_fingerprint`, rejected-diagnostic hashing, and global layer-order hashing. No alternate encoding is specified. Satisfying the receipt therefore requires either inventing prohibited machinery or omitting a required field. This blocks the Runaway receipt and criteria 14–15. The simplest resolution is to require only already-defined selected-pack provenance identities and migration/resource evidence, not an undefined snapshot identity.

2. **P0 — installed admission binding is not implementable against the pinned store contract without an unresolved persistence decision.**  
   §III.5 requires exact `validated_provenance_identity` and `accepted_permissions` receipt verification. In the pinned source, `InstallRecord` contains `manifest_digest`, `trust_summary`, and `permissions_accepted`, but no validated provenance identity or receipt identity/version (`astrid/core/pack/store.py:44-79`). Installation records a raw manifest-file digest and normalized permissions (`astrid/core/pack/install_local.py:295-310`); trust extraction still reparses the raw manifest (`astrid/core/pack/validate.py:1028-1130`). `InstallRecord.from_dict()` silently defaults missing fields for older records (`store.py:84-89`). The phrase “including its existing store-owned receipt identity/version when one exists” leaves the critical case undefined. Existing installed capability packs would either fail closed, violating criterion 12, or require an unspecified record migration/revalidation path. WP1 must settle the exact mapping and old-record behavior without introducing a second admission authority.

No additional material simplification or defect found in criteria 1–11 and 13–15, the accepted Wave 1–4 dispositions, or the North Star anti-patterns. The catalog, database, resource, documentation, Runaway-scope, and no-new-machinery constraints remain aligned apart from the two receipt/admission gaps above.
0

## RELEVANT SOURCE EVIDENCE


===== .oracle/findings/explore/E8-external-security.txt =====
1. **Earliest common seam: `discover_pack_metadata._add`.** All layered discovery converges there with provenance already known: `source`, `local`, `extra`, `env`, `installed` are ordered at `astrid/core/pack/discovery.py:39-41`; `_add(pack, source_kind)` creates the shared metadata at `:116-123`. Reject external `database` declarations there—before any typed registry projection or schema registry registration. This confirms `.oracle/plan.md` §6-7 and WP1.

2. **Admission paths traced.**
   - Bundled source packs: `discover_packs()` at `astrid/core/pack/loader.py:84-107`.
   - Project-local packs: materialized/discovered at `astrid/core/pack/loader.py:53-72` and `astrid/core/pack/discovery.py:216-219`; `local` is external to the bundled catalog.
   - Explicit extra roots and `ASTRID_PACKS_PATH`: `discovery.py:127-209`, `:227-234`.
   - Installed packs: active revisions from `InstalledPackStore` at `store.py:195-216`, consumed at `discovery.py:235-257`.
   - Git installs: clone/pin/detect, then re-enter local install at `install_git.py:300-355`; publication is active revision plus `install.json` at `install_local.py:375-434`.
   - Trust inspection is separate: `extract_trust_summary()` parses manifest-derived data at `validate.py:1028-1130`; installed trust audit runs later in rendering at `rendering/registry.py:717-780`.

3. **Critical provenance loss.** `discover_packs_ordered()` strips `DiscoveredPack` to bare `PackDefinition` at `discovery.py:262-282`; executor/orchestrator registries consume that at `execution/executor/registry.py:292-329`. This conflicts with the plan’s “derive trust from discovery provenance” control. All capability consumers must retain canonical provenance.

4. **Current database boundary is independently fixed.** `core/schema_packs/standard.py:31-45` loads only hard-coded bundled schema manifests; `SchemaPackRegistry.register_pack()` never opens SQL at `schema_packs/registry.py:142-144`; SQLite admission begins at `migrations/runner.py:301-322`. The future catalog must replace the fixed builder, not add a second guard downstream.

5. **Affected tests/risks.** Existing provenance coverage: `tests/core/rendering/test_registry_matrix.py:242-273`, `:609-650`, `:653-686`; Git/revision coverage: `tests/packs/test_git_pack_install.py:1-5`. Add capability-only success plus external database fail-closed cases across local, extra, env, Git-installed, and active-revision discovery. `pack.yaml` currently accepts self-declared `origin`/`install_tier` (`loader.py:161-172`) and cannot authorize trust.
0
===== .oracle/findings/explore/E5-coverage-ledger.txt =====
1. **Verified inventory — 19 capability packs.** IDs are fixed by `tests/packs/test_pack_layout_contract.py:46-69`: `blender`, `builtin`, `comfy_wrap`, `editorial`, `fal`, `foley`, `generation`, `iteration`, `media`, `moirae`, `reigh`, `rendering`, `runpod`, `stream_content`, `training`, `understanding`, `vibecomfy`, `video_editing`, `youtube`. Current scan: **64 executors, 12 orchestrators, 10 elements, 18 skill files**. Discovery grammar is `core/pack/_common.py:16-24`; canonical roots are `core/pack/validate_layout.py:84-93`.

2. **Database/product packs.** `timeline` owns one table plus stream/events/commands/repository/conformance, CLI and bridge mounts (`astrid/packs/timeline/schema-pack.yaml:12-48`); `shots` owns two tables and nested CLI mount (`shots/schema-pack.yaml:16-51`); `references` owns three tables and nested CLI mount (`references/schema-pack.yaml:17-59`); `runaway` owns one table, command, and repository but no stream/mount (`runaway/schema-pack.yaml:15-35`). Repository evidence: timeline (`timeline/repository.py:1-35`), shots (`shots/repository.py:1-12`), references (`references/repository.py:1-8`), runaway (`runaway/repository.py:1-18`).

3. **Protocol extensions.** `rendering` declares 3 renderers, 3 planners, 2 finalizers (`rendering/pack.yaml:43-58`) and element manifests; path confinement is already mechanically defined (`core/pack/registry.py:260-303`).

4. **Recommended static taxonomy.** Ledger keys:  
   `capability.{executor|orchestrator|element}`, `protocol.{renderer|planner|finalizer}`, `database.{migration|table}`, `vocabulary.{stream|event|command}`, `repository`, `conformance`, `surface.{cli|sdk|bridge}`, `resource`, `documentation`, `alias`, `consumer.{application|doctor|backup|restore|inspect}`.  
   Each row stores `surface_id`, `owner`, `evidence_paths`, and `projection_consumers`; never runtime settings. Discover rows from manifests, descriptors, SQL, and import/callsite scans. Pack ownership requires qualified-id/manifest-root evidence (`core/pack/_common.py:78-92`); kernel ownership requires core declarations (`core/migrations/catalog.py:51-89`, `core/events/registry.py:64-177`). Consumers are projections, not owners (`application.py:163-198`).

5. **Conflict/risk.** Both standard builders independently hard-code only three packs (`packs/__init__.py:68-110`; `core/schema_packs/standard.py:27-45`), while the frozen goal requires four (`.oracle/agent_goal.md:21-25`). `blender` has no structured skill; the skill test is only a non-exhaustive floor (`tests/packs/test_pack_layout_contract.py:353-383`).

**Affected tests:** catalog/migrations, four repository/conformance suites, CLI/SDK domain suites, rendering-extension tests, doctor/backup composition, and wheel closure (`.oracle/agent_goal.md:174-187`).
0
===== .oracle/findings/explore/E6-agent-documentation.txt =====
1. **P0 — frozen-goal conflict: split manifest species remains.**  
   Nineteen bundled `pack.yaml` files are all `schema_version: 1`, `pack_type: capability`, with no `database` or declared documentation block (`astrid/packs/blender/pack.yaml:1-11`; `astrid/packs/stream_content/pack.yaml:1-11`). `timeline`, `shots`, `references`, and `runaway` remain separate `schema-pack.yaml` authorities (`astrid/packs/references/schema-pack.yaml:1-24`; `astrid/packs/runaway/schema-pack.yaml:1-30`). Two duplicate fixed standard builders enumerate only `timeline`, `shots`, `references` (`astrid/packs/__init__.py:68-110`; `astrid/core/schema_packs/standard.py:27-45`). Conflicts with plan §§17, 26, WP1–3.

2. **P0 — documentation census is incomplete.**  
   Among 24 bundled directories: direct `skill/SKILL.md` exists for `_core`, `comfy_wrap`, `editorial`, `fal`, `foley`, `generation`, `iteration`, `media`, `moirae`, `reigh`, `rendering`, `runpod`, `stream_content`, `training`, `understanding`, `vibecomfy`, `video_editing`, `youtube`; absent for `blender`, `builtin`, `timeline`, `shots`, `references`, `runaway`. No pack-level `AGENTS.md` exists. Only nested skill found: `generation.generate_image`. `media/SKILL.md` lacks frontmatter (`astrid/packs/media/skill/SKILL.md:1-10`). Validator only checks explicitly declared docs and component `STAGE.md` (`astrid/core/pack/validate.py:285-291,501-510,636-640`). Conflicts with plan §38/WP2/WP5.

3. **P1 — discovery/status has multiple authorities.**  
   Loader accepts `pack.yaml`, `.yml`, `.json`, and schema-less flat YAML (`astrid/core/pack/_common.py:16-19`; `astrid/core/pack/loader.py:184-216`). Skill discovery independently scans files and skips only deprecated/hidden manifests (`astrid/skills/discovery.py:161-209`). `agent_index.py` separately layers `discover_packs()` and `InstalledPackStore`, reporting README/AGENTS/STAGE—not skills (`astrid/core/pack/agent_index.py:296-319,459-470`). Main CLI explicitly excludes `packs`/`skills` (`astrid/packs/_core/skill/SKILL.md:21-25`); `registry.is_current()` is false.

4. **P1 — current opt-outs are not legitimate manifest opt-outs.**  
   `_core` is a permanent skill-only shell (`astrid/core/pack/validate_layout.py:116-129`). The test suite excludes two “user-owned in-flight” nested docs by hard-coded path (`tests/v10/test_docs_cli_alignment.py:19-22,66-93`); no manifest reason/classification exists. `builtin` is merely `status: deprecated` (`astrid/packs/builtin/pack.yaml:1-18`).

5. **Affected tests and seam.**  
   Legacy gates include `tests/packs/test_pack_layout_contract.py:46-69,308-390`, `tests/packs/test_packs_validate.py:1-10`, `tests/v10/test_registry.py:162-181`, `tests/v10/test_m8_packaging.py:46-74`, and skill tests. Smallest complete seam: make one strict v2 loader/catalog own pack identity, resources, docs, DB projections, and census; replace both standard builders and skill/agent indexes with catalog projections. CI drift gate: enumerate bundled roots, require exactly one v2 `pack.yaml`, reject schema packs/alternate names, require documented opt-out only for internal non-user-facing packs, verify wheel resource closure, and byte-compare generated `_core` census against catalog.
0