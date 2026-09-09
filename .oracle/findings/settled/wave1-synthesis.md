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
