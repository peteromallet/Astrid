from __future__ import annotations

import json

import pytest

from astrid.packs.video_editing.orchestrators.runtime_orchestration import (
    CHILD_CAPABILITIES,
    CapabilityIdentity,
    ChildSpec,
    OrchestrationContractError,
    aggregate_child_outputs,
    admit_runtime_handoff,
    read_runtime_events,
    build_runtime_handoff,
    derive_child_idempotency_key,
    derive_stitch_idempotency_key,
)


ROOT_DIGEST = "sha256:" + "1" * 64
TRAVEL_DIGEST = "sha256:" + "2" * 64
INDIVIDUAL_DIGEST = "sha256:" + "3" * 64
STITCH_DIGEST = "sha256:" + "4" * 64


def _travel_handoff():
    return build_runtime_handoff(
        project="demo",
        root_name="travel_orchestrator",
        root_digest=ROOT_DIGEST,
        root_input_object_ids=["cas-first", "cas-last"],
        root_params={"continuity": "first_last"},
        children=(
            ChildSpec(
                "segment", 0, CapabilityIdentity(CHILD_CAPABILITIES["travel_segment"], TRAVEL_DIGEST),
                ("cas-first", "cas-last"), {"prompt": "a"},
            ),
            ChildSpec(
                "individual", 1, CapabilityIdentity(CHILD_CAPABILITIES["individual_travel_segment"], INDIVIDUAL_DIGEST),
                ("cas-middle",), {"prompt": "b"},
            ),
        ),
        stitch_digest=STITCH_DIGEST,
        output_policy={"publish": "one_cas_object"},
        settlement_effect={"kind": "lineage", "source": "root_task"},
        child_settlement_effect={"kind": "lineage", "source": "child_task"},
        stitch_settlement_effect={"kind": "lineage", "source": "stitch_task"},
    )


def test_handoff_emits_exact_identities_ordered_cas_edges_aggregation_and_effect():
    handoff = _travel_handoff()
    data = handoff.to_dict()
    assert data["root"]["capability_id"] == "video_editing.travel_orchestrator"
    assert [row["capability"]["capability_id"] for row in data["children"]] == [
        "video_editing.travel_segment", "video_editing.individual_travel_segment"
    ]
    assert data["stitch"]["capability_id"] == "rendering.travel_stitch"
    assert data["root_input_object_ids"] == ["cas-first", "cas-last"]
    assert [row["input_object_ids"] for row in data["children"]] == [["cas-first", "cas-last"], ["cas-middle"]]
    assert len(data["dependency_edges"]) == 4
    assert data["aggregation"]["source"] == "runtime.events"
    assert data["settlement_effect"] == {"kind": "lineage", "source": "root_task"}


def test_idempotency_is_attempt_independent_and_transport_only():
    handoff = _travel_handoff()
    first = handoff.child_admissions(root_task_id="runtime-root-1")
    second = handoff.child_admissions(root_task_id="runtime-root-1")
    assert [item.idempotency_key for item in first] == [item.idempotency_key for item in second]
    assert first[0].idempotency_key == "astrid.orchestration:v1:runtime-root-1:segment:0"
    assert all("idempotency_key" not in item.body for item in first)
    assert json.loads(first[0].canonical_bytes)["input_object_ids"] == ["cas-first", "cas-last"]
    assert first[0].body["settlement_effect"] == {"kind": "lineage", "source": "child_task"}


def test_edit_root_is_explicitly_childless_and_stitchless():
    handoff = build_runtime_handoff(
        project="demo",
        root_name="edit_video_orchestrator",
        root_digest=ROOT_DIGEST,
        root_input_object_ids=["cas-video"],
        root_params={"edit": "replace"},
        settlement_effect={"kind": "lineage", "source": "root_task"},
    )
    assert handoff.children == ()
    assert handoff.stitch is None
    assert handoff.dependency_edges == ()


def test_unknown_child_and_digest_fail_closed():
    with pytest.raises(OrchestrationContractError):
        build_runtime_handoff(
            project="demo",
            root_name="join_clips_orchestrator", root_digest="not-a-digest",
            root_input_object_ids=[], root_params={},
        )
    with pytest.raises(OrchestrationContractError):
        build_runtime_handoff(
            project="demo",
            root_name="join_clips_orchestrator", root_digest=ROOT_DIGEST,
            root_input_object_ids=[], root_params={},
            children=(ChildSpec("wrong", 0, CapabilityIdentity("video_editing.travel_segment", TRAVEL_DIGEST), (), {}),),
            stitch_digest=STITCH_DIGEST,
            settlement_effect={"kind": "lineage", "source": "root_task"},
            child_settlement_effect={"kind": "lineage", "source": "child_task"},
            stitch_settlement_effect={"kind": "lineage", "source": "stitch_task"},
        )

    with pytest.raises(OrchestrationContractError):
        build_runtime_handoff(
            project="demo",
            root_name="travel_orchestrator", root_digest=ROOT_DIGEST,
            root_input_object_ids=[], root_params={}, stitch_digest=STITCH_DIGEST,
            children=(ChildSpec(
                "segment", 0,
                CapabilityIdentity("evil.video_editing.travel_segment", TRAVEL_DIGEST), (), {},
            ),),
            settlement_effect={"kind": "lineage", "source": "root_task"},
            child_settlement_effect={"kind": "lineage", "source": "child_task"},
            stitch_settlement_effect={"kind": "lineage", "source": "stitch_task"},
        )

    with pytest.raises(OrchestrationContractError):
        build_runtime_handoff(
            project="demo", root_name="edit_video_orchestrator", root_digest=ROOT_DIGEST,
            root_input_object_ids=[], root_params={},
        )


def test_aggregation_reads_runtime_events_in_declared_child_order():
    handoff = _travel_handoff()
    events = [
        {"event_type": "task.succeeded", "payload": {"task_id": "child-2", "role": "individual", "index": 1, "outputs": ["cas-2"]}},
        {"event_type": "task.succeeded", "payload": {"task_id": "child-1", "role": "segment", "index": 0, "outputs": ["cas-1"]}},
    ]
    result = aggregate_child_outputs(handoff, events, child_task_ids=["child-1", "child-2"])
    assert [row["slot"] for row in result] == ["segment:0", "individual:1"]
    assert [row["payload"]["task_id"] for row in result] == ["child-1", "child-2"]


def test_aggregation_is_bound_to_admitted_ids_and_wraps_bad_events():
    handoff = _travel_handoff()
    unrelated = [{"event_type": "task.succeeded", "payload": {"task_id": "other", "role": "segment", "index": 0, "outputs": ["cas-other"]}}]
    with pytest.raises(OrchestrationContractError):
        aggregate_child_outputs(handoff, unrelated, child_task_ids=["child-1", "child-2"])
    malformed = [{"event_type": "task.succeeded", "payload": {"task_id": "child-1", "role": "segment", "index": "bad", "outputs": ["cas-1"]}}]
    with pytest.raises(OrchestrationContractError):
        aggregate_child_outputs(handoff, malformed, child_task_ids=["child-1", "child-2"])


def test_child_key_rejects_bad_index():
    with pytest.raises(OrchestrationContractError):
        derive_child_idempotency_key("root", "segment", -1)
    assert derive_stitch_idempotency_key("root") == "astrid.orchestration:v1:root:stitch:0"


def test_runtime_adapter_admits_root_and_children_and_reads_events():
    handoff = _travel_handoff()

    class Tasks:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return {"task_id": f"task-{len(self.calls)}"}

    class Runs:
        def events(self, project, run_id):
            assert (project, run_id) == ("demo", "task-1")
            return [
                {"event_type": "task.succeeded", "payload": {"task_id": "task-3", "role": "individual", "index": 1, "outputs": ["cas-2"]}},
                {"event_type": "task.succeeded", "payload": {"task_id": "task-2", "role": "segment", "index": 0, "outputs": ["cas-1"]}},
            ]

    class Client:
        tasks = Tasks()
        runs = Runs()

    client = Client()
    root_id, child_ids, stitch_id = admit_runtime_handoff(client, handoff, root_idempotency_key="root-key")
    assert (root_id, child_ids, stitch_id) == ("task-1", ("task-2", "task-3"), "task-4")
    assert [call["project_id"] for call in client.tasks.calls] == ["demo", "demo", "demo", "demo"]
    assert client.tasks.calls[1]["capability_digest"] == TRAVEL_DIGEST
    assert client.tasks.calls[0]["settlement_effect"] == {"kind": "lineage", "source": "root_task"}
    assert client.tasks.calls[3]["capability"] == "rendering.travel_stitch"
    assert client.tasks.calls[3]["input_manifest"] == ["cas-1", "cas-2"]
    assert client.tasks.calls[3]["settlement_effect"] == {"kind": "lineage", "source": "stitch_task"}
    assert read_runtime_events(client, "demo", "task-1")[0]["event_type"] == "task.succeeded"
