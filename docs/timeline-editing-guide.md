# Code-driven timeline editing

Open one pinned composition bundle, edit the detached candidate with ordinary
Python, validate/preview it, then submit it through the existing atomic commit
boundary. The helpers below mutate the same objects that a script can inspect
directly; they are not a second command language.

```python
from astrid.sdk import (
    add_shot, add_track, place_media, sequence, grid, quantize_interval,
    retime_with_ripple,
)

# `open_composition` is the composition adapter's pinned full-candidate read.
work = open_composition(project_id, timeline_id)  # candidate + base head
images = sorted(import_media(paths), key=lambda asset: (brightness[asset.id], asset.id))
shot = add_shot(work, name="Brightness montage")
track = add_track(shot, kind="video")
clips = [place_media(shot, image, track=track, start=0, end=0.1, fit="cover") for image in images]
sequence(clips, start=0, durations=[0.1] * len(clips))

# A four-panel edit uses the same placement helper and explicit rectangles.
for index, rectangle in enumerate(grid(2, 2)):
    panel = add_track(work, kind="video", name=f"Quadrant {index}")
    # Place selected images at supplied, already source-aligned beat boundaries.

validate_candidate(work)
preview_candidate(work)      # frozen candidate; canonical head unchanged
receipt = commit_candidate(work, idempotency_key=edit_run_id)
```

Important defaults are explicit:

- Clip intervals are half-open `[start, end)` in the containing timeline.
- Use `quantize_interval(start, end, fps, policy=...)` when boundaries are not exactly representable; it reports requested/applied frames and rejects collapsed intervals.
- Absolute placement does not move neighbours. Ripple is never implicit.
- If shifting following visual clips is intended, call `retime_with_ripple` with
  `scope="track"` and an explicit `parent_duration` policy. It never ripples
  audio, voice, music, or another track.
- `duplicate` allocates fresh editable identities and remaps internal references; immutable media can remain shared.
- `replace_media` selects the supplied asset and preserves the existing interval unless instructed otherwise.
- `reorder_layers` changes stacking order; `sequence` changes chronology.

The editing helpers do not select a “latest” asset, download the whole library,
or publish individual operations. Media import/list/open use the existing
runtime media services. Source viewing and composed preview are separate,
read-only actions. Unsupported renderer capabilities and missing assets must be
reported before commit.

## Render an unpublished candidate

`preview_authoring_candidate(work)` freezes the complete candidate, its base
parent head, deterministic candidate digest, and proposed publication. For a
composed video preview, use the connected SDK client:

```python
from astrid.sdk import preview_authoring_candidate, render_authoring_candidate_preview

frozen = preview_authoring_candidate(work)
render = render_authoring_candidate_preview(
    frozen, client, project="my-project", timeline_ref="main", wait=True,
)
```

This invokes the ordinary `rendering.render` managed run. Admission rereads the
base head and any reused immutable child revisions from Runtime, projects the
frozen candidate without publishing it, checks project-owned media, and
records the run receipt. The render authority is labelled `Unpublished
candidate preview` and includes the exact base head, candidate digest,
publication digest, and proposed parent revision ID. Editing `work` after the
preview was frozen cannot alter that run. If the parent head advances before
admission, the preview is rejected as stale.
