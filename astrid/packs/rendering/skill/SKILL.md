---
name: astrid-timeline
version: astrid-timeline-2026.09.23.1
description: >
  Author, inspect, edit, preview, render, and open runtime-owned Astrid
  timelines as one creative workflow. Use when shaping a canonical timeline,
  reviewing its textual or visual evidence, producing a video, or opening the
  resulting render. Text and visual inspection are sister views over one
  pinned composition, not separate timeline authorities.
---

# Astrid timeline authoring and inspection

This workflow opens, inspects, edits, previews, renders, and opens timeline
content. Rendering is one downstream evidence action, not a second timeline
authority or the name of the editing model. When the request also needs
new generated media (for example Foley audio), use [creative work](../../_core/skill/creative-work/SKILL.md)
to find its generation capability, then return here to assemble the result.

Treat the connected workspace runtime as the sole authority for projects,
timeline documents, versions, media objects, tasks, runs, and render outputs.
Use the public CLI or SDK; do not edit a checkout database, event log, CAS tree,
or generated run directory. Read current help before using a new option:

```bash
python3 -m astrid --help
python3 -m astrid timelines --help
```

## Agent operating contract

The timeline is one canonical authoring composition. `timelines show` (and the
typed authoring-bundle opener) is the bounded structural/text view;
`timelines visualize` is the rendered/input visual view; and offline
`timelines inspect --manifest` is a bounded read-only view of an already
published evidence pack. These are sister commands over the same identity and
time model in the single `timelines` product family. Internally,
`timelines visualize` delegates to the qualified `rendering.timeline_visualize`
capability because rendering owns the evidence-producing backend; that
implementation boundary is not a user-facing pack boundary. Never invent a
second text-only timeline, treat a filmstrip as a new source of truth, or
switch to a mutable child document because it is easier to read.

Use this loop for every inspection or edit:

1. **Resolve and pin scope.** Resolve the project and timeline explicitly, then
   capture one current authoring head, candidate digest, or explicit historical
   render identity. Label the lifecycle (`current`, `candidate preview`,
   `historical`, or `unverified legacy`) in the answer.
2. **Start broad, then narrow.** Get the compact structural overview first.
   Expand an occurrence, then its clip/track/property, then exact text or
   source media. Use the visual view to confirm what is on screen at the same
   target/time; use the text view to explain ownership, roles, bytes, and
   diagnostics. Do not scan the entire media library when a target can be
   addressed directly.
3. **Carry one target between views.** Every result is navigated by the same
   `occurrence_id` plus optional clip, track, media, text/property path and
   half-open time window. Shot names and ordinals are display conveniences, not
   identity. Switching text ↔ visual preserves scope, target, time window,
   expansion, and filters. A missing frame or source is reported explicitly;
   never substitute a nearby frame or a different occurrence.
4. **Choose the smallest supported edit.** Use a public command for a direct,
   exact primitive (replace media, sequence, reorder layers, quantize, ripple,
   text binding, or render). For a repeated or data-dependent change, open the
   same pinned authoring bundle and use ordinary Python/SDK code against its
   objects. That code is a detached candidate, not a new format or hidden
   command language. Do not edit Runtime files directly, call undocumented
   endpoints, or silently rebase a stale candidate.
5. **Validate, preview, publish once.** Validate the complete candidate, inspect
   its diff, and preview the frozen candidate when visual confirmation matters.
   Commit through the existing compare-and-swap/idempotent publication boundary.
   Re-read the newly published closure by its returned IDs (not a seed map),
   then use the visual view/render to verify the actual changed media and timing.
6. **Explain the evidence.** Report what was observed, what was changed, and
   what remains unavailable separately. A successful command, a semantic
   readback, a decoded media check, and a browser/render proof are different
   claims; do not collapse them into one “done”.

The short agent preamble is:

> Open one pinned composition. Find the target in the structural view, carry its
> exact identity to the visual view, and expand only as needed. Use the smallest
> supported command; otherwise edit a detached same-schema candidate with
> ordinary code. Validate, diff, preview, publish once, reopen the published
> closure, and verify the result in both views. Keep current, candidate, and
> historical evidence distinct.

This contract deliberately favors simple primitives for common work and code
for complex batch work. It does not add a DSL, persistent checkout, new media
store, or automatic merge service.

## Discover and inspect

Resolve the project explicitly whenever more than one project is visible. List
timelines for a compact inventory, then show the selected timeline for its
complete config, registry, identity, and `config_version`:

```bash
python3 -m astrid projects list --json
python3 -m astrid timelines list --project <project> --json
python3 -m astrid timelines show --project <project> <slug-or-id> --json
python3 -m astrid timelines history --project <project> <slug-or-id> --json
python3 -m astrid timelines diff --project <project> <slug-or-id> --json
```

For SDK callers that need the same bounded structural result as the CLI,
`client.timelines.open_composition(project, ref, ...)` is the shared read-only
adapter. It returns the pinned query, summary, targets, rows, pagination,
media classifications, diagnostics, and scope-preserving actions used by
`timelines show`; it does not create a second timeline document. The adapter's
scope marks source-media actions as metadata-only until Runtime exposes a
digest-bound source handle, so agents must not claim source playback or exact
frame access from `media.show` alone:

```python
opened = client.timelines.open_composition(
    "<project>", "<timeline>", occurrence="<occurrence-id>",
    range_value="10..15", limit=20, detail=True,
)
```

Keep the returned `head`, parent/revision identity, candidate digest, and
render identity together. A cursor is valid only for that complete scope;
reopen the composition after a head change instead of continuing an old page.

For visual continuity review, use the rendered filmstrip. It samples the exact
successful render into chronological PNG contact sheets, with Markdown and
a machine-readable frame index. Omit `--out`; Astrid
owns the run and returns local delivery paths for verified copies of the
published evidence objects. The durable authority is the managed run's
digest-verified bundle/manifest, not those disposable local paths.

When `output` and `inputs` are both shown, the primary page uses a paired-row
layout: five (or the requested `--columns`) output samples per row with the
input lanes relevant to that row immediately underneath. The row's linear
half-open time axis is shared by cards, placements, audio rails, and the PNG
and `static_surface.rows` JSON contract.
Paired pages show one row by default (five columns unless changed with
`--columns`; `--columns 6` gives six across), while standalone output/input
pages keep their normal page sizing. Pass `--page-size N` explicitly to opt
into a denser paired page, capped at two rows / 10 cards. Multi-page paired
results are intentional: open the numbered pages in order, then rerun with
`--range START..END --every 0.25` or `--shot first` / `--shot N` to drill down.
The frame index records the effective page size, page count, row ranges, and
copyable navigation guidance.

For a complete review pass, use `--show output,inputs,text,audio --every 5`.
The command reports the primary PNG, all numbered pages, and a bounded inspect
command. Open the pages in order; then use `--range 0..25 --every 0.25 --detail`
to zoom into one window, `--shot first` (or `--shot N`) to focus an authored
shot, and `--track vo` to isolate the voice lane. Use `--every` for seconds,
`--every-frames` for exact frame steps, `--columns`/`--page-size` for layout,
and `--resolution` for thumbnail size. The generated navigation metadata
contains copyable versions of these commands, so the full-timeline result is
the starting point rather than a dead-end overview.

```bash
python3 -m astrid timelines visualize <slug-or-id> --project <project> \
  --view filmstrip --render-run latest --every 0.5 --columns 5 --page-size 50 --include-media --json
python3 -m astrid timelines visualize <slug-or-id> --project <project> \
  --view filmstrip --render-run <exact-render-run-id> --at 12 --context 3 --every-frames 6
```

Use `--sample interval` (default) for regular time samples, `--sample clips`
for picture clips, `--sample cuts` for cut boundaries, and `--sample shots`
for authored story beat midpoints. Shots require authored shot metadata.
An explicit `--every` or `--every-frames` interval is a strict periodic grid;
pass `--include-cuts` when cut-neighbor frames should be added explicitly.
Shot-script context is retained in JSON/details and is shown once per shot
occurrence on review cards when no word/phrase timing exists; later samples
stay visually quiet while their machine-readable status is “same shot; no new
timed text.” Frozen timed speech captions
still take precedence, and “No timed text available” is used only when there
is no applicable timed phrase or shot script.
Use `--range 10..20`, `--shot`, `--clip`, or `--asset` to restrict the view.
The unified inspector can search dialogue, filter shots and time ranges, reduce
density, expand declared visual/audio tracks on one shared absolute-time ruler,
and enlarge a frame or copy its time, render-scoped target, and pinned focus
command. When the admitted render has audio, the disclosure adds bounded
multi-resolution waveform bins, measured “Quiet gap” intervals, and only
explicitly admitted immutable speech annotations. Audio rows are frozen to the
render; they never turn missing script into silence or present the rendered mix
as an isolated stem. Selecting an audio interval seeks the optional bundled
media and keeps the same frame/clip/track target model. If a clip has no
captured frame in its interval, the inspector says so and exposes the exact
focus command.
Density controls only select already captured frames; rerun with a finer
interval for additional detail. Extraction is bounded at 2,000 frames, so use
a coarser interval or a narrower range for long renders.

The PNG waveform uses a bounded display-only gain/contrast curve so quiet voice
remains visible; the JSON retains the measured amplitudes. Source audio-track
rails are timing signifiers (not per-source loudness measurements), and use the
same absolute time axis as the cards and input placements. In input lanes, each
rail is centered vertically inside its source clip and its label gets a dark
backing chip for legibility.

Filmstrips require a successful render with its frozen timeline snapshot and
managed video. They do not substitute source asset thumbnails. PNG cards show
spoken text in quotes and a prominent local waveform/cursor when the admitted
render has audio. Script captions
remain authored segment text, not word-aligned transcription. Missing or
uncertain speech timing is reported as unavailable/partial, while waveform
inspection remains usable; opening the inspector never starts a provider call.
`--include-media` explicitly adds a relative, hash-verified video member for
offline playback. Analysis sidecars are bounded, keyed by immutable render and
settings identity, and verified in the bundle manifest. A pinned render keeps
old visual evidence associated with its own timeline state even after later
edits.

The rendered paired filmstrip/storyboard is the only timeline visualization.
There is no separate structural diagram or frozen-object navigation route.
Use the managed filmstrip commands above with `--render-run`; do not supply a
caller-owned `--rendered-video` path. The frame index's render-scoped
range/shot/clip/track targets are the canonical navigation surface.

Use a coarse `--every 5` pass to locate a transition, then rerun the exact
time window with a finer `--every 0.25` (or `--every-frames 1` for frame-level
inspection) and add `--detail`. `--range START..END` is half-open, so the end
sample is excluded. `--shot first` and numeric `--shot N` use authored shot
order; use the exact shot name or a time range when chronological order is
what matters.

### Structural-to-visual navigation recipe

For an agent-facing investigation, keep the structural and visual calls next
to one another and reuse the returned target:

```bash
# 1. structural overview/current head
python3 -m astrid timelines show --project <project> <timeline> --json

# 2. visual overview on the exact successful render
python3 -m astrid timelines visualize <timeline> --project <project> \
  --view filmstrip --render-run <exact-render-run-id> \
  --show output,inputs,text,audio --every 5 --json

# 3. narrow both views to the same shot/time/clip/asset/track
python3 -m astrid timelines visualize <timeline> --project <project> \
  --render-run <exact-render-run-id> --shot <shot-id> \
  --range <start>..<end> --clip <clip-id> --detail --json
python3 -m astrid timelines inspect --manifest <manifest-path> \
  --section cards --limit 20 --json
```

The exact structural expansion is supplied by the authoring-bundle SDK when
the CLI `show` payload is not enough; it must return the same occurrence IDs,
media digests, and intervals that the visualizer uses. A result that cannot be
mapped back to the pinned scope is incomplete, not a new identity.

## Create and edit

The native timeline-evaluation worker resolves this checked-in skill at
`astrid/packs/rendering/skill/SKILL.md`. Its public brief pins the absolute path,
version, and SHA-256 so a worker can verify that it is reading these exact
instructions; there is no separate installed copy or package-manager step.

### Canonical edit bundle

Use the same pinned parent composition for direct edits and code-driven batch
edits. `timelines show` opens a read-only inspection projection; it is not the
editable bundle. For an exact parent-media replacement, use the supported
`timelines replace-parent-media` command only when the case-specific target
receipt declares that route and supplies its required locator. For other
supported edits, use ordinary Python against the detached same-schema bundle:

```python
from astrid.core.timeline.authoring_bundle import (
    open_authoring_bundle, validate_authoring_candidate,
    diff_authoring_candidate, preview_authoring_candidate,
    publish_authoring_candidate,
)

candidate = open_authoring_bundle(
    pinned_parent, shot_revisions=pinned_shots,
    internal_timeline_revisions=pinned_internal_timelines,
)
# Make the requested small edit or run a deterministic batch transform here.
validate_authoring_candidate(candidate)
diff = diff_authoring_candidate(candidate)
preview = preview_authoring_candidate(candidate)  # only when visual confirmation is useful
publication = publish_authoring_candidate(candidate, writer, idempotency_key=run_id)
# Reopen the returned parent/shot/internal revision closure and verify it.
```

Keep the exact publication response, including its `new_head` and complete
`dependency_manifest`, then reopen that returned closure rather than trusting
the candidate, seed map, or an agent-authored snapshot. These operations are
public where documented; an unsupported case-specific route must be reported
as unavailable, not inferred from the composition's shape.

The older `timelines save --config ... --registry ... --expected-version ...`
command below is a separate legacy whole-document compare-and-swap interface.
It requires the complete document and is not a substitute for the pinned
parent/shot/internal bundle workflow or the targeted parent-media route.

Create a named runtime timeline once; the returned document starts at
`config_version: 1`. A save is a whole-document compare-and-swap: `config` and
`registry` are both required, and `--expected-version` must equal the version
observed by `show` (or create). Merge edits into the freshly shown document:

```bash
python3 -m astrid timelines create --project <project> <slug> \
  --name "<name>" --config '<config-json>' --registry '<registry-json>' \
  --default --json

python3 -m astrid timelines save --project <project> <slug-or-id> \
  --config '<complete-config-json>' --registry '<complete-registry-json>' \
  --expected-version <version> --json
```

The user edit may be narrow, but the save payload must contain the complete
current document; do not reuse a stale snapshot. On a version conflict, run
`show`, reconcile the intended edit against the current complete document, and
retry with its new version. Preserve managed media identity and digests in the
registry; raw source paths, URLs, and private CAS locators do not belong in
durable canonical state. For reusable project shots, use nested `timelines
shots` commands.

To group existing timeline clips into a named shot, use the canonical grouping
command rather than constructing shot resources and child documents by hand:

```bash
python3 -m astrid timelines shots group <timeline> --project <project> \
  --clip <picture-clip-id> --clip <voiceover-clip-id> --name "Opening" \
  --expected-version <version> --json
```

The command creates a registered shot and child timeline, associates its managed
media, and replaces the selected clips with one shot clip. It preserves their
timing and authored order. Selected clips must be adjacent in the document's
clip order; nested shots are unsupported. Use `--hold <seconds>` to extend the
shot window through an intentional pause. Read `show` again before grouping
the next shot, since each successful group advances the timeline version.
For a transient failure partway through, retain the returned idempotency key
and retry the same arguments with `--idempotency-key <key>`; the parent timeline
is saved last. A parent version conflict needs a fresh inspection, updated
version, and new key; the error identifies any resources left unattached by the
earlier attempt. Keep effects spanning multiple shots on the parent timeline.

Keep narration in the shot's canonical `voiceover_script` text binding alongside
its voiceover media. Do not leave the only copy in a generation script:

```bash
python3 -m astrid timelines shots text set <shot-id> --project <project> \
  --kind voiceover_script --text-file <script.txt> --expected-head 0
python3 -m astrid timelines shots text list --project <project> \
  --kind voiceover_script
```

`list` and `show <binding-id>` include the verified text. Use head `0` to create
a binding; read its current head before updating it. The binding belongs to
the registered shot referenced by the timeline; it does not add visible text
or regenerate audio. Managed renders pin its immutable text identity and head
in provenance. When importing an existing script, verify that it corresponds
to the shot's current voiceover audio.

The config must be renderable before spending a render attempt. Keep clip types
explicit, use registered element IDs for custom visual elements, and keep the
output/profile compatible with the authoritative theme canvas. Read
[references/timeline-cookbook.md](references/timeline-cookbook.md) when
constructing or checking the JSON shape.

For the constrained transparent PNG layer supported by the FFmpeg backend, use
one ordinary managed `clipType: "media"` clip with a positive `hold` on a
visual track placed first, followed by exactly one ordinary visual picture
track:

```json
{
  "tracks": [
    {"id": "overlay", "kind": "visual"},
    {"id": "picture", "kind": "visual"}
  ],
  "clips": [
    {"id": "overlay", "at": 0, "track": "overlay", "clipType": "media", "asset": "managed-alpha.png", "hold": 1.0},
    {"id": "picture", "at": 0, "track": "picture", "clipType": "media", "asset": "managed-video.mp4", "from": 0, "to": 1.0, "volume": 0}
  ]
}
```

The registry entry for `managed-alpha.png` must resolve to a local, probed PNG
whose decoded dimensions exactly match the visual canvas and whose PNG bytes
declare transparency. This subset supports one full-duration static layer;
arbitrary transforms, crop, per-layer blending, and multiple held overlays are
unsupported. The overlay is looped, bounded to its hold interval, normalized to
the canvas, and composited after the base visual concat; existing text overlays
still use their current path. Stream copy is disabled for this overlay path.

## Render and open

For an editorial feedback cycle (including reference-frame and storyboard
previews), render with `--review` by default and keep it enabled for subsequent
revisions. Deliver and open that review render so the user can identify frames
by shot name and timecode. Use meaningful registered shot names, and check that
the labels are visible in the exported video. A filmstrip viewer is useful
alongside the video, but does not replace its review overlay. Omit `--review`
when the user requests a clean or final export.

Render through the product command. The positional reference is a runtime slug,
UUID, or ULID; it is never a file path. Rendering pins the current kernel
snapshot. Add `--expected-version` when the observed version must remain
unchanged, select a qualified backend only when needed, and use `--detach` only
when admission without terminal completion is intended:

```bash
python3 -m astrid timelines render <slug-or-id> --project <project> \
  --expected-version <version> --review --output-name <name>-review.mp4 --json
```

Review mode shows the registered shot name and running timeline time in the top-right corner in Remotion and Three.js, plus the pinned authored voiceover script as a readable bottom caption. Caption timing is the canonical shot interval and is explicitly marked non-word-aligned; no ASR timing is invented. Names and captions are pinned from canonical shot references and text bindings before expansion. Gaps show `No shot`; overlapping shots show all active names. The overlay exists only in this render; saved timeline documents are unchanged. FFmpeg rejects review mode explicitly; choose a review-capable backend for editorial previews rather than silently dropping the flag. SDK inputs use `"review": true`.

Remotion review renders default to a backend-native low resolution that fits the
authored canvas inside 640x360 while preserving its aspect ratio. The canonical
canvas remains in the timeline props and all positions are evaluated there;
Remotion's `--scale` performs the output scaling. The resulting artifact
profile records the dimensions Remotion actually emits. Such renders carry the
exact `Low Res Render` label at top left, while shot name and timecode remain at
top right. A clean render, or a render with an explicit profile, keeps the
existing full-resolution behavior.

Review labels and subtitles are inspection overlays. Keep the authored
creative composition centered in the full canvas; do not shift primary visual
content or reserve a caption-safe band for review text unless the user
explicitly requests a caption-safe design. Review typography scales with the
authored canvas under `--scale`, while badge readability is handled separately.

The default waits for completion and propagates terminal failure. A successful
render records its run and provenance in the runtime. Review the newest
successful render, or an exact run, through the runs surface (opening video is
currently supported on macOS):

```bash
python3 -m astrid runs open --project <project> --timeline <slug-or-id>
python3 -m astrid runs open <run-id> --project <project>
```

Use `--default-timeline` for the project's default. If no matching successful
render exists, render first or inspect `runs list/show`.

The [render capability contract](../executors/render/STAGE.md) covers detailed
SDK inputs and outputs; the [visualization contract](../executors/timeline_visualize/STAGE.md)
covers evidence navigation.

## SDK equivalent

Use the typed client or `astrid.sdk` when embedded in a program. Canonical
render uses `timeline_ref`, not a path-backed `timeline`:

```python
import astrid.sdk as sdk
result = sdk.invoke(
    "rendering.render", project="<project>",
    kind="executor",
    inputs={"timeline_ref": "<slug-or-id>", "expected_version": 4},
)
```

Use `rendering.timeline_visualize` for evidence and `client.timelines.show` /
`client.timelines.save` for programmatic editing. Keep `project` explicit and
use returned runtime IDs, manifests, and receipts for durable navigation.

## Renderer authoring

When building or extending a renderer, read the
[pack-builder skill](../../_core/skill/pack-builder/SKILL.md) and the protocol
contract at [docs/contracts/render-backend-v1.md](../../../../docs/contracts/render-backend-v1.md).
Renderer packs advertise qualified protocol capabilities; timeline editing and
the public `rendering.render` facade remain runtime-owned. Do not add a new
facade, direct module invocation, or backend-specific shape to the timeline.

## Runtime-owned multi-step stitching

For a two-child generation flow that must wait durably and preserve declared
output order, use the typed handoff in
`astrid.packs.video_editing.orchestrators.runtime_orchestration` and the stitch
admission in `astrid.packs.rendering.finalizers.runtime_stitch`. These modules
describe the graph and publication settings; the Runtime owns lifecycle,
continuation admission, canonical timeline CAS, and render-task creation. The
registered `rendering.assemble_timeline` executor consumes the claimed
`resolved_children` envelope and emits a deterministic authoring proposal. The
generic pack host sends that proposal through the fenced
`publish_timeline_render` checkpoint, which creates the ordinary
`rendering.render` task. Claim that task through the same host to run the
existing renderer and retrieve its output objects and receipt. Do not add a
pack-local timeline save, scheduler, polling loop, or second renderer.
