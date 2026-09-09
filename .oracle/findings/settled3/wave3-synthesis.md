# Settled-plan wave 3 synthesis

Plan SHA-256:
`b8797fe7dc1d5e806700106e7d3460ade61b26238295baf20e2d0fe8a1faff95`

## Accepted material changes

1. **Freeze source-inventory exclusions.** Replace the open-ended
   “cache/build metadata” exception with an exact fixed-path/name allowlist and
   matching rule. Exclusions cannot hide arbitrary files under pack roots;
   every remaining regular non-Python file is typed, supplemental, or justified
   authoring-only.
2. **Define provenance identity.** Freeze the root-independent value used for
   candidate identity, source/wheel comparison, duplicate handling, and any
   diagnostic correlation. It must be derived from canonical definition and
   declared content—not an ambient absolute path or vague source category.
3. **Simplify freshness semantics.** Remove the global snapshot fingerprint,
   rejected-diagnostic hashing, unstable-read retry system, and broad bundled
   stale-handle checks. A bundled catalog is immutable for its process/package
   lifetime; changing bundled source/package files requires a new lifetime (and
   tests explicitly clear/rebuild it). Dynamic external candidates are captured
   once per top-level operation, while external resource handles retain narrow
   size/digest verification immediately before the security-sensitive use that
   needs it.
4. **Reject legacy manifest-only directories during catalog discovery.** A
   bundled child with `pack.yml`, `pack.json`, or `schema-pack.yaml` but no
   `pack.yaml` is an error, not a non-pack directory to ignore. Exact legacy
   static gates remain defense in depth.
5. **Freeze one external trust/admission projection.** Identify the existing
   typed owner that evaluates active validated revision and accepted permissions;
   every external capability consumer must use its observable disposition.
   This is a projection from the operation snapshot, not a new universal trust
   service or manifest-supplied trust field.
6. **Make clean-wheel isolation executable.** The installed-artifact harness
   must run from outside the checkout with the checkout and source pack roots
   absent from `sys.path`/`PYTHONPATH`, then assert imported module/resource
   origins are inside the installed wheel environment.
7. **Specify baseline-independence receipts.** If a final full-suite failure is
   claimed as pre-existing, record the exact pinned source revision,
   environment, command, focused failing scenario, and controlled before/after
   result. Do not run a second baseline full suite or rebuild the wheel.

## Deduplication and dispositions

- The alternate-manifest sequencing finding was independently reported by two
  critics and is one accepted correction.
- The bundled-cache criticism and fingerprint-overhead criticism are resolved
  together by the simpler lifetime contract in item 3; no new cache invalidator
  or recursive per-operation bundled rescan is accepted.
- No finding widens scope. No dependency solver, project lock, lifecycle,
  service locator, runtime ledger, custom packaging backend, broad scanner, or
  repeated build is introduced.
- No investigation remains open; Sol can express these seven corrections as a
  complete replacement plan without a new research lane.

## North Star disposition

**Conditionally aligned.** The plan retains the correct canonical architecture,
but the accepted gaps could permit stale or alternate authority, ambiguous
external admission, or false wheel/baseline proof. Sol must revise, return exact
`STABLE`, and a fresh complete settled-plan wave must inspect the new snapshot.

