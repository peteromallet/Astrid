"""Focused checks for SDK invocation's runtime-only admission path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.sdk import invocation
from astrid.sdk.execution_request import TARGETED_EXECUTION_BINDING_CAPABILITY
from astrid.sdk.remote import RemoteTasks


class _Capability:
    id = "render.basic"
    capability_type = "executor"


class _TimelineVisualizeCapability:
    id = "rendering.timeline_visualize"
    capability_type = "executor"
    inputs = (SimpleNamespace(name="project_slug"),)


class _Tasks:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return type(
            "Result",
            (),
            {
                "ok": True,
                "data": {
                    "run_id": "run-1",
                    "task_id": "task-1",
                    "attempt_id": None,
                    "state": "queued",
                },
            },
        )()


class _Client:
    def __init__(self) -> None:
        self.tasks = _Tasks()


class _AdmissionTransport:
    """In-memory Runtime replay/conflict boundary for the real RemoteTasks path."""

    def __init__(self):
        self.digest = "sha256:registered-v1"
        self.calls = []
        self.receipts = {}

    def handshake(self, *_args):
        return {"capabilities": [TARGETED_EXECUTION_BINDING_CAPABILITY]}

    def list_capabilities(self, *, cursor=None, limit=50):
        return [[{
            "capability_id": "vibecomfy.validate",
            "definition_digest": self.digest,
            "status": "ready",
        }], None]

    def admit_task(self, **payload):
        self.calls.append(payload)
        key = payload["idempotency_key"]
        material = json.dumps(
            {name: value for name, value in payload.items() if name != "idempotency_key"},
            sort_keys=True,
        )
        if key in self.receipts:
            previous, task = self.receipts[key]
            if previous != material:
                raise RuntimeError("idempotency key was already used with different input")
            return task
        ordinal = len(self.receipts) + 1
        task = {"task_id": f"task-{ordinal}", "run_id": f"run-{ordinal}", "state": "queued"}
        self.receipts[key] = (material, task)
        return task


@pytest.mark.parametrize("change", ["capability_digest", "consent", "input", "target"])
def test_kernel_idempotency_uses_completed_remote_admission(change):
    transport = _AdmissionTransport()
    client = SimpleNamespace(tasks=RemoteTasks(transport))
    capability = SimpleNamespace(
        id="vibecomfy.validate", capability_type="executor",
        inputs=[SimpleNamespace(name="python", type="file")],
    )
    inputs = {
        "python": {"object_id": "sha256:" + "a" * 64, "filename": "workflow.py"},
        "python_execution_consent": "confirmed",
    }
    request = {"target": {"kind": "machine", "id": "worker-1"}}

    def invoke():
        result = invocation._kernel_invoke(
            capability, kind="executor", project="demo", inputs=inputs,
            outputs={}, execution_request=request, _client=client,
        )
        assert result[5] is True
        return result[1]

    first = invoke()
    # Mapping insertion order has no bearing on replay identity.
    inputs = dict(reversed(list(inputs.items())))
    assert invoke() == first
    assert len(transport.receipts) == 1
    assert transport.calls[0]["input_object_ids"] == ["sha256:" + "a" * 64]
    assert transport.calls[0]["spec"]["inputs"]["python_execution_consent"] == "confirmed"
    if change == "capability_digest":
        transport.digest = "sha256:registered-v2"
    elif change == "consent":
        inputs.pop("python_execution_consent")
    elif change == "input":
        inputs["python"] = {"object_id": "sha256:" + "b" * 64, "filename": "workflow.py"}
    else:
        request = {"target": {"kind": "machine", "id": "worker-2"}}
    changed = invoke()
    assert changed != first
    assert invoke() == changed
    assert len(transport.receipts) == 2
    assert transport.calls[0]["idempotency_key"] != transport.calls[2]["idempotency_key"]


@pytest.mark.parametrize("value", [
    "/Users/caller/request.json", "relative.json", Path("/tmp/local.json"),
    {"path": "/Users/caller/request.json"}, {"digest": "invalid"},
    {"digest": "a" * 64, "object_id": "b" * 64},
])
def test_managed_executor_rejects_unresolved_file_before_admission(value):
    client = _Client()
    capability = SimpleNamespace(
        id="h3_av.prepare", capability_type="executor",
        inputs=[SimpleNamespace(name="request", type="file")],
    )
    with pytest.raises(invocation.CapabilityValidationError, match="client.media.import_file"):
        invocation._kernel_invoke(capability, kind="executor", project="demo",
                                  inputs={"request": value}, outputs={}, _client=client)
    assert client.tasks.kwargs is None


@pytest.mark.parametrize("value", ["a" * 64, "sha256:" + "a" * 64,
                                   {"object_id": "sha256:" + "a" * 64, "filename": "request.json"}])
def test_managed_executor_authorizes_file_without_scanning_arbitrary_json(value):
    client = _Client()
    capability = SimpleNamespace(
        id="h3_av.prepare", capability_type="executor",
        inputs=[SimpleNamespace(name="request", type="file"), SimpleNamespace(name="settings", type="object")],
    )
    invocation._kernel_invoke(
        capability, kind="executor", project="demo", outputs={}, _client=client,
        inputs={"request": value, "settings": {"literal": "/Users/an-example-in-a-prompt"}},
    )
    assert client.tasks.kwargs["input_manifest"] == ["sha256:" + "a" * 64]
    assert client.tasks.kwargs["spec"]["input_digests"] == [{"name": "request", "digest": "sha256:" + "a" * 64}]


def test_kernel_invoke_admits_task_through_injected_runtime_client() -> None:
    client = _Client()
    result = invocation._kernel_invoke(
        _Capability(),
        kind="executor",
        project="demo",
        inputs={"prompt": "hello"},
        outputs={"format": "json"},
        _client=client,
    )

    run_id, task_id, attempt_id, manifest, raw, ok, error = result
    assert (run_id, task_id, attempt_id, manifest, ok, error) == (
        "run-1",
        "task-1",
        "",
        None,
        True,
        None,
    )
    assert raw["kernel_run_id"] == "run-1"
    assert client.tasks.kwargs["project_id"] == "demo"
    assert client.tasks.kwargs["capability"] == "render.basic"
    assert client.tasks.kwargs["spec"]["inputs"] == {"prompt": "hello"}


def test_kernel_invoke_derives_project_slug_for_runtime_manifest_expansion() -> None:
    client = _Client()
    invocation._kernel_invoke(
        _TimelineVisualizeCapability(),
        kind="executor",
        project="demo",
        inputs={"timeline_slug": "main"},
        outputs={},
        _client=client,
    )
    assert client.tasks.kwargs["spec"]["inputs"] == {
        "timeline_slug": "main",
        "project_slug": "demo",
    }


def test_kernel_invoke_forwards_storage_estimate_to_runtime_and_audit_metadata() -> None:
    client = _Client()
    invocation._kernel_invoke(
        _Capability(),
        kind="executor",
        project="demo",
        inputs={"prompt": "hello"},
        outputs={},
        admission_metadata={
            "storage_estimate": {"estimated_total_bytes": 123},
            "runtime_enforced": True,
        },
        storage_estimate={"scratch_bytes": 100, "output_bytes": 23},
        _client=client,
    )

    spec = client.tasks.kwargs["spec"]
    assert spec["inputs"] == {"prompt": "hello"}
    assert spec["admission_metadata"] == {
        "storage_estimate": {"estimated_total_bytes": 123},
        "runtime_enforced": True,
    }
    assert client.tasks.kwargs["storage_estimate"] == {
        "scratch_bytes": 100,
        "output_bytes": 23,
    }


def test_kernel_invoke_authorizes_digest_when_media_id_is_not_an_object_id() -> None:
    client = _Client()
    digest = "a" * 64
    invocation._kernel_invoke(
        _Capability(),
        kind="executor",
        project="demo",
        inputs={
            "timeline_snapshot": {
                "registry": {
                    "assets": {
                        "clip": {
                            "media_id": "human-facing-media-id",
                            "object_id": f"sha256:{digest}",
                            "content_sha256": digest,
                        }
                    }
                }
            }
        },
        outputs={},
        _client=client,
    )

    assert client.tasks.kwargs["input_manifest"] == [f"sha256:{digest}"]


def test_kernel_invoke_requires_explicit_runtime_client() -> None:
    import pytest

    with pytest.raises(invocation.CapabilityInvocationError, match="explicit generated"):
        invocation._kernel_invoke(
            _Capability(),
            kind="executor",
            project="demo",
            inputs={},
            outputs={},
        )


def test_wait_for_kernel_task_returns_runtime_outputs(monkeypatch) -> None:
    states = iter(
        [
            {"state": "running", "attempt_id": "attempt-1"},
            {
                "state": "succeeded",
                "attempt_id": "attempt-1",
                "result": {
                    "outputs": [
                        {
                            "name": "video",
                            "digest": "sha256:" + "a" * 64,
                            "media_type": "video/mp4",
                            "size": 123,
                        }
                    ]
                },
            },
        ]
    )
    tasks = SimpleNamespace(
        show=lambda _task_id: SimpleNamespace(ok=True, data=next(states))
    )
    monkeypatch.setattr(invocation.time, "sleep", lambda _seconds: None)

    raw, ok, attempt_id = invocation._wait_for_kernel_task(
        SimpleNamespace(tasks=tasks),
        task_id="task-1",
        run_id="run-1",
        timeout_seconds=10,
        poll_seconds=0.1,
    )

    assert ok is True
    assert attempt_id == "attempt-1"
    assert raw["state"] == "completed"
    assert raw["outputs"]["artifacts"][0]["name"] == "video"


def test_wait_for_kernel_task_propagates_terminal_failure() -> None:
    tasks = SimpleNamespace(
        show=lambda _task_id: SimpleNamespace(
            ok=True,
            data={
                "state": "failed",
                "attempt_id": "attempt-2",
                "result": {"error": {"message": "encoder exploded"}},
            },
        )
    )

    raw, ok, attempt_id = invocation._wait_for_kernel_task(
        SimpleNamespace(tasks=tasks),
        task_id="task-2",
        run_id="run-2",
        timeout_seconds=10,
        poll_seconds=0.1,
    )

    assert ok is False
    assert attempt_id == "attempt-2"
    assert raw["error"]["code"] == "task_failed"
    assert raw["error"]["message"] == "encoder exploded"


def test_wait_for_kernel_task_rejects_non_finite_timeout() -> None:
    import pytest

    with pytest.raises(invocation.CapabilityValidationError, match="positive"):
        invocation._wait_for_kernel_task(
            SimpleNamespace(tasks=SimpleNamespace(show=lambda _task_id: None)),
            task_id="task-3",
            run_id="run-3",
            timeout_seconds=float("nan"),
            poll_seconds=0.1,
        )
