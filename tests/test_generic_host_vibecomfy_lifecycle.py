from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from astrid.core.execution import generic_host
from astrid.core.execution.generic_host import GenericPackHost
from tests.test_generic_host import FakeRuntime


class _FakeCheckout:
    def __init__(self, events: list[str], *, spawn_child: bool) -> None:
        self.events = events
        self.child = (
            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
            if spawn_child
            else None
        )
        self.events.append("construct")

    def _revalidate_host_session(self) -> None:
        self.events.append("observe")

    def cancel(self) -> dict[str, object]:
        self.events.append("cancel")
        return {"ok": True, "cancelled": True}

    def release(self, *, reason: str = "requested") -> dict[str, object]:
        if self.child is not None:
            self.child.terminate()
            self.child.wait(timeout=5)
            assert self.child.returncode is not None
            self.events.append("old-child-exited")
        self.events.append(f"release:{reason}")
        return {"ok": True, "released": True}


def _task(task_id: str, digest: str) -> dict[str, object]:
    return {
        "task": {
            "id": task_id,
            "capability": "vibecomfy.run",
            "project_id": "fixture-project",
            "attempt_id": f"{task_id}-attempt",
            "fence": 1,
            "input_object_ids": [digest],
            "spec": {"spec": {"inputs": {}, "input_digests": [{"name": "workflow", "digest": digest}]}},
        }
    }


def _install_fixture(tmp_path: Path) -> tuple[str, bytes]:
    data = b"canonical workflow fixture\n"
    digest = hashlib.sha256(data).hexdigest()
    capability = tmp_path / "vibecomfy-fixture"
    capability.mkdir()
    command = (
        "from pathlib import Path; out=Path('{out}'); out.mkdir(parents=True,exist_ok=True); "
        "(out/'result.txt').write_bytes((out.parent/'inputs'/'workflow').read_bytes())"
    )
    manifest = {
        "schema_version": 1,
        "id": "vibecomfy.run",
        "name": "VibeComfy lifecycle fixture",
        "kind": "external",
        "version": "1.0",
        "command": {"argv": ["{python_exec}", "-c", command]},
        "inputs": [{"name": "workflow", "type": "file"}],
        "outputs": [{"name": "result", "type": "file", "path_template": "{out}/result.txt", "artifact_type": "text/plain"}],
        "metadata": {"adapter_family": "local_generation", "resource_keys": ["gpu"]},
    }
    (capability / "executor.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    return digest, data


def _profile() -> dict[str, object]:
    return {
        "schema_version": "hc03-worker-readiness.v1",
        "status": "ready",
        "verified_facts_digest": "facts-a",
        "verified_facts": {"exact": {
            "interpreter": "python", "runtime_lock": "runtime", "engine_lock": "engine",
            "model_digest": "sha256:" + "a" * 64, "custom_node_digest": "sha256:" + "b" * 64,
            "driver": "driver", "root": "/tmp/root", "port": 8188,
        }, "minimum": {"vram_bytes": 1, "scratch_bytes": 1}},
        "runtime": {"runtime_instance_id": "00000000-0000-4000-8000-000000000001"},
        "vibecomfy_session": {
            "session_dir": "/tmp/session", "process_birth_id": "process-a", "comfy_process_birth_id": "comfy-a",
            "server_url": "http://127.0.0.1:8188", "source_revision": "source-a",
            "source_content_digest": "sha256:" + "c" * 64, "config_digest": "sha256:" + "d" * 64,
        },
    }


def test_generic_host_run_task_keeps_same_resident_identity_warm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    digest, data = _install_fixture(tmp_path)
    runtime = FakeRuntime()
    runtime.get_object = lambda requested: data  # type: ignore[method-assign]
    profile_reads: list[int] = []

    def read_profile() -> dict[str, object]:
        profile = _profile()
        pid = 100 + len(profile_reads)
        profile_reads.append(pid)
        session = profile["vibecomfy_session"]
        assert isinstance(session, dict)
        session["pid"] = pid
        return profile

    monkeypatch.setattr(generic_host, "_read_readiness_profile_document", read_profile)
    identities = iter((("execution-a", "model-a"), ("execution-a", "model-a"), ("execution-b", "model-b"), ("execution-b", "model-b")))
    monkeypatch.setattr(generic_host, "_prepare_vibecomfy_execution_identity", lambda *args: (lambda value: (value[0], value[1], "template-a", {"model_id": value[1], "resident_metadata": {"model_assets": [value[1]]}}))(next(identities)))
    from astrid.core.generation.backends import vibecomfy
    events: list[str] = []
    monkeypatch.setattr(
        vibecomfy.CheckoutServerAdapter,
        "from_host_session",
        classmethod(lambda cls, **kwargs: (
            events.append(f"profile-pid:{kwargs['hc03_profile']['vibecomfy_session']['pid']}"),
            _FakeCheckout(events, spawn_child=("old-child-exited" in events or "construct" not in events)),
        )[1]),
    )
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    for task_id in ("warm-1", "warm-2", "changed-model", "changed-model-followup"):
        task = _task(task_id, digest)
        runtime.tasks[task_id] = task
        assert host.run_task(task, lease_token=f"lease-{task_id}")["task"]["status"] == "completed"
    observed_binding = runtime.settlements[0][2]["result"]["managed_tool_session"]["binding"]
    assert observed_binding["launch_generation"] == "process-a"
    assert observed_binding["engine_birth_id"] == "comfy-a"
    assert "release:capacity_replacement" not in events[: events.index("old-child-exited")]
    release_index = events.index("release:capacity_replacement")
    assert events.index("old-child-exited") < release_index
    assert release_index < events.index("construct", release_index + 1)
    assert "profile-pid:103" in events
    assert events.count("release:capacity_replacement") == 1
    host.managed_tool_session.close()


def test_generic_host_run_registration_fails_closed_without_readiness_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    digest, data = _install_fixture(tmp_path)
    runtime = FakeRuntime()
    runtime.get_object = lambda requested: data  # type: ignore[method-assign]
    monkeypatch.setattr(generic_host, "_read_readiness_profile_document", lambda: None)
    monkeypatch.setattr(generic_host, "_prepare_vibecomfy_execution_identity", lambda *args: ("execution-pip", "model-a", "template-a", {"model_id": "model-a", "resident_metadata": {}}))
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    task = _task("pip-embedded", digest)
    runtime.tasks["pip-embedded"] = task
    with pytest.raises(generic_host.HostError, match="unavailable.*readiness profile"):
        host.run_task(task, lease_token="lease-pip")
    assert runtime.settlements == []
