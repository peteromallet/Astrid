"""Typed, lossless execution-request and binding helpers.

The workspace runtime remains the authority for profile resolution, target
ownership, scheduling, and binding.  Astrid validates the request shape and
carries it as an immutable admission field; it does not claim that a local
client can enforce scheduler decisions.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping


ExecutionTargetKind = Literal["default", "profile", "machine", "runpod"]
# This token is deliberately not part of the current workspace.v1 Runtime
# handshake.  A Runtime may only accept targeted requests after a coordinated
# contract release explicitly advertises this capability.
TARGETED_EXECUTION_BINDING_CAPABILITY = "execution_binding.targeted.v1"
_LIFECYCLE_MODES = frozenset(
    {"terminate", "keep_warm", "leave_running", "reuse_or_start_owned"}
)
_TARGET_FIELDS = frozenset(
    {
        "kind",
        "id",
        "profile_alias",
        "profile_revision",
        "profile_digest",
        "release_digest",
        "machine_id",
        "pod_id",
        "provider_account_ref",
        "storage",
        "mounts",
    }
)
_REQUEST_FIELDS = frozenset({
    "schema_version", "workflow", "inputs", "execution", "target",
    "retry_policy", "lifecycle", "limits", "checks",
})
_WORKFLOW_FIELDS = frozenset({"id", "contract_digest", "required_bindings"})
_INPUT_FIELDS = frozenset({"name", "object_id", "filename", "required", "digest"})
_EXECUTION_FIELDS = frozenset({"target", "retry_policy"})
_RETRY_FIELDS = frozenset({"max_attempts"})
_CHECK_FIELDS = frozenset({"preflight", "outputs"})
_LIFECYCLE_FIELDS = frozenset({"mode", "idle_timeout_seconds"})
_LIMIT_FIELDS = frozenset(
    {
        "max_queue_seconds",
        "max_runtime_seconds",
        "collection_seconds",
        "queue_seconds",
        "runtime_seconds",
    }
)


class ExecutionRequestError(ValueError):
    """The caller supplied an unsafe or ambiguous execution request."""


def reject_caller_execution_binding(
    execution_request: ExecutionRequest | Mapping[str, Any] | None,
    spec: Mapping[str, Any] | None,
) -> None:
    """Reject scheduler-owned binding material at the caller boundary.

    A binding is issued by the Runtime while claiming an attempt.  Accepting
    one in a request or worker spec would let a caller turn an observation
    from another task/worker into admission input.
    """

    if isinstance(execution_request, Mapping) and "execution_binding" in execution_request:
        raise ExecutionRequestError(
            "caller-supplied execution_binding is not accepted in execution_request"
        )
    if not isinstance(spec, Mapping):
        return
    if "execution_request" in spec:
        raise ExecutionRequestError(
            "execution_request must be supplied through the first-class "
            "execution_request argument, not spec"
        )
    if "execution_binding" in spec:
        raise ExecutionRequestError(
            "caller-supplied execution_binding is not accepted in spec"
        )
    nested = spec.get("execution_request")
    if isinstance(nested, Mapping) and "execution_binding" in nested:
        raise ExecutionRequestError(
            "caller-supplied execution_binding is not accepted in spec.execution_request"
        )


def require_targeted_execution_binding_support(client: Any) -> None:
    """Fail closed unless the connected Runtime explicitly supports binding.

    The current Runtime handshake has no capability advertisement and its
    ``admit_task``/``claim_task`` contract has no first-class target binding.
    In particular, carrying a target inside ``spec`` is not equivalent to
    scheduler enforcement, so this gate must run before admission.
    """

    handshake = getattr(client, "handshake", None)
    if not callable(handshake):
        raise ExecutionRequestError(
            "targeted execution_request requires Runtime capability "
            f"{TARGETED_EXECUTION_BINDING_CAPABILITY}; the connected Runtime "
            "does not expose a compatible handshake"
        )
    try:
        response = getattr(client, "_last_handshake", None)
        if response is None:
            response = handshake("astrid-targeted-binding", "1.0", [])
    except Exception as exc:  # noqa: BLE001 - compatibility is fail-closed
        raise ExecutionRequestError(
            "targeted execution_request requires a successful Runtime "
            f"handshake advertising {TARGETED_EXECUTION_BINDING_CAPABILITY}"
        ) from exc

    advertised = response.get("capabilities") if isinstance(response, Mapping) else getattr(response, "capabilities", None)
    if isinstance(advertised, (list, tuple, set)) and TARGETED_EXECUTION_BINDING_CAPABILITY in advertised:
        generated = getattr(client, "_generated", client)
        admit_task = getattr(generated, "admit_task", None)
        try:
            parameters = inspect.signature(admit_task).parameters
        except (TypeError, ValueError):
            parameters = {}
        if callable(admit_task) and (
            "execution_request" in parameters
            or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values())
        ):
            return
        raise ExecutionRequestError(
            "targeted execution_request rejected: the generated Runtime client "
            "does not expose a first-class execution_request admission field"
        )
    raise ExecutionRequestError(
        "targeted execution_request rejected: the connected Runtime does not "
        f"advertise {TARGETED_EXECUTION_BINDING_CAPABILITY}; its workspace.v1 "
        "admission only persists an opaque spec and cannot issue or enforce a "
        "target-matched execution binding"
    )


def _object(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExecutionRequestError(f"{field} must be an object")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ExecutionRequestError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ExecutionRequestError(f"{field} must be a positive integer")
    return value


def _optional_positive_integer(value: Any, field: str) -> int | None:
    if value is None:
        return None
    return _positive_integer(value, field)


def _string_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ExecutionRequestError(f"{field} must be an array")
    result: list[str] = []
    for index, item in enumerate(value):
        text = _text(item, f"{field}[{index}]")
        if text in result:
            raise ExecutionRequestError(f"{field} must not contain duplicates")
        result.append(text)
    return tuple(result)


def _safe_filename(value: Any, field: str) -> str:
    filename = _text(value, field)
    path = Path(filename)
    if path.name != filename or path.is_absolute() or ".." in path.parts:
        raise ExecutionRequestError(f"{field} must be a safe basename")
    return filename


@dataclass(frozen=True)
class ExecutionWorkflow:
    """The immutable workflow identity referenced by a task request."""

    id: str
    contract_digest: str
    required_bindings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "contract_digest": self.contract_digest,
            "required_bindings": list(self.required_bindings),
        }


@dataclass(frozen=True)
class ExecutionInput:
    """One managed input and its task-bound filename."""

    name: str
    object_id: str
    filename: str
    required: bool = True
    digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "name": self.name,
            "object_id": self.object_id,
            "filename": self.filename,
            "required": self.required,
        }
        if self.digest is not None:
            value["digest"] = self.digest
        return value


@dataclass(frozen=True)
class ExecutionRetryPolicy:
    max_attempts: int = 1

    def to_dict(self) -> dict[str, int]:
        return {"max_attempts": self.max_attempts}


@dataclass(frozen=True)
class ExecutionIntent:
    """Nested execution spelling accepted by the canonical request stencil."""

    target: ExecutionTarget
    retry_policy: ExecutionRetryPolicy | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"target": self.target.to_dict()}
        if self.retry_policy is not None:
            value["retry_policy"] = self.retry_policy.to_dict()
        return value


@dataclass(frozen=True)
class ExecutionChecks:
    preflight: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "preflight": list(self.preflight),
            "outputs": list(self.outputs),
        }


@dataclass(frozen=True)
class ExecutionTarget:
    """One exact target choice; no fallback target is represented."""

    kind: ExecutionTargetKind
    id: str | None = None
    provider_account_ref: str | None = None
    profile_revision: str | None = None
    profile_digest: str | None = None
    release_digest: str | None = None
    storage: Mapping[str, Any] | None = None
    mounts: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"kind": self.kind}
        if self.kind == "profile":
            value["id"] = self.id
        elif self.kind == "machine":
            value["id"] = self.id
        elif self.kind == "runpod":
            value["pod_id"] = self.id
            value["provider_account_ref"] = self.provider_account_ref
        for key, item in (
            ("profile_revision", self.profile_revision),
            ("profile_digest", self.profile_digest),
            ("release_digest", self.release_digest),
        ):
            if item is not None:
                value[key] = item
        if self.storage is not None:
            value["storage"] = dict(self.storage)
        if self.mounts:
            value["mounts"] = [dict(item) for item in self.mounts]
        return value


@dataclass(frozen=True)
class ExecutionLifecycle:
    mode: str | None = None
    idle_timeout_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {}
        if self.mode is not None:
            value["mode"] = self.mode
        if self.idle_timeout_seconds is not None:
            value["idle_timeout_seconds"] = self.idle_timeout_seconds
        return value


@dataclass(frozen=True)
class ExecutionLimits:
    max_queue_seconds: int | None = None
    max_runtime_seconds: int | None = None
    collection_seconds: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in (
                ("max_queue_seconds", self.max_queue_seconds),
                ("max_runtime_seconds", self.max_runtime_seconds),
                ("collection_seconds", self.collection_seconds),
            )
            if value is not None
        }


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable admission metadata, separate from creative capability inputs."""

    target: ExecutionTarget
    execution: ExecutionIntent | None = None
    schema_version: int | None = None
    workflow: ExecutionWorkflow | None = None
    inputs: tuple[ExecutionInput, ...] = ()
    retry_policy: ExecutionRetryPolicy | None = None
    checks: ExecutionChecks | None = None
    lifecycle: ExecutionLifecycle = ExecutionLifecycle()
    limits: ExecutionLimits = ExecutionLimits()

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"target": self.target.to_dict()}
        if self.execution is not None:
            value["execution"] = self.execution.to_dict()
        if self.schema_version is not None:
            value["schema_version"] = self.schema_version
        if self.workflow is not None:
            value["workflow"] = self.workflow.to_dict()
        if self.inputs:
            value["inputs"] = [item.to_dict() for item in self.inputs]
        if self.retry_policy is not None:
            value["retry_policy"] = self.retry_policy.to_dict()
        if self.checks is not None:
            value["checks"] = self.checks.to_dict()
        lifecycle = self.lifecycle.to_dict()
        limits = self.limits.to_dict()
        if lifecycle:
            value["lifecycle"] = lifecycle
        if limits:
            value["limits"] = limits
        return value


def _normalize_target(value: Any) -> ExecutionTarget:
    raw = _object(value, "execution_request.target")
    unknown = set(raw) - _TARGET_FIELDS
    if unknown:
        raise ExecutionRequestError(
            "execution_request.target contains unsupported fields: "
            + ", ".join(sorted(str(item) for item in unknown))
        )
    kind = _text(raw.get("kind"), "execution_request.target.kind")
    if kind not in {"default", "profile", "machine", "runpod"}:
        raise ExecutionRequestError(
            "execution_request.target.kind must be one of default, profile, machine, runpod"
        )

    profile_constraints = {
        key: _text(raw[key], f"execution_request.target.{key}")
        for key in ("profile_revision", "profile_digest", "release_digest")
        if key in raw
    }
    storage = _normalize_storage_constraint(raw.get("storage")) if "storage" in raw else None
    mounts = _normalize_mount_constraints(raw.get("mounts")) if "mounts" in raw else ()
    placement_fields = {"profile_revision", "profile_digest", "release_digest", "storage", "mounts"}

    if kind == "default":
        if any(key in raw for key in _TARGET_FIELDS - {"kind"}):
            raise ExecutionRequestError("default target cannot carry an id or placement constraint")
        return ExecutionTarget(kind="default")

    if kind == "profile":
        if set(raw) - ({"kind", "id", "profile_alias"} | placement_fields):
            raise ExecutionRequestError("profile target contains fields for another target kind")
        identifier = raw.get("id", raw.get("profile_alias"))
        if "id" in raw and "profile_alias" in raw and raw["id"] != raw["profile_alias"]:
            raise ExecutionRequestError("profile target id and profile_alias conflict")
        profile_id = _text(identifier, "execution_request.target.id")
        return ExecutionTarget(
            kind="profile",
            id=profile_id,
            **profile_constraints,
            storage=storage,
            mounts=mounts,
        )

    if kind == "machine":
        if set(raw) - ({"kind", "id", "machine_id"} | placement_fields):
            raise ExecutionRequestError("machine target contains fields for another target kind")
        identifier = raw.get("id", raw.get("machine_id"))
        if "id" in raw and "machine_id" in raw and raw["id"] != raw["machine_id"]:
            raise ExecutionRequestError("machine target id and machine_id conflict")
        return ExecutionTarget(
            kind="machine",
            id=_text(identifier, "execution_request.target.id"),
            **profile_constraints,
            storage=storage,
            mounts=mounts,
        )

    if set(raw) - ({"kind", "pod_id", "provider_account_ref"} | placement_fields):
        raise ExecutionRequestError("runpod target contains fields for another target kind")
    if "id" in raw:
        raise ExecutionRequestError("runpod target requires pod_id, not ambiguous id")
    return ExecutionTarget(
        kind="runpod",
        id=_text(raw.get("pod_id"), "execution_request.target.pod_id"),
        provider_account_ref=_text(
            raw.get("provider_account_ref"),
            "execution_request.target.provider_account_ref",
        ),
        **profile_constraints,
        storage=storage,
        mounts=mounts,
    )


def _json_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ExecutionRequestError(f"{field} must be a non-empty object")
    try:
        normalized = json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ExecutionRequestError(f"{field} must contain JSON values only") from exc
    if not isinstance(normalized, dict):
        raise ExecutionRequestError(f"{field} must be an object")
    return normalized


def _normalize_storage_constraint(value: Any) -> dict[str, Any]:
    normalized = _json_object(value, "execution_request.target.storage")
    identities = ("id", "storage_id", "volume_id", "network_volume_id", "name")
    if not any(isinstance(normalized.get(key), str) and normalized[key].strip() for key in identities):
        raise ExecutionRequestError(
            "execution_request.target.storage requires an id, volume_id, or name"
        )
    return normalized


def _normalize_mount_constraints(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ExecutionRequestError("execution_request.target.mounts must be a non-empty array")
    result: list[dict[str, Any]] = []
    targets: set[str] = set()
    for index, raw in enumerate(value):
        mount = _json_object(raw, f"execution_request.target.mounts[{index}]")
        source = _text(mount.get("source"), f"execution_request.target.mounts[{index}].source")
        target = _text(mount.get("target"), f"execution_request.target.mounts[{index}].target")
        if not target.startswith("/"):
            raise ExecutionRequestError(
                f"execution_request.target.mounts[{index}].target must be an absolute path"
            )
        if target in targets:
            raise ExecutionRequestError("execution_request.target.mounts has duplicate targets")
        targets.add(target)
        mount["source"] = source
        mount["target"] = target
        if "read_only" in mount and type(mount["read_only"]) is not bool:
            raise ExecutionRequestError(
                f"execution_request.target.mounts[{index}].read_only must be a boolean"
            )
        result.append(mount)
    return tuple(result)


def _normalize_workflow(value: Any) -> ExecutionWorkflow:
    raw = _object(value, "execution_request.workflow")
    unknown = set(raw) - _WORKFLOW_FIELDS
    if unknown:
        raise ExecutionRequestError(
            "execution_request.workflow contains unsupported fields: "
            + ", ".join(sorted(str(item) for item in unknown))
        )
    return ExecutionWorkflow(
        id=_text(raw.get("id"), "execution_request.workflow.id"),
        contract_digest=_text(
            raw.get("contract_digest"),
            "execution_request.workflow.contract_digest",
        ),
        required_bindings=_string_list(
            raw.get("required_bindings", []),
            "execution_request.workflow.required_bindings",
        ),
    )


def _normalize_inputs(value: Any) -> tuple[ExecutionInput, ...]:
    if not isinstance(value, (list, tuple)):
        raise ExecutionRequestError("execution_request.inputs must be an array")
    result: list[ExecutionInput] = []
    names: set[str] = set()
    for index, item in enumerate(value):
        raw = _object(item, f"execution_request.inputs[{index}]")
        unknown = set(raw) - _INPUT_FIELDS
        if unknown:
            raise ExecutionRequestError(
                f"execution_request.inputs[{index}] contains unsupported fields"
            )
        name = _text(raw.get("name"), f"execution_request.inputs[{index}].name")
        if name in names:
            raise ExecutionRequestError(f"execution_request.inputs contains duplicate name {name!r}")
        names.add(name)
        object_id = _text(
            raw.get("object_id"),
            f"execution_request.inputs[{index}].object_id",
        )
        filename = _safe_filename(
            raw.get("filename"),
            f"execution_request.inputs[{index}].filename",
        )
        required = raw.get("required", True)
        if type(required) is not bool:
            raise ExecutionRequestError(
                f"execution_request.inputs[{index}].required must be a boolean"
            )
        digest = raw.get("digest")
        if digest is not None:
            digest = _text(digest, f"execution_request.inputs[{index}].digest")
            if digest != object_id:
                raise ExecutionRequestError(
                    f"execution_request.inputs[{index}].digest must match object_id"
                )
        result.append(ExecutionInput(name, object_id, filename, required, digest))
    return tuple(result)


def _normalize_checks(value: Any) -> ExecutionChecks:
    raw = _object(value, "execution_request.checks")
    unknown = set(raw) - _CHECK_FIELDS
    if unknown:
        raise ExecutionRequestError("execution_request.checks contains unsupported fields")
    return ExecutionChecks(
        preflight=_string_list(raw.get("preflight", []), "execution_request.checks.preflight"),
        outputs=_string_list(raw.get("outputs", []), "execution_request.checks.outputs"),
    )


def normalize_execution_request(value: ExecutionRequest | Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Return a deterministic request copy or raise before admission/spend.

    ``None`` keeps the existing server-selected/default behavior.  When a
    request is present, exactly one discriminated target is required.  No
    profile alias is resolved locally: the runtime must return its immutable
    revision/release identity, which this shape can carry without changing
    creative inputs.
    """

    if value is None:
        return None
    if isinstance(value, ExecutionRequest):
        return value.to_dict()
    raw = _object(value, "execution_request")
    unknown = set(raw) - _REQUEST_FIELDS
    if unknown:
        raise ExecutionRequestError(
            "execution_request contains unsupported fields: "
            + ", ".join(sorted(str(item) for item in unknown))
        )
    raw_execution = _object(raw.get("execution", {}), "execution_request.execution")
    unknown_execution = set(raw_execution) - _EXECUTION_FIELDS
    if unknown_execution:
        raise ExecutionRequestError(
            "execution_request.execution contains unsupported fields: "
            + ", ".join(sorted(str(item) for item in unknown_execution))
        )
    nested_target = raw_execution.get("target")
    if "target" not in raw and nested_target is None:
        raise ExecutionRequestError("execution_request.target is required")
    if "target" in raw and nested_target is not None:
        top_target = _normalize_target(raw["target"])
        inner_target = _normalize_target(nested_target)
        if top_target.to_dict() != inner_target.to_dict():
            raise ExecutionRequestError(
                "execution_request.target conflicts with execution.target"
            )
        target_value = raw["target"]
    else:
        target_value = raw.get("target", nested_target)

    schema_version = raw.get("schema_version")
    if schema_version is not None:
        if isinstance(schema_version, bool) or schema_version != 1:
            raise ExecutionRequestError("execution_request.schema_version must be 1")

    target = _normalize_target(target_value)
    workflow = (
        _normalize_workflow(raw["workflow"])
        if "workflow" in raw
        else None
    )
    inputs = _normalize_inputs(raw["inputs"]) if "inputs" in raw else ()
    if workflow is not None:
        input_names = {item.name for item in inputs}
        missing = sorted(set(workflow.required_bindings) - input_names)
        if missing:
            raise ExecutionRequestError(
                "execution_request.inputs is missing required workflow bindings: "
                + ", ".join(missing)
            )
    top_retry = raw.get("retry_policy")
    nested_retry = raw_execution.get("retry_policy")
    if top_retry is not None and nested_retry is not None and top_retry != nested_retry:
        raise ExecutionRequestError(
            "execution_request.retry_policy conflicts with execution.retry_policy"
        )
    retry_value = top_retry if top_retry is not None else nested_retry
    retry_raw = _object(retry_value or {}, "execution_request.retry_policy")
    unknown_retry = set(retry_raw) - _RETRY_FIELDS
    if unknown_retry:
        raise ExecutionRequestError("execution_request.retry_policy contains unsupported fields")
    retry_policy = (
        ExecutionRetryPolicy(
            max_attempts=_positive_integer(
                retry_raw.get("max_attempts"),
                "execution_request.retry_policy.max_attempts",
            )
        )
        if retry_value is not None
        else None
    )
    checks = _normalize_checks(raw["checks"]) if "checks" in raw else None
    lifecycle_raw = _object(raw.get("lifecycle", {}), "execution_request.lifecycle")
    unknown_lifecycle = set(lifecycle_raw) - _LIFECYCLE_FIELDS
    if unknown_lifecycle:
        raise ExecutionRequestError("execution_request.lifecycle contains unsupported fields")
    mode = lifecycle_raw.get("mode")
    if mode is not None:
        mode = _text(mode, "execution_request.lifecycle.mode")
        if mode not in _LIFECYCLE_MODES:
            raise ExecutionRequestError("execution_request.lifecycle.mode is unsupported")
    idle_timeout = _optional_positive_integer(
        lifecycle_raw.get("idle_timeout_seconds"),
        "execution_request.lifecycle.idle_timeout_seconds",
    )
    if idle_timeout is not None and mode != "keep_warm":
        raise ExecutionRequestError(
            "execution_request.lifecycle.idle_timeout_seconds requires mode=keep_warm"
        )

    limits_raw = _object(raw.get("limits", {}), "execution_request.limits")
    unknown_limits = set(limits_raw) - _LIMIT_FIELDS
    if unknown_limits:
        raise ExecutionRequestError("execution_request.limits contains unsupported fields")
    limits = ExecutionLimits(
        max_queue_seconds=_optional_positive_integer(
            limits_raw.get("max_queue_seconds", limits_raw.get("queue_seconds")),
            "execution_request.limits.max_queue_seconds",
        ),
        max_runtime_seconds=_optional_positive_integer(
            limits_raw.get("max_runtime_seconds", limits_raw.get("runtime_seconds")),
            "execution_request.limits.max_runtime_seconds",
        ),
        collection_seconds=_optional_positive_integer(
            limits_raw.get("collection_seconds"),
            "execution_request.limits.collection_seconds",
        ),
    )
    execution = (
        ExecutionIntent(target=target, retry_policy=retry_policy)
        if "execution" in raw
        else None
    )
    return ExecutionRequest(
        target=target,
        execution=execution,
        schema_version=schema_version,
        workflow=workflow,
        inputs=inputs,
        retry_policy=retry_policy,
        checks=checks,
        lifecycle=ExecutionLifecycle(mode=mode, idle_timeout_seconds=idle_timeout),
        limits=limits,
    ).to_dict()


def execution_request_from_task(task: Mapping[str, Any]) -> dict[str, Any] | None:
    """Recover the carried request from task/show/attempt-shaped data."""

    direct = task.get("execution_request")
    if isinstance(direct, Mapping):
        return dict(direct)
    for container_key in ("spec", "task", "result"):
        container = task.get(container_key)
        if isinstance(container, Mapping):
            nested = container.get("execution_request")
            if isinstance(nested, Mapping):
                return dict(nested)
    return None


def execution_request_input_manifest(
    request: ExecutionRequest | Mapping[str, Any] | None,
) -> list[str]:
    """Return the exact managed-object IDs declared by an execution request."""

    normalized = normalize_execution_request(request)
    if not isinstance(normalized, Mapping):
        return []
    inputs = normalized.get("inputs")
    if not isinstance(inputs, list):
        return []
    return [
        str(item["object_id"])
        for item in inputs
        if isinstance(item, Mapping) and isinstance(item.get("object_id"), str)
    ]


def merge_execution_input_manifest(
    request: ExecutionRequest | Mapping[str, Any] | None,
    supplied: list[str] | tuple[str, ...] | None,
) -> list[str]:
    """Derive/verify the admission manifest without silently dropping inputs."""

    declared = execution_request_input_manifest(request)
    provided = None if supplied is None else list(supplied)

    if len(set(declared)) != len(declared):
        raise ExecutionRequestError(
            "execution_request.inputs contains duplicate object IDs"
        )
    if provided is not None and len(set(provided)) != len(provided):
        raise ExecutionRequestError("input_object_ids contains duplicate object IDs")

    # An omitted manifest is intentionally derived from the immutable request.
    # Once a caller supplies a manifest, however, it is an exact ordered mirror:
    # missing, extra, and reordered IDs must all fail before admission.
    if declared and provided is not None:
        missing = [object_id for object_id in declared if object_id not in provided]
        extra = [object_id for object_id in provided if object_id not in declared]
        if missing or extra:
            details = []
            if missing:
                details.append("missing " + ", ".join(missing))
            if extra:
                details.append("extra " + ", ".join(extra))
            raise ExecutionRequestError(
                "input_object_ids does not exactly mirror execution_request.inputs: "
                + "; ".join(details)
            )
        if provided != declared:
            raise ExecutionRequestError(
                "input_object_ids order does not exactly mirror execution_request.inputs"
            )
        return provided
    return declared if declared else (provided or [])


def merge_execution_request_inputs(
    request: ExecutionRequest | Mapping[str, Any] | None,
    spec: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Make frozen managed-input descriptors the worker spec's input authority."""

    result = dict(spec or {})
    normalized = normalize_execution_request(request)
    declared = normalized.get("inputs", []) if isinstance(normalized, Mapping) else []
    workflow = normalized.get("workflow") if isinstance(normalized, Mapping) else None
    if isinstance(workflow, Mapping):
        # Carry the immutable workflow identity into the worker-facing spec
        # envelope.  This keeps the request contract and the capability spec
        # on one authority path instead of making the worker reconstruct a
        # second, independently supplied digest.
        for key, expected in (
            ("workflow_id", workflow["id"]),
            ("workflow_contract_digest", workflow["contract_digest"]),
        ):
            current = result.get(key)
            if current is not None and current != expected:
                raise ExecutionRequestError(
                    f"spec.{key} conflicts with the frozen execution workflow"
                )
            result[key] = expected
    if not declared:
        return result
    existing = result.get("inputs", {})
    if existing is None:
        existing = {}
    if not isinstance(existing, Mapping):
        raise ExecutionRequestError("spec.inputs must be an object when execution inputs are declared")
    merged = dict(existing)
    for item in declared:
        name = str(item["name"])
        descriptor = dict(item)
        current = merged.get(name)
        if current is not None:
            if not isinstance(current, Mapping):
                raise ExecutionRequestError(
                    f"spec.inputs.{name} conflicts with the frozen execution input descriptor"
                )
            for key in ("object_id", "digest", "filename", "required"):
                if key in current and current[key] != descriptor.get(key):
                    raise ExecutionRequestError(
                        f"spec.inputs.{name}.{key} conflicts with the frozen execution request"
                    )
            descriptor = {**dict(current), **descriptor}
        merged[name] = descriptor
    result["inputs"] = merged
    return result


def execution_binding_from_task(task: Mapping[str, Any]) -> dict[str, Any] | None:
    """Recover scheduler-owned binding fields without inventing them."""

    for key in ("binding", "execution_binding", "placement_binding"):
        value = task.get(key)
        if isinstance(value, Mapping):
            return dict(value)
    for container_key in ("attempt", "task", "result"):
        container = task.get(container_key)
        if isinstance(container, Mapping):
            for key in ("binding", "execution_binding", "placement_binding"):
                value = container.get(key)
                if isinstance(value, Mapping):
                    return dict(value)
    return None


__all__ = [
    "ExecutionBindingError",
    "ExecutionLifecycle",
    "ExecutionLimits",
    "ExecutionChecks",
    "ExecutionIntent",
    "ExecutionInput",
    "ExecutionRetryPolicy",
    "ExecutionRequest",
    "ExecutionRequestError",
    "ExecutionTarget",
    "ExecutionTargetKind",
    "ExecutionWorkflow",
    "TARGETED_EXECUTION_BINDING_CAPABILITY",
    "execution_binding_from_task",
    "execution_request_input_manifest",
    "execution_request_from_task",
    "merge_execution_input_manifest",
    "merge_execution_request_inputs",
    "normalize_execution_request",
    "reject_caller_execution_binding",
    "require_targeted_execution_binding_support",
]


# Kept as a distinct exported name for callers that want to classify binding
# validation separately once the runtime adds a typed binding response.
class ExecutionBindingError(ValueError):
    """A scheduler binding was malformed or internally inconsistent."""
