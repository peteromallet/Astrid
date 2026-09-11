from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from astrid.packs.rendering.executors.timeline_visualize import filmstrip_cards
from astrid.packs.rendering.executors.timeline_visualize.filmstrip_cards import plan_filmstrip, build_filmstrip_pack
from astrid.packs.rendering.executors.timeline_visualize.filmstrip_options import filmstrip_options


def snapshot(**changes):
    data = dict(project_slug='demo', timeline_id='main', timeline_name='A story', render_run_id='run-exact', video_digest='sha256:video', fps_rational=[24, 1], duration_frames=96, clips=[dict(id='a', kind='video', asset='one', at=0, duration=2, shot_id='beat'), dict(id='b', kind='video', asset='two', at=2, duration=2)], scripts=[dict(start=0, end=1, text='Hello'), dict(start=.5, end=1.5, text='Overlap')])
    data.update(changes)
    return data


def test_integer_fractional_fps_and_half_open_window():
    index = plan_filmstrip(snapshot(fps_rational=[30000, 1001], duration_frames=120, clips=[]), {'range': [.5, 2], 'every': .5})
    assert [c['frame'] for c in index['cards']] == [29, 44, 59]
    for c in index['cards']:
        assert Fraction(*c['time_rational']) == Fraction(c['frame'] * 1001, 30000)


def test_cut_neighbors_are_preserved_between_sparse_intervals():
    cards = plan_filmstrip(snapshot(), {'every': 3})['cards']
    frames = {c['frame']: c for c in cards}
    assert {47, 48, 95}.issubset(frames)
    assert frames[47]['clips'][0]['id'] == 'a'
    assert frames[48]['clips'][0]['id'] == 'b'
    assert 'before_cut' in frames[47]['sample_reasons']


def test_scripts_are_overlapping_segments_and_gaps_explicit():
    cards = {c['frame']: c for c in plan_filmstrip(snapshot(), {})['cards']}
    assert [s['text'] for s in cards[12]['scripts']] == ['Hello', 'Overlap']
    assert cards[24]['scripts'][0]['text'] == 'Overlap'
    assert cards[48]['scripts'] == []
    assert cards[48]['script_status'] == 'no script'


def test_filters_and_bounds_are_enforced():
    cards = plan_filmstrip(snapshot(), {'clip': 'b'})['cards']
    assert all(c['time_seconds'] >= 2 for c in cards)
    with pytest.raises(ValueError, match='No clips match'):
        plan_filmstrip(snapshot(), {'shot': 'unknown'})
    with pytest.raises(ValueError, match='exceeds'):
        plan_filmstrip(snapshot(), {'every_frames': 1, 'max_frames': 10})
    with pytest.raises(ValueError, match='positive'):
        plan_filmstrip(snapshot(), {'every': 0})
    with pytest.raises(ValueError, match='positive integer'):
        plan_filmstrip(snapshot(), {'every_frames': 1.5})


def test_v1_04_records_range_density_and_resolution_separately():
    options = filmstrip_options({'range': '1..3', 'every': 0.25, 'resolution': '320x180'})
    index = plan_filmstrip(snapshot(duration_frames=120), options)

    assert options['request'] == {
        'range': [1.0, 3.0], 'at': None,
        'density': {'mode': 'every_seconds', 'value': 0.25},
        'resolution': [320, 180],
    }
    assert index['sampling']['requested_range'] == [1.0, 3.0]
    assert index['sampling']['requested_at'] is None
    assert index['sampling']['density'] == options['density']
    assert index['sampling']['resolution'] == [320, 180]
    assert index['sampling']['effective_range'] == [1.0, 3.0]


def test_v1_04_rejects_conflicting_range_and_density_values():
    with pytest.raises(ValueError, match='range or at'):
        filmstrip_options({'range': '1..2', 'at': 1.5})
    with pytest.raises(ValueError, match='every seconds or every_frames'):
        filmstrip_options({'every': 0.5, 'every_frames': 12})
    with pytest.raises(ValueError, match='resolution'):
        filmstrip_options({'resolution': '320'})


def test_shots_sample_authored_midpoint():
    cards = plan_filmstrip(snapshot(), {'sample': 'shots'})['cards']
    assert [(c['frame'], c['sample_reasons']) for c in cards] == [(24, ['shot_midpoint'])]


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='ffmpeg required')
def test_pack_uses_rendered_frames_and_escapes_html(tmp_path):
    video = tmp_path / 'render.mp4'
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=red:size=160x90:rate=24:duration=4', '-c:v', 'libx264', '-y', str(video)], check=True)
    snap = snapshot(scripts=[dict(start=0, end=4, text='</script><script>alert("x")</script>')], metadata={'selection': 'explicit_render'})
    result = build_filmstrip_pack(out_root=tmp_path / 'pack', video_path=video, snapshot=snap, options={'every': 2})
    page = Path(result['paths']['html']).read_text()
    assert '</script><script>alert' not in page
    assert '\\u003c/script\\u003e' in page
    assert 'data:image/jpeg;base64,' in page
    assert 'https://' not in page
    index = json.loads(Path(result['paths']['json']).read_text())
    assert index['provenance']['render_run_id'] == 'run-exact'
    assert '--render-run run-exact' in index['cards'][0]['actions']['focus_command']
    from PIL import Image
    with Image.open(tmp_path / 'pack' / index['cards'][0]['image']) as image:
        r, g, b = image.getpixel((20, 20))
        assert r > 200 and g < 30 and b < 30
    assert Path(result['paths']['png'][0]).exists()
    svg = Path(result['paths']['svg'][0]).read_text()
    assert '&lt;/script&gt;' in svg
    assert 'Render run-exact · selection: explicit_render' in svg


def test_float_arithmetic_noise_does_not_move_cut_boundary():
    clean = snapshot(clips=[dict(id='a', kind='video', at=0, duration=3)])
    noisy = snapshot(clips=[dict(id='a', kind='video', at=0, duration=3.000000000000005)])
    clean_cards = plan_filmstrip(clean, {'sample': 'cuts'})['cards']
    noisy_cards = plan_filmstrip(noisy, {'sample': 'cuts'})['cards']
    assert [c['frame'] for c in noisy_cards] == [c['frame'] for c in clean_cards] == [0, 71, 72]
    assert noisy_cards[-1]['clips'] == []


@pytest.mark.parametrize('fps', [24, 30000 / 1001])
def test_clip_labels_and_cuts_use_canonical_renderer_frames(fps):
    from astrid.core.timeline.duration import clip_start_frame, clip_end_frame
    clip = dict(id='offset', kind='video', at=1.01, **{'from': 0, 'to': 1.02, 'speed': 1.3})
    rational = Fraction(str(fps)).limit_denominator(100000)
    start, end = clip_start_frame(clip, fps), clip_end_frame(clip, fps)
    cards = plan_filmstrip(snapshot(clips=[clip], fps_rational=[rational.numerator, rational.denominator]), {'sample': 'cuts'})['cards']
    by_frame = {c['frame']: c for c in cards}
    assert {start - 1, start, end - 1, end} == set(by_frame)
    assert not by_frame[start - 1]['clips']
    assert by_frame[start]['clips'] == [clip]
    assert by_frame[end - 1]['clips'] == [clip]
    assert not by_frame[end]['clips']


def test_filtered_sampling_jumps_to_short_clip_in_long_movie():
    clip = dict(id='late', kind='video', at=10**10, duration=1)
    cards = plan_filmstrip(snapshot(clips=[clip], duration_frames=24 * (10**10 + 2)), {'clip': 'late', 'every_frames': 1})['cards']
    assert len(cards) == 24
    assert cards[0]['frame'] == 24 * 10**10


def test_static_captions_are_bounded_and_full_script_preserved():
    from astrid.packs.rendering.executors.timeline_visualize.filmstrip_cards import _static_lines
    text = 'Long script. ' * 100000
    card = plan_filmstrip(snapshot(scripts=[dict(start=0, end=4, text=text)]), {})['cards'][0]
    lines = _static_lines(card)
    assert len(lines) <= 16
    assert lines[-1] == '[Excerpt; full text in HTML / JSON]'
    assert card['scripts'][0]['text'] == text


def test_repeated_shot_occurrences_have_separate_midpoints():
    clips = [dict(id='first', kind='video', at=0, duration=1, shot_id='repeat', occurrence_id='one'),
             dict(id='second', kind='video', at=3, duration=1, shot_id='repeat', occurrence_id='two')]
    occurrences = [dict(occurrence_id='one', shot_id='repeat', start_frame=0, end_frame=24),
                   dict(occurrence_id='two', shot_id='repeat', start_frame=72, end_frame=96)]
    cards = plan_filmstrip(snapshot(clips=clips, occurrences=occurrences), {'sample': 'shots'})['cards']
    assert [card['frame'] for card in cards] == [12, 84]
    assert [card['clips'][0]['occurrence_id'] for card in cards] == ['one', 'two']


def test_default_is_bounded_full_duration_overview_with_tail_evidence():
    snap = snapshot(
        duration_frames=240,
        clips=[
            dict(id='picture', kind='video', at=0, duration=8),
            dict(id='tail', kind='render_tail', at=8, duration=2, render_tail=True),
        ],
        metadata={'rendered_tail': {'start_frame': 192, 'end_frame': 240, 'status': 'unmapped'}},
    )

    index = plan_filmstrip(snap, {})
    frames = {card['frame']: card for card in index['cards']}

    assert index['sampling']['mode'] == 'overview'
    assert index['sampling']['overview'] is True
    assert len(index['cards']) <= 200
    assert {0, 191, 192, 239}.issubset(frames)
    assert 'overview_first_frame' in frames[0]['sample_reasons']
    assert 'overview_last_frame' in frames[239]['sample_reasons']
    assert 'rendered_tail_transition' in frames[191]['sample_reasons']
    assert 'rendered_tail_eof' in frames[239]['sample_reasons']
    assert index['coverage']['full_duration'] is True
    assert index['coverage']['window_seconds'] == [0.0, 10.0]
    assert index['coverage']['page_count'] == 4
    assert index['coverage']['selected_frame_ids'] == [card['id'] for card in index['cards']]


def test_hundreds_of_cuts_use_bounded_adaptive_overview_and_honest_coverage():
    clips = [dict(id=f'cut-{i:04d}', kind='video', at=i, duration=1) for i in range(400)]
    index = plan_filmstrip(snapshot(duration_frames=400 * 24, clips=clips), {})
    coverage = index['coverage']

    assert len(index['cards']) == 200
    assert index['cards'][0]['frame'] == 0
    assert index['cards'][-1]['frame'] == 9599
    assert coverage['full_duration'] is True
    assert coverage['selected_frame_count'] == 200
    assert coverage['boundary_count'] >= 800
    assert coverage['unselected_boundary_count'] > 0
    assert coverage['all_boundaries_sampled'] is False
    assert 'every fast-cut boundary is sampled' in coverage['not_promised']
    boundary_frames = {entry['frame'] for entry in index['boundary_index']['entries']}
    assert {0, 23, 24, 9599}.issubset(boundary_frames)
    assert all('selected' in entry for entry in index['boundary_index']['entries'])


def test_extract_uses_ffmpeg9_supported_filter_and_frame_mode(tmp_path, monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen['argv'] = argv
        frames = tmp_path / 'pack' / 'frames'
        frames.mkdir(parents=True, exist_ok=True)
        (frames / 'sample-000000.jpg').write_bytes(b'jpeg')
        return subprocess.CompletedProcess(argv, 0, stdout='', stderr='')

    monkeypatch.setattr(filmstrip_cards.subprocess, 'run', fake_run)
    filmstrip_cards._extract(
        tmp_path / 'render.mp4',
        [{'frame': 12, 'image': 'frames/frame-000000012.jpg'}],
        tmp_path / 'pack',
    )

    argv = seen['argv']
    assert '-vf' in argv
    assert argv[argv.index('-vf') + 1] == "select='eq(n,12)',scale=480:-2"
    assert argv[argv.index('-fps_mode:v') + 1] == 'passthrough'
    assert '-filter_script:v' not in argv
    assert '-vsync' not in argv
