from __future__ import annotations

import copy

import pytest

from astrid.sdk import move_occurrence_group
from astrid.sdk.timeline_editing import TimelineEditError
from evals.timeline.independent_readback import verify_occurrence_group_move


def _placements():
    starts = [0, 100, 300, 600]
    durations = [100, 200, 300, 400]
    return [
        {
            "occurrence_id": occurrence_id,
            "shot_id": f"shot-{occurrence_id}",
            "duration_ms": duration,
            "placement": {"start_ms": start, "track": "picture"},
            "provenance": {"opaque": occurrence_id},
        }
        for occurrence_id, start, duration in zip("abcd", starts, durations)
    ]


def test_move_occurrence_group_moves_whole_placement_and_is_idempotent():
    bundle = {"placements": _placements()}
    original = copy.deepcopy(bundle["placements"])
    expected = [original[0], original[3], original[1], original[2]]
    move_occurrence_group(bundle, "d", before_occurrence_id="b")

    assert [row["occurrence_id"] for row in bundle["placements"]] == ["a", "d", "b", "c"]
    assert [row["duration_ms"] for row in bundle["placements"]] == [100, 400, 200, 300]
    assert [row["placement"]["start_ms"] for row in bundle["placements"]] == [0, 100, 500, 700]
    for row in bundle["placements"]:
        source = next(candidate for candidate in expected if candidate["occurrence_id"] == row["occurrence_id"])
        assert row["shot_id"] == source["shot_id"]
        assert row["duration_ms"] == source["duration_ms"]
        assert row["provenance"] == source["provenance"]

    first_result = copy.deepcopy(bundle["placements"])
    move_occurrence_group(bundle, "d", before_occurrence_id="b")
    assert bundle["placements"] == first_result
    assert sum(row["duration_ms"] for row in bundle["placements"]) == sum(row["duration_ms"] for row in original)


@pytest.mark.parametrize(
    ("occurrence_id", "anchor_id", "reason"),
    [
        ("a", "a", "itself"),
        ("missing", "b", "not found"),
        ("a", "missing", "not found"),
    ],
)
def test_move_occurrence_group_rejects_invalid_targets_without_mutation(occurrence_id, anchor_id, reason):
    bundle = {"placements": _placements()}
    before = copy.deepcopy(bundle)
    with pytest.raises(TimelineEditError, match=reason):
        move_occurrence_group(bundle, occurrence_id, before_occurrence_id=anchor_id)
    assert bundle == before


def test_move_occurrence_group_rejects_gaps_or_invalid_duration_without_partial_edit():
    for mutate in (
        lambda placements: placements[2]["placement"].update(start_ms=301),
        lambda placements: placements[2].update(duration_ms=0),
    ):
        bundle = {"placements": _placements()}
        mutate(bundle["placements"])
        before = copy.deepcopy(bundle)
        with pytest.raises(TimelineEditError):
            move_occurrence_group(bundle, "d", before_occurrence_id="b")
        assert bundle == before


def _closure(order, starts):
    occurrences = []
    shots = []
    internals = []
    duration_by_id = dict(zip("abcd", [100, 200, 300, 400]))
    for occurrence_id, start in zip(order, starts):
        duration = duration_by_id[occurrence_id]
        shot_id = f"shot-{occurrence_id}"
        revision_id = f"revision-{occurrence_id}"
        internal_id = f"internal-{occurrence_id}"
        occurrences.append({
            "occurrence_id": occurrence_id,
            "shot_id": shot_id,
            "shot_revision_id": revision_id,
            "duration_ms": duration,
            "placement": {"start_ms": start, "track": "picture"},
        })
        shots.append({
            "shot_id": shot_id,
            "revision_id": revision_id,
            "internal_timeline_revision_id": internal_id,
            "payload": {
                "name": f"Shot {occurrence_id}",
                "items": [{"item_id": f"image-{occurrence_id}", "role": "picture"}],
                "audio_bindings": [{"clip_id": f"voice-{occurrence_id}"}],
                "text_bindings": [{"clip_id": f"caption-{occurrence_id}", "text": occurrence_id}],
                "internal_timeline_revision_id": internal_id,
            },
        })
        internals.append({
            "revision_id": internal_id,
            "payload": {"clips": [
                {"id": f"picture-{occurrence_id}", "asset": f"img-{occurrence_id}", "track": "picture"},
                {"id": f"voice-{occurrence_id}", "asset": f"vo-{occurrence_id}", "track": "voice"},
                {"id": f"caption-{occurrence_id}", "text": occurrence_id, "track": "caption"},
            ]},
        })
    return {
        "head_revision_id": "head",
        "parent_revision": {"revision_id": "head", "payload": {"occurrences": occurrences}},
        "shot_revisions": shots,
        "internal_timeline_revisions": internals,
    }


def test_independent_a03_readback_passes_whole_group_reorder_and_rejects_binding_damage():
    before = _closure("abcd", [0, 100, 300, 600])
    after = _closure("adbc", [0, 100, 500, 700])
    locator = {"closing_occurrence_id": "d", "middle_occurrence_id": "b"}
    result = verify_occurrence_group_move(before, after, locator)
    assert result["status"] == "pass"
    assert result["moved_group_preserves_picture_voice_caption_bindings"] is True
    assert result["total_duration_unchanged"] is True

    damaged = copy.deepcopy(after)
    damaged["internal_timeline_revisions"][1]["payload"]["clips"][1]["asset"] = "wrong-voice"
    result = verify_occurrence_group_move(before, damaged, locator)
    assert result["status"] == "fail"
    assert result["moved_group_preserves_picture_voice_caption_bindings"] is False


def test_independent_a03_readback_rejects_wrong_order_duration_and_total_time():
    before = _closure("abcd", [0, 100, 300, 600])
    locator = {"closing_occurrence_id": "d", "middle_occurrence_id": "b"}
    wrong_order = _closure("abdc", [0, 100, 300, 600])
    assert verify_occurrence_group_move(before, wrong_order, locator)["status"] == "fail"

    shortened = _closure("adbc", [0, 100, 500, 700])
    shortened["parent_revision"]["payload"]["occurrences"][1]["duration_ms"] = 399
    result = verify_occurrence_group_move(before, shortened, locator)
    assert result["durations_unchanged"] is False
    assert result["total_duration_unchanged"] is False


def test_independent_a03_readback_rejects_translation_of_the_whole_after_timeline():
    before = _closure("abcd", [1200, 1300, 1500, 1800])
    translated_after = _closure("adbc", [1210, 1310, 1710, 1910])
    result = verify_occurrence_group_move(
        before, translated_after,
        {"closing_occurrence_id": "d", "middle_occurrence_id": "b"},
    )
    assert result["status"] == "fail"
    assert result["cumulative_starts_valid"] is False
