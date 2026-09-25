# Offline filmstrip inspection

For render-free current-input inspection, use
`python3 -m astrid timelines visualize <timeline> --project <project> --show inputs --hide output`.
It projects declared placements without decoding rendered pixels or starting a
provider call. A rendered view requires a successful render and its exact
`--render-run <run-id>`; its conclusions are scoped to that frozen run.

Use the materialized bundle's returned inspection command to query evidence without starting the workspace runtime or regenerating frames:

```sh
python3 -m astrid timelines inspect --manifest /path/to/bundle/manifest.json --section summary
python3 -m astrid timelines inspect --manifest /path/to/bundle/manifest.json --section cards --range 30..40
python3 -m astrid timelines inspect --manifest /path/to/bundle/manifest.json --section placements --clip clip-id
python3 -m astrid timelines inspect --manifest /path/to/bundle/manifest.json --section audio --range 30..40
```

Sections are `summary`, `pages`, `cards`, `placements`, `audio`, and `boundaries`. Cards, placements, and boundaries support exact frame/card, shot ID or exact name, occurrence, clip, track, asset, and half-open time ranges. Audio supports time ranges. Unsupported selector combinations return a typed error.

Responses contain at most 10 records by default, 50 with `--limit`, and 8 KiB including the complete JSON envelope. A byte-limited page can contain fewer records. Pass `next_cursor` as `--cursor` with the identical query to continue. Cursors become invalid when the manifest or query changes. Text uses marked excerpts; audio exposes at most 128 bins from one existing waveform level and marks incomplete coverage. No JSONPath, recursive scalar dumps, raw objects, inline images, or archive inputs are supported.

New `astrid.filmstrip.v2` frame indexes are compact receipts: sampled image paths, decoded frames/times, stable IDs, canonical timeline version/hash, and hashed sidecar references. They do not embed the canonical timeline, navigation graph, raw audio arrays, or scripts. Legacy v1 bundles are read without rewriting them. The inspector verifies manifest-declared member hashes and sizes, rejects unsafe paths, and reads only named evidence files.

Placement metadata declares sources and intervals; it does not establish the
appearance of the rendered composition. Boundary records report whether
adjacent frames were actually captured. Missing adjacent evidence requires a
pinned `timelines visualize --render-run RUN --range START..END --every-frames 1`
refinement. Low energy is a measurement, not perceptual silence. Shot scripts
do not establish word-aligned speech.

Python callers can use `inspect_filmstrip(manifest, section='cards', frame=120)` from `astrid.packs.rendering.executors.timeline_visualize.inspection_contract`; it returns the same bounded five-key envelope without a runtime client. SDK visualization results include `outputs.inspection` with a copyable local command.
