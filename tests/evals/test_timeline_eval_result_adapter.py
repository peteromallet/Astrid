from __future__ import annotations

import pytest

from evals.timeline.result_adapter import (
    ResultContractError,
    adapt_worker_result,
    public_result_contract,
)


def _case(case_id: str) -> dict[str, object]:
    return {
        "id": case_id,
        "required_artifacts": [
            "brief.json", "trace.jsonl", "result.json",
            "evidence/identity-map.json" if case_id == "L02" else "evidence/diagnostic.json",
        ],
    }


def test_public_contract_declares_worker_and_coordinator_artifact_ownership() -> None:
    contract = public_result_contract(_case("L02"))
    assert contract["schema"] == "astrid.timeline-eval.worker-result.v1"
    assert "evidence/identity-map.json" in contract["ownership"]["worker_may_write"]
    assert "brief.json" not in contract["ownership"]["worker_may_write"]
    assert "brief.json" in contract["ownership"]["coordinator_only"]
    assert contract["ownership"]["coordinator_only"] == [
        "brief.json", "coordinator/cases/L02/readback.json",
    ]


def test_l02_adapter_normalizes_labelled_media_without_mutating_raw() -> None:
    raw = {
        "status": "completed",
        "observations": {"expanded_occurrences": [{
            "occurrence_id": "occ-1", "shot_id": "shot-1",
            "shot_revision_id": "shot-rev-1",
            "internal_timeline_revision_id": "internal-1",
            "media_handles": [{"role": "selected_image", "media_id": "sha256:image-1"}],
            "nested_clips": [],
        }]},
    }
    adapted = adapt_worker_result(_case("L02"), raw)
    normalized = adapted["observations"]["expanded_occurrences"][0]
    assert normalized["selected_image_media_id"] == "sha256:image-1"
    assert "selected_image_media_id" not in raw["observations"]["expanded_occurrences"][0]


def test_l02_adapter_rejects_conflicting_media_projections() -> None:
    with pytest.raises(ResultContractError, match="selected media conflict"):
        adapt_worker_result(_case("L02"), {
            "observations": {"expanded_occurrences": [{
                "occurrence_id": "occ-1", "shot_id": "shot-1",
                "shot_revision_id": "shot-rev-1",
                "internal_timeline_revision_id": "internal-1",
                "selected_image_media_id": "sha256:one",
                "media_handles": [{"role": "selected_image", "media_id": "sha256:two"}],
            }]},
        })


def test_l06_adapter_requires_explicit_diagnostic_shape() -> None:
    adapted = adapt_worker_result(_case("L06"), {"observations": {"diagnostic": {
        "status": "invalid", "error_type": "UnsupportedAuthoringEditError",
        "base_parent_revision_id": "parent-1", "message": "use placements",
    }}})
    assert adapted["observations"]["diagnostic"]["status"] == "invalid"
    with pytest.raises(ResultContractError, match="L06 diagnostic missing"):
        adapt_worker_result(_case("L06"), {"observations": {"diagnostic": {
            "status": "invalid", "error_type": "UnsupportedAuthoringEditError",
        }}})


def test_l06_adapter_accepts_flat_projection_and_rejects_conflict() -> None:
    adapted = adapt_worker_result(_case("L06"), {"observations": {
        "candidate_status": "invalid",
        "candidate_error_type": "UnsupportedAuthoringEditError",
        "base_parent_revision_id": "parent-1",
    }})
    assert adapted["observations"]["diagnostic"] == {
        "status": "invalid",
        "error_type": "UnsupportedAuthoringEditError",
        "base_parent_revision_id": "parent-1",
    }
    with pytest.raises(ResultContractError, match="diagnostic conflict"):
        adapt_worker_result(_case("L06"), {"observations": {
            "candidate_status": "invalid",
            "candidate_error_type": "UnsupportedAuthoringEditError",
            "base_parent_revision_id": "parent-flat",
            "diagnostic": {
                "status": "invalid",
                "error_type": "UnsupportedAuthoringEditError",
                "base_parent_revision_id": "parent-nested",
            },
        }})


def test_agent_status_and_status_conflict_is_rejected() -> None:
    with pytest.raises(ResultContractError, match="conflicting agent terminal statuses"):
        adapt_worker_result(_case("L06"), {"agent_status": "blocked", "status": "passed"})


def test_worker_cannot_relabel_coordinator_artifact() -> None:
    with pytest.raises(ResultContractError, match="artifact ownership conflict"):
        adapt_worker_result(_case("L02"), {
            "artifact_ownership": {"brief.json": "worker"},
        })
