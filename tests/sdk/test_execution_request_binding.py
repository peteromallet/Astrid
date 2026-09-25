from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

import pytest

from astrid.core.cli.task_progress import render_observation, task_observation
from astrid.sdk.execution_request import (
    ExecutionRequestError,
    TARGETED_EXECUTION_BINDING_CAPABILITY,
    execution_request_from_task,
    normalize_execution_request,
)
from astrid.sdk.remote import RemoteAstridClient, RemoteTasks
from astrid.sdk.workspace_client import WorkspaceClient


PROFILE_REQUEST = {
    "target": {"kind": "profile", "id": "h3-cu130"},
    "lifecycle": {"mode": "keep_warm", "idle_timeout_seconds": 600},
    "limits": {"max_queue_seconds": 3600, "max_runtime_seconds": 1800},
}


class _Generated:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def admit_task(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"task_id": "T-1", "run_id": "R-1", "state": "queued"}

    def handshake(self, *_args: Any) -> dict[str, Any]:
        return {"capabilities": [TARGETED_EXECUTION_BINDING_CAPABILITY]}


class _Transport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._requests: dict[str, str] = {}

    def list_capabilities(self, *, cursor=None, limit=50):
        del cursor, limit
        return [[{"capability_id": "vibecomfy.run", "definition_digest": "sha256:cap"}], None]

    def admit_task(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        key = kwargs["idempotency_key"]
        material = json.dumps(
            [
                kwargs["capability_digest"],
                kwargs["project_id"],
                kwargs["spec"],
                kwargs.get("input_object_ids"),
                kwargs.get("execution_request"),
                kwargs.get("storage_estimate"),
                kwargs.get("settlement_effect"),
                kwargs.get("generation_intent"),
            ],
            sort_keys=True,
            separators=(",", ":"),
        )
        previous = self._requests.setdefault(key, material)
        if previous != material:
            raise RuntimeError("idempotency key was already used with different input")
        return {"task_id": "T-1", "run_id": "R-1", "state": "queued"}


class _TargetedTransport(_Transport):
    def handshake(self, *_args: Any) -> dict[str, Any]:
        return {"capabilities": [TARGETED_EXECUTION_BINDING_CAPABILITY]}


class _MixedCapabilityTransport(_Transport):
    def list_capabilities(self, *, cursor=None, limit=50):
        del cursor, limit
        return [[
            {"capability_id": "vibecomfy.run", "definition_digest": "sha256:stale", "status": "unavailable"},
            {"capability_id": "vibecomfy.run", "definition_digest": "sha256:live", "status": "ready"},
        ], None]


class _ChangingCapabilityTransport(_Transport):
    digest = "sha256:first"

    def list_capabilities(self, *, cursor=None, limit=50):
        del cursor, limit
        return [[{"capability_id": "vibecomfy.run", "definition_digest": self.digest}], None]


class _RuntimeTransport(_Transport):
    def __init__(self) -> None:
        super().__init__()
        self.claim_kwargs: dict[str, Any] | None = None
        self.fail_kwargs: dict[str, Any] | None = None

    def claim_task(self, **kwargs: Any) -> dict[str, Any]:
        self.claim_kwargs = kwargs
        return {
            "task_id": "T-1",
            "attempt_id": "A-1",
            "lease_id": "L-1",
            "fence": 2,
            "runtime_epoch": kwargs["runtime_epoch"],
        }

    def fail_attempt(self, attempt_id: str, **kwargs: Any) -> dict[str, Any]:
        self.fail_kwargs = {"attempt_id": attempt_id, **kwargs}
        return {"status": "failed"}


def test_normalizes_one_target_without_mutating_creative_input() -> None:
    original = json.loads(json.dumps(PROFILE_REQUEST))
    normalized = normalize_execution_request(original)
    assert normalized == original
    assert original == PROFILE_REQUEST
    assert normalized is not original


def test_rejects_ambiguous_or_unsafe_target_before_transport() -> None:
    with pytest.raises(ExecutionRequestError, match="exactly one|target.kind"):
        normalize_execution_request({"target": {"kind": "anything", "id": "x"}})
    with pytest.raises(ExecutionRequestError, match="provider_account_ref"):
        normalize_execution_request({"target": {"kind": "runpod", "pod_id": "pod-1"}})
    with pytest.raises(ExecutionRequestError, match="idle_timeout"):
        normalize_execution_request(
            {
                "target": {"kind": "machine", "id": "machine-1"},
                "lifecycle": {"idle_timeout_seconds": 10},
            }
        )


def test_normalizes_full_immutable_execution_contract() -> None:
    request = normalize_execution_request(
        {
            "schema_version": 1,
            "workflow": {
                "id": "vibecomfy.run",
                "contract_digest": "sha256:workflow",
                "required_bindings": ["source_video", "prompt"],
            },
            "inputs": [
                {
                    "name": "source_video",
                    "object_id": "sha256:source",
                    "digest": "sha256:source",
                    "filename": "source.mov",
                    "required": True,
                },
                {
                    "name": "prompt",
                    "object_id": "sha256:prompt",
                    "filename": "prompt.txt",
                },
            ],
            "target": {"kind": "machine", "id": "local-gpu"},
            "retry_policy": {"max_attempts": 2},
            "lifecycle": {"mode": "leave_running"},
            "limits": {"max_queue_seconds": 30, "max_runtime_seconds": 120},
            "checks": {
                "preflight": ["workflow", "assets", "target"],
                "outputs": ["sha256", "decode"],
            },
        }
    )
    assert request is not None
    assert request["workflow"]["required_bindings"] == ["source_video", "prompt"]
    assert request["inputs"][0]["digest"] == "sha256:source"
    assert request["retry_policy"] == {"max_attempts": 2}


def test_normalizes_nested_execution_stencil_without_dropping_target_or_limits() -> None:
    request = normalize_execution_request(
        {
            "schema_version": 1,
            "workflow": {
                "id": "vibecomfy.run",
                "contract_digest": "sha256:workflow",
                "required_bindings": [],
            },
            "execution": {
                "target": {"kind": "machine", "id": "local-gpu"},
                "retry_policy": {"max_attempts": 2},
            },
            "lifecycle": {"mode": "reuse_or_start_owned"},
            "limits": {
                "queue_seconds": 30,
                "runtime_seconds": 120,
                "collection_seconds": 15,
            },
        }
    )
    assert request is not None
    assert request["target"] == {"kind": "machine", "id": "local-gpu"}
    assert request["execution"] == {
        "target": {"kind": "machine", "id": "local-gpu"},
        "retry_policy": {"max_attempts": 2},
    }
    assert request["retry_policy"] == {"max_attempts": 2}
    assert request["limits"] == {
        "max_queue_seconds": 30,
        "max_runtime_seconds": 120,
        "collection_seconds": 15,
    }


def test_target_profile_release_storage_and_mount_constraints_are_lossless() -> None:
    constraints = {
        "profile_digest": "sha256:profile",
        "release_digest": "sha256:release",
        "storage": {"network_volume_id": "volume-7", "region": "EU"},
        "mounts": [
            {"source": "/workspace", "target": "/mnt/workspace", "read_only": True}
        ],
    }
    normalized = normalize_execution_request(
        {"target": {"kind": "machine", "id": "machine-1", **constraints}}
    )
    assert normalized is not None
    assert normalized["target"] == {
        "kind": "machine",
        "id": "machine-1",
        **constraints,
    }
    with pytest.raises(ExecutionRequestError, match="absolute path"):
        normalize_execution_request(
            {
                "target": {
                    "kind": "runpod",
                    "pod_id": "pod-1",
                    "provider_account_ref": "account-1",
                    "mounts": [{"source": "volume", "target": "relative/path"}],
                }
            }
        )


def test_frozen_inputs_become_worker_spec_inputs() -> None:
    from astrid.sdk.execution_request import merge_execution_request_inputs

    request = {
        "target": {"kind": "machine", "id": "machine-1"},
        "inputs": [
            {
                "name": "source_video",
                "object_id": "sha256:source",
                "filename": "clip.mp4",
                "required": True,
                "digest": "sha256:source",
            }
        ],
    }
    spec = merge_execution_request_inputs(request, {"inputs": {"prompt": "hello"}})
    assert spec["inputs"]["source_video"] == request["inputs"][0]
    assert spec["inputs"]["prompt"] == "hello"
    with pytest.raises(ExecutionRequestError, match="conflicts with the frozen"):
        merge_execution_request_inputs(
            request,
            {"inputs": {"source_video": {"object_id": "sha256:other", "filename": "clip.mp4"}}},
        )


def test_full_contract_rejects_missing_binding_and_unsafe_input() -> None:
    with pytest.raises(ExecutionRequestError, match="missing required workflow bindings"):
        normalize_execution_request(
            {
                "workflow": {
                    "id": "vibecomfy.run",
                    "contract_digest": "sha256:workflow",
                    "required_bindings": ["source_video"],
                },
                "inputs": [],
                "target": {"kind": "machine", "id": "local-gpu"},
            }
        )
    with pytest.raises(ExecutionRequestError, match="safe basename"):
        normalize_execution_request(
            {
                "inputs": [
                    {
                        "name": "source_video",
                        "object_id": "sha256:source",
                        "filename": "../source.mov",
                    }
                ],
                "target": {"kind": "machine", "id": "local-gpu"},
            }
        )


def test_remote_task_create_carries_target_and_conflicts_on_changed_request() -> None:
    transport = _TargetedTransport()
    tasks = RemoteTasks(transport)  # type: ignore[arg-type]
    first = tasks.create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={"inputs": {"prompt": "creative"}},
        idempotency_key="same-key",
        execution_request=PROFILE_REQUEST,
    )
    replay = tasks.create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={"inputs": {"prompt": "creative"}},
        idempotency_key="same-key",
        execution_request=PROFILE_REQUEST,
    )
    assert first.ok and replay.ok
    assert transport.calls[0]["execution_request"] == PROFILE_REQUEST
    assert transport.calls[0]["spec"] == {"inputs": {"prompt": "creative"}}
    with pytest.raises(RuntimeError, match="different input"):
        tasks.create(
            project_id="P-1",
            capability="vibecomfy.run",
            spec={"inputs": {"prompt": "creative"}},
            idempotency_key="same-key",
            execution_request={"target": {"kind": "machine", "id": "machine-1"}},
        )


def test_remote_task_create_prefers_ready_duplicate_capability() -> None:
    transport = _MixedCapabilityTransport()
    result = RemoteTasks(transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={},
        idempotency_key="ready-key",
    )
    assert result.ok
    assert transport.calls[0]["capability_digest"] == "sha256:live"


def test_automatic_task_key_binds_selected_capability_and_replays_stably() -> None:
    transport = _ChangingCapabilityTransport()
    tasks = RemoteTasks(transport)  # type: ignore[arg-type]

    def admit():
        return tasks.create(
            project_id="P-1",
            capability="vibecomfy.run",
            spec={"inputs": {"prompt": "creative"}},
        )

    first = admit()
    replay = admit()
    assert first.ok and replay.ok
    assert transport.calls[0]["idempotency_key"] == transport.calls[1]["idempotency_key"]

    transport.digest = "sha256:refreshed"
    refreshed = admit()
    assert refreshed.ok
    assert transport.calls[2]["idempotency_key"] != transport.calls[0]["idempotency_key"]


def test_explicit_task_key_still_conflicts_when_selected_capability_changes() -> None:
    transport = _ChangingCapabilityTransport()
    tasks = RemoteTasks(transport)  # type: ignore[arg-type]
    kwargs = {
        "project_id": "P-1",
        "capability": "vibecomfy.run",
        "spec": {"inputs": {"prompt": "creative"}},
        "idempotency_key": "caller-selected-key",
    }

    assert tasks.create(**kwargs).ok
    transport.digest = "sha256:refreshed"
    with pytest.raises(RuntimeError, match="different input"):
        tasks.create(**kwargs)


def test_remote_claim_and_fail_preserve_the_frozen_runtime_epoch() -> None:
    transport = _RuntimeTransport()
    tasks = RemoteTasks(transport)

    claim = tasks.claim(
        executor_id="worker-1",
        capability_ids=["vibecomfy.run"],
        runtime_epoch=7,
        idempotency_key="claim-key",
    )
    assert claim.ok and claim.data["runtime_epoch"] == 7
    failed = tasks.fail(
        "T-1",
        "L-1",
        "delivery failed",
        attempt_id="A-1",
        fence=2,
        runtime_epoch=7,
    )
    assert failed.ok
    assert transport.claim_kwargs is not None
    assert transport.claim_kwargs["runtime_epoch"] == 7
    assert transport.fail_kwargs is not None
    assert transport.fail_kwargs["runtime_epoch"] == 7


def test_remote_task_create_derives_declared_input_manifest() -> None:
    transport = _TargetedTransport()
    result = RemoteTasks(transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={},
        idempotency_key="manifest-key",
        execution_request={
            "target": {"kind": "machine", "id": "machine-1"},
            "inputs": [
                {
                    "name": "source_video",
                    "object_id": "sha256:source",
                    "filename": "source.mov",
                }
            ],
        },
    )
    assert result.ok
    assert transport.calls[0]["input_object_ids"] == ["sha256:source"]
    assert transport.calls[0]["spec"]["inputs"]["source_video"] == {
        "name": "source_video",
        "object_id": "sha256:source",
        "filename": "source.mov",
        "required": True,
    }


def test_remote_task_create_rejects_manifest_drift_before_admission() -> None:
    transport = _Transport()
    result = RemoteTasks(transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={},
        input_manifest=["sha256:other"],
        idempotency_key="manifest-drift-key",
        execution_request={
            "target": {"kind": "machine", "id": "machine-1"},
            "inputs": [
                {
                    "name": "source_video",
                    "object_id": "sha256:source",
                    "filename": "source.mov",
                }
            ],
        },
    )
    assert not result.ok
    assert result.error is not None and result.error.code == "validation_error"
    assert transport.calls == []


def test_targeted_request_fails_closed_on_old_runtime_before_admission() -> None:
    transport = _Transport()
    result = RemoteTasks(transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={},
        idempotency_key="old-runtime-key",
        execution_request=PROFILE_REQUEST,
    )
    assert not result.ok
    assert result.error is not None
    assert TARGETED_EXECUTION_BINDING_CAPABILITY in result.error.message
    assert transport.calls == []


def test_remote_task_and_client_paths_fail_closed_identically() -> None:
    task_transport = _Transport()
    client_transport = _Transport()
    task_result = RemoteTasks(task_transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={"inputs": {"prompt": "creative"}},
        idempotency_key="parity-task-key",
        execution_request=PROFILE_REQUEST,
    )
    client_result = RemoteAstridClient(client_transport).invoke(
        "vibecomfy.run",
        project_id="P-1",
        spec={"inputs": {"prompt": "creative"}},
        idempotency_key="parity-client-key",
        execution_request=PROFILE_REQUEST,
    )
    assert not task_result.ok and not client_result.ok
    assert task_result.error is not None and client_result.error is not None
    assert task_result.error.code == client_result.error.code == "validation_error"
    assert task_result.error.message == client_result.error.message
    assert task_transport.calls == client_transport.calls == []


def test_caller_cannot_supply_execution_binding_or_opaque_execution_request() -> None:
    transport = _Transport()
    caller_binding = RemoteTasks(transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={},
        idempotency_key="caller-binding-key",
        execution_request={
            **PROFILE_REQUEST,
            "execution_binding": {"pod_id": "pod-1"},
        },
    )
    assert not caller_binding.ok
    assert caller_binding.error is not None
    assert "caller-supplied execution_binding" in caller_binding.error.message
    opaque = RemoteTasks(transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={"execution_request": PROFILE_REQUEST},
        idempotency_key="opaque-request-key",
    )
    assert not opaque.ok
    assert opaque.error is not None
    assert "first-class" in opaque.error.message
    assert transport.calls == []


def test_input_manifest_requires_exact_order_and_rejects_duplicates() -> None:
    from astrid.sdk.execution_request import merge_execution_input_manifest

    request = {
        "target": {"kind": "machine", "id": "machine-1"},
        "inputs": [
            {"name": "one", "object_id": "sha256:one", "filename": "one.bin"},
            {"name": "two", "object_id": "sha256:two", "filename": "two.bin"},
        ],
    }
    with pytest.raises(ExecutionRequestError, match="order"):
        merge_execution_input_manifest(request, ["sha256:two", "sha256:one"])
    with pytest.raises(ExecutionRequestError, match="duplicate"):
        merge_execution_input_manifest(request, ["sha256:one", "sha256:one"])


def test_vibecomfy_preflight_derives_optional_digest_from_object_id(monkeypatch) -> None:
    from astrid.sdk.remote import _vibecomfy_invocation_preflight

    payloads = {
        name: f"{name}-payload".encode("utf-8")
        for name in ("python", "companion", "source")
    }
    objects = {
        "sha256:" + hashlib.sha256(data).hexdigest(): data
        for data in payloads.values()
    }

    class Client:
        def get_object(self, object_id):
            return objects[object_id]

    monkeypatch.setattr(
        "astrid.packs.vibecomfy.invocation_preflight.preflight_invocation",
        lambda *args, **kwargs: {"phase": kwargs["phase"]},
    )
    spec = {
        "inputs": {
            name: {
                "object_id": next(
                    digest for digest, data in objects.items() if data == payloads[name]
                ),
                "filename": filename,
            }
            for name, filename in {
                "python": "workflow.py",
                "companion": "workflow.vibe.json",
                "source": "source.json",
            }.items()
        }
    }
    receipt = _vibecomfy_invocation_preflight(Client(), spec, strict=True)
    assert receipt is not None
    assert set(receipt["members"]) == {"python", "companion", "source"}
    assert all(row["digest"].startswith("sha256:") for row in receipt["members"].values())


def test_invalid_request_returns_validation_without_capability_lookup() -> None:
    transport = _Transport()
    result = RemoteTasks(transport).create(
        project_id="P-1",
        capability="vibecomfy.run",
        spec={},
        execution_request={"target": {"kind": "runpod", "pod_id": "pod-1"}},
    )
    assert not result.ok
    assert result.error is not None and result.error.code == "validation_error"
    assert transport.calls == []


def test_workspace_transport_retains_request_in_task_spec_envelope() -> None:
    generated = _Generated()
    client = object.__new__(WorkspaceClient)
    client._generated = generated
    client.admit_task(
        capability_id="vibecomfy.run",
        capability_digest="sha256:cap",
        input_object_ids=["sha256:source"],
        idempotency_key="k",
        spec={"inputs": {"prompt": "creative"}},
        execution_request=PROFILE_REQUEST,
    )
    payload = generated.calls[0]
    assert payload["spec"] == {"inputs": {"prompt": "creative"}}
    assert payload["execution_request"] == PROFILE_REQUEST
    assert payload["required_facts"] is None


def test_workspace_admission_derives_spec_inputs_manifest_and_preserves_target(monkeypatch) -> None:
    import astrid.sdk.remote as remote

    monkeypatch.setattr(
        remote,
        "_vibecomfy_invocation_preflight",
        lambda *_args, **_kwargs: {"phase": "submission"},
    )
    generated = _Generated()
    client = object.__new__(WorkspaceClient)
    client._generated = generated
    request = {
        "target": {
            "kind": "machine",
            "id": "machine-1",
            "profile_digest": "sha256:profile",
            "release_digest": "sha256:release",
            "storage": {"volume_id": "volume-1"},
            "mounts": [{"source": "volume-1", "target": "/mnt/data"}],
        },
        "inputs": [
            {
                "name": "source_video",
                "object_id": "sha256:source",
                "filename": "clip.mp4",
                "digest": "sha256:source",
            }
        ],
    }
    client.admit_task(
        capability_id="vibecomfy.run",
        capability_digest="sha256:cap",
        input_object_ids=["sha256:source"],
        idempotency_key="contract-admit",
        spec={"inputs": {"prompt": "hello"}},
        execution_request=request,
    )
    payload = generated.calls[0]
    assert payload["input_object_ids"] == ["sha256:source"]
    assert payload["spec"]["inputs"]["source_video"] == {
        **request["inputs"][0],
        "required": True,
    }
    assert payload["execution_request"]["target"] == request["target"]
    assert payload["spec"]["invocation_preflight"] == {"phase": "submission"}


def test_workspace_malformed_canonical_admission_has_zero_transport_mutation() -> None:
    generated = _Generated()
    client = object.__new__(WorkspaceClient)
    client._generated = generated
    with pytest.raises(ValueError, match="missing bundle members"):
        client.admit_task(
            capability_id="vibecomfy.run",
            capability_digest="sha256:cap",
            input_object_ids=[],
            idempotency_key="malformed-direct",
            spec={"inputs": {"python": {"digest": "sha256:" + "a" * 64, "filename": "workflow.py"}}},
        )
    assert generated.calls == []


def test_status_and_restart_helpers_preserve_request_and_binding() -> None:
    task = {
        "task_id": "T-1",
        "run_id": "R-1",
        "state": "waiting",
        "updated_at": "2026-09-18T00:00:00Z",
        "spec": {"execution_request": PROFILE_REQUEST},
        "execution_binding": {
            "machine_id": "machine-1",
            "provider_account_ref": "acct-1",
            "pod_id": "pod-1",
            "boot_epoch": "boot-2",
            "release_digest": "sha256:release",
        },
        "waiting_reason": "waiting_for_worker",
    }
    assert execution_request_from_task(task) == PROFILE_REQUEST
    observation = task_observation(
        task,
        kind="observed",
        followed_for_seconds=0,
        now=datetime.fromisoformat("2026-09-18T00:00:01+00:00"),
    )
    assert observation["execution_request"] == PROFILE_REQUEST
    assert observation["execution_binding"]["pod_id"] == "pod-1"
    line = render_observation(observation)
    assert 'target={"id":"h3-cu130","kind":"profile"}' in line
    assert '"pod_id":"pod-1"' in line
