# Deep authority and next-step judgment

Date: 2026-08-31  
Target: `7ac50c12e8e4d90988fee603ffdb9896e5628792`  
Question: what governs, what is actually complete, and what is the smallest
direct canonical-pack beta execution with no shims?

## Verdict

The canonical-pack product cutover has not started. This worktree has no diff
from `7ac50c12` under `astrid/`, `tests/`, `docs/`, `scripts/`, or
`pyproject.toml`; all work from this run is planning/research material under
`.oracle`. The substantial pack, SQLite, repository, SDK, doctor, backup, and
wheel behavior in the tree is inherited substrate, not implementation by this
run.

The governing product scope is the North Star plus the frozen agent goal,
interpreted through the user's explicit beta exclusions. The 513-line prep plan
is the best delivery outline, but is subordinate where the later frozen goal
strengthened coverage, agent documentation/census, inspection, and doctor
requirements. The 2,317-line `.oracle/plan.md` is not safe to execute: it mixes
the required bundled hard cut with a rejected installed-pack security/lifecycle
redesign and a large bespoke audit/evidence platform.

Proceed with a five-seam hard cut. Keep the lightweight coverage ledger,
structured pack docs and `_core` census, useful inspect/doctor output, and a
clean-wheel proof because the frozen goal explicitly requires them. Drop the
installed-record v2/revision-inventory/snapshot-lifetime program, exhaustive
Python/file ownership, executable migration-effect framework, and receipt
bureaucracy.

## Completion assessment

| Measure | Completion | Basis |
|---|---:|---|
| Planning | **75%** | Custody, North Star, frozen goal, source exploration, a reduced architecture, and extensive independent review exist. A correctly scoped stable execution plan, frozen canonical-pack tasklist, and pre-execution gate do not. The current tasklist is unrelated residue and the current replacement plan requires material pruning. |
| Product delivery by this run | **0%** | Zero product-path diff; no implementation batch, product commit, wheel, or canonical-pack test was produced. None of the 15 exact done criteria is fully satisfied in canonical form. |
| Product readiness including inherited substrate | **~35%** | The existing migration/registry/repository/operation machinery substantially reduces implementation effort, but the defining v2 authority, conversion, projections, consumer convergence, resource/doc closure, and deletion are all absent. This is readiness credit, not completion credit. |

The ~35% readiness estimate is intentionally conservative. Across the five
reduced delivery seams, the inherited tree supplies roughly 10–20% of the v2
contract seam, 50–60% of the four-pack behavior seam, 45–55% of the database
engine seam, 40–50% of the operational behavior seam, and 10–20% of final
packaging/deletion closure. Weighting those by the prep plan's estimates yields
about 35–40%. The end-state acceptance score remains 0/15 fully complete.

## Authority order

Use this order when documents disagree:

1. **Current user direction and explicit exclusions.** No per-project
   composition lock, install/enable/disable/purge lifecycle, third-party DB
   packs, marketplace, dynamic factories, or compatibility shims.
2. **`.oracle/northstar.md`.** It defines the enduring one-pack architecture,
   resource/documentation requirements, external-DB boundary, and proportional
   beta scope.
3. **`.oracle/agent_goal.md`.** It is explicitly frozen and is the executable
   scope contract. In particular, lines 40–71 settle one filename, one complete
   immutable object, manifest-derived composition, no second state record,
   static factories, user-facing docs, `_core` census, and common operational
   ownership data. Lines 73–92 explicitly retain a lightweight coverage ledger,
   inspect text/JSON, doctor census/status, agent docs, and clean-wheel closure.
4. **`.oracle/custody.md` and source `7ac50c12`.** These govern provenance and
   behavior floors. Existing tests enforcing forms explicitly named for deletion
   are not end-state authority.
5. **The original 513-line prep plan.** Use its five-batch architecture and KISS
   boundary where consistent with the frozen goal. It correctly limits the
   catalog, preserves typed registries/static wiring, uses
   `database.default_enabled`, and defers lifecycle/marketplace work. Its own
   header says it was prepared, not stable; it does not override later goal
   additions.
6. **Prior Luna/Sol reports and this judgment.** They are evidence/adjudication,
   not scope authority. Their core implementation ledger is sound. The earlier
   Sol recommendation goes too far only where it discards inspect, doctor,
   documentation/census, or all coverage work; those are in the frozen goal.
7. **`.oracle/plan.md`.** Treat as a non-governing design notebook. Reuse narrow
   details only after checking them against items 1–5.
8. **`.oracle/status.md` and `.oracle/tasklist.md`.** Neither governs execution.
   Status is stale; tasklist is a storyboard plan for another project.

The last planning chronology also matters. Sol stability pass 9 declared the
then-current plan `STABLE`, but settled-plan Wave 7 ran afterward. Its
`_report.json` records 3/3 successful Luna tasks and the three outputs all say
the plan is not clean. Wave 7 is complete but unreceipted, and status was never
updated. Its installed-store confinement, undeclared external resource,
wheel-Python byte binding, Runaway ordering, evidence-cycle, and doctor/Python
ownership findings concern the overgrown plan; most disappear when that scope
is removed. It cannot be ignored or misreported as not run.

## What is truly done

### Done by this canonical-pack run

- An isolated worktree at the pinned source and a custody record.
- Frozen North Star and agent goal.
- Ten focused repository exploration lanes (with the E7 replacement), repeated
  settled-plan reviews, and source-oriented Luna/Sol gap reports.
- A clear inventory of the architectural split and reusable substrate.
- No product implementation.

The research and planning are useful, but plan stability does not count as
product completion. Historical storyboard briefs/checkins/evidence already in
`.oracle` are unrelated and must not be credited to this run.

### Inherited and reusable product substrate

- **Capability packs:** immutable `PackDefinition`, v1 schema/validation,
  layered bundled/local/extra/environment/installed discovery, typed executor,
  orchestrator, element, rendering, and generation registries, and existing
  install/update/rollback/trust machinery. Preserve the typed algorithms; do not
  redesign external lifecycle.
- **Database packs:** a strict immutable schema-manifest parser and frozen
  collision registry covering IDs, migrations, tables, vocabulary,
  repositories, conformance, CLI mounts, and bridge mounts.
- **Migration safety:** dependency ordering/cycle rejection, exact-byte
  checksums, drift and too-new refusal, read-only probing, and per-migration
  transactions. `DatabaseWriter`, `UnitOfWork`, repositories, receipts, and
  conformance are real.
- **Four real product slices:** timeline, shots, references, and runaway already
  have SQL migrations and repository behavior. References already owns its
  three-table SDK/CLI/product slice. Runaway already has its one-table typed
  repository and command behavior. The work is custody conversion, not a data
  model rewrite.
- **Operations:** application composition, registry injection, long-lived SDK
  propagation, doctor, backup/restore, and read probes already work against the
  old registry seam.
- **Distribution/docs floor:** an installed-artifact harness, package-data
  tests, `_core` skill, and 17 top-level product-pack skills already exist.

Independent verification for this judgment ran:

```text
python3 -m pytest -q \
  tests/v10/test_registry.py \
  tests/v10/test_catalog_migrations.py \
  tests/v10/test_standard_application.py \
  tests/v10/test_doctor.py \
  tests/v10/test_backup_restore.py \
  tests/v10/test_reference_repository.py \
  tests/sdk/test_references.py

179 passed in 31.80s
```

This proves the inherited floor, not canonical convergence.

## What is not done

1. **No v2 authority.** There is no `CanonicalPack`, `BundledCatalog`, or
   equivalent complete catalog object. `PackDefinition` remains a v1-oriented
   object, and runtime/static validation remain separate paths.
2. **No strict one-form loader.** `_common.py:16` accepts `pack.yaml`,
   `pack.yml`, and `pack.json`; `loader.py:110-152,184-240` supplies defaults,
   accepts schema-less mappings, and contains the flat parser fallback.
3. **No bundled conversion.** The tree has 19 `pack.yaml`, all v1, plus four
   `schema-pack.yaml`. Timeline, shots, references, and runaway are not ordinary
   canonical packs.
4. **No derived default composition.** Both
   `astrid/core/schema_packs/standard.py:27-45` and
   `astrid/packs/__init__.py:68-110` hard-code timeline/shots/references.
   Other consumers repeat or reconstruct the same old authority.
5. **No owner-relative canonical migrations.** The runner rebuilds migration
   roots from pack IDs (`runner.py:113-138`), and dependency minimum versions
   are parsed but not enforced by the ordering path.
6. **No operational convergence.** Application, standalone SDK, kernel reads,
   rendering reads, doctor, restore, timeline edit helpers, and raw CLI mount
   reading still construct or reparse legacy composition independently.
7. **No hard deletion.** `builtin/pack.yaml` remains solely as a compatibility
   namespace. Current manifests contain 49 `builtin.*`, nine `external.*`, and
   one other deprecated alias. Four schema manifests, schema parser/model,
   fixed builders, v1/flat/alternate loading, and compatibility-oriented tests
   remain active.
8. **No final resource/doc closure.** Package data explicitly names the three
   legacy schema packs and excludes skills. Five retained product-pack
   directories currently lack top-level structured guidance: `blender`,
   `timeline`, `shots`, `references`, and `runaway`. The required generated
   `_core` census is absent.
9. **No goal-sized inspection/evidence closure.** Useful canonical inspect and
   doctor output, a lightweight zero-unclassified customization ledger, clean
   v2 wheel proof, and final criterion matrix have not been implemented.

## What to retain from the 2,317-line plan

- One strict v2 grammar, one normalized immutable definition/catalog entry, and
  one deterministic bundled catalog.
- Exactly 22 retained product packs after deleting `builtin`, with `_core` as
  irreducible guidance.
- Mechanical conversion of all manifests and all four database declarations.
- Bundled provenance is trusted; external `database` rejects before SQL or
  migration-resource access.
- Existing typed registries and static service/CLI/bridge factories remain.
- Owner-relative resource handles for declared runtime resources and migrations.
- Dependency minimum-head enforcement, or a simpler dependency grammar that is
  fully enforced.
- Structured documentation and `_core` census, with the frozen goal's explicit
  justified opt-out only for genuinely non-user-facing internal packs.
- Minimal pack inspect text/JSON and doctor catalog/migration status.
- A deterministic temporary Runaway fixture instead of restoring the absent
  historical demo.
- Clean source/wheel closure and final evidence mapped to the 15 goal criteria.

## What is overengineering or out of scope for beta

### Remove entirely

- **Strict installed-record v2, immutable complete revision inventories, and
  write-once revision publication.** These are a redesign of the installed-pack
  lifecycle explicitly deferred by the goal. Keep existing external capability
  install/update/rollback behavior; only require v2 manifests and reject an
  external `database` contribution.
- **Capture-time executable admission and post-capture lifetime semantics.**
  Operation freezing, revision A/B activation tests, permission mutation,
  revision invalidation, lazy-import origin enforcement, per-use manifest/resource
  receipts, and tamper contracts are not needed to unify bundled packs.
- **A universal `CatalogSnapshot` over bundled plus all dynamic external
  candidates.** Build a deterministic bundled catalog. Existing external
  capability discovery can remain on its current path, using the v2 definition
  and early DB rejection where required.
- **Exhaustive source-tree classification.** `authoring_only`, every-file routing,
  complete bundled Python-module ownership, runtime AST read scans, exact
  source/wheel Python module equality, and file-by-file ownership receipts turn
  pack unification into a repository-wide provenance system. Retain only
  declared runtime-resource closure and the frozen goal's lightweight
  customization-surface ledger.
- **Executable table-effect ownership infrastructure.** Do not add a migration
  observer hook, second disposable execution audit, or elaborate claimed-table
  evidence protocol. Existing SQL remains authoritative; preserve registry
  collisions and add ordinary fresh-schema assertions sufficient to catch
  declaration drift.
- **Operation receipt identity and special Runaway exactly-once machinery.** A
  deterministic `tmp_path` round trip is enough. No product schema for
  provenance receipts or JUnit extractor is required.
- **Custom coverage/evidence platforms.** Do not add a generalized inventory
  diff engine, plan-digest binding, schema-checked fifteen-row product tool, or
  one-command-only installed lane. A reviewed ledger plus ordinary test/build
  artifacts and a concise final matrix satisfy the frozen goal.

### Narrow rather than remove

- **Inspection:** keep it because the goal requires it, but expose only canonical
  identity/source, capability contribution summary, DB ownership/head,
  documentation, and declared resource closure. Omit installed revision
  inventory/admission/tamper diagnostics.
- **Doctor:** keep catalog census, declared-resource/doc health, and
  expected/applied/pending migration status. Do not make runtime doctor consume
  an offline Python-ownership ledger or rescan the source tree. Wave 7 correctly
  identified that contradiction.
- **Coverage:** inventory product custom surfaces and consumers—pack,
  capability/extension IDs, DB declarations, CLI/SDK/bridge mounts,
  documentation, and operational consumers. Do not inventory every Python
  module or arbitrary file.
- **Documentation:** retain structured docs and generated `_core` routing. Apply
  the goal's user/agent-facing rule and explicit internal opt-out; do not turn
  every source file into documentation evidence.
- **Wheel proof:** adapt the existing installed-artifact harness to load v2
  manifests, declared resources/migrations, skills, census, and a standard DB
  outside the checkout. Exact one-build orchestration is sensible validation
  discipline, not a new product contract.

### Correct direct contradictions

- Restore `database.default_enabled`. Selecting every bundled DB contribution,
  as current plan §VI does, changes current behavior and ignores the reduced
  architecture. Preserve default composition with
  `timeline=true`, `shots=true`, `references=true`, `runaway=false`; prove
  runaway through an explicit extended composition.
- A consumer-facing canonical entry must retain definition plus root, manifest,
  source/provenance, declared resources, and optional database contribution.
  Splitting value types internally is fine, but consumers must not reconstruct a
  complete pack by joining independent authorities.
- Do not require docs for internal packs without the goal's explicit opt-out
  mechanism. Conversely, do not drop docs/census; they are frozen requirements.

## Remaining decisions

Only one contract-level choice is genuinely unresolved before execution:

1. **The YAML scalar type for `schema_version`.** The prep example and accepted
   forms use string `"2"`; the 2,317-line plan uses integer `2`; the frozen goal
   says only “version 2.” Pick one at the contract gate and make schema, loader,
   fixtures, all manifests, and docs agree. Recommendation: use integer `2`,
   matching every current v1 YAML manifest and normal JSON-Schema version
   practice, but explicitly amend the prep example rather than silently
   contradicting it.

The following are not open product questions and should be frozen as execution
facts:

- Default DB composition preserves current behavior: timeline, shots, and
  references enabled; runaway opt-in.
- External capability manifests must use v2 after the hard cut, but existing
  installed-store record/lifecycle semantics are not redesigned.
- All 59 current aliases are deprecated compatibility shims and are deleted.
  The v2 grammar may retain non-deprecated pack-owned aliases for real aliasing.
- Static repositories, services, CLI, and bridge wiring remain.
- Existing schema SQL and four product semantics remain byte/behavior stable.
- Missing structured docs are filled for user/agent-facing packs; any internal
  opt-out is explicit in its manifest and visible in the census.

Pack-model class naming, exact internal module placement, and whether the
catalog is process-cached are engineering details, not user decisions, provided
there is one complete immutable consumer authority and no independent rereads.

## Minimal exact execution sequence

### Gate 0 — replace planning authority, no code

- Mark the current replacement plan non-executable and the storyboard tasklist
  unrelated.
- Freeze a short tasklist from the five seams below.
- Record the one schema-version scalar decision.
- Preserve the 15 goal criteria as the final checklist; do not add criteria.

Exit: one scoped tasklist and pre-execution review agree with North Star, frozen
goal, user exclusions, and this judgment.

### 1 — strict v2 object and bundled catalog

- Evolve the current pack model/loader into one complete immutable canonical
  entry. Do not build a parallel universal registry.
- Accept exactly `pack.yaml` v2; reject alternate names, schema-less/defaulted
  identity, flat parsing, v1, unknown fields, traversal, and symlink escapes.
- Add optional `database`, structured documentation/opt-out, declared resources,
  and `database.default_enabled`.
- Build one deterministic bundled catalog that parses each bundled manifest
  once and exposes narrow capability/database/resource/doc projections.
- Preserve existing external discovery/store behavior; external `database`
  rejects as a whole before SQL/resource use.
- Add capability-only, database-only, combined, legacy-invalid, path-invalid,
  and external-DB-invalid fixtures.

Gate: one object/path, strict forms, root confinement, three golden forms,
external DB rejection, and no installed lifecycle additions.

### 2 — convert the bundled tree mechanically

- Delete `builtin` and the 59 deprecated alias declarations.
- Convert the remaining 18 capability manifests to v2.
- Add v2 `pack.yaml` to timeline, shots, references, and runaway, merging the
  current schema declarations without changing SQL or product behavior.
- Set default flags: timeline/shots/references true; runaway false.
- Add/declare structured guidance for user/agent-facing packs, including the
  five current gaps unless a reviewed internal opt-out is justified.
- Make references the combined exemplar and generate the `_core` census from
  the catalog.

Gate: 22 retained bundled product packs load from one form; all four DB packs
are ordinary packs; SQL/resources remain owner-confined; no compatibility alias
survives.

### 3 — project databases through the existing engine

- Project canonical database declarations into the surviving immutable
  collision registry; remove schema-pack identity from the projection.
- Carry owner root and migration resource handle into the runner.
- Enforce dependency minimum heads (or simplify the grammar before conversion).
- Derive the standard registry only from bundled entries with
  `default_enabled=true`; derive explicit extended composition through the same
  projection.
- Delete both hard-coded standard tuples/builders as their call sites move.
- Preserve `schema_migrations`, checksum/drift/order/transaction behavior,
  `DatabaseWriter`, `UnitOfWork`, repositories, and conformance.

Gate: fresh default DB, existing default DB reopen, explicit runaway-extended
DB, read-only pending behavior, dependency/collision/drift/rollback tests, and a
temporary Runaway round trip pass.

### 4 — converge actual consumers and required surfaces

- Construct the bundled catalog/database projection at top-level application or
  operation boundaries and pass it to application, `AstridClient`, standalone
  SDK/read helpers, rendering reads, bridge composition, doctor, backup, restore,
  inspect, and package validation.
- Preserve exact client registry propagation and static typed service/CLI/bridge
  factories.
- Replace raw manifest reads such as CLI mount reconstruction with catalog
  projections; do not make mounts dynamic.
- Extend existing inspection with minimal stable text/JSON and doctor with
  catalog census plus expected/applied/pending migration status.
- Make backup/restore validate against the same expected projection without
  inventing snapshot digests or new state records.

Gate: all named consumers report the same ordered default composition and retain
current safety/feature behavior.

### 5 — hard deletion, lightweight coverage, docs, and wheel closure

- Delete all four `schema-pack.yaml`, the separate schema manifest/parser and
  standard-composition authorities, v1/flat/alternate loader paths, raw identity
  readers, fixed tuples, compatibility aliases, and tests/docs that require
  them. Move/reuse collision and migration algorithms rather than deleting them.
- Complete the customization-surface coverage ledger with zero unclassified
  product surfaces or unjustified kernel owners; do not enumerate every Python
  module/file.
- Package every canonical manifest, declared migration/resource, structured
  pack doc, nested skill required at runtime, and generated `_core` census.
- Replace the stale three-schema factoring assertion and historical Runaway-demo
  tests with final-state catalog and temporary-fixture tests.
- Run focused pack/database/consumer/docs tests, build one clean wheel, run the
  existing outside-checkout installed-artifact lane adapted for v2, run doctor,
  then run the full suite once.
- Produce a concise final matrix mapping the 15 frozen criteria to commands,
  results, artifacts, and independent review. No new evidence framework is
  needed.

Final gate: zero legacy authorities/shims, 22 canonical bundled packs, three-pack
default plus explicit runaway composition, one shared operational projection,
source/wheel resource and documentation closure, focused/full green results,
and independent oracle pass.

## Final adjudication

Do not continue plan-revision Wave 8 and do not execute `.oracle/plan.md` as
written. Planning has enough research; the next useful act is a short corrected
tasklist and pre-execution gate, followed immediately by the strict v2
object/catalog seam.

The beta is neither “mostly implemented” nor greenfield. It is a strong inherited
system awaiting a substantial but bounded authority consolidation. The cleanest
path is the original five-batch hard cut, strengthened only by the frozen goal's
lightweight coverage, documentation/census, inspect/doctor, and final evidence
requirements.
