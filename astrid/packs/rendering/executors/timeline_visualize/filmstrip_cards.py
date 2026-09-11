"""Deterministic contact sheets sampled from the exact rendered video."""
from __future__ import annotations

import base64
import html
import json
import math
import shutil
import subprocess
import textwrap
from fractions import Fraction
from pathlib import Path

from astrid.core.timeline.duration import clip_end_frame, clip_start_frame

from .inspector_navigation import build_inspector_navigation
from .inspector_viewer import render_inspector


def _q(value):
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


OVERVIEW_MAX_CARDS = 200


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
    is_full_overview = (mode == 'interval' and not filtered and options.get('range') is None
                        and options.get('at') is None and options.get('every_frames') is None
                        and options.get('every') in (None, 0.5))
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
            if visual and mode != 'shots':
                for frame, reason in ((start - 1, 'before_cut'), (start, 'after_cut'), (end - 1, 'before_cut'), (end, 'after_cut')):
                    add(frame, reason)
            if visual and mode not in ('cuts', 'shots'):
                add(max(first, start), 'clip_first')
            occurrence_key = clip.get('occurrence_id') or clip.get('shot_id')
            if not snapshot.get('occurrences') and occurrence_key and occurrence_key not in seen_shots:
                shot_spans = [spans[id(c)] for c in selected if (c.get('occurrence_id') or c.get('shot_id')) == occurrence_key]
                midpoint = (min(a for a, b in shot_spans) + max(b for a, b in shot_spans)) / 2
                add(math.floor(midpoint), 'shot_midpoint')
                seen_shots.add(occurrence_key)
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
        scripts = [s for s in snapshot.get('scripts', []) if _q(s['start']) <= time < _q(s['end'])]
        target = f"frame-{frame:09d}"
        cards.append({'id': target, 'frame': frame, 'time_seconds': float(time), 'time_rational': [time.numerator, time.denominator], 'time_label': f'{float(time):.3f}s', 'sample_reasons': sorted(why), 'clips': active, 'scripts': scripts, 'script_status': 'script segment (not word-aligned)' if scripts else 'no script', 'shot_ids': sorted({str(c['shot_id']) for c in active if c.get('shot_id')}), 'image': f'frames/{target}.jpg', 'actions': {'target': '#' + target}})
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
            'audio': navigation['audio'],
            'boundary_index': boundary_index,
            'coverage': coverage,
            'sampling': {'mode': 'overview' if is_full_overview else mode, 'overview': is_full_overview,
                         'range': [float(lo), float(hi)], 'effective_range': [float(lo), float(hi)],
                         'requested_range': options.get('range'), 'requested_at': options.get('at'),
                         'density': options.get('density'), 'resolution': options.get('resolution'),
                         'step_frames_rational': [step.numerator, step.denominator], 'options': options},
            'cards': cards}


def _lines(card):
    shots = ', '.join(dict.fromkeys(str(c.get('shot_name') or c.get('shot_id')) for c in card['clips'] if c.get('shot_id') or c.get('shot_name')))
    clips = ', '.join(str(c.get('id')) for c in card['clips']) or 'no active clip'
    return [f"{card['time_label']} · frame {card['frame']}", shots or 'No shot label', clips, card['script_status']] + [str(s.get('text', '')) for s in card['scripts']]


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


def _static_lines(card):
    """Bound bitmap text; complete captions remain in HTML/JSON/Markdown."""
    lines = []
    truncated = False
    source_lines = _lines(card)
    captions = source_lines[:2] + (source_lines[4:] or ['No script'])
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
        lines = lines[:15] + ['[Excerpt; full text in HTML / JSON]']
    return lines


def _static(cards, out_root, columns, page_size, timeline_name, render_run_id, render_selection):
    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.truetype('DejaVuSans.ttf', 13) if Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf').exists() else ImageFont.load_default(size=13)
    paths = {'png': [], 'svg': []}
    for page, offset in enumerate(range(0, len(cards), page_size), 1):
        group = cards[offset:offset + page_size]
        wrapped = [_static_lines(c) for c in group]
        heights = [max(260 + 18 * len(wrapped[i]) for i in range(row, min(row + columns, len(group)))) for row in range(0, len(group), columns)]
        width, height = columns * 344 + 24, sum(heights) + 88
        if width * height > 64_000_000:
            raise ValueError('Static page exceeds 64 million pixels; reduce --page-size.')
        sheet = Image.new('RGB', (width, height), '#111827')
        draw = ImageDraw.Draw(sheet)
        title = f'{timeline_name} · page {page} · rendered frames'
        provenance = f'Render {render_run_id} · selection: {render_selection}'
        draw.text((16, 8), title, font=font, fill='white')
        draw.text((16, 27), provenance, font=font, fill='#acbbcb')
        disclaimer = 'Authored script segments, not word-aligned. No script does not imply silence.'
        draw.text((16, 47), disclaimer, font=font, fill='#acbbcb')
        svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#111827"/><text x="16" y="28" fill="white">{html.escape(title)}</text><text x="16" y="44" fill="#acbbcb" font-family="sans-serif" font-size="13">{html.escape(provenance)}</text><text x="16" y="62" fill="#acbbcb" font-family="sans-serif" font-size="13">{html.escape(disclaimer)}</text>']
        y = 72
        for i, card in enumerate(group):
            x = 16 + (i % columns) * 344
            if i and i % columns == 0:
                y += heights[i // columns - 1]
            with Image.open(out_root / card['image']) as source:
                source.thumbnail((328, 216))
                sheet.paste(source, (x, y))
            data = base64.b64encode((out_root / card['image']).read_bytes()).decode()
            svg.append(f'<image x="{x}" y="{y}" width="328" height="216" preserveAspectRatio="xMinYMin meet" href="data:image/jpeg;base64,{data}"/>')
            for j, line in enumerate(wrapped[i]):
                ty = y + 224 + j * 18
                draw.text((x, ty), line, font=font, fill='#e5e7eb')
                svg.append(f'<text x="{x}" y="{ty + 13}" fill="#e5e7eb" font-family="sans-serif" font-size="13">{html.escape(line)}</text>')
        for suffix in ('png', 'svg'):
            path = out_root / f'filmstrip-{page:03d}.{suffix}'
            if suffix == 'png':
                sheet.save(path)
            else:
                path.write_text(''.join(svg) + '</svg>', encoding='utf-8')
            paths[suffix].append(str(path))
    return paths


def build_filmstrip_pack(*, out_root: Path, video_path: Path, snapshot: dict, options: dict) -> dict:
    index = plan_filmstrip(snapshot, options)
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
    paths = _static(cards, out_root, columns, page_size, snapshot.get('timeline_name') or snapshot['timeline_id'], snapshot['render_run_id'], (snapshot.get('metadata') or {}).get('selection') or options.get('render_run') or 'latest')
    for name, filename in [('json', 'frame-index.json'), ('html', 'filmstrip.html'), ('markdown', 'filmstrip.md')]:
        paths[name] = str(out_root / filename)
    index['request'] = {
        'range': options.get('range'),
        'at': options.get('at'),
        'density': options.get('density'),
        'resolution': options.get('resolution'),
        'effective_range': index['sampling']['range'],
    }
    Path(paths['json']).write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding='utf-8')
    md = ['# Rendered filmstrip', '', f"Render: `{snapshot['render_run_id']}`", '', 'Scripts are segment-level, not word-aligned. “No script” does not assert acoustic silence.', '']
    for card in cards:
        md += [f"## {card['id']}", '', f"![{card['time_label']}]({card['image']})", ''] + [html.escape(line) + '  ' for line in _lines(card)] + ['', '```sh', card['actions']['focus_command'], '```', '']
    Path(paths['markdown']).write_text('\n'.join(md), encoding='utf-8')
    embedded = dict(index, cards=[dict(c, image='data:image/jpeg;base64,' + base64.b64encode((out_root / c['image']).read_bytes()).decode()) for c in cards])
    Path(paths['html']).write_text(render_inspector(embedded, columns=columns), encoding='utf-8')
    return {'frame_index': index, 'cards': cards, 'paths': paths}
