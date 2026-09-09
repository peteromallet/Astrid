from __future__ import annotations

import shutil
import subprocess
import sys
import time

import pytest

from astrid.core.execution.guards import (
    ExecutionDeadlineError,
    ExecutionGuardPolicy,
    EvidenceCapError,
    ScratchFloorError,
    WarmReuseExpectationError,
)
import astrid.core.execution.generic_host as generic_host
from astrid.core.execution.generic_host import GenericPackHost


def test_scratch_floor_fails_closed_and_accepts_measured_space(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = ExecutionGuardPolicy(scratch_floor_bytes=4, evidence_cap_bytes=16)
    usage = shutil.disk_usage(tmp_path)
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: type(usage)(usage.total, usage.used, 3),
    )
    with pytest.raises(ScratchFloorError, match="below required floor"):
        policy.assert_scratch_floor(tmp_path)

    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: type(usage)(usage.total, usage.used, 8),
    )
    receipt = policy.assert_scratch_floor(tmp_path)
    assert receipt["free_bytes"] == 8


def test_generated_evidence_cap_is_enforced(tmp_path) -> None:
    (tmp_path / "evidence.bin").write_bytes(b"12345")
    policy = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=4)
    with pytest.raises(EvidenceCapError, match="exceeds cap"):
        policy.assert_evidence_cap(tmp_path)

    policy = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=5)
    assert policy.assert_evidence_cap(tmp_path)["observed_bytes"] == 5


def test_generated_budget_accumulates_and_excludes_immutable_inputs(tmp_path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "source.bin").write_bytes(b"input-bytes")
    output = tmp_path / "generated.log"
    output.write_bytes(b"123")
    policy = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=5)
    baseline = policy.immutable_input_baseline(inputs)
    first = policy.assert_evidence_cap(tmp_path, immutable_inputs=baseline)
    assert first["observed_bytes"] == 3
    output.write_bytes(b"12345")
    second = policy.assert_evidence_cap(tmp_path, immutable_inputs=baseline)
    assert second["attempt_delta_bytes"] == 2
    assert second["run_observed_bytes"] == 5
    output.write_bytes(b"123456")
    with pytest.raises(EvidenceCapError, match="run budget"):
        policy.assert_evidence_cap(tmp_path, immutable_inputs=baseline)


def test_budget_latches_after_cross_attempt_breach(tmp_path) -> None:
    policy = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=5)
    first = tmp_path / "first"
    second = tmp_path / "second"
    third = tmp_path / "third"
    for directory in (first, second, third):
        directory.mkdir()
    (first / "out").write_bytes(b"123")
    (second / "out").write_bytes(b"456")
    (third / "out").write_bytes(b"7")
    policy.assert_evidence_cap(first)
    with pytest.raises(EvidenceCapError, match="run budget"):
        policy.assert_evidence_cap(second)
    with pytest.raises(EvidenceCapError, match="exhausted"):
        policy.assert_evidence_cap(third)
    assert policy.evidence_budget.exhausted is True
    assert policy.evidence_budget.breach == {
        "attempt_observed_bytes": 3,
        "run_observed_bytes": 6,
        "cap_bytes": 5,
    }


def test_modified_or_managed_input_is_not_exempt(tmp_path) -> None:
    inputs = tmp_path / "inputs"
    managed = tmp_path / "managed-objects"
    inputs.mkdir()
    managed.mkdir()
    input_file = inputs / "source.bin"
    managed_file = managed / "asset.bin"
    input_file.write_bytes(b"input-data")
    managed_file.write_bytes(b"managed-data")
    policy = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=64)
    baseline = policy.immutable_input_baseline(inputs)
    baseline.update(policy.immutable_input_baseline(managed))
    assert policy.assert_evidence_cap(tmp_path, immutable_inputs=baseline)["observed_bytes"] == 0
    input_file.write_bytes(b"changedata")
    assert policy.assert_evidence_cap(tmp_path, immutable_inputs=baseline)["observed_bytes"] == len(b"changedata")


def test_running_writer_is_detected_while_still_alive(tmp_path) -> None:
    output = tmp_path / "running-output.bin"
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; import sys, time; Path(sys.argv[1]).write_bytes(b'x' * 2048); time.sleep(30)",
            str(output),
        ]
    )
    policy = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=1024)
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if output.exists():
                assert process.poll() is None
                with pytest.raises(EvidenceCapError, match="run budget"):
                    policy.assert_evidence_cap(tmp_path)
                break
            time.sleep(0.01)
        else:
            pytest.fail("writer did not publish evidence before watchdog deadline")
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_deadline_gate_rejects_expired_attempt() -> None:
    policy = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=1, deadline_seconds=1)
    with pytest.raises(ExecutionDeadlineError, match="deadline"):
        policy.assert_deadline(time.monotonic() - 0.001)


def test_warm_expectation_is_not_derived_from_a_listener_port() -> None:
    cold = ExecutionGuardPolicy(scratch_floor_bytes=1, evidence_cap_bytes=1)
    assert cold.warm_expectation() == {
        "warm_reuse_expected": False,
        "listener_port": None,
        "port_independent": True,
    }
    warm = ExecutionGuardPolicy(
        scratch_floor_bytes=1,
        evidence_cap_bytes=1,
        warm_reuse_expected=True,
    )
    assert warm.warm_expectation()["warm_reuse_expected"] is True
    with pytest.raises(WarmReuseExpectationError):
        warm.warm_expectation(listener_port=0)


def test_warm_expectation_requires_a_boolean() -> None:
    with pytest.raises(WarmReuseExpectationError):
        ExecutionGuardPolicy(
            scratch_floor_bytes=1,
            evidence_cap_bytes=1,
            warm_reuse_expected=1,
        )


def test_generic_host_carries_the_guard_policy_without_a_listener_port(tmp_path) -> None:
    policy = ExecutionGuardPolicy(
        scratch_floor_bytes=1,
        evidence_cap_bytes=1,
        warm_reuse_expected=False,
    )
    host = GenericPackHost(pack_roots=[tmp_path], execution_policy=policy)
    try:
        assert host.execution_policy is policy
        assert host.execution_policy.warm_expectation()["listener_port"] is None
    finally:
        host.shutdown()


def test_cleanup_helper_does_not_claim_absence_after_recursive_delete_error(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "attempt"
    root.mkdir()
    monkeypatch.setattr(
        generic_host.shutil,
        "rmtree",
        lambda _path: (_ for _ in ()).throw(FileNotFoundError("descendant vanished")),
    )
    with pytest.raises(generic_host.HostError, match="cleanup was not verified"):
        generic_host._cleanup_ephemeral_attempt(root)
