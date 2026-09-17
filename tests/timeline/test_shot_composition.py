from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from astrid.core.timeline.shot_composition import (
    ShotCompositionValidationError,
    StaleWriteError,
    assert_expected_head,
    parse_shot_composition,
    stable_occurrence_deep_link,
    stable_output_identity,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "timeline" / "shot_composition.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_contract_preserves_revision_occurrence_and_input_identity() -> None:
    contract = parse_shot_composition(load_fixture())
    occurrences = contract["occurrences"]
    revisions = {(row["shot_id"], row["revision_id"]) for row in contract["shot_revisions"]}

    assert len(occurrences) == 4
    assert (occurrences[0]["shot_id"], occurrences[0]["revision_id"]) == ("shot-alpha", "rev-a")
    assert (occurrences[1]["shot_id"], occurrences[1]["revision_id"]) == ("shot-alpha", "rev-a")
    assert occurrences[0]["occurrence_id"] != occurrences[1]["occurrence_id"]
    assert ("shot-alpha", "rev-b") in revisions
    assert ("shot-beta", "rev-a") in revisions
    assert occurrences[0]["output_identity"] != occurrences[1]["output_identity"]
    assert occurrences[0]["stable_deep_link"] == stable_occurrence_deep_link(
        "project-001", "document-primary", "shot-alpha", "rev-a", "occ-1"
    )
    assert occurrences[0]["output_identity"] == stable_output_identity(
        "project-001", "document-primary", "occ-1"
    )

    alpha = next(row for row in contract["shot_revisions"] if row["revision_id"] == "rev-a" and row["shot_id"] == "shot-alpha")
    assert alpha["timing"]["duration_ms"] == 2000
    assert alpha["audio"]["scope"]["project_id"] == "project-001"
    assert alpha["provenance"]["source"] == "travel-between-images"
    assert [row["ordinal"] for row in alpha["generation_inputs"]] == [0, 1]
    assert alpha["dependencies"] == [{"shot_id": "shot-beta", "revision_id": "rev-a", "required": True}]


def test_contract_carries_missing_dependency_and_rejects_stale_head() -> None:
    contract = parse_shot_composition(load_fixture())
    assert contract["cases"]["missing_dependency"]["expected"] == "missing_dependency"
    stale = contract["cases"]["stale_write_rejection"]
    assert stale["expected_status"] == 409
    with pytest.raises(StaleWriteError) as error:
        assert_expected_head(stale["expected_head_revision_id"], stale["submitted_head_revision_id"])
    assert error.value.status == 409


def test_contract_rejects_legacy_group_and_shot_clip_shapes() -> None:
    legacy_group = copy.deepcopy(load_fixture())
    legacy_group["pinnedShotGroups"] = []
    with pytest.raises(ShotCompositionValidationError, match="migration-only"):
        parse_shot_composition(legacy_group)

    legacy_clip = copy.deepcopy(load_fixture())
    legacy_clip["shot_revisions"][0]["internal_timeline_revision"]["timeline"]["clips"][0]["clipType"] = "shot"
    with pytest.raises(ShotCompositionValidationError, match="migration-only"):
        parse_shot_composition(legacy_clip)
