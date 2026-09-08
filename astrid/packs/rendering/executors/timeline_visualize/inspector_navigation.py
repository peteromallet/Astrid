"""Shared, render-scoped navigation for rendered frames and frozen track lanes.

Targets belong only to this inspector schema, never legacy --from-view refs.
Commands reuse public selectors while pinning the exact source render.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from fractions import Fraction
import hashlib
import json
import shlex
from urllib.parse import quote

from astrid.core.timeline.duration import clip_start_frame, clip_end_frame


def inspector_scope(snapshot: Mapping) -> dict:
    keys = ('project_slug', 'timeline_id', 'render_run_id', 'video_digest')
    scope = {key: snapshot[key] for key in keys}
    if not all(isinstance(value, str) and value for value in scope.values()):
        raise ValueError('Inspector requires an immutable render identity.')
    scope['scope_id'] = hashlib.sha256(json.dumps(scope, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:20]
    scope['fps_rational'] = list(snapshot['fps_rational'])
    scope['duration_frames'] = snapshot['duration_frames']
    return scope


def _target(scope: Mapping, kind: str, identity: str | int) -> str:
    return f"ins:{scope['scope_id']}:{kind}:{quote(str(identity), safe='')}"


def target_for_frame(snapshot: Mapping, frame: int) -> str:
    if type(frame) is not int or not 0 <= frame < snapshot['duration_frames']:
        raise ValueError('Frame target is outside the pinned render.')
    return _target(inspector_scope(snapshot), 'frame', frame)


def _base(snapshot: Mapping) -> list[str]:
    return ['python3', '-m', 'astrid', 'timelines', 'visualize', '--project', snapshot['project_slug'],
        '--timeline-slug', snapshot['timeline_id'], '--view', 'filmstrip', '--render-run', snapshot['render_run_id']]


def _seconds(snapshot: Mapping, frame: int) -> str:
    return repr(float(Fraction(frame, 1) / Fraction(*snapshot['fps_rational'])))


def _frame_command(snapshot: Mapping, frame: int, *, clip_id: str | None = None) -> str:
    args = _base(snapshot) + ['--at', _seconds(snapshot, frame), '--context', '1', '--every-frames', '1']
    if clip_id is not None:
        args += ['--clip', clip_id]
    return shlex.join(args)


def build_range_target(snapshot: Mapping, start_frame: int, end_frame: int) -> dict:
    if (type(start_frame) is not int or type(end_frame) is not int
            or not 0 <= start_frame < end_frame <= snapshot['duration_frames']):
        raise ValueError('Range target must be a non-empty integer frame interval in the render.')
    scope = inspector_scope(snapshot)
    return {'target': _target(scope, 'range', f'{start_frame}-{end_frame}'), 'id': f'{start_frame}-{end_frame}',
        'kind': 'range', 'label': f'Frames {start_frame}–{end_frame - 1}',
        'start_frame': start_frame, 'end_frame': end_frame,
        'actions': {'focus_command': shlex.join(_base(snapshot) + ['--range', f'{_seconds(snapshot, start_frame)}..{_seconds(snapshot, end_frame)}'])}}


def build_inspector_navigation(snapshot: Mapping, cards: Sequence[Mapping]) -> dict:
    """Build one target graph for the grid, lanes, details and copy actions.

    Unsampled clips retain frame_target=None. Repeated clips/shot placements
    use occurrence identities; all bounds are half-open canonical frames.
    """
    scope = inspector_scope(snapshot)
    fps = float(Fraction(*snapshot['fps_rational']))
    total = snapshot['duration_frames']
    if fps <= 0 or type(total) is not int or total < 1:
        raise ValueError('Inspector requires a positive frame rate and frame extent.')
    targets: dict[str, dict] = {}
    frame_records = []
    captured: dict[int, dict] = {}
    for card in cards:
        frame = card['frame']
        target = target_for_frame(snapshot, frame)
        if frame in captured:
            raise ValueError('Duplicate captured frame in inspector index.')
        record = {'target': target, 'id': card['id'], 'card_id': card['id'], 'kind': 'frame',
            'label': f'Frame {frame}', 'frame': frame, 'start_frame': frame, 'end_frame': frame + 1,
            'active_clip_targets': [], 'actions': {'focus_command': _frame_command(snapshot, frame)}}
        targets[target] = record; frame_records.append(record); captured[frame] = record
    frame_records.sort(key=lambda r: r['frame'])

    def first_captured(start, end):
        return next((r['target'] for r in frame_records if start <= r['frame'] < end), None)

    tracks = []
    track_by_id = {}
    for raw in snapshot.get('tracks', []):
        track_id = str(raw['id'])
        if track_id in track_by_id:
            raise ValueError('Duplicate frozen track identity.')
        target = _target(scope, 'track', track_id)
        record = {'target': target, 'id': track_id, 'track_id': track_id, 'kind': 'track',
            'track_kind': raw.get('kind', 'unknown'), 'label': raw.get('label') or raw.get('name') or track_id,
            'metadata': dict(raw),
            'start_frame': 0, 'end_frame': total, 'clip_targets': [],
            'actions': {'focus_command': shlex.join(_base(snapshot)),
                'note': 'Shows the composited render; does not isolate this track.'}}
        tracks.append(record); track_by_id[track_id] = record; targets[target] = record
    clips = []
    seen_clip_keys = set()
    for index, raw in enumerate(snapshot.get('clips', [])):
        clip_id = str(raw['id']); track_id = str(raw.get('track', ''))
        # Stable within the immutable snapshot even for repeated authored ids.
        identity = json.dumps([raw.get('occurrence_id'), track_id, clip_id, index], separators=(',', ':'))
        if identity in seen_clip_keys:
            raise ValueError('Duplicate clip occurrence identity.')
        seen_clip_keys.add(identity)
        start = raw.get('start_frame'); end = raw.get('end_frame')
        if start is None or end is None:
            timed = dict(raw)
            if 'hold' not in timed and 'to' not in timed and 'duration' in timed:
                timed['hold'] = timed['duration']
            start, end = clip_start_frame(timed, fps), clip_end_frame(timed, fps)
        start, end = max(0, start), min(total, end)
        if start >= end:
            continue
        target = _target(scope, 'clip', identity)
        record = {'target': target, 'id': clip_id, 'clip_id': clip_id, 'track_id': track_id,
            'kind': 'clip', 'clip_kind': raw.get('kind', 'unknown'),
            'label': raw.get('label') or raw.get('name') or clip_id,
            'start_frame': start, 'end_frame': end, 'frame_target': first_captured(start, end),
            'actions': {'focus_command': _frame_command(snapshot, start, clip_id=clip_id)},
            'source': {key: raw[key] for key in ('asset', 'from', 'to', 'speed') if key in raw}}
        for key in ('shot_id', 'shot_name', 'occurrence_id'):
            if key in raw:
                record[key] = raw[key]
        clips.append(record); targets[target] = record
        if track_id in track_by_id:
            track_by_id[track_id]['clip_targets'].append(target)
        for frame in frame_records:
            if start <= frame['frame'] < end:
                frame['active_clip_targets'].append(target)
    shots = []
    for index, raw in enumerate(snapshot.get('occurrences', [])):
        identity = raw.get('occurrence_id') or f"{index}:{raw['shot_id']}"
        start, end = raw['start_frame'], raw['end_frame']
        target = _target(scope, 'shot', identity)
        command = _base(snapshot) + ['--shot', raw['shot_id'], '--range',
            f'{_seconds(snapshot, start)}..{_seconds(snapshot, end)}']
        record = {'target': target, 'id': identity, 'occurrence_id': identity,
            'kind': 'shot', 'shot_id': raw['shot_id'], 'label': raw.get('shot_name') or raw['shot_id'],
            'start_frame': start, 'end_frame': end, 'frame_target': first_captured(start, end),
            'actions': {'focus_command': shlex.join(command)}}
        shots.append(record); targets[target] = record
    full_range = build_range_target(snapshot, 0, total)
    targets[full_range['target']] = full_range
    return {'schema': 'astrid.inspector-navigation.v1', 'scope': scope, 'targets': targets,
        'tracks': tracks, 'clips': clips, 'shots': shots, 'frames': frame_records,
        'ranges': [full_range], 'legacy_from_view_compatible': False}
