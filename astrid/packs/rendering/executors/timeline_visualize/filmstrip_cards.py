"""Deterministic contact sheets sampled from the exact rendered video."""
from __future__ import annotations

import base64
from fractions import Fraction
import html
import json
import math
from pathlib import Path
import subprocess
import textwrap

from astrid.core.timeline.duration import clip_start_frame, clip_end_frame
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
    if mode == 'interval':
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
    return {'navigation': navigation, 'schema': 'astrid.filmstrip.v1', 'provenance': {k: snapshot.get(k) for k in ('project_slug', 'timeline_id', 'timeline_name', 'render_run_id', 'video_digest', 'fps_rational', 'duration_frames', 'metadata')}, 'sampling': {'mode': mode, 'range': [float(lo), float(hi)], 'step_frames_rational': [step.numerator, step.denominator], 'options': options}, 'cards': cards}


def _lines(card):
    shots = ', '.join(dict.fromkeys(str(c.get('shot_name') or c.get('shot_id')) for c in card['clips'] if c.get('shot_id') or c.get('shot_name')))
    clips = ', '.join(str(c.get('id')) for c in card['clips']) or 'no active clip'
    return [f"{card['time_label']} · frame {card['frame']}", shots or 'No shot label', clips, card['script_status']] + [str(s.get('text', '')) for s in card['scripts']]


def _extract(video_path, cards, out_root):
    frames = out_root / 'frames'
    frames.mkdir(parents=True, exist_ok=True)
    expression = '+'.join(f'eq(n,{c["frame"]})' for c in cards)
    filter_path = out_root / 'frame-selection.txt'
    filter_path.write_text(f"select='{expression}',scale=480:-2", encoding='utf-8')
    result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(video_path), '-filter_script:v', str(filter_path), '-vsync', '0', '-q:v', '3', '-y', str(frames / 'sample-%06d.jpg')], capture_output=True, text=True)
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
    _extract(video_path, cards, out_root)
    paths = _static(cards, out_root, columns, page_size, snapshot.get('timeline_name') or snapshot['timeline_id'], snapshot['render_run_id'], (snapshot.get('metadata') or {}).get('selection') or options.get('render_run') or 'latest')
    for name, filename in [('json', 'frame-index.json'), ('html', 'filmstrip.html'), ('markdown', 'filmstrip.md')]:
        paths[name] = str(out_root / filename)
    Path(paths['json']).write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding='utf-8')
    md = ['# Rendered filmstrip', '', f"Render: `{snapshot['render_run_id']}`", '', 'Scripts are segment-level, not word-aligned. “No script” does not assert acoustic silence.', '']
    for card in cards:
        md += [f"## {card['id']}", '', f"![{card['time_label']}]({card['image']})", ''] + [html.escape(line) + '  ' for line in _lines(card)] + ['', '```sh', card['actions']['focus_command'], '```', '']
    Path(paths['markdown']).write_text('\n'.join(md), encoding='utf-8')
    embedded = dict(index, cards=[dict(c, image='data:image/jpeg;base64,' + base64.b64encode((out_root / c['image']).read_bytes()).decode()) for c in cards])
    Path(paths['html']).write_text(render_inspector(embedded, columns=columns), encoding='utf-8')
    return {'frame_index': index, 'cards': cards, 'paths': paths}
