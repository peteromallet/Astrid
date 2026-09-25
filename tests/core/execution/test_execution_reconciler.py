from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest

from astrid.core.execution.reconciler import (
    ExecutionReconciler,
    ExecutionUncertain,
    OutputCustodyError,
    verify_output_custody,
)
from astrid.core.execution.target_adapter import (
    LocalMachineTargetAdapter,
    RunPodTargetAdapter,
    TargetAdapterError,
)


CONTRACT = {
    "schema_version": 1,
    "workflow": {
        "id": "render.basic",
        "contract_digest": "sha256:workflow",
        "required_bindings": [],
    },
    "target": {"kind": "machine", "id": "local-1"},
    "retry_policy": {"max_attempts": 2},
    "checks": {"outputs": ["sha256"]},
}


class _Runtime:
    def __init__(self, *, epoch: int = 7) -> None:
        self.epoch = epoch
        self.calls: list[tuple[str, object]] = []

    def create(self, **kwargs):
        self.calls.append(("create", kwargs))
        return {"task_id": "task-1", "run_id": "run-1"}

    def claim(self, **kwargs):
        self.calls.append(("claim", kwargs))
        return {
            "task_id": "task-1",
            "attempt_id": "attempt-1",
            "lease_id": "lease-1",
            "fence": 4,
            "runtime_epoch": self.epoch,
        }

    def settle(self, *args, **kwargs):
        self.calls.append(("settle", {"args": args, **kwargs}))
        return {"ok": True}

    def fail(self, *args, **kwargs):
        self.calls.append(("fail", {"args": args, **kwargs}))
        return {"ok": True}


class _DurableRuntime(_Runtime):
    def __init__(self, snapshots: list[dict[str, object]], *, epoch: int = 7) -> None:
        super().__init__(epoch=epoch)
        self.snapshots = list(snapshots)

    def get_task(self, task_id: str):
        self.calls.append(("get_task", task_id))
        return self.snapshots.pop(0)


def _observation(root: Path, *, launch: str = "launch-1", pod_id: str | None = None):
    return {
        "kind": "runpod" if pod_id else "machine",
        "target_id": pod_id or "local-1",
        "live": True,
        "runtime_epoch": 7,
        "launch_generation": launch,
        "process_birth_id": "process-1",
        "engine_birth_id": "engine-1",
        "output_root": str(root),
        "pod_id": pod_id,
        "provider_account_ref": "acct-1" if pod_id else None,
        "volume_id": "volume-1" if pod_id else None,
    }


def _write_output(root: Path, name: str = "result.bin") -> dict[str, object]:
    path = root / name
    data = b"verified output"
    path.write_bytes(data)
    return {
        "path": name,
        "content_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "decoded": True,
    }


def test_local_reconciler_settles_only_after_fenced_delivery(tmp_path: Path) -> None:
    runtime = _Runtime()
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )

    def execute(_claim, observation):
        return {"submission": {"engine_id": "engine-job-1"}, "outputs": [_write_output(Path(observation.output_root))]}

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={"prompt": "proof"},
        executor_id="worker-1",
        execute=execute,
        idempotency_key="request-1",
    )

    assert result.status == "complete"
    assert result.phase == "settlement"
    assert [name for name, _ in runtime.calls] == ["create", "claim", "settle"]
    settle = dict(runtime.calls[-1][1])
    assert settle["runtime_epoch"] == 7
    assert settle["fence"] == 4


def test_uncertain_execution_is_not_replayed_or_settled(tmp_path: Path) -> None:
    runtime = _Runtime()
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )

    def execute(_claim, _observation):
        raise ExecutionUncertain("engine accepted work but response was lost")

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=execute,
        idempotency_key="request-uncertain",
    )

    assert result.status == "undetermined"
    assert result.phase == "execution"
    assert [name for name, _ in runtime.calls] == ["create", "claim"]


def test_nonterminal_replay_is_undetermined_without_duplicate_claim_or_execute(
    tmp_path: Path,
) -> None:
    class InFlightRuntime(_Runtime):
        def __init__(self) -> None:
            super().__init__()
            self.claim_calls = 0

        def create(self, **kwargs):
            self.calls.append(("create", kwargs))
            return {"task_id": "task-1", "run_id": "run-1"}

        def get_task(self, task_id: str):
            assert task_id == "task-1"
            return {
                "task_id": task_id,
                "run_id": "run-1",
                "state": "running",
                "attempt_id": "attempt-old",
                "idempotency_key": "request-replay",
                "capability_id": "render.basic",
            }

        def claim(self, **kwargs):
            self.claim_calls += 1
            return super().claim(**kwargs)

    runtime = InFlightRuntime()
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )
    executed = 0

    def execute(_claim, _observation):
        nonlocal executed
        executed += 1
        return {}

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=execute,
        idempotency_key="request-replay",
    )

    assert result.status == "undetermined"
    assert result.phase == "recovery"
    assert runtime.claim_calls == 0
    assert executed == 0


def test_runtime_deadline_returns_without_waiting_for_a_hung_callback(tmp_path: Path) -> None:
    runtime = _Runtime()
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )

    def execute(_claim, _observation):
        time.sleep(2.0)
        return {}

    started = time.monotonic()
    result = ExecutionReconciler(runtime, adapter).run(
        contract={**CONTRACT, "limits": {"max_runtime_seconds": 1}},
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=execute,
        idempotency_key="request-hung",
    )

    assert time.monotonic() - started < 1.8
    assert result.status == "failed"
    assert result.phase == "execution"
    assert [name for name, _ in runtime.calls] == ["create", "claim", "fail"]


def test_terminal_replay_recovers_without_claim_or_execute(tmp_path: Path) -> None:
    runtime = _DurableRuntime(
        [{
            "task_id": "task-1",
            "run_id": "run-1",
            "state": "succeeded",
            "attempt_id": "attempt-previous",
            "idempotency_key": "request-replay",
            "capability_id": "render.basic",
            "result": {"outputs": [{"content_hash": "sha256:durable"}]},
        }]
    )
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )
    executed: list[bool] = []

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=lambda *_args: executed.append(True) or {},
        idempotency_key="request-replay",
    )

    assert result.status == "complete"
    assert result.phase == "recovery"
    assert result.attempt_id == "attempt-previous"
    assert executed == []
    assert [name for name, _ in runtime.calls] == ["create", "get_task"]


def test_settlement_timeout_recovers_terminal_runtime_result(tmp_path: Path) -> None:
    runtime = _DurableRuntime(
        [
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "state": "queued",
                "idempotency_key": "request-settle-recovery",
                "capability_id": "render.basic",
            },
            {
                "task_id": "task-1",
                "run_id": "run-1",
                "state": "succeeded",
                "attempt_id": "attempt-1",
                "idempotency_key": "request-settle-recovery",
                "capability_id": "render.basic",
                "result": {"outputs": [{"content_hash": "sha256:durable"}]},
            },
        ]
    )

    def uncertain_settle(*args, **kwargs):
        runtime.calls.append(("settle", {"args": args, **kwargs}))
        return {"ok": False, "error": "response lost"}

    runtime.settle = uncertain_settle
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=lambda _claim, observation: {
            "outputs": [_write_output(Path(observation.output_root))]
        },
        idempotency_key="request-settle-recovery",
    )

    assert result.status == "complete"
    assert result.phase == "settlement_recovery"
    assert [name for name, _ in runtime.calls] == [
        "create", "get_task", "claim", "settle", "get_task"
    ]


def test_claim_for_different_task_is_never_executed_or_settled(tmp_path: Path) -> None:
    runtime = _Runtime()

    def wrong_claim(**kwargs):
        runtime.calls.append(("claim", kwargs))
        return {
            "task_id": "different-task",
            "attempt_id": "wrong-attempt",
            "lease_id": "wrong-lease",
            "fence": 1,
            "runtime_epoch": 7,
        }

    runtime.claim = wrong_claim
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )
    executed: list[bool] = []

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=lambda *_args: executed.append(True) or {},
        idempotency_key="request-wrong-claim",
    )

    assert result.status == "undetermined"
    assert result.phase == "claim"
    assert "does not match" in str(result.error)
    assert executed == []
    assert [name for name, _ in runtime.calls] == ["create", "claim"]


def test_reconciler_rejects_adapter_for_different_request_target(tmp_path: Path) -> None:
    runtime = _Runtime()
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )
    contract = {**CONTRACT, "target": {"kind": "machine", "id": "local-2"}}

    result = ExecutionReconciler(runtime, adapter).run(
        contract=contract,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=lambda *_args: pytest.fail("wrong target must not execute"),
        idempotency_key="request-wrong-target",
    )

    assert result.status == "retryable"
    assert result.phase == "target_preflight"
    assert runtime.calls == []


def test_delivery_hash_failure_is_fenced_and_cannot_settle(tmp_path: Path) -> None:
    runtime = _Runtime()
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )

    def execute(_claim, observation):
        output = _write_output(Path(observation.output_root))
        output["content_hash"] = "sha256:" + "0" * 64
        return {"outputs": [output]}

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=execute,
        idempotency_key="request-bad-output",
    )

    assert result.status == "failed"
    assert result.phase == "delivery"
    assert [name for name, _ in runtime.calls] == ["create", "claim", "fail"]


def test_runtime_deadline_fences_claim_before_settlement(tmp_path: Path) -> None:
    runtime = _Runtime()
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: _observation(tmp_path),
    )
    now = [0.0]

    def clock() -> float:
        return now[0]

    def execute(_claim, observation):
        now[0] = 2.0
        return {"outputs": [_write_output(Path(observation.output_root))]}

    contract = {**CONTRACT, "limits": {"max_runtime_seconds": 1}}
    result = ExecutionReconciler(runtime, adapter, clock=clock).run(
        contract=contract,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=execute,
        idempotency_key="request-deadline",
    )

    assert result.status == "failed"
    assert result.phase == "execution"
    assert [name for name, _ in runtime.calls] == ["create", "claim", "fail"]


def test_incarnation_change_returns_undetermined(tmp_path: Path) -> None:
    runtime = _Runtime()
    observations = iter([_observation(tmp_path), _observation(tmp_path, launch="launch-2")])
    adapter = LocalMachineTargetAdapter(
        {"kind": "machine", "id": "local-1"},
        observer=lambda: next(observations),
    )

    def execute(_claim, observation):
        return {"outputs": [_write_output(Path(observation.output_root))]}

    result = ExecutionReconciler(runtime, adapter).run(
        contract=CONTRACT,
        project_id="project-1",
        capability="render.basic",
        spec={},
        executor_id="worker-1",
        execute=execute,
        idempotency_key="request-restart",
    )

    assert result.status == "undetermined"
    assert result.phase == "delivery"
    assert [name for name, _ in runtime.calls] == ["create", "claim", "fail"]


def test_existing_runpod_adapter_never_provisions_when_not_ready(tmp_path: Path) -> None:
    provision_calls: list[str] = []
    adapter = RunPodTargetAdapter(
        {
            "kind": "runpod",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-1",
        },
        observer=lambda: {
            "kind": "runpod",
            "target_id": "pod-1",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-1",
            "runtime_epoch": 7,
            "live": False,
        },
    )
    with pytest.raises(TargetAdapterError, match="will not provision"):
        adapter.attach_or_start_owned()
    assert provision_calls == []


def test_existing_runpod_adapter_attaches_only_exact_live_pod() -> None:
    adapter = RunPodTargetAdapter(
        {
            "kind": "runpod",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-1",
        },
        observer=lambda: {
            "kind": "runpod",
            "target_id": "pod-1",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-1",
            "volume_id": "volume-1",
            "runtime_epoch": 7,
            "launch_generation": "launch-1",
            "process_birth_id": "process-1",
            "engine_birth_id": "engine-1",
            "output_root": "/tmp/outputs",
            "live": True,
        },
    )

    receipt = adapter.attach_or_start_owned()

    assert receipt.action == "attach_existing"
    assert receipt.observation.identity_key[:6] == (
        "runpod", "pod-1", 7, "launch-1", "process-1", "engine-1"
    )


def test_runpod_adapter_rejects_wrong_provider_account() -> None:
    adapter = RunPodTargetAdapter(
        {
            "kind": "runpod",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-1",
        },
        observer=lambda: {
            "kind": "runpod",
            "target_id": "pod-1",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-2",
            "runtime_epoch": 7,
            "live": True,
            "launch_generation": "launch-1",
            "process_birth_id": "process-1",
            "engine_birth_id": "engine-1",
            "output_root": "/tmp/outputs",
        },
    )

    with pytest.raises(TargetAdapterError, match="provider_account_ref mismatch"):
        adapter.attach_or_start_owned()


def test_runpod_adapter_rejects_wrong_requested_storage() -> None:
    adapter = RunPodTargetAdapter(
        {
            "kind": "runpod",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-1",
            "storage": {"volume_id": "volume-required"},
        },
        observer=lambda: {
            "kind": "runpod",
            "target_id": "pod-1",
            "pod_id": "pod-1",
            "provider_account_ref": "acct-1",
            "volume_id": "volume-other",
            "runtime_epoch": 7,
            "live": True,
            "launch_generation": "launch-1",
            "process_birth_id": "process-1",
            "engine_birth_id": "engine-1",
            "output_root": "/tmp/outputs",
        },
    )

    with pytest.raises(TargetAdapterError, match="storage identity mismatch"):
        adapter.attach_or_start_owned()


def test_output_custody_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="unsafe path"):
        verify_output_custody(
            tmp_path,
            [{"path": "../outside", "content_hash": "sha256:" + "0" * 64}],
        )


def test_output_custody_rejects_declared_decode_from_unverified_bytes(
    tmp_path: Path,
) -> None:
    path = tmp_path / "README.md"
    data = b"not a video, regardless of decoded=true"
    path.write_bytes(data)

    with pytest.raises(OutputCustodyError, match="decode"):
        verify_output_custody(
            tmp_path,
            [{
                "path": path.name,
                "content_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
                "bytes": len(data),
                "media_type": "video/mp4",
                "decoded": True,
            }],
            requirements=("sha256", "decode", "audio"),
        )


def test_output_custody_rejects_unsupported_requirement(tmp_path: Path) -> None:
    with pytest.raises(OutputCustodyError, match="unsupported output requirements"):
        verify_output_custody(
            tmp_path,
            [],
            requirements=("sha256", "telepathy"),
        )


def test_output_custody_accepts_injectable_byte_verifier(tmp_path: Path) -> None:
    path = tmp_path / "result.custom"
    data = b"custom-media-container"
    path.write_bytes(data)
    calls: list[tuple[Path, tuple[str, ...]]] = []

    def verifier(
        verified_path: Path,
        _output: object,
        requirements: tuple[str, ...],
    ) -> dict[str, object]:
        assert verified_path.read_bytes() == data
        calls.append((verified_path, requirements))
        return {"decoder": "test-decoder", "has_audio": True}

    outputs = verify_output_custody(
        tmp_path,
        [{
            "path": path.name,
            "content_hash": "sha256:" + hashlib.sha256(data).hexdigest(),
            "decoded": True,
        }],
        requirements=("sha256", "decode", "audio"),
        verifier=verifier,
    )

    assert calls == [(path, ("sha256", "decode", "audio"))]
    assert "decoded" not in outputs[0]
    assert outputs[0]["verification"] == {
        "decoder": "test-decoder",
        "has_audio": True,
    }
