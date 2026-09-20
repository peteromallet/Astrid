"""Typed, lossless execution-request and binding helpers.

The workspace runtime remains the authority for profile resolution, target
ownership, scheduling, and binding.  Astrid validates the request shape and
carries it as an immutable admission field; it does not claim that a local
client can enforce scheduler decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping


ExecutionTargetKind = Literal["default", "profile", "machine", "runpod"]
_LIFECYCLE_MODES = frozenset({"terminate", "keep_warm", "leave_running"})
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
    }
)
_REQUEST_FIELDS = frozenset({"target", "lifecycle", "limits"})
_LIFECYCLE_FIELDS = frozenset({"mode", "idle_timeout_seconds"})
_LIMIT_FIELDS = frozenset({"max_queue_seconds", "max_runtime_seconds"})


class ExecutionRequestError(ValueError):
    """The caller supplied an unsafe or ambiguous execution request."""


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


@dataclass(frozen=True)
class ExecutionTarget:
    """One exact target choice; no fallback target is represented."""

    kind: ExecutionTargetKind
    id: str | None = None
    provider_account_ref: str | None = None
    profile_revision: str | None = None
    profile_digest: str | None = None
    release_digest: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"kind": self.kind}
        if self.kind == "profile":
            value["id"] = self.id
            for key, item in (
                ("profile_revision", self.profile_revision),
                ("profile_digest", self.profile_digest),
                ("release_digest", self.release_digest),
            ):
                if item is not None:
                    value[key] = item
        elif self.kind == "machine":
            value["id"] = self.id
        elif self.kind == "runpod":
            value["pod_id"] = self.id
            value["provider_account_ref"] = self.provider_account_ref
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

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in (
                ("max_queue_seconds", self.max_queue_seconds),
                ("max_runtime_seconds", self.max_runtime_seconds),
            )
            if value is not None
        }


@dataclass(frozen=True)
class ExecutionRequest:
    """Immutable admission metadata, separate from creative capability inputs."""

    target: ExecutionTarget
    lifecycle: ExecutionLifecycle = ExecutionLifecycle()
    limits: ExecutionLimits = ExecutionLimits()

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {"target": self.target.to_dict()}
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

    if kind == "default":
        if any(key in raw for key in _TARGET_FIELDS - {"kind"}):
            raise ExecutionRequestError("default target cannot carry an id or placement constraint")
        return ExecutionTarget(kind="default")

    if kind == "profile":
        identifier = raw.get("id", raw.get("profile_alias"))
        if "id" in raw and "profile_alias" in raw and raw["id"] != raw["profile_alias"]:
            raise ExecutionRequestError("profile target id and profile_alias conflict")
        profile_id = _text(identifier, "execution_request.target.id")
        return ExecutionTarget(
            kind="profile",
            id=profile_id,
            profile_revision=(
                _text(raw["profile_revision"], "execution_request.target.profile_revision")
                if "profile_revision" in raw
                else None
            ),
            profile_digest=(
                _text(raw["profile_digest"], "execution_request.target.profile_digest")
                if "profile_digest" in raw
                else None
            ),
            release_digest=(
                _text(raw["release_digest"], "execution_request.target.release_digest")
                if "release_digest" in raw
                else None
            ),
        )

    if kind == "machine":
        identifier = raw.get("id", raw.get("machine_id"))
        if "id" in raw and "machine_id" in raw and raw["id"] != raw["machine_id"]:
            raise ExecutionRequestError("machine target id and machine_id conflict")
        return ExecutionTarget(kind="machine", id=_text(identifier, "execution_request.target.id"))

    if "id" in raw:
        raise ExecutionRequestError("runpod target requires pod_id, not ambiguous id")
    return ExecutionTarget(
        kind="runpod",
        id=_text(raw.get("pod_id"), "execution_request.target.pod_id"),
        provider_account_ref=_text(
            raw.get("provider_account_ref"),
            "execution_request.target.provider_account_ref",
        ),
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
    if "target" not in raw:
        raise ExecutionRequestError("execution_request.target is required")

    target = _normalize_target(raw["target"])
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
            limits_raw.get("max_queue_seconds"),
            "execution_request.limits.max_queue_seconds",
        ),
        max_runtime_seconds=_optional_positive_integer(
            limits_raw.get("max_runtime_seconds"),
            "execution_request.limits.max_runtime_seconds",
        ),
    )
    return ExecutionRequest(
        target=target,
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
    "ExecutionRequest",
    "ExecutionRequestError",
    "ExecutionTarget",
    "ExecutionTargetKind",
    "execution_binding_from_task",
    "execution_request_from_task",
    "normalize_execution_request",
]


# Kept as a distinct exported name for callers that want to classify binding
# validation separately once the runtime adds a typed binding response.
class ExecutionBindingError(ValueError):
    """A scheduler binding was malformed or internally inconsistent."""
