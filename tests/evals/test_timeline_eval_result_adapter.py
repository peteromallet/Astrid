from __future__ import annotations

import pytest

from evals.timeline.result_adapter import (
    ResultContractError,
    adapt_worker_result,
    build_outcome_record,
    public_result_contract,
    worker_protocol_record,
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


def test_l08_adapter_projects_ordered_segment_text_and_preserves_rich_observations() -> None:
    raw = {"observations": {
        "segments": [
            {"segment_id": "seg-2", "start": 4.0, "text": "Second"},
            {"segment_id": "seg-1", "start": 1.0, "text": "First"},
        ],
        "missing_text_roles": ["transcript"],
    }}
    adapted = adapt_worker_result(_case("L08"), raw)
    assert adapted["observations"]["available_segment_titles"] == ["Second", "First"]
    assert raw["observations"]["segments"][0]["segment_id"] == "seg-2"
    assert raw["observations"]["missing_text_roles"] == ["transcript"]


def test_l08_adapter_rejects_conflicting_text_projection() -> None:
    with pytest.raises(ResultContractError, match="L08 segment conflict"):
        adapt_worker_result(_case("L08"), {"observations": {
            "segments": [{"text": "Expected"}],
            "available_segment_titles": ["Different"],
        }})


def test_protocol_health_is_separate_from_semantic_outcome_and_preserves_malformed_evidence() -> None:
    protocol = worker_protocol_record(_case("L06"), {
        "agent_status": "blocked", "status": "passed",
    })
    assert protocol["valid"] is False
    assert protocol["raw_preserved"] is True
    record = build_outcome_record(
        _case("L06"), worker_protocol=protocol,
        conclusion={"answer": "observed"},
        independent_before={"head": "before"}, independent_after={"head": "after"},
        independent_readback={"status": "pass"},
        render_artifacts={"preview": "preview.json"},
        playback_artifacts=None,
    )
    assert record["semantic_outcome"]["status"] == "unjudged"
    assert record["worker_protocol"]["valid"] is False
    assert record["independent_evidence"]["before"]["head"] == "before"
