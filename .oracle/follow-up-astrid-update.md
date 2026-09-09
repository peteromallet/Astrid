# Follow-up: Simple, Pack-Aware `astrid update`

## Status and sequencing

- **Queued, not started.** This is a separate follow-up project.
- It begins only after the canonical-pack beta has passed B1–B5, all 15 final
  criteria, and the final push.
- Its base is that completed canonical-pack result. Do not mix it into the
  current cutover.
- Sol owns planning and oracle judgment. Luna handles normal implementation
  and review, following the Megado process.

## Goal

Provide one dependable beta command that updates a supported Astrid
installation and safely brings existing projects forward. It must preserve
project-owned files, local packs, media, and all database changes already
applied through pack migrations.

The command is an orchestrator over existing trusted machinery, not a new
package manager or reconciliation framework.

## Beta contract

1. Support **one explicitly documented installation/update path**. Select the
   concrete path from the final post-cutover installation contract; do not
   abstract over multiple package managers in beta.
2. Provide a dry-run/preflight that reports the current version, target
   version, affected projects, pending canonical pack migrations, backup
   location, and any refusal reason.
3. Refuse a dirty editable/source checkout with a clear recovery instruction.
   Do not merge, stash, rebase, or rewrite user source changes.
4. Acquire the existing exclusive database ownership lock and use the existing
   backup/journaled-restore path before changing a project database.
5. Stage and validate the target Astrid package before activating it.
6. Use the canonical pack catalog and existing migration probe/runner to apply
   only pending migrations, once, transactionally, in deterministic order.
7. Run `astrid doctor` after activation. On failure, restore the prior package
   and database backup and report exactly what happened.
8. Be idempotent: an already-current healthy installation is a successful
   no-op.
9. Emit a concise human report plus a structured receipt suitable for later
   inspection.

## Reuse — do not rebuild

- canonical pack object and catalog;
- schema-migration registry, read-only drift/too-new probe, and transactional
  pending-migration runner;
- exclusive database ownership lock;
- backup and journaled restore;
- doctor validation;
- pack install provenance and the existing install/update/rollback primitives;
  and
- the final documented Astrid installation contract.

## Hard exclusions

The beta does **not** include:

- arbitrary Git merge/stash/rebase behavior or preservation of edits inside an
  Astrid source checkout;
- multi-package-manager support or a generic environment auto-detector;
- a generic three-way file reconciliation engine;
- per-project composition locks;
- pack enable/disable/purge lifecycle;
- marketplace, dependency solver, signing, sandbox, permissions UI, or a
  background updater/daemon;
- schema diffing, generated DDL, database copying, rewriting migration history,
  or rerunning applied migrations;
- compatibility shims, dual catalogs, or an incremental legacy path; or
- mutation of local/custom pack source, project files, media, or unrelated
  user configuration.

If a proposed plan introduces any of these, reduce the plan before execution.

## Acceptance criteria

- A clean supported installation updates successfully through the single
  documented path.
- Preflight is read-only and accurately predicts pending work.
- Existing projects retain project files, local packs, media, and pack-created
  database data.
- Pending canonical migrations run exactly once; applied migrations do not
  rerun.
- Drift, a too-new database, a dirty source checkout, or a lock conflict causes
  a safe refusal before mutation.
- A forced post-activation failure proves package rollback and journaled
  database restoration.
- A second invocation is a healthy no-op.
- Documentation explains the supported path, refusal cases, recovery, and the
  structured receipt.

## Size guard

Target **5–8 engineering days (roughly 1–2 engineer-weeks)** for a strong beta.
If the reviewed plan exceeds two engineer-weeks, it is almost certainly
rebuilding machinery or expanding beyond this contract and must be simplified
before Megado execution begins.
