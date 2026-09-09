# Timeline Visualize

`rendering.timeline_visualize` freezes one or more managed timeline generations
and produces a deterministic evidence pack for agent inspection. Default,
slug, UUID, ULID, and `all` selectors resolve only the canonical runtime
timeline; the current row is the snapshot projection and the immutable stream
head/version/hash pins provenance.
Leaf evidence manifests make this boundary explicit with
`inputs.source_mode`: `kernel` for current canonical selection and `frozen`
for navigation from an existing view. `resolved_project` and
`resolved_timelines` carry the exact selected identities.

Use the canonical [Astrid timeline skill](../../skill/SKILL.md) for the
end-to-end workflow and its [timeline cookbook](../../skill/references/timeline-cookbook.md)
for renderable document examples; this stage is the executor contract for the
evidence-producing visualization path.

ULID spelling has one deliberate compatibility seam. Public v10 timeline
`create`, `list`, and `show` DTOs use the kernel's canonical lowercase
Crockford spelling. Frozen timeline-visualize v1 identity and snapshot fields
remain uppercase because their schema and immutable evidence packs require it.
New manifests therefore also include additive
`inputs.canonical_timeline_identities`, whose UUID/slug are unchanged and whose
ULID is lowercase for direct comparison with public kernel DTOs. Do not rewrite
`resolved_timelines` or `snapshots` in an existing pack; compare the additive
identity when present, or compare legacy ULIDs case-insensitively.
It is a first-class project executor, but it deliberately declares
`requires_timeline: false`: one run may cover several timelines and is never
bound to, or recorded in, a timeline `manifest.json`.

## Rendered filmstrip view

Use `--view filmstrip` for continuity review. The existing diagram remains
`--view structure`, which is the compatibility default. Filmstrip inputs are
`sample` (`interval`, `clips`, `cuts`, `shots`), `every` (seconds, default 0.5)
or `every_frames` (positive integer, mutually exclusive with `every`),
`render_run` (exact successful run id or `latest`), `columns` (default 5),
`page_size` (default 50), and the opt-in `include_media` flag. Existing range,
timestamp/context, clip, asset, and shot selectors restrict frame selection.

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

The frame index records integer frames, rational times, active clips, authored
script segments, sample reasons, render provenance, and commands pinned to
the exact render run. When audio is present it also records a digest-scoped
analysis identity, bounded channel-preserving waveform levels, measured
low-amplitude quiet gaps, and (when explicitly admitted in the frozen input)
projected speech phrases. Intervals retain neighboring visual cut frames;
`clips` means picture clips, `cuts` means cut boundaries, and `shots` means
authored story beat midpoints. There is no inferred scene detection.
Sampling is bounded at 2,000 cards and fails with guidance to narrow the
range or increase the interval.

Outputs include a self-contained offline HTML viewer, chronological paginated
PNG and SVG contact sheets, Markdown, and JSON frame cards. Cards show time,
frame, human shot name, and wrapped script text. The filmstrip view is the
unified inspector: it adds expandable declared visual/audio track lanes on the
same time ruler and uses the frozen snapshot's integer clip intervals. Empty
tracks remain visible; declared audio lanes are placement intervals, while
rendered waveform rows appear only when the admitted render has an audio stream.
A lane row means timing overlap at the selected time; it does not
assert that the clip contributes visible or audible output when tracks are
muted, occluded, transparent, or otherwise composited away. Preserve those
frozen track flags in the lane metadata. Frame and clip selection share one
render-scoped target. A clip with no captured frame reports that fact and
exposes its exact focus command instead of choosing an unrelated card. Clip
identities remain in the frame index and expanded inspection. The viewer
supports dialogue search, shot and time filters, density reduction, and
enlarged frames with copyable times, stable targets, and pinned focus commands.
The dense captured-frame grid is a sample of the selected render; it is not a
second time ruler and does not claim unsampled frames exist. It cannot
produce finer sampling from already captured frames; rerun the command for
that. Script captions are segment-level, not word-aligned. “No script” is
separate from any claim about acoustic silence. Filmstrip navigation uses
its frame actions; legacy `--from-view` object navigation belongs to the
structural view. Missing or uncertain speech timing is unavailable rather than
approximated, opening the viewer never invokes a provider, and `--include-media`
adds only a relative digest-verified video; the rendered mix is never presented
as an isolated stem.

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

The rendered view writes `filmstrip-view/` and publishes `filmstrip-bundle.zip`,
a standalone HTML file, and its result manifest as managed objects. The SDK
verifies and extracts the bundle into a disposable local delivery directory,
returning `html`, `pages`, `frame_index`, and `manifest_path`, plus verified
`audio_analysis` and `media` paths when those members are present. The runtime
objects remain the durable record and the result manifest covers every member.

The structural view writes `agent-view/manifest.json` plus the mandatory machine bundle:

- `ground-truth.json`, `view-map.json`, and `action-index.json`
- `asset-index.json`, `transcript-index.json`, and `diagnostics.json`
- `reading-guide.md` and optional factual `structure.md`
- numbered `PG*.png`, optional matching `PG*.svg`, sampled `filmstrip/` media,
  and `pack-hashes.json`

For `--all`, `agent-view/manifest.json` is a project index and each selected
timeline has a deterministic `TLNN/` child pack. Run ULIDs, run paths, and wall
clock time are excluded from pack content identity.

## Inputs and navigation

Cold selectors mirror the timeline-navigation façade of the executor: optional
timeline reference (slug, UUID, or ULID), `--all`, `--shot`, `--range`, `--at`,
`--clip`, `--asset`, `--context`, `--neighbors`, `--layout`, repeatable
`--format`, `--filmstrip`, `--rendered-video`, and `--include-media`.
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
        "layout": "both",
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
# Omit --timeline-slug for the project default; use --all for every active row.
```

`--format` is repeatable and comma-separated (`png`, `svg`, `md`, or `all`),
with `all` exclusive of other formats. Invalid ownership, selectors, and
combinations are returned as typed validation errors before a run/task is
admitted.

Use `source_mode`, `resolved_project`, `resolved_timelines`, and
`canonical_timeline_identities` for provenance and cross-surface comparison.

Do not pass `out` together with `project`: the project-scoped runner supplies
the private staging output and publishes the evidence pack under the managed
run.

Snapshot-safe `--from-view`/`--focus` navigation accepts the durable managed
manifest path returned by a successful visualization (Astrid rehydrates and
hash-verifies its kernel-owned companion outputs). This is the structural
frozen-object grammar; filmstrip inspector targets are render-scoped
frame/clip/track references and are not silently treated as structural refs.
It follows
`docs/architecture/timeline-visualization-agent-navigation.md`. That document
is the canonical agent navigation contract once R18 lands; the evidence pack's
`action-index.json` is the executable source of navigation actions.
