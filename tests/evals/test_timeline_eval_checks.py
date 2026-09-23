from __future__ import annotations

import pytest

from evals.timeline.checks import run_checks


def test_wrong_media_selector_fails_independently() -> None:
    result = run_checks(
        [{"id": "selector", "check": "path_equals", "artifact": "after",
          "path": "selected.digest", "expected": "new-image"}],
        {"after": {"selected": {"digest": "old-video"}}},
    )[0]
    assert result.status == "fail"


def test_records_include_accepts_extra_projection_fields_and_any_target() -> None:
    result = run_checks(
        [{"id": "identity", "check": "records_include", "artifact": "result",
          "path": "observations.expanded_occurrences", "mode": "any",
          "expected": [{"occurrence_id": "occ-1", "shot_id": "shot-1",
                         "shot_revision_id": "shot-rev-1",
                         "internal_timeline_revision_id": "internal-1",
                         "selected_image_media_id": "sha256:image-1"},
                        {"occurrence_id": "occ-2", "shot_id": "shot-2",
                         "shot_revision_id": "shot-rev-2",
                         "internal_timeline_revision_id": "internal-2",
                         "selected_image_media_id": "sha256:image-2"}]}],
        {"result": {"observations": {"expanded_occurrences": [
            {"occurrence_id": "occ-1", "shot_id": "shot-1",
             "shot_revision_id": "shot-rev-1",
             "internal_timeline_revision_id": "internal-1",
             "selected_image_media_id": "sha256:image-1",
             "nested_clips": [{"id": "shot-1"}],
             "derived": {"local_path": "media/image-1"}},
        ]}}},
    )[0]
    assert result.status == "pass"


def test_semantic_oracle_unavailable_is_explicit_missing_capability() -> None:
    result = run_checks(
        [{"id": "l04_semantic", "check": "semantic_oracle_unavailable"}], {},
    )[0]
    assert result.status == "missing_capability"
    assert "semantic oracle is unavailable" in result.message


def test_moved_audio_timing_fails_independently() -> None:
    result = run_checks(
        [{"id": "audio_stays", "check": "paths_unchanged",
          "paths": ["audio.vo.start_ms", "audio.vo.source_in_ms", "audio.vo.rate"]}],
        {"before": {"audio": {"vo": {"start_ms": 1200, "source_in_ms": 300, "rate": 1.0}}},
         "after": {"audio": {"vo": {"start_ms": 1500, "source_in_ms": 300, "rate": 1.0}}}},
    )[0]
    assert result.status == "fail"
    assert result.evidence == ("audio.vo.start_ms",)


def test_removed_word_fails_exact_text_check() -> None:
    result = run_checks(
        [{"id": "full_script", "check": "path_equals", "artifact": "after",
          "path": "text.script", "expected": "Ideas images words together"}],
        {"after": {"text": {"script": "Ideas images together"}}},
    )[0]
    assert result.status == "fail"


def test_changed_script_fails_unchanged_check_even_if_title_is_correct() -> None:
    results = run_checks(
        [{"id": "title", "check": "path_equals", "artifact": "after",
          "path": "text.title", "expected": "A more curious internet"},
         {"id": "script", "check": "paths_unchanged", "paths": ["text.script"]}],
        {"before": {"text": {"title": "Old title", "script": "Keep every word."}},
         "after": {"text": {"title": "A more curious internet", "script": "Keep some words."}}},
    )
    assert [result.status for result in results] == ["pass", "fail"]


def test_shared_copy_identity_fails() -> None:
    result = run_checks(
        [{"id": "copy_ids", "check": "identity_disjoint",
          "original_ids_path": "original.ids", "duplicate_ids_path": "duplicate.ids"}],
        {"before": {"original": {"ids": ["shot-1", "item-1"]}},
         "after": {"duplicate": {"ids": ["shot-2", "item-1"]}}},
    )[0]
    assert result.status == "fail"
    assert result.evidence == ("item-1",)


def test_missing_panel_fails_coverage_check() -> None:
    panels = [
        {"quadrant": "top_left", "rect": {"x": 0, "y": 0, "width": 0.5, "height": 0.5}},
        {"quadrant": "top_right", "rect": {"x": 0.5, "y": 0, "width": 0.5, "height": 0.5}},
        {"quadrant": "bottom_left", "rect": {"x": 0, "y": 0.5, "width": 0.5, "height": 0.5}},
    ]
    result = run_checks([{"id": "four", "check": "panel_coverage", "path": "panels"}],
                        {"after": {"panels": panels}})[0]
    assert result.status == "fail"
    assert "bottom_right" in result.message


def test_reordered_tie_fails_stable_id_tiebreak() -> None:
    result = run_checks(
        [{"id": "brightness", "check": "order", "artifact": "after",
          "path": "images", "sort_path": "luma", "id_path": "media_id"}],
        {"after": {"images": [{"media_id": "img-b", "luma": 0.4},
                               {"media_id": "img-a", "luma": 0.4}]}},
    )[0]
    assert result.status == "fail"


@pytest.mark.parametrize(
    ("ids", "expected"),
    [(["img-a", "img-b"], "pass"), (["img-b", "img-a"], "fail")],
)
def test_equal_brightness_is_sorted_by_media_id(ids: list[str], expected: str) -> None:
    by_id = {"img-a": {"media_id": "img-a", "luma": 0.4},
             "img-b": {"media_id": "img-b", "luma": 0.4}}
    result = run_checks(
        [{"id": "tie", "check": "order", "artifact": "after", "path": "images",
          "sort_path": "luma", "id_path": "media_id"}],
        {"after": {"images": [by_id[item] for item in ids]}},
    )[0]
    assert result.status == expected


def test_decoded_media_absence_is_blocked_not_passed() -> None:
    result = run_checks([{"id": "pixels", "check": "decoded_media"}], {})[0]
    assert result.status == "missing_capability"


def test_valid_panels_pass() -> None:
    quadrants = ("top_left", "top_right", "bottom_left", "bottom_right")
    rects = ((0, 0), (0.5, 0), (0, 0.5), (0.5, 0.5))
    panels = [{"quadrant": name, "rect": {"x": x, "y": y, "width": 0.5, "height": 0.5}}
              for name, (x, y) in zip(quadrants, rects)]
    result = run_checks([{"id": "four", "check": "panel_coverage", "path": "panels"}],
                        {"after": {"panels": panels}})[0]
    assert result.status == "pass"
