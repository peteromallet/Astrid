# Review criteria

The linked PLAN.md acceptance matrix is authoritative; these IDs group it for review.

- C1 (T0–T1): unrelated dirty work preserved; only superseded prototype removed;
  canonical v2 Hivemind pack retains seven executor identities/resources/contracts.
- C2 (T2): pinned default provisioning, atomic activation, cache/offline/check,
  disable/restore and failure recovery work without personal-source fallback.
- C3 (T3): discovery, CLI/SDK/skills/host agree on roots and precedence; env skills
  included; revision changes invalidate host reuse; tampering rejected.
- C4 (T4–T5): writable composed root SKILL.md, nested directory links and reachable
  resources work from installed harness paths and a read-only wheel; opt-outs and
  foreign files preserved; docs reflect supported commands.
- C5 (T6): full acceptance matrix evidenced, fresh agent navigation and live read-only
  search/get_item receipts included; remote failures distinguished from installation;
  no corpus publication; limitations and exact release/pin dependency reported.

- C6 (A2): validated executor project-required/optional metadata replaces the
  Hivemind-specific SDK list; explicit project wins, required work uses saved
  selection, optional work runs projectless; ordinary host lifecycle preserves
  truthful failures/cancellation and source fences. Runtime changes require a
  concrete failing fixture, not hypothetical gaps.

T1 is an upstream dependency now; C1/C5 replacement and live Hivemind acceptance
remain pending until a valid immutable H3 source is available. Do not certify
those criteria using the bundled copy or silently broaden this run upstream.

Integrated evidence: the final affected Astrid suite passed 123 tests and 8 subtests
after the source-contract correction. The stale test that treated bundled
Hivemind as an always-default skill now verifies that Hivemind is not selected
without a provisioned managed source.
