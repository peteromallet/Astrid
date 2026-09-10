# Plan 1: Timeline Visualization Fixes

Status: immediate implementation plan; no generic lifecycle dependency

Authoritative Megado run: [`.otto/runs/timeline-visualization-fixes-20260910/START-HERE.md`](../../.otto/runs/timeline-visualization-fixes-20260910/START-HERE.md). The run remains `planning_only`; this design document is the product-plan source, while run state, authority, budgets, counters, and handoff artifacts live only in that run directory.

## Outcome

Make the existing `timelines visualize --view filmstrip` route a trustworthy Render Review entrypoint. Reuse current admission, frozen render authority, digest checks, `timeline_filmstrip` result manifest, run/task events, generic host publication, and disposable rehydration. Do not build a storage framework or wait for Plan 2.

## Scope and tasks

1. Freeze the current public CLI grammar from `Astrid/astrid/packs/timeline/cli.py:645-710`; remove/document no unsupported `review render`, `timeline view`, `--preset`, or `--resolution` examples. Keep exact `--render-run` provenance and current `latest` freshness behavior from `Astrid/astrid/sdk/timeline_filmstrip.py:197-269`.
2. Extend the existing filmstrip snapshot/executor (`filmstrip_execution.py:19-89,119-143`) to make decoded rendered duration authoritative, preserve the full excess tail as an unmapped rendered region, and retain proven shot IDs without inferring labels from authored-only data. Preserve wrong-digest rejection.
3. Make the first useful result one full-duration overview over the existing bundle (`filmstrip_cards.py:71-113,200-285`), with first/last decoded frames and tail transition mandatory, adaptive bounded interior sampling, honest coverage/page metadata, and exhaustive boundary/index data for drill-down. Do not promise every fast-cut shot boundary.
4. Add independent range, sampling density, and spatial resolution request values and record them separately. Keep current range/`--at`/`--every`/`--every-frames` semantics (`filmstrip_options.py:30-72`); introduce resolution only where the parser and executor can prove it.
5. Keep spoken text independent of shot presence using the existing allowlist/frozen verification (`sdk/timeline_filmstrip.py:54-62,141-155`). Prompts and unmarked transcripts remain excluded; script timing and verified speech timing remain distinct.
6. Return manifest/CAS identity and entrypoint locators in the existing result envelope. Do not fabricate a mutation receipt for a read-only visualization or add review-specific events.
7. Document existing disposable cache/host cleanup behavior and the output contract used by the visualizer. Migration to the shared lifecycle is owned entirely by Plan 2 and is not a completion dependency here.

## Agent UX evaluation and iterative optimization

Plan 1 includes a bounded evaluation loop, designed now but not dispatched in this planning-only package. It tests both views and their handoff:

- **Authored structure:** tracks/layers, overlap, text and audio placement, authored timing, and the distinction from rendered evidence.
- **Rendered filmstrip:** actual frames, full decoded tail, spoken-text metadata, rendered clock, and exact render identity.
- **Cross-view journey:** an agent discovers the appropriate view, starts with a full overview, drills to a range and detail/exact frame, then answers an evidence-backed question while preserving the interval and naming the snapshot/render identity. It must flag clock mapping unavailable or mismatches rather than assume authored and rendered clocks agree.

Use a small local synthetic fixture (approximately five minutes) with overlapping layers, a shotless spoken segment, prompt traps, a rendered tail, and two render versions. Reuse Sisypy's existing evidence pack and action capture; do not add an evaluator service. Actors receive ordinary user briefs and public docs/tools only, with no answer, command, or hidden-ground-truth coaching. The harness freezes the actual images viewed, traces, artifacts, and manifest IDs.

Scenario candidates:

| ID | User ask | Canonical surface | Likely wrong turn | Evidence / shape |
|---|---|---|---|---|
| UX-01 | “What overlaps and where are the text/audio items at the ending?” | authored structure view | answer from filmstrip or authored duration mismatch | structure manifest, interval/timing fields, commands; positive |
| UX-02 | “Find the black transition and spoken moment in this render.” | rendered filmstrip overview → range → exact frame | treat page one as whole film, suppress speech without shot, expose prompts | viewed images, manifest coverage, spoken metadata, frame identity; positive |
| UX-03 | “Diagnose why the ending differs between plan and render.” | cross-view structure + pinned render | assume identical clocks/identity or silently switch render | paired snapshot IDs, clock mapping/mismatch flags, evidence-backed answer; positive |
| UX-04 | “Review this requested render after a newer render exists.” | explicit render identity/admission | use latest or local path and claim success | stale rejection, digests, no mismatched artifact; negative/recovery |
| UX-05 | “Navigate a fast-cut/unknown interval and state what the overview proves.” | overview/index → range/detail | claim every boundary was sampled or invent a shot | selected cards, coverage limits, exact range evidence; held-out recovery |

The recommended first five-minute task is UX-02, with UX-04 as its matched stale-render case. A missing-spoken-metadata variant must produce “no spoken-text metadata,” never inferred silence. Actors must actually view images for visual-usability claims; missing image access or incomplete capture is **undetermined**, not pass.

Delivery evaluation is bounded to a baseline plus two UX improvement passes: (1) fresh Luna actors establish discovery and wrong-turn traces; (2) Astra assesses friction and evidence from frozen traces, then Luna high fixes only precise demonstrated issues; (3) a second Astra assessment verifies the affected UX, followed by a fresh Luna held-out task. Sol is used only for a demonstrated hard kernel after decomposition. The two Astra UX rounds are explicitly capped at one invocation each and are not hidden oracle calls or an extra final review. Deterministic identity/coverage/caption gates block; friction is observed from traces, not gamed by narrative.

## Acceptance evidence

- Render A remains selected after render B/timeline edits; wrong materialized bytes fail.
- Long tail coverage reaches the decoded final frame and is not called black without pixel evidence.
- Spoken captions remain present when no shot label exists, while prompts/unmarked transcripts never appear.
- Hundreds of cuts produce a bounded full-duration overview with mandatory boundaries, explicit selected coverage, and drill-down commands that use real flags.
- Range, density, and resolution are independently represented; a stateless range has no fabricated parent.
- Structure/render kinds, clocks, and authorities remain distinct; cache deletion can rehydrate from the exact recorded render identity.
- Every documented command parses against current help.

## Estimate and boundary

Estimate: withdrawn pending one non-duplicating remaining-work breakdown at delivery setup. Existing digest admission, rendered-clock alignment, manifests, and cache verification are baseline reuse, not reimplementation. Plan 1 is complete when visualization acceptance checks pass and current disposable lifecycle behavior is documented. Plan 2 owns the later migration and its acceptance checks.
