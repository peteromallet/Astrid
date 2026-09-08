# Astrid skill navigation review — 2026-09-08

## Method

Seven Luna agents evaluated 15 distinct maker queries: three agents handled
five queries each, with later measured traversals and four fresh agents checking
Foley, title-effect authoring, saved characters, and final route selection. The first three batches shared context within each batch. They were
not 15 independent cold starts. Trials inspected docs, contracts, help, and in
some cases read-only runtime discovery. They did not generate, render, edit
projects, publish, or verify execution end to end.

The first reports grouped reads across queries, so their totals cannot establish
per-query latency or a before/after improvement percentage. A second measured
traversal records per-query actions in an already-warmed agent session. Treat
those as observed informed navigation, not cold-start performance. Tool actions
can open multiple documents; document counts and action counts are different.

## Measured navigation

The [per-query measured traversal](measured-routes.md) recorded 37 document opens
and 17 help calls across 15 queries: 3–4 actions per query in warmed context.
That speed did not mean correctness: the trace includes wrong-router failures
for Banodoco research, reusable title authoring, and building a custom pack,
and partial handoffs for other requests. These observations are retained.

The fresh title and Foley trials each used 10 tool actions, including a guessed
path correction; some actions read multiple documents. The saved-character
trial read four documents, used one path-resolution action, and made one failed
path attempt. The final route-selection trial is narrower than full contract
verification and reports actual opens separately from reused core context.

Core now places a task map before setup/navigation, including direct routes to
pack builder, Hivemind, references, and timeline work. A final Foley routing miss
also prompted an explicit generation-versus-existing-timeline distinction and a
return link from timeline work to creative generation.

No controlled pre-change baseline or timing measurement was collected. These
trials support specific usability fixes, not a claimed global speedup or a
statistically meaningful pass rate.

## Findings and changes

- Main/default render lookup, archived recovery, and visual timeline overview
  have direct product commands. Existing project data confirmed the main render
  route without opening it during the audit.
- A failed run's summary returned no useful failure payload; its events exposed
  the error. Core now explicitly routes from empty failure detail to events.
- Foley routing conflated a whole-clip sound track with a tiled spatial review
  workflow. Creative work now separates them and links audio generation to
  timeline assembly for the final video.
- A fresh Foley agent guessed a nonexistent capability-contract path. The fal
  and rendering skills now link directly to their stage contracts; creative
  work also explains their normal source location.
- Saved character references cannot currently be supplied directly to the image
  generator's path-based input. The references skill explicitly documents the
  supported local-original route and the limitation when only a managed ID
  remains. This is a product handoff limitation, not a broken skill link.
- YouTube publishing requires a reachable video URL and configured integration.
  Finding the upload route does not prove a local render is ready to publish.
- Pack building has an actionable element/orchestrator decision map and static
  validation path. Detailed element work still requires template and precedent
  reads; their necessity should be judged against the requested implementation.
- Broad run inventories and unfiltered SDK discovery produced unnecessary output
  in the audits. Targeted product reads and capability inspection are preferable
  once the relevant identity is known.

## Evidence

- [Navigation queries 1–5](navigation.md)
- [Creative queries 6–10](creative.md)
- [Extension and publishing queries 11–15](extensions.md)
- [Fresh Foley trial](cold-foley.md)
- [Fresh title-effect trial](cold-title.md)
- [Saved-character trial](cold-character.md)
- [Final route selection and Foley retest](final-routing.md)
- [Measured per-query steps](measured-routes.md)
- [Initial skill hashes and sizes](baseline.json)

## Structural implementation

Astrid is the single orientation entry point. Creative work routes to existing
pack skills. Timeline editing and rendering share one skill. Pack builder is
linked authoring guidance within core, not a new executable pack. Project setup
uses the existing getting-started guide. References live with their existing
product mount. Hivemind remains a prominent external knowledge route.

Full capability and pack indexes now live in supporting references. Both index
generators were checked to leave the main skill unchanged. The old Claude-only
timeline guide was backed up and replaced with a link to the shared timeline
skill; dangling Hivemind aliases were repaired, and the references target was
restored.

## Validation

The CLI documentation and skill installation/registry suites passed 60 tests
after the structural changes. Final documentation checks, relative-link checks,
and generator idempotence checks were repeated after navigation fixes. Live
creative execution was outside these navigation trials.
