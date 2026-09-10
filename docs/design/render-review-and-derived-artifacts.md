# Render Review and Derived Artifact Lifecycle

Status: split planning umbrella (2026-09-10)

Render Review must never confuse an authored timeline with bytes actually rendered. The rendered projection is governed by one managed render/task and its video digest; Timeline Structure remains governed by the authored timeline/config snapshot. The rendered clock is the decoded/probed video clock, including any excess tail. Captions are an explicit spoken-text allowlist; generation prompts and unmarked transcripts never enter that channel.

This umbrella is split into two standalone plans:

1. [Plan 1 — timeline visualization fixes](timeline-visualization-fixes-plan.md) is the immediate executable path. It improves the existing `timelines visualize --view filmstrip` route using current render admission, digest verification, manifests, run/task events, CAS publication, and disposable rehydrated caches. It does not wait for a new retention service.
2. [Plan 2 — ephemeral derived-artifact lifecycle](ephemeral-derived-artifact-lifecycle-plan.md) is the generic cross-tool facility. It defines durable primary-generation outputs, temporary derivative defaults, runtime-owned retention/pin/promotion/deletion, and extension-author contracts. Plan 2 ends by migrating the completed Plan 1 visualizer to this facility and proving the integration end to end.

Plan 1 may ship and be completed with existing storage/cleanup behavior. Plan 2's generic facility can be built independently; its final migration task depends on the completed visualizer and shared lifecycle contract.

Durable Megado setup packages are ready for later delivery: [Plan 1 run package](../../.otto/runs/timeline-visualization-fixes-20260910/README.md) and [Plan 2 run package](../../.otto/runs/ephemeral-derived-artifact-lifecycle-20260910/README.md). The earlier planning provenance and adopted oracle decision remain in the [archived original planning run](../../.otto/archive/render-review-plan-20260910/status.md).

## Shared invariants

- A review identifies `(render_run_id, render_task_id, video_digest, manifest_digest)`; paths are locators/materializations, never authority.
- A materialized video with the wrong digest is rejected. Drill-down cannot switch renders or silently resolve a new `latest`.
- Render duration/coverage comes from decoded rendered bytes, not authored duration. Excess output is an explicit unmapped rendered tail unless pixel evidence proves blackness.
- Spoken text is sourced only from explicit/verified metadata. Missing metadata means “no spoken-text metadata,” not proven silence.
- Structure and rendered review JSON have distinct kinds, clocks, authorities, and metadata channels.
- Independent range, sampling-density, and spatial-resolution values are recorded separately. Full overview coverage and selected-card/page coverage are honest and explicit.
- A stateless range/frame request may have no parent. A manifest-derived child records parent manifest identity and rejects conflicting render selectors.

## Accepted simplification decisions

The user requested this two-plan split after Astra's earlier architecture decision (`RR-ORACLE-001`, one call consumed). That decision remains applicable: reuse existing task/run/receipt/CAS/host mechanisms; do not add a dedicated review database or review-specific event family; use conditional lineage; use mandatory overview boundaries plus adaptive interior sampling; treat manifest/CAS identity as authority; document only parser-backed CLI commands. Current source inspection found no generic review-ready TTL/pin/GC API, so Plan 2 owns that missing facility explicitly.

## Deferred beyond both plans

Waveform/visual-change detection, word alignment or transcription admission, offline media bundles, project retention UI, and new command spellings remain follow-up work. They cannot weaken the invariants above.
