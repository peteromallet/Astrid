# Timeline cookbook

Read this reference when authoring or validating a timeline document. The
runtime owns the saved document; these examples describe the renderable JSON
boundary rather than a local storage format.

## Minimal renderable config

Use explicit tracks, explicit clip types, and an output contract:

```json
{"tracks":[{"id":"cards","kind":"visual","label":"Cards"}],"clips":[{"id":"title","at":0,"track":"cards","clipType":"text","hold":2,"text":{"content":"HELLO ASTRID","fontSize":64,"color":"#ffffff","align":"center"}}],"output":{"resolution":"640x360","fps":30,"file":"title.mp4"}}
```

Text-shaped data without `clipType: "text"` is ambiguous and is rejected
before renderer admission. A reusable visual element is a clip whose
`clipType` is its registered element ID and whose arguments are in `params`.
The clip-level `effects` field is for fade timing (`fade_in`/`fade_out`); do
not use it as an unregistered effects namespace.

## Layers and canvas

Visual tracks render in reversed array order: put overlay tracks before the
source track to draw them on top. Use a track per editing concern (for example
brand, captions, effects, b-roll, source) and descriptive clip ids. Read the
[small timeline example](../../../../../examples/hype.timeline.json) for structure.

`output.resolution` and `output.fps` are legacy hints, not the authoritative
canvas. Set `theme_overrides.visual.canvas` when changing the canvas, and match
an explicit render profile to that canvas. The default is 1920x1080 at 30 fps.

## Registry and authority

The `registry` supplied to `create`/`save` is the complete asset registry for
that timeline version. Media references must be runtime-owned object IDs with
verified content digests. The host materializes verified bytes for a render;
durable timeline state must not contain source paths, URLs, or renderer-local
CAS locators. Keep authored storyboard inputs separate from runtime materializations when
using a storyboard compiler.

## RenderProfile v1

`timelines render --profile` accepts one flat JSON object; do not nest `video`
and `audio` mappings. A complete Remotion MP4 profile is:

```json
{"width":1920,"height":1080,"fps_rational":[30,1],"time_base":[1,90000],"container":"mp4","video_codec":"h264","video_profile":null,"video_level":null,"pixel_format":"yuv420p","audio_codec":"aac","audio_sample_rate":48000,"audio_channel_layout":"stereo","duration_tolerance":1}
```

Required fields are `width`, `height`, `fps_rational`, `time_base`, `container`,
`video_codec`, `video_profile`, `video_level`, `pixel_format`, and
`duration_tolerance`. The audio fields are an all-or-none trio. An omitted
profile resolves from the authoritative theme canvas (currently 1920x1080 at
30 fps); an explicit profile must match that canvas. Use current
`timelines render` help as the final authority when profiles evolve.

The default H.264/AAC output needs an `.mp4` filename. Alpha-stamped timelines
may use `.mov` for their declared ProRes 4444/PCM contract. Do not infer a
different extension or codec from a backend alias.

## Visual evidence

`timelines visualize` accepts `png`, `svg`, `md`, or `all` formats and
`time-scaled`, `linear`, or `both` layouts. Start with `--filmstrip off` when
there is no verified rendered-video source. The returned manifest and pack root
are navigation artifacts for the selected frozen runtime state, not editable
timeline input.

For a successful managed render, `--view filmstrip` opens the unified
inspector: composited frame cards plus expandable visual/audio lanes on one
canonical integer-frame ruler. It uses the render's frozen timeline snapshot,
so empty declared tracks remain visible and current edits cannot annotate an
older render. Audio clips are placement intervals; the inspector does not infer
waveforms or silence. Frame and clip selections share a render-scoped target,
and a clip with no captured frame reports that state instead of selecting an
unrelated card. `--view structure` remains the structural evidence view and its
legacy `--from-view`/`--focus` object references remain distinct from the
filmstrip inspector's frame/clip/track targets.
