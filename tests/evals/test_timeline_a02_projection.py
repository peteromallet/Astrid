from __future__ import annotations

import copy

import pytest

from evals.timeline.a02_projection import (
    A02FixtureUnavailable,
    A02_PROJECTION,
    materialize_a02_derivative,
    validate_a02_readback,
)
from evals.timeline.fixture_contracts import action_target_contract


def _closure() -> dict[str, object]:
    occurrences = [
        {"occurrence_id": f"occ-{i}", "shot_id": f"shot-{i}",
         "shot_revision_id": f"rev-{i}", "duration_ms": 1000,
         "placement": {"start_ms": i * 1000}}
        for i in range(4)
    ]
    shots = []
    internals = []
    for i in range(4):
        shots.append({"shot_id": f"shot-{i}", "revision_id": f"rev-{i}",
                      "internal_timeline_revision_id": f"internal-{i}",
                      "payload": {"items": []}})
        internals.append({"revision_id": f"internal-{i}", "payload": {
            "clips": [{"id": f"picture-{i}", "track": "picture"},
                      {"id": f"voice-{i}", "track": "vo"}],
        }})
    return {
        "parent_revision": {"revision_id": "parent-before", "payload": {
            "duration_ms": 4000,
            "occurrences": occurrences,
            "clips": [{"id": "music", "track": "music", "at_ms": 0,
                       "duration_ms": 4000, "source_from": 12}],
        }},
        "shot_revisions": shots,
        "internal_timeline_revisions": internals,
    }


def _removed_closure() -> tuple[dict[str, object], dict[str, object]]:
    before = _closure()
    after = copy.deepcopy(before)
    payload = after["parent_revision"]["payload"]
    payload["duration_ms"] = 3000
    payload["occurrences"] = [
        {**row, "placement": {"start_ms": row["placement"]["start_ms"] - 1000}}
        if row["occurrence_id"] in {"occ-2", "occ-3"} else row
        for row in payload["occurrences"] if row["occurrence_id"] != "occ-1"
    ]
    payload["clips"][0]["duration_ms"] = 3000
    after["parent_revision"]["revision_id"] = "parent-after"
    return before, after


def test_a02_materializes_only_from_four_shots_with_voice_and_music() -> None:
    derivative = materialize_a02_derivative(_closure(), target_occurrence_id="occ-1")
    assert derivative["readback_projection"] == A02_PROJECTION
    assert derivative["target_locator"]["remove_voice_clip_ids"] == ["voice-1"]
    with pytest.raises(A02FixtureUnavailable, match="exactly four"):
        materialize_a02_derivative({**_closure(), "parent_revision": {
            **_closure()["parent_revision"],
            "payload": {**_closure()["parent_revision"]["payload"],
                        "occurrences": _closure()["parent_revision"]["payload"]["occurrences"] + [
                            {"occurrence_id": "extra", "shot_id": "extra", "duration_ms": 1,
                             "placement": {"start_ms": 4000}}
                        ]},
        }}, target_occurrence_id="occ-1")


def test_a02_positive_oracle_compacts_later_occurrences_and_music() -> None:
    before, after = _removed_closure()
    assert validate_a02_readback(before, after, target_occurrence_id="occ-1") == []


def test_a02_negative_oracle_rejects_duration_or_music_drift() -> None:
    before, after = _removed_closure()
    after["parent_revision"]["payload"]["occurrences"][1]["duration_ms"] = 900
    after["parent_revision"]["payload"]["clips"][0]["duration_ms"] = 2800
    errors = validate_a02_readback(before, after, target_occurrence_id="occ-1")
    assert any("duration changed" in error for error in errors)
    assert any("music clip music was not trimmed" in error for error in errors)


def test_a02_negative_oracle_rejects_duplicate_remaining_occurrence() -> None:
    before, after = _removed_closure()
    duplicate = copy.deepcopy(after["parent_revision"]["payload"]["occurrences"][1])
    after["parent_revision"]["payload"]["occurrences"].append(duplicate)
    errors = validate_a02_readback(before, after, target_occurrence_id="occ-1")
    assert "remaining occurrences contain duplicate occurrence IDs" in errors


def test_a02_negative_oracle_rejects_muted_voice_and_music_identity_drift() -> None:
    before, after = _removed_closure()
    after["internal_timeline_revisions"][2]["payload"]["clips"][1]["muted"] = True
    after["parent_revision"]["payload"]["clips"][0]["asset"] = "different-music"
    errors = validate_a02_readback(before, after, target_occurrence_id="occ-1")
    assert any("voice clip voice-2 muted state changed" in error for error in errors)
    assert "music clip music media identity changed" in errors


def test_a02_contract_exposes_projection_but_remains_blocked_without_route() -> None:
    contract = action_target_contract({"id": "A02"})
    assert contract.readback_projection == A02_PROJECTION
    assert contract.status == "blocked"
