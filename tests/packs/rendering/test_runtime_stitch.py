from __future__ import annotations

import pytest

from astrid.packs.rendering.finalizers.runtime_stitch import build_stitch_admission
from astrid.packs.video_editing.orchestrators.runtime_orchestration import OrchestrationContractError


DIGEST = "sha256:" + "a" * 64


def test_stitch_admission_uses_ordered_cas_and_runtime_success_edges():
    admission = build_stitch_admission(
        project="demo",
        stitch_name="join_final_stitch",
        stitch_digest=DIGEST,
        root_task_id="root-1",
        child_task_ids=["child-1", "child-2"],
        input_object_ids=["cas-1", "cas-2"],
        settlement_effect={"kind": "lineage", "source": "stitch"},
        idempotency_key="producer-stitch-key",
    )
    assert admission.body["capability_id"] == "rendering.join_final_stitch"
    assert admission.body["input_object_ids"] == ["cas-1", "cas-2"]
    edges = admission.body["spec"]["runtime_dependencies"]["edges"]
    assert [edge["from_task_id"] for edge in edges] == ["child-1", "child-2"]
    assert all(edge["requires_event"] == "task.succeeded" for edge in edges)
    assert "idempotency_key" not in admission.body


def test_stitch_rejects_duplicate_or_unknown_identity():
    with pytest.raises(OrchestrationContractError):
        build_stitch_admission(
            project="demo",
            stitch_name="not-a-finalizer", stitch_digest=DIGEST, root_task_id="root",
            child_task_ids=[], input_object_ids=[], idempotency_key="key",
        )
    with pytest.raises(OrchestrationContractError):
        build_stitch_admission(
            project="demo",
            stitch_name="travel_stitch", stitch_digest=DIGEST, root_task_id="root",
            child_task_ids=["child", "child"], input_object_ids=["cas"], idempotency_key="key",
        )


def test_stitch_requires_explicit_non_empty_settlement_effect():
    with pytest.raises(OrchestrationContractError):
        build_stitch_admission(
            project="demo", stitch_name="travel_stitch", stitch_digest=DIGEST,
            root_task_id="root", child_task_ids=["child"], input_object_ids=["cas"],
            idempotency_key="key",
        )
