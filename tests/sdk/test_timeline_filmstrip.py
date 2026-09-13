import hashlib
from copy import deepcopy

import pytest

from astrid.sdk.timeline_filmstrip import build_filmstrip_snapshot, prepare_filmstrip
from astrid.sdk.exceptions import CapabilityValidationError

TEXT = b'Take the blue pill.'
DIGEST = 'sha256:' + hashlib.sha256(TEXT).hexdigest()
VIDEO = 'sha256:' + 'a' * 64
DIRECT_RENDER_RUN = '084ba36177a5400f9c4e844444931d25'
DIRECT_RENDER_TASK = '36e4f00dae80429b8f48630f702ea816'
DIRECT_TIMELINE = 'c9c685ea84fe4f3c880d55e9e28b8f02'


def envelope():
    return {'authority_context': {'timeline_id': 'tl', 'timeline_slug': 'cut', 'config_version': 1,
        'expansion': {'children': [], 'shots': [{'shot_id': 'sh', 'name': 'Blue', 'text_bindings': [
            {'binding_id': 'binding', 'head': 1, 'media_id': DIGEST, 'content_hash': DIGEST,
             'byte_size': len(TEXT), 'kind': 'voiceover_script'}]}]}},
        'inputs': {'review_context': {'shots': [{'shot_id': 'sh', 'at': 0, 'hold': 3}]},
            'timeline_snapshot': {'config': {'theme_overrides': {'visual': {'canvas': {'fps': 24}}},
                'tracks': [{'id': 'picture', 'kind': 'visual'}, {'id': 'vo', 'kind': 'audio'}],
                'clips': [{'id': 'picture', 'track': 'picture', 'at': 0, 'from': 70, 'to': 73},
                          {'id': 'voice', 'track': 'vo', 'at': 1, 'from': 0, 'to': 1}]}}}}


class FakeClient:
    def __init__(self):
        self.current_version = 1
        self.current_head = 1
        self.raw = TEXT
        self.owned = True
        self.read_binding = False

    def get_object(self, object_id): return {'data': self.raw}
    def get_project(self, project): return {'id': 'p', 'metadata': {'default_timeline_id': 'tl'}}
    def list_timelines(self, project, **kwargs): return [[{'timeline_id': 'tl', 'slug': 'cut'}], None]
    def list_project_runs(self, project, **kwargs): return [[self.get_run('run')], None]
    def get_run(self, ref): return {'id': 'run', 'project_id': 'p', 'capability': 'rendering.render', 'status': 'succeeded', 'task_ids': ['task']}
    def get_task(self, ref): return {'state': 'succeeded', 'capability_id': 'rendering.render', 'spec': {'spec': envelope()}, 'result': {'outputs': [{'name': 'video', 'digest': VIDEO}]}}
    def get_timeline(self, ref): return {'config_version': self.current_version}
    def get_project_shot_text_binding(self, project, binding):
        self.read_binding = True
        return {'head': self.current_head, 'content_hash': DIGEST}
    def list_project_objects(self, project, **kwargs): return [[{'object_id': VIDEO}] if self.owned else [], None]


class DirectRenderClient(FakeClient):
    def get_run(self, ref):
        assert ref == DIRECT_RENDER_RUN
        return {'id': DIRECT_RENDER_RUN, 'project_id': 'p', 'capability': 'rendering.render',
            'status': 'succeeded', 'task_ids': [DIRECT_RENDER_TASK]}

    def get_task(self, ref):
        assert ref == DIRECT_RENDER_TASK
        frozen = envelope()
        authority = frozen.pop('authority_context')
        authority.update({
            'project_id': 'p', 'project_slug': 'p', 'timeline_id': DIRECT_TIMELINE,
            'timeline_ulid': DIRECT_TIMELINE, 'head_event_id': '1',
            'head_hash': 'head', 'config_hash': 'config',
            'registry_hash': 'registry', 'materialized_registry_hash': 'registry',
        })
        frozen['inputs']['timeline_authority'] = authority
        frozen['inputs']['timeline_ref'] = DIRECT_TIMELINE
        frozen['timeline_snapshot'] = frozen['inputs'].pop('timeline_snapshot')
        return {'task_id': DIRECT_RENDER_TASK, 'state': 'succeeded',
            'capability_id': 'rendering.render', 'spec': {'spec': frozen},
            'result': {'outputs': [{'name': 'video', 'digest': VIDEO}]}}

    def list_timelines(self, project, **kwargs):
        return [[{'timeline_id': DIRECT_TIMELINE, 'slug': 'cut'}], None]


def test_exact_old_render_uses_frozen_script_without_current_binding_reads():
    client = FakeClient(); client.current_version = 9; client.current_head = 7
    value = envelope()
    value['authority_context']['expansion']['occurrences'] = [
        {'shot_occurrence_id': 'shot-occ-0000-sh', 'shot_id': 'sh', 'at': 0, 'hold': 3}
    ]
    client.get_task = lambda ref: {'state': 'succeeded', 'capability_id': 'rendering.render', 'spec': {'spec': value}, 'result': {'outputs': [{'name': 'video', 'digest': VIDEO}]}}
    result = prepare_filmstrip({'render_run': 'run'}, project='p', client=client)
    snapshot = result['filmstrip_snapshot']
    assert snapshot['duration_frames'] == 72
    assert snapshot['scripts'][0]['head'] == 1
    assert snapshot['scripts'][0]['text'] == TEXT.decode()
    assert snapshot['scripts'][0]['timing_basis'] == 'shot_script'
    assert (snapshot['scripts'][0]['start'], snapshot['scripts'][0]['end']) == (0, 3)
    assert not client.read_binding


def test_direct_render_uses_frozen_inputs_authority_and_exact_run():
    result = prepare_filmstrip(
        {'render_run': DIRECT_RENDER_RUN, 'timeline_ref': DIRECT_TIMELINE},
        project='p', client=DirectRenderClient(),
    )

    assert result['render_run_id'] == DIRECT_RENDER_RUN
    assert result['timeline_id'] == DIRECT_TIMELINE


def test_identical_legacy_duplicates_remain_compatible():
    client = DirectRenderClient()
    original = client.get_task

    def get_task(ref):
        task = original(ref)
        frozen = task['spec']['spec']
        frozen['authority_context'] = deepcopy(frozen['inputs']['timeline_authority'])
        frozen['inputs']['timeline_snapshot'] = deepcopy(frozen['timeline_snapshot'])
        return task

    client.get_task = get_task
    result = prepare_filmstrip(
        {'render_run': DIRECT_RENDER_RUN, 'timeline_ref': DIRECT_TIMELINE},
        project='p', client=client,
    )

    assert result['render_run_id'] == DIRECT_RENDER_RUN


@pytest.mark.parametrize('mutation, message', [
    (lambda value: value.__setitem__('authority_context', dict(
        value['inputs']['timeline_authority'], timeline_slug='other')),
     'authority sources disagree'),
    (lambda value: value.__setitem__('authority_context', dict(
        value['inputs']['timeline_authority'], project_id='other')),
     'authority sources disagree'),
    (lambda value: value.__setitem__('authority_context', dict(
        value['inputs']['timeline_authority'], head_hash='other')),
     'authority sources disagree'),
    (lambda value: value['inputs'].__setitem__('timeline_snapshot', dict(
        value['timeline_snapshot'], config={'conflicting': True})),
     'timeline snapshots disagree'),
])
def test_conflicting_duplicate_frozen_sources_are_rejected(mutation, message):
    client = DirectRenderClient()
    original = client.get_task

    def get_task(ref):
        task = original(ref)
        mutation(task['spec']['spec'])
        return task

    client.get_task = get_task
    with pytest.raises(CapabilityValidationError, match=message):
        prepare_filmstrip(
            {'render_run': DIRECT_RENDER_RUN, 'timeline_ref': DIRECT_TIMELINE},
            project='p', client=client,
        )


@pytest.mark.parametrize('mutation, message', [
    (lambda value: value['inputs'].__setitem__('timeline_authority', 'malformed'), 'malformed'),
    (lambda value: value['inputs']['timeline_authority'].__setitem__('timeline_id', 'other'), 'No successful render'),
])
def test_direct_render_refuses_malformed_or_mismatched_authority(mutation, message):
    client = DirectRenderClient()
    original = client.get_task

    def get_task(ref):
        task = original(ref)
        mutation(task['spec']['spec'])
        return task

    client.get_task = get_task
    with pytest.raises(CapabilityValidationError, match=message):
        prepare_filmstrip(
            {'render_run': DIRECT_RENDER_RUN, 'timeline_ref': DIRECT_TIMELINE},
            project='p', client=client,
        )


def test_filmstrip_exposes_spoken_text_only_not_generation_prompts():
    value = envelope()
    value['authority_context']['expansion']['occurrences'] = [
        {'shot_occurrence_id': 'shot-occ-0000-sh', 'shot_id': 'sh', 'at': 0, 'hold': 3}
    ]
    bindings = value['authority_context']['expansion']['shots'][0]['text_bindings']
    bindings.extend([
        {'binding_id': 'positive', 'head': 1, 'media_id': DIGEST,
         'content_hash': DIGEST, 'byte_size': len(TEXT), 'kind': 'prompt', 'slot': 'positive'},
        {'binding_id': 'negative', 'head': 1, 'media_id': DIGEST,
         'content_hash': DIGEST, 'byte_size': len(TEXT), 'kind': 'prompt', 'slot': 'negative'},
        {'binding_id': 'unmarked-transcript', 'head': 1, 'media_id': DIGEST,
         'content_hash': DIGEST, 'byte_size': len(TEXT), 'kind': 'transcript'},
        {'binding_id': 'spoken-transcript', 'head': 1, 'media_id': DIGEST,
         'content_hash': DIGEST, 'byte_size': len(TEXT), 'kind': 'transcript', 'spoken': True},
    ])
    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    assert [script['kind'] for script in result['scripts']] == ['voiceover_script', 'transcript']
    assert [script['binding_id'] for script in result['scripts']] == ['binding', 'spoken-transcript']


def test_shotless_verified_speech_is_available_without_shot_identity():
    value = envelope()
    value['inputs']['speech_annotations'] = [{
        'id': 'speech-line', 'start': 0, 'end': 1,
        'text': 'Shotless spoken line', 'source_type': 'verified_speech',
    }]
    value['inputs']['speech_occurrences'] = [{
        'id': 'speech-occurrence', 'from': 0, 'to': 1, 'placement': 10,
    }]

    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    phrases = result['audio']['speech']['phrases']

    assert len(phrases) == 1
    assert phrases[0]['canonical_text'] == 'Shotless spoken line'
    assert phrases[0]['status'] == 'projected'
    assert phrases[0]['occurrence_id'] == 'speech-occurrence'
    assert 'shot_id' not in phrases[0]
    assert phrases[0]['render_interval']['start'] == [10, 1]
    assert phrases[0]['render_interval']['end'] == [11, 1]


def test_speech_annotation_allowlist_excludes_prompt_and_unmarked_transcript():
    value = envelope()
    value['inputs']['speech_annotations'] = [
        {'id': 'prompt', 'start': 0, 'end': 1, 'text': 'PROMPT_TRAP', 'source_type': 'generation_prompt'},
        {'id': 'unmarked', 'start': 0, 'end': 1, 'text': 'UNMARKED_TRAP', 'source_type': 'transcript'},
        {'id': 'spoken', 'start': 0, 'end': 1, 'text': 'Verified speech', 'source_type': 'verified_speech'},
    ]
    value['inputs']['speech_occurrences'] = [{'id': 'speech-occurrence', 'from': 0, 'to': 1, 'placement': 2}]

    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    texts = [phrase['canonical_text'] for phrase in result['audio']['speech']['phrases']]

    assert texts == ['Verified speech']


def test_shotless_speech_without_explicit_render_occurrence_does_not_guess_timing():
    value = envelope()
    value['inputs']['speech_annotations'] = [{
        'id': 'source-only', 'start': 4, 'end': 5, 'text': 'Source-only line',
        'source_type': 'verified_speech',
    }]
    value['inputs']['speech_occurrences'] = []

    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)

    assert result['audio']['speech']['status'] == 'no_occurrences'
    assert result['audio']['speech']['phrases'] == []


@pytest.mark.parametrize('field', ['current_version', 'current_head'])
def test_default_refuses_stale_timeline_or_script(field):
    client = FakeClient(); setattr(client, field, 2)
    with pytest.raises(CapabilityValidationError, match='stale'):
        prepare_filmstrip({}, project='p', client=client)


def test_refuses_changed_script_bytes():
    client = FakeClient(); client.raw = b'wrong'
    with pytest.raises(CapabilityValidationError, match='bytes'):
        prepare_filmstrip({'render_run': 'run'}, project='p', client=client)


def test_missing_placement_does_not_guess_script_from_clip_name():
    value = envelope(); del value['inputs']['review_context']
    value['authority_context']['expansion']['occurrences'] = []
    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    assert result['scripts'] == []
    assert not result['metadata']['script_mapping_available']


def test_flattened_image_clip_uses_admission_occurrence_identity():
    value = envelope()
    authority = value['authority_context']
    authority['expansion']['occurrences'] = [{
        'shot_occurrence_id': 'shot-occ-0000-sh', 'shot_id': 'sh',
        'name': 'Blue', 'at': 0, 'hold': 3,
        'timeline_document_id': 'child', 'source_index': 0,
    }]
    config = value['inputs']['timeline_snapshot']['config']
    config['clips'][0].update(
        clipType='image', shot_id='sh', shot_name='forged child name',
        shot_occurrence_id='shot-occ-0000-sh',
    )
    # The sidecar is the source of truth for the name/script; no timing join
    # or filename/clip-type inference is needed for this flattened payload.
    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    assert result['metadata']['script_mapping_available']
    assert result['scripts'][0]['occurrence_id'] == 'shot-occ-0000-sh'
    assert result['clips'][0]['shot_name'] == 'Blue'
    assert result['clips'][0]['shot_id'] == 'sh'


def test_rejects_foreign_output_and_arbitrary_path():
    client = FakeClient(); client.owned = False
    with pytest.raises(CapabilityValidationError, match='owned'):
        prepare_filmstrip({'render_run': 'run'}, project='p', client=client)
    with pytest.raises(CapabilityValidationError, match='managed'):
        prepare_filmstrip({'rendered_video': '/tmp/video.mp4'}, project='p', client=client)


def test_repeated_shots_keep_distinct_occurrences_and_canonical_duration():
    value = envelope()
    value['authority_context']['expansion']['occurrences'] = [
        {'shot_occurrence_id': 'one', 'shot_id': 'sh', 'at': 0, 'hold': 3},
        {'shot_occurrence_id': 'two', 'shot_id': 'sh', 'at': 4.01, 'hold': 1.01},
    ]
    value['inputs']['timeline_snapshot']['config']['clips'].append(
        {'id': 'repeat', 'track': 'picture', 'at': 4.01, 'hold': 1.01,
         'shot_occurrence_id': 'two'})
    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    assert len({s['occurrence_id'] for s in result['scripts']}) == 2
    assert result['clips'][-1]['occurrence_id'] == result['scripts'][-1]['occurrence_id']
    assert result['clips'][-1]['start_frame'] == 96
    assert result['duration_frames'] == 120  # rounded start + rounded duration, not ceil(5.02*24)


def test_authored_review_context_never_infers_shot_labels():
    value = envelope()
    value['inputs']['timeline_snapshot']['config']['clips'][0].update(
        shot_id='forged', shot_name='Authored-only label'
    )
    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    assert result['occurrences'] == []
    assert result['scripts'] == []
    assert not any(key in result['clips'][0] for key in ('shot_id', 'shot_name', 'occurrence_id', 'occurrence_ids'))


def test_legacy_output_fps_hint_is_not_treated_as_render_evidence():
    value = envelope()
    config = value['inputs']['timeline_snapshot']['config']
    del config['theme_overrides']
    config['output'] = {'fps': 30}
    with pytest.raises(CapabilityValidationError, match='frame rate'):
        build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)


def test_tracks_are_frozen_including_empty_lanes():
    value = envelope()
    tracks = value['inputs']['timeline_snapshot']['config']['tracks']
    tracks.append({'id': 'empty', 'kind': 'audio', 'label': 'Unused soundtrack'})
    result = build_filmstrip_snapshot(value, client=FakeClient(), project='p', run_id='run', video_digest=VIDEO)
    assert result['tracks'][-1] == tracks[-1]
    tracks[-1]['label'] = 'Changed after freezing'
    assert result['tracks'][-1]['label'] == 'Unused soundtrack'
