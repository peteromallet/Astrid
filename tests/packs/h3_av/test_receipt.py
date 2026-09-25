from __future__ import annotations

import json

import pytest

from astrid.packs.h3_av.src.receipt import ReceiptError, build_final_receipt


def _cleanup(*, verified: bool = True) -> dict[str, object]:
    return {
        "resources": [
            {
                "kind": "runpod_pod",
                "id": "pod-5090",
                "owned": True,
                "expected_postcondition": "terminated and absent from provider list",
                "observed_postcondition": "terminated and absent from provider list",
                "verified": verified,
            },
            {
                "kind": "network_volume",
                "id": "volume-backup",
                "owned": False,
                "expected_postcondition": "preserved and still attached to no deleted resource",
                "observed_postcondition": "preserved",
                "verified": True,
            },
        ]
    }


def test_final_receipt_keeps_execution_verification_approval_and_cleanup_separate() -> None:
    receipt = build_final_receipt(
        request_digest="sha256:request",
        task_succeeded={"task_id": "task-1", "attempt_id": "attempt-1"},
        candidate_verified={"verification": "verified"},
        editorially_approved={"review_id": "review-1"},
        cleanup=_cleanup(),
    )

    assert receipt["overall_status"] == "complete"
    assert {name: value["status"] for name, value in receipt["states"].items()} == {
        "task_succeeded": "passed",
        "candidate_verified": "passed",
        "editorially_approved": "passed",
        "cleanup_verified": "passed",
    }
    assert receipt["cleanup"]["resources"][0]["owned"] is True
    assert receipt["cleanup"]["resources"][1]["owned"] is False
    json.dumps(receipt)


def test_successful_task_does_not_claim_editorial_or_cleanup_approval_by_default() -> None:
    receipt = build_final_receipt(
        request_digest="sha256:request",
        task_succeeded={"task_id": "task-1"},
        candidate_verified={"verification": "verified"},
    )

    assert receipt["overall_status"] == "candidate_verified"
    assert receipt["states"]["editorially_approved"]["status"] == "not_claimed"
    assert receipt["states"]["cleanup_verified"]["status"] == "not_claimed"
    assert receipt["cleanup"]["resources"] == []


def test_failed_cleanup_cannot_be_hidden_by_successful_generation() -> None:
    receipt = build_final_receipt(
        request_digest="sha256:request",
        task_succeeded={"task_id": "task-1"},
        candidate_verified={"verification": "verified"},
        cleanup=_cleanup(verified=False),
    )

    assert receipt["overall_status"] == "candidate_verified"
    assert receipt["states"]["cleanup_verified"]["status"] == "failed"


def test_cleanup_requires_exact_unique_resource_postconditions() -> None:
    cleanup = _cleanup()
    cleanup["resources"] = [cleanup["resources"][0], cleanup["resources"][0]]  # type: ignore[index]
    with pytest.raises(ReceiptError, match="duplicate resource"):
        build_final_receipt(
            request_digest="sha256:request",
            task_succeeded={"task_id": "task-1"},
            candidate_verified={"verification": "verified"},
            cleanup=cleanup,
        )
