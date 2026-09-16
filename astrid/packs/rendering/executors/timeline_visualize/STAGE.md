# Timeline Visualize

`rendering.timeline_visualize` reads one canonical runtime timeline together
with a successful managed render and produces a deterministic paired filmstrip
for agent inspection. Slug, UUID, and ULID selectors resolve the runtime
timeline; the admitted render snapshot and immutable stream head/version/hash
pin provenance. The output is a render-scoped filmstrip pack, not a second
timeline authority.

Use the canonical [Astrid timeline skill](../../skill/SKILL.md) for the
end-to-end workflow and its [timeline cookbook](../../skill/references/timeline-cookbook.md)
for renderable document examples; this stage is the executor contract for the
evidence-producing visualization path.

It is a first-class project executor with one explicitly selected managed
timeline per review run; it is never bound to, or recorded in, a timeline
`manifest.json`.

## Rendered filmstrip view

The rendered paired filmstrip/storyboard is the only continuity-review
view. Filmstrip inputs are
`sample` (`interval`, `clips`, `cuts`, `shots`), `every` (seconds, default 0.5)
or `every_frames` (positive integer, mutually exclusive with `every`),
`render_run` (exact successful run id or `latest`), `columns` (default 5),
`page_size` (default 50 for standalone views; paired output+inputs pages show
one row by default, normally five cards across), the opt-in `include_media` flag, and optional exact
`resolution` (`WIDTHxHEIGHT`) applied by the frame extractor. Range, density,
and resolution are recorded as separate request values. Existing range,
timestamp/context, clip, asset, and shot selectors restrict frame selection.
The shared component grammar is `--show COMPONENT` (repeatable or
comma-separated: `output`, `text`, `audio`, `inputs`) and `--hide COMPONENT`;
`--track` is repeatable and `--detail` enlarges the current selection.
`--show inputs --hide output` is render-free input inspection and emits
readable, paginated input-band PNGs plus the machine-readable frame index.
When `inputs` and `output` are selected together, the primary static PNG page
is a paired-row surface: up to `columns` (default five) sampled rendered cards
are grouped per row, and the input lanes active in that row sit directly below
them. Each row has one linear, half-open time window; card positions, input
placements, audio rails, and the row ruler all use that same window. The raw
rendered page and input-band pages remain in the bundle as auxiliary evidence.
The JSON `static_surface.rows` metadata lists each row's card ids, exact time
range, and active input tracks; SVG mirrors the same composed surface as the
PNG. This is the default combined layout, while output-only and input-only
views retain their existing layouts.

Combined results may produce several numbered pages intentionally; by default
each paired page is one row of cards. Pass `--columns 6` for six across, or
pass `--page-size N` explicitly when a denser two-row page is useful. Open
`filmstrip-001.png`, `filmstrip-002.png`, and so on in order. Use
`--page-size N` for a smaller/focused page, `--columns N` to change row width,
and rerun with `--range START..END --every 0.25` or `--shot first`/`--shot N`
to drill into a page or authored shot. The returned frame-index navigation
metadata repeats these commands and the effective page count.

An explicit `--every` or `--every-frames` request is a strict periodic grid.
Use `--include-cuts` with interval sampling when cut-neighbor evidence is also
wanted; those extra frames are never inserted implicitly.

Shot focus accepts an exact canonical shot id or name, plus the friendly
aliases `first` and positive one-based ordinals. For example, `--shot first`
and `--shot 1` select the first authored shot, while `--shot 2` selects the
second. Exact id/name matching wins first, so an authored shot whose id is
literally `1` remains addressable as `--shot 1`; aliases resolve only when no
exact match exists. Ordering is the frozen authored `pinnedShotGroups` /
admission occurrence order. An out-of-range ordinal fails with the available
shot count rather than producing an empty view. The same selector is applied
to rendered, input-only, and synchronized filmstrip surfaces.

```bash
python3 -m astrid timelines visualize main --project demo \
  --view filmstrip --render-run latest --every 0.5 --include-media
python3 -m astrid timelines visualize main --project demo \
  --view filmstrip --render-run <exact-run-id> --range 10..20 --every-frames 6
```

The executor samples presentation frame numbers from the actual managed
render video with ffmpeg and rational frame timing. It uses the render's
frozen timeline snapshot for clip and script annotations; current edits do
not silently annotate an older render. Missing render provenance fails with
an actionable error. SDK-injected `filmstrip_authority` is internal handoff
data, never a public caller override.

The frame index records integer frames, rational times, active clips, complete
shot-script context, timed caption projections, sample reasons, render
provenance, and commands pinned to the exact render run. When audio is present it also records a digest-scoped
analysis identity, bounded channel-preserving waveform levels, measured
low-amplitude quiet gaps, and (when explicitly admitted in the frozen input)
projected speech phrases. `clips` means picture-clip first frames, `cuts` means
cut boundaries, and `shots` means authored story beat midpoints. There is no
inferred scene detection. Shot-script context is never presented as a precise
frame caption: when no timed phrase covers a sample, cards show each
applicable shot script once per occurrence (marked “Shot script
(not word-aligned)”). Later samples in that same coarse shot are intentionally
quiet in the visual strip; their machine-readable status remains
“same shot; no new timed text.” “No timed text available” remains the honest
status when neither timed speech nor an applicable shot script exists.
Sampling is bounded at 2,000 cards and fails with guidance to narrow the
range or increase the interval.

Outputs include chronological paginated PNG and SVG contact sheets, Markdown,
and JSON frame cards. Cards show time,
frame, human shot name, and wrapped spoken text; PNG cards also include a
prominent card-local waveform and frame-time cursor whenever the admitted render
has audio. The filmstrip view is the
unified inspector: it adds expandable declared visual/audio track lanes on the
same time ruler and uses the frozen snapshot's integer clip intervals. The
canonical JSON keeps every declared track, while paired rows omit lanes with no
placement in that row so inactive tracks do not create dead space. Input-only
views can still expose the complete declared track set. Declared audio lanes are
placement intervals, while rendered waveform rows appear only when the admitted
render has an audio stream.
A source clip that declares or occupies an audio lane also carries an
`audio_signifier` with its exact timeline and source-time window; the static
input surface draws digest-verified source audio as a measured amplitude
waveform over that exact span (centered vertically in the source placement and
backed by a dark clip-label chip). Source analysis is cached in
`source-audio-analysis/<source-digest>.json` and the clip keeps a compact
interval projection with both measured and display-only amplitudes. If the
source is unavailable, tampered, unsupported, or has no audio stream, the
surface falls back to an amber timing rail with uniform markers and records the
reason; it never fabricates amplitude data. This is deliberately distinct from
the measured composite render waveform: each input waveform describes that
source asset, while the rendered waveform describes the final mix.
The brighter, taller card waveform and source-waveform bars use display-only
gain and contrast; measured amplitudes and all clip timing remain unchanged.
A lane row means timing overlap at the selected time; it does not
assert that the clip contributes visible or audible output when tracks are
muted, occluded, transparent, or otherwise composited away. Preserve those
frozen track flags in the lane metadata. Frame and clip selection share one
render-scoped target. A clip with no captured frame reports that fact and
exposes its exact focus command instead of choosing an unrelated card. Clip
identities remain in the frame index and can be consumed by a downstream
inspection tool. Use the copyable commands in the frame index for dialogue,
shot, time, density, and enlarged-frame queries.
The dense captured-frame grid is a sample of the selected render; it is not a
second time ruler and does not claim unsampled frames exist. It cannot
produce finer sampling from already captured frames; rerun the command for
that. Script captions are segment-level, not word-aligned. “No script” is
separate from any claim about acoustic silence. Filmstrip navigation uses
its frame actions. Missing or uncertain speech timing is unavailable rather than
approximated, and `--include-media`
adds only a relative digest-verified video; the rendered mix is never presented
as an isolated stem.

## Offline inspection

The materialized `manifest.json` is the authority for a bounded, runtime-free
inspection route:

```bash
python3 -m astrid timelines inspect --manifest <manifest_path> --section summary
python3 -m astrid timelines inspect --manifest <manifest_path> --section cards --limit 5
```

Sections are `summary`, `pages`, `cards`, `placements`, `audio`, and
`boundaries`. Selectors and half-open ranges are explicit, responses are capped
at 8 KiB, and `next_cursor` continues a query without loading the full JSON.
The receipt contains only projections and hashed sidecar references; the full
frozen snapshot remains a verified provenance sidecar.

## Read-only contract

The executor reads timeline rows/config/history from the workspace runtime and
materializes one attempt-local snapshot for rendering. It does not read or
repair project timeline files, append events, or update
`manifest.json.contributing_runs`. Existing timeline files remain outside the
product authority boundary.

The managed run ledger owns operational identity and retention. Its metadata
contains sorted `timeline_ids`, `evidence: true`, and the executor contract
digest. Run GC preserves evidence runs by default; removing them requires an
explicit evidence-inclusive GC pass with `--apply` (ledger-level tooling, not
a gateway command).

## Pack layout

The rendered view writes `filmstrip-view/` and publishes `filmstrip-bundle.zip`
and its result manifest as managed objects. The SDK verifies and extracts the
bundle into the deterministic, project-namespaced
cache at `~/Library/Caches/Astrid/timeline-visualize/<project>/<bundle-digest>/`
on macOS (or `$XDG_CACHE_HOME/astrid/timeline-visualize/...` elsewhere),
returning `pages`, `svg_pages`, `markdown`, `frame_index`, and `manifest_path`, plus verified
`audio_analysis` and `media` paths when those members are present. Extraction
uses a hidden sibling staging directory and publishes only after all members
pass integrity checks. The runtime objects remain the durable authority and
the result manifest covers every member.

### Filmstrip result and disposable-host contract

The rendered filmstrip executor returns the existing read-only result envelope
with `manifest_path`, `identity`, `cas`, and `entrypoints` fields. `identity.render`
is the exact tuple `{render_run_id, timeline_id, video_digest}` from the admitted
render. `identity.manifest.content_hash` and
`identity.bundle.content_hash` are SHA-256 content identities; `cas` repeats the
rendered-video, nested-manifest, and bundle digest locators that the host can
publish as CAS objects. They are not inferred from a local filename. The
relative entrypoints are `filmstrip-view/manifest.json`,
`filmstrip-view/frame-index.json`, the first static PNG/SVG/Markdown page,
and `filmstrip-bundle.zip`. The nested manifest remains the filmstrip domain
manifest; the output-root `manifest.json` is the generic
`timeline_filmstrip_result` host receipt with the bundle as its primary result.
This read-only path emits no mutation receipt and no review-specific events.

The assigned output root is disposable attempt storage. The host/run ledger
owns publication and retention of the generic receipt and its CAS outputs;
the executor does not introduce a storage or lifecycle framework. Audio
analysis reuse is a sibling `.audio-analysis-cache/` keyed by the immutable
render digest and analysis settings, bounded to 256 JSON entries with stale
entries removed when a new entry is stored. The cache is disposable: a missing
or invalid entry is recomputed from the same admitted render identity.

For SDK-managed results, the published bundle is read and hash-verified before
being extracted into the deterministic project cache
`~/Library/Caches/Astrid/timeline-visualize/<project>/<bundle-digest>/` (or the
platform XDG equivalent). Extraction uses a hidden sibling staging directory,
publishes with an atomic rename only after every declared member verifies, and
removes failed staging or process-owned rehydrated views. Deleting that local
cache does not change render authority; rehydration can repeat from the
published bundle and its exact digest identities.

## Inputs and navigation

Cold selectors mirror the timeline-navigation façade of the executor: optional
timeline reference (slug, UUID, or ULID), `--shot`, `--range`, `--at`,
`--clip`, `--asset`, `--context`, `--neighbors`, repeatable `--format`,
`--show`/`--hide`, `--track`, `--every`/`--every-frames`, and `--include-media`.
The managed public
`--view filmstrip` route selects a project-owned rendered video with
`--render-run RUN_ID|latest`; it does not accept a caller-owned
`--rendered-video` path. There is no second visualization route.
`project_slug` is the
executor-level project identity and is derived from `project=<slug>` for a
managed SDK invocation. All selectors resolve canonical runtime timelines
created/saved through the public timeline SDK. Standalone timeline paths and
raw event-log files are not product inputs.

The command spelling is singular and repeatable while the SDK field is plural:

```bash
python3 -m astrid.packs.rendering.executors.timeline_visualize.run \
  --out /tmp/agent-view \
  --project-slug desert-plant-growth \
  --timeline-slug storyboard \
  --format png --format svg
# Equivalent: --format png,svg
```

For the normal project-scoped maker path, omit `out` and let Astrid manage the
run-owned output tree:

```python
import astrid.sdk as sdk

result = sdk.invoke(
    "rendering.timeline_visualize",
    kind="executor",
    project="desert-plant-growth",
    inputs={
        "timeline_slug": "storyboard",  # UUID, ULID, or slug; omit for default
        "formats": ["png", "svg"],
    },
)
assert result.ok
print(result.outputs)
```

The same path is available as the public nested timeline command. It is
synchronous, emits the standard five-key CLI envelope with run/kernel IDs and
durable output paths in `data`, and accepts either a slug, UUID, or ULID. The
project may be omitted when a project has been selected:

```bash
python3 -m astrid timelines visualize --project desert-plant-growth \
  --timeline-slug storyboard --format png,svg --format md --json
# Omit --timeline-slug for the project default; use --range/--shot to focus.
```

`--format` is repeatable and comma-separated (`png`, `svg`, `md`, or `all`),
with `all` exclusive of other formats. Invalid ownership, selectors, and
combinations are returned as typed validation errors before a run/task is
admitted.

Do not pass `out` together with `project`: the project-scoped runner supplies
the private staging output and publishes the evidence pack under the managed
run.

Filmstrip navigation is render-scoped: use the frame index's copyable
`--range`, `--at`, `--shot`, `--clip`, `--asset`, `--track`, and density commands.
The former frozen structural `--from-view`/`--focus` route is retired; the
historical architecture note is not an executable contract.
