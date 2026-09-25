"""Compiled H3 inventory and final-publication output contract."""

from __future__ import annotations

from typing import Any, Mapping


class OutputContractError(ValueError):
    """A compiled graph cannot be admitted under its declared output contract."""


def build_output_contract(graph_outputs: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a one-generation contract from compiler-owned graph outputs.

    ``graph_outputs`` is ordered as the selected workflow publishes its files.
    Exactly one video is public; any additional declared stream is internal
    composition material and is not a second public generation.
    """
    outputs = [dict(row) for row in graph_outputs]
    if not outputs:
        raise OutputContractError("compiled workflow declares no outputs")
    if any(row.get("expected_cardinality") != "one" for row in outputs):
        raise OutputContractError("every compiled workflow output must declare cardinality one")
    videos = [row for row in outputs if row.get("modality") == "video"]
    if len(videos) != 1:
        raise OutputContractError("compiled H3 workflow must declare exactly one video output")
    for index, row in enumerate(outputs):
        if row.get("modality") not in {"video", "audio"}:
            raise OutputContractError(f"compiled output {index} has unsupported modality")
        row["output_port"] = "vibecomfy_run"
        row["ordinal"] = index
        row["role"] = "primary" if row["modality"] == "video" else "internal"
    primary = videos[0]
    primary_index = outputs.index(primary)
    # Keep the primary video at ordinal zero because the Runtime's generation
    # selector binds the original inventory ordinal, not a later display order.
    if primary_index != 0:
        raise OutputContractError("the primary video must be the first compiled workflow output")
    # The raw graph inventory remains owned by vibecomfy.run.  The public
    # selector deliberately names the later verify result so a raw inference
    # task can never acquire the H3 generation effect by accident.
    inference_outputs = [dict(row) for row in outputs]
    return {
        "schema_version": 2,
        "inference": {
            "output_port": "vibecomfy_run",
            "graph_outputs": inference_outputs,
        },
        # Keep this projection at the top level for the existing VibeComfy
        # inventory validator.  It is not the publication port.
        "output_port": "vibecomfy_run",
        "graph_outputs": outputs,
        "public_generation": {
            "final_output_port": "verified_candidate",
            "inference_output_port": "vibecomfy_run",
            "primary_outputs": [{
                "output_port": "verified_candidate",
                "ordinal": 0,
                "group_key": "main",
                "selector": "main-0",
                "variant_key": "original",
                "modality": "video",
                "required": True,
            }],
            "internal_outputs": [
                {"output_port": "vibecomfy_run", "ordinal": row["ordinal"], "modality": row["modality"]}
                for row in outputs if row["role"] == "internal"
            ],
        },
    }


def validate_output_contract(value: Any) -> dict[str, Any]:
    """Validate raw graph accounting and the one-final-output invariant."""
    if not isinstance(value, Mapping) or value.get("schema_version") not in {1, 2}:
        raise OutputContractError("compiled output contract must use schema_version 1 or 2")
    schema_version = value["schema_version"]
    graph_outputs = value.get("graph_outputs")
    public = value.get("public_generation")
    if not isinstance(graph_outputs, list) or not graph_outputs:
        raise OutputContractError("compiled output contract must declare graph_outputs")
    if not isinstance(public, Mapping):
        raise OutputContractError("compiled output contract is missing public_generation")
    primary = public.get("primary_outputs")
    internal = public.get("internal_outputs")
    if not isinstance(primary, list) or len(primary) != 1:
        raise OutputContractError("public_generation must declare exactly one primary output")
    if not isinstance(internal, list):
        raise OutputContractError("public_generation.internal_outputs must be an array")
    if schema_version == 2:
        if value.get("output_port") != "vibecomfy_run":
            raise OutputContractError("schema_version 2 raw output_port must be vibecomfy_run")
        inference = value.get("inference")
        if not isinstance(inference, Mapping) or inference.get("output_port") != "vibecomfy_run":
            raise OutputContractError("schema_version 2 must declare the raw inference projection")
        if public.get("final_output_port") != "verified_candidate":
            raise OutputContractError("schema_version 2 final output must be verified_candidate")
        if public.get("inference_output_port") != "vibecomfy_run":
            raise OutputContractError("schema_version 2 must separate inference and publication ports")
    elif public.get("final_output_port") is not None:
        raise OutputContractError("schema_version 1 cannot declare a final publication port")
    declared = [*primary, *internal]
    if len(declared) != len(graph_outputs):
        raise OutputContractError(
            "compiled graph output cardinality does not match its public/internal output contract"
        )
    if schema_version == 2 and inference.get("graph_outputs") != graph_outputs:
        raise OutputContractError("inference projection does not match graph_outputs")
    identities: set[tuple[str, int]] = set()
    for index, output in enumerate(graph_outputs):
        if not isinstance(output, Mapping):
            raise OutputContractError(f"graph_outputs[{index}] must be an object")
        port = output.get("output_port")
        ordinal = output.get("ordinal")
        if not isinstance(port, str) or not port or type(ordinal) is not int or ordinal < 0:
            raise OutputContractError(f"graph_outputs[{index}] has an invalid port/ordinal")
        identity = (port, ordinal)
        if identity in identities:
            raise OutputContractError(f"graph output {identity!r} is declared more than once")
        identities.add(identity)
        if output.get("expected_cardinality") != "one":
            raise OutputContractError(f"graph_outputs[{index}] must have expected_cardinality=one")
    expected_primary = graph_outputs[0]
    primary_row = primary[0]
    primary_fields = ("ordinal", "modality") if schema_version == 2 else ("output_port", "ordinal", "modality")
    for field in primary_fields:
        if primary_row.get(field) != expected_primary.get(field):
            raise OutputContractError("primary output does not match graph output ordinal zero")
    if primary_row.get("modality") != "video":
        raise OutputContractError("the single public primary output must be video")
    if schema_version == 2:
        if primary_row.get("output_port") != "verified_candidate":
            raise OutputContractError("schema_version 2 primary output must use verified_candidate")
        if (
            primary_row.get("group_key") != "main"
            or primary_row.get("selector") != "main-0"
            or primary_row.get("ordinal") != 0
            or primary_row.get("variant_key") != "original"
            or primary_row.get("required") is not True
        ):
            raise OutputContractError("schema_version 2 must seal selector main-0/original at ordinal 0")
    expected_internal = [
        {"output_port": row.get("output_port"), "ordinal": row.get("ordinal"), "modality": row.get("modality")}
        for row in graph_outputs[1:]
    ]
    if internal != expected_internal:
        raise OutputContractError("internal output declarations do not match compiled graph outputs")
    return dict(value)


def generation_intent_from_contract(
    value: Any,
    *,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Derive Runtime generation selectors only from the validated contract."""
    contract = validate_output_contract(value)
    selectors = contract["public_generation"]["primary_outputs"]
    primary = selectors[0]
    return {
        "version": 1,
        "modality": "video",
        "partial_success_policy": "reject",
        "groups": [{
            "group_key": primary["group_key"],
            "selectors": [{
                "selector": primary["selector"],
                "ordinal": primary["ordinal"],
                "variant_key": primary["variant_key"],
                "required": primary["required"],
            }],
        }],
        "metadata": dict(metadata or {}),
    }


__all__ = [
    "OutputContractError",
    "build_output_contract",
    "generation_intent_from_contract",
    "validate_output_contract",
]
