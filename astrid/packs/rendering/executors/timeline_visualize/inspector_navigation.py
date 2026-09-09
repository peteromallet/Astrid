"""Shared, render-scoped navigation for rendered frames and frozen track lanes.

Targets belong only to this inspector schema, never legacy --from-view refs.
Commands reuse public selectors while pinning the exact source render.
"""
from __future__ import annotations

import hashlib
import json
import shlex
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any
from urllib.parse import quote

from astrid.core.timeline.duration import clip_end_frame, clip_start_frame


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


def _time_value(value: object) -> Fraction:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return Fraction(int(value[0]), int(value[1]))
    return Fraction(str(value))


def _time_command(snapshot: Mapping, start: Fraction, end: Fraction) -> str:
    return shlex.join(_base(snapshot) + [
        '--range', f'{float(start)!r}..{float(end)!r}',
    ])


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
            'active_clip_targets': [], 'active_audio_targets': [], 'actions': {'focus_command': _frame_command(snapshot, frame)}}
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

    # Audio is an additive lane.  Its facts are supplied by the render-bound
    # analyzer/projection; navigation only mints stable targets and pinned
    # range actions.  Never infer a waveform or speech from old card scripts.
    raw_audio = snapshot.get('audio')
    audio = dict(raw_audio) if isinstance(raw_audio, Mapping) else {
        'status': 'not_analyzed',
        'speech': {'status': 'no_transcript', 'phrases': []},
        'waveform': {'levels': []},
        'quiet_gaps': [],
        'coverage': {'state': 'not_analyzed'},
    }
    analysis_identity = str(audio.get('analysis_identity') or 'no-analysis')
    speech = audio.get('speech') if isinstance(audio.get('speech'), Mapping) else {}
    annotation_identity = str(speech.get('annotation_identity') or audio.get('annotation_identity') or 'no-annotation')
    audio_targets = {'waveform': [], 'gaps': [], 'phrases': []}

    def add_audio_target(kind: str, item: Mapping[str, Any], identity: str, start: Fraction, end: Fraction, label: str) -> None:
        if end <= start:
            return
        item_identity = item.get('id')
        if not item_identity:
            item_identity = ':'.join(str(item.get(key)) for key in (
                'level_id', 'index', 'start_sample', 'end_sample'
            ))
        target = _target(scope, kind, f'{identity}:{kind}:{item_identity}')
        record = {
            'target': target, 'id': str(item.get('id') or identity), 'kind': kind,
            'label': label, 'start': [start.numerator, start.denominator],
            'end': [end.numerator, end.denominator], 'start_seconds': float(start),
            'end_seconds': float(end), 'duration_seconds': float(end - start),
            'analysis_identity': analysis_identity, 'annotation_identity': annotation_identity,
            'actions': {
                'focus_command': _time_command(snapshot, start, end),
                'seek': {'start': [start.numerator, start.denominator], 'end': [end.numerator, end.denominator]},
            },
        }
        if kind == 'phrase':
            for key in ('canonical_text', 'recognized_text', 'uncertainty', 'timing_method', 'coverage', 'correction_version', 'mapping_state', 'status'):
                if key in item:
                    record[key] = item[key]
        if kind == 'gap':
            record.update({'measurement': item.get('measurement', 'low_amplitude'),
                           'threshold': item.get('threshold'), 'aggregation': item.get('aggregation')})
        if kind == 'waveform':
            record['level_id'] = item.get('level_id')
            record['sample_bounds'] = [item.get('start_sample'), item.get('end_sample')]
        targets[target] = record
        audio_targets[{'waveform': 'waveform', 'gap': 'gaps', 'phrase': 'phrases'}[kind]].append(record)
        for frame in frame_records:
            frame_start = Fraction(frame['frame'], 1) / Fraction(*snapshot['fps_rational'])
            frame_end = Fraction(frame['frame'] + 1, 1) / Fraction(*snapshot['fps_rational'])
            if frame_start < end and frame_end > start:
                frame['active_audio_targets'].append(target)

    gaps = audio.get('quiet_gaps') if isinstance(audio.get('quiet_gaps'), list) else []
    for index, gap in enumerate(gaps):
        if not isinstance(gap, Mapping):
            continue
        try:
            start, end = _time_value(gap.get('start')), _time_value(gap.get('end'))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        add_audio_target('gap', gap, analysis_identity, start, end,
                         f'Quiet gap · {float(end - start):.3f}s')

    phrases = speech.get('phrases') if isinstance(speech.get('phrases'), list) else audio.get('phrases', [])
    for index, phrase in enumerate(phrases):
        if not isinstance(phrase, Mapping):
            continue
        interval = phrase.get('render_interval') if isinstance(phrase.get('render_interval'), Mapping) else phrase
        if not isinstance(interval, Mapping) or interval.get('start') is None or interval.get('end') is None:
            continue
        try:
            start, end = _time_value(interval['start']), _time_value(interval['end'])
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        text = str(phrase.get('canonical_text') or phrase.get('text') or 'Unavailable phrase')
        add_audio_target('phrase', phrase, annotation_identity, start, end, text)

    waveform = audio.get('waveform') if isinstance(audio.get('waveform'), Mapping) else {}
    origin = _time_value((audio.get('presentation_origin') or {}).get('seconds', [0, 1])) if isinstance(audio.get('presentation_origin'), Mapping) else Fraction(0)
    sample_rate = int((audio.get('stream') or {}).get('sample_rate') or 0) if isinstance(audio.get('stream'), Mapping) else 0
    for level in waveform.get('levels', []) if isinstance(waveform.get('levels'), list) else []:
        if not isinstance(level, Mapping) or not isinstance(level.get('bins'), list) or sample_rate <= 0:
            continue
        level_id = str(level.get('id') or level.get('target_bins') or 'level')
        for item in level['bins']:
            if not isinstance(item, Mapping):
                continue
            start_sample, end_sample = int(item.get('start_sample', 0)), int(item.get('end_sample', 0))
            start, end = origin + Fraction(start_sample, sample_rate), origin + Fraction(end_sample, sample_rate)
            enriched = dict(item, level_id=level_id)
            add_audio_target('waveform', enriched, analysis_identity, start, end, f'Waveform {level_id} bin {item.get("index", 0)}')

    audio['speech'] = dict(speech or {'status': 'no_transcript', 'phrases': []})
    audio['waveform_targets'] = audio_targets['waveform']
    audio['gap_targets'] = audio_targets['gaps']
    audio['phrase_targets'] = audio_targets['phrases']
    full_range = build_range_target(snapshot, 0, total)
    targets[full_range['target']] = full_range
    return {'schema': 'astrid.inspector-navigation.v1', 'scope': scope, 'targets': targets,
        'tracks': tracks, 'clips': clips, 'shots': shots, 'frames': frame_records,
        'audio': audio,
        'waveforms': audio_targets['waveform'], 'gaps': audio_targets['gaps'], 'phrases': audio_targets['phrases'],
        'ranges': [full_range], 'legacy_from_view_compatible': False}
