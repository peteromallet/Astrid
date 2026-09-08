# Astrid creative-work navigation audit — 2026-09-08

Scope: read-only navigation for queries 6–10. No generation, rendering, saves,
task admission, public search, external writes, or paid actions were invoked.
The five traces share this session's already-read core/router context; they are
not independent cold starts.

## Chronological trace

1. Read `astrid/packs/_core/skill/SKILL.md` first, as required.
2. Read `_core/skill/creative-work/SKILL.md` and routed each intent.
3. Read the relevant pack skills: generation and generate-image for query 6;
   references for query 7; rendering for query 8; editorial and video_editing
   for query 9; Hivemind for query 10.
4. Read-only CLI help: top-level, projects, timelines, media references,
   tasks, and runs. `doctor --json` returned `credential lacks required scope`
   with next action `banodoco-local up --profile astrid`.
5. Read-only SDK discovery: `sdk.discover()` succeeded but emitted a very
   verbose representation; no capability was invoked.
6. Read-only runtime discovery: doctor; projects list/current; timelines list;
   references list; runs list; timeline show. Runtime returned project
   `astrid-intro`, timeline `main-final-blackend2`, no references, and existing
   render runs. Current project preference was unset.
7. Read relevant read-only `STAGE.md` contracts in one batch: generate_image,
   rendering.render, video_editing.hype, editorial.transcribe, quote_scout,
   arrange, video_editing.cut, and vibecomfy inspect/validate/run.

## Query results

### (6) Paper lantern over a lake, available model — navigation success; execution not attempted

Shortest supported route: choose `flux-schnell`, explicit `t2i`, `cloud`, and
the prompt; call `sdk.invoke("generation.generate_image", kind="executor",
project=<project>, inputs={model, mode, execution, prompt})`. Required input is
`prompt`; `mode` is mandatory and there is no executor CLI. The registry probe
confirmed cloud endpoint `fal-ai/flux/schnell`; `z-image` is the local/open
alternative and requires ComfyUI/VibeComfy. Ambiguities are project/output and
desired aspect ratio. The stage contract confirms the SDK endpoint and model
matrix; generation readiness was not tested.

Evidence: `astrid/packs/generation/executors/generate_image/skill/SKILL.md:20-49,64-83,106-108`; `astrid/packs/generation/executors/generate_image/STAGE.md:1-18,44-75,104-121`.

Per-query measurement: docs not separately measured (batched); no help call;
one read-only model-registry probe.

### (7) Existing character, preserve appearance — navigation success; execution readiness partial

Shortest route: `media references list --project <project> --json`, show the
chosen character, retain its canonical association, then generate a variant
with `flux-dev` or `z-image`, `mode=i2i`, `image_ref=<existing local absolute
or invocation-relative file>`, and a prompt for the new scene. A reference or
managed media id cannot be passed as `image_ref`; if only the managed id remains,
the documented limitation applies. Runtime discovery found no references in
`astrid-intro`, so the character name and accessible original image remain
missing. The route is verified; execution inputs are not.

Evidence: `astrid/packs/references/skill/SKILL.md:8-18,44-55`; `astrid/packs/generation/executors/generate_image/skill/SKILL.md:84-101`.

Per-query measurement: docs not separately measured (batched); no help call;
one shared read-only `media references list` discovery call.

### (8) Change opening title, hold two seconds longer, render — navigation success; execution readiness partial

Shortest route: list/show the main timeline, identify the opening title clip
and exact text/hold fields, merge the complete config and registry, save with
the observed `expected-version`, then render with the same timeline and version
pin. Discovery found `astrid-intro` / `main-final-blackend2`, config version 1,
with 33 assets and 34 clips. The shown config has media clips and an
end-spanning layer but no obvious title text clip, so an asset/clip id or visual
inspection is needed before a safe edit. The render endpoint is verified by
`render/STAGE.md`; no save/render was attempted.

Evidence: `astrid/packs/rendering/skill/SKILL.md:25-38,51-77,82-103`; `astrid/packs/rendering/executors/render/STAGE.md:1-28,56-86`; `astrid/packs/_core/skill/SKILL.md:68-80,91-93`.

Per-query measurement: docs not separately measured (batched); no help call;
two shared runtime discoveries (`timelines list`, `timelines show`) plus the
project list used to resolve the project.

### (9) Transcribe interview and find short announcement clips — navigation success; execution readiness partial

Shortest supported route: use `video_editing.hype` with required runtime-
materialized `video` and `brief` inputs, optional explicit `theme`; it sequences
transcribe → scenes → quality zones → shots → triage → scene describe → quote
scout → pool/arrange → cut → render → review/validate. The individual route is
`editorial.transcribe` → quote scout/arrange → `video_editing.cut` → render.
`transcribe` requires audio/video input and an OpenAI key; quote candidates carry
timestamps, speakers, and scores. The Hype and stage contracts verify this plan;
source media/brief/credentials are not present in this audit.

Evidence: `astrid/packs/video_editing/orchestrators/hype/STAGE.md:1-22`; `astrid/packs/editorial/executors/transcribe/STAGE.md:1-26`; `astrid/packs/editorial/executors/quote_scout/STAGE.md:1-28`; `astrid/packs/video_editing/skill/SKILL.md:19-20,31-37`.

Per-query measurement: docs not separately measured (batched); no help call;
no query-specific discovery call.

### (10) Banodoco ComfyUI recommendation and how to run in Astrid — navigation success; recommendation unavailable by explicit no-search constraint

The route is the Hivemind read/search surface: query Banodoco for ComfyUI
video workflow practice, prefer distillations then workflow/resource/message
hits, and retrieve full cited items before choosing. Public search was expressly
not performed, so no recommendation can be selected. In Astrid, the verified
plan after choosing a workflow is `vibecomfy.inspect` (read-only projection),
`vibecomfy.validate`, then `vibecomfy.run`; the run contract identifies the
workflow input and requires the executor package installation flow. The query
also leaves video model, local/cloud execution, and source workflow ambiguous.

Evidence: `/Users/peteromalley/.codex/skills/astrid-hivemind/SKILL.md:19-22,30-46,50-58`; `astrid/packs/vibecomfy/executors/inspect/STAGE.md:1-7`; `astrid/packs/vibecomfy/executors/run/STAGE.md:1-30`; `astrid/packs/_core/skill/creative-work/SKILL.md:18-24,48-54`.

Per-query measurement: docs not separately measured (batched); no help call;
zero public search/discovery calls by constraint.

## Measured totals

- Docs read: 8 checkout skill docs + 1 external Hivemind skill + 10 relevant
  stage contracts = 19 total. No audit reports were read.
- Help calls: 6 (`astrid`, projects, timelines, media references, tasks, runs).
- Discovery calls: 1 SDK `discover()` + 7 runtime CLI calls: doctor,
  projects list/current, timelines list, references list, runs list, timeline
  show. (The project list/current pair counts as two.)
- Backtracks: 1 initial path correction from workspace-root `astrid/...` to
  `Astrid/astrid/...`; no route backtracks after the core router.
- Navigation outcomes: 5/5 routes located; execution readiness: 6 untested,
  7/8/9 input-dependent, 10 recommendation unavailable only because public
  search was prohibited. No navigation route was blocked.
- Unnecessary reading/friction: `runs list` produced a huge payload not needed
  for route selection; default `sdk.discover()` repr was excessively verbose;
  Hivemind search was intentionally omitted by the audit constraint.

