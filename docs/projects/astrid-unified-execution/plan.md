# Plan pointer — UNIFIED-PLAN v3

`authority/UNIFIED-PLAN-v3.md` is the sole current execution authority and is
preserved byte-for-byte at SHA-256
`0772f5ac5196b7c0e28d19c1d636f18c26a3cc8c550f9f1a09bd9a4e2ddb7dc0`.
This file is a portable index, not a replacement for that authority.

The historical 45-row ledger is not copied. The selected read-only obligation
record is `authority/LEDGER-OBLIGATIONS.md`; it preserves the adjudicated
state without private local paths or raw receipts.

## Current state

This is a planning-only handover. No product source was edited, no tests or GPU
provider calls ran, no acceptance was earned, and no final composition or
45/45 result is claimed. The preserved state is 22 accepted scoped closures,
one reopened `B03-T01` HC-04 correction, and 22 original pending rows. Pending
evidence does not silently close a row.

## Sequencing contract

P0 is custody, provenance, capacity, routing, and bounded recovery/reconstruction.
`P0.d` must reconcile historical spend and attempts and sign remaining
allowance before any live/GPU fire. `P0.b` must recover the exact missing
Fire-19 checkout backend if possible or reconstruct its two missing methods
against preserved contracts; it must not restore an overlay wholesale.

P1 integrates VibeComfy content in clean custody. P2 implements the
engine-neutral `ManagedToolSession` and checkout adapter. P3 converts the
harness to session-aware evidence. P4 proves checkout lifecycle, P5 checks Wan
residency feasibility honestly, and P6 proves retained embedded-session
behavior. These CPU-first stages are not GPU acceptance.

P7 completes the producer/deletion CPU chain (`B03-T05a-e`, aggregate `T05`,
`B04-T04` admission, then `B03-T08`, `B04-T05` through `T07`, and `B05-T01`
through `T04`), obtains
`B05-T04 / CR2 PASS`, freezes the final composition, runs the final CPU/GPU
journey and capture, obtains independent Sol `B06-T07`, then records either
full acceptance or an honest terminal disposition.

The `B04-T04` admission precedes `B03-T08` deletion in this portable index;
that dependency-order correction reflects the adjudicated ledger obligation and
does not broaden scope or reopen ratification.

## Future review gates

`run.yaml` deliberately has `review_stages: []` because this handover is
planning-only. Future delivery gates are P1/P2 independent review, CR2 before
`B06-T01`, and independent Sol final review. They are not current passes and a
future review packet must be created from the actual candidate.

## Estimate and unresolved risks

The v3 estimate is an optimistic ten working days (about two calendar weeks),
not a promise. Runtime local custody is currently unusable and needs recovery;
historical provider spend/attempt balance is unresolved; the exact Fire-19
backend is missing; provider cleanup is not independently certified; and any
verification/readiness/liveness/settlement bypass is an immediate stop.
