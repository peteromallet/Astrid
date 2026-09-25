from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import pytest

from astrid.core.execution import generic_host


def _grant(*, channel: str = "channel-1", birth: str = "birth-1") -> dict[str, object]:
    return {
        "version": "runtime.local-worker-activation/v1",
        "operation_id": "operation-1",
        "channel_id": channel,
        "credential_file": "/private/worker.token",
        "executor_incarnation": "incarnation-1",
        "evidence_digest": "sha256:" + "a" * 64,
        "host": {"pid": os.getpid(), "birth_id": birth},
    }


def test_parked_host_accepts_one_same_process_grant_before_continuing(monkeypatch) -> None:
    monkeypatch.setattr(generic_host, "process_birth_identity", lambda pid=None: "birth-1")
    worker, host = socket.socketpair()
    completed = threading.Event()
    result: list[dict[str, object]] = []

    def wait() -> None:
        result.append(
            generic_host._await_worker_activation(
                host.detach(),
                operation_id="operation-1",
                channel_id="channel-1",
                credential_file="/private/worker.token",
                timeout_seconds=2,
            )
        )
        completed.set()

    thread = threading.Thread(target=wait)
    thread.start()
    time.sleep(0.02)
    assert not completed.is_set(), "parked host continued before an activation grant"
    worker.sendall(json.dumps(_grant()).encode() + b"\n")
    acknowledgement = json.loads(worker.makefile("rb").readline())
    thread.join(timeout=2)

    assert completed.is_set()
    assert result == [_grant()]
    assert acknowledgement["version"] == "astrid.local-worker-activation-accepted/v1"
    assert acknowledgement["host"] == {"pid": os.getpid(), "birth_id": "birth-1"}
    worker.close()


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda value: value.update(channel_id="stale"), "wrong private channel"),
        (lambda value: value.update(version="old"), "version"),
        (lambda value: value.update(executor_incarnation=""), "incarnation"),
        (lambda value: value.update(evidence_digest="sha256:bad"), "digest"),
        (lambda value: value["host"].update(birth_id="replacement"), "process identity"),
        (lambda value: value.update(credential_file="/private/other.token"), "credential"),
    ],
)
def test_parked_host_rejects_wrong_or_stale_grant(monkeypatch, mutation, message) -> None:
    monkeypatch.setattr(generic_host, "process_birth_identity", lambda pid=None: "birth-1")
    worker, host = socket.socketpair()
    grant = _grant()
    mutation(grant)
    worker.sendall(json.dumps(grant).encode() + b"\n")
    with pytest.raises(generic_host.HostError, match=message):
        generic_host._await_worker_activation(
            host.detach(),
            operation_id="operation-1",
            channel_id="channel-1",
            credential_file="/private/worker.token",
            timeout_seconds=2,
        )
    worker.close()


def test_targeted_direct_launch_refuses_before_bootstrap(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "astrid.core.execution.generic_host",
            "--pack-root",
            str(tmp_path),
            "--execution-target-json",
            '{"kind":"default"}',
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert completed.returncode == 2
    assert "targeted execution requires Worker-supervised activation" in completed.stderr


def test_parked_host_times_out_without_reading_a_credential(monkeypatch) -> None:
    monkeypatch.setattr(generic_host, "process_birth_identity", lambda pid=None: "birth-1")
    worker, host = socket.socketpair()
    with pytest.raises(generic_host.HostError, match="channel failed"):
        generic_host._await_worker_activation(
            host.detach(),
            operation_id="operation-1",
            channel_id="channel-1",
            credential_file="/path/that/must/not/be/read.token",
            timeout_seconds=0.02,
        )
    worker.close()


def test_activated_host_waits_for_runtime_to_enable_disabled_bearer(monkeypatch) -> None:
    calls = []

    class Client:
        def health(self):
            calls.append("health")
            if len(calls) < 3:
                raise RuntimeError("disabled bearer")
            return {"status": "ok"}

    monkeypatch.setattr(generic_host.time, "sleep", lambda _seconds: None)
    generic_host._await_enabled_runtime_credential(Client(), timeout_seconds=1)
    assert calls == ["health", "health", "health"]
