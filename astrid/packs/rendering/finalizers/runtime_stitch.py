"""Runtime-owned stitch finalizer admission contract.

The finalizer receives ordered Runtime CAS outputs and Runtime event-derived
dependency edges.  It only emits typed admission data; the Runtime owns
claiming, execution lifecycle, publication, and fenced settlement.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from astrid.packs.video_editing.orchestrators.runtime_orchestration import (
    CapabilityIdentity,
    OrchestrationContractError,
    RuntimeAdmission,
    SCHEMA_VERSION,
    STITCH_CAPABILITIES,
    STITCH_FAMILY,
)


def build_stitch_admission(
    *,
    project: str,
    stitch_name: str,
    stitch_digest: str,
    root_task_id: str,
    child_task_ids: Sequence[str],
    input_object_ids: Sequence[str],
    output_policy: Mapping[str, Any] | None = None,
    settlement_effect: Mapping[str, Any] | None = None,
    idempotency_key: str,
) -> RuntimeAdmission:
    """Create the finalizer HC-04 body with Runtime event dependencies."""

    if stitch_name not in STITCH_CAPABILITIES:
        raise OrchestrationContractError(f"unknown stitch finalizer {stitch_name!r}")
    root_task_id = _string(root_task_id, "root_task_id")
    child_task_ids = tuple(_string(value, f"child_task_ids[{i}]") for i, value in enumerate(child_task_ids))
    input_object_ids = tuple(_string(value, f"input_object_ids[{i}]") for i, value in enumerate(input_object_ids))
    if len(set(child_task_ids)) != len(child_task_ids):
        raise OrchestrationContractError("child_task_ids must be unique and ordered")
    if len(set(input_object_ids)) != len(input_object_ids):
        raise OrchestrationContractError("input_object_ids must be unique and ordered")
    identity = CapabilityIdentity(STITCH_CAPABILITIES[stitch_name], stitch_digest)
    edges = [
        {"from_task_id": task_id, "to": "self", "requires_event": "task.succeeded", "fence": "runtime_task"}
        for task_id in child_task_ids
    ]
    return RuntimeAdmission(
        body={
            "project": _string(project, "project"),
            "capability_id": identity.capability_id,
            "capability_digest": identity.capability_digest,
            "schema_version": SCHEMA_VERSION,
            "input_object_ids": list(input_object_ids),
            "spec": {
                "family": STITCH_FAMILY,
                "params": {"root_task_id": root_task_id, "child_task_ids": list(child_task_ids)},
                "output_policy": dict(output_policy or {}),
                "runtime_dependencies": {
                    "edges": edges,
                    "event_source": "runtime.events",
                    "aggregation": {
                        "kind": "ordered_cas_inputs",
                        "order": list(input_object_ids),
                    },
                },
            },
            "storage_estimate": {"estimated_scratch_bytes": 0, "estimated_output_bytes": 0},
            "settlement_effect": _typed_settlement_effect(settlement_effect),
        },
        idempotency_key=idempotency_key,
    )


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrchestrationContractError(f"{field} must be a non-empty string")
    return value


def _typed_settlement_effect(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise OrchestrationContractError("settlement_effect must be a non-empty typed settlement effect")
    return dict(value)


__all__ = ["build_stitch_admission"]
