# Astrid extension usability audit — 2026-09-08

Scope: read-only navigation audit of `/Users/peteromalley/Documents/reigh-workspace/Astrid` for queries 11–15. No SDK invocation, runtime startup, build, generation, render, open, upload, external search, or message was performed. The first required read was `Astrid/astrid/packs/_core/skill/SKILL.md`.

## Trace and counts

Chronological read-only trace (the failed first path check is retained):

1. `sed Astrid/packs/_core/skill/SKILL.md` — failed path check; the checkout is nested at `Astrid/astrid/...` (backtrack 1).
2. `rg --files -g SKILL.md ...` — located the canonical core skill and pack skills (discovery 1).
3. Read `Astrid/astrid/packs/_core/skill/SKILL.md` fully (core orientation).
4. Read `creative-work`, `pack-builder`, and the relevant `foley`, `youtube`, `iteration`, `video_editing`, `rendering`, `media`, `generation`, `editorial`, and `stream_content` skills (shared docs).
5. `rg --files Astrid/docs` plus manifest inventory — located authoritative pack-builder docs and component manifests (discovery 2).
6. Read relevant element, orchestrator/executor `STAGE.md`, and manifest files for title effects, experiment review, Foley, and YouTube (contract evidence).
7. Read `rendering/SKILL.md`, `creating-packs.md`, `creating-tools.md`, `discovery-for-agents.md`, and `reference/sdk.md` (docs).
8. Read numbered core/creative-work/pack-builder sections for exact line evidence (docs).
9. Ran read-only help: `python3 -m astrid --help`, `projects --help`, `timelines --help`, `python3 -m astrid.core.pack.cli --help`, and `pack cli new/validate/inspect --help` (7 help calls; all exit 0).

Counts for the shared audit: 34 file-read attempts (including 1 failed path target; 33 successful files), 7 help calls, 2 filesystem discovery scans, 1 path backtrack, and 0 SDK discovery calls. Context warmed after query 11: core orientation, creative-work routing, Pack Builder decision map, rendering conventions, pack authoring/discovery docs, and the relevant manifest shape were reused for queries 12–15 without rereading.

## Query results

### 11. “Build a reusable animated title effect I can use in videos.”

Classification: **success for navigation; implementation readiness depends on the title contract**.

Evidence: `creative-work` routes timeline elements/rendering to `rendering` (`Astrid/astrid/packs/_core/skill/creative-work/SKILL.md:21-25`); Pack Builder explicitly classifies an editable visual effect/animation as an **element** (`Astrid/astrid/packs/_core/skill/pack-builder/SKILL.md:42-57`). Existing title primitives are `rendering` `text-card` (`Astrid/astrid/packs/rendering/elements/effects/text-card/element.yaml:11-20,38-57`) and `type-on` (`Astrid/astrid/packs/rendering/elements/animations/type-on/element.yaml:13-23,47-59`). The stable final route is timeline selection followed by `rendering.render` (`Astrid/astrid/packs/rendering/skill/SKILL.md:74-91,106-122`).

Shortest supported route: discover/inspect the element registry with `sdk.discover()` / `sdk.get_capability(..., kind="element")`; compose `text-card` + `type-on` in a project timeline; save the complete timeline document with CAS version; render through `rendering.render`. If the requested title behavior exceeds those primitives, author a new rendering element in the owning source pack, validate it, then discover and use it. `rendering.html_canvas_effect` is a local effect scaffold (`Astrid/astrid/packs/rendering/executors/html_canvas_effect/executor.yaml:3-8,66-73`), but it is a creation aid, not a title-specific endpoint.

Missing inputs: project, timeline, title text, visual style/layout, duration/frame rate, and whether existing `text-card`/`type-on` are sufficient.

Ambiguities: “build” may mean use an existing title element or author a new reusable element; “animated” does not specify reveal, motion, or transition behavior.

Unnecessary detail/friction: core orientation sends an agent to the pack catalog, then Pack Builder and rendering docs. The HTML-canvas scaffold adds source-authoring detail before the title’s visual contract is known, but the authored path is usable.

Actual per-query incremental counts were not separately measured: the trace used shared reads and one initial help census. The SDK discovery/lookup calls in the route above are proposed, not executed.

### 12. “Turn my repeatable transcribe-select-cut-render workflow into a reusable Astrid pack.”

Classification: **success** (authoring path is explicit; implementation was intentionally not performed).

Evidence: Pack Builder says to try composition first, then choose executor/orchestrator, and forbids executors calling orchestrators (`Astrid/astrid/packs/_core/skill/pack-builder/SKILL.md:42-68`). The editorial pipeline already exposes transcribe through arrange, cut, render, review, and validate, with cross-pack ownership clearly shown (`Astrid/astrid/packs/editorial/skill/SKILL.md:10-34`). Pack authoring supplies the exact scaffold/manifest/component/validation sequence (`Astrid/docs/packs/creating-packs.md:17-36`; `Astrid/astrid/packs/_core/skill/pack-builder/SKILL.md:70-90`).

Shortest supported route: `sdk.discover()` and inspect `editorial.transcribe`, `editorial.arrange`, `video_editing.cut`/the relevant orchestrator, and `rendering.render`; write one new orchestrator that invokes existing capabilities in the desired order; scaffold a pack with `python3 -m astrid.core.pack.cli new <pack_id>`; declare `pack.yaml`, orchestrator manifest/`run.py`/`STAGE.md`/skill docs; run `python3 -m astrid.core.pack.cli validate <path>`; confirm cold-agent SDK discovery. Use a new executor only for a genuinely missing atomic operation.

Missing inputs: pack id, exact selection rule/brief format, source media contract, project binding, review gate behavior, and desired outputs.

Ambiguities: “select” could mean quote/scene/shot selection or human review; “cut” could mean existing `video_editing.cut` or a new policy layer.

Unnecessary detail/friction: authoring requires several source-of-truth docs and explicit manifests; the user-facing request has no one-step “promote this workflow” command. The docs do, however, give a coherent and recoverable route.

Actual per-query incremental counts were not separately measured. The SDK catalog/inspect calls in the route above are proposed, not executed.

### 13. “Compare a set of generated image experiments in a review gallery.”

Classification: **success**.

Evidence: creative-work routes comparison to `iteration` (`Astrid/astrid/packs/_core/skill/creative-work/SKILL.md:24-27`). `iteration.experiment_prepare` normalizes provider manifests to `review.json`/diagnostics (`Astrid/astrid/packs/iteration/executors/experiment_prepare/STAGE.md:8-27`); `iteration.experiment_review` renders a deterministic HTML gallery with case cards, inputs, prompts, outputs, and playback (`Astrid/astrid/packs/iteration/executors/experiment_review/STAGE.md:8-45`); the interactive session is available when rubric decisions are needed (`Astrid/astrid/packs/iteration/orchestrators/experiment_review_session/STAGE.md:8-19,21-45`).

Shortest supported route: prepare an `experiment.json` plus runs/manifests with `iteration.experiment_prepare`; invoke `iteration.experiment_review` with `review.json` and optional `runs_dir`; use `iteration.experiment_review_session` when scored decisions/notes must be persisted. Inspect via SDK discovery and explicit `kind`.

Missing inputs: experiment definition, run/manifests location, desired rubric or conclusions, project, and whether static HTML or interactive review is wanted.

Ambiguities: “generated image experiments” may be runtime-owned runs or unmanaged legacy folders; the former should use runtime-derived manifests, while the latter needs the documented import/prepare path.

Unnecessary detail/friction: the gallery is a two-stage prepare→review route, and interactive review adds a third orchestration layer; the user must know or supply the experiment contract.

Actual per-query incremental counts were not separately measured. The SDK route lookup above is proposed, not executed.

### 14. “Add Foley to an existing short video.”

Classification: **partial; documentation handoff gap for the literal deliverable**.

Evidence: creative-work routes Foley to `foley.foley_map` or `fal.fal_foley` (`Astrid/astrid/packs/_core/skill/creative-work/SKILL.md:25-27`). The Foley pack is explicitly spatial: tile video, generate per-tile Foley, review, and emit a spatial audio viewer (`Astrid/astrid/packs/foley/skill/SKILL.md:1-20`). Its documented output is `tiles.json`, per-tile audio, and `review.html`; no final muxed video is listed (`Astrid/astrid/packs/foley/orchestrators/foley_map/STAGE.md:77-87`). The orchestrator also requires external FAL and VLM credentials (`Astrid/astrid/packs/foley/skill/SKILL.md:42-49`).

Shortest supported route: for a spatial soundscape, invoke `foley.foley_map` with `kind="orchestrator"`, video, grid/overlap/trim, and project; stop after review, flag bad tiles, and retry flagged tiles. For ordinary whole-video Foley, inspect `fal.fal_foley`, place the resulting audio on the existing runtime timeline, and use the normal timeline/render path. The docs do not provide one explicit handoff recipe from Foley outputs to that timeline.

Missing inputs: source video, spatial-vs-global Foley intent, tile grid/overlap/trim, prompt/style, target timeline/project, and whether the expected deliverable is a review viewer or a rendered MP4.

Ambiguities: “add Foley” normally implies one finished video with synchronized audio; the documented pack’s canonical output is a spatial audio viewer and review manifest, not that finished video.

Unnecessary detail/friction: the route exposes grid economics and tile retry mechanics before establishing whether spatial Foley is desired. The documentation leaves the Foley-output-to-timeline handoff implicit.

Actual per-query incremental counts were not separately measured. The SDK route lookup above is proposed, not executed.

### 15. “Publish my finished video to YouTube.”

Classification: **success for navigation; readiness depends on external hosting and Zapier/OAuth configuration**.

Evidence: creative-work maps publishing to `youtube.upload` (`Astrid/astrid/packs/_core/skill/creative-work/SKILL.md:29-30`). The executor is implemented and is a terminal service executor (`Astrid/astrid/packs/youtube/executors/upload/STAGE.md:1-10,70-82`), with exact required/optional fields (`Astrid/astrid/packs/youtube/executors/upload/STAGE.md:57-68`; manifest `Astrid/astrid/packs/youtube/executors/upload/executor.yaml:13-60`). It requires a reachable HTTP(S) video URL and configured banodoco-social Zapier webhook (`Astrid/astrid/packs/youtube/executors/upload/STAGE.md:12-21`).

Shortest supported route: finish and validate/render the video; host it at a reachable HTTPS URL; discover/inspect `youtube.upload`; invoke `sdk.invoke("youtube.upload", kind="executor", project=<project>, inputs={video_url,title,description, optional tag/tags, privacy_status, playlist_id, made_for_kids})`. Confirm the returned runtime receipt and publication result.

Missing inputs: reachable video URL, title, description, privacy status, optional tags/playlist/kids flag, project, and working Zapier/OAuth configuration.

Ambiguities: “finished” may mean an existing successful runtime render or merely a local file; the executor cannot ingest a local file directly.

Unnecessary detail/friction: hosting is an external step outside Astrid, and the upload endpoint forwards metadata to Zapier rather than accepting a local MP4. The exact schema and endpoint are otherwise clear.

Actual per-query incremental counts were not separately measured. The SDK route lookup above is proposed, not executed.

## Totals

Query classifications: 4 success for navigation (11, 12, 13, 15), 1 partial (14 documentation handoff). Readiness caveats are explicit for 11, 14, and 15. Shared navigation was reusable after query 11; later queries required no new backtracking. No state-changing action was taken.
