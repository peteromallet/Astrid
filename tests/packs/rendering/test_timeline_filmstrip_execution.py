import hashlib
import json
import shutil
import struct
import subprocess
import wave
from argparse import Namespace
from pathlib import Path

import pytest

from astrid.packs.rendering.executors.timeline_visualize import filmstrip_execution as execution
from astrid.packs.rendering.executors.timeline_visualize.filmstrip_cards import plan_filmstrip
from astrid.packs.rendering.executors.timeline_visualize.filmstrip_options import filmstrip_options
from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import project_input_window


def test_managed_coverage_projects_actual_overview_source_pack():
    source = plan_filmstrip(
        {
            'fps_rational': [24, 1],
            'duration_frames': 48,
            'clips': [],
            'occurrences': [],
            'scripts': [],
            'metadata': {},
        },
        filmstrip_options({}),
    )

    managed = execution._filmstrip_managed_coverage(source)

    assert managed == {
        'sampling': {
            'mode': 'interval',
            'range': {'start': 0, 'end': 48},
            'step_frames_rational': {'numerator': 12, 'denominator': 1},
            'every': 0.5,
        },
    }


def test_input_projection_filters_pinned_shot_alias_membership():
    projection = project_input_window(
        [
            {'id': 'clip-a', 'track': 'picture', 'asset': 'a', 'at': 0, 'hold': 2},
            {'id': 'clip-b', 'track': 'picture', 'asset': 'b', 'at': 2, 'hold': 2},
        ],
        start_frame=0, end_frame=120, fps=30,
        shot_id='shot-b',
        shot_groups=[
            {'shotId': 'shot-a', 'clipIds': ['clip-a'], 'name': 'Opening'},
            {'shotId': 'shot-b', 'clipIds': ['clip-b'], 'name': 'Middle'},
        ],
    )
    clips = projection['tracks'][0]['clips']
    assert [clip['clip_id'] for clip in clips] == ['clip-b']
    assert clips[0]['shot_id'] == 'shot-b'
    assert clips[0]['shot_name'] == 'Middle'


def test_input_audio_rail_is_prominent_but_remains_timing_only(tmp_path):
    from PIL import Image

    projection = {
        'window': {'fps': [30, 1], 'start_frame': 0, 'end_frame': 150},
        'tracks': [{
            'track_id': 'vo',
            'clips': [{
                'clip_id': 'vo_b01',
                'window': [0, 150],
                'source_preview': {'status': 'verified', 'media_type': 'audio'},
                'audio_signifier': {'present': True, 'basis': 'clip_placement'},
            }],
        }],
        'track_bands': [{'track_ids': ['vo'], 'label': 'voice'}],
    }
    paths = execution._render_input_projection_png(
        projection, {'timeline_name': 'Main'}, tmp_path, width=600,
    )
    with Image.open(paths[0]) as image:
        pixels = list(image.getdata())
        # The boosted rail and markers are intentionally much more visible than
        # the old one-pixel amber line, while still encoding placement timing.
        assert pixels.count((255, 192, 120)) >= 150
        assert pixels.count((255, 224, 168)) >= 30
        marker_rows = [
            y for y in range(image.height)
            if any(image.getpixel((x, y)) == (255, 224, 168) for x in range(image.width))
        ]
        # The 56px audio placement starts at y=186; marker extents are
        # balanced around its vertical midpoint (y=214), rather than being
        # anchored against the old bottom-biased rail.
        assert marker_rows and min(marker_rows) + max(marker_rows) == 2 * 214
        # The centered rail passes behind the clip label, which is protected by
        # a dark rounded chip for contrast.
        assert image.getpixel((80, 212)) == (16, 22, 29)


@pytest.mark.skipif(shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None, reason='ffmpeg required')
def test_input_audio_visualizer_uses_verified_source_amplitude(tmp_path):
    source = tmp_path / 'source.wav'
    frames = [0.8] * 500 + [0.05] * 500
    with wave.open(str(source), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(1000)
        output.writeframes(b''.join(struct.pack('<h', int(value * 32767)) for value in frames))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    projection = {
        'window': {'fps': [30, 1], 'start_frame': 0, 'end_frame': 30},
        'tracks': [{
            'track_id': 'vo',
            'clips': [{
                'clip_id': 'vo-source', 'asset_key': 'voice',
                'window': [0, 30], 'window_seconds': [[0, 1], [1, 1]],
                'source_time': [[0, 1], [1, 1]],
                'source_preview': {'status': 'verified', 'media_type': 'audio/wav'},
                'audio_signifier': {'present': True},
            }],
        }],
        'track_bands': [{'track_ids': ['vo'], 'label': 'voice'}],
    }
    execution.attach_input_audio_waveforms(
        projection,
        integrity={'voice': {
            'state': 'verified_original', 'path': str(source),
            'observed_sha256': digest,
        }},
        out_root=tmp_path,
        count=32,
    )
    signifier = projection['tracks'][0]['clips'][0]['audio_signifier']
    assert signifier['basis'] == 'source_audio_analysis'
    assert signifier['visual_encoding'] == 'amplitude_waveform'
    measured = signifier['waveform']['amplitudes']
    assert measured[0] > measured[-1] * 5
    assert signifier['analysis_path'].startswith('source-audio-analysis/')
    assert (tmp_path / signifier['analysis_path']).is_file()

    paths = execution._render_input_projection_png(
        projection, {'timeline_name': 'Main'}, tmp_path, width=600,
    )
    from PIL import Image
    with Image.open(paths[0]) as image:
        mint = (143, 246, 221)
        mint_rows = {
            y for y in range(image.height)
            if any(image.getpixel((x, y)) == mint for x in range(image.width))
        }
    assert mint_rows and min(mint_rows) < 200 < max(mint_rows)


@pytest.mark.skipif(shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None, reason='ffmpeg required')
def test_input_audio_visualizer_discovers_audio_embedded_in_verified_video(tmp_path):
    source = tmp_path / 'source.mp4'
    subprocess.run([
        'ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i',
        'color=blue:size=32x32:rate=4:duration=1', '-f', 'lavfi', '-i',
        'sine=frequency=440:sample_rate=8000:duration=1', '-c:v', 'libx264',
        '-c:a', 'aac', '-shortest', '-y', str(source),
    ], check=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    projection = {
        'window': {'fps': [4, 1], 'start_frame': 0, 'end_frame': 4},
        'tracks': [{
            'track_id': 'picture',
            'clips': [{
                'clip_id': 'picture-source', 'asset_key': 'picture',
                'window': [0, 4], 'window_seconds': [[0, 1], [1, 1]],
                'source_time': [[0, 1], [1, 1]],
                'source_preview': {'status': 'verified', 'media_type': 'video/mp4'},
            }],
        }],
        'track_bands': [{'track_ids': ['picture'], 'label': 'pictures'}],
    }
    execution.attach_input_audio_waveforms(
        projection,
        integrity={'picture': {
            'state': 'verified_original', 'path': str(source),
            'observed_sha256': digest,
        }},
        out_root=tmp_path,
        count=16,
    )
    signifier = projection['tracks'][0]['clips'][0].get('audio_signifier')
    assert signifier is not None
    assert signifier['basis'] == 'source_audio_analysis'
    assert max(signifier['waveform']['amplitudes']) > 0.1


def test_alignment_uses_decoded_eof_and_marks_excess_tail_unmapped(monkeypatch, tmp_path):
    snapshot = {
        'fps_rational': [24, 1], 'duration_frames': 72,
        'clips': [
            {'id': 'authored', 'at': 0, 'duration': 3, 'start_frame': 0, 'end_frame': 72,
             'shot_id': 'unproven', 'shot_name': 'must not reach tail'},
        ],
        'occurrences': [{'occurrence_id': 'shot-occ', 'shot_id': 'shot',
                         'shot_name': 'Shot', 'start': 0, 'end': 3,
                         'start_frame': 0, 'end_frame': 72}],
        'scripts': [{'start': 0, 'end': 3, 'text': 'line'}],
        'metadata': {},
    }
    monkeypatch.setattr(execution, '_rendered_timing', lambda video, fps: (120, 5.0))

    execution._align_snapshot_to_render(snapshot, tmp_path / 'render.mp4')

    assert snapshot['duration_frames'] == 120
    assert snapshot['metadata']['duration_basis'] == 'rendered_video'
    assert snapshot['metadata']['rendered_duration_seconds'] == 5.0
    assert snapshot['metadata']['authored_duration_seconds'] == 3.0
    tail = snapshot['metadata']['rendered_tail']
    assert tail == snapshot['unmapped_regions'][0]
    assert tail['status'] == tail['mapping_status'] == 'unmapped'
    assert (tail['start_frame'], tail['end_frame']) == (72, 120)
    tail_clip = snapshot['clips'][-1]
    assert tail_clip['render_tail'] is True
    assert tail_clip['mapping_status'] == 'unmapped'
    assert tail_clip['end_frame'] == 120
    assert 'shot_id' not in tail_clip and 'shot_name' not in tail_clip
    assert snapshot['occurrences'][0]['end_frame'] == 72


def test_alignment_clamps_short_render_without_changing_identity(monkeypatch, tmp_path):
    snapshot = {'fps_rational': [24, 1], 'duration_frames': 120,
                'clips': [{'id': 'clip', 'at': 0, 'duration': 5,
                           'start_frame': 0, 'end_frame': 120}],
                'occurrences': [], 'scripts': [], 'metadata': {}}
    monkeypatch.setattr(execution, '_rendered_timing', lambda video, fps: (72, 3.0))

    execution._align_snapshot_to_render(snapshot, tmp_path / 'render.mp4')

    assert snapshot['duration_frames'] == 72
    assert snapshot['unmapped_regions'] == []
    assert snapshot['metadata']['rendered_tail'] is None
    assert snapshot['clips'][0]['end_frame'] == 72


def test_alignment_preserves_declared_authored_clock_when_snapshot_duration_is_rendered(
    monkeypatch, tmp_path
):
    snapshot = {
        'fps_rational': [30, 1], 'duration_frames': 9000,
        'clips': [{'id': 'clip', 'start_frame': 0, 'end_frame': 8910}],
        'occurrences': [], 'scripts': [],
        'metadata': {'authored_duration_frames': 8910},
    }
    monkeypatch.setattr(execution, '_rendered_timing', lambda video, fps: (9000, 300.0))

    execution._align_snapshot_to_render(snapshot, tmp_path / 'render.mp4')

    assert snapshot['duration_frames'] == 9000
    assert snapshot['metadata']['authored_duration_frames'] == 8910
    assert snapshot['metadata']['rendered_tail']['start_frame'] == 8910


def test_managed_execution_verifies_video_before_extracting(tmp_path, monkeypatch):
    video = tmp_path / 'video'
    video.write_bytes(b'actual video')
    snapshot = dict(project_slug='demo', timeline_id='main', render_run_id='run',
                    video_digest='sha256:' + hashlib.sha256(video.read_bytes()).hexdigest(),
                    fps_rational=[24, 1])
    authority = dict(mode='filmstrip', filmstrip_snapshot=snapshot,
                     video_digest=snapshot['video_digest'])
    args = Namespace(filmstrip_authority=json.dumps(authority), project_slug='demo',
                     rendered_video=video, range_value=None, out=tmp_path / 'output')
    called = []
    def build(**kwargs):
        called.append(kwargs)
        root = kwargs['out_root']
        root.mkdir(parents=True)
        (root / 'filmstrip-001.png').write_bytes(b'png')
        (root / 'filmstrip-001.svg').write_text('<svg/>')
        (root / 'filmstrip.md').write_text('# Filmstrip')
        (root / 'frame-index.json').write_text('{}')
        return {
            'frame_index': {
                'provenance': {'fps_rational': [24, 1]},
                'coverage': {'window_seconds': [0.0, 1.0]},
                'sampling': {
                    'mode': 'interval',
                    'density': {'mode': 'every_seconds', 'value': 0.5},
                    'step_frames_rational': [12, 1],
                },
                'cards': [
                    {
                        'frame': 0,
                        'time_seconds': 0.0,
                        'time_rational': [0, 1],
                        'sample_reasons': ['interval'],
                    },
                ],
            },
            'paths': {
                'png': [str(root / 'filmstrip-001.png')],
                'svg': [str(root / 'filmstrip-001.svg')],
                'markdown': str(root / 'filmstrip.md'),
                'json': str(root / 'frame-index.json'),
            },
        }
    monkeypatch.setattr(execution, 'build_filmstrip_pack', build)
    result = execution.execute_filmstrip(args)
    manifest = json.loads(open(result['manifest_path']).read())
    assert manifest['kind'] == 'timeline_filmstrip'
    assert [o['path'] for o in manifest['outputs'] if o['is_primary']] == ['filmstrip-001.png']
    assert 'filmstrip.html' not in {o['path'] for o in manifest['outputs']}
    host_manifest = json.loads((tmp_path / 'output' / 'manifest.json').read_text())
    assert host_manifest['kind'] == 'timeline_filmstrip_result'
    assert {entry['name'] for entry in host_manifest['outputs']} == {
        'filmstrip_manifest', 'filmstrip_bundle'
    }
    assert all('content_hash' in entry and 'bytes' in entry for entry in host_manifest['outputs'])
    bundle_entry = next(entry for entry in host_manifest['outputs'] if entry['name'] == 'filmstrip_bundle')
    manifest_entry = next(entry for entry in host_manifest['outputs'] if entry['name'] == 'filmstrip_manifest')
    assert bundle_entry['path'] == 'filmstrip-bundle.zip'
    assert bundle_entry['is_primary'] is True
    assert bundle_entry['durability'] == 'durable'
    assert manifest_entry['is_primary'] is False
    assert manifest_entry['durability'] == 'temporary'
    expected_coverage = {
        'sampling': {
            'mode': 'interval',
            'range': {'start': 0, 'end': 24},
            'step_frames_rational': {'numerator': 12, 'denominator': 1},
            'every': 0.5,
            'cards': [{
                'frame': 0,
                'time_seconds': 0.0,
                'time_rational': {'numerator': 0, 'denominator': 1},
                'sample_reasons': ['interval'],
            }],
        },
    }
    for entry in host_manifest['outputs']:
        assert entry['producer'] == {'capability_id': 'rendering.timeline_visualize', 'view': 'filmstrip'}
        assert entry['provenance'] == {
            'render_run_id': 'run', 'timeline_id': 'main',
            'video_digest': snapshot['video_digest'],
        }
        regeneration = entry['regeneration']
        assert regeneration['available'] is True
        assert regeneration['capability_id'] == 'rendering.timeline_visualize'
        assert regeneration['source_refs'] == [snapshot['video_digest']]
        assert regeneration['exact_inputs']['render_run_id'] == 'run'
        assert regeneration['exact_inputs']['timeline_id'] == 'main'
        assert regeneration['exact_inputs']['video_digest'] == snapshot['video_digest']
        assert regeneration['recipe_digest'].startswith('sha256:')
        assert entry['coverage'] == expected_coverage
    assert result['identity']['render'] == {
        'render_run_id': 'run', 'timeline_id': 'main',
        'video_digest': snapshot['video_digest'],
    }
    assert result['cas']['rendered_video'] == snapshot['video_digest']
    assert result['identity']['manifest']['content_hash'] == (
        'sha256:' + hashlib.sha256(Path(result['manifest_path']).read_bytes()).hexdigest()
    )
    assert result['entrypoints'] == {
        'manifest': 'filmstrip-view/manifest.json',
        'frame_index': 'filmstrip-view/frame-index.json',
        'png': 'filmstrip-view/filmstrip-001.png',
        'svg': 'filmstrip-view/filmstrip-001.svg',
        'markdown': 'filmstrip-view/filmstrip.md',
        'bundle': 'filmstrip-bundle.zip',
    }
    assert not any(key in host_manifest for key in ('mutation', 'mutation_receipt', 'events'))
    assert called[0]['snapshot'] == snapshot
    video.write_bytes(b'changed')
    with pytest.raises(ValueError, match='digest'):
        execution.execute_filmstrip(args)
    assert len(called) == 1


def test_execution_requires_admitted_authority(tmp_path):
    with pytest.raises(ValueError, match='admission'):
        execution.execute_filmstrip(Namespace(filmstrip_authority=None))


def test_synchronized_surface_composes_output_and_input_panels(tmp_path):
    from PIL import Image

    output = tmp_path / 'filmstrip-001.png'
    inputs = tmp_path / 'input-band-001.png'
    Image.new('RGB', (400, 200), '#101827').save(output)
    Image.new('RGB', (300, 100), '#202f3d').save(inputs)

    pages = execution._compose_synchronized_surface(
        [str(output)], [inputs], pack_root=tmp_path,
    )

    assert pages == [str(output)]
    assert (tmp_path / 'rendered-filmstrip-001.png').is_file()
    with Image.open(output) as image:
        assert image.size == (400, 353)
        assert image.getpixel((200, 201)) == (11, 17, 24)


def test_synchronized_surface_anchors_samples_to_shared_time_coordinates(tmp_path):
    from PIL import Image

    output = tmp_path / 'filmstrip-001.png'
    inputs = tmp_path / 'input-band-001.png'
    Image.new('RGB', (400, 200), '#101827').save(output)
    Image.new('RGB', (1500, 20), '#202f3d').save(inputs)
    Image.new('RGB', (1200, 675), '#c0392b').save(tmp_path / 'frame-0.png')
    Image.new('RGB', (1200, 675), '#27ae60').save(tmp_path / 'frame-5.png')
    Image.new('RGB', (1200, 675), '#2980b9').save(tmp_path / 'frame-10.png')
    Image.new('RGB', (1200, 675), '#8e44ad').save(tmp_path / 'frame-15.png')

    frame_index = {
        'provenance': {'timeline_name': 'Main', 'timeline_id': 'tl', 'render_run_id': 'run', 'fps_rational': [30, 1], 'duration_frames': 600},
        'input_projection': {'window': {'start_frame': 0, 'end_frame': 600}},
        'cards': [
            {'id': 'f0', 'time_seconds': 0.0, 'time_label': '0.000s', 'image': 'frame-0.png', 'clips': []},
            {'id': 'f5', 'time_seconds': 5.0, 'time_label': '5.000s', 'image': 'frame-5.png', 'clips': []},
            {'id': 'f10', 'time_seconds': 10.0, 'time_label': '10.000s', 'image': 'frame-10.png', 'clips': []},
            {'id': 'f15', 'time_seconds': 15.0, 'time_label': '15.000s', 'image': 'frame-15.png', 'clips': []},
        ],
    }

    pages = execution._compose_synchronized_surface(
        [str(output)], [inputs], pack_root=tmp_path,
        frame_index=frame_index, options={'page_size': 50},
    )

    assert pages == [str(output)]
    with Image.open(output) as image:
        # The 5s card starts at the same x-coordinate as the 5s ruler tick:
        # 24 + 5/20 * (1476 - 24) = 387px.
        assert image.getpixel((50, 200)) == (192, 57, 43)
        assert image.getpixel((400, 200)) == (39, 174, 96)


def test_paired_surface_groups_five_samples_and_clips_input_rows(tmp_path):
    from PIL import Image

    output = tmp_path / 'filmstrip-001.png'
    inputs = tmp_path / 'input-band-001.png'
    Image.new('RGB', (400, 200), '#101827').save(output)
    Image.new('RGB', (1500, 20), '#202f3d').save(inputs)
    cards = []
    for index, seconds in enumerate(range(0, 120, 5)):
        frame = tmp_path / 'frames' / f'frame-{index:03d}.jpg'
        frame.parent.mkdir(exist_ok=True)
        Image.new('RGB', (160, 90), (index * 7 % 255, 40, 80)).save(frame)
        cards.append({'id': f'f{index}', 'time_seconds': float(seconds),
                      'time_label': f'{seconds:.3f}s',
                      'image': str(frame.relative_to(tmp_path)), 'clips': [],
                      'captions': [], 'display_scripts': []})
    frame_index = {
        'provenance': {'timeline_name': 'Main', 'timeline_id': 'tl',
                       'render_run_id': 'run', 'fps_rational': [30, 1]},
        'input_projection': {
            'window': {'start_frame': 0, 'end_frame': 3512, 'fps': [30, 1]},
            'tracks': [{'track_id': 'picture', 'clips': [
                {'clip_id': 'pic', 'window': [0, 3512],
                 'source_preview': {'status': 'unavailable'}}]}],
            'track_bands': [{'track_ids': ['picture'], 'label': 'pictures'}],
        },
        'cards': cards, 'components': ['output', 'inputs', 'text', 'audio'],
    }

    pages = execution._compose_synchronized_surface(
        [str(output)], [inputs], pack_root=tmp_path,
        frame_index=frame_index, options={'page_size': 50, 'columns': 5, 'page_size_explicit': False},
    )

    assert len(pages) == 5
    assert pages[0] == str(output)
    surface = frame_index['static_surface']
    assert surface['mode'] == 'paired_rows'
    assert surface['page_size'] == 5
    assert surface['page_count'] == 5
    assert surface['row_count'] == 5
    assert [row['output_card_count'] for row in surface['rows']] == [5, 5, 5, 5, 4]
    assert surface['rows'][0]['time_range'] == [0.0, 25.0]
    assert surface['rows'][-1]['time_range'] == [100.0, 117.06666666666666]
    assert all((tmp_path / f'filmstrip-{page:03d}.svg').is_file() for page in range(1, 4))


def test_paired_surface_page_size_respects_smaller_request_and_sparse_card_fills_row(tmp_path):
    from PIL import Image

    output = tmp_path / 'filmstrip-001.png'
    inputs = tmp_path / 'input-band-001.png'
    Image.new('RGB', (400, 200), '#101827').save(output)
    Image.new('RGB', (1500, 20), '#202f3d').save(inputs)
    frame = tmp_path / 'frame.jpg'
    Image.new('RGB', (160, 90), '#c0392b').save(frame)
    frame_index = {
        'provenance': {'timeline_name': 'Main', 'timeline_id': 'tl', 'render_run_id': 'run', 'fps_rational': [30, 1]},
        'input_projection': {
            'window': {'start_frame': 0, 'end_frame': 150, 'fps': [30, 1]},
            'tracks': [{'track_id': 'picture', 'clips': [{'clip_id': 'pic', 'window': [0, 150]}]}],
            'track_bands': [{'track_ids': ['picture'], 'label': 'pictures'}],
        },
        'cards': [{'id': 'f0', 'time_seconds': 0.0, 'time_label': '0.000s',
                   'image': 'frame.jpg', 'clips': [], 'captions': [], 'display_scripts': []}],
        'components': ['output', 'inputs', 'text', 'audio'],
    }
    pages = execution._compose_synchronized_surface(
        [str(output)], [inputs], pack_root=tmp_path, frame_index=frame_index,
        options={'page_size': 3, 'columns': 5},
    )
    assert pages == [str(output)]
    surface = frame_index['static_surface']
    assert surface['page_size'] == 3
    assert surface['page_count'] == 1
    assert surface['rows'][0]['time_range'] == [0.0, 5.0]
    # The single red thumbnail is centered in a full-width card, well beyond
    # the first fifth of the row that the old fixed-slot layout used.
    with Image.open(output) as image:
        red_x = [x for y in range(image.height) for x in range(image.width)
                 if (lambda rgb: rgb[0] > 140 and rgb[1] < 100 and rgb[2] < 120)(image.getpixel((x, y)))]
        assert red_x and min(red_x) > 500


def test_paired_surface_centers_spoken_text_in_card_body(tmp_path, monkeypatch):
    from PIL import Image
    from astrid.packs.rendering.executors.timeline_visualize import filmstrip_cards

    output = tmp_path / 'filmstrip-001.png'
    inputs = tmp_path / 'input-band-001.png'
    Image.new('RGB', (400, 200), '#101827').save(output)
    Image.new('RGB', (1500, 20), '#202f3d').save(inputs)
    frame = tmp_path / 'frame.jpg'
    Image.new('RGB', (160, 90), '#c0392b').save(frame)
    frame_index = {
        'provenance': {'timeline_name': 'Main', 'timeline_id': 'tl', 'render_run_id': 'run', 'fps_rational': [30, 1]},
        'input_projection': {
            'window': {'start_frame': 0, 'end_frame': 150, 'fps': [30, 1]},
            'tracks': [{'track_id': 'picture', 'clips': [{'clip_id': 'pic', 'window': [0, 150]}]}],
            'track_bands': [{'track_ids': ['picture'], 'label': 'pictures'}],
        },
        'cards': [{'id': 'f0', 'time_seconds': 0.0, 'time_label': '0.000s',
                   'image': 'frame.jpg', 'clips': [], 'captions': [{'text': 'A centered spoken line'}],
                   'display_scripts': []}],
        'components': ['output', 'inputs', 'text'],
    }
    calls = []
    original = filmstrip_cards._png_draw_text

    def spy(draw, xy, text, *args, **kwargs):
        if str(text).startswith('“'):
            calls.append((xy, str(text)))
        return original(draw, xy, text, *args, **kwargs)

    monkeypatch.setattr(filmstrip_cards, '_png_draw_text', spy)
    execution._compose_synchronized_surface(
        [str(output)], [inputs], pack_root=tmp_path, frame_index=frame_index,
        options={'page_size': 3, 'columns': 5},
    )
    assert len(calls) == 1
    # One card owns the full 0–5s row. Its caption is centered in the wide
    # body rather than starting at the card's left padding or bottom edge.
    (x, y), _ = calls[0]
    assert x > 500
    assert 320 <= y <= 370


def test_paired_surface_omits_empty_lanes_but_preserves_canonical_track_metadata(tmp_path):
    from PIL import Image

    output = tmp_path / 'filmstrip-001.png'
    inputs = tmp_path / 'input-band-001.png'
    Image.new('RGB', (400, 200), '#101827').save(output)
    Image.new('RGB', (1500, 20), '#202f3d').save(inputs)
    frame_index = {
        'provenance': {'timeline_name': 'Main', 'timeline_id': 'tl', 'render_run_id': 'run', 'fps_rational': [30, 1]},
        'input_projection': {
            'window': {'start_frame': 0, 'end_frame': 150, 'fps': [30, 1]},
            'tracks': [
                {'track_id': 'picture', 'clips': [{'clip_id': 'pic', 'window': [0, 150]}]},
                {'track_id': 'terminal_background', 'clips': []},
            ],
            'track_bands': [{'track_ids': ['picture', 'terminal_background'], 'label': 'tracks'}],
        },
        'cards': [{'id': 'f0', 'time_seconds': 0.0, 'time_label': '0.000s', 'image': '', 'clips': []}],
        'components': ['output', 'inputs'],
    }
    execution._compose_synchronized_surface(
        [str(output)], [inputs], pack_root=tmp_path, frame_index=frame_index,
        options={'page_size': 3, 'columns': 5},
    )
    surface = frame_index['static_surface']
    assert surface['canonical_input_tracks'] == ['picture', 'terminal_background']
    assert surface['rows'][0]['input_tracks'] == ['picture']
    assert 'terminal_background' not in surface['rows'][0]['input_tracks']


def test_paired_navigation_describes_pages_and_drill_down():
    from astrid.packs.rendering.executors.timeline_visualize.filmstrip_cards import _navigation_usage

    navigation = _navigation_usage(
        {'project_slug': 'demo', 'timeline_id': 'main', 'render_run_id': 'run'},
        {'components': ['output', 'text', 'audio', 'inputs'], 'columns': 5, 'page_size': 50, 'page_size_explicit': False},
    )
    assert any('one row' in note for note in navigation['notes'])
    assert any('numbered PNG/SVG pages' in note for note in navigation['keyboard'])
    assert '--page-size' not in navigation['commands']['rerun_base']


@pytest.mark.skipif(shutil.which('ffmpeg') is None or shutil.which('ffprobe') is None, reason='ffmpeg required')
def test_execution_delivers_audio_sidecar_optional_media_and_reuses_cache(tmp_path, monkeypatch):
    video = tmp_path / 'video.mp4'
    subprocess.run([
        'ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=blue:size=64x64:rate=4:duration=1',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=8000:duration=1',
        '-c:v', 'libx264', '-c:a', 'aac', '-shortest', '-y', str(video)
    ], check=True)
    digest = 'sha256:' + hashlib.sha256(video.read_bytes()).hexdigest()
    snapshot = dict(project_slug='demo', timeline_id='main', timeline_name='Main', render_run_id='run',
                    video_digest=digest, fps_rational=[4, 1], duration_frames=4, clips=[], tracks=[], scripts=[])
    authority = dict(mode='filmstrip', filmstrip_snapshot=snapshot, video_digest=digest)
    calls = []
    original = execution.analyze_audio
    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)
    monkeypatch.setattr(execution, 'analyze_audio', counted)

    def args(out):
        return Namespace(filmstrip_authority=json.dumps(authority), project_slug='demo', rendered_video=video,
                         range_value=None, out=out, include_media=True)

    first = execution.execute_filmstrip(args(tmp_path / 'one'))
    second = execution.execute_filmstrip(args(tmp_path / 'two'))
    assert len(calls) == 1
    for result in (first, second):
        index = json.loads((Path(result['outputs']['pack_root']) / 'frame-index.json').read_text())
        assert index['schema'] == 'astrid.filmstrip.v2'
        assert 'audio' not in index
        assert index['audio_sidecar']['verified'] is True
        assert index['audio_sidecar']['digest'].startswith('sha256:')
        assert index['media']['source_digest'] == digest
        manifest = json.loads(open(result['manifest_path']).read())
        paths = {entry['path'] for entry in manifest['outputs']}
        assert 'audio-analysis.json' in paths and 'media/rendered-video.mp4' in paths
        host_manifest = json.loads((Path(result['run_root']) / 'manifest.json').read_text())
        assert any(entry['name'] == 'filmstrip_bundle' for entry in host_manifest['outputs'])
