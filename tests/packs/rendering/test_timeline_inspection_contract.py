from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import (
    normalize_components,
    normalize_input_window,
    project_input_window,
    render_status,
)


def test_components_are_shared_and_conflicts_are_rejected():
    assert normalize_components("inputs,text", "output")["resolved"] == ["text", "audio", "inputs"]
    try:
        normalize_components("inputs", "inputs")
    except ValueError as exc:
        assert "both" in str(exc)
    else:
        raise AssertionError("conflicting component selectors were accepted")


def test_timestamp_window_is_exact_half_open_rational():
    window = normalize_input_window(at="107.5", context="2.5")
    assert window == {"start": [105, 1], "end": [110, 1], "half_open": True, "selected": [215, 2]}


def test_projection_keeps_short_and_repeated_occurrences_at_end_boundary():
    clips = [
        {"id": "one", "track": "picture", "at": 100, "duration": 10, "occurrence_id": "repeat-a"},
        {"id": "two", "track": "picture", "at": 105, "duration": 10, "occurrence_id": "repeat-b"},
        {"id": "excluded", "track": "picture", "at": 110, "duration": 1, "occurrence_id": "end"},
    ]
    rows = project_input_window(clips, start_frame=3150, end_frame=3300, fps=30)["tracks"][0]["clips"]
    assert [row["occurrence_id"] for row in rows] == ["repeat-a", "repeat-b"]
    assert [row["window"] for row in rows] == [[3150, 3300], [3150, 3300]]
    assert [row["subrow"] for row in rows] == [0, 1]


def test_projection_selection_filters_clip_shot_and_asset_without_rekeying_occurrence():
    clips = [
        {"id": "keep", "track": "picture", "at": 0, "hold": 4,
         "shot_id": "shot-a", "asset": "asset-a", "occurrence_id": "occ-1"},
        {"id": "other", "track": "picture", "at": 0, "hold": 4,
         "shot_id": "shot-b", "asset": "asset-a", "occurrence_id": "occ-2"},
    ]
    projection = project_input_window(
        clips, start_frame=0, end_frame=120, fps=30,
        clip_id="keep", shot_id="shot-a", asset_id="asset-a",
    )
    assert [clip["occurrence_id"] for clip in projection["tracks"][0]["clips"]] == ["occ-1"]


def test_projection_exposes_canonical_asset_key_for_preview_provenance():
    projection = project_input_window(
        [{"id": "picture-1", "track": "picture", "asset": "anchor-v3", "at": 0, "duration": 2}],
        start_frame=0, end_frame=60, fps=30,
    )
    assert projection["tracks"][0]["clips"][0]["asset_key"] == "anchor-v3"


def test_projection_marks_source_audio_on_exact_clip_window():
    projection = project_input_window(
        [
            {"id": "voice", "track": "vo", "at": 2, "duration": 3, "clipType": "media"},
            {"id": "muted", "track": "picture", "at": 2, "duration": 3, "clipType": "media", "audio_source": "source-a", "volume": 0},
        ], start_frame=0, end_frame=180, fps=30,
    )
    voice = next(track for track in projection["tracks"] if track["track_id"] == "vo")["clips"][0]
    muted = next(track for track in projection["tracks"] if track["track_id"] == "picture")["clips"][0]
    assert voice["audio_signifier"]["present"] is True
    assert voice["audio_signifier"]["window"] == [60, 150]
    assert voice["audio_signifier"]["window_seconds"] == [[2, 1], [5, 1]]
    assert voice["audio_signifier"]["visual_encoding"] == "timing_rail"
    assert voice["audio_signifier"]["source_window"] == [[0, 1], [3, 1]]
    assert muted["audio_signifier"]["present"] is False
    assert muted["audio_signifier"]["reason"] == "muted"


def test_status_keeps_timeout_running_and_offers_argv_actions():
    status = render_status(
        lifecycle="timed_out",
        output={"task_id": "T", "timeline": "TL"},
        project="P",
    )
    assert status["kind"] == "running"
    assert status["next_actions"][0]["argv"][:3] == ["astrid", "tasks", "follow"]


def test_input_projection_default_uses_admitted_extent_past_short_render():
    from astrid.packs.rendering.executors.timeline_visualize.filmstrip_cards import (
        _input_projection_bounds,
    )

    snapshot = {
        "fps_rational": [24, 1],
        "duration_frames": 72,  # decoded output is only three seconds
        "input_clips": [{"id": "late", "track": "v", "at": 3, "duration": 3, "end_frame": 144}],
        "metadata": {"input_extent_frames": 144},
    }
    assert _input_projection_bounds(snapshot, {"input_window": None}, {}) == (0, 144)
    assert _input_projection_bounds(
        snapshot, {"input_window": {"start": [2, 1], "end": [10, 1]}}, {}
    ) == (48, 144)


def test_dense_projection_bands_include_every_track():
    clips = [
        {"id": f"clip-{index}", "track": f"track-{index:02d}", "at": 0, "hold": 1}
        for index in range(14)
    ]
    projection = project_input_window(clips, start_frame=0, end_frame=30, fps=30)
    assert projection["track_bands"][0]["track_ids"] == [f"track-{index:02d}" for index in range(10)]
    assert projection["track_bands"][1]["track_ids"] == [f"track-{index:02d}" for index in range(10, 14)]


def test_source_preview_requires_admitted_digest_and_managed_identity(tmp_path):
    import hashlib
    from astrid.packs.rendering.executors.timeline_visualize.filmstrip_execution import _asset_integrity_from_registry

    source = tmp_path / "still.png"
    source.write_bytes(b"png-bytes")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    assert _asset_integrity_from_registry({"assets": {"plain": {"file": str(source)}}})["plain"]["state"] == "unavailable"
    verified = _asset_integrity_from_registry({"assets": {"managed": {"file": str(source), "media_id": "m1", "content_sha256": digest}}})
    assert verified["managed"]["state"] == "verified_original"
