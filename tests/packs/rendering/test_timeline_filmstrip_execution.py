import hashlib
import json
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from astrid.packs.rendering.executors.timeline_visualize import filmstrip_execution as execution


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
