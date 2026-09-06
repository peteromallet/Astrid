from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from astrid.packs.vibecomfy.src.dimensional_ltx import (
    ALL_ROUTE_KEYS,
    FIRST_LAST_TEMPLATE_ID,
    ICLORA_TEMPLATE_ID,
    NEGATIVE_ROUTE_KEYS,
    SUPPORTED_ROUTE_KEYS,
    LtxRequest,
    compile_dimensional_ltx,
)


def request_for(route_key: str, **overrides: object) -> dict[str, object]:
    request: dict[str, object] = {
        "route_key": route_key,
        "prompt": "a continuous camera move through a sunlit room",
        "negative_prompt": "blurry, low quality",
        "seed": 17,
        "width": 1024,
        "height": 576,
        "frames": 81,
        "fps": 24,
        "start_image_object_id": "cas:start-frame-01",
        "end_image_object_id": "cas:end-frame-01",
    }
    if "ltx_control_" in route_key:
        request["guide_object_id"] = "cas:guide-video-01"
    request.update(overrides)
    return request


def test_fixture_coverage_is_exact_and_unique() -> None:
    assert len(SUPPORTED_ROUTE_KEYS) == 6
    assert len(NEGATIVE_ROUTE_KEYS) == 2
    assert len(ALL_ROUTE_KEYS) == 8
    assert len(set(ALL_ROUTE_KEYS)) == len(ALL_ROUTE_KEYS)
    assert set(ALL_ROUTE_KEYS) == set(SUPPORTED_ROUTE_KEYS) | set(NEGATIVE_ROUTE_KEYS)


@pytest.mark.parametrize("route_key", SUPPORTED_ROUTE_KEYS)
def test_every_supported_row_compiles_to_typed_task(route_key: str) -> None:
    result = compile_dimensional_ltx(request_for(route_key))

    assert result.accepted
    assert result.rejection is None
    assert result.fallback_template_id is None
    assert result.task is not None
    task = result.task
    assert task.route_key == route_key
    assert task.capability_id == "vibecomfy.dimensional_ltx"
    assert task.semantic_family in {"ltx_first_last", "ltx_iclora"}
    assert task.template_id in {FIRST_LAST_TEMPLATE_ID, ICLORA_TEMPLATE_ID}
    assert task.input_object_ids[:2] == ("cas:start-frame-01", "cas:end-frame-01")
    assert task.bindings["start_image"]["object_id"] == "cas:start-frame-01"
    assert task.bindings["end_image"]["object_id"] == "cas:end-frame-01"
    assert task.as_dict()["input_object_ids"] == list(task.input_object_ids)


@pytest.mark.parametrize(
    ("route_key", "model_id"),
    [
        (SUPPORTED_ROUTE_KEYS[0], "ltx2"),
        (SUPPORTED_ROUTE_KEYS[1], "ltx2_distilled"),
    ],
)
def test_first_last_preserves_base_and_distilled_model_identity(
    route_key: str, model_id: str
) -> None:
    task = compile_dimensional_ltx(request_for(route_key)).task
    assert task is not None
    assert task.semantic_family == "ltx_first_last"
    assert task.model_id == model_id
    assert task.control_identity is None
    assert set(task.bindings) == {"start_image", "end_image"}
    assert task.template_id == FIRST_LAST_TEMPLATE_ID


@pytest.mark.parametrize(
    ("route_key", "control_identity"),
    [
        (SUPPORTED_ROUTE_KEYS[2], "ltx_control_pose"),
        (SUPPORTED_ROUTE_KEYS[3], "ltx_control_depth"),
        (SUPPORTED_ROUTE_KEYS[4], "ltx_control_canny"),
        (SUPPORTED_ROUTE_KEYS[5], "ltx_control_cameraman"),
    ],
)
def test_iclora_preserves_control_identity_and_ordered_guide(
    route_key: str, control_identity: str
) -> None:
    task = compile_dimensional_ltx(request_for(route_key)).task
    assert task is not None
    assert task.semantic_family == "ltx_iclora"
    assert task.model_id == "ltx2_distilled"
    assert task.control_identity == control_identity
    assert task.template_id == ICLORA_TEMPLATE_ID
    assert task.input_object_ids == (
        "cas:start-frame-01",
        "cas:end-frame-01",
        "cas:guide-video-01",
    )
    assert task.bindings["guide_video"]["kind"] == "video"
    assert task.bindings["guide_video"]["object_id"] == "cas:guide-video-01"


@pytest.mark.parametrize("route_key", NEGATIVE_ROUTE_KEYS)
def test_negative_rows_fail_closed_with_no_compiled_task_or_fallback(route_key: str) -> None:
    result = compile_dimensional_ltx(request_for(route_key, guide_object_id="cas:guide-video-01"))

    assert not result.accepted
    assert result.task is None
    assert result.fallback_template_id is None
    assert result.rejection is not None
    assert result.rejection.code == "unsupported_semantic_family"
    assert result.rejection.reason
    assert "generic" not in result.rejection.reason.lower()
    assert "template" not in result.rejection.reason.lower() or route_key == NEGATIVE_ROUTE_KEYS[1]


def test_raw_control_negative_reason_is_typed_and_deterministic() -> None:
    route_key = NEGATIVE_ROUTE_KEYS[0]
    first = compile_dimensional_ltx(request_for(route_key))
    second = compile_dimensional_ltx(request_for(route_key))

    assert first == second
    assert first.rejection is not None
    assert first.rejection.reason == (
        "ltx_raw_control_video is unsupported pending a typed raw-guide contract"
    )


def test_unknown_route_cannot_select_a_generic_template() -> None:
    result = compile_dimensional_ltx(request_for("travel_segment__unknown"))

    assert result.task is None
    assert result.fallback_template_id is None
    assert result.rejection is not None
    assert result.rejection.code == "unsupported_route"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("seed", True),
        ("width", 0),
        ("height", "576"),
        ("frames", -1),
        ("fps", 0),
        ("prompt", ""),
        ("template_id", "arbitrary/workflow"),
    ],
)
def test_invalid_or_unallowlisted_fields_are_rejected(field: str, value: object) -> None:
    result = compile_dimensional_ltx(request_for(SUPPORTED_ROUTE_KEYS[0], **{field: value}))

    assert result.task is None
    assert result.rejection is not None
    assert result.rejection.code == "invalid_request"


def test_missing_iclora_guide_is_rejected_before_compilation() -> None:
    result = compile_dimensional_ltx(request_for(SUPPORTED_ROUTE_KEYS[2], guide_object_id=None))

    assert result.task is None
    assert result.rejection is not None
    assert result.rejection.code == "missing_required_cas_input"
    assert result.rejection.reason == (
        "ltx_iclora requires guide_object_id for ltx_control_pose"
    )


def test_first_last_rejects_a_guide_that_has_no_typed_binding() -> None:
    result = compile_dimensional_ltx(request_for(SUPPORTED_ROUTE_KEYS[0], guide_object_id="cas:guide"))

    assert result.task is None
    assert result.rejection is not None
    assert result.rejection.code == "invalid_request"


@pytest.mark.parametrize("field", ["start_image_object_id", "end_image_object_id"])
def test_missing_first_last_cas_input_is_rejected(field: str) -> None:
    result = compile_dimensional_ltx(request_for(SUPPORTED_ROUTE_KEYS[0], **{field: None}))

    assert result.task is None
    assert result.rejection is not None
    assert result.rejection.code == "missing_required_cas_input"


def test_local_paths_cannot_become_durable_input_identity() -> None:
    result = compile_dimensional_ltx(
        request_for(SUPPORTED_ROUTE_KEYS[0], start_image_object_id="/tmp/frame.png")
    )

    assert result.task is None
    assert result.rejection is not None
    assert result.rejection.code == "invalid_request"


    payload = request_for(SUPPORTED_ROUTE_KEYS[2])
    typed = LtxRequest(**cast(dict[str, Any], payload))

    from_mapping = compile_dimensional_ltx(payload)
    from_dataclass = compile_dimensional_ltx(typed)

    assert from_mapping == from_dataclass
    assert from_dataclass.task is not None
    assert from_dataclass.task.as_dict()["bindings"]["guide_video"] == {
        "kind": "video",
        "object_id": "cas:guide-video-01",
    }


def test_compiled_payload_contains_no_machine_local_readiness_fields() -> None:
    task = compile_dimensional_ltx(request_for(SUPPORTED_ROUTE_KEYS[2])).task
    assert task is not None
    payload = task.as_dict()
    serialized = repr(payload)
    for forbidden in ("/tmp/", "127.0.0.1", "python", "port", "pack_root"):
        assert forbidden not in serialized


def test_request_dataclass_remains_immutable() -> None:
    request = LtxRequest(**cast(dict[str, Any], request_for(SUPPORTED_ROUTE_KEYS[0])))
    with pytest.raises(FrozenInstanceError):
        request.route_key = "unsupported"  # type: ignore[misc]

