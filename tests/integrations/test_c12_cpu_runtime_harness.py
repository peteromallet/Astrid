"""CPU end-to-end C12 seam: Runtime -> Worker -> GenericPackHost -> child.

The Worker neutral preflight is exercised with a deterministic CPU fact probe;
the public launcher, Runtime HTTP authority, host registration, claim loop,
inline CAS settlement, cancellation, and Worker-owned process cleanup remain
real.  This test is deliberately not GPU acceptance.
"""

from __future__ import annotations

import hashlib
import base64
import json
import multiprocessing
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any, Mapping

import pytest

RUNTIME_ROOT = Path(
    os.environ.get("BANODOCO_RUNTIME_CHECKOUT")
    or "/Users/hannahomalley/Documents/Codex/2026-09-09/can-you-see-the-poms-skills/work/astrid-prep/repos/Runtime"
).resolve()
WORKER_ROOT = Path(
    os.environ.get("REIGH_WORKER_CHECKOUT")
    or "/Users/hannahomalley/Documents/Codex/2026-09-09/can-you-see-the-poms-skills/work/astrid-prep/repos/reigh-worker"
).resolve()
sys.path.insert(0, str(RUNTIME_ROOT))
sys.path.insert(0, str(WORKER_ROOT))

from runtime_protocol.daemon import RuntimeDaemon  # noqa: E402
from source.runtime import supervisor  # noqa: E402
from source.runtime.worker import preflight  # noqa: E402
from astrid.core.execution.generic_host import GenericPackHost, RuntimeProtocolClient  # noqa: E402
from astrid.core.gateway.dispatch import compose_profile_handoff  # noqa: E402
from astrid.sdk.workspace_client import WorkspaceClient  # noqa: E402


FIXTURE_PACK = Path(__file__).parents[1] / "fixtures" / "c12_cpu_pack"


def _worker_entry(config: supervisor.HostLaunchConfig, environ: Mapping[str, str]) -> None:
    """Run the public Worker launcher in a separate process.

    The only CPU seam is the neutral GPU fact probe. All discovery, Runtime
    identity, Worker readiness publication, host registration, lease loop,
    settlement and cleanup use the production code path.
    """

    preflight._probe_gpu = lambda: {
        "uuid": "cpu-fixture-gpu",
        "name": "CPU fixture probe",
        "driver": "fixture-driver",
        "cuda": "fixture-cuda",
        "vram_bytes": 1,
    }
    code = supervisor.launch_generic_pack_host(
        config,
        environ=dict(environ),
        enforce_readiness=True,
    )
    raise SystemExit(code)


def _manifest(root: Path, filename: str, content: bytes) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    payload = root / filename
    payload.write_bytes(content)
    manifest = root.parent / f"{root.name}.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "path": filename,
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return root, manifest


def _facts(tmp_path: Path, source_checkout: Path, python: Path) -> dict[str, str]:
    engine_lock = tmp_path / "engine.lock"
    engine_lock.write_text("c12-engine-lock\n", encoding="utf-8")
    model_root, model_manifest = _manifest(tmp_path / "models", "model.bin", b"c12-model")
    node_root, node_manifest = _manifest(tmp_path / "nodes", "node.py", b"c12-node")
    scratch = tmp_path / "scratch"
    cas = tmp_path / "cas"
    output = tmp_path / "output"
    scratch.mkdir()
    cas.mkdir()
    output.mkdir()
    return {
        "REIGH_INTERPRETER": str(python),
        "REIGH_ENGINE_INTERPRETER": str(python),
        "REIGH_RUNTIME_LOCK_PATH": str(WORKER_ROOT / "uv.lock"),
        "REIGH_ENGINE_LOCK_PATH": str(engine_lock),
        "REIGH_MODEL_ROOT": str(model_root),
        "REIGH_MODEL_MANIFEST_PATH": str(model_manifest),
        "REIGH_CUSTOM_NODE_ROOT": str(node_root),
        "REIGH_CUSTOM_NODE_MANIFEST_PATH": str(node_manifest),
        "REIGH_SCRATCH_ROOT": str(scratch),
        "REIGH_CAS_ROOT": str(cas),
        "REIGH_OUTPUT_ROOT": str(output),
    }


def _value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(key, default)
    return getattr(value, key, default)


def _inventory_sources() -> dict[str, list[str]]:
    payload = json.loads(
        (Path(__file__).with_name("c12_cpu_case_inventory.json")).read_text(
            encoding="utf-8"
        )
    )
    return {
        str(case): list(sources)
        for case, sources in payload["evidence_sources"].items()
    }


def _mutation_data(value: Any) -> Any:
    if isinstance(value, Mapping) and "data" in value and "receipt" in value:
        return value["data"]
    return value


def _task_state(client: WorkspaceClient, task_id: str) -> tuple[str, Any]:
    task = client.get_task(task_id)
    return str(_value(task, "state", "")), task


def _wait_state(client: WorkspaceClient, task_id: str, expected: set[str], timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        state, task = _task_state(client, task_id)
        last = state
        if state in expected:
            return task
        time.sleep(0.1)
    raise AssertionError(f"task {task_id} did not reach {sorted(expected)}; last={last}")


def _wait_file(path: Path, process: multiprocessing.Process, timeout: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        if not process.is_alive():
            raise AssertionError(f"Worker exited before readiness: exitcode={process.exitcode}")
        time.sleep(0.1)
    raise AssertionError(f"Worker readiness file was not published: {path}")


def _stop_worker(process: multiprocessing.Process, state_file: Path) -> dict[str, Any]:
    if process.is_alive():
        process.terminate()
    process.join(timeout=30)
    if process.is_alive():
        process.kill()
        process.join(timeout=10)
    assert not process.is_alive()
    assert state_file.is_file()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["status"] == "exited"
    return state


def _wait_pid_absent(pid: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        state = result.stdout.strip()
        stderr = result.stderr.strip()
        if result.returncode == 0 and state.startswith("Z"):
            return
        if result.returncode == 1 and not state and not stderr:
            return
        if result.returncode != 0 or not state:
            raise AssertionError(
                f"process observation failed for {pid}: returncode={result.returncode} stderr={stderr!r}"
            )
        time.sleep(0.1)
    raise AssertionError(f"owned CPU child {pid} remained live: {state!r}")


def _wait_port_available(port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = socket.socket()
        try:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind(("127.0.0.1", port))
            probe.listen(1)
            return
        except OSError as exc:
            if exc.errno not in {48, 98, 10048}:  # EADDRINUSE on macOS/Linux/Windows
                raise AssertionError(f"port observation failed for {port}: {exc}") from exc
        finally:
            probe.close()
        time.sleep(0.1)
    raise AssertionError(f"owned CPU child port {port} remained bound")


def test_c12_observation_helpers_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_args, **_kwargs: type(
            "Result", (), {"returncode": 2, "stdout": "", "stderr": "permission denied"}
        )(),
    )
    with pytest.raises(AssertionError, match="process observation failed"):
        _wait_pid_absent(12345, timeout=0.1)

    occupied = socket.socket()
    occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    occupied.bind(("127.0.0.1", 0))
    port = occupied.getsockname()[1]
    try:
        with pytest.raises(AssertionError, match="remained bound"):
            _wait_port_available(port, timeout=0.1)
    finally:
        occupied.close()


def _start_worker(
    *,
    daemon: RuntimeDaemon,
    support_root: Path,
    source_checkout: Path,
    facts: Mapping[str, str],
    suffix: str,
) -> tuple[multiprocessing.Process, Path, Path, dict[str, Any]]:
    host_root = support_root / f"astrid-host-{suffix}"
    host_root.mkdir(parents=True, exist_ok=True)
    boot_manifest = host_root / "boot-manifest.json"
    handoff = compose_profile_handoff(boot_manifest, support_root=support_root)
    ready_file = support_root / f"host-ready-{suffix}.json"
    state_file = support_root / f"worker-state-{suffix}.json"
    config = supervisor.HostLaunchConfig(
        # Preserve the venv entrypoint lexically.  ``Path.resolve()`` follows
        # the macOS venv symlink back to the system interpreter and would drop
        # the prepared YAML/runtime dependencies from the host child.
        host_python=Path(sys.executable),
        source_checkout=source_checkout.resolve(),
        pack_root=FIXTURE_PACK.resolve(),
        runtime_endpoint=str(daemon.endpoint),
        credential_file=Path(daemon.worker_credential_path).resolve(),
        support_root=support_root.resolve(),
        runtime_instance_id=daemon.instance_id,
        ready_file=ready_file.resolve(),
        state_file=state_file.resolve(),
        boot_manifest_path=boot_manifest.resolve(),
        boot_manifest_hash=str(handoff["sha256"]),
    )
    environ = dict(os.environ)
    environ.update(facts)
    environ["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    environ["PYTHONPATH"] = os.pathsep.join((str(WORKER_ROOT), str(RUNTIME_ROOT), str(source_checkout)))
    context = multiprocessing.get_context("spawn")
    process = context.Process(target=_worker_entry, args=(config, environ), name=f"c12-worker-{suffix}")
    process.start()
    readiness = _wait_file(ready_file, process)
    assert readiness["status"] == "ready"
    assert readiness["executor_id"] == "astrid-pack-host"
    assert "c12_cpu.echo" in readiness["ready_capabilities"]
    assert "c12_cpu.slow" in readiness["ready_capabilities"]
    return process, ready_file, state_file, readiness


@pytest.mark.timeout(120)
def test_c12_cpu_runtime_worker_host_harness(tmp_path: Path) -> None:
    source_checkout = Path(__file__).parents[2].resolve()
    support_root = (tmp_path / "support").resolve()
    daemon = RuntimeDaemon(
        tmp_path / "realm",
        support_root=support_root,
        production_worker_credentials=True,
    ).start()
    worker: multiprocessing.Process | None = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        inventory_sources = _inventory_sources()
        runtime_cases = {
            "cold_success",
            "cancel_confirmed",
            "restart_replaces_incarnation",
            "stale_fence_rejected",
            "cas_settlement_exactly_once",
            "cleanup_releases_owned_session",
        }
        assert runtime_cases <= set(inventory_sources)
        assert all("runtime_worker" in inventory_sources[case] for case in runtime_cases)
        records = {
            record.id: record
            for record in GenericPackHost(pack_roots=[FIXTURE_PACK]).discover()
        }
        assert set(records) == {"c12_cpu.echo", "c12_cpu.slow"}
        facts = _facts(tmp_path, source_checkout, Path(sys.executable).resolve())

        worker, _ready, state_file, readiness = _start_worker(
            daemon=daemon,
            support_root=support_root,
            source_checkout=source_checkout,
            facts=facts,
            suffix="first",
        )

        success = owner.admit_task(
            capability_id="c12_cpu.echo",
            capability_digest=records["c12_cpu.echo"].capability_digest,
            input_object_ids=[],
            idempotency_key="c12-runtime-success",
            spec={"inputs": {}},
        )
        success_id = str(_value(_mutation_data(success), "task_id"))
        completed = _wait_state(owner, success_id, {"succeeded"})
        result = _value(completed, "result", {})
        outputs = _value(result, "outputs", [])
        assert isinstance(outputs, list) and len(outputs) == 1
        output = outputs[0]
        digest = str(_value(output, "digest"))
        assert digest == "sha256:" + hashlib.sha256(b"c12-runtime-output").hexdigest()
        stored = owner.get_object(digest)
        assert bytes(_value(stored, "data")) == b"c12-runtime-output"
        success_attempt_id = str(_value(completed, "attempt_id"))
        success_attempt = daemon.service.store.conn.execute(
            "SELECT lease_id, fence, runtime_epoch FROM attempts WHERE id=?",
            (success_attempt_id,),
        ).fetchone()
        assert success_attempt is not None
        duplicate_output = b"duplicate-must-not-publish"
        duplicate_digest = "sha256:" + hashlib.sha256(duplicate_output).hexdigest()
        duplicate_client = RuntimeProtocolClient(
            daemon.endpoint,
            Path(daemon.worker_credential_path).read_text(encoding="utf-8").strip(),
        )
        with pytest.raises(Exception, match="stale|settled|cancelled"):
            duplicate_client.generated.settle_attempt(
                success_attempt_id,
                {
                    "attempt_id": success_attempt_id,
                    "lease_id": success_attempt["lease_id"],
                    "fence": int(success_attempt["fence"]),
                    "runtime_epoch": int(success_attempt["runtime_epoch"]),
                    "outputs": [{
                        "name": "answer",
                        "kind": "object",
                        "media_type": "text/plain",
                        "digest": duplicate_digest,
                        "size": len(duplicate_output),
                        "data_base64": base64.b64encode(duplicate_output).decode("ascii"),
                    }],
                    "result": {"duplicate_replay": True},
                },
                idempotency_key="c12-success-duplicate-replay",
            )
        events = daemon.service.events(str(_value(completed, "run_id")))
        assert [event.get("event_type", event.get("kind")) for event in events].count("task.completed") == 1
        with pytest.raises(Exception):
            owner.get_object(duplicate_digest)

        slow_pid_file = tmp_path / "slow-child.pid"
        slow_port_file = tmp_path / "slow-child.port"
        slow = owner.admit_task(
            capability_id="c12_cpu.slow",
            capability_digest=records["c12_cpu.slow"].capability_digest,
            input_object_ids=[],
            idempotency_key="c12-runtime-cancel",
            spec={
                "inputs": {
                    "marker": str(slow_pid_file),
                    "port_marker": str(slow_port_file),
                }
            },
        )
        slow_id = str(_value(_mutation_data(slow), "task_id"))
        _wait_state(owner, slow_id, {"running"})
        running_slow = owner.get_task(slow_id)
        slow_attempt_id = str(_value(running_slow, "attempt_id"))
        slow_attempt = daemon.service.store.conn.execute(
            "SELECT lease_id, fence, runtime_epoch FROM attempts WHERE id=?",
            (slow_attempt_id,),
        ).fetchone()
        assert slow_attempt is not None
        _wait_file(slow_pid_file, worker)
        slow_pid = int(slow_pid_file.read_text(encoding="utf-8"))
        _wait_file(slow_port_file, worker)
        slow_port = int(slow_port_file.read_text(encoding="utf-8"))
        port_probe = socket.socket()
        try:
            assert port_probe.connect_ex(("127.0.0.1", slow_port)) == 0
        finally:
            port_probe.close()
        owner.cancel_task(slow_id, idempotency_key="c12-runtime-cancel-request")
        cancelled = _wait_state(owner, slow_id, {"cancelled"})
        assert _value(cancelled, "result") in (None, {})
        _wait_pid_absent(slow_pid)
        _wait_port_available(slow_port)

        first_state = _stop_worker(worker, state_file)
        assert first_state["signals"]
        first_host_pid = int(readiness["pid"])
        with pytest.raises(OSError):
            os.kill(first_host_pid, 0)
        worker = None

        worker, _ready2, state_file2, readiness2 = _start_worker(
            daemon=daemon,
            support_root=support_root,
            source_checkout=source_checkout,
            facts=facts,
            suffix="restart",
        )
        stale_client = RuntimeProtocolClient(
            daemon.endpoint,
            Path(daemon.worker_credential_path).read_text(encoding="utf-8").strip(),
        )
        stale_output = b"stale-must-not-publish"
        stale_digest = "sha256:" + hashlib.sha256(stale_output).hexdigest()
        with pytest.raises(Exception, match="stale|settled|cancelled"):
            stale_client.generated.settle_attempt(
                slow_attempt_id,
                {
                    "attempt_id": slow_attempt_id,
                    "lease_id": slow_attempt["lease_id"],
                    "fence": int(slow_attempt["fence"]),
                    "runtime_epoch": int(slow_attempt["runtime_epoch"]),
                    "outputs": [
                        {
                            "name": "answer",
                            "kind": "object",
                            "media_type": "text/plain",
                            "digest": stale_digest,
                            "size": len(stale_output),
                            "data_base64": base64.b64encode(stale_output).decode("ascii"),
                        }
                    ],
                    "result": {"stale_replay": True},
                },
                idempotency_key="c12-stale-replay",
            )
        cancelled_events = daemon.service.events(str(_value(cancelled, "run_id")))
        assert [event.get("event_type", event.get("kind")) for event in cancelled_events].count("task.completed") == 0
        with pytest.raises(Exception):
            owner.get_object(stale_digest)
        restarted = owner.admit_task(
            capability_id="c12_cpu.echo",
            capability_digest=records["c12_cpu.echo"].capability_digest,
            input_object_ids=[],
            idempotency_key="c12-runtime-restart",
            spec={"inputs": {}},
        )
        restarted_id = str(_value(_mutation_data(restarted), "task_id"))
        restarted_task = _wait_state(owner, restarted_id, {"succeeded"})
        restarted_output = _value(_value(restarted_task, "result", {}), "outputs", [])[0]
        assert _value(restarted_output, "digest") == digest
        second_host_pid = int(readiness2["pid"])
        assert second_host_pid != first_host_pid
        _stop_worker(worker, state_file2)
        with pytest.raises(OSError):
            os.kill(second_host_pid, 0)
        worker = None
    finally:
        if worker is not None:
            _stop_worker(worker, state_file)
        daemon.stop()
