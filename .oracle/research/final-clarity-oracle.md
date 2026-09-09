# Final clarity oracle — canonical pack beta reconciliation

Date: 2026-08-31  
Audited HEAD: `7ac50c12e8e4d90988fee603ffdb9896e5628792`  
Audited artifacts: `.oracle/implementation-ledger.md`, `.oracle/tasklist.md`,
`.oracle/status.md`, archived `.oracle/plan.md`, frozen goal/North Star, source,
conversation reconstruction, and prior `deep-authority-and-next.md`.

## Oracle verdict

**Not yet 100% clear. Correctable without another planning wave.**

The four active artifacts now get the central truth right:

- the prior canonical-pack run performed planning/research only;
- its product diff is zero;
- Astrid's mature capability/SQLite/SDK/operations machinery is inherited;
- the canonical v2 cutover is 0/15 complete;
- the overgrown replacement plan is non-executable history;
- Wave 7 completed 3/3, was not clean, and was unreceipted;
- the remaining product work is a bounded five-seam hard cut; and
- locks, lifecycle expansion, external DB packs, marketplaces, shims, and the
  installed-revision security program are excluded.

That is a major improvement and is sufficient for a human to understand the
project. It is not yet safe to call the reconciliation perfectly closed or the
tasklist frozen because several statements and dependencies conflict, two goal
proofs are not explicit tasks, and unrelated top-level run artifacts can still
look authoritative to automation.

Assessment:

| Dimension | Judgment |
|---|---|
| Historical truth | **PASS** |
| Inherited-vs-run attribution | **PASS** |
| Frozen 15-criterion coverage | **CONDITIONAL PASS** |
| Scope proportionality | **PASS** |
| Execution ordering | **FAIL pending bounded corrections** |
| Evidence namespace clarity | **FAIL pending archival/labeling** |
| Ready to mark clarity goal complete now | **NO** |
| Ready after corrections below | **YES** |
| Canonical-pack product goal complete | **NO — remains 0/15** |

No product code should be written until the small consistency corrections are
applied and rechecked. No additional Luna/Sol plan-revision wave is warranted.

## Evidence cross-check

The active claims about the product remain source-true:

- `git diff --name-only 7ac50c12 -- . ':(exclude).oracle'` returns zero files.
- Current source has 19 `pack.yaml`, all v1, and four
  `schema-pack.yaml`; no v2 catalog implementation is present.
- `astrid/core/pack/_common.py:16` still admits three manifest filenames.
- `astrid/core/pack/loader.py:110-152,184-240` still defaults fields and keeps
  schema-less/flat fallback behavior.
- The two fixed standard authorities remain in
  `astrid/core/schema_packs/standard.py:27-45` and
  `astrid/packs/__init__.py:68-110`.
- Migration resources are reconstructed from pack ID in
  `astrid/core/migrations/runner.py:113-138`; dependency minimum heads are not
  enforced by the current ordering path.
- Current package data names the three old standard schema packs and excludes
  skills (`pyproject.toml:79-95,109-123`).
- The direct documentation census is 17/22 retained product packs, with
  `blender`, `timeline`, `shots`, `references`, and `runaway` missing.
- Current aliases comprise 49 `builtin.*`, nine `external.*`, and one other
  deprecated alias: 59 compatibility declarations total.
- The inherited registry/migration/application/doctor/backup/reference floor
  passed the 179-test focused verification recorded in the ledger and prior
  oracle report.
- `python3 -c 'import build'` still raises
  `ModuleNotFoundError: No module named 'build'`; wheel closure remains
  untested, as the ledger states.

The product status `NOT STARTED`, final criteria `0/15`, and zero product diff
are therefore correct. The ~35% figure is properly labeled inherited readiness,
not product completion.

## What the active artifacts now explain correctly

### Actual prior goal

The authority chain is clear and correct: current user direction, North Star,
frozen agent goal, custody/source, implementation ledger, then tasklist. The
original prep plan is useful proportional architecture; the large replacement
plan is history only.

The ledger accurately restores goal details that the earlier narrow Sol report
would have dropped: lightweight zero-unclassified customization coverage,
structured pack documentation, generated `_core` census, useful pack inspect
text/JSON, doctor census/migration status, clean-wheel closure, and a final
15-criterion evidence matrix are required. Exhaustive Python/file attestation
and runtime audit-ledger use are not.

### Work performed by the run

The ledger correctly records custody, one Sol plan, ten accepted Luna research
areas with one E7 replacement output, nine revision/stability cycles including
failed/rejected retries, and seven three-Luna settled waves. It correctly uses
`findings/settled7/_report.json` as proof that Wave 7 ran and records its lack of
a receipt/status update.

The statement at ledger lines 257–258 that the run “stopped before a canonical
tasklist” is historically correct only if read as the stopping point of the
original run. Since the reconciliation subsequently created a tasklist, change
this to “the original run stopped before...” to avoid a present-tense
contradiction.

### Inherited foundation

The pack-by-pack ledger is unusually useful: it names all 22 retained packs,
their current behavior, documentation state, and exact canonical delta. The
database and operational sections distinguish reusable algorithms from missing
authority convergence. This is the right level of implementation handoff.

One wording correction is required: `PackDefinition` is a frozen dataclass
shell, but it contains mutable `dict` fields (`definition.py:31-53`). Calling
the current complete object “immutable” or implying deep normalization
overstates the substrate. Say it is a frozen record with reusable normalized
fields whose mutable mappings must become deeply immutable in v2.

### Remaining scope

The five tasklist sections cover every frozen criterion at least nominally and
reject the overgrown plan's major scope additions. Integer
`schema_version: 2`, three-default/Runaway-opt-in composition, deletion of the
59 deprecated aliases, the 22-pack target, five missing skills, static typed
factories, and no installed-record redesign are now explicit decisions rather
than open questions.

## Material corrections required

### C1 — make “frozen” and completion state internally consistent

Current conflict:

- tasklist line 3 says **“reconciled and frozen for execution”**;
- tasklist lines 235–236 and ledger lines 427–430 say planning is only 75%
  complete and a pre-execution consistency check remains;
- status line 3 says reconciliation is **COMPLETE** and line 25 says no blocker;
- tasklist P0.8 is already checked as complete.

Those cannot all be true before this final audit is applied.

Correction:

1. Add one final P0 item: apply this oracle's corrections, verify the frozen
   15-criterion trace and dependency graph, and record the pre-execution pass.
2. Until it is checked, call the tasklist “reconciled draft pending final
   consistency gate,” status reconciliation “CORRECTIONS REQUIRED,” and next
   action “apply final clarity corrections,” not B1.
3. After it passes, mark reconciliation/planning clarity **100% complete** and
   tasklist frozen. Keep product implementation **NOT STARTED**, product
   delivery **0%**, and criteria **0/15**.
4. Either remove the old 75% number or label it explicitly as the state before
   the current reconciliation. It is stale once the tasklist and final gate
   exist.

This does not claim the product goal is complete. It closes only the active
clarity/planning-reconciliation goal.

### C2 — repair the impossible B1/B2 green-gate sequence

Tasklist B1 simultaneously requires:

- production accepts only v2 and rejects v1 (B1.3–B1.4);
- the bundled catalog parses every bundled manifest (B1.7); and
- typed registries still work at Gate B1.

But all bundled manifests remain v1 until B2. A green B1 checkpoint is therefore
impossible unless implementation adds a temporary dual loader/shim, breaks the
bundled product, or quietly converts manifests early.

Correction: make B1 a **contract/fixture gate only**. It may implement the v2
model, strict parser, and catalog against isolated golden fixture roots, but it
must not replace the active bundled production path before conversion. B2 then
converts all manifests and atomically activates the strict bundled v2 catalog.
No v1-to-v2 compatibility adapter or dual runtime read is allowed.

Alternatively combine B1 and B2 into one atomic cutover batch. The first option
retains the current ownership split with the smallest edit.

Gate wording should become:

- B1: v2 model/parser/catalog are fixture-proven; current runtime remains the
  pinned baseline; no compatibility code added.
- B2: all 22 manifests convert and the runtime flips atomically to v2; v1 forms
  fail from this boundary onward.

### C3 — state the no-dual-authority cutover boundary

B2 adds database declarations to four new `pack.yaml` files, B3 creates the
projection, B4 moves consumers, and B5 deletes `schema-pack.yaml` and its parser.
Without an explicit boundary, B2–B4 can be read as an accepted period with two
active database declarations, contradicting the North Star and no-shim goal.

Correction: declare B2–B4 an unshipped cutover tranche and identify one atomic
activation boundary. Before activation, only the legacy source is active;
after activation, only canonical v2 is active. Old schema manifests/code may
remain physically present briefly for mechanical deletion, but no active
consumer may read them and no checkpoint may be described as a shippable dual
authority.

For maximum clarity, delete the four `schema-pack.yaml` files in the same
activation batch that flips the last consumer, rather than deferring them to a
generic B5 cleanup.

### C4 — fix B3/B4 deletion ordering

Tasklist B3.5 says remove both fixed standard builders “as their consumers
move,” Gate B3 says no fixed list remains, but consumers do not move until B4.
B5.3 then lists fixed tuples for deletion again.

Correction:

- B3 builds and tests the catalog-derived projection through explicit injection;
  it does not delete a builder still used by production consumers.
- B4 moves every consumer, then deletes both fixed builders and raw mount reads
  at the atomic activation boundary.
- B5 retains only a zero-legacy verification gate, not a second deletion task.

This gives every batch a realizable dependency and avoids either breakage or a
shim.

### C5 — resolve dependency grammar before manifest conversion

Tasklist B3.3 says enforce dependency minimum heads “or simplify the grammar
before manifest conversion,” but manifest conversion already occurs in B2.
B1.5 also calls dependencies “fully enforced” before the database projection
exists.

Correction:

- B1 freezes the grammar. Adopt the already selected minimum-head semantics
  (`depends_on` pack plus positive minimum migration head), or remove the
  minimum field at B1—not B3.
- B2 writes only that frozen shape.
- B3 implements and proves the frozen semantics in the real projection/runner.

No decision remains after this clarification; the recommended and already
documented outcome is to keep and enforce minimum migration heads.

### C6 — add the missing external-capability success proof

Criterion 12 requires both halves:

1. external capability-only packs still work; and
2. external `database` rejects closed.

B1.8 and B1.9 explicitly test rejection but do not require a positive v2
external capability execution/discovery test after the hard cut. B5 names
criterion 12 but contains no corresponding explicit task.

Correction: add a golden external capability-only v2 pack that succeeds through
the existing supported external discovery/install path, plus otherwise-identical
fixtures with `database` for local/extra/environment/installed sources that
reject before SQL/migration resource access. Re-run the positive case in the
clean installed-artifact lane. This must not redesign installed records.

### C7 — prove resource completeness, not only declared-resource existence

The frozen goal requires missing **and undeclared** resource gates. Current
tasks prove confinement and that every declared resource loads, but the
lightweight coverage ledger in B2.9 omits runtime-resource surfaces. An actual
pack-relative runtime read could remain undeclared and still pass “every
declared resource exists.”

Correction: add a bounded resource-use inventory covering existing typed
component/rendering loaders and explicit pack-relative file reads. Every known
runtime resource must be reached by a canonical declaration or justified
kernel owner, and the source/wheel check must compare that declared set. This is
not the rejected every-file/Python ownership system: do not classify arbitrary
authoring files or every `.py` module.

Add `runtime_resource` ownership to B2.9's lightweight ledger and a zero-known-
undeclared-resource check to B5.

### C8 — make documentation policy singular

B2.7 orders five new direct skills and validation of all 22 documentation
roots, while also allowing an internal opt-out. B5.4 assumes 22 pack
skills/docs are included. The current intended result appears to be a direct
document for all 22 retained packs, which also satisfies the user's strengthened
documentation requirement.

Correction: freeze one statement:

- Preferred: all 22 retained product packs ship direct structured guidance;
  no bundled opt-out is used in this beta. The general v2 grammar may retain an
  explicit justified opt-out for future genuinely internal packs.

If an actual bundled opt-out is discovered during conversion, B5 must say “all
declared docs plus explicit reviewed opt-outs,” not “22 skills/docs.” Do not let
the tasklist promise both outcomes.

### C9 — add the known build-environment prerequisite

The ledger honestly records that the Python `build` module is absent, but the
tasklist jumps directly to `python3 -m build` closure. This is not an
architecture blocker, yet it is a known execution prerequisite.

Correction: add a validation-environment preflight before B5.8 that provides the
project's declared build tooling in an isolated environment and records its
version. Do not treat installing a tool as product completion or silently waive
the clean-wheel criterion.

## Evidence-namespace correction required

The large plan now has a strong non-executable banner, but it still occupies
the canonical path `.oracle/plan.md` and contains 2,300+ lines of imperative,
contradictory work packages. A human reading line 1 sees the warning; an
automation or Megado convention that consumes `.oracle/plan.md` may not.

For 100% clarity, do one of:

1. move the full body to
   `.oracle/prior-runs/canonical-pack-overgrown-plan.md` and replace
   `.oracle/plan.md` with a short redirect to the frozen goal, ledger, and
   authoritative tasklist; or
2. replace `.oracle/plan.md` with a concise executable five-batch plan and put
   the historical body under `prior-runs`.

The second is structurally cleaner, but the first is enough for the active
clarity goal. Merely adding a banner leaves machine-facing ambiguity.

Several other top-level artifacts are unrelated historical material:

- `.oracle/evidence/final-matrix.md` is explicitly a storyboard evidence matrix;
- `.oracle/checkins/batch-1.md`, `batch-2.md`, and `batch-2-rework.md` concern a
  prior run-ledger project;
- `.oracle/briefs/pre-exec-review.md` is not a completed canonical-pack
  pre-execution receipt; and
- `.oracle/execution.log` stops in the old revision-loop chronology and is not
  the current status authority.

These files are clear when opened, but their canonical-looking locations can
falsely imply that canonical-pack execution/checkins/final evidence exist.
Archive them under named prior-run directories or explicitly enumerate them as
non-authoritative historical artifacts in the ledger/status. The existing
ledger's general statement about unrelated history is not enough when a file is
literally named `evidence/final-matrix.md` and criterion 15 remains pending.

## Frozen 15-criterion trace audit

| Criterion | Current task coverage | Oracle disposition |
|---|---|---|
| 1. Strict v2 bundled packs | B1, B2, B5 | Covered after C2/C3 atomic-cutover correction |
| 2. One parsed authority | B1, B4, B5 | Covered after C2/C4 sequencing correction |
| 3. Zero-unclassified customization | B2.9, B5.10 | Covered, but add runtime resources per C7 |
| 4. Manifest-derived default composition | B3 | Covered; preserve three true/Runaway false |
| 5. Four-pack semantics | B2, B3, Runaway fixture | Covered |
| 6. Owner-relative migrations/dependencies | B1, B3 | Covered after C5 grammar timing correction |
| 7. Operational agreement | B4 | Covered after C3/C4 activation boundary |
| 8. Pack docs and `_core` census | B2, B5 | Covered after C8 wording correction |
| 9. Inspect and doctor | B4 | Covered at proportionate scope |
| 10. Clean-wheel closure | B5 | Covered after C7/C9 resource and build preflight additions |
| 11. Legacy deletion | B2, B4, B5 | Covered after single-owner deletion boundary is stated |
| 12. External capability/DB policy | B1, nominally B5 | **Missing positive external capability proof; add C6** |
| 13. Three golden forms | B1, B2 | Covered |
| 14. Focused/full validation | B5 | Covered; current 179 tests are baseline only |
| 15. Evidence matrix/oracle | B5.10–B5.11 | Covered; stale storyboard matrix must be archived/labeled |

No frozen criterion calls for installed-record v2, revision inventories,
snapshot lifetime, exhaustive Python ownership, a SQL observer, or a bespoke
evidence platform. Their exclusion remains correct.

## Exact correction sequence for the clarity goal

1. Apply C1: add/finalize the reconciliation gate and remove stale 75%/frozen
   contradictions.
2. Apply C2–C5 to task dependencies and gate wording. Record B1 as fixture-only
   contract work and the B2–B4 activation as one unshipped atomic cutover
   tranche.
3. Add C6 positive external capability proof, C7 bounded resource completeness,
   C8 singular docs policy, and C9 build preflight.
4. Correct the two ledger phrasings: “original run stopped before tasklist” and
   “frozen record with mutable mappings,” not fully immutable.
5. Move the overgrown plan body and unrelated storyboard/run-ledger
   checkins/evidence to explicit prior-run locations, or add an exact
   non-authoritative artifact inventory if movement is intentionally deferred.
6. Re-run read-only truth checks: zero product diff, 19 v1/four schema census,
   59 alias census, 17/22 docs census, fixed-builder/source callsite scan, and
   goal-to-task trace.
7. Record a final reconciliation PASS. Then set:
   - clarity/reconciliation: **COMPLETE**;
   - planning/tasklist: **100% clear and frozen**;
   - product implementation: **NOT STARTED / 0%**;
   - frozen product criteria: **0/15**;
   - next action: **B1 fixture-only v2 contract/model/parser work**.

## Completion decision

The active clarity goal **can be marked complete after these bounded
corrections**. No further broad research, settled-plan wave, product mutation,
or user decision is required. Integer schema version, default composition,
alias deletion, docs target, static factories, and beta exclusions are already
decidable from the frozen goal and conversation.

Do **not** mark the canonical-pack implementation goal complete. It remains
0/15, with zero product files changed. The completed clarity goal should hand
off an honest, dependency-valid tasklist whose first action is the isolated v2
contract/fixture seam, followed by one atomic bundled cutover with no runtime
shim or dual-authority release.
