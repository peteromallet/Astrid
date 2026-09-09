# Settled-plan wave 4 synthesis

Plan SHA-256:
`36431cec838e59670f8b41b1ab4fba76853049b6f15d04969b9d5d08fb82b40a`

## Accepted material changes

1. **Bind installed admission state at use time.** The operation snapshot keeps
   its selected external candidate and accepted permission receipt, but
   immediately before installed capability execution the existing
   `InstalledPackStore` admission owner must verify that the same revision is
   still active, valid, provenance-matching, and permission-matching. This is a
   narrow state check keyed by captured revision/receipt—not candidate
   rediscovery, manifest reparsing, retry, a project lock, or a new trust
   service. A changed disposition fails closed; a newly activated revision is
   visible only to a later operation snapshot.
2. **Freeze the Runaway round-trip fixture.** The absent historical demo project
   is not restored or packaged. Tests create a deterministic temporary project,
   apply the canonical Runaway migration path, and exercise the required
   repository/event/command/CLI/SDK/conformance surfaces that exist. The
   four-pack matrix records explicit N/A reasons for absent surfaces, and the
   final receipt names this generated fixture and exact commands.

## Rejected finding

- **Plan header says “not STABLE”: reject as a state-model misunderstanding.**
  The replacement plan truthfully records its issuance state. Exact Sol
  stability is an immutable later receipt (`phase3-stability-5.md`) over that
  digest, while `.oracle/status.md` owns current run phase. Rewriting the plan
  merely to copy later procedural state would invalidate the reviewed snapshot
  and conflate plan content with the Megado state machine.

## Other dispositions

- The simplicity critic returned `CLEAN`; all prior Wave 1–3 changes remain
  resolved without new ceremony.
- No new research lane or `[XHARD]` work is needed.
- The two accepted corrections add no service locator, cache invalidator,
  composition lock, lifecycle, rescan, compatibility path, or packaged demo
  asset.

## North Star disposition

**Conditionally aligned.** The canonical architecture remains sound, but the
installed-admission race and ambiguous Runaway fixture must be frozen in a
complete replacement. Sol must revise, return exact `STABLE`, and a fresh
complete settled-plan wave must inspect the new snapshot.

