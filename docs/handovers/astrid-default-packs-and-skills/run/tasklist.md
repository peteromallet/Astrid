# Delivery tasklist and ownership

> Handover note: the scoped T0–T6/A2 implementation described below is
> complete in the committed candidate. The assignment table is retained as
> historical scope and boundary information; do not restart completed tasks or
> reset review counters. Continue only the pending Hivemind H3/T1 dependency
> described in `agent_goal.md` and `status.md`.

Source: `/Users/peteromalley/Documents/reigh-workspace/Astrid`, dirty baseline
captured in `baseline-20260908-delivery/`; no worktree. Hivemind remains
external at branch commit `52e6e357aeba15861b6237b2fa6dd48af2e0a607`; its H3
is not an Astrid implementation dependency that can be fabricated here.

## Active assignments

1. **A2 generic project scope — normal Luna worker**
   Own only generic executor metadata validation/serialization and SDK
   project-required versus project-optional resolution, with focused fixture
   tests. Structured argv, stdout/stderr/exit/cancellation belongs to H3's
   upstream thin adapter; host changes are allowed only for a concrete failing
   fixture. Do not modify pack provisioning, skills, or Hivemind.
2. **T2/T3 source provisioning and shared inventory — normal Luna worker**
   Own declared external source setup, staging/validation/activation, offline
   check/disable/restore behavior, shared root discovery and host handoff.
   Use local fixtures; do not claim a valid Hivemind v2 release pin or remove
   the bundled copy. Avoid A2 files.
3. **T4/T5 skills and packaging — normal Luna worker, after T2/T3 seam**
   Own writable composed skill view, harness sync/registry, package data and
   docs. Consume the shared inventory; do not create an installer database or
   modify runtime scope/A2 files.

Root coordinator integrates only at actual seams, runs affected checks, and
assembles the scheduled source-contract and final review packets. Root/original
host retains oracle authority. No push, merge, deploy, global install or
corpus write.

## Current state

T0 custody and baseline are complete. Source mapping is recorded in
`docs/plans/standalone-tools/evidence/astrid-source-surfaces.md` and
`astrid-entrypoint-surfaces.md`. A2 and T2/T3 are independent and ready;
T4/T5 waits for the shared inventory interface. T1/H3 external manifest work
is honestly blocked on the canonical Hivemind release revision.
