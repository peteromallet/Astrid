from __future__ import annotations

from fractions import Fraction

import pytest

from astrid.sdk.timeline_editing import (
    TimelineEditError,
    add_shot,
    add_track,
    align,
    duplicate,
    fit_duration,
    frame_time,
    grid,
    place_media,
    quantize_interval,
    quantize_time,
    remove,
    reorder_layers,
    replace_media,
    retime_with_ripple,
    sequence,
    source_to_timeline_time,
    timeline_to_source_time,
)


def _candidate():
    return {"shots": [], "timeline": {"tracks": [], "opaque": {"keep": True}}}


def test_helpers_build_duplicate_and_edit_independent_shots():
    candidate = _candidate()
    shot = add_shot(candidate, name="A")
    track = add_track(shot, name="Pictures")
    place_media(shot, "asset-a", track=track, start=0, end=0.1)
    copied = duplicate(shot, remap_prefix="shot")
    assert copied["id"] != shot["id"]
    assert copied["timeline"]["clips"][0]["asset"] == "asset-a"
    replace_media(copied, copied["timeline"]["clips"][0]["id"], "asset-b")
    assert shot["timeline"]["clips"][0]["asset"] == "asset-a"
    assert copied["timeline"]["clips"][0]["asset"] == "asset-b"
    assert candidate["timeline"]["opaque"] == {"keep": True}


def test_sequence_grid_and_explicit_duration_behaviour():
    candidate = _candidate()
    track = add_track(candidate)
    clips = [place_media(candidate, f"a-{i}", track=track, start=99, end=100) for i in range(3)]
    sequence(clips, start=0, durations=[0.1, 0.1, 0.1])
    actual = [(c["at"], c["to"]) for c in clips]
    expected = [(0, 0.1), (0.1, 0.2), (0.2, 0.3)]
    assert all(abs(a - b) < 1e-9 for pair_a, pair_b in zip(actual, expected) for a, b in zip(pair_a, pair_b))
    assert len(grid(2, 2)) == 4
    assert fit_duration(candidate) == pytest.approx(0.3)
    reorder_layers(candidate, [track["id"]])


def test_time_and_alignment_helpers_are_explicit():
    assert frame_time(3, 30) == Fraction(1, 10)
    assert quantize_time(0.1, 30) == 3
    clip = {"id": "c", "at": 0, "to": 1}
    align([clip], [2], edge="center")
    assert clip["at"] == 1.5 and clip["to"] == 2.5
    with pytest.raises(TimelineEditError):
        quantize_time(0.1, 0)
    with pytest.raises(TimelineEditError):
        remove(_candidate(), "missing", kind="shot")


def test_source_timeline_conversion_is_exact_and_rate_aware():
    assert source_to_timeline_time(1.5, source_start=1, timeline_start=2, speed=2) == Fraction(9, 4)
    assert timeline_to_source_time(Fraction(9, 4), source_start=1, timeline_start=2, speed=2) == Fraction(3, 2)
    with pytest.raises(TimelineEditError):
        source_to_timeline_time(1, speed=0)


def test_quantize_interval_reports_rounding_and_rejects_collapsed_ranges():
    result = quantize_interval(0.1, 0.2, 30)
    assert result["start_frame"] == 3
    assert result["end_frame"] == 6
    assert result["applied_start"] == Fraction(1, 10)
    assert result["rounded"] is False
    with pytest.raises(TimelineEditError, match="collapsed"):
        quantize_interval(0.01, 0.02, 24)


def test_ripple_is_track_scoped_and_never_moves_audio():
    candidate = _candidate()
    picture = add_track(candidate, kind="visual", track_id="picture")
    audio = add_track(candidate, kind="audio", track_id="music")
    first = place_media(candidate, "a", track=picture, start=0, end=1, clip_id="first")
    second = place_media(candidate, "b", track=picture, start=1, end=2, clip_id="second")
    music = place_media(candidate, "m", track=audio, start=0, end=2, clip_id="music")
    candidate["timeline"]["duration"] = 2

    retime_with_ripple(candidate, first["id"], end=1.5, parent_duration="extend")
    assert (first["at"], first["to"]) == (0, 1.5)
    assert (second["at"], second["to"]) == (1.5, 2.5)
    assert (music["at"], music["to"]) == (0, 2)
    assert candidate["timeline"]["duration"] == 2.5

    with pytest.raises(TimelineEditError, match="audio/voice/music"):
        retime_with_ripple(candidate, music["id"], end=3, parent_duration="extend")
    with pytest.raises(TimelineEditError, match="parent duration"):
        retime_with_ripple(candidate, first["id"], end=3, parent_duration="preserve")


def test_track_ownership_and_removal_cannot_leave_dangling_clips():
    candidate = _candidate()
    track = add_track(candidate, track_id="owned")
    other = {"id": "foreign", "kind": "video"}
    with pytest.raises(TimelineEditError, match="does not belong"):
        place_media(candidate, "asset", track=other, start=0, end=1)
    place_media(candidate, "asset", track=track, start=0, end=1)
    remove(candidate, "owned", kind="track")
    assert candidate["timeline"]["tracks"] == []
    assert candidate["timeline"]["clips"] == []


def test_move_validates_target_ownership_before_mutating():
    from astrid.sdk.timeline_editing import move

    candidate = _candidate()
    track = add_track(candidate, track_id="owned")
    clip = place_media(candidate, "asset", track=track, start=0, end=1)
    with pytest.raises(TimelineEditError, match="does not belong"):
        move(candidate, clip["id"], track={"id": "foreign"})
    assert clip["track"] == "owned" and clip["at"] == 0 and clip["to"] == 1


def test_place_and_replace_media_use_direct_digest_selectors():
    candidate = _candidate()
    track = add_track(candidate)
    digest = "sha256:" + "a" * 64
    clip = place_media(candidate, digest, track=track, start=0, end=1)
    assert clip["media_id"] == digest
    assert "asset" not in clip
    replace_media(candidate, clip["id"], "b" * 64)
    assert clip["media_id"] == "b" * 64
