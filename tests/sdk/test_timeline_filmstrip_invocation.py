from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.sdk import invocation
from astrid.sdk.exceptions import CapabilityValidationError

DIGEST = 'sha256:' + 'b' * 64


def test_filmstrip_preflight_supports_intersecting_filters(monkeypatch):
    received = {}
    def prepare(inputs, *, project, client):
        received.update(inputs)
        assert project == 'p'
        assert client == 'runtime'
        return {'mode': 'filmstrip'}
    monkeypatch.setattr('astrid.sdk.timeline_filmstrip.prepare_filmstrip', prepare)
    result = invocation._validate_timeline_visualize_inputs(
        {'view': 'filmstrip', 'shot': 'shot1', 'clip': 'clip1', 'asset': 'a'},
        project='p', _client='runtime')
    assert result['mode'] == 'filmstrip'
    assert received['shot'] == 'shot1'
    assert received['clip'] == 'clip1'


def test_caller_cannot_supply_authority():
    with pytest.raises(CapabilityValidationError, match='host-owned'):
        invocation._validate_timeline_visualize_inputs(
            {'view': 'filmstrip', 'filmstrip_authority': '{}'}, project='p')


def test_managed_video_is_in_task_authorization_manifest():
    recorded = {}
    class ReachedAdmission(Exception): pass
    def create(**kwargs):
        recorded.update(kwargs)
        raise ReachedAdmission
    client = SimpleNamespace(tasks=SimpleNamespace(create=create))
    authority = {'mode': 'filmstrip', 'video_object_id': DIGEST}
    with pytest.raises(ReachedAdmission):
        invocation._kernel_invoke(SimpleNamespace(id='rendering.timeline_visualize'),
            kind='executor', project='p', outputs={},
            inputs={'rendered_video': {'object_id': DIGEST, 'digest': DIGEST}},
            idempotency_context=authority, _client=client)
    assert recorded['input_manifest'] == [DIGEST]
    assert recorded['spec']['authority_context'] == authority


def test_mismatched_video_identity_rejected_before_admission():
    with pytest.raises(CapabilityValidationError, match='identity mismatch'):
        invocation._kernel_invoke(SimpleNamespace(id='rendering.timeline_visualize'),
            kind='executor', project='p', outputs={},
            inputs={'rendered_video': {'object_id': DIGEST, 'digest': 'sha256:' + 'c' * 64}},
            idempotency_context={'mode': 'filmstrip', 'video_object_id': DIGEST})


def test_bundle_rehydration_preserves_html_and_pages(tmp_path):
    import hashlib
    import io
    import json
    import shutil
    import zipfile
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('manifest.json', json.dumps({'kind': 'timeline_filmstrip', 'outputs': [
            {'path': name, 'content_hash': 'sha256:' + hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
            for name, content in [('filmstrip.html', b'<html>review</html>'), ('filmstrip-001.png', b'png'), ('frame-index.json', b'{}')]
        ]}))
        bundle.writestr('filmstrip.html', '<html>review</html>')
        bundle.writestr('filmstrip-001.png', b'png')
        bundle.writestr('frame-index.json', '{}')
    data = archive.getvalue()
    raw = {'outputs': {'artifacts': [{'name': 'filmstrip_bundle', 'digest': 'sha256:' + hashlib.sha256(data).hexdigest(), 'size': len(data)}]}}
    client = SimpleNamespace(media=SimpleNamespace(read_bytes=lambda _: data))
    manifest = invocation._materialize_filmstrip_outputs(raw, client)
    try:
        result = invocation._invocation_outputs(raw, manifest_path=manifest, capability_id='rendering.timeline_visualize')
        assert result['html'].endswith('filmstrip.html')
        assert len(result['pages']) == 1
    finally:
        shutil.rmtree(raw['outputs']['pack_root'])


def test_bundle_traversal_rejected():
    import hashlib
    import io
    import zipfile
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('../escape', 'bad')
    data = archive.getvalue()
    raw = {'outputs': {'artifacts': [{'name': 'filmstrip_bundle', 'digest': 'sha256:' + hashlib.sha256(data).hexdigest(), 'size': len(data)}]}}
    client = SimpleNamespace(media=SimpleNamespace(read_bytes=lambda _: data))
    with pytest.raises(invocation.CapabilityInvocationError, match='unsafe'):
        invocation._materialize_filmstrip_outputs(raw, client)


def test_bundle_rehydration_exposes_verified_audio_and_media(tmp_path):
    import hashlib
    import io
    import json
    import shutil
    import zipfile

    members = {
        'filmstrip.html': b'<html>review</html>',
        'filmstrip-001.png': b'png',
        'audio-analysis.json': b'{"status":"ok"}\n',
        'media/rendered-video.mp4': b'video',
    }
    index = json.dumps({'media': {'path': 'media/rendered-video.mp4'}, 'audio_sidecar': {'path': 'audio-analysis.json'}}).encode()
    members['frame-index.json'] = index
    manifest_members = [
        {'path': name, 'content_hash': 'sha256:' + hashlib.sha256(content).hexdigest(), 'bytes': len(content)}
        for name, content in members.items()
    ]
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('manifest.json', json.dumps({'kind': 'timeline_filmstrip', 'outputs': manifest_members}))
        for name, content in members.items():
            bundle.writestr(name, content)
    data = archive.getvalue()
    raw = {'outputs': {'artifacts': [{'name': 'filmstrip_bundle', 'digest': 'sha256:' + hashlib.sha256(data).hexdigest(), 'size': len(data)}]}}
    client = SimpleNamespace(media=SimpleNamespace(read_bytes=lambda _: data))
    manifest = invocation._materialize_filmstrip_outputs(raw, client)
    try:
        assert raw['outputs']['audio_analysis'].endswith('audio-analysis.json')
        assert raw['outputs']['media'].endswith('rendered-video.mp4')
        assert Path(raw['outputs']['audio_analysis']).read_bytes() == members['audio-analysis.json']
    finally:
        shutil.rmtree(Path(manifest).parent)


def test_structure_rejects_filmstrip_controls():
    with pytest.raises(CapabilityValidationError, match='controls require'):
        invocation._validate_timeline_visualize_inputs({'view': 'structure', 'every': 0.5}, project='p')


def test_invalid_sampling_rejected_before_runtime():
    with pytest.raises(CapabilityValidationError, match='positive'):
        invocation._validate_timeline_visualize_inputs({'view': 'filmstrip', 'every_frames': 0}, project='p')
