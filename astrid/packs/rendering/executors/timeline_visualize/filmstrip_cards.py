"""Deterministic contact sheets sampled from the exact rendered video."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import math
import shlex
import shutil
import subprocess
import textwrap
from collections.abc import Mapping
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from urllib.parse import quote

from astrid.core.timeline.duration import clip_end_frame, clip_start_frame

from .audio_analysis import (
    AudioAnalysisError,
    analyze_audio,
    audio_analysis_identity,
    project_waveform,
)
from .inspection_contract import project_input_window
from .inspector_navigation import build_inspector_navigation


def _q(value):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return Fraction(int(value[0]), int(value[1]))
    result = Fraction(str(value))
    # Runtime JSON floats can carry arithmetic noise at exact frame boundaries.
    # Preserve explicit decimal strings; recover float rationals to nanosecond precision.
    return result.limit_denominator(1_000_000_000) if isinstance(value, float) else result


def _frame_span(clip, fps):
    # Normalized snapshots may expose effective duration rather than source trim.
    timing = dict(clip)
    if clip.get('duration') is not None:
        timing.update(hold=float(clip['duration']), speed=1)
    return clip_start_frame(timing, float(fps)), clip_end_frame(timing, float(fps))


def _speech_caption_records(snapshot, time):
    """Return frozen timed speech phrases covering ``time``.

    Shot scripts are deliberately kept separate from this channel: a
    shot-wide script explains the shot, but it does not establish which words
    are spoken at an individual frame.  Only explicitly projected, half-open
    speech intervals may appear as a frame caption.
    """
    audio = snapshot.get('audio')
    speech = audio.get('speech') if isinstance(audio, dict) else None
    phrases = speech.get('phrases') if isinstance(speech, dict) else None
    if not isinstance(phrases, list):
        return []
    matches = []
    seen = set()
    for phrase in phrases:
        if not isinstance(phrase, dict) or phrase.get('status') not in (None, 'projected'):
            continue
        interval = phrase.get('render_interval') if isinstance(phrase.get('render_interval'), dict) else phrase
        if not isinstance(interval, dict) or interval.get('start') is None or interval.get('end') is None:
            continue
        try:
            start, end = _q(interval['start']), _q(interval['end'])
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if end <= start or not (start <= time < end):
            continue
        identity = (str(phrase.get('id')) if phrase.get('id') else (
            phrase.get('annotation_id'), phrase.get('occurrence_id'),
            tuple(start.as_integer_ratio()), tuple(end.as_integer_ratio()),
        ))
        if identity in seen:
            continue
        seen.add(identity)
        matches.append((start, end, str(identity), dict(phrase)))
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in matches]


def _project_display_scripts(cards):
    """De-duplicate shot-script context for the human-facing card display.

    A script binding can legitimately cover many sampled frames.  Without
    word timing, showing it on every card is noisy and implying a changing
    transcript would be false.  Keep the complete ``scripts`` field intact,
    but surface each occurrence's script once at its first captured frame.
    """
    seen = set()
    for card in cards:
        displayed = []
        for script in card.get('scripts') or []:
            identity = (
                script.get('binding_id'), script.get('occurrence_id'),
                script.get('start'), script.get('end'), script.get('text'),
            )
            if identity in seen:
                continue
            seen.add(identity)
            displayed.append(script)
        card['display_scripts'] = displayed
        if card.get('captions'):
            card['caption_status'] = 'timed caption'
        elif displayed:
            card['caption_status'] = 'shot script context (not word-aligned)'
        elif card.get('scripts'):
            # The script still overlaps this frame, but we have no word/phrase
            # timing that would justify repeating it or claiming it is spoken
            # here.  Keep that distinction explicit in metadata and review UI.
            card['caption_status'] = 'same shot; no new timed text'
        else:
            card['caption_status'] = 'no timed text available'


OVERVIEW_MAX_CARDS = 200


def _attach_input_navigation(index: dict, projection: dict, *, track_meta=None) -> None:
    """Expose the input projection through the viewer's existing lane model."""
    navigation = index.setdefault('navigation', {})
    provenance = index.get('provenance') if isinstance(index.get('provenance'), dict) else {}

    def input_focus_command(*, track_id=None, clip_id=None, start_frame=None, end_frame=None):
        argv = ['python3', '-m', 'astrid', 'timelines', 'visualize']
        if provenance.get('project_slug'):
            argv += ['--project', str(provenance['project_slug'])]
        if provenance.get('timeline_id'):
            argv += ['--timeline-slug', str(provenance['timeline_id'])]
        if provenance.get('render_run_id'):
            argv += ['--render-run', str(provenance['render_run_id'])]
        argv += ['--view', 'filmstrip', '--show', 'inputs', '--hide', 'output', '--detail']
        if track_id:
            argv += ['--track', str(track_id)]
        if clip_id:
            argv += ['--clip', str(clip_id)]
        if start_frame is not None and end_frame is not None:
            fps = Fraction(*(projection['window'].get('fps') or [30, 1]))
            start = float(Fraction(int(start_frame), 1) / fps)
            end = float(Fraction(int(end_frame), 1) / fps)
            argv += ['--range', f'{start!r}..{end!r}']
        return shlex.join(argv)

    track_meta = {str(item.get('id')): item for item in (track_meta or []) if isinstance(item, dict)}
    targets = navigation.setdefault('targets', {})
    for track in projection.get('tracks', []):
        track_id = str(track.get('track_id'))
        input_track_id = f'input:{track_id}'
        meta = track_meta.get(track_id, {})
        track_target = f'input-track-{quote(track_id, safe="")}'
        navigation['tracks'].append({
            'id': input_track_id, 'track_id': input_track_id,
            'track_kind': meta.get('kind', 'other'), 'kind': meta.get('kind', 'other'),
            'label': f"Input · {meta.get('label') or track_id}",
            'target': track_target,
            'actions': {'focus_command': input_focus_command(track_id=track_id)},
        })
        window_start = projection.get('window', {}).get('start_frame', min((int(c.get('window', [0, 0])[0]) for c in track.get('clips', []) if isinstance(c, dict)), default=0))
        window_end = projection.get('window', {}).get('end_frame', max((int(c.get('window', [0, 0])[1]) for c in track.get('clips', []) if isinstance(c, dict)), default=window_start + 1))
        targets[track_target] = {
            'kind': 'track', 'id': input_track_id, 'track_id': input_track_id,
            'label': f"Input · {meta.get('label') or track_id}",
            'start_frame': window_start,
            'end_frame': window_end,
            'actions': {'focus_command': input_focus_command(track_id=track_id)},
        }
        for clip in track.get('clips', []):
            start_frame, end_frame = clip['window']
            # A single admitted shot occurrence can supply picture, voiceover,
            # and other tracks.  Include track and clip identity so selecting
            # one placement never overwrites a sibling target.
            identity = '|'.join((track_id, str(clip['clip_id']), str(clip['occurrence_id'])))
            target = f"input-clip-{quote(identity, safe='')}"
            navigation['clips'].append({
                'id': clip['clip_id'], 'clip_id': clip['clip_id'],
                'occurrence_id': clip['occurrence_id'], 'track_id': input_track_id,
                'asset_key': clip.get('asset_key'),
                'start_frame': start_frame, 'end_frame': end_frame,
                'label': clip['clip_id'], 'clip_kind': meta.get('kind', 'other'),
                'source_preview': clip.get('source_preview'),
                'audio_signifier': clip.get('audio_signifier'),
                'source_time': clip.get('source_time'), 'subrow': clip.get('subrow'),
                'continuation': clip.get('continuation'), 'target': target,
                'actions': {'focus_command': input_focus_command(
                    track_id=track_id, clip_id=clip['clip_id'],
                    start_frame=start_frame, end_frame=end_frame,
                )},
            })
            targets[target] = {
                'kind': 'clip', 'clip_id': clip['clip_id'], 'occurrence_id': clip['occurrence_id'],
                'track_id': input_track_id, 'asset_key': clip.get('asset_key'),
                'start_frame': start_frame, 'end_frame': end_frame,
                'source_time': clip.get('source_time'), 'source_preview': clip.get('source_preview'),
                'audio_signifier': clip.get('audio_signifier'),
                'actions': {'focus_command': input_focus_command(
                    track_id=track_id, clip_id=clip['clip_id'],
                    start_frame=start_frame, end_frame=end_frame,
                )},
            }


def _source_audio_asset_candidates(clip: Mapping, integrity: Mapping) -> list[str]:
    """Return the admitted asset keys that could supply a placement's audio."""
    candidates: list[str] = []
    audio = clip.get("audio_signifier")
    if isinstance(audio, Mapping):
        declared = audio.get("source")
        # A declared source string is an asset key when it is present in the
        # canonical registry.  Labels such as ``embedded source audio`` are
        # intentionally ignored here and fall through to the clip asset.
        if isinstance(declared, str) and declared in integrity:
            candidates.append(declared)
    asset_key = clip.get("asset_key")
    if isinstance(asset_key, str) and asset_key:
        candidates.append(asset_key)
    return list(dict.fromkeys(candidates))


def _source_audio_digest(entry: Mapping) -> str | None:
    """Normalize the digest that the audio analyzer must verify."""
    raw = entry.get("observed_sha256") or entry.get("expected_sha256") or entry.get("sha256")
    if not isinstance(raw, str):
        return None
    value = raw.removeprefix("sha256:")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value.lower()):
        return None
    return "sha256:" + value.lower()


def attach_input_audio_waveforms(
    projection: dict,
    *,
    integrity: Mapping | None,
    out_root: Path,
    settings: Mapping | None = None,
    count: int = 64,
) -> dict:
    """Attach measured, per-source waveforms to an input projection.

    Input placements are projected from a frozen timeline, while source bytes
    arrive through the attempt-local, digest-verified integrity map.  Only
    ``verified_original`` files are opened.  Each source is analyzed once and
    its complete bounded analysis is written to a sidecar; clips receive only
    the small interval projection needed by the static lane renderer.  When a
    source cannot be materialized or has no audio stream, the existing
    placement rail remains available and carries an explicit fallback reason.
    """
    if not isinstance(projection, dict) or not isinstance(integrity, Mapping):
        return projection
    try:
        requested_count = int(count)
    except (TypeError, ValueError):
        return projection
    if requested_count <= 0 or requested_count > 4096:
        return projection
    output_root = Path(out_root)
    analysis_root = output_root / "source-audio-analysis"
    source_records: dict[str, dict] = {}
    analyses: dict[str, tuple[dict, str]] = {}

    for track in projection.get("tracks") or []:
        if not isinstance(track, Mapping):
            continue
        track_id = str(track.get("track_id") or "").lower()
        for clip in track.get("clips") or []:
            if not isinstance(clip, dict):
                continue
            audio = clip.get("audio_signifier")
            preview = clip.get("source_preview") if isinstance(clip.get("source_preview"), Mapping) else {}
            media_kind = str(preview.get("media_type") or "").lower().split("/", 1)[0]
            audio_track = track_id in {"audio", "vo", "voiceover", "music", "sound", "sfx"}
            # A verified video may contain embedded audio even when the authored
            # clip did not declare ``has_audio``.  Analyze those files as well;
            # still images are never sent through ffprobe unnecessarily.
            if not isinstance(audio, Mapping) and not (audio_track or media_kind in {"audio", "video"}):
                continue
            if isinstance(audio, Mapping) and audio.get("present") is False:
                continue
            candidates = _source_audio_asset_candidates(clip, integrity)
            if not candidates:
                continue
            selected_key = None
            entry = None
            digest = None
            source_path = None
            for candidate in candidates:
                candidate_entry = integrity.get(candidate)
                if not isinstance(candidate_entry, Mapping) or candidate_entry.get("state") != "verified_original":
                    continue
                candidate_digest = _source_audio_digest(candidate_entry)
                candidate_path = candidate_entry.get("path")
                if candidate_digest is None or not isinstance(candidate_path, str) or not Path(candidate_path).is_file():
                    continue
                selected_key, entry, digest, source_path = candidate, candidate_entry, candidate_digest, Path(candidate_path)
                break
            if selected_key is None or entry is None or digest is None or source_path is None:
                # Leave the truthful timing rail in place.  The renderer's
                # fallback is visibly distinct and the reason is retained in
                # the machine-facing signifier when one already exists.
                if isinstance(audio, dict):
                    audio.setdefault("analysis_status", "source_unavailable")
                continue

            cached = analyses.get(digest)
            if cached is None:
                try:
                    analysis = analyze_audio(source_path, render_digest=digest, settings=settings)
                except (AudioAnalysisError, OSError, subprocess.SubprocessError) as exc:
                    analysis = {
                        "schema_version": 1,
                        "analysis_version": "astrid.audio-analysis.v1",
                        "analysis_identity": audio_analysis_identity(digest, None, settings, status="analysis_error"),
                        "render_digest": digest,
                        "status": "analysis_error",
                        "error": str(exc),
                        "waveform": {"levels": []},
                        "quiet_gaps": [],
                        "coverage": {"state": "analysis_error"},
                    }
                sidecar_name = f"{digest.removeprefix('sha256:')}.json"
                sidecar_path = analysis_root / sidecar_name
                analysis_root.mkdir(parents=True, exist_ok=True)
                sidecar_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
                cached = (analysis, sidecar_path.relative_to(output_root).as_posix())
                analyses[digest] = cached
            analysis, sidecar_rel = cached
            record = source_records.setdefault(
                digest,
                {
                    "digest": digest,
                    "asset_keys": [],
                    "status": analysis.get("status"),
                    "analysis_identity": analysis.get("analysis_identity"),
                    "path": sidecar_rel,
                },
            )
            if selected_key not in record["asset_keys"]:
                record["asset_keys"].append(selected_key)

            source_window = (audio.get("source_window") if isinstance(audio, Mapping) else None) or clip.get("source_time")
            projected = None
            if isinstance(source_window, (list, tuple)) and len(source_window) == 2:
                projected = project_waveform(
                    analysis, source_window[0], source_window[1], count=requested_count,
                )
            if projected is None:
                if isinstance(audio, dict):
                    audio.update({
                        "analysis_status": analysis.get("status") or "no_waveform",
                        "analysis_identity": analysis.get("analysis_identity"),
                        "source_digest": digest,
                        "source_asset_key": selected_key,
                        "analysis_path": sidecar_rel,
                    })
                continue

            updated = dict(audio) if isinstance(audio, Mapping) else {}
            updated.setdefault("present", True)
            updated.setdefault("source", selected_key)
            updated.setdefault("window", clip.get("window"))
            updated.setdefault("window_seconds", clip.get("window_seconds"))
            updated.setdefault("source_window", source_window)
            updated.setdefault("speed", clip.get("speed"))
            updated.update({
                "basis": "source_audio_analysis",
                "visual_encoding": "amplitude_waveform",
                "analysis_status": analysis.get("status", "ok"),
                "analysis_identity": analysis.get("analysis_identity"),
                "source_digest": digest,
                "source_asset_key": selected_key,
                "analysis_path": sidecar_rel,
                "waveform": {
                    "amplitudes": projected["amplitudes"],
                    "display_amplitudes": _png_waveform_display_amplitudes(projected["amplitudes"]),
                    "source_start": projected["start"],
                    "source_end": projected["end"],
                    "sample_rate": projected["source_sample_rate"],
                },
            })
            clip["audio_signifier"] = updated

    if source_records:
        projection["source_audio"] = {
            "schema": "astrid.timeline-source-audio.v1",
            "sources": source_records,
            "waveform_bins": requested_count,
        }
    return projection


def _input_projection_bounds(snapshot: dict, options: dict, index: dict) -> tuple[int, int]:
    """Resolve the input clock independently from decoded output duration."""
    fps = Fraction(*snapshot['fps_rational'])
    metadata = snapshot.get('metadata') if isinstance(snapshot.get('metadata'), dict) else {}
    clips = snapshot.get('input_clips') or snapshot.get('clips') or []
    admitted_extent = metadata.get('input_extent_frames')
    if not isinstance(admitted_extent, int) or admitted_extent < 0:
        admitted_extent = max(
            [int(snapshot.get('duration_frames') or 0)]
            + [int(clip.get('end_frame', 0)) for clip in clips if isinstance(clip, dict)]
        )
    window = options.get('input_window')
    if isinstance(window, dict):
        start_raw, end_raw = window.get('start'), window.get('end')
        start_seconds = Fraction(*start_raw) if isinstance(start_raw, (list, tuple)) else Fraction(str(start_raw))
        end_seconds = Fraction(*end_raw) if isinstance(end_raw, (list, tuple)) else Fraction(str(end_raw))
    else:
        # No explicit navigation window means the complete admitted input
        # extent, even when the decoded rendered output is shorter.
        start_seconds, end_seconds = Fraction(0), Fraction(admitted_extent, 1) / fps
    ceil_frame = lambda value: (value.numerator + value.denominator - 1) // value.denominator
    return (
        max(0, min(admitted_extent, ceil_frame(start_seconds * fps))),
        max(0, min(admitted_extent, ceil_frame(end_seconds * fps))),
    )


def _navigation_usage(snapshot: Mapping[str, object], options: Mapping[str, object]) -> dict[str, object]:
    """Return copyable CLI guidance alongside every filmstrip result."""
    base = [
        'python3', '-m', 'astrid', 'timelines', 'visualize',
        '--project', str(snapshot.get('project_slug') or '<project>'),
        '--timeline-slug', str(snapshot.get('timeline_id') or '<timeline>'),
        '--render-run', str(snapshot.get('render_run_id') or '<render-run>'),
        '--view', 'filmstrip',
    ]
    components = options.get('components') or ('output', 'text', 'audio')
    if isinstance(components, (list, tuple, set)):
        component_tokens = [str(item) for item in components]
    else:
        component_tokens = [str(components)]
    if component_tokens:
        base += ['--show', ','.join(component_tokens)]
    input_only = [
        'python3', '-m', 'astrid', 'timelines', 'visualize',
        '--project', str(snapshot.get('project_slug') or '<project>'),
        '--timeline-slug', str(snapshot.get('timeline_id') or '<timeline>'),
        '--render-run', str(snapshot.get('render_run_id') or '<render-run>'),
        '--view', 'filmstrip', '--show', 'inputs', '--hide', 'output',
    ]
    paired = 'output' in component_tokens and 'inputs' in component_tokens
    paired_layout = [
        'Paired output+inputs pages show one row (five cards by default); use --columns 6 for six across.',
        'Pass --page-size N explicitly to opt into denser paired pages (up to two rows / 10 cards).',
        'Open numbered PNG/SVG pages in order; use frame-index.json static_surface.rows for exact row/card ranges.',
    ] if paired else []
    if paired:
        paired_columns = max(1, int(options.get('columns') or 5))
        base += ['--columns', str(paired_columns)]
        if bool(options.get('page_size_explicit', True)):
            paired_page_size = min(10, paired_columns * 2, max(1, int(options.get('page_size') or 50)))
            base += ['--page-size', str(paired_page_size)]
    return {
        'viewer': 'Open the returned PNG/SVG pages for visual inspection; use frame-index.json for exact card and asset lookup.',
        'keyboard': ['Use numbered PNG/SVG pages for the overview; a multi-page result is intentional for readability.', 'Use frame-index.json to inspect a specific frame, clip, lane, or exact target.', 'Use the copyable focus commands below to regenerate a narrower view.'],
        'filters': ['Use Shot, Track, From/To, Samples, and Density by rerunning the command with the matching flags.', 'Density only reduces captured frames; rerun the command for finer samples.'],
        'commands': {
            'rerun_base': shlex.join(base),
            'zoom_range': shlex.join(base + ['--range', 'START..END', '--every', '0.25', '--detail']),
            'change_interval_seconds': shlex.join(base + ['--every', '1']),
            'change_interval_frames': shlex.join(base + ['--every-frames', '12']),
            'change_resolution': shlex.join(base + ['--resolution', '960x540']),
            'input_lanes_only': shlex.join(input_only),
        },
        'notes': ['--every and --every-frames are mutually exclusive.', '--range is half-open START..END seconds.', '--columns and --page-size change static layout; --track narrows input lanes.', *paired_layout],
        'request': dict(options.get('request') or {}),
    }


def _materialize_input_previews(projection: dict, pack_root: Path) -> None:
    """Materialize digest-verified visual stills/posters into the result pack.

    Runtime-managed files are intentionally extensionless, so media type comes
    from the admitted registry metadata rather than the path suffix. Audio
    clips have no visual preview and are left as waveform-only placements.
    """
    from PIL import Image

    preview_root = pack_root / 'source-previews'
    seen: set[str] = set()
    for track in projection.get('tracks') or []:
        for clip in track.get('clips') or []:
            preview = clip.get('source_preview') if isinstance(clip, dict) else None
            if not isinstance(preview, dict) or preview.get('status') != 'verified':
                continue
            source = preview.get('path')
            if not isinstance(source, str) or not source:
                continue
            source_path = Path(source).expanduser()
            if not source_path.is_file():
                continue
            media_type = str(preview.get('media_type') or '').lower()
            media_kind = media_type.split('/', 1)[0]
            if media_kind == 'audio':
                # An audio source is represented by its exact amber timing
                # rail, never by a misleading crossed/thumbnail tile.
                continue
            digest = str(preview.get('digest') or '')
            name = hashlib.sha256((digest or source_path.as_posix()).encode()).hexdigest()[:24] + '.png'
            destination = preview_root / name
            if name not in seen:
                preview_root.mkdir(parents=True, exist_ok=True)
                try:
                    if media_kind == 'video':
                        subprocess.run(
                            [
                                'ffmpeg', '-hide_banner', '-loglevel', 'error',
                                '-i', str(source_path), '-frames:v', '1',
                                '-vf', 'scale=320:180:force_original_aspect_ratio=decrease',
                                '-y', str(destination),
                            ], check=True, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                    else:
                        with Image.open(source_path) as source_image:
                            source_image.convert('RGBA').save(destination, format='PNG')
                except (OSError, ValueError, subprocess.SubprocessError):
                    continue
                seen.add(name)
            materialized = dict(preview)
            materialized.pop('path', None)
            materialized['preview'] = f'source-previews/{name}'
            materialized['preview_kind'] = 'poster' if media_kind == 'video' else 'still'
            clip['source_preview'] = materialized


def _spread(values, count):
    """Choose deterministic, evenly distributed values from sorted input."""
    values = sorted(set(values))
    if count <= 0 or not values:
        return []
    if len(values) <= count:
        return values
    if count == 1:
        return [values[(len(values) - 1) // 2]]
    return [values[(i * (len(values) - 1) + (count - 1) // 2) // (count - 1)] for i in range(count)]


def _evenly_spaced(total, count):
    """Return at most ``count`` interior frames without scanning the render."""
    if total <= 0 or count <= 0:
        return []
    return sorted({(i * (total - 1) + count // 2) // count for i in range(1, count + 1)})


def _boundary_index(snapshot, clips, spans, total, fps):
    entries = [
        {'frame': 0, 'time_seconds': 0.0, 'kind': 'rendered_first_frame', 'source': 'decoded_render'},
        {'frame': total - 1, 'time_seconds': float(Fraction(total - 1, 1) / fps),
         'kind': 'rendered_eof', 'source': 'decoded_render'},
    ]
    for clip in clips:
        start, end = spans[id(clip)]
        if clip.get('kind') in ('audio', 'voiceover', 'music', 'sound'):
            continue
        for frame, boundary in (
            (start - 1, 'before_start'), (start, 'start'),
            (end - 1, 'before_end'), (end, 'end_exclusive'),
        ):
            if 0 <= frame < total:
                entries.append({'frame': frame, 'time_seconds': float(Fraction(frame, 1) / fps),
                                'kind': 'clip_boundary', 'boundary': boundary,
                                'clip_id': str(clip.get('id'))})
    for occurrence in snapshot.get('occurrences', []):
        start, end = int(occurrence.get('start_frame', 0)), int(occurrence.get('end_frame', 0))
        for frame, boundary in ((start, 'start'), (end, 'end_exclusive')):
            if 0 <= frame < total:
                entries.append({'frame': frame, 'time_seconds': float(Fraction(frame, 1) / fps),
                                'kind': 'admitted_occurrence_boundary', 'boundary': boundary,
                                'occurrence_id': str(occurrence.get('occurrence_id'))})
    tail = (snapshot.get('metadata') or {}).get('rendered_tail')
    if not isinstance(tail, dict):
        tail = next((clip for clip in clips if clip.get('render_tail')), None)
    if isinstance(tail, dict):
        start = int(tail.get('start_frame', 0))
        if 0 < start < total:
            entries.append({'frame': start - 1, 'time_seconds': float(Fraction(start - 1, 1) / fps),
                            'kind': 'rendered_tail_transition', 'source': 'decoded_render'})
            entries.append({'frame': start, 'time_seconds': float(Fraction(start, 1) / fps),
                            'kind': 'rendered_tail_start', 'source': 'decoded_render'})
    return entries


def _full_overview(snapshot, clips, spans, total, fps, limit):
    """Plan a bounded full-render overview while retaining boundary evidence."""
    entries = _boundary_index(snapshot, clips, spans, total, fps)
    reasons = {}

    def add(frame, reason):
        if 0 <= frame < total:
            reasons.setdefault(frame, set()).add(reason)

    add(0, 'overview_first_frame')
    add(total - 1, 'overview_last_frame')
    tail = (snapshot.get('metadata') or {}).get('rendered_tail')
    if not isinstance(tail, dict):
        tail = next((clip for clip in clips if clip.get('render_tail')), None)
    tail_start = int(tail.get('start_frame', 0)) if isinstance(tail, dict) else None
    if tail_start is not None:
        if tail_start > 0:
            add(tail_start - 1, 'rendered_tail_transition')
        add(tail_start, 'rendered_tail_start')
        add(total - 1, 'rendered_tail_eof')
    mandatory_count = len(reasons)
    if mandatory_count > limit:
        raise ValueError(f'Overview requires {mandatory_count} mandatory frames but max_frames is {limit}.')

    boundary_frames = [entry['frame'] for entry in entries if entry['frame'] not in reasons]
    remaining = limit - len(reasons)
    boundary_budget = min(len(set(boundary_frames)), remaining // 2)
    for frame in _spread(boundary_frames, boundary_budget):
        add(frame, 'overview_boundary')
    interior_budget = limit - len(reasons)
    for frame in _evenly_spaced(total, interior_budget):
        if frame not in reasons:
            add(frame, 'overview_interior')
    # Interior points can coincide with mandatory or boundary selections. Use
    # one bounded oversampled candidate set to fill any remaining slots while
    # keeping the overview capped and deterministic.
    if len(reasons) < limit:
        for frame in _evenly_spaced(total, max(limit * 2, 1)):
            if frame not in reasons:
                add(frame, 'overview_interior')
                if len(reasons) >= limit:
                    break
    for entry in entries:
        entry['selected'] = entry['frame'] in reasons
    selected_boundary_count = sum(1 for entry in entries if entry['selected'])
    coverage = {
        'clock': 'rendered_decoded',
        'full_duration': True,
        'window_seconds': [0.0, float(Fraction(total, 1) / fps)],
        'selected_frame_count': len(reasons),
        'selected_fraction': len(reasons) / total,
        'mandatory_frames': sorted(reasons),
        'boundary_count': len(entries),
        'selected_boundary_count': selected_boundary_count,
        'unselected_boundary_count': len(entries) - selected_boundary_count,
        'all_boundaries_sampled': False,
        'guarantees': ['first decoded frame', 'last decoded frame', 'rendered-tail transition and EOF'],
        'not_promised': ['every fast-cut boundary is sampled', 'overview cards provide exact navigation for every frame'],
    }
    return reasons, {'schema': 'astrid.filmstrip.boundary-index.v1', 'clock': 'rendered_decoded',
                     'rendered_frame_count': total, 'entries': entries}, coverage


def plan_filmstrip(snapshot: dict, options: dict) -> dict:
    """Plan integer presentation frames; all time windows are half-open."""
    # Resolve friendly shot aliases once against the frozen snapshot.  Exact
    # ids/names remain unchanged; ``first`` and one-based ordinals become the
    # canonical id before filtering both cards and input/output projections.
    if options.get('shot') is not None:
        from .shot_selector import resolve_shot_selector
        resolved_shot = resolve_shot_selector(options.get('shot'), snapshot)
        if resolved_shot != options.get('shot'):
            options = dict(options)
            options['shot'] = resolved_shot
    fps = Fraction(*snapshot['fps_rational'])
    total = int(snapshot['duration_frames'])
    if fps <= 0 or total <= 0:
        raise ValueError('Filmstrip requires a positive frame rate and duration.')
    duration = Fraction(total, 1) / fps
    mode = options.get('sample') or 'interval'
    if mode not in ('interval', 'clips', 'cuts', 'shots'):
        raise ValueError(f'Unknown sampling mode: {mode}')
    lo, hi = Fraction(0), duration
    if options.get('range') is not None:
        lo, hi = map(_q, options['range'])
    if options.get('at') is not None:
        if options.get('range') is not None:
            raise ValueError('Choose range or at/context, not both.')
        at, context = _q(options['at']), _q(options.get('context', 2))
        if context <= 0:
            raise ValueError('Context must be positive.')
        lo, hi = at - context, at + context
    lo, hi = max(lo, Fraction(0)), min(hi, duration)
    if hi <= lo:
        raise ValueError('Requested window contains no rendered frames.')
    clips = snapshot.get('clips', [])
    spans = {id(c): _frame_span(c, fps) for c in clips}
    selected = clips
    for key in ('clip', 'shot', 'asset'):
        value = options.get(key)
        if value is not None:
            fields = {'clip': ('id',), 'shot': ('shot_id', 'shot_name'), 'asset': ('asset',)}[key]
            selected = [c for c in selected if str(value) in [str(c.get(f)) for f in fields]]
            if not selected:
                raise ValueError(f'No clips match {key}={value!r}.')
    filtered = any(options.get(k) is not None for k in ('clip', 'shot', 'asset'))
    if mode == 'shots' and not snapshot.get('occurrences') and not any(c.get('shot_id') for c in selected):
        raise ValueError('Shot sampling requires shot metadata.')
    first, stop = math.ceil(lo * fps), min(total, math.ceil(hi * fps))
    reasons = {}
    boundary_index = None
    coverage = None
    limit = int(options.get('max_frames') or 2000)
    def add(frame, reason):
        if not first <= frame < stop:
            return
        if filtered and not any(a <= frame < b for a, b in (spans[id(c)] for c in selected)):
            return
        reasons.setdefault(frame, set()).add(reason)
        if len(reasons) > limit:
            raise ValueError(f'Filmstrip exceeds {limit} frames; use a coarser --every or a narrower --range.')
    if options.get('every_frames') is not None and options.get('every') is not None:
        raise ValueError('Choose every or every_frames, not both.')
    if options.get('every_frames') is not None:
        step = _q(options['every_frames'])
        if step.denominator != 1 or step <= 0:
            raise ValueError('every_frames must be a positive integer.')
    else:
        seconds = _q(options.get('every') if options.get('every') is not None else '0.5')
        if seconds <= 0:
            raise ValueError('every must be positive.')
        step = max(Fraction(1), seconds * fps)
    explicit_interval = (bool(options.get('explicit_interval'))
                         if 'explicit_interval' in options
                         else options.get('every') is not None or options.get('every_frames') is not None)
    include_cuts = bool(options.get('include_cuts'))
    is_full_overview = (mode == 'interval' and not filtered and options.get('range') is None
                        and options.get('at') is None and not explicit_interval)
    if is_full_overview:
        overview_limit = min(limit, OVERVIEW_MAX_CARDS)
        reasons, boundary_index, coverage = _full_overview(snapshot, clips, spans, total, fps, overview_limit)
    elif mode == 'interval':
        # Jump directly into selected clip windows; never scan an entire movie
        # to discover a short filtered clip near its end.
        windows = sorted((max(first, spans[id(c)][0]), min(stop, spans[id(c)][1])) for c in selected) if filtered else [(first, stop)]
        merged = []
        for a, b in windows:
            if b <= a:
                continue
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        candidates = 0
        for a, b in merged:
            k = math.ceil(Fraction(a, 1) / step)
            while (frame := math.floor(k * step)) < b:
                candidates += 1
                if candidates > limit + len(merged):
                    raise ValueError(f'Filmstrip exceeds {limit} sample candidates; use a coarser --every or a narrower --range.')
                add(frame, 'interval')
                k += 1
    if not is_full_overview:
        seen_shots = set()
        for clip in selected:
            start, end = spans[id(clip)]
            if end <= first or start >= stop:
                continue
            visual = clip.get('kind') not in ('audio', 'voiceover', 'music', 'sound')
            # Interval sampling is a strict periodic grid.  Boundary
            # neighbors are a separate, explicit policy so ``--every 5``
            # cannot silently turn into 5s + 7.03s + 7.06s + shot beats.
            if visual and (mode == 'cuts' or (mode == 'interval' and include_cuts)):
                for frame, reason in ((start - 1, 'before_cut'), (start, 'after_cut'), (end - 1, 'before_cut'), (end, 'after_cut')):
                    add(frame, reason)
            if visual and mode == 'clips':
                add(max(first, start), 'clip_first')
            if mode == 'shots':
                occurrence_key = clip.get('occurrence_id') or clip.get('shot_id')
                if not snapshot.get('occurrences') and occurrence_key and occurrence_key not in seen_shots:
                    shot_spans = [spans[id(c)] for c in selected if (c.get('occurrence_id') or c.get('shot_id')) == occurrence_key]
                    midpoint = (min(a for a, b in shot_spans) + max(b for a, b in shot_spans)) / 2
                    add(math.floor(midpoint), 'shot_midpoint')
                    seen_shots.add(occurrence_key)
        if mode == 'shots':
            for occurrence in snapshot.get('occurrences', []):
                if options.get('shot') and options['shot'] not in {occurrence.get('shot_id'), occurrence.get('shot_name')}:
                    continue
                start, end = occurrence['start_frame'], occurrence['end_frame']
                if start < stop and end > first:
                    add((start + end) // 2, 'shot_midpoint')
    if not reasons:
        raise ValueError('No rendered frames match the requested sample and filters.')
    if boundary_index is None:
        boundary_index = _boundary_index(snapshot, clips, spans, total, fps)
        selected = set(reasons)
        for entry in boundary_index:
            entry['selected'] = entry['frame'] in selected
        coverage = {
            'clock': 'rendered_decoded',
            'full_duration': first == 0 and stop == total,
            'window_seconds': [float(lo), float(hi)],
            'selected_frame_count': len(reasons),
            'selected_fraction': len(reasons) / max(1, stop - first),
            'boundary_count': len(boundary_index),
            'selected_boundary_count': sum(1 for entry in boundary_index if entry['selected']),
            'unselected_boundary_count': sum(1 for entry in boundary_index if not entry['selected']),
            'all_boundaries_sampled': all(entry['selected'] for entry in boundary_index),
            'not_promised': ['every fast-cut boundary is sampled'] if not all(entry['selected'] for entry in boundary_index) else [],
        }
    cards = []
    for frame, why in sorted(reasons.items()):
        time = Fraction(frame, 1) / fps
        active = [c for c in clips if spans[id(c)][0] <= frame < spans[id(c)][1]]
        # ``scripts`` remains the complete shot-script context for JSON/Markdown
        # drill-down.  ``captions`` is the precise display channel and only
        # contains frozen, timed speech annotations covering this frame.
        scripts = [s for s in snapshot.get('scripts', []) if _q(s['start']) <= time < _q(s['end'])]
        captions = _speech_caption_records(snapshot, time)
        caption_status = 'timed caption' if captions else 'no timed text available'
        target = f"frame-{frame:09d}"
        cards.append({'id': target, 'frame': frame, 'time_seconds': float(time), 'time_rational': [time.numerator, time.denominator], 'time_label': f'{float(time):.3f}s', 'sample_reasons': sorted(why), 'clips': active, 'scripts': scripts, 'captions': captions, 'caption_status': caption_status, 'script_status': 'script segment (not word-aligned)' if scripts else 'no script', 'shot_ids': sorted({str(c['shot_id']) for c in active if c.get('shot_id')}), 'image': f'frames/{target}.jpg', 'actions': {'target': '#' + target}})
    _project_display_scripts(cards)
    navigation = build_inspector_navigation(snapshot, cards)
    for card, target in zip(cards, navigation['frames']):
        card['navigation_target'] = target['target']
        card['actions']['focus_command'] = target['actions']['focus_command']
    page_size = int(options.get('page_size') or 50)
    page_count = math.ceil(len(cards) / page_size)
    coverage['page_count'] = page_count
    coverage['page_size'] = page_size
    coverage['selected_frame_ids'] = [card['id'] for card in cards]
    return {'navigation': navigation, 'schema': 'astrid.filmstrip.v1',
            'provenance': {k: snapshot.get(k) for k in ('project_slug', 'timeline_id', 'timeline_name', 'render_run_id', 'video_digest', 'fps_rational', 'duration_frames', 'metadata')},
            'audio': snapshot.get('audio') if isinstance(snapshot.get('audio'), dict) else navigation['audio'],
            'boundary_index': boundary_index,
            'coverage': coverage,
            'sampling': {'mode': 'overview' if is_full_overview else mode, 'overview': is_full_overview,
                         'range': [float(lo), float(hi)], 'effective_range': [float(lo), float(hi)],
                         'requested_range': options.get('range'), 'requested_at': options.get('at'),
                         'density': options.get('density'), 'resolution': options.get('resolution'),
                         'step_frames_rational': [step.numerator, step.denominator],
                         'explicit_interval': explicit_interval, 'include_cuts': include_cuts,
                         'options': options},
            'cards': cards}


def _lines(card):
    shots = ', '.join(dict.fromkeys(str(c.get('shot_name') or c.get('shot_id')) for c in card['clips'] if c.get('shot_id') or c.get('shot_name')))
    clips = ', '.join(str(c.get('id')) for c in card['clips']) or 'no active clip'
    # ``scripts`` is the complete overlapping shot context retained for
    # machine-readable inspection.  The human-facing strip must use the
    # de-duplicated display channel when the planner provided it; otherwise a
    # coarse sample repeats one untimed shot script on every card.
    if card.get('captions'):
        text_items = card['captions']
    elif 'display_scripts' in card:
        text_items = card.get('display_scripts') or []
    else:
        text_items = card.get('scripts') or []
    if card.get('captions'):
        status = 'timed caption'
    elif card.get('display_scripts'):
        status = 'shot script context (not word-aligned)'
    elif 'display_scripts' in card:
        # The occurrence is still active, but its untimed script was already
        # shown on an earlier sample.  Keep the card quiet instead of printing
        # a status label that looks like a second caption.
        status = ''
    else:
        status = card.get('script_status', '')
    return [f"{card['time_label']} · frame {card['frame']}", shots or 'No shot label', clips, status] + [str(s.get('canonical_text') or s.get('text', '')) for s in text_items]


def _extract(video_path, cards, out_root, resolution=None):
    frames = out_root / 'frames'
    frames.mkdir(parents=True, exist_ok=True)
    expression = '+'.join(f'eq(n,{c["frame"]})' for c in cards)
    filter_path = out_root / 'frame-selection.txt'
    scale = f'{resolution[0]}:{resolution[1]}' if resolution else '480:-2'
    filter_path.write_text(f"select='{expression}',scale={scale}", encoding='utf-8')
    # FFmpeg 9 removed the legacy -filter_script[:v] and -vsync options. Keep
    # the deterministic filter text in the fixture-local file for provenance,
    # but pass the graph and passthrough frame mode through their supported
    # options.
    filter_graph = filter_path.read_text(encoding='utf-8')
    result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(video_path), '-vf', filter_graph, '-fps_mode:v', 'passthrough', '-q:v', '3', '-y', str(frames / 'sample-%06d.jpg')], capture_output=True, text=True)
    if result.returncode:
        raise ValueError('Rendered frame extraction failed: ' + result.stderr[-2000:])
    samples = sorted(frames.glob('sample-*.jpg'))
    if len(samples) != len(cards):
        raise ValueError(f'Render has {len(samples)} requested frames, expected {len(cards)}; verify render provenance and duration.')
    for source, card in zip(samples, cards):
        source.rename(out_root / card['image'])


def _static_lines(card, *, show_text=True):
    """Bound bitmap text; complete captions remain in JSON/Markdown."""
    lines = []
    truncated = False
    source_lines = _lines(card)
    captions = source_lines[:3] if not show_text else source_lines[:2] + (source_lines[4:] or ['No script'])
    for text in captions:
        clipped = text[:1200]
        wrapped = textwrap.wrap(clipped, 43) or ['']
        remaining = 16 - len(lines)
        lines.extend(wrapped[:remaining])
        if len(text) > 1200 or len(wrapped) > remaining:
            truncated = True
        if len(lines) >= 16:
            truncated = True
            break
    if truncated:
        lines = lines[:15] + ['[Excerpt; full text in JSON / Markdown]']
    return lines


_PNG_FONT_PATH = Path(__file__).with_name('fonts') / 'PowerGrotesk-Regular.ttf'
_PNG_FALLBACK_FONT_PATH = Path(__file__).with_name('fonts') / 'NotoSansSC-Regular.ttf'
_PNG_EMOJI_FONT_PATH = Path(__file__).with_name('fonts') / 'NotoEmoji-Regular.ttf'
_PNG_PAGE_WIDTH_STRIDE = 344
_PNG_CARD_WIDTH = 328
_PNG_IMAGE_HEIGHT = 216
_PNG_HEADER_HEIGHT = 56
# Give the measured mix enough vertical room to read at a glance.  The raw
# bins remain unchanged; this is presentation chrome only.  This is a display
# height, not a change to the waveform's sample/time resolution.
_PNG_AUDIO_HEIGHT = 76
_PNG_AUDIO_BAR_COUNT = 72
_PNG_AUDIO_BAR_WIDTH = 4
_PNG_ROW_GAP = 26
_PNG_ROW_RULE_COLOR = '#405769'
# Keep spoken text in a stable, visually deliberate panel below the preview
# and waveform.  The panel is larger than the text block so short captions do
# not look pinned to the lower-left corner of a card.
_PNG_TEXT_LINE_HEIGHT = 22
_PNG_TEXT_AREA_MIN_HEIGHT = 72
_PNG_TEXT_AREA_PADDING = 16


class _PngFontChain:
    """Keep the designed face for ordinary text and fill missing glyphs locally."""

    __slots__ = ('primary', 'fallback', 'emoji', '_missing_masks')

    def __init__(self, primary, fallback, emoji):
        self.primary = primary
        self.fallback = fallback
        self.emoji = emoji
        self._missing_masks = {}

    def _missing(self, font, character):
        key = (id(font), character)
        if key not in self._missing_masks:
            try:
                actual = font.getmask(character)
                sentinel = font.getmask('\uffff')
                self._missing_masks[key] = actual.size == sentinel.size and bytes(actual) == bytes(sentinel)
            except (AttributeError, UnicodeEncodeError, ValueError):
                self._missing_masks[key] = True
        return self._missing_masks[key]

    def for_character(self, character):
        if not self._missing(self.primary, character):
            return self.primary
        if not self._missing(self.fallback, character):
            return self.fallback
        if not self._missing(self.emoji, character):
            return self.emoji
        # The CJK fallback is the broadest bundled face. It gives a stable,
        # non-tofu result even for a code point outside both curated ranges.
        return self.fallback


def _png_font(size):
    from PIL import ImageFont
    try:
        primary = ImageFont.truetype(str(_PNG_FONT_PATH), size)
    except OSError as exc:
        raise RuntimeError(f'Bundled PNG font is unavailable: {_PNG_FONT_PATH}') from exc
    try:
        fallback = ImageFont.truetype(str(_PNG_FALLBACK_FONT_PATH), size)
        emoji = ImageFont.truetype(str(_PNG_EMOJI_FONT_PATH), size)
    except OSError as exc:
        raise RuntimeError(
            f'Bundled PNG fallback fonts are unavailable: {_PNG_FALLBACK_FONT_PATH} and {_PNG_EMOJI_FONT_PATH}'
        ) from exc
    return _PngFontChain(primary, fallback, emoji)


def _png_font_runs(text, font):
    if not isinstance(font, _PngFontChain):
        yield str(text), font
        return
    run, run_font = '', None
    for character in str(text):
        character_font = font.for_character(character)
        if run and character_font is not run_font:
            yield run, run_font
            run = ''
        run += character
        run_font = character_font
    if run:
        yield run, run_font


def _png_draw_text(draw, xy, text, font, **kwargs):
    """Draw measured runs so unsupported glyphs use the bundled fallback face."""
    x, y = xy
    for run, actual_font in _png_font_runs(text, font):
        draw.text((x, y), run, font=actual_font, **kwargs)
        x += _png_text_width(draw, run, actual_font)


def _png_text_width(draw, text, font):
    if isinstance(font, _PngFontChain):
        return sum(_png_text_width(draw, run, actual_font) for run, actual_font in _png_font_runs(text, font))
    try:
        return float(draw.textlength(text, font=font))
    except (AttributeError, TypeError):
        left, _top, right, _bottom = draw.textbbox((0, 0), text, font=font)
        return float(right - left)


def _png_wrap(draw, text, font, width):
    """Wrap measured text, including long unbroken tokens, without truncation."""
    lines = []
    for paragraph in str(text).split('\n'):
        if not paragraph:
            lines.append('')
            continue
        line = ''
        for token in paragraph.split(' '):
            candidate = token if not line else f'{line} {token}'
            if line and _png_text_width(draw, candidate, font) > width:
                lines.append(line)
                line = ''
            if _png_text_width(draw, token, font) <= width:
                line = token if not line else f'{line} {token}'
                continue
            # Break a token by measured glyph width so URLs, IDs, and Unicode
            # strings cannot escape the card bounds.
            for character in token:
                candidate = character if not line else line + character
                if line and _png_text_width(draw, candidate, font) > width:
                    lines.append(line)
                    line = character
                else:
                    line = candidate
        lines.append(line)
    return lines or ['']


def _png_bounded_lines(draw, text, font, width, limit):
    lines = _png_wrap(draw, text, font, width)
    excerpt = len(lines) > limit
    return lines[:limit], excerpt


def _png_ellipsis(draw, text, font, width):
    marker = '…'
    if _png_text_width(draw, marker, font) > width:
        return marker
    result = str(text)
    while result and _png_text_width(draw, result + marker, font) > width:
        result = result[:-1]
    return result + marker if result else marker


def _png_chrome_lines(draw, text, font, width, limit):
    lines, excerpt = _png_bounded_lines(draw, text, font, width, limit)
    if excerpt:
        lines[-1] = _png_ellipsis(draw, lines[-1], font, width)
    return lines


def _png_shot_label(card):
    labels = []
    for clip in card.get('clips') or []:
        label = clip.get('shot_name') or clip.get('shot_id')
        if label and str(label) not in labels:
            labels.append(str(label))
    return ' · '.join(labels) if labels else 'Unlabelled shot'


def _png_script_lines(draw, card, font, *, show_text=True):
    if not show_text:
        return [], False
    if 'captions' in card:
        timed = card.get('captions') or []
        source = timed or card.get('display_scripts') or []
        text = '\n'.join(str(item.get('canonical_text') or item.get('text') or '')
                          for item in source).strip()
        status = card.get('caption_status') or 'No timed text available'
        # Repeated samples inside one coarse shot are intentionally quiet in
        # the visual strip.  The machine-readable status remains available in
        # frame-index/details; putting it under every frame reads like a fake
        # caption and obscures the actual review image.
        empty_label = '' if status == 'same shot; no new timed text' else status
    else:
        # Keep the low-level renderer useful for callers constructing a legacy
        # card by hand; canonical planner output always carries ``captions``.
        text = '\n'.join(str(script.get('text', '')) for script in card.get('scripts') or []).strip()
        empty_label = 'No spoken text'
    if not text:
        return [empty_label, ''], False
    bounded = f'“{text[:1200]}”'
    lines, excerpt = _png_bounded_lines(draw, bounded, font, 308, 6)
    if len(lines) < 2:
        lines.append('')
    if len(text) > 1200:
        excerpt = True
    return lines, excerpt


def _png_audio_time(value):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return Fraction(int(value[0]), int(value[1]))
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    try:
        return Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _png_waveform_for_card(audio, card, *, count=_PNG_AUDIO_BAR_COUNT, context_seconds=2.4):
    """Project the frozen render waveform into a small card-local strip.

    The PNG is a static overview, so it uses the highest bounded analysis level
    and resamples bins around the captured frame time.  This keeps silence
    honest (zero-height bars) while retaining a visible cursor at the frame.
    """
    if not isinstance(audio, dict) or str(audio.get('status', '')).lower() not in {
        'ok', 'available', 'complete', 'analysis_complete', 'analyzed'
    }:
        return None
    stream = audio.get('stream')
    waveform = audio.get('waveform')
    if not isinstance(stream, dict) or not isinstance(waveform, dict):
        return None
    try:
        sample_rate = int(stream.get('sample_rate'))
    except (TypeError, ValueError):
        return None
    if sample_rate <= 0:
        return None
    levels = waveform.get('levels')
    if not isinstance(levels, list):
        return None
    usable = [level for level in levels if isinstance(level, dict) and isinstance(level.get('bins'), list)]
    if not usable:
        return None
    level = max(usable, key=lambda item: int(item.get('target_bins') or len(item.get('bins') or [])))
    bins = level.get('bins') or []
    origin = _png_audio_time((audio.get('presentation_origin') or {}).get('seconds', [0, 1]))
    if origin is None:
        origin = Fraction(0)
    try:
        card_time = Fraction(str(card.get('time_seconds', 0)))
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    duration_value = waveform.get('duration_seconds')
    try:
        duration = Fraction(str(duration_value)) if duration_value is not None else None
    except (TypeError, ValueError, ZeroDivisionError):
        duration = None
    if duration is None:
        ends = [item.get('end_sample') for item in bins if isinstance(item, dict)]
        duration = Fraction(max(ends), sample_rate) if ends and max(ends) is not None else None
    render_end = origin + duration if duration is not None and duration > 0 else None
    half = Fraction(str(context_seconds)) / 2
    start, end = card_time - half, card_time + half
    if render_end is not None:
        start, end = max(origin, start), min(render_end, end)
    if end <= start:
        return None
    amplitudes = [0.0] * max(1, int(count))
    for index in range(len(amplitudes)):
        bucket_start = start + (end - start) * index / len(amplitudes)
        bucket_end = start + (end - start) * (index + 1) / len(amplitudes)
        peak = 0.0
        for item in bins:
            if not isinstance(item, dict):
                continue
            try:
                item_start = origin + Fraction(int(item.get('start_sample', 0)), sample_rate)
                item_end = origin + Fraction(int(item.get('end_sample', 0)), sample_rate)
            except (TypeError, ValueError, ZeroDivisionError):
                continue
            if item_end <= bucket_start or item_start >= bucket_end:
                continue
            values = item.get('peak') or item.get('max') or []
            if not isinstance(values, (list, tuple)):
                values = [values]
            for value in values:
                try:
                    peak = max(peak, abs(float(value)))
                except (TypeError, ValueError):
                    continue
        amplitudes[index] = min(1.0, peak)
    cursor = float((card_time - start) / (end - start))
    return {
        # ``amplitudes`` are the measured values.  Keep these as the stable
        # machine-facing signal and derive a display-only version below so a
        # quiet-but-real voice track does not disappear in a small card.
        'amplitudes': amplitudes,
        'display_amplitudes': _png_waveform_display_amplitudes(amplitudes),
        'cursor': max(0.0, min(1.0, cursor)),
        'start': float(start), 'end': float(end),
    }


def _png_waveform_display_amplitudes(
    amplitudes, *, target_peak=0.96, max_gain=24.0, gamma=0.62,
):
    """Make a low-level measured waveform legible without inventing sound.

    Static cards are a visual inspection surface, not a loudness meter.  Use
    peak normalization only for non-zero bins: silence stays at zero, while a
    quiet voice recording gets a useful visual range as a louder mix.  A
    bounded power curve increases contrast in low-amplitude speech without
    changing ordering or turning zero into sound.  The original measured
    amplitudes remain available in ``amplitudes``.
    """
    values = []
    for value in amplitudes or []:
        try:
            values.append(max(0.0, min(1.0, float(value))))
        except (TypeError, ValueError):
            values.append(0.0)
    peak = max(values, default=0.0)
    if peak <= 0.0:
        return values
    gain = min(float(max_gain), float(target_peak) / peak)
    return [
        min(1.0, float(target_peak) * ((value * gain / float(target_peak)) ** float(gamma)))
        for value in values
    ]


def _png_card_metrics(draw, card, name_font, timestamp_font, script_font, audio=None, *, show_text=True, image_height=_PNG_IMAGE_HEIGHT):
    timestamp = str(card.get('time_label', ''))
    timestamp_lines = _png_wrap(draw, timestamp, timestamp_font, 150)
    timestamp_width = max((_png_text_width(draw, line, timestamp_font) for line in timestamp_lines), default=0)
    name_width = 308 - timestamp_width - 12
    separate_timestamp = name_width < 100
    if separate_timestamp:
        name_width = 308
    name_lines, name_excerpt = _png_bounded_lines(draw, _png_shot_label(card)[:1200], name_font, name_width, 2)
    if name_excerpt:
        name_lines[-1] = _png_ellipsis(draw, name_lines[-1], name_font, name_width)
    header_lines = max(len(name_lines), len(timestamp_lines), 1)
    if separate_timestamp:
        header_lines = max(header_lines + 1, 2)
    extra_header_lines = max(0, header_lines - 2)
    script_lines, excerpt = _png_script_lines(draw, card, script_font, show_text=show_text)
    waveform = _png_waveform_for_card(audio, card)
    audio_extra = _PNG_AUDIO_HEIGHT + 8 if waveform is not None else 0
    text_content_height = _PNG_TEXT_LINE_HEIGHT * len(script_lines) + (
        _PNG_TEXT_LINE_HEIGHT if excerpt else 0
    )
    text_area_height = max(_PNG_TEXT_AREA_MIN_HEIGHT, text_content_height + _PNG_TEXT_AREA_PADDING)
    height = 314 + (image_height - _PNG_IMAGE_HEIGHT) + audio_extra + text_area_height + 22 * extra_header_lines
    return {
        'timestamp': timestamp, 'timestamp_lines': timestamp_lines,
        'name_lines': name_lines, 'name_width': name_width,
        'separate_timestamp': separate_timestamp,
        'header_lines': header_lines, 'extra_header_lines': extra_header_lines,
        'script_lines': script_lines, 'excerpt': excerpt, 'waveform': waveform,
        'audio_extra': audio_extra, 'text_content_height': text_content_height,
        'text_area_height': text_area_height, 'height': height,
    }


def _static_svg(cards, out_root, columns, page_size, timeline_name, render_run_id, render_selection, *, show_text=True, show_output=True, detail=False):
    """Render the pre-refresh SVG contract byte-for-byte."""
    from PIL import ImageFont
    font = ImageFont.truetype('DejaVuSans.ttf', 13) if Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists() else ImageFont.load_default(size=13)
    paths = []
    for page, offset in enumerate(range(0, len(cards), page_size), 1):
        group = cards[offset:offset + page_size]
        wrapped = [_static_lines(c, show_text=show_text) for c in group]
        image_height = 288 if detail else 216
        text_area_heights = [max(72, 18 * len(lines) + 16) for lines in wrapped]
        heights = [max(260 + (image_height - 216) + text_area_heights[i] for i in range(row, min(row + columns, len(group)))) for row in range(0, len(group), columns)]
        width, height = columns * 344 + 24, sum(heights) + 88
        if width * height > 64_000_000:
            raise ValueError('Static page exceeds 64 million pixels; reduce --page-size.')
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#111827"/><text x="16" y="28" fill="white">{html.escape(f"{timeline_name} · page {page} · rendered frames")}</text><text x="16" y="44" fill="#acbbcb" font-family="sans-serif" font-size="13">{html.escape(f"Render {render_run_id} · selection: {render_selection}")}</text><text x="16" y="62" fill="#acbbcb" font-family="sans-serif" font-size="13">{html.escape("Authored script segments, not word-aligned. No script does not imply silence.")}</text>']
        y = 72
        for i, card in enumerate(group):
            x = 16 + (i % columns) * 344
            if i and i % columns == 0:
                y += heights[i // columns - 1]
            if show_output:
                data = base64.b64encode((out_root / card['image']).read_bytes()).decode()
                svg.append(f'<image x="{x}" y="{y}" width="328" height="{image_height}" preserveAspectRatio="xMinYMin meet" href="data:image/jpeg;base64,{data}"/>')
            else:
                svg.append(f'<rect x="{x}" y="{y}" width="328" height="{image_height}" rx="6" fill="#162630" stroke="#405769"/><text x="{x + 12}" y="{y + image_height / 2}" fill="#9fb0bf" font-family="sans-serif" font-size="14">Output hidden</text>')
            text_area_top = y + image_height + 8
            text_area_height = text_area_heights[i]
            text_block_height = 18 * len(wrapped[i])
            text_top = text_area_top + max(0, (text_area_height - text_block_height) / 2)
            for j, line in enumerate(wrapped[i]):
                ty = text_top + j * 18
                svg.append(f'<text x="{x + 164}" y="{ty + 13}" text-anchor="middle" fill="#e5e7eb" font-family="sans-serif" font-size="13">{html.escape(line)}</text>')
        paths.append((page, width, height, ''.join(svg) + '</svg>'))
    return paths


def _static_png(cards, out_root, columns, page_size, timeline_name, render_run_id, render_selection, audio=None, *, show_text=True, show_output=True, detail=False):
    from PIL import Image, ImageDraw
    measure_image = Image.new('RGB', (1, 1))
    measure_draw = ImageDraw.Draw(measure_image)
    name_font, timestamp_font, script_font = _png_font(22 if detail else 18), _png_font(16 if detail else 14), _png_font(18 if detail else 16)
    image_height = 288 if detail else _PNG_IMAGE_HEIGHT
    notice_font = _png_font(12)
    layouts = [_png_card_metrics(measure_draw, card, name_font, timestamp_font, script_font, audio, show_text=show_text, image_height=image_height) for card in cards]
    paths = []
    for page, offset in enumerate(range(0, len(cards), page_size), 1):
        group = cards[offset:offset + page_size]
        group_layouts = layouts[offset:offset + page_size]
        row_heights = [max(group_layouts[i]['height'] for i in range(row, min(row + columns, len(group_layouts)))) for row in range(0, len(group_layouts), columns)]
        width = columns * _PNG_PAGE_WIDTH_STRIDE + 24
        page_title_font, chrome_font = _png_font(20), _png_font(12)
        chrome_width = width - 32
        title_lines = _png_chrome_lines(measure_draw, f'{timeline_name} · page {page} · rendered frames', page_title_font, chrome_width, 2)
        provenance_lines = _png_chrome_lines(measure_draw, f'Render {render_run_id} · selection: {render_selection}', chrome_font, chrome_width, 2)
        disclaimer_lines = _png_chrome_lines(measure_draw, 'Timed speech uses frozen intervals; shot scripts are shown once per occurrence. Missing timed text does not imply silence.', chrome_font, chrome_width, 2)
        chrome_bottom = 10 + 22 * len(title_lines) + 4 + 16 * len(provenance_lines) + 4 + 16 * len(disclaimer_lines)
        card_origin = max(96, chrome_bottom + 8)
        height = card_origin + sum(row_heights) + _PNG_ROW_GAP * max(0, len(row_heights) - 1) + 24
        if width * height > 64_000_000:
            raise ValueError('Static page exceeds 64 million pixels; reduce --page-size.')
        sheet = Image.new('RGB', (width, height), '#111827')
        draw = ImageDraw.Draw(sheet)
        chrome_y = 10
        for line in title_lines:
            _png_draw_text(draw, (16, chrome_y), line, page_title_font, fill='white')
            chrome_y += 22
        chrome_y += 4
        for line in provenance_lines:
            _png_draw_text(draw, (16, chrome_y), line, chrome_font, fill='#acbbcb')
            chrome_y += 16
        chrome_y += 4
        for line in disclaimer_lines:
            _png_draw_text(draw, (16, chrome_y), line, chrome_font, fill='#acbbcb')
            chrome_y += 16
        y = card_origin
        for i, (card, layout) in enumerate(zip(group, group_layouts)):
            x = 16 + (i % columns) * _PNG_PAGE_WIDTH_STRIDE
            if i and i % columns == 0:
                previous_row = i // columns - 1
                y += row_heights[previous_row] + _PNG_ROW_GAP
                separator_y = y - (_PNG_ROW_GAP // 2)
                draw.line((12, separator_y, width - 12, separator_y), fill=_PNG_ROW_RULE_COLOR, width=2)
            header_height = _PNG_HEADER_HEIGHT + 22 * layout['extra_header_lines']
            name_y = y + 8
            timestamp_y = y + 10
            if layout['separate_timestamp']:
                timestamp_y = y + 8
                name_y = y + 30
            for line_no, line in enumerate(layout['name_lines']):
                _png_draw_text(draw, (x + 10, name_y + line_no * 22), line, name_font, fill='white')
            for line_no, line in enumerate(layout['timestamp_lines']):
                right = x + 318
                _png_draw_text(draw, (right - _png_text_width(draw, line, timestamp_font), timestamp_y + line_no * 22), line, timestamp_font, fill='#8ce0d0')
            if show_output:
                with Image.open(out_root / card['image']) as source:
                    source.thumbnail((_PNG_CARD_WIDTH, image_height))
                    image_x = x + (_PNG_CARD_WIDTH - source.width) // 2
                    image_y = y + header_height + (image_height - source.height) // 2
                    sheet.paste(source, (image_x, image_y))
            else:
                draw.rounded_rectangle((x, y + header_height, x + _PNG_CARD_WIDTH, y + header_height + image_height), radius=6, fill='#162630', outline='#405769', width=1)
                _png_draw_text(draw, (x + 12, y + header_height + image_height // 2 - 8), 'Output hidden', timestamp_font, fill='#9fb0bf')
            image_end = y + header_height + image_height
            if layout['waveform'] is not None:
                wave_y = image_end + 6
                wave_x, wave_width = x + 10, _PNG_CARD_WIDTH - 20
                draw.rounded_rectangle((wave_x, wave_y, wave_x + wave_width, wave_y + _PNG_AUDIO_HEIGHT), radius=5,
                                        fill='#0d1a22', outline='#467486', width=2)
                center = wave_y + _PNG_AUDIO_HEIGHT // 2
                draw.line((wave_x + 7, center, wave_x + wave_width - 7, center), fill='#476b76', width=2)
                amplitudes = layout['waveform'].get('display_amplitudes') or layout['waveform']['amplitudes']
                inner_width = wave_width - 16
                for bar_index, amplitude in enumerate(amplitudes):
                    bar_x = wave_x + 8 + inner_width * (bar_index + 0.5) / len(amplitudes)
                    bar_height = max(2, int(round(amplitude * (_PNG_AUDIO_HEIGHT - 8) / 2))) if amplitude else 0
                    if bar_height:
                        draw.line((bar_x, center - bar_height, bar_x, center + bar_height), fill='#8ff6dd', width=_PNG_AUDIO_BAR_WIDTH)
                cursor_x = wave_x + 8 + inner_width * layout['waveform']['cursor']
                draw.line((cursor_x, wave_y + 3, cursor_x, wave_y + _PNG_AUDIO_HEIGHT - 3), fill='#ffc276', width=2)
            body_y = image_end + 10 + layout['audio_extra']
            text_area_height = layout['text_area_height']
            text_block_height = layout['text_content_height']
            text_y = body_y + max(0, (text_area_height - text_block_height) // 2)
            for line_no, line in enumerate(layout['script_lines']):
                line_width = _png_text_width(draw, line, script_font)
                text_x = x + 10 + max(0, (308 - line_width) / 2)
                _png_draw_text(draw, (text_x, text_y + line_no * _PNG_TEXT_LINE_HEIGHT), line, script_font, fill='#e5e7eb')
            if layout['excerpt']:
                notice = 'Excerpt; full text in JSON / Markdown'
                notice_width = _png_text_width(draw, notice, notice_font)
                notice_x = x + 10 + max(0, (308 - notice_width) / 2)
                _png_draw_text(draw, (notice_x, text_y + _PNG_TEXT_LINE_HEIGHT * len(layout['script_lines']) + 6), notice, notice_font, fill='#acbbcb')
        path = out_root / f'filmstrip-{page:03d}.png'
        sheet.save(path)
        paths.append(str(path))
    return paths


def _static(cards, out_root, columns, page_size, timeline_name, render_run_id, render_selection, audio=None, *, components=None, detail=False):
    components = set(components or ('output', 'text', 'audio'))
    svg_pages = _static_svg(cards, out_root, columns, page_size, timeline_name, render_run_id, render_selection, show_text='text' in components, show_output='output' in components, detail=detail)
    png_paths = _static_png(cards, out_root, columns, page_size, timeline_name, render_run_id, render_selection, audio if 'audio' in components else None, show_text='text' in components, show_output='output' in components, detail=detail)
    svg_paths = []
    for page, _width, _height, content in svg_pages:
        path = out_root / f'filmstrip-{page:03d}.svg'
        path.write_text(content, encoding='utf-8')
        svg_paths.append(str(path))
    return {'png': png_paths, 'svg': svg_paths}


def build_filmstrip_pack(*, out_root: Path, video_path: Path, snapshot: dict, options: dict) -> dict:
    index = plan_filmstrip(snapshot, options)
    # Keep the resolved component contract in the frame index itself; the
    # The static surface must not infer visibility from whether optional lanes happen to
    # be present in a legacy snapshot.
    index['components'] = list(options.get('components') or ('output', 'text', 'audio'))
    index['component_request'] = options.get('component_request')
    columns, page_size = int(options.get('columns') or 5), int(options.get('page_size') or 50)
    if not 1 <= columns <= 12 or not 1 <= page_size <= 200:
        raise ValueError('columns must be 1–12 and page_size 1–200.')
    out_root.mkdir(parents=True, exist_ok=True)
    cards = index['cards']
    _extract(video_path, cards, out_root, options.get('resolution'))
    media_record = None
    if options.get('include_media'):
        media_root = out_root / 'media'
        media_root.mkdir(parents=True, exist_ok=True)
        suffix = video_path.suffix.lower() if video_path.suffix.lower() in {'.mp4', '.mov', '.webm', '.mkv'} else '.mp4'
        destination = media_root / f'rendered-video{suffix}'
        shutil.copyfile(video_path, destination)
        digest = 'sha256:' + __import__('hashlib').sha256(destination.read_bytes()).hexdigest()
        media_record = {'path': destination.relative_to(out_root).as_posix(), 'digest': digest,
                        'bytes': destination.stat().st_size, 'verified': True, 'kind': 'rendered_video'}
        media_record['source_digest'] = snapshot.get('video_digest')
        index['media'] = media_record
        index['provenance']['media'] = media_record
    audio = index.get('audio')
    if isinstance(audio, dict) and audio.get('status') not in (None, 'not_analyzed'):
        audio_path = out_root / 'audio-analysis.json'
        audio_path.write_text(json.dumps(audio, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        audio_digest = 'sha256:' + __import__('hashlib').sha256(audio_path.read_bytes()).hexdigest()
        index['audio_sidecar'] = {'path': audio_path.relative_to(out_root).as_posix(),
                                  'analysis_identity': audio.get('analysis_identity'),
                                  'render_digest': audio.get('render_digest'),
                                  'digest': audio_digest, 'bytes': audio_path.stat().st_size,
                                  'verified': audio.get('render_digest') == snapshot.get('video_digest')}
    # Static pages honor component visibility too.  Keep the full machine
    # index intact for drill-down, but do not print hidden script/audio facts
    # into a supposedly filtered PNG/SVG page.
    display_cards = deepcopy(cards)
    if 'text' not in (options.get('components') or ('output', 'text', 'audio')):
        for card in display_cards:
            card['scripts'] = []
            card['display_scripts'] = []
            card['captions'] = []
            card['script_status'] = 'text hidden'
            card['caption_status'] = 'text hidden'
    display_audio = index.get('audio') if 'audio' in (options.get('components') or ('output', 'text', 'audio')) else None
    paths = _static(display_cards, out_root, columns, page_size, snapshot.get('timeline_name') or snapshot['timeline_id'], snapshot['render_run_id'], (snapshot.get('metadata') or {}).get('selection') or options.get('render_run') or 'latest', display_audio, components=options.get('components'), detail=bool(options.get('detail')))
    for name, filename in [('json', 'frame-index.json'), ('markdown', 'filmstrip.md')]:
        paths[name] = str(out_root / filename)
    index['request'] = {
        'range': options.get('range'),
        'at': options.get('at'),
        'density': options.get('density'),
        'resolution': options.get('resolution'),
        'effective_range': index['sampling']['range'],
    }
    index.setdefault('navigation', {})['usage'] = _navigation_usage(snapshot, options)
    if 'inputs' in (options.get('components') or ()):
        fps = Fraction(*snapshot['fps_rational'])
        start_frame, end_frame = _input_projection_bounds(snapshot, options, index)
        integrity = (snapshot.get('metadata') or {}).get('asset_integrity', {})
        index['input_projection'] = project_input_window(
            snapshot.get('input_clips') or snapshot.get('clips') or [], start_frame=start_frame,
            end_frame=end_frame, fps=fps, track_ids=options.get('track_ids') or (),
            clip_id=options.get('clip'), shot_id=options.get('shot'), asset_id=options.get('asset'),
            integrity=integrity,
        )
        attach_input_audio_waveforms(
            index['input_projection'], integrity=integrity, out_root=out_root,
        )
        shared_window = index['input_projection']['window']
        index['sampling']['shared_window'] = [
            float(Fraction(shared_window['start_frame'], 1) / fps),
            float(Fraction(shared_window['end_frame'], 1) / fps),
        ]
        _materialize_input_previews(index['input_projection'], out_root)
        _attach_input_navigation(index, index['input_projection'], track_meta=snapshot.get('tracks'))
    Path(paths['json']).write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding='utf-8')
    md = ['# Rendered filmstrip', '', f"Render: `{snapshot['render_run_id']}`", '', 'Scripts are segment-level, not word-aligned. “No script” does not assert acoustic silence.', '']
    for card in cards:
        md += [f"## {card['id']}", '', f"![{card['time_label']}]({card['image']})", ''] + [html.escape(line) + '  ' for line in _lines(card)] + ['', '```sh', card['actions']['focus_command'], '```', '']
    Path(paths['markdown']).write_text('\n'.join(md), encoding='utf-8')
    return {'frame_index': index, 'cards': cards, 'paths': paths}
