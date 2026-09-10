from copy import deepcopy
from types import SimpleNamespace
import pytest
from astrid.sdk.contracts import DomainResult, ErrorObject
from astrid.sdk.shot_grouping import group_timeline_clips
from astrid.core.timeline.expand_shots import expand_shot_clips
from astrid.packs.shots.cli import build_parser


class Runtime:
    def __init__(self):
        self.parent = {'timeline_id': 'parent', 'config_version': 4, 'config': {
            'theme': 'banodoco-default', 'output': {'file': 'test.mp4', 'fps': 30, 'resolution': '1920x1080'},
            'tracks': [{'id': 'picture', 'kind': 'visual', 'label': 'Picture'}, {'id': 'vo', 'kind': 'audio', 'label': 'VO'}],
            'clips': [
                {'id': 'pic', 'clipType': 'media', 'asset': 'v', 'at': 10., 'from': 2., 'to': 10., 'speed': 2., 'track': 'picture'},
                {'id': 'voice', 'clipType': 'media', 'asset': 'a', 'at': 10.5, 'from': 0., 'to': 2., 'track': 'vo'},
                {'id': 'next', 'clipType': 'media', 'asset': 'v', 'at': 15., 'from': 0., 'to': 4., 'track': 'picture'},
            ]}, 'registry': {'assets': {'v': {'type': 'video', 'media_id': 'v'}, 'a': {'type': 'audio', 'media_id': 'a'}}}}
        self.original = deepcopy(self.parent)
        self.children = {}; self.records = {}; self.items = {}; self.calls = []; self.fail_child_once = False
        self.timelines = SimpleNamespace(show=self.show, create=self.create_child, save=self.save)
        self.shots = SimpleNamespace(show=self.show_shot, create=self.create_shot, add_item=self.add_item)

    def show(self, project, ref):
        return DomainResult.success(deepcopy(self.parent if ref in {'main', 'parent'} else self.children[ref]))

    def show_shot(self, project, sid):
        return DomainResult.success(deepcopy(self.records[sid]))

    def create_shot(self, **kw):
        self.calls.append('shot')
        sid = kw['shot']['shot_id']
        self.records.setdefault(sid, {'name': kw['name'], 'metadata': kw['metadata']})
        return DomainResult.success(self.records[sid])

    def create_child(self, **kw):
        self.calls.append('child')
        if self.fail_child_once:
            self.fail_child_once = False
            return DomainResult.failure(ErrorObject('unavailable', 'temporary', {}))
        self.children.setdefault(kw['timeline_id'], deepcopy(kw))
        return DomainResult.success(self.children[kw['timeline_id']])

    def add_item(self, project, sid, **kw):
        self.calls.append('item')
        self.items.setdefault(kw['idempotency_key'], kw)
        return DomainResult.success(kw)

    def save(self, project, ref, **kw):
        self.calls.append('save')
        assert ref == 'parent'
        assert self.parent['config_version'] == kw['expected_version']
        self.parent.update(config=deepcopy(kw['config']), registry=deepcopy(kw['registry']), config_version=kw['expected_version'] + 1)
        return DomainResult.success(deepcopy(self.parent))

    def group(self, **kw):
        args = dict(shots=self.shots, timelines=self.timelines, project='project', timeline='main', clip_ids=['voice','pic'], name='A shot', expected_version=4, hold=5, idempotency_key='stable')
        args.update(kw)
        return group_timeline_clips(**args)


def test_group_preserves_order_source_bounds_speed_audio_and_registry():
    r = Runtime(); result = r.group(); assert result.ok, result
    expanded, registry = expand_shot_clips(r.parent['config'], r.parent['registry'], load_timeline=lambda ref: (r.children[ref]['config'], r.children[ref]['registry']))
    assert [{k: v for k, v in clip.items() if k not in {'shot_id', 'shot_occurrence_id', 'shot_name'}} for clip in expanded['clips']] == r.original['config']['clips']
    assert expanded['clips'][0]['shot_occurrence_id'].startswith('shot-occ-0000-')
    assert registry == r.original['registry']
    assert len(r.items) == 2 and len(r.records) == 1
    assert r.calls[-1] == 'save'
    replay = r.group(); assert replay.ok and replay.data['replayed']
    assert r.parent['config_version'] == 5


def test_partial_failure_retries_without_duplicate_resources():
    r = Runtime(); r.fail_child_once = True
    result = r.group(); assert not result.ok and result.error.details['stage'] == 'create_child'
    assert r.parent == r.original
    result = r.group(); assert result.ok
    assert len(r.records) == len(r.children) == 1
    assert len(r.items) == 2


@pytest.mark.parametrize('override', [
    {'expected_version': 3}, {'hold': 1}, {'hold': float('nan')},
    {'clip_ids':['missing']}, {'clip_ids':['pic','pic']},
    {'clip_ids':['pic','next']},
])
def test_rejects_bad_selection_or_window_before_mutations(override):
    r = Runtime(); result = r.group(**override)
    assert not result.ok and not r.calls
    assert r.parent == r.original


def test_replay_key_cannot_change_request():
    r = Runtime(); assert r.group().ok
    result = r.group(name='Different')
    assert not result.ok and result.error.code == 'idempotency_conflict'


def test_group_cli_dispatches_single_sdk_operation(capsys):
    calls=[]
    client=SimpleNamespace(shots=SimpleNamespace(group=lambda *a, **kw: calls.append((a,kw)) or DomainResult.success({})))
    args=build_parser(client).parse_args(['group','main','--project','demo','--clip','pic','--clip','vo','--name','Intro','--expected-version','4','--hold','5','--idempotency-key','stable'])
    assert args.handler(args)==0
    assert calls == [(('demo','main'),dict(clip_ids=['pic','vo'],name='Intro',expected_version=4,hold=5.,idempotency_key='stable'))]


def test_missing_required_tracks_fail_before_mutations():
    r = Runtime()
    for clip in r.parent['config']['clips']:
        clip.pop('track')
    result = r.group()
    assert not result.ok and result.error.code == 'validation_error' and not r.calls


def test_edited_partial_child_is_not_silently_attached():
    r = Runtime()
    original_add = r.shots.add_item
    r.shots.add_item = lambda *a, **kw: DomainResult.failure(ErrorObject('unavailable', 'temporary', {}))
    assert not r.group().ok
    next(iter(r.children.values()))['config']['clips'][0]['from'] = 3.
    r.shots.add_item = original_add
    result = r.group()
    assert not result.ok and result.error.details['stage'] == 'verify_child'
    assert r.parent == r.original


def test_schema_invalid_parent_returns_typed_failure():
    r = Runtime(); r.parent['config']['tracks'][0].pop('label')
    result = r.group()
    assert not result.ok and result.error.code == 'validation_error' and not r.calls
