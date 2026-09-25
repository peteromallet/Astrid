"""Target-neutral observations for local-machine and existing RunPod targets.

Adapters own transport and machine facts.  They do not admit tasks, own
leases, or decide whether a generation may settle; those decisions stay in the
Runtime/reconciler boundary.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol

from astrid.sdk.execution_request import ExecutionRequestError, normalize_execution_request


class TargetAdapterError(RuntimeError):
    """A target could not be observed or did not match the frozen request."""


@dataclass(frozen=True, slots=True)
class TargetObservation:
    kind: str
    target_id: str
    live: bool
    runtime_epoch: int
    launch_generation: str
    process_birth_id: str
    engine_birth_id: str
    output_root: str
    profile_revision: str | None = None
    profile_digest: str | None = None
    release_digest: str | None = None
    provider_account_ref: str | None = None
    pod_id: str | None = None
    volume_id: str | None = None
    storage: Mapping[str, Any] | None = None
    mounts: tuple[Mapping[str, Any], ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TargetObservation":
        def text(name: str, *, required: bool = True) -> str:
            raw = value.get(name)
            if raw is None and not required:
                return ""
            if not isinstance(raw, str) or (required and not raw.strip()):
                raise TargetAdapterError(f"target observation requires non-empty {name}")
            return raw.strip()

        raw_epoch = value.get("runtime_epoch")
        if isinstance(raw_epoch, bool) or not isinstance(raw_epoch, int) or raw_epoch < 0:
            raise TargetAdapterError("target observation runtime_epoch must be a non-negative integer")
        live = value.get("live")
        if type(live) is not bool:
            live = value.get("status") == "ready"
        raw_storage = value.get("storage")
        if raw_storage is not None and not isinstance(raw_storage, Mapping):
            raise TargetAdapterError("target observation storage must be an object")
        raw_mounts = value.get("mounts", ())
        if not isinstance(raw_mounts, (list, tuple)) or any(
            not isinstance(item, Mapping) for item in raw_mounts
        ):
            raise TargetAdapterError("target observation mounts must be an array of objects")
        observation = cls(
            kind=text("kind"),
            target_id=text("target_id"),
            live=live,
            runtime_epoch=raw_epoch,
            launch_generation=text("launch_generation", required=live),
            process_birth_id=text("process_birth_id", required=live),
            engine_birth_id=text("engine_birth_id", required=live),
            output_root=text("output_root", required=live),
            profile_digest=text("profile_digest", required=False) or None,
            profile_revision=text("profile_revision", required=False) or None,
            release_digest=text("release_digest", required=False) or None,
            provider_account_ref=text("provider_account_ref", required=False) or None,
            pod_id=text("pod_id", required=False) or None,
            volume_id=text("volume_id", required=False) or None,
            storage=dict(raw_storage) if isinstance(raw_storage, Mapping) else None,
            mounts=tuple(dict(item) for item in raw_mounts),
        )
        if observation.live and observation.runtime_epoch < 1:
            raise TargetAdapterError("live target observation requires a positive runtime_epoch")
        return observation

    @property
    def identity_key(self) -> tuple[Any, ...]:
        return (
            self.kind,
            self.target_id,
            self.runtime_epoch,
            self.launch_generation,
            self.process_birth_id,
            self.engine_birth_id,
            self.profile_digest,
            self.profile_revision,
            self.release_digest,
            self.pod_id,
            self.volume_id,
            _canonical_json(self.storage),
            _canonical_json(self.mounts),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "kind": self.kind,
                "target_id": self.target_id,
                "live": self.live,
                "runtime_epoch": self.runtime_epoch,
                "launch_generation": self.launch_generation,
                "process_birth_id": self.process_birth_id,
                "engine_birth_id": self.engine_birth_id,
                "output_root": self.output_root,
                "profile_digest": self.profile_digest,
                "profile_revision": self.profile_revision,
                "release_digest": self.release_digest,
                "provider_account_ref": self.provider_account_ref,
                "pod_id": self.pod_id,
                "volume_id": self.volume_id,
                "storage": dict(self.storage) if self.storage is not None else None,
                "mounts": [dict(item) for item in self.mounts] if self.mounts else None,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class TargetReceipt:
    action: str
    observation: TargetObservation

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "observation": self.observation.to_dict()}


class TargetAdapter(Protocol):
    def observe(self) -> TargetObservation: ...

    def attach_or_start_owned(self) -> TargetReceipt: ...

    def revalidate(self, prior: TargetObservation) -> TargetObservation: ...

    def assert_request_target(self, requested: Mapping[str, Any]) -> None: ...


def _canonical_json(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TargetAdapterError("target identity contains non-JSON values") from exc


def _target_request(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        normalized = normalize_execution_request({"target": dict(value)})
    except ExecutionRequestError as exc:
        raise TargetAdapterError(str(exc)) from exc
    if not isinstance(normalized, Mapping):
        raise TargetAdapterError("target request is missing")
    target = normalized.get("target")
    if not isinstance(target, Mapping):
        raise TargetAdapterError("target request is malformed")
    return dict(target)


class _BaseTargetAdapter:
    def __init__(
        self,
        target: Mapping[str, Any],
        *,
        observer: Callable[[], Mapping[str, Any]],
    ) -> None:
        self.target = _target_request(target)
        self._observer = observer

    def assert_request_target(self, requested: Mapping[str, Any]) -> None:
        frozen = _target_request(requested)
        if _canonical_json(frozen) != _canonical_json(self.target):
            raise TargetAdapterError(
                "target adapter identity does not match the frozen execution request"
            )

    def observe(self) -> TargetObservation:
        try:
            raw = self._observer()
        except TargetAdapterError:
            raise
        except Exception as exc:  # noqa: BLE001 - adapter boundary
            raise TargetAdapterError(f"target observation failed: {exc}") from exc
        if not isinstance(raw, Mapping):
            raise TargetAdapterError("target observer returned no mapping")
        observation = TargetObservation.from_mapping(raw)
        expected_kind = self.target.get("kind")
        if observation.kind != expected_kind:
            raise TargetAdapterError(
                f"target kind mismatch: expected {expected_kind!r}, observed {observation.kind!r}"
            )
        expected_id = self.target.get("id") or self.target.get("pod_id")
        if expected_id is not None and observation.target_id != expected_id:
            raise TargetAdapterError(
                f"target identity mismatch: expected {expected_id!r}, observed {observation.target_id!r}"
            )
        for field in (
            "profile_revision",
            "profile_digest",
            "release_digest",
            "provider_account_ref",
        ):
            expected = self.target.get(field)
            actual = getattr(observation, field)
            if expected is not None and actual != expected:
                raise TargetAdapterError(f"target {field} mismatch")
        expected_storage = self.target.get("storage")
        if isinstance(expected_storage, Mapping):
            if observation.storage is not None:
                if _canonical_json(observation.storage) != _canonical_json(expected_storage):
                    raise TargetAdapterError("target storage mismatch")
            else:
                expected_volume = next(
                    (
                        expected_storage.get(key)
                        for key in (
                            "volume_id",
                            "network_volume_id",
                            "storage_id",
                            "id",
                            "name",
                        )
                        if isinstance(expected_storage.get(key), str)
                        and str(expected_storage.get(key)).strip()
                    ),
                    None,
                )
                if expected_volume != observation.volume_id:
                    raise TargetAdapterError("target storage identity mismatch")
                if set(expected_storage) - {
                    "volume_id",
                    "network_volume_id",
                    "storage_id",
                    "id",
                    "name",
                }:
                    raise TargetAdapterError(
                        "target storage constraints were not observed in full"
                    )
        expected_mounts = self.target.get("mounts")
        if expected_mounts and _canonical_json(observation.mounts) != _canonical_json(expected_mounts):
            raise TargetAdapterError("target mounts mismatch")
        return observation

    def revalidate(self, prior: TargetObservation) -> TargetObservation:
        current = self.observe()
        if not current.live:
            raise TargetAdapterError("target is no longer live")
        if current.identity_key != prior.identity_key:
            raise TargetAdapterError("target incarnation changed during execution")
        return current


class LocalMachineTargetAdapter(_BaseTargetAdapter):
    """Attach to an owned local target or start exactly one owned process."""

    def __init__(
        self,
        target: Mapping[str, Any],
        *,
        observer: Callable[[], Mapping[str, Any]],
        starter: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(target, observer=observer)
        if self.target["kind"] not in {"default", "profile", "machine"}:
            raise TargetAdapterError("local adapter cannot handle a RunPod target")
        self._starter = starter

    def attach_or_start_owned(self) -> TargetReceipt:
        observed = self.observe()
        if observed.live:
            return TargetReceipt("attach", observed)
        if self._starter is None:
            raise TargetAdapterError("local target is not live and no owned starter was supplied")
        self._starter()
        started = self.observe()
        if not started.live:
            raise TargetAdapterError("owned local target did not become live")
        return TargetReceipt("start_owned", started)


class RunPodTargetAdapter(_BaseTargetAdapter):
    """Bind to one already-existing RunPod target; never provision a replacement."""

    def __init__(
        self,
        target: Mapping[str, Any],
        *,
        observer: Callable[[], Mapping[str, Any]],
    ) -> None:
        super().__init__(target, observer=observer)
        if self.target["kind"] != "runpod":
            raise TargetAdapterError("RunPod adapter requires target.kind=runpod")

    def attach_or_start_owned(self) -> TargetReceipt:
        observed = self.observe()
        if not observed.live:
            raise TargetAdapterError(
                "RUNPOD_TARGET_NOT_READY: existing-pod mode will not provision a replacement"
            )
        expected_pod = self.target.get("pod_id")
        if observed.pod_id != expected_pod:
            raise TargetAdapterError("RunPod pod identity is not exact")
        expected_account = self.target.get("provider_account_ref")
        if observed.provider_account_ref != expected_account:
            raise TargetAdapterError("RunPod provider account binding is not exact")
        return TargetReceipt("attach_existing", observed)


__all__ = [
    "LocalMachineTargetAdapter",
    "RunPodTargetAdapter",
    "TargetAdapter",
    "TargetAdapterError",
    "TargetObservation",
    "TargetReceipt",
]
