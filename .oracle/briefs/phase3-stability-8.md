You are the Phase 3 stability reviser for the Astrid Megado run. Work read-only. Do not edit files, mutate state, create branches, or dispatch models.

Review the COMPLETE Wave-5-revised replacement against the COMPLETE frozen goal and North Star. Verify every accepted Wave 5 correction and its explicit supersession of the Wave 4 pre-use store-state check; strict v2 installed-record behavior; direct-child/docs/Python ownership closure; concrete receipt identity without a snapshot fingerprint; all retained Wave 1–4 contracts; all 15 criteria; every anti-pattern; and internal evidence-reference accuracy for this exact digest. If no material change or exploration is required, answer exactly STABLE and nothing else. Otherwise return a complete corrected replacement plan.

COMPLETE NORTH STAR:

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



COMPLETE FROZEN GOAL:

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



COMPLETE WAVE-5-REVISED PLAN:

# Phase 3 replacement plan — canonical pack beta hard cut

Status: **complete replacement issued for fresh settled-plan review**.

This plan incorporates every accepted Wave 1–5 correction. Wave 5 supersedes Wave 4’s installed-pack pre-use store-state verification. Installed admission is frozen when the top-level operation snapshot is captured; later store mutations affect the next operation. Immediate pre-use verification covers only the captured manifest and resource handles actually consumed.

The plan artifact, mutable Megado status, and any stability judgment remain separate. Any later stability judgment must be recorded in a separate immutable receipt bound to this exact plan digest; this plan neither names that receipt file nor copies its state.

## Determination

- Estimated effort: **5.9–8.2 engineer-weeks**, including cumulative review and rework.
- Huge run: **yes**.
- Difficulty: **5/5**.
- New exploration or research: **none required**.
- New `[XHARD]` implementation work: **none required**.
- Open planning questions: **none**.
- Execution order: immutable baseline → executable v2 contract/catalog → bundled conversion and ownership closure → database hard cut → operational convergence → legacy deletion and packaging preparation → one-build validation and evidence closure.
- Runaway’s absent historical demo is neither restored nor packaged. Preservation uses the deterministic temporary-project fixture in §VII.1.

# I. Mandate and boundaries

Implement one strict canonical pack system:

- Every retained bundled product pack is declared by exactly one `pack.yaml` with integer `schema_version: 2`.
- Delete the empty `builtin` product pack, leaving exactly 22 retained product packs plus irreducible `_core` guidance.
- Every direct directory child of bundled `astrid/packs` except `_core` must be one of those loaded v2 packs. There is no generic bundled non-pack directory category.
- Convert `timeline`, `shots`, `references`, and `runaway` into ordinary packs with optional `database` contributions.
- Preserve typed registries, migration safety, repositories, `DatabaseWriter`, `UnitOfWork`, static application/service/CLI/bridge factories, SDK behavior, the eight-family gateway, and conformance semantics.
- Select standard database composition algorithmically from every trusted bundled catalog entry with `database`; the expected four-pack result is test evidence, never runtime authority.
- Derive bundled trust solely from loader provenance.
- Keep external packs capability-only. Reject an external manifest containing `database` as a whole before resolving resources or reading SQL.
- Hard-cut installed records to strict v2. Pre-v2, incomplete, malformed, or unknown-version records fail closed with an explicit reinstall diagnostic. Add no migration, inferred defaults, raw-manifest trust fallback, or automatic revalidation.
- Freeze installed admission in the immutable top-level operation snapshot. Store mutations after capture affect only a later operation.
- Before executing external pack code, verify only the captured manifest handle and resource handles consumed by the chosen projection.
- Assign every bundled customization and Python module to a canonical pack or explicitly justified kernel owner.
- Package structured documentation for all 22 retained product packs.
- Add no per-project composition state, dependency solver, dynamic database plugin system, marketplace, lifecycle machinery, universal service locator, custom packaging backend, global snapshot fingerprint, cache invalidator, revocation service, operation-wide execution lock, or recursive bundled rescan.
- Do not restore, reconstruct from custody, or package `projects/runaway-piano-colour-demo`. Generate the bounded Runaway project only beneath pytest’s temporary root.

The complete North Star guides implementation but cannot widen the frozen goal.

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
| `RelativeFile` | `RelativePath` resolving to one regular non-symlink file where the resource class is admitted |
| `RelativeDir` | `RelativePath` resolving to one non-symlink directory where the resource class is admitted |
| `NonBlankText` | String whose outer-trimmed value is non-empty |
| `EnvironmentName` | `^[A-Z][A-Z0-9_]*$` |

The executable schema uses normal regex alternation. YAML booleans never satisfy integer fields. Null is never accepted. Optional means absent.

## 2. Top-level fields

Every object uses `additionalProperties: false`, except the two explicitly scoped frozen-JSON maps.

| Field | Required | Type/default | Semantics |
|---|---:|---|---|
| `schema_version` | yes | integer exactly `2` | No numeric string, float, or boolean |
| `id` | yes | `PackId` | Equals the logical owner-directory name supplied by discovery |
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
| `permissions` | no | `Permission[]`, default `[]` | Disclosure/admission data |
| `content` | no | `ContentRoots`, default `{}` | Typed content roots |
| `extensions` | no | `Extensions`, default `{}` | Typed extension declarations |
| `aliases` | no | `Alias[]`, default `[]` | Live aliases only |
| `agent` | no | `AgentRouting`, default empty values | Descriptive routing |
| `documentation` | no | tagged `Documentation` | Mandatory and non-`none` for bundled packs |
| `secrets` | no | `Secret[]`, default `[]` | Install/trust disclosure |
| `dependencies` | no | `RuntimeDependencies`, default empty lists | Runtime disclosure, not pack solving |
| `astrid_version` | no | `ReleaseVersion` | Minimum compatible Astrid release metadata |
| `database` | no | `DatabaseContribution` | Trusted bundled SQLite contribution |
| `resources` | no | `SupplementalResource[]`, default `[]` | Assets not reached by another declaration |
| `authoring_only` | no | `AuthoringExclusion[]`, default `[]` | Source-only, non-wheel classifications |

At least one of `content`, `extensions`, `documentation`, `database`, or `resources` must contribute a non-empty value.

Prohibit v1 fields `origin`, `install_tier`, `pack_type`, `metadata`, and `docs`.

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

Rules:

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

Rules:

- Exact keys: `kind`, `alias`, `canonical_id`.
- `kind` is `executor`, `orchestrator`, `renderer`, `planner`, or `finalizer`.
- Both IDs are distinct `QualifiedId` values whose pack prefix equals the declaring pack ID.
- Duplicate `(kind, alias)` rejects.
- `deprecated` and `deprecation_message` are prohibited.
- Delete all deprecated aliases, including the 49 `builtin.*` aliases and every remaining `external.*` or legacy alias.

V2 aliases cannot serve as compatibility shims.

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
- `none` permits only `kind` plus nonblank `reason`.
- Any bundled candidate using `documentation.kind: none` rejects during bundled admission.
- Bundled admission never consults the audit-only coverage ledger.
- All 22 retained product packs use `skill` or `agents`.
- The frozen goal’s opt-out mechanism remains available in the general grammar for genuinely non-user-facing non-bundled/internal contexts, but is unused by this bundled beta catalog.

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

Only `python`, `npm`, and `system` exist. Each is a duplicate-free list of trimmed `NonBlankText`. They are disclosures and do not participate in dependency solving.

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

Python source is not declared here merely to make it package data. Python ownership is closed separately by §IV.4.

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

Normalization records immutable owner-relative declarations without requiring installed-wheel presence.

Audit semantics:

- Source audit requires every declared path to exist, remain realpath-confined, contain no symlink, avoid runtime-resource overlap, and have a nonblank reason.
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

Migration descriptors appear in strictly increasing version order. A table has one owning pack globally. The migration first creating a table records ownership; later owner-pack migrations may alter it without reclaiming it. The four converted beta packs retain their current single initial migrations and SQL bytes.

YAML never contains columns, indexes, constraints, transformations, checksums, applied state, or a mutable head.

## 4. Normalization and immutable model

One parse produces a manifest-derived `PackDefinition` containing no root, source, trust, install state, manifest path, or raw mapping.

Normalization:

- Strip outer whitespace from prose and disclosure strings.
- Require identifiers in canonical case; never lowercase silently.
- Convert paths to canonical POSIX-relative strings.
- Preserve declared order only for `agent.normal_entrypoints` and migrations.
- Require increasing migration order.
- Reject duplicates and lexically normalize set-like lists.
- Sort mapping keys.
- Recursively freeze arbitrary JSON only in `generation.backends[].init_kwargs` and `extensions.schemas`.
- Make definitions, nested declarations, catalog entries, provenance, resource handles, database projections, admission projections, and snapshots frozen slot-based values.
- Serialize only normalized manifest data; roots and trust are never manifest fields.

```text
CatalogEntry
├── definition: PackDefinition
├── provenance: CatalogProvenance
├── manifest: ResourceHandle
├── resources: tuple[ResourceHandle, ...]
└── authoring_exclusions: tuple[AuthoringExclusion, ...]
```

Resource handles record owner-relative path, resolved root, role/kind, size, and SHA-256. Authoring exclusions remain declarations rather than handles.

Define:

```text
normalized_manifest_digest =
  SHA-256(canonical JSON(normalized PackDefinition))
```

This is distinct from:

- The raw `pack.yaml` resource-handle digest.
- `provenance_identity`.
- Migration checksums.
- Runtime-resource receipts.

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
- Bundled `documentation.kind: none`.
- Absolute, backslash, empty, traversal, symlink, missing, wrong-kind, or duplicate runtime paths.
- Supplemental/typed duplication.
- Source authoring-resource overlap or missing authoring path.
- Authoring-only paths present in a wheel.
- External `database`.
- Missing dependency, capability-only dependency, invalid minimum head, self-dependency, cycle, and duplicate dependency.
- Unordered/duplicate migrations, duplicate table ownership, and non-SQL paths.
- Provenance spoofing.
- Undeclared bundled non-Python files.
- Unowned, multiply owned, or unjustified bundled Python modules.
- Wheel-only/source-only runtime resources or Python modules.
- Legacy-only and canonical-plus-legacy bundled directories.
- Manifestless direct bundled children.
- Strict installed-record failures for pre-v2, missing-field, unknown-field, default-dependent, and unknown-version records.

# III. Catalog construction, provenance, installed admission, and lifetime

## 1. Bundled catalog discovery is closed over direct children

Build one immutable `BundledCatalog` from the source or installed `astrid/packs` package root.

Enumerate every direct child directory in lexical order without following symlinks.

For each child:

1. If its name is `_core`, require it to be the sole explicit non-pack kernel guidance directory. Validate its expected skill/documentation shape separately.
2. Every other direct child is required to be a product pack.
3. Inspect the child root for exact basenames:
   - `pack.yaml`
   - `pack.yml`
   - `pack.json`
   - `schema-pack.yaml`
4. Reject if any legacy basename exists, whether or not `pack.yaml` also exists.
5. Reject if `pack.yaml` is absent.
6. Parse `pack.yaml` exactly once, enforce v2 and owner-directory/ID equality, normalize it, validate mandatory structured documentation, resolve admitted runtime resources, and construct its immutable entry.
7. Reject duplicate IDs or an unloaded direct child.
8. Require the sorted direct-child names excluding `_core` to equal the sorted loaded owner-directory names and loaded pack IDs.

The reviewed final retained set is exactly:

```text
blender
comfy_wrap
editorial
fal
foley
generation
iteration
media
moirae
references
reigh
rendering
runaway
runpod
shots
stream_content
timeline
training
understanding
vibecomfy
video_editing
youtube
```

The runtime catalog does not use this list as an allowlist. WP0 freezes it as the expected beta source-layout audit fixture, and the executable audit compares:

- Direct filesystem children.
- Loaded owner directories.
- Loaded pack IDs.
- Reviewed expected retained names and count.
- Source/wheel child and catalog sets.

A missing, extra, manifestless, legacy-only, duplicate, or unloaded direct child fails.

Cache the bundled catalog once for the process/package-root lifetime. It contains declarations and resource handles only—never connections, repositories, CLI parsers, bridges, capability instances, services, or application objects.

## 2. Root-independent provenance identity

Every parsed candidate receives:

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

Canonical JSON uses sorted keys, no insignificant whitespace, UTF-8, JSON boolean/null rules, and arrays already normalized by the manifest contract.

`declared_paths` includes every path directly declared by:

- `content`.
- Rendering extensions.
- Database migrations.
- Documentation.
- `agent.required_context`.
- Supplemental resources.
- Authoring-only declarations.

It excludes absolute roots, checkout paths, installation paths, discovery order, provenance class, rejected diagnostics, resource bytes, and mutable installation state.

Uses:

- Candidate key: `<pack_id>@<provenance_identity>`.
- Source/wheel comparison requires equal identity plus independent runtime-resource and Python-module comparisons.
- Duplicate handling compares identity and exact resource receipts.
- Diagnostics use the same candidate key.
- External-database rejection can compute identity after normalization and before SQL/resource access.
- Installed v2 admission records bind to this identity.

Two candidates with equal provenance identity but different resource receipts are not identical duplicates.

`CatalogProvenance` contains:

- Provenance class.
- `provenance_identity`.
- `normalized_manifest_digest`.
- Optional diagnostic root/revision details.
- Captured installed admission disposition where applicable.

Manifest fields cannot set or override provenance.

## 3. Dynamic candidate capture and precedence

Each top-level operation captures dynamic candidates once from:

1. Project-local packs.
2. Explicit extra roots in caller order.
3. `ASTRID_PACKS_PATH` roots in environment order.
4. Installed active revisions sorted by pack ID.

Within a root, sort candidates by pack ID and canonical manifest path.

Precedence:

```text
bundled > local > explicit-extra > environment > installed
```

Duplicate policy:

- Bundled IDs are reserved and always win.
- Candidates with the same pack ID, provenance identity, and exact resource receipts deduplicate.
- Same ID with differing identity or receipts produces a `duplicate_id` loser diagnostic containing winner and loser provenance.
- A losing candidate contributes nothing.
- Invalid external discovery may be recorded while other discovery continues, preserving current fault isolation.
- Direct validation or installation of the rejected candidate is a hard error.

Read-only discovery never creates `astrid/packs/local`; only explicit create or fork operations may do so.

## 4. External database fail-closed boundary

After structural normalization and provenance assignment, any non-bundled candidate containing `database` rejects as `external_database_forbidden`.

Rejection occurs before:

- Resource resolution.
- SQL reads.
- Migration projection.
- Capability or alias projection.
- Permission admission.
- Installation publication.

The entire candidate rejects; the database block is never stripped.

Tests cover local, explicit-extra, environment, Git-installed, and installed-revision candidates.

## 5. Strict installed record v2

Replace permissive `InstallRecord.from_dict()` behavior with one exact v2 parser. Unknown keys, missing fields, wrong types, nulls, silent defaults, schema versions other than 2, and legacy records reject.

The v2 record contains exact typed fields:

```text
InstallRecordV2
├── record_schema_version: integer exactly 2
├── pack_id: PackId
├── pack_name: NonBlankText
├── pack_version: ReleaseVersion
├── revision_identity: NonBlankText
├── installed_at: normalized UTC timestamp
├── source: InstalledSource
├── provenance_identity: lowercase SHA-256 hex
├── normalized_manifest_digest: lowercase SHA-256 hex
├── accepted_permissions: tuple[NormalizedPermission, ...]
└── validation: InstalledValidation
```

`InstalledSource` is a strict tagged union:

```text
local:
  kind: local
  diagnostic_origin: NonBlankText

git:
  kind: git
  git_url: NonBlankText
  commit_sha: exactly 40 lowercase hexadecimal characters
  requested_ref: NonBlankText
```

`diagnostic_origin` is informational and never authorizes trust.

`InstalledValidation` has exact fields:

```text
disposition: accepted | rejected
validated_at: normalized UTC timestamp
reason_codes: tuple[LowerIdent, ...]
```

Rules:

- A revision is executable only when its record is exact v2 and `validation.disposition == accepted`.
- Successful installation publishes a fresh accepted v2 record only after canonical validation, external-database rejection, permission acceptance, manifest/resource verification, and staged-copy verification.
- Rejected validation is not published as the active revision. A retained rejected record may be inspectable as history but cannot contribute capabilities.
- Active state remains owned by the store’s active-revision pointer; it is not duplicated by an `active` field in the record.
- `revision_identity` is the store-owned revision identifier and must agree with the selected revision directory.
- `provenance_identity` and `normalized_manifest_digest` must agree with the canonical candidate parsed from that selected revision.
- `accepted_permissions` is the exact normalized permission tuple accepted for that revision and must exactly cover the immutable candidate declaration.
- Remove persisted component inventories, entrypoint summaries, derived secrets/dependencies, raw trust summaries, mutable trust tiers, and other facts that canonical parsing can project.
- Inspect-only source metadata may remain only in the strict `source` union above.
- Remove raw-manifest trust reparsing from installation and discovery.
- Remove old-record field filtering and every missing-field default.
- Pre-v2, incomplete, malformed, or unknown-version records yield deterministic `installed_record_v2_required` / `reinstall_required` diagnostics.
- There is no old-record migration, lazy rewrite, default shim, fallback trust summary, fallback validation, or automatic reinstallation.

Golden external tests always install fresh v2 records.

## 6. Capture-time installed admission

`InstalledPackStore` remains the sole installed-state and admission owner. It emits an immutable `ExternalAdmissionDisposition` while the top-level snapshot is constructed.

```text
ExternalAdmissionDisposition
├── inspectable: bool
├── executable: bool
├── reason_codes: tuple[str, ...]
├── revision_identity: optional str
├── provenance_identity: optional str
├── normalized_manifest_digest: optional str
└── accepted_permissions: tuple[NormalizedPermission, ...]
```

For an installed candidate, the captured admission binding is:

```text
(
  pack_id,
  revision_identity,
  provenance_identity,
  normalized_manifest_digest,
  accepted_permissions,
  validation_disposition
)
```

The store performs one coherent store-owned capture:

1. Resolve the active revision.
2. Strictly parse its v2 record.
3. Confirm record pack/revision identity.
4. Canonically load the candidate once.
5. Confirm record provenance identity equals candidate provenance identity.
6. Confirm record normalized manifest digest equals the canonical definition digest.
7. Confirm accepted permissions exactly cover the candidate’s normalized permission declaration.
8. Confirm validation disposition is accepted.
9. Confirm the candidate has no `database`.
10. Capture the manifest handle and admitted resource handles.

The store may use its existing narrow per-pack synchronization to obtain a coherent read while capturing these facts. No lock is retained after snapshot construction and no lock is held across pack execution.

Source policy:

| Source | Inspect | Capability execution | Database |
|---|---:|---:|---:|
| bundled | yes | yes | yes |
| local | yes | yes | no |
| explicit extra | yes | yes | no |
| environment | yes | no | no |
| installed | yes | only when capture-time v2 admission succeeds | no |

An installed pack declaring no permissions requires an exact empty accepted-permission tuple.

Missing or mismatched evidence produces inspect-only disposition with deterministic reason codes. It never falls back to executable.

Every external capability consumer—executor, orchestrator, rendering, generation, SDK, or other registry—uses this single captured projection. Consumers do not reparse manifests or implement another trust policy.

## 7. Superseded Wave 4 behavior: no pre-use store-state check

After snapshot capture:

- The selected installed revision remains admitted for that operation lifetime.
- Activation, rollback, invalidation, record replacement, or permission-receipt changes affect the next top-level operation.
- Current execution does not reread the active pointer or install record.
- Current execution does not switch revisions or update its admission disposition.
- No store check is inserted immediately before capability invocation.
- No lock spans capability execution.
- No revocation service, retry, rediscovery, snapshot replacement, or alternate-revision selection is added.

Immediately before external capability execution, verify only:

1. The captured raw manifest `ResourceHandle`.
2. The captured resource handles consumed by the selected capability projection.

A missing, changed, wrong-size, or wrong-digest captured manifest/resource fails closed before pack code runs.

Store-only mutations after capture do not invalidate the current operation’s admitted capability. Physical mutation/removal of the captured manifest or consumed resources does fail the handle check.

Required concurrency/lifetime tests:

- Capture revision A, activate B, and prove the existing operation still selects A.
- A later operation sees B.
- Capture A, mark its store record invalid/rejected, and prove the existing operation still selects A when captured files are intact.
- A later operation refuses A.
- Capture A, replace its accepted-permission record, and prove the existing operation retains its captured admission.
- A later operation evaluates the replacement record.
- Change the captured manifest after capture and prove use fails closed.
- Change or delete a consumed resource after capture and prove use fails closed.
- Mutate an unconsumed external resource and prove no broad rescan occurs.
- Prove no execution path rereads store admission state, retries, or switches revisions.

## 8. Snapshot construction

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
- No whole-snapshot identity.
- No hashing of rejected diagnostics.
- No global layer-order hash.
- No retry-on-change system.
- No general stale-handle scan.

`construction_context` is diagnostic-only and may retain local roots/order. It is excluded from source/wheel semantic comparison and operation-receipt identity.

## 9. Lifetime and freshness contract

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

Consumers cannot rescan or reconstruct a snapshot internally. Convenience APIs create one only at a top-level boundary. Registries accept the snapshot or narrow typed projections.

Bundled lifetime:

- Bundled catalog is immutable for the process/package-root lifetime.
- Production performs no recursive rescan, cache invalidation, global fingerprint comparison, or broad stale-handle verification.
- Changing bundled files requires a new process/catalog lifetime.
- Tests mutating fixtures explicitly end the old lifetime and use a narrow test factory/cache-clear seam.
- Migration checksum verification remains existing database safety, not catalog freshness machinery.

Dynamic external lifetime:

- Candidates and installed admission are captured once per top-level operation.
- External manifest and resource handles retain captured size/digest receipts.
- Security-sensitive use verifies the captured manifest and only the consumed resource handles.
- Installation verifies the manifest and all admitted resource handles before publication.
- Direct resource validation verifies the handles it consumes.
- A handle mismatch fails closed without retry, rediscovery, snapshot update, or candidate replacement.
- Inspection-only operations do not perform broad resource reverification.
- External filesystem changes become visible to later operations.
- Installed store-state changes become authoritative to later operations.

# IV. Bundled resource and Python ownership closure

## 1. Exact inventory exclusions

Walk each bundled source pack deterministically without following symlinks. Reject every symlink before classification.

There is no generic cache/build exclusion and no skipped subtree.

Python source is handled separately:

- Regular files ending exactly in `.py` enter the Python ownership audit in §IV.4.
- They are excluded from non-Python package-data equality.
- Other Python/runtime artifacts are not covered by this exclusion.

The only audit-noise allowlist is:

1. A regular file whose exact basename is `.DS_Store`.
2. A regular file whose owner-relative path matches:

```regex
(?:^|/)__pycache__/[^/]+\.py[co]$
```

Rules:

- No directory is skipped wholesale.
- A non-bytecode file under `__pycache__` is inventoried normally.
- `.pyc` or `.pyo` outside an immediate `__pycache__` is inventoried normally.
- `.gitignore`, `.gitkeep`, generated output, build directories, test data, editor metadata, requirements, services, templates, schemas, docs, fonts, and all other files are not implicitly excluded.
- Intentional source-only content uses `authoring_only`.
- Unexpected cache/build artifacts fail as undeclared or prohibited content.

Every remaining regular non-Python file must have exactly one classification:

- Typed runtime reachability.
- Supplemental runtime declaration.
- Authoring-only declaration.

Zero classifications is `undeclared_file`; multiple classifications is `duplicate_classification`.

## 2. Typed resource reachability

- Executor, orchestrator, and element roots use existing typed validators instead of claiming directories blindly.
- Component manifests, schema-declared paths, `STAGE.md`, assets, and documentation routes create resource edges.
- Schema, example, and documentation roots recursively classify files.
- Renderer, planner, and finalizer declarations classify their manifests and typed path fields.
- Migration paths classify SQL.
- Documentation and `agent.required_context` classify documents.
- Supplemental directories expand recursively.
- Nested skills, requirements, templates, services, and opaque assets must be reached through typed or supplemental declarations.
- Empty runtime-resource directories reject.
- Each physical file may be reached by exactly one declaration path.

## 3. Targeted runtime-use audit

Scan runtime Python below bundled pack roots.

Recognize:

- `open`.
- `Path.open`, `read_text`, and `read_bytes`.
- `importlib.resources.files`, `open_text`, and `open_binary`.
- `pkgutil.get_data`.
- Simple literal `Path(__file__)` and `__file__` composition using `/`, `joinpath`, `with_name`, and `parent`.
- Existing executor requirements-file probing.
- Blender service-unit lookup.
- Existing typed component and rendering resource APIs.

Use only intra-module propagation of simple literal assignments. Do not attempt general analysis of generated paths, project paths, user input, or network resources.

Every statically resolvable pack-relative runtime read must enter runtime-resource closure. A resolvable cross-root read must move into its owner or resolve through a justified kernel-owned resource recorded in the coverage ledger.

Migration SQL, component manifests, `STAGE.md`, `SKILL.md`, `requirements*.txt`, referenced schemas/templates, services, and runtime assets cannot be authoring-only.

## 4. Complete Python ownership audit

Python remains governed by ordinary module packaging, not the non-Python `resources` grammar.

The coverage inventory enumerates every `.py` file beneath every retained bundled pack root and derives its canonical module name. Each module must have:

- Exactly one physical owner, determined by its pack root.
- Exactly one justified ownership route.
- Source and installed-wheel import-origin evidence.

Valid ownership routes are:

1. The module lies beneath a manifest-declared typed `content` subtree.
2. The module implements a manifest-declared typed extension whose canonical registry/module mapping points to it.
3. The module implements a manifest-declared database surface—repository, command, vocabulary, conformance, CLI, or bridge—proven by exact registry/import/AST evidence.
4. It is an exact `__init__.py` package-initialization module with a recorded, nonblank initialization role and no independent unclassified customization.

Rules:

- Directory location alone establishes physical ownership but not contribution reachability.
- Wildcard “all Python in this pack” claims are invalid.
- A module reachable through more than one conflicting contribution route fails as multiply owned.
- A module with no route fails as unclassified.
- A package initializer containing substantive registrations or behavior must be mapped to those declared surfaces; the initializer exception cannot hide customization.
- Pack-local test or development Python that is not a shipped contribution must move to the normal test tree rather than being smuggled through package initialization.
- No Python file is added to `resources` solely to satisfy package-data closure.
- Installed-wheel validation compares the logical bundled module set and proves imported module origins lie beneath the isolated wheel environment.
- Any source module absent from the wheel, unexpected wheel-only module, source-origin import, multiply owned module, or unclassified module fails.

Coverage adds:

```text
python_module:<pack_id>/<canonical_module_name>
```

with exact source path, ownership route, manifest surface IDs, consumers, and installed origin evidence.

## 5. Source/wheel equality

Each non-Python audit emits sorted resource records:

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

- Direct bundled child sets.
- Loaded pack IDs.
- `provenance_identity`.
- `normalized_manifest_digest`.
- Normalized definitions, including authoring-only declarations.
- Runtime-resource paths, roles, sizes, and hashes.
- Database declarations and derived heads.
- Documentation routes.
- Bundled provenance class.
- Logical bundled Python module sets.

Also require:

- Every source authoring-only path exists.
- No authoring-only path exists in the wheel.
- No undeclared non-Python bundled file exists.
- Every bundled Python module has one valid ownership route.
- Every installed bundled Python import resolves beneath the isolated wheel.
- Absolute roots are never compared.

Use existing setuptools package-data and normal Python module packaging. Add no packaging backend.

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

Runtime never imports these artifacts. Bundled admission never consults them.

Inventory inputs:

- Direct bundled child census.
- Canonical bundled snapshot.
- Typed executor, orchestrator, element, renderer, planner, and finalizer projections.
- Canonical database projection.
- Runtime-resource closure.
- Complete bundled Python module inventory and ownership graph.
- Structured documentation routes.
- Code-declared kernel migration, vocabulary, and repository constants.
- Exact AST inspection of application composition, SDK surfaces, product/operational CLI declarations, bridge mounts, doctor, backup, restore, inspect, package audit, and census generation.

Do not use the ledger to discover inventory and do not broadly grep arbitrary prose.

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
python_module:<pack_id>/<canonical module>
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
- Python physical owner is derived from its pack root; the ledger supplies exact contribution reachability evidence, not an alternate owner.
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
- `unclassified_python_module`
- `multiply_owned_python_module`
- `unreachable_python_module`
- `unexpected_owner`
- `bundled_child_mismatch`
- `unloaded_bundled_child`

Boundary diffs record added, removed, changed-owner, changed-evidence, changed-consumer, changed-resource-digest, and changed-Python-module sets. Every non-empty category requires review.

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
- Every minimum is positive and no greater than target head.
- The graph is acyclic.
- Existing table, migration identity/name, vocabulary, repository, CLI, bridge, and other collision checks pass.

## 3. Expected bundled fixture and ordering

Converted manifests are expected to project:

```text
core@1
├── references@1  requires core >= 1
├── runaway@1     requires core >= 1
├── shots@1       requires core >= 1
└── timeline@1    requires core >= 1
```

This is fixture evidence, not composition authority.

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

Maintain a four-pack preservation matrix for timeline, shots, references, and runaway across:

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

Runaway entries:

- Migration: `runaway/1`, one owned `runaway_transitions` table.
- Repository: `RunawayRepository`.
- Command: `runaway.create`, including receipt replay/mismatch behavior.
- Conformance: `writer_ownership` and `crash_atomicity`.
- Streams: `N/A — Runaway declares no pack-owned stream type`.
- Events: `N/A — Runaway declares no pack-owned event kind`; kernel run/evidence events are not Runaway-owned.
- CLI: `N/A — Runaway declares no CLI mount`.
- SDK: `N/A — Runaway has no dedicated public SDK facade`; standard `AstridClient` composition is operational-consumer proof, not invented API.
- Bridge: `N/A — Runaway declares no bridge mount`.

## 1. Deterministic Runaway temporary-project fixture

Use:

```text
tests/packs/test_runaway_canonical_roundtrip.py
fixture: generated_runaway_project
test: test_generated_temporary_project_round_trip
```

The fixture:

1. Creates a fresh pytest-owned temporary projects root outside bundled pack roots.
2. Uses fixed slug `runaway-roundtrip` and stable logical project/run identifiers.
3. Uses fixed clock/input values or excludes nondeterministic timestamps from semantic comparison.
4. Creates a small fixed transition payload in memory or beneath the temporary project:
   - Unique contiguous ordinals.
   - Fixed start/duration values.
   - Fixed nonblank prompts.
   - Fixed metadata.
   - No external media or historical demo input.
5. Opens through the canonical standard application/snapshot path, producing:

```text
core/1
references/1
runaway/1
shots/1
timeline/1
```

6. Creates the kernel project and run through sanctioned application/repository seams.
7. Exercises:
   - `RunawayRepository.create`.
   - Ordered list, show, and ordinal lookup.
   - `runaway.create` command receipt.
   - Identical idempotent replay.
   - Mismatched replay rejection.
   - FK/writer ownership.
   - Transaction/crash atomicity.
8. Reopens through the standard client/database path and proves transitions and migration rows round-trip unchanged.
9. Records the explicit N/A reasons above.
10. Relies on ordinary pytest cleanup and adds nothing to source or wheel.

The fixture must not import, probe, restore, synthesize from, or assert the existence of:

```text
projects/runaway-piano-colour-demo
```

Demo-dependent tests are rewritten around the generated payload or deleted where they only test missing historical content. Prompt unit tests keep small in-memory cases without recreating the missing 566-transition demo.

## 2. Concrete operation-receipt identity

No receipt records a snapshot fingerprint or undefined snapshot identity.

Every operation receipt that must bind execution to canonical inputs records an ordered `selected_provenance` sequence. Each selected entry contains:

```text
pack_id
pack_version
provenance_class
provenance_identity
normalized_manifest_digest
revision_identity  # null for non-installed entries
```

Ordering is the exact canonical selected-entry order used by that operation.

Receipts additionally record ordered consumed identities:

```text
consumed_migrations:
  pack_id
  pack_version
  migration_version
  migration_name
  owner_relative_path
  resource_sha256
  migration_checksum

consumed_resources:
  pack_id
  pack_version
  owner_relative_path
  role
  size
  sha256
```

Rules:

- Include only selected provenance relevant to the operation.
- Include only migrations/resources actually consumed or verified for that proof.
- Preserve semantic operation order.
- Do not serialize rejected candidates.
- Do not hash or serialize global layer ordering.
- Do not include diagnostic construction context.
- Do not invent a whole-snapshot fingerprint.

## 3. Runaway receipt

Authoritative path:

```text
.oracle/evidence/canonical-pack/final/runaway-roundtrip.json
```

Schema:

```text
astrid.canonical_pack.runaway_roundtrip.v1
```

It records:

- Fixture/test identifier.
- `generated_temporary_project: true`.
- `historical_demo_restored: false`.
- `historical_demo_packaged: false`.
- Exact focused command and exit code.
- Source or installed-wheel mode and Astrid origin.
- Temporary root used for the run.
- Normalized fixed input and SHA-256.
- Ordered selected provenance records from §VII.2.
- Ordered applied migration identities, resource digests, and migration checksums.
- Any additional consumed resource identities.
- Project/run identifiers.
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

The test writes only when `ASTRID_RUNAWAY_RECEIPT` is supplied. Ordinary test runs remain artifact-free. The final evidence command runs once; the full suite may later execute the test normally without rewriting the receipt.

# VIII. Work packages

## WP0 — immutable baseline and ownership reconciliation

Estimate: **0.45–0.65 week**.

- Verify source `7ac50c12e8e4d90988fee603ffdb9896e5628792`.
- Capture 19 capability manifests, four schema manifests, `_core`, 64 executors, 12 orchestrators, 10 elements, eight rendering extensions, four database packs, and 18 existing skills.
- Record the 24 current direct directories: `_core`, 23 product directories, `builtin` deletion, and the reviewed final 22-pack set.
- Inventory every customization, Python module, non-Python resource, and initial owner.
- Record all deprecated aliases as intended deletions.
- Capture installed-record v1 behavior and every callsite currently depending on permissive/defaulted fields, solely as deletion evidence.
- Capture database ordering, migration identities/checksums, open behavior, repositories, vocabulary, CLI/SDK/bridge behavior, doctor, backup, restore, and wheel behavior.
- Seed the four-pack preservation matrix and 15-criterion evidence matrix.
- Freeze the exact audit-noise allowlist from §IV.1; executors cannot expand it without reopening the plan.
- Record the missing historical Runaway demo as absent baseline evidence and freeze the generated fixture as its only replacement gate.
- Explicitly forbid restoring or packaging that demo.
- Do not build a wheel or run the full suite.

Exit: every baseline surface and Python module is pack-owned, kernel-owned, intended deletion, or an explicitly justified Runaway N/A; the final direct-child set is reviewed.

## WP1 — contract, immutable model, catalog, v2 installed admission, and audit tools

Estimate: **1.25–1.7 weeks**. Depends on WP0.

Contract-freeze subgate:

- Land the exact v2 manifest schema and immutable normalized types.
- Land golden and invalid fixtures.
- Land provenance, manifest digest, resource, authoring-exclusion, admission, and strict installed-record types.
- Prove source versus wheel authoring semantics.
- Prove manifestless, legacy-only, and canonical-plus-legacy direct-child failures.
- Prove bundled `documentation.kind: none` rejection without ledger access.
- Pass schema and normalization tests.
- Obtain cumulative review before conversion.

Then:

- Evolve `PackDefinition`; do not create a parallel product model.
- Implement the sole v2 loader.
- Delete fallback parsing from the new path.
- Implement confined digest-carrying runtime-resource handles.
- Implement process/package-lifetime `BundledCatalog`.
- Enforce closed direct-child discovery with `_core` as the only exception.
- Implement candidate capture and `CatalogSnapshot` without fingerprint machinery.
- Implement deterministic precedence, duplicates, provenance, and external-database rejection.
- Replace permissive install records with strict `InstallRecordV2`.
- Remove raw-manifest trust reparsing and old-record defaults.
- Make `InstalledPackStore` emit one capture-time admission projection.
- Route all external capability projections through that disposition.
- Implement narrow pre-use manifest/consumed-resource verification.
- Do not implement the superseded pre-use store-state verification.
- Prove current-operation freezing and later-operation visibility for activation, invalidation, and permission-record mutations.
- Prove changed captured manifest/resource failure.
- Make local pack creation emit strict capability-only v2.
- Implement bounded non-Python classification, targeted resource-use audit, and full Python ownership audit.
- Implement coverage tooling.
- Adapt registries to accept snapshot projections.

Exit: contract, catalog, lifetime, strict installed records, capture-time admission, resource closure, Python ownership, and coverage tooling are fixture-proven.

## WP2 — bundled conversion, ownership, resources, and documentation

Estimate: **1.0–1.35 weeks**. Depends on WP1.

- Convert all 22 retained packs.
- Fold four schema manifests into `database`.
- Preserve migration bytes and behavior declarations.
- Make references the combined exemplar without changing its three-table model or semantics.
- Delete `builtin` and deprecated aliases.
- Add missing direct skills and repair media.
- Require non-`none` documentation for all 22 packs.
- Classify every bundled non-Python source file.
- Map every bundled Python module to a typed contribution or exact initialization role.
- Explicitly declare requirements, Blender service unit, templates, schemas, nested skills, fonts, SQL, and runtime assets.
- Move pack-owned cross-root assets to their owner; justify true kernel assets.
- Switch bundled discovery to v2.
- Regenerate capability/census output.
- Add the generated Runaway fixture without adding historical demo resources.

Boundary A:

- Generate inventory/check/diff.
- Prove the exact 22-name direct-child, loaded-directory, and loaded-ID sets agree.
- Prove no `schema-pack.yaml`, alternate manifest, manifestless child, or unloaded child remains.
- Prove all 22 documentation declarations and packaged paths.
- Prove source resource classification, authoring exclusions, and Python ownership.
- Prove missing Runaway demo is absent from source and package-data inputs.
- Review contract, lifetime, provenance, strict installed records, capture-time admission, documentation, resources, Python ownership, and overall ownership cumulatively.
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
  - Read-only pending Runaway without mutation.
  - Existing four-pack no-op.
  - Collisions.
  - Missing/self/duplicate dependencies.
  - Cycles.
  - Minimum-head failures.
  - Checksum/name drift.
  - Transaction rollback.
  - Unknown/too-new applied rows.
  - External database rejection for every provenance class.
  - Generated Runaway temporary-project migration and reopen.

Boundary B:

- Generate inventory/check/diff.
- Regenerate the four-pack matrix, including Runaway N/A reasons.
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

- `open_database(path, registry)` as SQLite seam.
- `DatabaseWriter` and its exclusive-owner lock.
- `UnitOfWork`.
- Static repository/service/CLI/bridge factories.
- Backup/restore payload semantics.
- Eight-family CLI gateway and two nested mounts.

Raw database reads use the shared compatibility probe or an already-probed connection.

Every installed execution route must:

1. Select only from the snapshot’s captured executable admission projection.
2. Verify the captured manifest and resources consumed by that projection.
3. Invoke captured pack code without rereading store admission state.

No executor, SDK facade, rendering path, or registry may implement a second admission policy, refresh store state, or switch revisions.

`python3 -m astrid.core.pack.cli inspect <id> [--json]` exposes normalized identity, provenance class/identity, normalized manifest digest, captured admission disposition, installed revision identity where applicable, contribution categories, database dependencies/migrations/tables/head, documentation, runtime-resource closure, and relevant rejection/handle diagnostics.

Inspect reports captured state and does not refresh it. JSON uses a versioned envelope and sorted arrays; text renders from the same DTO.

Doctor reports canonical census, catalog/resource/documentation/Python ownership health, strict installed-record diagnostics, and expected/applied/pending migrations by owner without mutation.

Exit: all operational consumers agree on one snapshot; none reparses identity, rescans, re-evaluates installed admission after capture, or bypasses manifest/resource verification.

## WP5 — deletion, final gates, and packaging preparation

Estimate: **0.8–1.15 weeks**. Depends on WP4.

Delete:

- All `schema-pack.yaml`.
- Schema-pack parser, model, discovery, builders, standard lists, and compatibility exports.
- V1 pack parsing and flat/schema-less loading.
- Alternate filename probes.
- Manifest-supplied trust handling.
- Raw identity readers.
- Raw-manifest installed trust reparsing.
- Permissive `InstallRecord.from_dict()` field filtering/defaults.
- Pre-v2 record migration/revalidation paths.
- Independent pack/skill inventories.
- Deprecated aliases and compatibility tests/docs.
- Fixed database tuples and name-based selection.
- Legacy-format audit support.
- Snapshot fingerprint or general stale-snapshot machinery introduced during implementation.
- Any Wave 4-style pre-use store recheck, lock-across-execution, or immediate-revocation machinery.
- Historical Runaway-demo assertions and tests depending only on absent content.

Retain exact gates for:

- Prohibited paths and retired symbols.
- Fixed composition tuples.
- Raw identity reconstruction.
- Independent rescans.
- Divergent external admission.
- Store rereads after snapshot capture.
- Retry or replacement-revision selection.
- Pre-v2/defaulted installed records.
- Direct-child/catalog set mismatch.
- Bundled documentation opt-outs.
- Coverage and Python ownership.
- Behavior matrix.
- Targeted resource use.
- Census drift.
- Source/wheel closure.
- Absence of the historical Runaway demo.
- Presence and deterministic behavior of the generated fixture.

Packaging:

- Extend ordinary package-data patterns for every runtime-resource kind.
- Include all manifests, SQL, skills/docs, requirements, services, schemas, templates, fonts, and runtime assets.
- Package Python through ordinary module packaging.
- Exclude authoring-only paths.
- Include neither generated Runaway fixture data nor historical demo content.
- Add no custom backend.
- Convert wheel-building tests into source contracts, mocked builder units, or consumers of `ASTRID_PREBUILT_WHEEL`.
- Add `InstalledArtifactHarness.from_wheel(path, ...)`.
- Ensure every current `build_once` callsite consumes the prebuilt wheel when set.
- Keep `build_once` only as optional developer convenience; authoritative validation cannot invoke it.

Boundary C:

- Generate inventory/check/diff.
- Run source package-data, authoring-exclusion, Python ownership, documentation, and direct-child checks without building.
- Regenerate final matrix candidate.
- Review convergence, deletion, admission freezing, strict records, Runaway fixture, resource/Python closure, packaging, and build-call graph.
- Prove authoritative validation has exactly one build invocation.
- Resolve findings before WP6.

## WP6 — one-build validation and evidence closure

Estimate: **0.5–0.7 week**. Depends on Boundary C.

One authoritative owner runs:

```bash
python3 -m build --outdir .oracle/evidence/final-build
```

Require exactly one wheel, record SHA-256, and set:

```bash
ASTRID_PREBUILT_WHEEL=<absolute-wheel-path>
```

No later command may invoke `python -m build`, `build_once`, `pip wheel`, or another source build.

Run:

```bash
python3 -m pytest tests/packs tests/v10/test_catalog_migrations.py \
  tests/v10/test_m8_packaging.py tests/v10/test_pack_factoring.py \
  tests/v10/test_reference_repository.py tests/sdk/test_references.py \
  tests/sdk/test_extended_composition.py
```

Run the Runaway receipt command exactly once:

```bash
ASTRID_RUNAWAY_RECEIPT="$PWD/.oracle/evidence/canonical-pack/final/runaway-roundtrip.json" \
python3 -m pytest -q \
  tests/packs/test_runaway_canonical_roundtrip.py::test_generated_temporary_project_round_trip
```

Run:

```bash
python3 -m astrid doctor
```

Using the same wheel, run:

- Installed bundled-catalog load.
- Exact direct-child/catalog-set audit.
- Source/wheel normalized-definition and provenance comparison.
- Bidirectional runtime-resource audit.
- Logical Python-module-set and import-origin audit.
- Source authoring-path presence and wheel absence.
- Documentation and `_core` census audit.
- Fresh, upgraded, read-only-pending, and existing SQLite scenarios.
- External capability success and external database rejection for every source class.
- Fresh strict-v2 installed capability execution success.
- Pre-v2, incomplete, malformed, default-dependent, and unknown-version record failures with reinstall diagnostics.
- Installed inactive, rejected-validation, identity-mismatched, digest-mismatched, and permission-mismatched inspect-only behavior at capture.
- Post-capture active-revision switch: current operation remains on captured revision; later operation sees replacement.
- Post-capture invalidation or permission-record replacement: current operation retains captured admission; later operation re-evaluates and fails or changes disposition.
- Captured manifest mutation failure.
- Consumed-resource mutation/removal failure.
- Proof that no post-capture store read, retry, snapshot replacement, lock-across-execution, or alternate revision execution occurs.
- References round trip.
- Generated Runaway round trip and receipt.
- Proof historical Runaway demo was neither restored nor packaged.
- Backup/restore.
- Inspect text/JSON.
- Doctor/inspect non-mutation.
- Exact legacy gates.
- Zero-unclassified resource, Python, documentation, and customization coverage.

Then run once:

```bash
python3 -m pytest
```

# IX. Executable clean-wheel isolation contract

The installed-artifact harness must:

1. Create a temporary virtual environment outside the checkout and all source pack roots.
2. Install the single prebuilt wheel without editable/source installation.
3. Launch that environment’s Python from outside the checkout.
4. Invoke Python with `-I -P`.
5. Set `PYTHONNOUSERSITE=1`.
6. Remove `PYTHONPATH` and source-path injection variables.
7. Assert checkout and source pack roots are absent from normalized `sys.path`.
8. Assert `astrid.__file__`, every imported Astrid module, catalog manifest, and `importlib.resources` origin lies beneath isolated site-packages.
9. Fail if any origin resolves beneath the checkout, a source pack root, or ambient Astrid installation.
10. Compare logical bundled Python module sets and import representative or registry-reachable modules from every pack.
11. Run catalog, docs/census, migration-resource, strict installed-record, and closure checks only after origin assertions pass.

The harness receipt records:

- Wheel path and SHA-256.
- Environment root.
- Python executable and flags.
- Working directory.
- Normalized `sys.path`.
- Astrid module origin.
- Audited Python module origins.
- Every audited manifest/resource origin.
- Ordered selected provenance and consumed resource/migration identities where applicable.
- Exit status.

A passing source import never counts as wheel evidence.

# X. Baseline-independence receipt contract

If the final full suite exposes an apparently unrelated failure, do not run a second baseline full suite and do not rebuild the wheel.

Reproduce only the focused failing scenario against the pinned source. Record:

- Exact pinned source revision.
- Verification that the baseline tree contains that revision and no test-affecting edits.
- Final branch revision.
- OS, architecture, Python version, dependency/environment receipt, and relevant normalized environment variables.
- Exact focused command or node IDs.
- Working directory and project/test temporary-root configuration.
- Exit code.
- Full failure signature and relevant output for baseline and final.
- Controlled before/after table under the same environment.
- Comparison of exception type, assertion, and normalized failure signature.
- Confirmation that no baseline wheel build or baseline full suite occurred.

Classify a failure as pre-existing only when the focused pinned-source run reproduces materially the same failure. Otherwise criterion 14 remains failed and implementation continues.

The absent historical Runaway demo is baseline evidence, not a failure waiver. Final acceptance comes only from the generated fixture and receipt.

# XI. Final artifacts

Final closure produces:

- One wheel and SHA-256.
- Installed isolation and module/resource-origin evidence.
- Direct-child/catalog-set audit.
- Coverage inventory/check/diff.
- Runtime-resource source/wheel comparison.
- Python ownership and source/wheel module-origin audit.
- Authoring-only source/wheel audit.
- Documentation and census audit.
- Four-pack preservation matrix.
- Runaway temporary-project receipt.
- Proof the historical demo is absent from source additions and wheel.
- Fifteen-row evidence matrix.
- Focused and full-suite receipts.
- Doctor and inspect receipts.
- External admission matrix covering strict records, capture-time freezing, later-operation visibility, handle mutation, and unchanged success.
- Exact legacy/deletion-gate receipt.
- Any baseline-independence receipts.
- Independent reviewer dispositions.

After all evidence passes:

- Obtain final Sol oracle review.
- Record any stability result only in a separate immutable stability receipt bound to this plan digest, without modifying this plan.
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

Focused checks may run during implementation. Immutable cumulative artifacts are generated only at defined boundaries.

The plan artifact, current run status, and stability judgment remain separate:

- This plan owns executable intent.
- `.oracle/status.md` owns the current Megado phase.
- A separate immutable receipt owns any stability judgment over this exact plan digest.

# XIII. Criterion traceability

| Criterion | Primary proof |
|---|---|
| 1. Strict v2 bundled packs | WP1–WP2, closed direct-child discovery, Boundary A, final legacy gates |
| 2. No independent identity parsing | Catalog/snapshot invariant, WP4–WP6 |
| 3. Zero-unclassified ledger | Resource and Python ownership audits at every boundary |
| 4. Manifest-derived database composition | WP3 synthetic bundled-database test |
| 5. Four-pack semantics preserved | Preservation matrix and Runaway receipt |
| 6. Owner-relative migrations and safety | WP3 SQLite matrix and ordered migration identities |
| 7. Operational agreement | WP4 snapshot threading and Boundary C |
| 8. Structured docs and `_core` census | All-22 admission rule, WP2, wheel audit |
| 9. Inspect and doctor | WP4, Boundary C, final |
| 10. Clean-wheel closure | Isolated wheel harness, resource and Python-origin audits |
| 11. Legacy deletion | Exact path/import/AST/record gates |
| 12. External capability/database policy | Strict v2 records, capture-time admission, handle checks, later-operation semantics |
| 13. Golden forms | WP1 and final |
| 14. Focused/full validation | WP6 one-build flow and receipt contracts |
| 15. Evidence matrix and oracle | WP6 closure and separate stability receipt |

# XIV. Explicit North Star anti-pattern rejection

- **No hidden schema-pack subsystem:** schema-pack identity, parser, discovery, builders, lists, exports, and manifests are deleted.
- **No universal service locator:** catalog supplies immutable definitions and typed projections; typed registries and static factories retain construction ownership.
- **No duplicated DDL or mutable facts:** YAML and documentation contain no columns, constraints, indexes, transformations, checksums, applied rows, mutable heads, or mutable admission state.
- **No project-composition machinery:** no pack locks, enable/disable/purge system, database-aware uninstall, or dynamic database plugin framework.
- **No external SQL:** non-bundled `database` rejects before resources or SQL are read.
- **No unloadable kernel:** synthetic `core` and `_core` remain irreducible.
- **No compatibility forms:** no v1 manifests, alternate filenames, schema-less loading, schema packs, deprecated aliases, dual reads, old-record migration, missing-field defaults, or revalidation fallback.
- **No silent bundled disappearance:** every direct bundled child except `_core` must load as one v2 pack.
- **No documentation bypass:** all 22 product packs have direct packaged structured documentation; bundled `none` rejects.
- **No Python ownership gap:** every bundled Python module has one pack owner and one exact typed contribution or initialization justification.
- **No premature success:** completion is impossible while any customization, Python module, documentation surface, operational consumer, resource, trust decision, or database projection bypasses canonical ownership.

Additional rejections:

- No fixed-composition disguise.
- No runtime coverage ledger.
- No manifest-supplied trust.
- No operation-internal discovery.
- No contribution from losing candidates.
- No snapshot fingerprint or whole-snapshot receipt identity.
- No rejected-diagnostic hash.
- No retry-on-change.
- No bundled cache invalidator or recursive per-operation rescan.
- No pre-use installed-state reread.
- No lock across capability execution.
- No immediate revocation service.
- No alternate revision selection after capture.
- No newly activated revision entering an existing operation.
- No second admission service.
- No capability-specific permission policy.
- No raw-manifest trust parsing.
- No permissive or migrated pre-v2 installed records.
- No general static-analysis ambition.
- No runtime asset hidden as authoring-only.
- No Python declared as package data merely to close ownership.
- No broad cache/build exclusion.
- No relaxed wheel grammar.
- No dependency solver, marketplace, signing, sandboxing, remote activation, or UI.
- No generalized dynamic factory framework.
- No custom packaging backend.
- No broad repository-wide regex scanner.
- No repeated wheel build or second baseline full suite.
- No repeated immutable boundary artifacts.
- No restoration or packaging of the historical Runaway demo.
- No invented Runaway stream, event, CLI, SDK, or bridge surface.
- No unrelated model, LoRA, taxonomy, or kernel migration.
- No receipt bound to an invented snapshot fingerprint.
- No stability state embedded in this plan.

This replacement advances the complete North Star strictly within the frozen goal. It requires **no new exploration lane** and **no `[XHARD]` work**.
