"""Typed Runtime contract for the migrated Reigh orchestration families.

This module describes Runtime task admissions; it does not own task lifecycle,
persist a graph, or execute an engine.  The Runtime owns task identity,
dependency gating, event ordering, retries, and fenced settlement.  The pack
only supplies typed capability/specification data and deterministic transport
keys for child replay.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

SCHEMA_VERSION = "1"
CHILD_KEY_PREFIX = "astrid.orchestration:v1"
ROOT_FAMILY = "orchestration_roots"
CHILD_FAMILY = "generic_child_generation"
STITCH_FAMILY = "stitch_finalization"

ROOT_CAPABILITIES = {
    "travel_orchestrator": "video_editing.travel_orchestrator",
    "join_clips_orchestrator": "video_editing.join_clips_orchestrator",
    "edit_video_orchestrator": "video_editing.edit_video_orchestrator",
}
CHILD_CAPABILITIES = {
    "travel_segment": "video_editing.travel_segment",
    "individual_travel_segment": "video_editing.individual_travel_segment",
    "join_clips_segment": "video_editing.join_clips_segment",
}
STITCH_CAPABILITIES = {
    "travel_stitch": "rendering.travel_stitch",
    "join_final_stitch": "rendering.join_final_stitch",
}
_ALLOWED_CHILDREN = {
    "travel_orchestrator": frozenset({"travel_segment", "individual_travel_segment"}),
    "join_clips_orchestrator": frozenset({"join_clips_segment"}),
    "edit_video_orchestrator": frozenset(),
}
_ROOT_STITCH = {
    "travel_orchestrator": "travel_stitch",
    "join_clips_orchestrator": "join_final_stitch",
}


class OrchestrationContractError(ValueError):
    """A typed orchestration contract cannot be represented safely."""


def _non_empty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrchestrationContractError(f"{field} must be a non-empty string")
    return value


def _digest(value: Any, field: str) -> str:
    value = _non_empty(value, field)
    if not value.startswith("sha256:") or len(value) != 71:
        raise OrchestrationContractError(f"{field} must be a sha256: digest")
    try:
        int(value[7:], 16)
    except ValueError as exc:
        raise OrchestrationContractError(f"{field} must be a sha256: digest") from exc
    return value


def _object_ids(value: Sequence[str], field: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)):
        raise OrchestrationContractError(f"{field} must be an ordered object-id list")
    result = tuple(_non_empty(item, f"{field}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise OrchestrationContractError(f"{field} must not contain duplicate object IDs")
    return result


@dataclass(frozen=True)
class CapabilityIdentity:
    capability_id: str
    capability_digest: str

    def __post_init__(self) -> None:
        _non_empty(self.capability_id, "capability_id")
        _digest(self.capability_digest, "capability_digest")

    def to_dict(self) -> dict[str, str]:
        return {
            "capability_id": self.capability_id,
            "capability_digest": self.capability_digest,
        }


@dataclass(frozen=True)
class ChildSpec:
    role: str
    index: int
    capability: CapabilityIdentity
    input_object_ids: tuple[str, ...]
    params: Mapping[str, Any]

    def __post_init__(self) -> None:
        _non_empty(self.role, "child.role")
        if isinstance(self.index, bool) or not isinstance(self.index, int) or self.index < 0:
            raise OrchestrationContractError("child.index must be a non-negative integer")
        _object_ids(self.input_object_ids, "child.input_object_ids")
        if not isinstance(self.params, Mapping):
            raise OrchestrationContractError("child.params must be an object")

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "index": self.index,
            "capability": self.capability.to_dict(),
            "input_object_ids": list(self.input_object_ids),
            "params": dict(self.params),
        }


@dataclass(frozen=True)
class RuntimeAdmission:
    """Logical HC-04 body plus its transport-only idempotency key."""

    body: Mapping[str, Any]
    idempotency_key: str

    def __post_init__(self) -> None:
        _non_empty(self.idempotency_key, "idempotency_key")
        if "idempotency_key" in self.body:
            raise OrchestrationContractError("idempotency_key is transport-only")

    @property
    def canonical_bytes(self) -> bytes:
        return json.dumps(self.body, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class RuntimeOrchestrationHandoff:
    """Producer-facing, immutable description of one root dependency graph."""

    project: str
    root_name: str
    root: CapabilityIdentity
    root_input_object_ids: tuple[str, ...]
    root_params: Mapping[str, Any]
    children: tuple[ChildSpec, ...]
    stitch: CapabilityIdentity | None
    output_policy: Mapping[str, Any]
    settlement_effect: Mapping[str, Any]

    def __post_init__(self) -> None:
        _non_empty(self.project, "project")
        if self.root_name not in ROOT_CAPABILITIES:
            raise OrchestrationContractError(f"unknown orchestration root {self.root_name!r}")
        if self.root.capability_id != ROOT_CAPABILITIES[self.root_name]:
            raise OrchestrationContractError("root capability identity does not match root route")
        _object_ids(self.root_input_object_ids, "root_input_object_ids")
        if not isinstance(self.root_params, Mapping):
            raise OrchestrationContractError("root_params must be an object")
        if not isinstance(self.output_policy, Mapping):
            raise OrchestrationContractError("output_policy must be an object")
        if not isinstance(self.settlement_effect, Mapping):
            raise OrchestrationContractError("settlement_effect must be an object")
        allowed = _ALLOWED_CHILDREN[self.root_name]
        seen_slots: set[tuple[str, int]] = set()
        for child in self.children:
            short_id = child.capability.capability_id.rsplit(".", 1)[-1]
            if short_id not in CHILD_CAPABILITIES or short_id not in allowed:
                raise OrchestrationContractError(
                    f"child {child.capability.capability_id!r} is not allowed for {self.root_name!r}"
                )
            slot = (child.role, child.index)
            if slot in seen_slots:
                raise OrchestrationContractError(f"duplicate child slot {slot!r}")
            seen_slots.add(slot)
        expected_stitch = _ROOT_STITCH.get(self.root_name)
        if expected_stitch is None:
            if self.stitch is not None:
                raise OrchestrationContractError("childless edit root cannot declare a stitch")
        elif self.stitch is None or self.stitch.capability_id != STITCH_CAPABILITIES[expected_stitch]:
            raise OrchestrationContractError("stitch capability identity does not match root route")

    @property
    def dependency_edges(self) -> tuple[dict[str, Any], ...]:
        root_ref = "root"
        edges = [
            {
                "from": root_ref,
                "to": f"child:{child.role}:{child.index}",
                "requires_event": "task.running",
                "fence": "parent_attempt",
            }
            for child in self.children
        ]
        if self.stitch is not None:
            edges.extend(
                {
                    "from": f"child:{child.role}:{child.index}",
                    "to": "stitch:0",
                    "requires_event": "task.succeeded",
                    "fence": "runtime_task",
                }
                for child in self.children
            )
        return tuple(edges)

    @property
    def aggregation(self) -> dict[str, Any]:
        return {
            "kind": "ordered_children",
            "order": [f"{child.role}:{child.index}" for child in self.children],
            "source": "runtime.events",
            "require_terminal": "task.succeeded",
            "output_field": "outputs",
        }

    def root_admission(self, *, idempotency_key: str) -> RuntimeAdmission:
        return RuntimeAdmission(
            body={
                "project": self.project,
                "capability_id": self.root.capability_id,
                "capability_digest": self.root.capability_digest,
                "schema_version": SCHEMA_VERSION,
                "input_object_ids": list(self.root_input_object_ids),
                "spec": {
                    "family": ROOT_FAMILY,
                    "params": dict(self.root_params),
                    "output_policy": dict(self.output_policy),
                    "runtime_dependencies": {
                        "children": [child.to_dict() for child in self.children],
                        "edges": list(self.dependency_edges),
                        "aggregation": self.aggregation,
                    },
                },
                "storage_estimate": {"estimated_scratch_bytes": 0, "estimated_output_bytes": 0},
                "settlement_effect": dict(self.settlement_effect),
            },
            idempotency_key=idempotency_key,
        )

    def child_admissions(self, *, root_task_id: str) -> tuple[RuntimeAdmission, ...]:
        root_task_id = _non_empty(root_task_id, "root_task_id")
        admissions: list[RuntimeAdmission] = []
        for child in self.children:
            key = derive_child_idempotency_key(root_task_id, child.role, child.index)
            admissions.append(
                RuntimeAdmission(
                    body={
                        "project": self.project,
                        "capability_id": child.capability.capability_id,
                        "capability_digest": child.capability.capability_digest,
                        "schema_version": SCHEMA_VERSION,
                        "input_object_ids": list(child.input_object_ids),
                        "spec": {
                            "family": CHILD_FAMILY,
                            "params": {**dict(child.params), "role": child.role, "index": child.index},
                            "output_policy": dict(self.output_policy),
                            "runtime_dependencies": {
                                "edges": [
                                    {
                                        "from_task_id": root_task_id,
                                        "to": "self",
                                        "requires_event": "task.running",
                                        "fence": "parent_attempt",
                                    }
                                ]
                            },
                        },
                        "storage_estimate": {"estimated_scratch_bytes": 0, "estimated_output_bytes": 0},
                        "settlement_effect": {},
                    },
                    idempotency_key=key,
                )
            )
        return tuple(admissions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "project": self.project,
            "root": {"name": self.root_name, **self.root.to_dict()},
            "root_input_object_ids": list(self.root_input_object_ids),
            "children": [child.to_dict() for child in self.children],
            "stitch": self.stitch.to_dict() if self.stitch else None,
            "dependency_edges": list(self.dependency_edges),
            "aggregation": self.aggregation,
            "settlement_effect": dict(self.settlement_effect),
            "idempotency": {
                "transport": "Idempotency-Key",
                "derivation": f"{CHILD_KEY_PREFIX}:<root_task_id>:<role>:<index>",
            },
        }


def derive_child_idempotency_key(root_task_id: str, role: str, index: int) -> str:
    """Derive an attempt-independent key; callers send it only as a header."""

    root_task_id = _non_empty(root_task_id, "root_task_id")
    role = _non_empty(role, "role")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        raise OrchestrationContractError("index must be a non-negative integer")
    return f"{CHILD_KEY_PREFIX}:{root_task_id}:{role}:{index}"


def build_runtime_handoff(
    *,
    project: str,
    root_name: str,
    root_digest: str,
    root_input_object_ids: Sequence[str],
    root_params: Mapping[str, Any],
    children: Sequence[ChildSpec] = (),
    stitch_digest: str | None = None,
    output_policy: Mapping[str, Any] | None = None,
    settlement_effect: Mapping[str, Any] | None = None,
) -> RuntimeOrchestrationHandoff:
    """Build one producer-consumable HC-04 orchestration handoff."""

    if root_name not in ROOT_CAPABILITIES:
        raise OrchestrationContractError(f"unknown orchestration root {root_name!r}")
    short_stitch = _ROOT_STITCH.get(root_name)
    stitch = (
        CapabilityIdentity(STITCH_CAPABILITIES[short_stitch], _digest(stitch_digest, "stitch_digest"))
        if short_stitch is not None
        else None
    )
    return RuntimeOrchestrationHandoff(
        project=_non_empty(project, "project"),
        root_name=root_name,
        root=CapabilityIdentity(ROOT_CAPABILITIES[root_name], root_digest),
        root_input_object_ids=_object_ids(root_input_object_ids, "root_input_object_ids"),
        root_params=dict(root_params),
        children=tuple(children),
        stitch=stitch,
        output_policy=dict(output_policy or {}),
        settlement_effect=dict(settlement_effect or {}),
    )


def _result_data(result: Any) -> Mapping[str, Any]:
    if hasattr(result, "ok"):
        if not bool(result.ok):
            error = getattr(result, "error", None)
            raise OrchestrationContractError(str(error or "Runtime task admission failed"))
        result = getattr(result, "data", None)
    if not isinstance(result, Mapping):
        raise OrchestrationContractError("Runtime task admission returned an invalid resource")
    return result


def _task_id(result: Any) -> str:
    data = _result_data(result)
    task = data.get("task")
    candidate = task.get("id") if isinstance(task, Mapping) else data.get("task_id", data.get("id"))
    return _non_empty(candidate, "Runtime task id")


def admit_runtime_task(client: Any, admission: RuntimeAdmission) -> str:
    """Admit one HC-04 record through the generated Runtime task client."""

    body = admission.body
    tasks = getattr(client, "tasks", None)
    create = getattr(tasks, "create", None)
    if not callable(create):
        raise OrchestrationContractError("Runtime client does not expose tasks.create")
    result = create(
        project_id=body["project"],
        capability=body["capability_id"],
        capability_digest=body["capability_digest"],
        schema_version=body["schema_version"],
        spec=body["spec"],
        input_manifest=list(body["input_object_ids"]),
        storage_estimate=dict(body["storage_estimate"]),
        settlement_effect=dict(body["settlement_effect"]),
        idempotency_key=admission.idempotency_key,
    )
    return _task_id(result)


def admit_runtime_handoff(
    client: Any,
    handoff: RuntimeOrchestrationHandoff,
    *,
    root_idempotency_key: str,
) -> tuple[str, tuple[str, ...]]:
    """Admit root then children in handoff order; Runtime gates dependencies."""

    root_task_id = admit_runtime_task(client, handoff.root_admission(idempotency_key=root_idempotency_key))
    child_ids = tuple(
        admit_runtime_task(client, admission)
        for admission in handoff.child_admissions(root_task_id=root_task_id)
    )
    return root_task_id, child_ids


def read_runtime_events(client: Any, project: str, run_id: str) -> tuple[Mapping[str, Any], ...]:
    """Read the ordered event snapshot from the Runtime run service."""

    runs = getattr(client, "runs", None)
    read = getattr(runs, "events", None)
    if not callable(read):
        raise OrchestrationContractError("Runtime client does not expose runs.events")
    result = read(project, _non_empty(run_id, "run_id"))
    if hasattr(result, "ok"):
        if not bool(result.ok):
            error = getattr(result, "error", None)
            raise OrchestrationContractError(str(error or "Runtime event read failed"))
        result = getattr(result, "data", None)
    if not isinstance(result, (list, tuple)) or any(not isinstance(item, Mapping) for item in result):
        raise OrchestrationContractError("Runtime events returned an invalid ordered event list")
    return tuple(result)


def aggregate_child_outputs(
    handoff: RuntimeOrchestrationHandoff,
    events: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Aggregate terminal Runtime event outputs in the declared child order."""

    by_task: dict[str, Mapping[str, Any]] = {}
    for event in events:
        if not isinstance(event, Mapping) or event.get("event_type") != "task.succeeded":
            continue
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            continue
        task_id = payload.get("task_id")
        if isinstance(task_id, str) and task_id not in by_task:
            by_task[task_id] = payload
    # Runtime event reads identify task outputs.  Ordering remains explicit in
    # the handoff; callers provide the task-id projection from Runtime.
    ordered: list[dict[str, Any]] = []
    for child in handoff.children:
        slot = f"{child.role}:{child.index}"
        matches = [
            dict(payload)
            for payload in by_task.values()
            if payload.get("role") == child.role and int(payload.get("index", -1)) == child.index
        ]
        if len(matches) != 1:
            raise OrchestrationContractError(f"Runtime events do not contain one terminal output for {slot}")
        ordered.append({"slot": slot, "payload": matches[0]})
    return tuple(ordered)


__all__ = [
    "CHILD_CAPABILITIES",
    "CHILD_FAMILY",
    "CHILD_KEY_PREFIX",
    "CapabilityIdentity",
    "ChildSpec",
    "OrchestrationContractError",
    "ROOT_CAPABILITIES",
    "ROOT_FAMILY",
    "RuntimeAdmission",
    "RuntimeOrchestrationHandoff",
    "SCHEMA_VERSION",
    "STITCH_CAPABILITIES",
    "STITCH_FAMILY",
    "aggregate_child_outputs",
    "admit_runtime_handoff",
    "admit_runtime_task",
    "build_runtime_handoff",
    "derive_child_idempotency_key",
    "read_runtime_events",
]
