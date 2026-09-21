from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import pytest

from astrid.core.cli.task_progress import render_observation, task_observation
from astrid.sdk.execution_request import (
    ExecutionRequestError,
    execution_request_from_task,
    normalize_execution_request,
)
from astrid.sdk.remote import RemoteTasks
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
            [kwargs["spec"], kwargs.get("execution_request")],
            sort_keys=True,
            separators=(",", ":"),
        )
        previous = self._requests.setdefault(key, material)
        if previous != material:
            raise RuntimeError("idempotency key was already used with different input")
        return {"task_id": "T-1", "run_id": "R-1", "state": "queued"}


class _MixedCapabilityTransport(_Transport):
    def list_capabilities(self, *, cursor=None, limit=50):
        del cursor, limit
        return [[
            {"capability_id": "vibecomfy.run", "definition_digest": "sha256:stale", "status": "unavailable"},
            {"capability_id": "vibecomfy.run", "definition_digest": "sha256:live", "status": "ready"},
        ], None]


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


def test_remote_task_create_carries_target_and_conflicts_on_changed_request() -> None:
    transport = _Transport()
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
        input_object_ids=[],
        idempotency_key="k",
        spec={"inputs": {"prompt": "creative"}},
        execution_request=PROFILE_REQUEST,
    )
    payload = generated.calls[0]
    assert payload["spec"] == {"inputs": {"prompt": "creative"}, "execution_request": PROFILE_REQUEST}
    assert payload["required_facts"] is None


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
