from __future__ import annotations

import pytest

from astrid.packs.h3_av.src.output_contract import (
    OutputContractError,
    build_output_contract,
    generation_intent_from_contract,
    validate_output_contract,
)


def test_four_video_outputs_cannot_be_admitted_as_one_public_selector() -> None:
    graph_outputs = [
        {"name": f"segment-{index}", "modality": "video", "expected_cardinality": "one"}
        for index in range(4)
    ]

    with pytest.raises(OutputContractError, match="exactly one video output"):
        build_output_contract(graph_outputs)


def test_contract_rejects_unaccounted_graph_output_before_child_admission() -> None:
    contract = build_output_contract([
        {"name": "video", "modality": "video", "expected_cardinality": "one"},
    ])
    contract["graph_outputs"].extend([
        {"name": f"segment-{index}", "modality": "video", "expected_cardinality": "one", "output_port": "vibecomfy_run", "ordinal": index + 1, "role": "internal"}
        for index in range(3)
    ])

    with pytest.raises(OutputContractError, match="cardinality does not match"):
        validate_output_contract(contract)


def test_generation_intent_is_derived_from_the_single_compiled_primary() -> None:
    contract = build_output_contract([
        {"name": "video", "modality": "video", "expected_cardinality": "one"},
        {"name": "audio", "modality": "audio", "expected_cardinality": "one"},
    ])

    intent = generation_intent_from_contract(contract, metadata={"test": "receipt"})

    assert intent["groups"][0]["selectors"] == [{
        "selector": "main-0",
        "ordinal": 0,
        "variant_key": "original",
        "required": True,
    }]
    assert contract["public_generation"]["internal_outputs"] == [
        {"output_port": "vibecomfy_run", "ordinal": 1, "modality": "audio"}
    ]
