import hashlib
import json
from argparse import Namespace

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
