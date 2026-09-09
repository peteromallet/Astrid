# Astrid unified execution — portable planning handover

This is a `planning_only` Megado handover. The copy-paste delivery note is
[`assets/handover-message.md`](assets/handover-message.md). Start with these
records in order:

1. Read `authorization.md` for scope and branch boundaries.
2. Read `northstar.md`, `agent_goal.md`, and `status.md` for direction,
   objective, and honest current state.
3. Read `run.yaml` as the single role/model/budget declaration.
4. Read `authority/UNIFIED-PLAN-v3.md` at its recorded SHA-256, then
   `plan.md`, `tasklist.json`, `criteria.md`, and
   `authority/ADJUDICATION.md`.
5. Read `authority/LEDGER-OBLIGATIONS.md` for the selected, read-only
   historical obligation state.
6. Read `provenance.md` and `dependencies.md` before any later delivery
   preparation.

No product implementation, tests, GPU/provider calls, acceptance, final
composition freeze, 45/45 claim, zero-pods claim, merge, deployment, or PR was
performed by this package. Handover publication to the authorized branch is a
separate packaging action. Runtime custody, historical
spend/attempt balance, exact Fire-19 checkout backend, and provider cleanup
remain unresolved. Future review packets must await the actual candidate.

## Future receiver start

From the Astrid repository on the authorized handover branch, verify the
package paths above and validate that `run.yaml` parses with mode
`planning_only`. Do not execute the product plan. If delivery is later
authorized, preserve the role settings and counters, read the Megado execution
mechanics, resolve custody/budget prerequisites first, and dispatch only the
earliest dependency-ready task.
