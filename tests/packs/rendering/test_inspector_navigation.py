from copy import deepcopy
import shlex

import pytest

from astrid.packs.rendering.executors.timeline_visualize.inspector_navigation import (
    build_inspector_navigation, build_range_target, target_for_frame)


def snapshot():
    return dict(project_slug='a project', timeline_id='timeline', render_run_id='old-render',
        video_digest='sha256:' + 'a'*64, fps_rational=[24,1], duration_frames=144,
        tracks=[{'id':'picture','kind':'visual','label':'Main picture'},
                {'id':'voice','kind':'audio','label':'Voice'}, {'id':'empty','kind':'audio','label':'Empty lane'}],
        clips=[{'id':'a','track':'picture','kind':'visual','at':0,'hold':1,'shot_id':'shot','occurrence_id':'first'},
               {'id':'audio','track':'voice','kind':'audio','at':0,'hold':2},
               {'id':'unsampled','track':'picture','kind':'visual','at':2.01,'hold':.01},
               {'id':'a','track':'picture','kind':'visual','at':4,'hold':1,'shot_id':'shot','occurrence_id':'second'}],
        occurrences=[{'shot_id':'shot','occurrence_id':'first','start_frame':0,'end_frame':24},
                     {'shot_id':'shot','occurrence_id':'second','start_frame':96,'end_frame':120}])


def cards():
    return [{'id':f'frame-{n:09d}','frame':n} for n in [0,12,96,119]]


def test_shared_frame_clip_graph_preserves_audio_and_empty_tracks():
    data=build_inspector_navigation(snapshot(),cards())
    assert data['tracks'][-1]['label']=='Empty lane'
    assert data['tracks'][-1]['metadata']==snapshot()['tracks'][-1]
    assert data['tracks'][-1]['clip_targets']==[]
    frame=data['frames'][0]
    assert {data['targets'][t]['clip_id'] for t in frame['active_clip_targets']}=={'a','audio'}
    assert all(data['targets'][t]['start_frame']<=frame['frame']<data['targets'][t]['end_frame'] for t in frame['active_clip_targets'])


def test_unsampled_clip_has_no_unrelated_frame_and_exact_pinned_command():
    data=build_inspector_navigation(snapshot(),cards())
    clip=next(c for c in data['clips'] if c['id']=='unsampled')
    assert (clip['start_frame'],clip['end_frame'])==(48,49)
    assert clip['frame_target'] is None
    command=shlex.split(clip['actions']['focus_command'])
    assert command[command.index('--render-run')+1]=='old-render'
    assert command[command.index('--clip')+1]=='unsampled'
    assert command[command.index('--project')+1]=='a project'


def test_repeated_shots_and_clips_keep_occurrence_targets():
    data=build_inspector_navigation(snapshot(),cards())
    assert len({s['target'] for s in data['shots']})==2
    repeated=[c for c in data['clips'] if c['id']=='a']
    assert repeated[0]['target']!=repeated[1]['target']
    assert data['targets'][repeated[1]['frame_target']]['frame']==96
    assert '--range 4.0..5.0' in data['shots'][1]['actions']['focus_command']


def test_stable_target_scoped_to_immutable_render_and_digest():
    original=snapshot()
    assert target_for_frame(original,12)==target_for_frame(deepcopy(original),12)
    for field in ['render_run_id','video_digest','timeline_id','project_slug']:
        changed=deepcopy(original);changed[field]+='new'
        assert target_for_frame(changed,12)!=target_for_frame(original,12)


def test_range_target_roundtrip_and_bounds():
    data=build_range_target(snapshot(),12,24)
    assert data['start_frame']==12 and data['end_frame']==24
    assert '--range 0.5..1.0' in data['actions']['focus_command']
    with pytest.raises(ValueError):build_range_target(snapshot(),24,24)
    with pytest.raises(ValueError):target_for_frame(snapshot(),144)


def test_navigation_does_not_claim_legacy_focus_compatibility():
    data=build_inspector_navigation(snapshot(),cards())
    assert data['legacy_from_view_compatible'] is False
    assert all('--from-view' not in t['actions']['focus_command'] for t in data['targets'].values())
