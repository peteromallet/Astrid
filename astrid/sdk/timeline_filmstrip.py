"""Freeze a managed render and its exact script identities for visual review."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
import hashlib
from typing import Any

from .exceptions import CapabilityValidationError
from .pagination import paged_rows
from .project_render import _identifier, _state, _render_capability, _SUCCESS_STATES


def _fail(message: str) -> None:
    raise CapabilityValidationError(message)


def _envelope(task: Mapping) -> Mapping:
    value = task.get('spec', {})
    for _ in range(4):
        if isinstance(value, Mapping) and 'inputs' in value:
            return value
        value = value.get('spec', {}) if isinstance(value, Mapping) else {}
    _fail('Render has no immutable input snapshot; rerender the selected timeline.')


def _digest(value: Any) -> str:
    raw = str(value or '').removeprefix('sha256:')
    if len(raw) != 64 or any(c not in '0123456789abcdef' for c in raw):
        _fail('Render contains an invalid managed object digest.')
    return 'sha256:' + raw


def _read_text(client: Any, binding: Mapping) -> str:
    object_id = _digest(binding.get('media_id'))
    if object_id != binding.get('content_hash'):
        _fail('Frozen script binding identity does not match its content hash.')
    response = client.get_object(object_id)
    raw = response.get('data') if isinstance(response, Mapping) else response.data
    if not isinstance(raw, bytes) or 'sha256:' + hashlib.sha256(raw).hexdigest() != object_id or len(raw) != binding.get('byte_size'):
        _fail('Frozen script bytes do not match the render binding digest and size.')
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        _fail('Frozen script is not UTF-8 text.')


def _duration(clip: Mapping) -> float:
    from astrid.core.timeline.duration import clip_timeline_duration
    return clip_timeline_duration(clip)


def build_filmstrip_snapshot(envelope: Mapping, *, client: Any, project: str, run_id: str, video_digest: str) -> dict:
    """Pure snapshot mapping except verified reads of pinned immutable text objects."""
    inputs = envelope.get('inputs', {})
    authority = envelope.get('authority_context') or inputs.get('timeline_authority', {})
    timeline = inputs.get('timeline_snapshot', {})
    config = timeline.get('config', {})
    if not isinstance(config.get('clips'), list) or not authority.get('timeline_id'):
        _fail('Render lacks a frozen canonical timeline; rerender it before visual review.')
    canvas = config.get('theme_overrides', {}).get('visual', {}).get('canvas', {})
    profile = inputs.get('profile') or {}
    if not isinstance(profile, Mapping):
        _fail('Render profile is not a frozen profile mapping; rerender with explicit frame rate.')
    fps_value = profile.get('fps_rational') or canvas.get('fps')
    if isinstance(fps_value, (list, tuple)) and len(fps_value) == 2:
        fps = Fraction(*fps_value)
    elif fps_value:
        fps = Fraction(str(fps_value))
    else:
        _fail('Render snapshot does not record its frame rate; rerender with an explicit canvas.')
    if fps <= 0:
        _fail('Render frame rate is invalid.')
    tracks = {t['id']: t.get('kind', '') for t in config.get('tracks', [])}
    from astrid.core.timeline.duration import clip_start_frame, clip_end_frame, timeline_duration_frames
    clips = []
    for raw in config['clips']:
        clip = deepcopy(dict(raw))
        clip.update(kind=tracks.get(raw.get('track'), ''), duration=_duration(raw),
            start_frame=clip_start_frame(raw, float(fps)), end_frame=clip_end_frame(raw, float(fps)))
        clips.append(clip)
    # These occurrences were admitted by the renderer from canonical registered
    # shots. Never infer a shot from a filename, ordinal, or current document.
    occurrences = inputs.get('review_context', {}).get('shots', [])
    frozen_shots = {s['shot_id']: s for s in authority.get('expansion', {}).get('shots', [])}
    scripts = []
    shot_occurrences = []
    for occurrence_index, occurrence in enumerate(occurrences):
        shot_id = occurrence.get('shot_id')
        shot = frozen_shots.get(shot_id)
        if not shot:
            continue
        occurrence_id = f"occurrence-{occurrence_index:04d}-{shot_id}"
        start_frame = clip_start_frame(occurrence, float(fps))
        end_frame = clip_end_frame(occurrence, float(fps))
        start = start_frame / float(fps); end = end_frame / float(fps)
        shot_occurrences.append({'occurrence_id': occurrence_id, 'shot_id': shot_id,
            'shot_name': shot['name'], 'start': start, 'end': end,
            'start_frame': start_frame, 'end_frame': end_frame})
        active = [c for c in clips if c['start_frame'] < end_frame and c['end_frame'] > start_frame]
        for clip in active:
            if clip['start_frame'] >= start_frame and clip['end_frame'] <= end_frame:
                clip.setdefault('occurrence_ids', []).append(occurrence_id)
                if len(clip['occurrence_ids']) == 1:
                    clip.update(shot_id=shot_id, shot_name=shot['name'], occurrence_id=occurrence_id)
                else:
                    # Overlapping placements without explicit child identity are
                    # ambiguous. Retain candidates, never overwrite ownership.
                    for key in ('shot_id', 'shot_name', 'occurrence_id'):
                        clip.pop(key, None)
        for binding in shot.get('text_bindings', []):
            text = _read_text(client, binding)
            # A canonical shot script is not an aligned audio transcript. Even
            # a single overlapping audio clip could be music: don't invent timing.
            scripts.append({'start': start, 'end': end, 'text': text,
                'shot_id': shot_id, 'shot_name': shot['name'], 'kind': binding['kind'],
                'occurrence_id': occurrence_id, 'start_frame': start_frame, 'end_frame': end_frame,
                'binding_id': binding['binding_id'], 'head': binding['head'],
                'media_id': binding['media_id'], 'timing_basis': 'shot_script',
                'label': 'Shot script (not word-aligned)'})
    return {'project_slug': project, 'timeline_id': authority['timeline_id'],
        'timeline_name': authority.get('timeline_slug', authority['timeline_id']),
        'render_run_id': run_id, 'video_digest': video_digest,
        'fps_rational': [fps.numerator, fps.denominator],
        'duration_frames': timeline_duration_frames(config, float(fps)),
        'clips': clips, 'scripts': scripts, 'occurrences': shot_occurrences,
        'tracks': deepcopy(config.get('tracks', [])),
        'metadata': {'canonical_timeline': deepcopy(authority),
            'script_timing': 'shot_script',
            'script_mapping_available': bool(occurrences and frozen_shots),
            'script_mapping_note': 'Frozen shot script; no word alignment.' if occurrences and frozen_shots else 'Render did not pin shot placements and scripts; rerender for script labels.'}}


def prepare_filmstrip(inputs: Mapping, *, project: str, client: Any = None) -> dict:
    """Select a successful managed render; never admit a caller-provided file."""
    if client is None:
        from .client import AstridClient
        with AstridClient.open_from_launcher() as connected:
            return prepare_filmstrip(inputs, project=project, client=connected)
    client = getattr(getattr(client, '_remote', None), '_transport', client)
    if inputs.get('rendered_video'):
        _fail('Filmstrip review accepts a managed --render-run, not --rendered-video.')
    project_row = client.get_project(project)
    project_id = _identifier(project_row, 'project_id', 'id')
    selector = inputs.get('timeline_slug') or inputs.get('timeline_ref')
    exact = inputs.get('render_run')
    if exact == 'latest':
        exact = None
    canonical_project = str(project_row.get('slug') or project)
    timeline_row = None
    if selector or not exact:
        selector = selector or project_row.get('metadata', {}).get('default_timeline_id')
        rows = paged_rows(client.list_timelines, project_id, limit=50) or []
        timeline_row = next((r for r in rows if selector in {r.get('timeline_id'), r.get('id'), r.get('slug')}), None)
        if timeline_row is None:
            _fail('Select a canonical timeline before filmstrip review.')
    if exact:
        candidates = [client.get_run(exact)]
    else:
        candidates = paged_rows(client.list_project_runs, project_id, limit=50) or []
        candidates = sorted(candidates, key=lambda r: (str(r.get('created_at', '')), _identifier(r, 'id', 'run_id')), reverse=True)
    selected = None
    for candidate in candidates:
        run = client.get_run(_identifier(candidate, 'id', 'run_id'))
        if _identifier(run, 'project_id', 'project') != project_id or _render_capability(run) != 'rendering.render' or _state(run) not in _SUCCESS_STATES:
            continue
        tasks = [client.get_task(t) for t in run.get('task_ids', [])]
        tasks = [t for t in tasks if _render_capability(t) == 'rendering.render' and _state(t) in _SUCCESS_STATES]
        if len(tasks) != 1:
            continue
        task = tasks[0]; envelope = _envelope(task)
        authority = envelope.get('authority_context', {})
        if timeline_row and authority.get('timeline_id') != _identifier(timeline_row, 'timeline_id', 'id'):
            continue
        selected = (run, task, envelope, authority)
        break
    if selected is None:
        _fail(f'No successful render for this selection. Run: python3 -m astrid timelines render {selector or "<timeline>"} --project {project}')
    run, task, envelope, authority = selected
    if not exact:
        pins = [{'timeline_id': authority['timeline_id'], 'config_version': authority.get('config_version')}]
        pins += authority.get('expansion', {}).get('children', [])
        for pin in pins:
            current = client.get_timeline(pin['timeline_id'])
            if current.get('config_version') != pin.get('config_version'):
                _fail(f'Latest render is stale. Run: python3 -m astrid timelines render {selector} --project {project}; or inspect the old render explicitly with --render-run {_identifier(run, "id", "run_id")}.')
        # Script-only edits do not necessarily advance timeline versions.
        for shot in authority.get('expansion', {}).get('shots', []):
            for binding in shot.get('text_bindings', []):
                current = client.get_project_shot_text_binding(project_id, binding['binding_id'])
                if current.get('head') != binding.get('head') or current.get('content_hash') != binding.get('content_hash'):
                    _fail(f'Latest render has stale script text; rerender {selector} in project {project}, or select its --render-run explicitly.')
    outputs = task.get('result', {}).get('outputs', [])
    videos = [o for o in outputs if o.get('name') == 'video']
    if len(videos) != 1:
        _fail('Render must publish exactly one managed video output.')
    digest = _digest(videos[0].get('digest') or videos[0].get('object_id'))
    objects = paged_rows(client.list_project_objects, project_id, limit=50) or []
    if not any(digest in {o.get('object_id'), o.get('digest')} for o in objects):
        _fail('Rendered video is not owned by the selected project.')
    run_id = _identifier(run, 'id', 'run_id')
    snapshot = build_filmstrip_snapshot(envelope, client=client, project=canonical_project, run_id=run_id, video_digest=digest)
    snapshot['metadata']['selection'] = 'explicit_render' if exact else 'latest_current_render'
    return {'mode': 'filmstrip', 'filmstrip_snapshot': snapshot,
        'video_object_id': digest, 'video_digest': digest, 'render_run_id': run_id,
        'project_id': project_id, 'timeline_id': authority['timeline_id']}
