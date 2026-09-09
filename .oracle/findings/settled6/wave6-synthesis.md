# Settled-plan wave 6 synthesis

Plan SHA-256:
`e910347401c061da0a28ed64f2cf413e145883a0e3f1d8e7a64efb9ffde1ac2e`

## Accepted material changes

1. **Bind installed executable Python at snapshot capture.** Strict v2 install
   records include a normalized inventory/digest of every regular file in the
   installed revision, including Python modules. Capture-time admission
   recomputes and matches the complete revision inventory before selecting the
   candidate; lazy imports must originate within that captured revision root.
   Astrid writes revisions once and activates by changing store state, never by
   mutating revision contents. Out-of-band mutation after successful snapshot
   capture is local tampering outside the supported operation contract and is
   observed on the next capture; no continuous watcher, lock, or per-use tree
   rehash is added. Consumed non-Python resource handles retain their narrow
   immediate pre-use digest check.
2. **Verify declared table ownership against migration effects.** Table names
   remain ownership claims, not DDL. The bundled database validator executes the
   complete ordered migration graph in a disposable SQLite database using the
   real migration runner and transaction rules, introspects `sqlite_schema`
   before/after each migration, and proves that each claimed table is first
   created by its owning migration and every newly created user table is claimed
   exactly once. Later alters do not transfer ownership. This is execution plus
   introspection—not SQL parsing, YAML columns/constraints/indexes, or a new
   runtime database state record.
3. **Specify backup/restore as catalog database-projection consumers.** Backup
   creation receives the operation snapshot's ordered bundled database
   projection and compatibility result, records expected heads plus actual
   `schema_migrations`, and refuses an incompatible read. Restore uses the same
   projection to validate/apply the target composition before data restoration.
   A scenario receipt binds both operations to the ordered pack/provenance/head
   identities and proves agreement with doctor/inspect/application.
4. **Run the generated Runaway round trip once.** Focused pack commands exclude
   the Runaway canonical round-trip test. There is no separate duplicate exact
   invocation. The authoritative final `python3 -m pytest` run executes it once;
   the test emits the deterministic fixture/pack/provenance/migration/surface
   receipt, and the host extracts that passing test plus artifact from the one
   full-suite result.
5. **Freeze one exact source-isolated installed-artifact harness.** Define a
   single command that creates/uses the wheel-only environment, changes to a
   temporary directory outside the checkout, clears `PYTHONPATH` and Astrid pack
   root overrides, invokes that environment's interpreter with `-I -P`, and runs
   the installed catalog/doctor/inspect/backup/restore/source-wheel audits while
   asserting every Astrid module/resource origin is inside the environment. All
   installed-lane commands go through this wrapper and consume the one prebuilt
   wheel hash.
6. **Make the fifteen-row evidence matrix executable.** Freeze a JSON schema and
   deterministic generator/checker. Exactly criteria 1–15 appear once, each
   with non-empty criterion text, command/owner, evidence artifact path plus
   digest, result/status, reviewer artifact plus disposition, and North Star
   alignment. The checker rejects missing/duplicate/stale rows, nonexistent or
   digest-mismatched artifacts, non-passing results, or absent dispositions.
7. **Classify manifests implicitly and separately.** `pack.yaml` and prohibited
   legacy manifest basenames are part of the manifest/discovery audit and are
   excluded from non-Python resource classification. A canonical manifest is an
   implicit declaration input, never a typed/supplemental/authoring resource and
   never self-declared. Legacy basenames still fail discovery/static gates.

## Dispositions

- These changes close executable-code integrity, ownership/SQL agreement,
  backup/restore authority, validation duplication/isolation, final evidence
  completeness, and manifest self-reference without creating new systems beyond
  bounded validators/checkers already required by the plan.
- No SQL parser, DDL duplication, continuous watcher, lock-across-execution,
  project composition state, second migration state table, second wheel build,
  or duplicate full suite is accepted.
- No new research lane or `[XHARD]` work is required.

## North Star disposition

**Conditionally aligned.** The canonical architecture remains correct, but
these seven proof/closure contracts must be incorporated into a complete
replacement before the plan is settled. Sol must revise, return exact `STABLE`,
and a fresh complete settled-plan wave must inspect the new snapshot.

