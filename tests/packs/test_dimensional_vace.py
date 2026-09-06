from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from astrid.packs.vibecomfy.src.dimensional_vace import (
    ALLOWLISTED_TEMPLATE_IDS,
    DimensionalVaceError,
    I2V_TEMPLATE_ID,
    ROUTE_FIXTURES,
    SUPPORTED_ROUTE_KEYS,
    UnsupportedDimensionalRoute,
    VACE_TEMPLATE_ID,
    compile_dimensional_request,
)


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "dimensional_vace_routes.json"


def _rows() -> list[dict[str, object]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["routes"]


def _request(row: dict[str, object]) -> dict[str, object]:
    return {
        key: row[key]
        for key in (
            "family",
            "operation",
            "model",
            "guidance",
            "continuity",
            "profile",
            "input_object_ids",
        )
    } | {"prompt": "a deterministic test shot"}


def test_fixture_enumerates_exact_frozen_routes_without_duplicates() -> None:
    rows = _rows()
    keys = [str(row["route_key"]) for row in rows]
    assert len(rows) == 16
    assert len(set(keys)) == 16
    assert set(keys) == SUPPORTED_ROUTE_KEYS
    assert tuple(row.route_key for row in ROUTE_FIXTURES) == tuple(keys)


def test_every_frozen_row_selects_allowlisted_template_and_typed_bindings() -> None:
    for row in _rows():
        compiled = compile_dimensional_request(_request(row))
        expected_roles = cast(list[str], row["expected_input_roles"])
        input_ids = cast(list[str], row["input_object_ids"])
        assert tuple(
            key for key in compiled.bindings if key in {"first_image", "last_image", "guidance_video", "video_source", "left_clip", "right_clip"}
        ) == tuple(expected_roles)
        assert compiled.result_semantics.output_kind == row["expected_output_kind"]
        assert compiled.input_object_ids == tuple(input_ids)
        assert "route_key" not in compiled.as_dict()
        assert "path" not in json.dumps(compiled.as_dict())


def test_compilation_is_deterministic_and_preserves_cas_order() -> None:
    row = _rows()[2]
    request = _request(row)
    first = compile_dimensional_request(request)
    second = compile_dimensional_request(dict(request))
    assert first.as_dict() == second.as_dict()
    assert first.input_object_ids == (
        "cas-image-first",
        "cas-image-last",
        "cas-source-flow",
    )
    assert first.bindings["first_image"] == "cas-image-first"
    assert first.bindings["last_image"] == "cas-image-last"
    assert first.bindings["video_source"] == "cas-source-flow"


def test_semantic_families_have_distinct_result_contracts() -> None:
    compiled = [compile_dimensional_request(_request(row)) for row in _rows()]
    by_family = {item.semantic_family: item for item in compiled}
    assert by_family["wan_i2v_first_last"].template_id == I2V_TEMPLATE_ID
    assert by_family["wan_vace_travel"].result_semantics.output_kind == "travel_segment"
    assert by_family["wan_vace_individual"].result_semantics.output_kind == "individual_segment"
    assert by_family["wan_vace_join_bridge"].result_semantics.output_kind == "join_bridge"
    assert by_family["wan_vace_join_bridge"].result_semantics.continuity == "join_bridge"
    assert {item.template_id for item in compiled if item.semantic_family != "wan_i2v_first_last"} == {VACE_TEMPLATE_ID}


@pytest.mark.parametrize(
    "bad_patch, message",
    [
        ({"unknown": True}, "unknown request field"),
        ({"family": "wan_vace_travel", "guidance": "uni3c"}, "unsupported dimensional route"),
        ({"profile": "fast"}, "unsupported dimensional route"),
        ({"input_object_ids": []}, "requires"),
        ({"input_object_ids": ["cas-a", "cas-b", "/tmp/local.mp4"]}, "machine-local path"),
    ],
)
def test_invalid_fields_and_inputs_fail_closed(bad_patch: dict[str, object], message: str) -> None:
    request = _request(_rows()[1])
    request.update(bad_patch)
    error_type = UnsupportedDimensionalRoute if message == "unsupported dimensional route" else DimensionalVaceError
    with pytest.raises(error_type, match=message):
        compile_dimensional_request(request)


def test_missing_required_fields_fail_before_template_selection() -> None:
    request = _request(_rows()[0])
    del request["prompt"]
    with pytest.raises(DimensionalVaceError, match="missing required field.*prompt"):
        compile_dimensional_request(request)


def test_unsupported_semantic_combinations_have_no_fallback() -> None:
    request = _request(_rows()[0])
    request.update({"family": "wan_i2v_first_last", "continuity": "video_source"})
    with pytest.raises(UnsupportedDimensionalRoute, match="unsupported dimensional route"):
        compile_dimensional_request(request)


def test_numeric_shape_is_typed_and_deterministic() -> None:
    request = _request(_rows()[0])
    request.update({"width": 1024, "height": 576, "frames": 81, "fps": 24, "steps": 8, "seed": 7})
    compiled = compile_dimensional_request(request)
    assert compiled.bindings["width"] == 1024
    assert compiled.bindings["height"] == 576
    assert compiled.bindings["frames"] == 81
    assert compiled.bindings["fps"] == 24
    assert compiled.bindings["steps"] == 8
    assert compiled.bindings["seed"] == 7
    with pytest.raises(DimensionalVaceError, match="divisible by 8"):
        compile_dimensional_request(request | {"width": 1023})
