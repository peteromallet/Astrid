---
name: astrid-timeline
description: >
  Discover, inspect, edit, save, render, and open runtime-owned Astrid
  timelines as one creative workflow. Use when shaping a canonical timeline,
  reviewing its visual evidence, producing a video, or opening the resulting
  render.
---

# Astrid timeline workflow

This workflow edits and renders timeline content. When the request also needs
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

For visual continuity review, use the rendered filmstrip. It samples the exact
successful render into an offline HTML viewer and chronological PNG/SVG contact
sheets, with Markdown and a machine-readable frame index. Omit `--out`; Astrid
owns the run and returns local delivery paths for verified copies of the
published evidence objects. The durable authority is the managed run's
digest-verified bundle/manifest, not those disposable local paths.

```bash
python3 -m astrid timelines visualize <slug-or-id> --project <project> \
  --view filmstrip --render-run latest --every 0.5 --columns 5 --page-size 50 --include-media --json
python3 -m astrid timelines visualize <slug-or-id> --project <project> \
  --view filmstrip --render-run <exact-render-run-id> --at 12 --context 3 --every-frames 6
```

Use `--sample interval` (default) for regular time samples, `--sample clips`
for picture clips, `--sample cuts` for cut boundaries, and `--sample shots`
for authored story beat midpoints. Shots require authored shot metadata.
Interval samples retain adjacent visual cut frames even between sample ticks.
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

Filmstrips require a successful render with its frozen timeline snapshot and
managed video. They do not substitute source asset thumbnails. Script captions
remain authored segment text, not word-aligned transcription. Missing or
uncertain speech timing is reported as unavailable/partial, while waveform
inspection remains usable; opening the inspector never starts a provider call.
`--include-media` explicitly adds a relative, hash-verified video member for
offline playback. Analysis sidecars are bounded, keyed by immutable render and
settings identity, and verified in the bundle manifest. A pinned render keeps
old visual evidence associated with its own timeline state even after later
edits.

For the structural timeline diagram and frozen object navigation, use
`--view structure` (the compatibility default):

```bash
python3 -m astrid timelines visualize <slug-or-id> --project <project> \
  --view structure --format md,png,svg --layout both --filmstrip off --json
```

Structural views support `--all`, a prior manifest with `--from-view`/`--focus`,
and the legacy `--filmstrip rendered --rendered-video` thumbnail policy. The
structural `--from-view`/`--focus` grammar addresses frozen object manifests;
the filmstrip inspector's render-scoped frame/clip/track targets are separate
until an explicit adapter exists. Use the frame index's pinned focus command to
navigate a rendered inspector.

## Create and edit

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

Render through the product command. The positional reference is a runtime slug,
UUID, or ULID; it is never a file path. Rendering pins the current kernel
snapshot. Add `--expected-version` when the observed version must remain
unchanged, select a qualified backend only when needed, and use `--detach` only
when admission without terminal completion is intended:

```bash
python3 -m astrid timelines render <slug-or-id> --project <project> \
  --expected-version <version> --output-name <name>.mp4 --json
```

For a review copy, add `--review`: `astrid timelines render <ref> --project <project> --review`. Remotion and Three.js show the registered shot name and running timeline time in the top-right corner, plus the pinned authored voiceover script as a readable bottom caption. Caption timing is the canonical shot interval and is explicitly marked non-word-aligned; no ASR timing is invented. Names and captions are pinned from canonical shot references and text bindings before expansion. Gaps show `No shot`; overlapping shots show all active names. The overlay exists only in this render; saved timeline documents are unchanged. FFmpeg rejects review mode explicitly. Omit the flag for a clean export. SDK inputs use `"review": true`.

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
