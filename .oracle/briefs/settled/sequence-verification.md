# Settled-plan wave 1 — sequence-verification

You are an independent GPT-5.6 Luna plan critic. Work read-only. Do not edit
files, run mutating commands, create branches, dispatch models, widen scope, or
redesign the plan.

## Lens

Challenge batch dependencies, synchronization seams, cumulative gates, and validation proportionality. Find unsafe ordering, stale-state risks, redundant ceremony, missing proof, or expensive checks that can be made cheaper without weakening the frozen criteria. Do not rewrite the plan.

## Output contract

Identify and rank only concrete simplifications or material plan defects, with
plan-section or source evidence. For each, state ACCEPT-CANDIDATE, REJECT-AS-
UNSAFE, or INVESTIGATE and why. Check every frozen criterion and provide an
explicit North Star alignment disposition. If no material simplification or
investigation exists, say CLEAN. Maximum 500 words.

Every critic receives the identical immutable plan snapshot below.
Plan SHA-256: `0e478ccea3a01cc53dbf379b02a9563f7a1108ee4dd012b32c2eef4b271fe52d`.

## Complete North Star

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



## Complete frozen agent goal

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



## Complete immutable plan snapshot

# Phase 3 revised plan — canonical pack beta hard cut

Status: **revised; awaiting explicit Sol `STABLE` and settled-plan sense-check**.

## Determination

- Estimate: **5.9–8.7 engineer-weeks**.
- Huge run: **yes**.
- Difficulty: **5/5**.
- Proposed `[XHARD]` implementation tasks: **none**.
- Dependency order: baseline → canonical contract → pack conversion → database
  cutover → consumer convergence → deletion/package closure → final validation.
- New exploration areas: **none**. E1–E10 resolved plan-shaping questions.

The missing runaway demo fixture is an implementation-test issue, not a new
research lane: replace its external dependency with a deterministic temporary
project unless custody evidence proves it is intentionally packaged.

## Resolved evidence

1. There are two active manifest species, three accepted pack filenames,
   schema-less parsing, two `PackDefinition` construction paths, and several raw
   mapping consumers. They must cut over together.
2. Existing typed capability registries are the right projections. Preserve
   ordering, conflict, alias/override/fork, graph, and specialized validation.
3. Existing database collision/freeze/checksum/drift/probe/transaction mechanics
   are reusable; minimum-version enforcement and owner-root provenance are the
   gaps.
4. `open_database(path, registry)` and `DatabaseWriter` remain the SQLite
   boundaries; other project-opening reads need the common compatibility probe.
5. Baseline: 19 capability directories, four schema-pack directories, `_core`,
   64 executors, 12 orchestrators, 10 elements, eight rendering protocol
   extensions, four database packs, and 18 current skills. Counts are audit
   baselines, not runtime constants.
6. `builtin` owns no live behavior. Delete it and all 49 deprecated `builtin.*`
   aliases. The target is 22 ordinary product packs plus irreducible `_core`.
7. All 22 retained product packs require structured skills. Add direct skills
   for blender, timeline, shots, references, and runaway; repair media
   frontmatter. There are no speculative documentation opt-outs.
8. Wheel rules currently exclude skills, Markdown, requirements files, and
   Blender's service unit. These become declared owner resources.
9. External provenance exists at shared discovery then is lost; retain it in
   catalog entries/projections and never trust self-declared origin/install tier.
10. Runaway adds one migration/table. Writable three-pack DBs apply it;
    read-only probes report it pending without mutation; existing four-pack DBs
    reopen unchanged.
11. Historical `.oracle`, findings/planning/input material, and unrelated
    training manifests are excluded from active-authority scans.

## Final architecture

### Canonical definition and catalog

- Evolve `PackDefinition` in place into one deeply immutable v2 object.
- Accept only `pack.yaml` with required schema v2; reject alternate filenames,
  schema-less/legacy shapes, and schema manifests.
- Parse/validate once. Validation, install, inspect, index, typed registries, and
  packaging consume the normalized object rather than raw mappings.
- Include normalized identity, declared resources, typed capabilities, optional
  database contribution, vocabularies, repositories, conformance, static
  CLI/bridge ownership, and documentation routes.
- Attach source kind, owner root, installed revision, and bundled trust as
  loader/catalog provenance; transport metadata cannot reconstruct identity.
- Preserve automatic local-pack creation only by emitting strict capability-only
  v2 and failing existing legacy local manifests.

### Typed projections

- Expose narrow executor, orchestrator, element, rendering, generation,
  database, CLI ownership, skills, inspect, and resource projections.
- Retain existing typed registries/factories and their specialized behavior.
- Preserve discovery order/provenance through projections; do not strip entries
  before admission checks.
- The catalog owns declarations, not arbitrary service instantiation.

### Database contribution

- Keep core migrations as explicit kernel behavior.
- Bundled packs may declare ownership and migration/resource metadata; SQL owns
  columns, constraints, indexes, and transformations.
- Standard composition is core plus references, runaway, shots, and timeline in
  deterministic dependency order.
- Relocate useful database registry/migration algorithms without preserving
  schema-pack identity or compatibility exports.
- Registered migrations carry owner-relative resource handles and provenance.
- Enforce dependency existence, cycles, and minimum versions.
- Preserve SQL bytes, migration identity, checksums, drift, probing, and
  per-migration `BEGIN IMMEDIATE` transactions.
- Reject `database` on local, extra-root, environment, Git-installed, and active
  installed-revision packs before resource resolution or registration.

### Documentation and census

- Every retained bundled product pack declares `skill/SKILL.md`.
- `_core` remains kernel-owned/non-unloadable and links a generated packaged
  census of stable identity, capability categories, database ownership, and doc
  routes.
- Census/skills contain no DDL or mutable database state.
- One deterministic generator has check mode; remove independent skill/index
  manifest parsing.

### Coverage ledger

Create a reviewed audit-only ledger with `surface_id`, `kind`, `owner`
(`pack:<id>` or `kernel:<subsystem>`), `evidence_paths`, and
`projection_consumers`.

Kinds cover typed capabilities, rendering protocols, database migrations/table
ownership, vocabularies, repositories, conformance, CLI/SDK/bridge surfaces,
resources, docs, and operational consumers. Reject missing, stale, duplicate,
or conflicting ownership. Consumers are never owners. Record `builtin`/aliases
as deleted residue, not artificial ownership.

## Work packages

### WP0 — baseline reconciliation and executable gates

Estimate: **0.4–0.6 engineer-week**. Depends on nothing.

- Establish the coverage ledger and explicit kernel classifications.
- Record retirement of `builtin` and deprecated aliases.
- Add characterization for fresh standard composition; three-pack writable
  upgrade; read-only pending runaway; four-pack reopen; external capability
  success/database rejection; and current repository/event/command/CLI/SDK/
  bridge behavior.
- Replace missing runaway demo dependency with a temporary fixture if needed.
- Define historical/training scan exclusions and start the evidence matrix.

Exit: every baseline surface is owned, deliberately deleted, or kernel-owned;
all characterization outcomes are understood.

### WP1 — strict v2 loader and deterministic catalog

Estimate: **1.0–1.4 engineer-weeks**. Depends on WP0.

- Define strict v2 schema and deeply immutable definition.
- Replace loader/static-validator duplication with one pipeline.
- Accept only `pack.yaml`; remove arbitrary-path/flat behavior.
- Resolve all resources relative to owner roots with realpath/symlink
  confinement.
- Retain provenance/trust through entries and projections.
- Reject external database contributions at shared admission.
- Rewire every discovery/install admission path to the same loader.
- Remove self-declared origin/install-tier authority.
- Update scaffolding/local creation and add three golden fixture types.

Exit: one filename/schema/parser/object/catalog/resolver; legacy fails closed.

### WP2 — bundled conversion and documentation

Estimate: **0.8–1.1 engineer-weeks**. Depends on WP1.

- Convert all retained manifests to v2.
- Fold timeline, shots, references, and runaway into normal manifests while
  preserving SQL bytes and behavior.
- Make references the combined database/repository/SDK/CLI/docs exemplar.
- Delete `builtin` and its deprecated aliases.
- Add the five missing structured skills and repair media frontmatter.
- Declare every migration, skill, document, requirements file, service file,
  and runtime asset through its owner manifest.

Exit: exactly 22 retained v2 product packs, all documented; no schema manifest.

### WP3 — database projection and migration cutover

Estimate: **1.0–1.5 engineer-weeks**. Depends on WP2.

- Relocate reusable registry/migration algorithms without compatibility exports.
- Build the frozen projection from core plus bundled catalog contributions.
- Remove both fixed-three builders.
- Add owner resource/provenance and enforce dependency minimum versions.
- Preserve collision/freeze/checksum/drift/probe/transaction semantics.
- Validate fresh four-pack composition, deterministic order, three-pack writable
  upgrade, read-only pending state, four-pack reopen, and all fail-closed cases.

Exit: one manifest-derived DB authority with all safety guarantees intact.

### WP4 — operational, inspection, doctor, and agent convergence

Estimate: **1.1–1.6 engineer-weeks**. Depends on WP3.

- Inject one projection through application, bridge, SDK, kernel reads,
  timeline/rendering helpers, backup, and restore.
- Require raw project reads to use the common probe or an already-probed
  connection.
- Keep backup/restore payload semantics stable while changing expected authority.
- Drive CLI ownership/mount validation from declarations while retaining static
  factories.
- Remove raw parsing from installers, inspect, index, trust summaries,
  validators, and folder consumers.
- Produce stable inspect text/JSON for identity, provenance, capabilities,
  database ownership/dependencies/migrations/head, docs, and resource closure.
- Add read-only doctor census/status and generate/check `_core` census.

Exit: operational consumers, inspect, doctor, skills, and `_core` agree; no
inspection mutates databases.

### WP5 — hard deletion, authority gates, and clean-wheel closure

Estimate: **0.8–1.2 engineer-weeks**. Depends on WP4.

- Delete all schema manifests/parser/identity, fixed builders/tuples, v1 schema,
  alternate filename probes, flat parser, raw identity readers, compatibility
  exports, and alias compatibility tests.
- Extend lint/CI against schema imports, legacy names, fixed lists, raw identity
  reconstruction, and independent first-party inventories.
- Package declared skills, Markdown, requirements, SQL, Blender service unit,
  and existing runtime assets; exclude tests/caches/authoring-only/undeclared.
- Audit the installed catalog in a source-isolated process and compare source
  versus wheel identity, provenance, docs, migrations, and closure.
- Enable zero-unclassified/multi-owner/stale/legacy gates.

Exit: old authorities are absent and every declared resource loads from wheel.

### WP6 — authoritative validation and evidence closure

Estimate: **0.8–1.3 engineer-weeks**. Depends on WP5.

Run focused validation:

```bash
python3 -m pytest tests/packs tests/v10/test_catalog_migrations.py \
  tests/v10/test_m8_packaging.py tests/v10/test_pack_factoring.py \
  tests/v10/test_reference_repository.py tests/sdk/test_references.py \
  tests/sdk/test_extended_composition.py
python3 -m astrid doctor
python3 -m build
```

Also validate golden fixtures; every external source; fresh/upgrade/reopen/
read-only database paths; checksum/name/version/dependency/collision/drift;
references/runaway round trips; backup/restore; inspect text/JSON; doctor
non-mutation; census drift; authority/coverage gates; clean wheel; and one full
`python3 -m pytest` run.

Reproduce unrelated failures against the pinned custody source. Complete all 15
evidence rows, pass final Sol review, commit reviewed paths, push only the
explicit branch, open the worktree, and never merge/deploy/promote/publish.

Exit: every criterion has evidence and independent reviewer disposition.

## Cumulative huge-run boundaries

1. **A — canonical contract:** after WP1–WP2.
2. **B — persistence/consumer convergence:** after WP3–WP4.
3. **C — hard-cut product closure:** after WP5.
4. **Final — evidence closure:** after WP6.

No dependent work advances until the relevant integrated gate passes.

## Explicit anti-pattern rejections and simplicity controls

- Delete the schema-pack species; retain only relocated generic mechanics.
- Keep typed registries/static factories; do not create a universal locator.
- YAML owns declarations, SQL owns DDL, `schema_migrations` owns applied state.
- No locks, lifecycle, marketplace, solver, signing, dynamic DB/plugin/factory,
  down migration, or migration ceremony.
- Reject all external SQL before resource resolution.
- Keep core and `_core` irreducible; do not fake unloadability.
- No aliases, dual reads, v1 shim, fallback, compatibility export, or legacy
  parser.
- Delete empty `builtin` rather than inventing a purpose.
- Do not redesign repositories, writer/UoW, SDK, or transactions.
- Keep coverage ledger non-runtime.
- Use ordinary package-data rules plus installed-wheel tests, not a custom
  packaging backend.
- Do not treat training manifests as packs or duplicate census logic.
- Do not widen to global models/LoRAs/taxonomies/kernel primitives unless the
  ownership audit proves an existing pack-owned surface requires classification.
- Any unclassified surface, bypass, missing doc, or missing wheel resource is a
  failed run, not deferred cleanup.


## Complete accepted exploration evidence


===== .oracle/findings/explore/E1-manifest-authorities.txt =====
**Ranked verified findings**

1. **Two pack grammars and three filename authorities.**  
   `astrid/core/pack/_common.py:16-25` accepts `pack.yaml`, `pack.yml`, `pack.json`; component manifests likewise accept YAML/YML/JSON. `loader.py:184-216` probes those names in order, parses JSON directly, YAML via `safe_load`, then falls back to a schema-less flat `key: value` parser (`:219-240`). Direct `load_pack_manifest()` also accepts arbitrary non-JSON paths. Generic parsing separately lives at `manifest.py:19-65`. Layout validation repeats the filename list at `validate_layout.py:84-93,146-150`. This directly conflicts with frozen `pack.yaml`-only v2.

2. **`PackDefinition` is reconstructed twice.**  
   Runtime loading constructs it at `loader.py:110-152`; static validation reparses raw data and reconstructs a divergent object at `validate.py:518-539` for component discovery. The validator hardcodes `pack.yaml` in `manifest_path`, while the loader preserves the selected path. `PackDefinition` is frozen only shallowly: its dict fields remain mutable (`definition.py:31-53`).

3. **Raw pack mapping consumers bypass normalization.**  
   `validate.py:1035-1043` (`extract_trust_summary`), `cli_inspect.py:57-85`, `install_local.py:121-145,711-734`, `install_git.py:470-483`, `scaffold.py:110-140`, and `agent_index.py:393-399` independently parse/read fields. Agent index also directly parses component YAML/JSON (`:102-120`). Folder extractors parse emitted JSON separately (`execution/*/folder.py:93-105`).

4. **Discovery fan-out.**  
   `discovery.py:88-111,127-257` scans source, auto-local, extra, env, and installed roots; registries consume it through executor/orchestrator, element, rendering, generation, timeline, SDK, skills, CLI list/inspect (`execution/*/registry.py:292-303`; `element/registry.py:206-212`; `sdk/discovery.py:139-146`).

5. **Database authority remains separate.**  
   `schema_packs/manifest.py:34-46,407-421`, `schema_packs/standard.py:27-45`, and `packs/__init__.py:68-110` maintain schema-pack identity plus duplicate fixed tuples. Consumers include application, doctor, backup, kernel reads, SDK invocation, timeline helpers, rendering assets, and runaway migration (`doctor.py:636-642`; `backup/operations.py:1287-1292`; `scripts/migrations/runaway_v1_migrate.py:108-117`).

6. **Automatic local-pack creation.**  
   `loader.py:35-72` creates `astrid/packs/local/pack.yaml`; called by executor/orchestrator forks, discovery when local elements exist, and `html_canvas_effect/run.py:109-124`.

**Tests affected:** `tests/packs/test_pack_yaml_schema.py:1647-1677`; `tests/v10/test_registry.py:162-216`; `tests/v10/test_pack_factoring.py:82-95`; `tests/v10/test_m8_packaging.py:46-53,207-220`; discovery/local tests around `tests/packs/test_pack_discovery_metadata.py:98-102`.

**Simplest seam:** make one strict loader return the immutable canonical definition plus resolved resources/database/docs; make discovery produce that catalog, then pass projections to validation, registries, install/inspect, CLI, skills, and database composition. Delete `schema_packs`, duplicate builders, legacy filename probes, and raw mapping consumers. This confirms `.oracle/plan.md` WP1/WP4/WP7; current code violates the frozen goal.
0
===== .oracle/findings/explore/E2-capability-projections.txt =====
1. **[CONFLICT] Identity/parser authority split.** `PackDefinition` is only shallowly frozen (`dict` fields remain mutable): `astrid/core/pack/definition.py:31-53`. Loader still accepts `pack.yml/json`, schema-less flat YAML, and a legacy parser: `astrid/core/pack/_common.py:16-19`; `astrid/core/pack/loader.py:184-240`. Validation independently reconstructs a `PackDefinition`: `astrid/core/pack/validate.py:518-539`. This directly violates the one v2 parser/object requirement.

2. **[CONFIRMS] Reusable typed mechanics.** Generic ordered winner/shadow storage, conflict reporting, aliases, and override hooks are well-factored in `CapabilityRegistry`: `astrid/core/registry/base.py:54-71,88-185`. Executor/orchestrator registries specialize validation/graph checks; elements specialize tuple keys; rendering shares `_RenderingRegistry`; generation has typed backend/taxonomy descriptors: `astrid/core/execution/executor/registry.py:66-149`; `astrid/core/execution/orchestrator/registry.py:55-142`; `astrid/core/rendering/registry.py:168-243`; `astrid/core/generation/backends/registry.py:28-124`.

3. **[CONFLICT] Discovery/trust duplication.** Shared layered discovery exists—source, local, extra, env, installed—with explicit path de-duplication: `astrid/core/pack/discovery.py:39-107,127-259`. Yet SDK loads three registries independently (`astrid/sdk/discovery.py:98-131`), rendering and generation each rescan manifests, and the agent index has a separate `discover_packs()` plus `InstalledPackStore` overlay: `astrid/core/pack/agent_index.py:11-27,329-374`. Trust is rendering-specific (`registry.py:687-780`), while executor/orchestrator loading does not apply equivalent admission.

4. **[CONFIRMS/CONFLICT] Resolution mechanics.** Alias graphs, precedence peeling, canonical-id overrides, fork provenance, and hash/git dirty detection are reusable: `alias_resolver.py:19-125`; `rendering/registry.py:939-1088`; `executor/registry.py:191-246`; `dirty.py:20-119`. Element forks are documented but no element fork implementation was found; this is an ownership gap.

5. **[CONFLICT] Priorities/caches/docs.** Element/executor priorities collapse most layers to `30` (`element/registry.py:351-404`; `executor/registry.py:333-358`), unlike rendering’s explicit discovery index (`rendering/registry.py:589-594`). Element registries have duplicated caches (`element/registry.py:186-246`; `catalog.py:83-107`). `_core/SKILL.md` contains static runtime census prose (`:12-25,386-390`) while the generator independently loads registries (`scripts/gen_capability_index.py:21-83`).

**Affected tests:** registry, fork, override, dirty, rendering registry/matrix, generation model registry, skills sync, pack factoring, packaging, authority lint.  
**Seam:** make one strict loader/catalog return immutable pack projections; retain typed registries as projections; route SDK, rendering, generation, skills, index, and trust through that catalog.
0
===== .oracle/findings/explore/E3-database-projection.txt =====
1. **[CONFLICT] Split authority is real.** `schema-pack.yaml` is an independent strict 11-field species: identity/version/dependencies/migrations/vocabularies/repositories/conformance/mounts (`astrid/core/schema_packs/manifest.py:34-59`, `369-404`). Both kernel and pack layers hard-code `("timeline","shots","references")` and load schema manifests independently (`astrid/core/schema_packs/standard.py:27-45`; `astrid/packs/__init__.py:68-110`). `runaway` is excluded from standard composition and manually appended in tests (`tests/test_runaway_transitions.py:32-39`; `tests/sdk/test_extended_composition.py:18-27`). This directly conflicts with the frozen one-`pack.yaml`/four-pack goal.

2. **[CONFIRMS mechanics; CONFLICTS dependency requirement]** Parsing accepts only `pack >= positive-integer`, rejects duplicate *raw strings*, and returns immutable dependencies (`manifest.py:167-195`). Ordering rejects missing packs and cycles, but ignores `dependency.version`; `core >= 1` and `core >= 99` are not compared with the dependency manifest version (`runner.py:146-201`). Plan requirement for minimum-version enforcement is currently unmet (`.oracle/plan.md:106-115`).

3. **[CONFIRMS collision guarantees]** Registration is atomic per manifest and reports deterministic sorted collisions. Global table/vocabulary/repository/mount collisions are rejected; migration version/name collisions are scoped to `(pack, version/name)` (`registry.py:162-180`, `221-294`). Freeze yields sorted immutable mappings (`registry.py:183-202`). This is the strongest reusable database projection seam.

4. **[CONFLICT] Migration provenance/resource lookup is insufficient.** `RegisteredMigration` carries only pack/version/name/path/tables (`registry.py:53-65`). `source_path` exists on manifests but is discarded. The runner reconstructs roots from pack id, with a special core path (`runner.py:113-138`); no owner root/revision handle exists. External/resource-package loading cannot reuse this safely.

5. **[CONFIRMS safety]** Applied state records `(pack,version,name,checksum,applied_at)` (`runner.py:209-230`; core SQL `0001_initial.sql:27-35`). Probe validates unregistered/too-new versions, missing descriptors, name drift, and exact-byte SHA-256 drift without writes (`runner.py:233-322`). Writable opens apply PRAGMAs, then each migration’s DDL plus ledger row in its own `BEGIN IMMEDIATE` transaction (`runner.py:387-457`; `store/database.py:67-98`). Covered by `tests/v10/test_catalog_migrations.py:627-663`, `777-940`.

6. **Clean seam:** evolve `FrozenSchemaPackRegistry` into the canonical catalog’s typed **database projection**; add owner-relative resource handles/provenance to `RegisteredMigration`; retain `open_database`/`DatabaseWriter` signatures and runner guarantees. Generate core plus trusted bundled contributions from one catalog. Add dependency-version tests, runaway standard-composition tests, and wheel resource probes (`tests/v10/test_m8_packaging.py:276-300`).
0
===== .oracle/findings/explore/E4-operational-consumers.txt =====
1. **Split authority (conflict with frozen goal; confirms WP1/WP3/WP7).** `astrid/packs/__init__.py:68-110` hard-codes `(timeline, shots, references)`; `astrid/core/schema_packs/standard.py:27-45` repeats the tuple and builder. `runaway` is a fourth shipped schema pack (`astrid/packs/runaway/schema-pack.yaml:1-5,15-30`) but is omitted. `tests/v10/test_registry.py:154-181,201-216` explicitly asserts both duplication and omission; these tests must be deleted or rewritten.

2. **Write/open seam (conflict; confirms WP4).** `open_database()` is the correct migration/probe gate (`astrid/core/store/database.py:67-98`), and `DatabaseWriter` routes writable/read-only opens through it (`astrid/core/store/writer.py:303-325,408-430`). Application composition uses `build_standard_registry`/`open_standard_writer` (`astrid/application.py:315-338`); bridge composition directly constructs another writer (`astrid/packs/__init__.py:247-278`); SDK invocation constructs one itself (`astrid/sdk/invocation.py:868-874`). Writer lint only exempts store, conformance, and `astrid/packs/__init__.py` (`scripts/reshape/authority_lint.py:397-432`).

3. **Read/operational bypasses (conflict; confirms WP4/WP5).** Kernel reads and doctor use the duplicate registry (`astrid/core/kernel/read.py:32-52`; `astrid/core/doctor.py:636-642`). Backup creation snapshots migration rows without a registry (`astrid/core/backup/operations.py:1122-1172,334-375`); restore rebuilds the duplicate (`:1253-1296`). SDK events, media resolution, and render/visualize readers use raw RO SQLite (`astrid/sdk/events.py:69-101`; `astrid/core/io/managed_media_resolver.py:79-108`; `astrid/packs/rendering/executors/render/managed_timeline.py:244-248`; `.../timeline_visualize/select.py:212-219`).

4. **Least-disruptive boundary (confirms plan).** Core cannot import packs except `gateway/dispatch.py`; pack-to-pack imports are forbidden (`scripts/reshape/authority_lint.py:11-22,59-61,335-393`). Evolve the existing `astrid.core.pack` `PackDefinition`/discovery (`definition.py:31-53`; `discovery.py:1-15,88-108`) into the single trusted bundled catalog, then derive `FrozenSchemaPackRegistry` once. Keep `open_database(path, registry)` as the SQLite boundary and inject that projection everywhere. CLI ownership currently reparses fixed manifests (`astrid/core/cli/domain_product.py:154-174`); timeline helpers cache another registry (`astrid/core/timeline/_edit_helpers.py:56-72,384-390`).

5. **Affected tests.** `tests/v10/conftest.py:24-41`, `test_registry.py`, `test_pack_factoring.py`, `test_m8_packaging.py:16-40`, `tests/sdk/test_extended_composition.py:18-27,61-72`, and `test_runaway_transitions.py:32-46`; preserve application, kernel-read, backup/restore, doctor, CLI, rendering, and conformance behavior suites.
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
===== .oracle/findings/explore/E7-packaging-closure-r2.txt =====
[launch_hermes_agent] model=codex:gpt-5.6-luna → resolved=openai-codex/gpt-5.6-luna toolsets=['file', 'web'] max_tokens=65536 context_budget_tokens=(auto)
[launch_hermes_agent] NOTE: omp gives the full toolset (Bash, Read, Edit, web, …); the file/web/terminal subset is a superset here.
[launch_hermes_agent] cwd=/Users/peteromalley/Documents/reigh-workspace/Astrid-canonical-pack-beta
Working...
1. **Critical split authority — conflicts with frozen goal and plan WP1/WP2/WP7.** `timeline`, `shots`, `references`, and `runaway` still use separate `schema-pack.yaml` manifests (`astrid/packs/timeline/schema-pack.yaml:1-19`; `runaway/schema-pack.yaml:1-24`). Two independent standard builders hard-code only `timeline, shots, references` (`astrid/core/schema_packs/standard.py:27-45`; `astrid/packs/__init__.py:88-110`), while CLI mounts repeat the same fixed paths (`astrid/core/cli/domain_product.py:154-174`). Legacy filename/parser fallback still accepts `pack.yml`, `pack.json`, and flat YAML (`astrid/core/pack/_common.py:16-19`; `loader.py:184-216`).

2. **Wheel policy directly violates clean-wheel documentation/resource closure.** `include-package-data=false`; package data excludes every `skill/` tree and includes no Markdown, TXT, or `.service` patterns (`pyproject.toml:66-133`). The wheel test explicitly forbids `/skill/`, `STAGE.md`, and `requirements.txt` (`tests/v10/test_m8_packaging.py:63-74`). This conflicts with goal criteria 8/10 and plan WP6.

3. **Current recursive inclusion is extension-based, not manifest/resource-based.** YAML/JSON/HTML/CSS/JS/TS/TSX/TTF are recursively included (`pyproject.toml:103-133`), covering training schemas/UI (`dataset_build/config.py:20-22`; `phases.py:37-38`) and the visualization font (`render_png.py:72-89`). Opaque runtime files are omitted: Blender reads `server/blender-render-api.service` (`blender/deploy.py:46-59,282-293`); executor discovery/installation can consume `requirements.txt` (`execution/executor/folder.py:155-175`; `install.py:182-201`).

4. **Path/symlink risk remains uneven.** Declared content roots resolve without confinement (`pack/walkers.py:84-115`); docs and entrypoint checks join paths and follow symlinks (`pack/validate.py:501-510,736-743`). Rendering extension paths and migration paths do enforce containment (`pack/registry.py:293-301`; `schema_packs/manifest.py:322-334`). Confirms plan’s realpath-risk control.

5. **Simplest seam:** extend `tests/v10/test_m8_packaging.py`’s `build_once` harness (`:303-370`) with an installed-process, manifest-driven closure audit: load the canonical catalog, enumerate every declared pack resource/migration/skill/document, assert existence/readability, and reject source-tree imports. Replace hard-coded `EXPECTED_RESOURCES`; broaden `test_package_data.py:57-86` and the nine-pack skill floor (`test_pack_layout_contract.py:367-390`). Actual wheel membership remains unobserved because this was read-only exploration.
[launch_hermes_agent] done in 297.5s (exit=0)
0

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
===== .oracle/findings/explore/E9-legacy-ci.txt =====
**Ranked verified inventory**

1. **P0 conflict — active second schema-pack species.** Four shipped `schema-pack.yaml` files are parsed by `astrid/core/schema_packs/manifest.py:34-50,369-421`. Two independent builders hard-code `("timeline","shots","references")` in `astrid/core/schema_packs/standard.py:27-45` and `astrid/packs/__init__.py:68-100`; `runaway/schema-pack.yaml:1-35` is excluded. Affected: `tests/v10/test_registry.py:154-181`, `test_m6_gate.py:132-135`, `test_pack_factoring.py:52-95`, `scripts/reshape/m4_gate.py:94-103,559-599`, `scripts/reshape/check_pack_factoring.py:91-204`.

2. **P0 conflict — legacy pack filenames and flat parsing execute.** `PACK_MANIFEST_NAMES` accepts `pack.yaml`, `pack.yml`, and `pack.json` (`astrid/core/pack/_common.py:16`); `loader.py:184-240` selects them and implements `_parse_flat_yaml`. The same contract is enforced by `validate.py:257-275`, `validate_layout.py:84-85,149`, `validate_first_party.py:20-45,131-149`, and `install_git.py:247-285`. Active schema: `astrid/core/pack/schemas/v1/pack.json`. Affected: `tests/packs/test_pack_yaml_schema.py`, `test_pack_layout_contract.py:75-88,229-305`, `test_packs_validate.py`.

3. **P0 conflict — independent consumers.** CLI mounts reread fixed schema manifests (`astrid/core/cli/domain_product.py:154-174`); `agent_index.py:102-120,393-422` reparses raw YAML/JSON; installed-wheel tests regex-parse YAML (`tests/v10/test_m8_installed_contract.py:55-83`); `install_git.py:470-484` reparses versions.

4. **P1 conflict — packaging/docs encode the split.** `pyproject.toml:109-125`, `tests/v10/test_m8_packaging.py:46-53,216-220`, and `scripts/smoke_wheel_install.sh:82-87` enumerate only three schema packs. Active v1 docs: `docs/contracts/platform-contract.md:161-186`, `docs/packs/creating-packs.md:111-154`. Generated `_core/skill/SKILL.md:566-570` is capability-only, not a pack census.

**Historical/non-authoritative:** `.oracle/**`, `findings/**`, `planning/**`, `inputs/astrid-first/**`, and `docs/astrid-v10-implementation-decisions.md:1-8,61-79`; exclude from scans. Training flat manifests (`tests/packs/builtin/test_training_run_manifest_input.py:66-129`) are unrelated.

**Zero-legacy seam:** extend `scripts/reshape/authority_lint.py`; invoke from `.github/workflows/ci.yml:116-123`. Fail on any legacy filename, schema-pack import, fixed tuple/list, flat parser, or raw pack-manifest parse. Require every bundled pack, including `runaway`, to load through one catalog and pass clean-wheel closure.
0
===== .oracle/findings/explore/E10-runaway-builtin.txt =====
### Ranked verified facts

1. **Runaway is extended-only today; plan confirms.** Both standard builders hard-code only `timeline`, `shots`, `references` (`astrid/packs/__init__.py:68-110`; `astrid/core/schema_packs/standard.py:27-45`). `tests/sdk/test_extended_composition.py:18-27` manually adds runaway; `:61-64` expects five migration rows. This directly confirms `.oracle/plan.md:26-29,113-115`.

2. **Runaway contributes exactly one table, one migration, one command, and one repository—no stream/event/CLI/bridge surface.** Manifest evidence: `astrid/packs/runaway/schema-pack.yaml:15-35`; DDL adds `runaway_transitions`, two indexes, and FKs to `projects`, `runs`, `tasks` (`migrations/0001_initial.sql:21-40`). Static composition confirms migration order becomes `core, references, runaway, shots, timeline`.

3. **Standard inclusion changes opens materially.** Writable opens probe first, then apply pending migrations (`astrid/core/store/database.py:67-98`; runner `:387-457`). Existing standard databases go from 20 to 21 tables and gain `schema_migrations(runaway,1)`. Existing extended databases currently fail default reads/writes with `MigrationTooNewError` (`test_extended_composition.py:66-71`); final composition must accept them unchanged. Read-only opens must see pending runaway without applying it (`database.py:73-79`). Backup restore validation uses the same standard probe (`backup/operations.py:1253-1296`).

4. **`builtin.*` is compatibility residue, not implementation ownership.** The `builtin` pack has no capabilities and says it ships no live components (`astrid/packs/builtin/pack.yaml:13-20`; directory contains only `pack.yaml`). All 49 `builtin.*` aliases are declared by canonical packs, all deprecated; resolver maps aliases to canonical IDs (`alias_resolver.py:109-125`). Alias behavior is currently tested (`tests/test_external_app_contract.py:148-155`; `tests/test_sdk_public_surface.py:295-311`), but hard-cut policy supports deleting these compatibility assertions/declarations.

### Exact hard-cut tests/scenarios

- Rewrite fixed-three/20-table assertions: `tests/v10/test_registry.py:154-181,219-224`; `test_standard_application.py:299-314`; `test_m6_gate.py:47-48,132-136`; `test_m8_installed_contract.py:243-250`.
- Replace extended-only characterization with: fresh four-pack open; existing three-pack writable apply; existing four-pack reopen; read-only pending nonmutation; checksum/name drift rejection; unknown-pack rejection; backup/restore for both states.
- Preserve runaway repository/round-trip coverage (`tests/test_runaway_transitions.py:32-63,304-374`), but its referenced `projects/runaway-piano-colour-demo` fixture is absent in this checkout (`:28-29`): restore/provide it before relying on that gate.
- Simplest seam: one canonical bundled catalog supplies both standard builders and all operational consumers; convert runaway to v2 `pack.yaml`, then delete schema-pack builders and aliases.
0

