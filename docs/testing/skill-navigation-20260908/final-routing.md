# Final Astrid skill routing check — 2026-09-08

Scope: endpoint selection only. No commands, capability execution, Hivemind
search, or source browsing was performed.

## Document opens

1. `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/_core/skill/SKILL.md`
   — opened first, as required; this was the cold entry-point read.
2. `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/_core/skill/pack-builder/SKILL.md`
   — opened for query A.
3. `/Users/peteromalley/.codex/skills/hivemind/SKILL.md`
   — opened for query B.
4. `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/rendering/skill/SKILL.md`
   — opened for query C.

The core entry point was physically opened once for cold query A and was not
opened again for warmed queries B and C. Query A opened 2 physical documents;
queries B and C each opened 1 physical linked guide, with the core reused but
not counted as an open. Every query stayed within the three-open maximum.

## Routes

### A — “Build my own reusable transcribe-select-cut-render pack”

Route: **Pack builder** — `pack-builder/SKILL.md`.

Reason: the core map sends requests to build a reusable tool, workflow, or
visual element to Pack builder. The linked guide confirms it covers reusable
Astrid extension packs and capability shape selection.

Cold status: first query; core was opened cold, then the pack-builder guide.
Actual opens for this query: 2 documents.

### B — “What does Banodoco recommend for ComfyUI video workflows?”

Route: **Hivemind** — `/Users/peteromalley/.codex/skills/hivemind/SKILL.md`.

Reason: the core map sends Banodoco advice, model settings, and workflow
precedents to Hivemind. The guide explicitly covers ComfyUI workflows and
Banodoco community knowledge.

Warm status: core reused from query A, then Hivemind was opened.
Actual opens for this query: 1 physical document open (Hivemind).

### C — “Add Foley to one short video and deliver finished video”

Route: **Timeline editing and rendering** —
`Astrid/astrid/packs/rendering/skill/SKILL.md`.

Reason: the original cold route reached the timeline editing/rendering guide,
which covers editing, rendering, and opening the resulting video. That route
missed the Foley-generation step, so it was incomplete for the stated goal.

Warm status: core reused from query A, then the rendering guide was opened.
Actual opens for this query: 1 physical document open (rendering).

## Warm retest of C

The clarified warm retest followed the actual new-media path:

1. **Creative work** — `creative-work/SKILL.md` identifies the specific
   “add sound to one short video clip” route.
2. **fal** — `fal/SKILL.md` identifies `fal.fal_foley` as the Foley generator
   and states that it returns audio only.
3. **Timeline editing and rendering** — `rendering/skill/SKILL.md` receives
   the generated audio, assembles it alongside the source video, and renders
   the finished video.

The core guide was reused and not opened. Actual retest opens: 3 physical
documents, within the maximum. This retest resolves the missing Foley step;
the original C observation remains an incomplete rendering-only route.

## Result

Routes A and B were clear. The original C route was incomplete because it
stopped at timeline rendering and did not route through Foley generation. The
warm C retest produced the complete endpoint path: creative work → fal Foley →
timeline editing/rendering. Original-trace physical opens: 4 total (core plus
pack-builder, Hivemind, and rendering); retest physical opens: 3, with core
reused and not opened.
