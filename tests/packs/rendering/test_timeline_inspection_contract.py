from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import (
    canonical_clip_identity,
    classify_output_records,
    normalize_components,
    normalize_input_window,
    project_timeline_document,
    project_input_window,
    render_status,
    semantic_media_inventory,
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


def test_input_projection_prefers_canonical_occurrence_id_in_pinned_groups():
    projection = project_input_window(
        [{"id": "clip-1", "track": "picture", "at": 0, "duration": 2,
          "occurrence_id": "occ-canonical", "shot_id": "shot-a"}],
        start_frame=0, end_frame=60, fps=30,
        occurrence_id="occ-canonical",
        shot_occurrences=[{"occurrence_id": "occ-canonical", "shot_id": "shot-a"}],
    )
    assert projection["tracks"][0]["clips"][0]["occurrence_id"] == "occ-canonical"


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


def test_canonical_identity_keeps_occurrence_clip_and_reusable_shot_distinct():
    target = canonical_clip_identity(
        {"id": "clip-1", "shot_id": "shot-A"}, timeline_id="tl-1",
        occurrence_id="occ-2",
    )
    assert target == {
        "kind": "clip", "timeline_id": "tl-1", "occurrence_id": "occ-2",
        "clip_id": "clip-1", "shot_id": "shot-A", "addressable": True,
    }
    unplaced = canonical_clip_identity({"shot_id": "shot-A"}, timeline_id="tl-1")
    assert unplaced["occurrence_id"] is None and not unplaced["addressable"]


def test_output_classification_never_promotes_candidate_and_marks_old_head():
    rows = classify_output_records([
        {"id": "c", "disposition": "candidate", "source_head": "h2"},
        {"id": "preview", "status": "succeeded", "source_head": "h2",
         "metadata": {"render_mode": "authoring_candidate_preview"}},
        {"id": "now", "source_head": "h2"},
        {"id": "old", "disposition": "historical", "source_head": "h1"},
        {"id": "legacy"},
    ], current_head="h2", current_output_id="now")
    assert [row["classification"] for row in rows] == ["candidate", "candidate", "current", "historical", "unverified"]
    assert rows[1]["render_mode"] == "authoring_candidate_preview"
    assert rows[2]["current_for_head"] is True


def test_semantic_media_inventory_separates_selected_alternative_and_invalid_media():
    inventory = semantic_media_inventory([
        {"id": "picture-1", "track": "picture", "asset": "selected", "at": 0, "hold": 2},
        {"id": "bad", "track": "picture", "asset": "missing", "at": -1, "hold": 0},
        None,
    ], {"assets": {
        "selected": {"media_id": "media-1", "sha256": "abc"},
        "option": {"role": "alternative"},
        "old": {"role": "historical"},
    }})
    states = {row["asset_key"]: row["state"] for row in inventory["items"]}
    assert states == {"old": "historical", "option": "alternative", "selected": "active"}
    assert inventory["diagnostics"] == [
        {"code": "invalid_clip_timing", "clip_id": "bad", "message": "clip has invalid or non-positive timing"},
        {"code": "selected_media_missing_registry", "clip_id": "bad", "asset_key": "missing",
         "message": "selected media key is absent from registry"},
        {"code": "invalid_clip_record", "clip_index": 2, "message": "clip must be an object"},
    ]


def test_semantic_media_inventory_walks_nested_clips_and_inherited_mute():
    inventory = semantic_media_inventory([
        {"id": "lane", "muted": True, "children": [
            {"id": "nested", "asset": "nested-selected", "at": 0, "hold": 1},
        ]},
        {"id": "active", "asset": "active-selected", "at": 0, "hold": 1},
    ], {"assets": {
        "nested-selected": {"media_id": "nested-media"},
        "active-selected": {"media_id": "active-media"},
    }})
    states = {row["asset_key"]: row["state"] for row in inventory["items"]}
    assert states == {"active-selected": "active", "nested-selected": "muted"}
    nested = next(row for row in inventory["items"] if row["asset_key"] == "nested-selected")
    assert nested["uses"][0]["clip_id"] == "nested"


def test_zero_visual_track_gain_does_not_hide_image_but_mutes_its_audio():
    inventory = semantic_media_inventory([
        {"id": "video", "track": "picture", "clipType": "media",
         "asset": "visual", "audio_source": "embedded-audio", "volume": 0,
         "at": 0, "hold": 2},
    ], {"assets": {"visual": {"media_id": "media-1", "media_type": "video/mp4"}}})
    item = inventory["items"][0]
    assert item["state"] == "active"
    assert item["uses"][0]["visual_state"] == "active"
    assert item["uses"][0]["audio_state"] == "muted"


def test_shared_timeline_document_projection_filters_paginates_and_expands_text():
    document = {
        "timeline_id": "tl-1", "project_slug": "astrid-intro", "slug": "intro",
        "head_hash": "h2", "current_output_id": "out-current",
        "occurrences": [{"clip_id": "clip-2", "occurrence_id": "occ-2", "shot_id": "shot-A"}],
        "config": {"clips": [
            {"id": "clip-1", "track": "picture", "at": 0, "hold": 2, "text": "A" * 600,
             "asset": "img-1"},
            {"id": "clip-2", "track": "picture", "at": 2, "hold": 2, "shot_id": "shot-A",
             "asset": "img-2"},
            {"id": "clip-3", "track": "audio", "at": 4, "hold": 2, "asset": "music"},
        ]},
        "registry": {"assets": {"img-1": {"media_id": "m1"}, "img-2": {"media_id": "m2"},
                                  "music": {"role": "music"}}},
        "outputs": [{"id": "out-current", "source_head": "h2"},
                    {"id": "draft", "disposition": "candidate"}],
    }
    first = project_timeline_document(document, limit=1, track="picture")
    assert first["clips"][0]["clip_id"] == "clip-1"
    assert first["targets"][0]["clip_id"] == "clip-1"
    assert first["clips"][0]["text_truncated"] is True
    assert first["pagination"]["total"] == 2 and first["pagination"]["next_cursor"]
    second = project_timeline_document(document, limit=1, cursor=first["pagination"]["next_cursor"], track="picture")
    assert second["clips"][0]["occurrence_id"] == "occ-2"
    assert second["clips"][0]["target"] == second["targets"][0]
    assert [output["classification"] for output in first["outputs"]] == ["current", "candidate"]
    expanded = project_timeline_document(document, clip="clip-1", detail=True)
    assert expanded["clips"][0]["text"] == "A" * 600
    assert expanded["clips"][0]["actions"]["visualize"]["argv"][-2:] == ["--show", "inputs"]
    filtered = project_timeline_document(document, occurrence="occ-2")
    assert [row["clip_id"] for row in filtered["clips"]] == ["clip-2"]


def test_projection_exposes_bounded_composition_provenance_and_source_time():
    result = project_timeline_document({
        "timeline_id": "tl-1", "head_revision_id": "parent-1",
        "config": {"clips": [{
            "id": "occ-1:local", "track": "picture", "at": 2, "hold": 1,
            "from": 4, "to": 5, "speed": 1,
            "app": {"astrid_shot_composition": {
                "shot_id": "shot-1", "shot_revision_id": "shot-r1",
                "internal_timeline_revision_id": "internal-r1",
                "occurrence_id": "occ-1", "source_clip_id": "local",
                "stable_deep_link": "astrid://occurrences/occ-1",
            }},
        }]},
    })
    row = result["clips"][0]
    assert row["composition"]["occurrence_id"] == "occ-1"
    assert row["composition"]["source_clip_id"] == "local"
    assert row["source_time"] == {"from": 4, "to": 5, "speed": 1}


def test_inspection_orders_rational_times_and_rejects_invalid_millisecond_input():
    document = {
        "timeline_id": "tl-1", "project_id": "p-1", "head_hash": "head-1",
        "config": {"clips": [
            {"id": "half", "track": "picture", "at_ms": 500, "duration_ms": 1000},
            {"id": "third", "track": "picture", "at_ms": 333, "duration_ms": 1000},
            {"id": "bad", "track": "picture", "at_ms": "not-a-time", "duration_ms": 1000},
        ]},
    }
    result = project_timeline_document(document)
    assert [row["clip_id"] for row in result["clips"]] == ["third", "half", "bad"]
    assert result["clips"][0]["at_seconds"] == [333, 1000]
    assert any(item["code"] == "invalid_clip_timing" for item in result["diagnostics"])
    assert result["clips"][0]["actions"]["expand"]["argv"][4] == "p-1"


def test_inspection_cursor_is_bound_to_the_document_head():
    document = {
        "timeline_id": "tl-1", "head_hash": "head-1",
        "config": {"clips": [
            {"id": "clip", "at": 0, "hold": 1},
            {"id": "clip-2", "at": 1, "hold": 1},
        ]},
    }
    cursor = project_timeline_document(document, limit=1)["pagination"]["next_cursor"]
    changed = dict(document, head_hash="head-2")
    try:
        project_timeline_document(changed, limit=1, cursor=cursor)
    except ValueError as exc:
        assert "cursor" in str(exc)
    else:
        raise AssertionError("cursor from a different committed head was accepted")


def test_inspection_cursor_is_bound_to_parent_candidate_and_render_scope():
    document = {
        "timeline_id": "tl-1", "project_id": "p-1", "head_hash": "head-1",
        "parent_revision_id": "parent-1", "candidate_digest": "sha256:candidate-1",
        "render_run_id": "run-1", "config": {"clips": [
            {"id": "clip", "at": 0, "hold": 1},
            {"id": "clip-2", "at": 1, "hold": 1},
        ]},
    }
    cursor = project_timeline_document(document, limit=1)["pagination"]["next_cursor"]
    changed = dict(document, parent_revision_id="parent-2")
    try:
        project_timeline_document(changed, limit=1, cursor=cursor)
    except ValueError as exc:
        assert "cursor" in str(exc)
    else:
        raise AssertionError("cursor from a different parent revision was accepted")


def test_row_actions_retain_repeated_occurrence_scope():
    projection = project_timeline_document({
        "timeline_id": "tl-1", "project_id": "p-1", "head_hash": "h1",
        "occurrences": [{"clip_id": "clip", "occurrence_id": "occ-7", "shot_id": "shot-7"}],
        "config": {"clips": [{"id": "clip", "at": 0, "hold": 1}]},
    })
    row = projection["clips"][0]
    assert ["--occurrence", "occ-7"] == row["actions"]["expand"]["argv"][-4:-2]
    assert "--shot" in row["actions"]["visualize"]["argv"]
