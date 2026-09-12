import hashlib
import json
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from astrid.packs.rendering.executors.timeline_visualize import filmstrip_execution as execution


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
                    video_digest='sha256:' + hashlib.sha256(video.read_bytes()).hexdigest())
    authority = dict(mode='filmstrip', filmstrip_snapshot=snapshot,
                     video_digest=snapshot['video_digest'])
    args = Namespace(filmstrip_authority=json.dumps(authority), project_slug='demo',
                     rendered_video=video, range_value=None, out=tmp_path / 'output')
    called = []
    def build(**kwargs):
        called.append(kwargs)
        root = kwargs['out_root']
        root.mkdir(parents=True)
        (root / 'filmstrip.html').write_text('<html>Verified frame sheet</html>')
        return {'paths': {'png': [], 'html': str(root / 'filmstrip.html')}}
    monkeypatch.setattr(execution, 'build_filmstrip_pack', build)
    result = execution.execute_filmstrip(args)
    manifest = json.loads(open(result['manifest_path']).read())
    assert manifest['kind'] == 'timeline_filmstrip'
    assert [o['path'] for o in manifest['outputs'] if o['is_primary']] == ['filmstrip.html']
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
        'html': 'filmstrip-view/filmstrip.html',
        'frame_index': 'filmstrip-view/frame-index.json',
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
        assert index['audio']['status'] == 'ok'
        assert index['audio_sidecar']['verified'] is True
        assert index['audio_sidecar']['digest'].startswith('sha256:')
        assert index['media']['source_digest'] == digest
        manifest = json.loads(open(result['manifest_path']).read())
        paths = {entry['path'] for entry in manifest['outputs']}
        assert 'audio-analysis.json' in paths and 'media/rendered-video.mp4' in paths
        host_manifest = json.loads((Path(result['run_root']) / 'manifest.json').read_text())
        assert any(entry['name'] == 'filmstrip_bundle' for entry in host_manifest['outputs'])
