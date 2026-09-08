# Implementation handoff

Use the worker bindings in the prepared run configuration: Luna for ordinary
implementation and Sol for justified XHARD assignments.

Implement [PLAN.md](PLAN.md) in its T0–T6 order. The coordinator has made the
architecture decisions; the three Luna memos are supporting evidence, not a
request to choose among competing approaches.

The contract is simple: Astrid setup provisions the pinned external Hivemind
pack by default; skill sync builds the canonical Astrid skill tree using links
to installed pack-owned skills; the runtime receives the same validated roots.
Hivemind owns its skill and all seven executors. Discovery and skill sync stay
offline and do not install code.

Start by reading [source-state.json](source-state.json) and inspecting current
diffs. Preserve unrelated user changes and the approved skill reorganization.
Remove only the superseded Hivemind-copy/default-selection prototype identified
in the plan. Fix the canonical external manifest, then pin its valid revision.
Do not substitute the personal Hivemind skill, bundle copied executors into
Astrid, or introduce a general runtime pack manager.

Implement the setup declaration and provisioning path, shared installed-root
resolution, explicit host handoff, writable composed skill view, packaging, and
documentation. Follow the plan's acceptance matrix, especially a fresh install
without personal skills, offline resync, opt-outs, read-only installed package
resources, and skill/runtime root agreement. Use only read operations for live
Hivemind validation. Report any unavailable live validation precisely.

The existing dirty prototype is not certified. Finish with evidence for the
implemented path and a concise report of remaining limitations. Publication of
upstream commits or releases is a separate action; prepare the required changes
and identify any resulting release/pin dependency explicitly.

Prepared Megado control root: [START-HERE.md](../../../.otto/runs/astrid-default-packs-and-skills/START-HERE.md). The run is configured but not launched.
