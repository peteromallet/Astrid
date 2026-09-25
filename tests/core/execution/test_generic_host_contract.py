from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import pytest

from astrid.core.execution.generic_host import GenericPackHost, HostError, _execution_contract
from astrid.sdk.execution_request import normalize_execution_request
from tests.test_generic_host import FakeRuntime, _write_manifest


def _task(*, limits: dict[str, int] | None = None) -> dict[str, object]:
    request = normalize_execution_request({
        "schema_version": 1,
        "workflow": {"id": "test.echo", "contract_digest": "sha256:workflow", "required_bindings": []},
        "inputs": [],
        "target": {"kind": "machine", "id": "local-1"},
        "limits": limits or {},
    })
    assert request is not None
    return {"task": {
        "id": "task-contract", "capability": "test.echo", "project_id": "demo",
        "attempt_id": "attempt-contract", "lease_id": "lease-contract",
        "executor_id": "astrid-pack-host", "fence": 1, "runtime_epoch": 1,
        "input_object_ids": [], "created_at": time.time(),
        "execution_binding": {
            "binding_id": "binding-contract", "task_id": "task-contract",
            "run_id": "run-contract", "attempt_id": "attempt-contract",
            "lease_id": "lease-contract", "fence": 1,
            "executor_id": "astrid-pack-host", "session_id": "runtime-session",
            "runtime_epoch": 1, "capability_id": "test.echo",
            "target_kind": "machine", "target_id": "local-1",
            "resolved_target": {"kind": "machine", "id": "local-1"},
            "status": "claimed",
        },
        "spec": {"execution_request": request, "spec": {
            "inputs": {}, "workflow_contract_digest": "sha256:workflow",
        }},
    }}


def _host(tmp_path: Path, runtime: FakeRuntime) -> GenericPackHost:
    _write_manifest(tmp_path / "echo")
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    host.register()
    return host


@pytest.mark.parametrize("mutation, expected", [
    (lambda task: task["task"]["spec"]["spec"].update(workflow_contract_digest="wrong"), "workflow contract digest"),
    (lambda task: task["task"]["execution_binding"].update(target_id="other"), "target binding target_id"),
    (lambda task: task["task"].update(input_object_ids=["sha256:" + "a" * 64]), "input_object_ids"),
    (lambda task: task["task"].pop("execution_binding"), "observed task binding"),
    (lambda task: task["task"].update(runtime_session_id="wrong-session"), "session_id"),
])
def test_contract_mismatch_fails_before_child(tmp_path: Path, mutation, expected: str) -> None:
    runtime = FakeRuntime()
    host = _host(tmp_path, runtime)
    task = _task()
    mutation(task)
    runtime.tasks["task-contract"] = task
    with pytest.raises(HostError, match=expected):
        host.run_task(task, lease_token="lease")
    assert len(runtime.failures) == 1
    assert runtime.settlements == []
    assert runtime.uploaded_objects == {}


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("task_id", "other-task", "task_id"),
        ("run_id", "other-run", "run_id"),
        ("attempt_id", "other-attempt", "attempt_id"),
        ("lease_id", "other-lease", "lease_id"),
        ("fence", 9, "fence"),
        ("executor_id", "other-executor", "executor_id"),
        ("runtime_epoch", 9, "runtime_epoch"),
        ("capability_id", "other-capability", "capability_id"),
    ],
)
def test_runtime_binding_attempt_identity_is_fenced(field: str, value, expected: str) -> None:
    task = _task()["task"]
    task["run_id"] = "run-contract"
    task["execution_binding"][field] = value
    with pytest.raises(HostError, match=expected):
        _execution_contract(task)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("pod_id", "pod-other", "pod_id"),
        ("provider_account_ref", "account-other", "provider_account_ref"),
        ("release_digest", "release-other", "release_digest"),
    ],
)
def test_runtime_binding_exact_target_identity_is_fenced(
    field: str, value: str, expected: str
) -> None:
    task = _task()["task"]
    request = copy.deepcopy(task["spec"]["execution_request"])
    target = {
        "kind": "runpod",
        "pod_id": "pod-1",
        "provider_account_ref": "account-1",
        "release_digest": "release-1",
    }
    request["target"] = target
    task["spec"]["execution_request"] = request
    task["execution_binding"].update(
        {
            "target_kind": "runpod",
            "pod_id": "pod-1",
            "provider_account_ref": "account-1",
            "release_digest": "release-1",
            "resolved_target": target,
        }
    )
    task["execution_binding"][field] = value
    with pytest.raises(HostError, match=expected):
        _execution_contract(task)


def test_contract_input_descriptor_must_match_manifest_and_spec() -> None:
    task = _task()
    payload = b"source"
    object_id = "sha256:" + hashlib.sha256(payload).hexdigest()
    request = copy.deepcopy(task["task"]["spec"]["execution_request"])
    request["inputs"] = [{"name": "source", "object_id": object_id, "filename": "source.mov", "required": True}]
    task["task"]["spec"]["execution_request"] = request
    task["task"]["input_object_ids"] = [object_id]
    task["task"]["spec"]["spec"]["inputs"] = {
        "source": {"digest": object_id, "filename": "different.mov"},
    }
    with pytest.raises(HostError, match="filename"):
        _execution_contract(task["task"])
    task["task"]["spec"]["spec"]["inputs"]["source"]["filename"] = "source.mov"
    task["task"]["spec"]["spec"]["inputs"]["source"]["object_id"] = object_id
    assert _execution_contract(task["task"]) == request
    task["task"]["spec"]["spec"]["inputs"]["source"].pop("digest")
    assert _execution_contract(task["task"]) == request
    task["task"]["spec"]["spec"]["inputs"]["source"].pop("object_id", None)
    with pytest.raises(HostError, match="materialization digest"):
        _execution_contract(task["task"])
    task["task"]["spec"]["spec"]["inputs"]["source"]["object_id"] = object_id
    task["task"]["spec"]["spec"]["inputs"]["other"] = {"digest": object_id}
    with pytest.raises(HostError, match="absent from execution_request"):
        _execution_contract(task["task"])


def test_contract_target_storage_and_mounts_are_checked() -> None:
    task = _task()
    request = copy.deepcopy(task["task"]["spec"]["execution_request"])
    request["target"]["storage"] = {"volume_id": "volume-1"}
    request["target"]["mounts"] = [
        {"source": "volume-1", "target": "/mnt/work", "read_only": True}
    ]
    task["task"]["spec"]["execution_request"] = request
    task["task"]["execution_binding"].update(
        {
            "storage": {"volume_id": "volume-1"},
            "mounts": [{"source": "volume-1", "target": "/mnt/work", "read_only": True}],
        }
    )
    task["task"]["execution_binding"]["resolved_target"].update(
        {
            "storage": {"volume_id": "volume-1"},
            "mounts": [{"source": "volume-1", "target": "/mnt/work", "read_only": True}],
        }
    )
    assert _execution_contract(task["task"]) == request
    task["task"]["execution_binding"]["resolved_target"]["storage"] = {"volume_id": "volume-2"}
    with pytest.raises(HostError, match="target binding storage"):
        _execution_contract(task["task"])


def test_contract_queue_deadline_fails_before_child(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    host = _host(tmp_path, runtime)
    task = _task(limits={"max_queue_seconds": 1})
    task["task"]["created_at"] = time.time() - 3
    runtime.tasks["task-contract"] = task
    with pytest.raises(HostError, match="max_queue_seconds"):
        host.run_task(task, lease_token="lease")
    assert runtime.settlements == []
    assert len(runtime.failures) == 1


def test_contract_runtime_limit_and_session_identity_are_settled(tmp_path: Path) -> None:
    runtime = FakeRuntime()
    host = _host(tmp_path, runtime)
    task = _task(limits={"max_runtime_seconds": 12, "collection_seconds": 5})
    runtime.tasks["task-contract"] = task
    result = host.run_task(task, lease_token="lease")
    assert result["task"]["status"] == "completed"
    payload = runtime.settlements[0][2]["result"]
    assert payload["execution_guards"]["deadline_seconds"] == 12
    assert payload["execution_guards"]["collection_seconds"] == 5
    binding = payload["managed_tool_session"]["binding"]
    assert binding["runtime_epoch"] == 1
    assert binding["launch_generation"] == binding["process_birth_id"]
    assert binding["engine_birth_id"] == binding["process_birth_id"]


def test_contract_collection_deadline_fences_settlement(tmp_path: Path) -> None:
    class SlowUpload(FakeRuntime):
        def upload_object(self, *args, **kwargs):
            time.sleep(1.1)
            return super().upload_object(*args, **kwargs)

    runtime = SlowUpload()
    host = _host(tmp_path, runtime)
    task = _task(limits={"collection_seconds": 1})
    runtime.tasks["task-contract"] = task
    result = host.run_task(task, lease_token="lease")
    assert result["status"] == "failed"
    assert result["deadline_exceeded"] is True
    assert runtime.settlements == []
    assert len(runtime.failures) == 1


def test_contract_runtime_deadline_cancels_slow_child(tmp_path: Path) -> None:
    manifest = _write_manifest(tmp_path / "echo")
    definition = json.loads(manifest.read_text(encoding="utf-8"))
    definition["command"]["argv"][-1] = "import time; time.sleep(5)"
    manifest.write_text(json.dumps(definition), encoding="utf-8")
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    host.register()
    task = _task(limits={"max_runtime_seconds": 1})
    runtime.tasks["task-contract"] = task
    result = host.run_task(task, lease_token="lease")
    assert result["status"] == "failed"
    assert result["deadline_exceeded"] is True
    assert runtime.settlements == []
    assert len(runtime.failures) == 1
