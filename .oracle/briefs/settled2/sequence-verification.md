# Settled-plan wave 2 — sequence-verification

You are a fresh independent GPT-5.6 Luna plan critic. You did not author or
review Wave 1. Work read-only. Do not edit files, run mutating commands, create
branches, dispatch models, widen scope, or redesign the plan.

## Lens

Challenge the complete revised dependency order, cumulative boundaries, ledger lifecycle, per-pack matrix, and validation proportionality. Find unsafe ordering, stale-state risks, redundant checks, or missing frozen-criterion proof. Do not rewrite the plan.

## Output contract

Identify and rank only concrete material simplifications, defects, or unresolved
investigations with plan-section or source evidence. Check every frozen done
criterion and every North Star anti-pattern. If no accepted material
simplification or unresolved investigation remains, answer CLEAN and give a
brief explicit North Star alignment disposition. Maximum 500 words.

Every Wave 2 critic receives the identical complete snapshot.
Plan SHA-256: `c5cfa3128be626c6a263d131b3a2baa3292c74d0fed3d2e12d86a607e5ad92b5`.

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



## Complete frozen goal

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



## Complete immutable revised plan

# Phase 3 complete replacement plan — canonical pack beta hard cut

Status: **revised replacement; ready for a subsequent exact `STABLE` check**.

This plan incorporates every accepted Wave 1 synthesis item. It does not claim `STABLE`; after an exact `STABLE` response, Megado must run a fresh settled-plan wave against this complete snapshot before Phase 4.

## Determination

- Estimated implementation effort: **5.7–8.0 engineer-weeks**, including integration reviews and expected rework.
- Huge run: **yes**; the estimate remains well above two weeks.
- Difficulty: **5/5** because the hard cut spans manifest parsing, trusted discovery, persistence, operational consumers, documentation, and packaging.
- Proposed `[XHARD]` implementation tasks: **none**. All planned work is decomposable and presumed normal Luna work; the Phase 4 oracle must still finalize classifications.
- New exploration or research lanes: **none**.
- Open planning questions: **none**.
- Execution order: baseline evidence → v2 contract/catalog → pack conversion → database cutover → operational convergence → hard deletion/wheel closure → final evidence.
- The estimate is slightly lower than the prior 5.9–8.7 weeks because baseline and final validation are no longer duplicated and broad textual scanning is removed. The contract-freeze and resource-closure work prevent a larger reduction.

The missing runaway demo input remains a bounded implementation-test issue: use a deterministic temporary project fixture unless custody evidence proves that input is intentionally packaged.

## Mandate and scope boundary

Implement one strict bundled-pack system:

- Every retained bundled product pack is declared by one `pack.yaml` with integer `schema_version: 2`.
- `timeline`, `shots`, `references`, and `runaway` become ordinary canonical packs with optional database contributions.
- Existing typed registries, static factories, migration machinery, repositories, `DatabaseWriter`, `UnitOfWork`, SDK behavior, and conformance semantics remain.
- Every bundled customization is assigned to a canonical pack or an evidence-backed irreducible kernel owner.
- Every user/agent-facing product pack has structured packaged documentation.
- External packs remain capability-only and fail closed if they declare `database`.
- The result is a beta hard cut: no old manifests, legacy reads, compatibility exports, or alternate authorities.

The frozen goal remains the operational authority. The North Star guides the end state but cannot widen scope.

## Canonical architecture

### 1. One declaration and one catalog path

Evolve the existing `PackDefinition` rather than creating a parallel product model.

A canonical pack load produces:

- A deeply immutable manifest-derived definition.
- A catalog entry pairing that definition with loader-derived provenance and resolved owner-relative resources.
- Narrow typed projections consumed by existing registries and operational systems.

No consumer may reparse `pack.yaml`, reconstruct identity from a directory name, or recover trust from manifest metadata.

The existing generic component-manifest parser may remain where non-pack component formats still need it. It must no longer serve as an alternate pack parser.

### 2. V2 field contract

WP1 begins with a contract-freeze gate. Before loader work or pack conversion can fan out, it must land an executable JSON Schema, immutable normalized types, golden fixtures, and invalid fixtures covering this semantic contract:

Required top-level fields:

- `schema_version`: integer, exactly `2`.
- `id`: validated canonical pack identifier.
- `name`: non-empty display name.
- `version`: validated pack release version.

Retained optional declarations, using existing spellings where possible:

- Descriptive identity: `description`, `status`, `visibility`, `domain`, `stability`, `support`, and `keywords`.
- Permissions.
- Existing typed content roots for executors, orchestrators, elements, schemas, examples, and documents.
- Existing typed capability and extension declarations.
- Agent-routing metadata.
- Canonical aliases only where current typed registry semantics require them; aliases cannot provide manifest compatibility, and all deprecated `builtin.*` aliases are deleted.
- Scoped metadata only where an existing consumer requires it.

New or consolidated declarations:

- Optional `database`, containing the former schema-pack declarations: dependencies, ordered migrations, table ownership, stream/event/command vocabularies, repositories, conformance claims, and static CLI/bridge ownership.
- Structured documentation routes to `skill/SKILL.md` or `AGENTS.md`, or an explicit non-user-facing opt-out reason.
- Typed supplemental resources for runtime or documentation files not already reached through a contribution.

Contract constraints:

- Unknown top-level fields fail unless they are within an explicitly retained scoped metadata/extension map.
- Self-asserted `origin`, `install_tier`, trust, or bundled status cannot authorize behavior. Source kind, owner root, installed revision, and bundled trust come exclusively from discovery/catalog provenance.
- Any legacy `pack_type` distinction that describes a capability species versus schema species is removed; contribution presence defines what a pack supplies.
- SQL owns columns, constraints, indexes, and transformations. YAML may declare migration paths and table ownership but cannot restate DDL.
- Database head/version for dependency checking is derived from declared ordered migration versions; no mutable head or applied state is stored in YAML.
- Lists and mappings normalize into immutable typed values; consumers do not receive raw manifest mappings.
- No conversion work may change the contract after the freeze without reopening the plan and re-running its gate.

Golden fixtures cover capability-only, database-only, and combined packs. Invalid fixtures cover missing/wrong schema version, alternate filenames, legacy shapes, unknown fields, malformed contributions, bad documentation routes, path escapes, missing resources, dependency failures, external database declarations, and provenance spoofing.

### 3. Narrow catalog boundary

The catalog is a declaration index, not a runtime container:

- One deterministic immutable bundled catalog may be cached per process.
- Local and external discovery remains dynamic where it is dynamic today; each discovery operation creates an immutable candidate snapshot through the same loader.
- Discovery code owns catalog construction and provenance assignment.
- Permitted catalog operations are identity lookup, deterministic enumeration, provenance inspection, resource inspection, and narrow typed declaration projections.
- Typed registries and existing static factories continue to construct executors, orchestrators, rendering implementations, repositories, CLI mounts, and services.
- Consumers receive the narrowest projection they need, not a general catalog object when a typed registry or database projection suffices.
- The catalog never owns database connections, service instances, repository instances, application lifetime, dependency injection, or arbitrary string-keyed lookup.

### 4. Manifest-derived database composition

Standard beta composition is an algorithm:

1. Begin with explicit irreducible kernel migrations.
2. Select every catalog entry whose provenance is trusted and bundled and whose canonical definition contains `database`.
3. Validate dependencies, cycles, and minimum database migration versions.
4. Topologically order contributions with a deterministic tie-break.
5. Project them into the existing collision, migration, checksum, drift, probe, and transaction machinery.

`references`, `runaway`, `shots`, and `timeline` are only the expected result for the current bundled-catalog fixture. They never appear in a runtime tuple, allowlist, builder, or selection branch.

A semantic test must add a synthetic trusted bundled database pack to a test catalog and prove it is selected without editing composition code.

External database declarations are rejected at shared admission before migration resource resolution, SQL reading, or registry registration. Manifest claims cannot upgrade an external source to trusted bundled status.

Preserve:

- Core migrations as explicit kernel behavior.
- Existing migration identity and SQL bytes.
- Collision and ordering rules.
- Checksums, drift detection, freeze behavior, probes, and per-migration `BEGIN IMMEDIATE` transactions.
- `schema_migrations` as the only applied-state record.
- Writable standard-open migration behavior and read-only non-mutating compatibility probes.

### 5. Resource-closure invariant

Every file required by a bundled pack must be represented by exactly one of:

- A typed path reachable through a declared contribution.
- A declared structured documentation route.
- A typed supplemental resource declaration.

Closure rules:

- Paths are owner-relative, normalized, non-empty, and cannot be absolute or traverse with `..`.
- Resolution uses real paths and rejects symlink escapes.
- Declared directories expand recursively and deterministically to required regular files.
- Nested component manifests and schemas are followed recursively.
- Runtime-use auditing covers opaque assets reached by pack code, including requirements files, Blender’s service unit, SQL, schemas, templates, and other current runtime assets.
- Missing or undeclared required assets fail validation.
- Source and installed-wheel closures must match by relative path and content digest. Absolute roots may differ.
- The wheel must load every canonical definition and declared resource in a source-isolated process.

Use the project’s ordinary package-data configuration. Do not create a custom packaging backend.

### 6. Documentation and census

- All 22 retained product packs declare structured documentation.
- Add direct structured skills for blender, timeline, shots, references, and runaway.
- Repair media’s malformed frontmatter.
- There are no speculative product-pack documentation opt-outs.
- `_core` remains irreducible kernel guidance and is not dynamically unloadable.
- A deterministic generator/check mode produces the packaged `_core` census from the canonical bundled catalog.
- The census includes stable identity, capability categories, database ownership, and documentation routes.
- It contains no DDL or mutable database state.
- Delete independent skill/index manifest parsing and duplicated first-party inventories.

### 7. Audit-only coverage ledger

Maintain one reviewed coverage artifact with:

- `surface_id`
- `kind`
- `owner`, as `pack:<id>` or `kernel:<subsystem>`
- `evidence_paths`
- `projection_consumers`

Kinds cover typed capabilities, rendering protocols, migrations/table ownership, vocabularies, repositories, conformance, CLI/SDK/bridge surfaces, runtime resources, documentation, and operational consumers.

Rules:

- Consumers are not owners.
- `builtin` and its aliases are recorded as deleted residue, not assigned artificial owners.
- Missing, stale, duplicate, conflicting, or unclassified ownership fails the gate.
- Kernel classifications require concrete evidence.
- The ledger is an audit/CI artifact only. It is never imported by runtime code, consulted for composition, or exposed as configuration.

Lifecycle:

1. WP0 captures the immutable pre-change inventory and reviewed initial classifications.
2. Regenerate and compare after bundled conversion.
3. Regenerate and compare at cumulative boundaries A, B, and C.
4. Regenerate from the final tree for the exact completion gate.

The WP0 snapshot remains baseline evidence; it never becomes stale runtime truth.

### 8. Per-pack preservation matrix

Maintain an evidence matrix for each of:

- `timeline`
- `shots`
- `references`
- `runaway`

Each row covers:

- Migration behavior
- Repository behavior
- Events
- Commands
- CLI
- SDK
- Bridge, where applicable
- Conformance

Every cell has baseline evidence and final evidence, or an explicit evidence-backed `N/A` reason. Broad suite success cannot replace this criterion-level mapping.

## Work packages

### WP0 — immutable baseline and ownership reconciliation

Estimate: **0.35–0.5 engineer-week**. Depends on nothing.

- Capture immutable before-state artifacts from the pinned custody source.
- Inventory the current 19 capability directories, four schema-pack directories, `_core`, 64 executors, 12 orchestrators, 10 elements, eight rendering extensions, four database packs, and 18 skills. These remain audit baselines, never runtime constants.
- Establish the initial audit-only coverage ledger and explicit irreducible kernel classifications.
- Record the intended deletion of empty `builtin` behavior and all 49 deprecated `builtin.*` aliases.
- Capture focused baseline behavior needed for before/after proof: current database composition/open behavior, repositories, events, commands, CLI, SDK, bridge, and conformance surfaces.
- Establish the four-pack behavior matrix with explicit `N/A` cells.
- Define exact exclusions for historical `.oracle` material, planning/findings inputs, training-run manifests, and other unrelated manifest formats.
- Start the 15-row completion evidence matrix.
- Do not run the final clean-wheel build or full suite here. If final validation later exposes a suspected unrelated baseline failure, reproduce only that failure against the pinned source.
- Treat the missing runaway demo input as a deterministic test-fixture repair, not an investigation lane.

Exit:

- Every baseline surface is owned, deliberately deleted, or justified as kernel.
- Baseline evidence is immutable and sufficient to compare preserved behavior.
- No research question remains.

### WP1 — frozen v2 contract, loader, resolver, and catalog

Estimate: **1.0–1.35 engineer-weeks**. Depends on WP0.

First, pass the v2 contract-freeze subgate:

- Land the exact field table, JSON Schema, normalized immutable types, three golden fixtures, and invalid-case fixtures described above.
- Record provenance/trust semantics and resource grammar.
- Prohibit conversion fan-out until the contract tests pass.

Then:

- Evolve `PackDefinition` in place.
- Implement one `pack.yaml` v2 loader/normalizer/validator.
- Accept no `pack.yml`, `pack.json`, schema-less YAML, flat shape, arbitrary manifest path, or `schema-pack.yaml`.
- Consolidate runtime and static pack validation onto this pipeline.
- Implement confined owner-relative resource handles and recursive closure validation.
- Construct catalog entries with discovery-owned provenance.
- Implement the narrow catalog API and immutable process-cached bundled catalog.
- Preserve dynamic local/external candidate discovery through the same loader.
- Reject external database declarations before resource resolution.
- Rewire install admission, validation admission, and automatic local-pack creation. Newly created local packs emit strict capability-only v2; existing legacy local manifests fail.
- Preserve existing typed registry construction and specialized validation.

Exit:

- One filename, v2 grammar, parser, validator, canonical definition, provenance envelope, resolver, and catalog boundary exist.
- The catalog constructs no services.
- All legacy pack forms fail closed.

### WP2 — bundled conversion, ownership, resources, and documentation

Estimate: **0.75–1.05 engineer-weeks**. Depends on WP1.

- Convert all 22 retained product packs to strict v2.
- Fold timeline, shots, references, and runaway declarations into their ordinary `pack.yaml`.
- Preserve migration SQL bytes and all current database vocabulary and ownership declarations.
- Make references the combined database/repository/SDK/CLI/documentation exemplar without changing its three-table model.
- Delete the empty builtin product pack and its 49 deprecated aliases.
- Add the five missing structured skills and repair media frontmatter.
- Declare all migrations, structured documentation, component manifests, schemas, requirements files, service units, templates, and runtime assets through typed or supplemental resources.
- Add changed-contract tests for pack conversion and documentation/resource declarations.
- Regenerate and compare the audit ledger and four-pack behavior matrix.
- Confirm the retained-pack count only as a test fixture result, never as runtime selection logic.

Exit:

- Exactly 22 current product-pack fixtures load through v2, plus irreducible `_core`.
- Every product pack has structured documentation.
- No bundled `schema-pack.yaml` remains.
- All current required resources are declared and confined.

### WP3 — database projection and migration hard cut

Estimate: **0.95–1.3 engineer-weeks**. Depends on WP2.

- Relocate reusable registry/migration algorithms out of the schema-pack subsystem without retaining its identity, parser, standard builders, or compatibility exports.
- Build the database projection using the trusted-bundled-with-`database` selection algorithm.
- Keep core migrations explicitly kernel-owned.
- Enforce dependency existence, cycles, deterministic order, and minimum database migration versions.
- Carry owner resource handles and loader provenance into registered migrations.
- Preserve collision, freeze, checksum, drift, probing, ordering, and transaction behavior.
- Remove both fixed-three builders and every duplicated database-pack tuple.
- Add the synthetic bundled-database-pack composition test.
- Validate focused unit and integration behavior for:

  - Fresh current bundled composition.
  - Three-pack writable upgrade applying runaway.
  - Read-only three-pack probe reporting runaway pending without mutation.
  - Existing four-pack reopen without changes.
  - Collision, dependency, version, checksum, drift, and transaction failures.
  - Every external provenance class failing closed for `database`.

- Update the audit ledger and four-pack matrix.

Exit:

- The canonical catalog is the only bundled database-composition authority.
- The current fixture yields references, runaway, shots, and timeline solely because those trusted bundled manifests declare `database`.
- Existing migration safety guarantees remain intact.

### WP4 — operational, inspection, doctor, and agent convergence

Estimate: **1.0–1.4 engineer-weeks**. Depends on WP3.

- Feed narrow canonical projections into application startup, bridge wiring, SDK access, kernel reads, timeline/rendering helpers, backup, and restore.
- Preserve `open_database(path, registry)` and `DatabaseWriter` as SQLite boundaries.
- Require raw project-opening reads to use the common non-mutating compatibility probe or an already-probed connection.
- Preserve backup/restore payload semantics while deriving expected composition from the canonical database projection.
- Drive CLI ownership and mount validation from declarations while retaining static CLI factories.
- Remove raw pack mapping reads from install summaries, indexes, agent discovery, inspect, trust summaries, validators, and folder consumers.
- Add stable pack inspection text and JSON for:

  - Identity
  - Loader-derived provenance
  - Capability categories
  - Database dependencies, migrations, ownership, and derived head
  - Documentation routes
  - Resource closure

- Add doctor’s read-only canonical pack census and database migration status.
- Generate/check the `_core` census from the bundled catalog.
- Prove inspect and doctor never migrate or otherwise mutate a project.
- Regenerate the audit ledger and four-pack matrix.

Exit:

- Every named operational consumer agrees on canonical ownership and composition.
- No operational or documentation consumer independently parses or inventories bundled packs.
- Runtime construction remains with typed registries/static factories.

### WP5 — hard deletion, proportionate authority gates, and wheel closure

Estimate: **0.7–1.0 engineer-weeks**. Depends on WP4.

Delete:

- Schema-pack manifests, parser, identity model, and discovery.
- Fixed builders, tuples, and standard-list authorities.
- V1 pack schema and schema-less/flat parsing.
- Alternate pack filename probes.
- Raw identity readers and compatibility exports.
- Deprecated builtin aliases and their compatibility tests/docs.
- Independent bundled pack/skill inventories.

Keep proportionate gates:

- Exact prohibited-path checks for active `schema-pack.yaml`, alternate pack filenames, and retired parser/schema entry points.
- Exact import/AST checks for retired schema-pack modules, fixed composition authorities, and prohibited pack identity reconstruction.
- Loader/catalog semantic tests for strict v2 and provenance.
- Coverage and per-pack matrix gates.
- Source-isolated clean-wheel catalog and resource audits.

Do not use broad repository-wide regex scans that would flag historical, training, test-fixture, or unrelated component-manifest material.

Packaging:

- Extend ordinary package-data configuration for declared SQL, structured skills, Markdown, requirements, Blender’s service unit, component schemas, and current runtime assets.
- Exclude tests, caches, `.oracle` authoring inputs, and undeclared authoring-only files.
- Build one wheel for the final audit.
- Compare source and wheel declaration semantics, relative resource paths, content digests, documentation routes, database contributions, and trust class. Do not compare absolute owner roots.
- Regenerate the exact audit ledger and behavior matrix at boundary C.

Exit:

- No active alternate authority survives.
- Every declared resource is wheel-complete and loadable.
- Exact static gates catch prohibited residue without becoming a brittle textual policy engine.

### WP6 — authoritative validation and evidence closure

Estimate: **0.5–0.75 engineer-week**. Depends on WP5.

One authoritative owner runs each expensive validation once.

Run the required focused suite once in the final tree:

```bash
python3 -m pytest tests/packs tests/v10/test_catalog_migrations.py \
  tests/v10/test_m8_packaging.py tests/v10/test_pack_factoring.py \
  tests/v10/test_reference_repository.py tests/sdk/test_references.py \
  tests/sdk/test_extended_composition.py
python3 -m astrid doctor
python3 -m build
```

Using that single build artifact, run the source-isolated wheel load/resource/documentation audit.

Then run one full authoritative suite:

```bash
python3 -m pytest
```

Final contract scenarios also cover:

- Capability-only, database-only, and combined golden fixtures.
- Every current external discovery source: capability success and database rejection.
- Fresh, writable-upgrade, read-only-pending, and existing-four-pack SQLite paths.
- Name/version/dependency/cycle/collision/checksum/drift/transaction failures.
- Complete references and runaway round trips.
- Backup and restore.
- Inspect text and JSON stability.
- Doctor and inspect non-mutation.
- `_core` census drift.
- Exact legacy-authority gates.
- Final zero-unclassified, zero-conflict, zero-stale ownership gate.
- Final four-pack behavior matrix with explicit `N/A` reasons.
- Final wheel resource closure.

Focused tests during earlier packages may validate the code they change, but they do not repeat the expensive full suite, build, or clean-wheel audit.

If final validation exposes a suspected unrelated baseline failure, reproduce that specific failure against `7ac50c12e8e4d90988fee603ffdb9896e5628792`; do not rerun an entire baseline campaign.

Complete the evidence matrix mapping every frozen done criterion to:

- Command or deterministic audit.
- Artifact/result path.
- Outcome.
- Before/after evidence where applicable.
- Independent reviewer disposition.

After all evidence passes:

- Obtain the final Sol oracle review.
- Commit only reviewed paths.
- Push only `HEAD:refs/heads/megado/canonical-pack-beta`.
- Open the completed worktree.
- Do not merge, deploy, promote, or publish.

Exit:

- All 15 criteria have direct evidence and reviewer disposition.
- Final oracle disposition is passing and North-Star-aligned.

## Huge-run cumulative boundaries

The revised cadence uses three cumulative gates plus final review:

1. **Boundary A — canonical contract and authority foundation:** after WP1.

   Rationale: the field-level v2 contract, catalog lifetime, provenance rules, and resource grammar must be stable before 22-pack conversion fans out.

2. **Boundary B — bundled ownership and persistence cutover:** after WP3.

   Rationale: converted manifests and catalog-derived migrations must agree before operational consumers are rewired.

3. **Boundary C — operational hard cut and packaged product:** after WP5.

   Rationale: all consumers, deletions, documentation, coverage, and installed-wheel closure must converge before final validation.

4. **Final — evidence closure:** after WP6.

At A, B, and C:

- Regenerate the audit ledger and relevant matrices from the cumulative tree.
- Converge code, artifacts, receipts, and status on one checkpoint.
- Run exactly one cumulative independent review pass by default.
- Resolve accepted findings and obtain a fresh pass before dependent work continues.
- Do not substitute routine batch review for the cumulative gate.

## Done-criterion traceability

| Criterion | Primary packages |
|---|---|
| 1. Every bundled product pack is strict v2 | WP1, WP2, WP5, WP6 |
| 2. No independent identity parsing | WP1, WP4, WP5, WP6 |
| 3. Zero-unclassified coverage ledger | WP0, WP2, WP4, WP5, WP6 |
| 4. Manifest-derived database composition | WP3, WP5, WP6 |
| 5. Four-pack behavior preservation | WP0, WP2–WP4, WP6 |
| 6. Owner-relative migrations and safety | WP1, WP3, WP6 |
| 7. Operational-consumer agreement | WP3, WP4, WP6 |
| 8. Structured docs and `_core` census | WP2, WP4–WP6 |
| 9. Inspect and doctor output | WP4, WP6 |
| 10. Clean-wheel closure | WP2, WP5, WP6 |
| 11. Legacy authority deletion | WP1, WP5, WP6 |
| 12. External capability success/database failure | WP1, WP3, WP6 |
| 13. Three golden pack forms | WP1, WP6 |
| 14. Focused/full validation or baseline proof | WP0, WP6 |
| 15. Evidence matrix and oracle pass | WP0, WP6 |

## Explicit anti-pattern rejections

- **No hidden schema-pack subsystem.** Generic migration algorithms may move; schema-pack identity, manifest, parser, discovery, builders, and compatibility exports are deleted.
- **No fixed composition disguise.** Named packs appear only in expected test results and preservation evidence.
- **No universal service locator.** The catalog exposes declarations and narrow projections only; typed registries and static factories retain runtime construction.
- **No runtime ledger or configuration registry.** The coverage ledger is audit-only and never consulted by runtime code.
- **No YAML DDL or mutable state.** SQL owns schema; `schema_migrations` owns applied state.
- **No research lanes.** E1–E10 and Wave 1 investigations are resolved by this contract.
- **No lifecycle/plugin machinery.** No locks, enable/disable/purge state machine, dynamic database plugins, uninstall ceremony, dependency solver, marketplace, signing, sandboxing, or UI.
- **No external SQL.** External `database` fails before resource resolution.
- **No dynamically unloadable kernel.** Core migrations and `_core` remain irreducible.
- **No compatibility.** No v1, aliases-as-shims, dual reads, alternate filenames, schema-less manifests, fallbacks, or compatibility exports.
- **No generalized factory framework.** Static application, repository, SDK, CLI, and bridge wiring stays unless the frozen goal directly requires a projection change.
- **No custom packaging backend.** Use existing package-data mechanisms plus wheel verification.
- **No broad textual policing.** Retain exact prohibited file/import checks and favor semantic catalog, coverage, AST/import, and clean-wheel gates.
- **No validation ceremony.** WP0 records immutable baseline evidence; WP6 runs final integrated and expensive checks once.
- **No scope expansion into global models, LoRAs, taxonomies, or kernel primitives** unless the frozen zero-unclassified audit proves an existing bundled customization requires classification.
- **No hollow success.** Any active bypass, unclassified surface, missing documentation route, undeclared required asset, or missing wheel resource fails the run.

## Final disposition

This replacement is aligned with the complete North Star and frozen goal. It resolves the Wave 1 reopening without adding new systems: composition is algorithmic, the catalog boundary is narrow, v2 freezes before fan-out, resource closure is explicit, the ledger has a non-runtime lifecycle, four-pack behavior is proven per surface, and validation/static gates are proportionate.

The next Phase 3 action is an exact Sol `STABLE` check against this complete snapshot. If Sol returns exactly `STABLE`, run a fresh full settled-plan sense-check wave before accepting the plan as settled.



## Prior accepted Wave 1 synthesis and disposition

# Settled-plan wave 1 synthesis

Plan snapshot SHA-256:
`0e478ccea3a01cc53dbf379b02a9563f7a1108ee4dd012b32c2eef4b271fe52d`

## Accepted material changes

1. **Composition algorithm, not named set.** Standard composition selects every
   trusted bundled catalog entry with `database` and dependency-orders that
   projection. References/runaway/shots/timeline are an expected fixture result,
   never a runtime list or tuple.
2. **Narrow catalog boundary.** Define construction/lifetime/ownership and the
   permitted declaration/projection API. The catalog never constructs services;
   typed registries/static factories retain runtime construction ownership.
3. **Freeze a field-level v2 contract before parallel implementation.** Record
   required/optional fields, normalized types, contribution constraints,
   resource grammar, documentation routing, provenance/trust semantics, and
   invalid cases in schema plus golden fixtures.
4. **Define resource-closure completeness.** Every runtime/documentation file
   reachable through a declared contribution or used by pack runtime code must
   be declared through one typed resource or explicit supplemental resource.
   Closure is recursive, owner-relative, realpath-confined, source/wheel equal,
   and rejects undeclared required assets.
5. **Separate baseline from final validation.** WP0 captures immutable before
   artifacts; later packages turn changed contracts into automated tests. WP6
   consumes those artifacts and reruns only final contract scenarios, plus each
   expensive build/wheel/full-suite check once.
6. **Ledger lifecycle.** Regenerate/compare the audit ledger after conversion
   and at cumulative boundaries A/B/C, then perform the final exact gate. Do not
   let the WP0 snapshot become stale runtime truth.
7. **Per-pack behavior matrix.** Criterion 5 must map each of timeline, shots,
   references, and runaway across every applicable migration/repository/event/
   command/CLI/SDK/conformance surface, with explicit N/A reasons where a pack
   intentionally has no surface.
8. **Proportionate legacy gates.** Keep exact checks for prohibited files,
   imports, parser entry points, and fixed authorities. Prefer loader/catalog,
   coverage, AST/import, and clean-wheel semantic checks over broad textual
   regex scans that would flag historical or unrelated material.

## Rejected or narrowed findings

- Reject removing all static legacy checks as unsafe. Exact prohibited path and
  import gates remain necessary because a file can survive without being loaded
  by the happy-path catalog.
- Do not add a runtime ledger, configuration registry, new research lane, or
  generalized catalog service API to resolve these findings.

## Investigations resolved by plan contract

- Catalog lifetime: one immutable bundled catalog may be cached per process;
  local/external candidate discovery remains dynamic where it is dynamic today.
- Resource completeness: explicit typed/supplemental declaration plus recursive
  references and runtime-use audit; no custom packaging backend.
- V2 contract: schema/golden fixtures are the executable contract, frozen at WP1
  before conversion work fans out.

## North Star disposition

**Aligned after revision.** The accepted changes make “one authority” concrete,
preserve typed mechanisms and SQL authority, prevent a fixed-list disguise,
close docs/resources, remove redundant ceremony, and add no lifecycle/plugin/
marketplace scope.

Because the changes affect architecture, sequencing, and proof, the plan is
materially reopened. Sol must issue a complete revision, return `STABLE`, and a
fresh full settled-plan wave must run on the new snapshot.


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

