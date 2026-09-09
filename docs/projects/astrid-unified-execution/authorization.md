# Authorization and boundaries

This package is authorized as a planning-only handover for the public
existing Astrid repository.

- **Destination:** a handover branch on top of Astrid `main`, base
  `8150c3b70887495f0fae4a55c1ac70085a900550`, using the existing public
  `origin` remote.
- **Recipient mode:** `planning_only`.
- **Authorized now:** package and publish the portable control records on the
  handover branch, preserving the declared roles, budgets, counters, and
  authority.
- **Not authorized:** product implementation or source mutation, tests,
  provider/GPU calls, deployment, release, merge to `main`, PR completion,
  destructive cleanup, old-ledger edits, or delivery dispatch.

The receiving agent must not infer product delivery, acceptance, merge,
deployment, or PR authority from this handover. A later explicit delivery
authorization must change the single authoritative `run.yaml` mode while
preserving the existing role/model settings, budgets, unknown counts, and
review boundaries. Future review packets must be based on the actual candidate;
this package contains planning evidence only.

