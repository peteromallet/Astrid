# Settled-plan wave 2 synthesis

Plan SHA-256:
`c5cfa3128be626c6a263d131b3a2baa3292c74d0fed3d2e12d86a607e5ad92b5`

## Accepted material changes

1. **Exact executable v2 field contract.** Freeze required/optional fields,
   normalized immutable types, enums, version grammar, typed contribution roots,
   alias/permission treatment, database dependency semantics, documentation
   route, supplemental resources, unknown-field rejection, and invalid fixtures
   in the plan—not merely as future WP1 design work.
2. **One operation snapshot.** Define one immutable `CatalogSnapshot` per
   top-level operation/composition. It combines the process-cached bundled
   catalog with a dynamic external candidate snapshot, applies one deterministic
   precedence/duplicate/trust policy, and is threaded through all projections;
   consumers cannot rescan inside the operation.
3. **Bounded resource-completeness algorithm.** Within every bundled pack root,
   every non-Python regular file is either reached by a declared typed resource,
   declared supplemental resource, or a narrowly typed authoring-only exclusion
   with reason. Directories expand recursively; symlinks/escapes reject. Pack
   runtime may not require undeclared files outside its root; move such assets to
   the owner or classify them as kernel-owned. AST/import checks cover known
   runtime resource APIs. Source/wheel digest equality then proves the declared
   closed set.
4. **Concrete coverage generator/diff.** Specify the command/artifact schema,
   canonical inputs, normalization/order, deleted-surface records, kernel
   justification rules, and exact missing/stale/duplicate/conflict comparison.
   Runtime never imports it.
5. **Deterministic database semantics.** Dependencies use an exact structured
   minimum migration-head integer, not release-version solving. Define graph
   nodes, core participation, validation, and tie-break. Preserve current
   applied migration identity/order where dependencies constrain it.
6. **One-build packaging proof.** Convert packaging unit tests to contract/
   inventory checks or make them consume the single prebuilt wheel artifact.
   WP6 performs one build, then all installed-wheel audits consume it.
7. **Reduce artifact ceremony.** Package-local ledger/matrix checks may run as
   focused validation; immutable regeneration/diff artifacts are required only
   at cumulative boundaries A/B/C and final closure.

## Resolved direction

- No new research lane is required. Sol may inspect v1 schema and existing
  discovery/registry contracts read-only while producing the replacement.
- Do not attempt perfect general static analysis of arbitrary Python file opens.
  The closed-world bundled-pack file classification plus targeted known-API AST
  checks is the proportional beta invariant.
- Do not introduce a dependency solver, persistent project lock, runtime ledger,
  service locator, packaging backend, or broad textual scanner.

## North Star disposition

**Conditionally aligned.** The architecture remains correct, but the plan cannot
be accepted until these executable boundary contracts replace prose ambiguity.
Sol must revise, return exact `STABLE`, and another fresh full settled-plan wave
must inspect the new snapshot.

