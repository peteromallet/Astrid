# Code-driven timeline editing

`open_composition` is a read-only inspection projection. Editing uses a
separate detached bundle opened from an exact parent/shot/internal-timeline
revision closure; that bundle is then validated, previewed, and published as
one complete candidate through the existing Runtime writer.

For a supplied target and credential file, the complete public SDK route is
below. Save it as `edit_target.py` and pass `target.json`, the supplied token
path, an edit JSON object such as `{"occurrence-id": 1200}` (new `start_ms`
values), and the credential's actor ID (the disposable owner token uses
`owner`). The selected Runtime must have `rendering.render` registered to
produce pixels.

```python
import json
import sys
from pathlib import Path

from astrid.sdk.authoring_bundle import render_authoring_candidate_preview
from astrid.sdk.client import AstridClient
from astrid.sdk.workspace_client import PROTOCOL

target = json.loads(Path(sys.argv[1]).read_text())
edits = json.loads(Path(sys.argv[3]).read_text())
assert edits and all(isinstance(value, int) for value in edits.values())
client = AstridClient.open(
    endpoint=target["endpoint"], credential=Path(sys.argv[2]),
    realm_id=target["realm_id"], actor_id=sys.argv[4],
    client_name="astrid-timeline-editor", client_version="1",
    protocol_version=PROTOCOL,
)
bound = client.open_authoring_target(target)
work = bound.open()  # detached parent/shot/internal closure at target's exact head
placements = {row["occurrence_id"]: row for row in work["placements"]}
assert edits.keys() <= placements.keys()
for occurrence_id, start_ms in edits.items():
    placements[occurrence_id]["start_ms"] = start_ms
assert all(placements[key]["start_ms"] == value for key, value in edits.items())
bound.validate(work)
diff = bound.diff(work)
assert diff["changed"]  # inspect the full diff and assert all requested behavior
frozen = bound.preview(work)  # frozen JSON and digest; no rendered media
render = render_authoring_candidate_preview(
    frozen, client, project=target["project_id"],
    timeline_ref=target["timeline_id"], wait=True,
)
assert render.ok, render.error  # actual composed preview; retain render.run_id
receipt = bound.publish(work, idempotency_key=frozen["candidate_digest"])
new_head = receipt["publication"]["new_head"]
committed_target = {**target, "head_revision_id": new_head}
readback = client.open_authoring_target(committed_target).open()
committed = {row["occurrence_id"]: row for row in readback["placements"]}
assert all(committed[key]["start_ms"] == value for key, value in edits.items())
print({"render_run": render.run_id, "new_head": new_head,
       "candidate_digest": receipt["candidate_digest"]})
```

`bound.open()` returns a plain candidate: `placements` hold parent occurrence
placement fields, while `shots[shot_id]["payload"]` and
`shots[shot_id]["internal_timeline"]` hold the selected shot and its nested
clips. `bound.validate`, `bound.diff`, and `bound.preview` return plain data;
the rendered preview returns an `InvocationResult` with `.ok`, `.error`, and
`.run_id`. A failed render has no pixel proof and stops this example before
publication. The returned publication head is reopened for exact readback.

```python
from astrid.sdk import (
    add_authoring_shot, add_track, place_media, sequence,
    open_authoring_bundle, validate_authoring_candidate,
    preview_authoring_candidate, publish_authoring_candidate,
)

# Inspection only: this does not return an editable candidate.
inspection = client.timelines.open_composition(project_id, timeline_id)

# These three inputs are the exact pinned closure read from Runtime.
work = open_authoring_bundle(
    pinned_parent, shot_revisions=pinned_shots,
    internal_timeline_revisions=pinned_internal_timelines,
)
shot = add_authoring_shot(
    work,
    name="Brightness montage",
    occurrence_id="brightness-montage",
    start_ms=0,
)
track = add_track(shot, kind="visual")
images = sorted(imported_media, key=lambda item: (brightness[item["id"]], item["id"]))
clips = [
    place_media(shot, image["id"], track=track, start=0, end=0.1, fit="cover")
    for image in images
]
sequence(clips, start=0, durations=[0.1] * len(clips))
# The child sequence does not implicitly resize its parent occurrence.
placement = next(row for row in work["placements"]
                 if row["occurrence_id"] == "brightness-montage")
placement["duration_ms"] = round(len(clips) * 0.1 * 1000)

validate_authoring_candidate(work)
frozen = preview_authoring_candidate(work)  # exact candidate artifact; no pixels rendered
receipt = publish_authoring_candidate(work, runtime_writer, idempotency_key=edit_run_id)
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

| Helper | Effect |
| --- | --- |
| `place_media` | Adds one admitted media reference with `at`, source `from`/`to`, and optional `speed`. |
| `move` / `retime` | Changes timeline placement/length while retaining source origin and speed. |
| `sequence` / `align` | Arranges supplied clips without affecting unrelated clips. |
| `retime_with_ripple` | Shifts later visual clips on the same track under an explicit duration policy. |
| `fit_duration` | Sets or extends the container duration to cover its clips. |
| `quantize_interval` | Reports exact requested and frame-applied half-open boundaries. |
| `duplicate` / `replace_media` / `remove` | Copies identity, changes selected media, or removes an authored object. |

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
