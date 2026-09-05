from __future__ import annotations

import hashlib
import json
import sys
import threading
from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from astrid.core.generation.backends.vibecomfy import (
    PipEmbeddedProfile,
    PipEmbeddedSession,
    VibeComfyBackend,
)


def _sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _profile(tmp_path: Path, *, root_suffix: str = "") -> PipEmbeddedProfile:
    root = tmp_path / root_suffix if root_suffix else tmp_path
    environment = root / "venv"
    source = root / "Astrid"
    pack = source / "astrid" / "packs"
    engine = root / "vibecomfy"
    nodes = engine / "custom_nodes"
    models = root / "models"
    output = root / "output"
    scratch = root / "scratch"
    cas = root / "cas"
    for path in (environment, pack, nodes, models, output, scratch, cas):
        path.mkdir(parents=True, exist_ok=True)
    interpreter = str(Path(sys.executable).resolve())
    facts = {
        "exact": {
            "interpreter": interpreter,
            "runtime_lock": "sha256:" + "1" * 64,
            "engine_lock": "sha256:" + "2" * 64,
            "model_digest": "sha256:" + "3" * 64,
            "custom_node_digest": "sha256:" + "4" * 64,
            "driver": "fixture-driver",
            "root": "sha256:" + "5" * 64,
            "port": 18765,
        },
        "minimum": {"vram_bytes": 1, "scratch_bytes": 1},
    }
    readiness = {
        "schema_version": "hc03-worker-readiness.v1",
        "status": "ready",
        "verified_facts": facts,
        "verified_facts_digest": _sha(facts),
        "runtime": {
            "endpoint": "http://127.0.0.1:18765",
            "port": 18765,
            "pid": 1,
            "process_birth_id": "proc-start-ticks:1",
            "runtime_instance_id": "runtime-instance-1",
            "runtime_epoch": 1,
            "schema_digest": "sha256:" + "6" * 64,
            "coordinator_epoch": "coordinator-1",
            "active_realm": "realm-1",
            "credential_reference": "/private/credential.token",
            "discovery_digest": "sha256:" + "7" * 64,
        },
        "launch": {
            "host_interpreter": interpreter,
            "source_checkout": str(source.resolve()),
            "engine_interpreter": interpreter,
            "output_root": str(output.resolve()),
            "pack_root": str(pack.resolve()),
            "support_root": str((root / "support").resolve()),
            "ready_file": str((root / "support" / "ready.json").resolve()),
            "state_file": str((root / "support" / "state.json").resolve()),
            "boot_manifest_path": str((root / "support" / "boot.json").resolve()),
            "boot_manifest_hash": "sha256:" + "8" * 64,
        },
        "worker_actor": "astrid-pack-host",
        "worker_scopes": [
            "handshake",
            "worker:register",
            "worker:execute",
            "tasks:read",
            "objects:read",
            "objects:write",
        ],
    }
    return PipEmbeddedProfile.from_hc03(
        python_executable=interpreter,
        python_environment=environment,
        vibecomfy_revision="dc8d962a8e330015bbb209080292fad248f1ceb3",
        package_lock_digest="sha256:" + "2" * 64,
        astrid_source_root=source,
        astrid_pack_root=pack,
        engine_root=engine,
        custom_nodes_root=nodes,
        model_root=models,
        output_root=output,
        scratch_root=scratch,
        cas_root=cas,
        hc03_profile=readiness,
    )


def _profile_kwargs(profile: PipEmbeddedProfile) -> dict[str, Any]:
    return {field.name: getattr(profile, field.name) for field in fields(profile)}


def test_profile_digests_are_deterministic_and_explicit(tmp_path: Path) -> None:
    first = _profile(tmp_path)
    second = _profile(tmp_path)

    assert first.to_dict() == second.to_dict()
    assert first.command[0] == str(Path(sys.executable).resolve())
    assert first.command[1] == "-c"
    assert "from vibecomfy.runtime.run import run_sync" in first.command[2]
    assert first.command_digest.startswith("sha256:")
    assert first.readiness_digest.startswith("sha256:")
    assert first.profile_digest.startswith("sha256:")


def test_profile_binds_interpreter_lock_and_all_roots(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    identity = profile.identity

    for field in (
        "python_executable",
        "python_environment",
        "vibecomfy_revision",
        "package_lock_digest",
        "astrid_source_root",
        "astrid_pack_root",
        "engine_root",
        "custom_nodes_root",
        "model_root",
        "output_root",
        "scratch_root",
        "cas_root",
        "hc03",
    ):
        assert field in identity

    with pytest.raises(ValueError, match="interpreter"):
        PipEmbeddedProfile.from_hc03(
            **{**_profile_kwargs(profile), "python_executable": "/usr/bin/python3"}
        )


def test_profile_relocation_changes_root_bearing_identity(tmp_path: Path) -> None:
    first = _profile(tmp_path, root_suffix="one")
    second = _profile(tmp_path, root_suffix="two")

    assert first.profile_digest != second.profile_digest
    assert first.command_digest != second.command_digest


def test_profile_rejects_missing_readiness_or_secret_material(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    with pytest.raises(ValueError, match="verified facts digest"):
        PipEmbeddedProfile.from_hc03(
            **{**_profile_kwargs(profile), "hc03_profile": {**profile.hc03_profile, "verified_facts_digest": "sha256:" + "0" * 64}}
        )
    with pytest.raises(ValueError, match="secret-shaped"):
        PipEmbeddedProfile.from_hc03(
            **{**_profile_kwargs(profile), "hc03_profile": {**profile.hc03_profile, "worker_token": "do-not-copy"}}
        )


def test_session_is_cold_only_and_never_reuses_a_handle(tmp_path: Path) -> None:
    profile = _profile(tmp_path)
    calls: list[tuple[str, Path]] = []

    class Handle:
        def __init__(self, value: object, staging: Path) -> None:
            self.value = value
            self.staging = staging

        def run(self) -> object:
            calls.append(("run", self.staging))
            return self.value

        def terminate(self) -> None:
            calls.append(("terminate", self.staging))

        def reap(self) -> None:
            calls.append(("reap", self.staging))

        def cleanup(self) -> None:
            calls.append(("cleanup", self.staging))

    handles = 0

    def factory(_profile: PipEmbeddedProfile, workflow: object, staging: Path) -> Handle:
        nonlocal handles
        handles += 1
        return Handle(workflow, staging)

    session = PipEmbeddedSession(profile, execution_factory=factory)
    assert session.run("a", task_identity="task-a") == "a"
    assert session.run("b", task_identity="task-b") == "b"
    assert handles == 2
    assert session.warm is False
    assert session.last_warm_reused is False
    assert not list(Path(profile.scratch_root).glob("pip-embedded-*"))
    assert [name for name, _path in calls] == ["run", "reap", "cleanup", "run", "reap", "cleanup"]


class _BlockingHandle:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.released = threading.Event()
        self.calls: list[str] = []

    def run(self) -> str:
        self.started.set()
        self.released.wait(timeout=5)
        return "cancelled-run"

    def terminate(self) -> None:
        self.calls.append("terminate")
        self.released.set()

    def reap(self) -> None:
        self.calls.append("reap")

    def cleanup(self) -> None:
        self.calls.append("cleanup")


def test_cancel_terminates_reaps_cleans_and_rejects_mismatched_identity(tmp_path: Path) -> None:
    handle = _BlockingHandle()
    session = PipEmbeddedSession(
        _profile(tmp_path),
        execution_factory=lambda _profile, _workflow, _staging: handle,
    )
    thread = threading.Thread(target=session.run, args=("workflow",), kwargs={"task_identity": "task-a"})
    thread.start()
    assert handle.started.wait(timeout=2)
    with pytest.raises(RuntimeError, match="identity mismatch"):
        session.cancel(task_identity="task-b")
    assert session.poisoned is True
    handle.released.set()
    thread.join(timeout=2)


def test_cancel_and_release_transition_exactly_once(tmp_path: Path) -> None:
    handle = _BlockingHandle()
    session = PipEmbeddedSession(
        _profile(tmp_path),
        execution_factory=lambda _profile, _workflow, _staging: handle,
    )
    thread = threading.Thread(target=session.run, args=("workflow",))
    thread.start()
    assert handle.started.wait(timeout=2)
    assert session.cancel()["status"] == "cancelled"
    thread.join(timeout=2)
    assert handle.calls == ["terminate", "reap", "cleanup"]
    assert session.release()["status"] == "cancelled"
    assert handle.calls == ["terminate", "reap", "cleanup"]


@pytest.mark.parametrize("failure_method", ["run", "reap", "cleanup"])
def test_lifecycle_failure_poisons_session_and_requires_clean_cold_recovery(
    tmp_path: Path, failure_method: str
) -> None:
    class FailingHandle(_BlockingHandle):
        def run(self) -> str:
            if failure_method == "run":
                raise RuntimeError("run failed")
            return "ok"

        def terminate(self) -> None:
            super().terminate()
            if failure_method == "terminate":
                raise RuntimeError("terminate failed")

        def reap(self) -> None:
            super().reap()
            if failure_method == "reap":
                raise RuntimeError("reap failed")

        def cleanup(self) -> None:
            super().cleanup()
            if failure_method == "cleanup":
                raise RuntimeError("cleanup failed")

    session = PipEmbeddedSession(
        _profile(tmp_path),
        execution_factory=lambda _profile, _workflow, _staging: FailingHandle(),
    )
    if failure_method == "run":
        with pytest.raises(RuntimeError, match="run failed"):
            session.run("workflow")
    else:
        with pytest.raises(RuntimeError):
            session.run("workflow")
    assert session.poisoned is True
    with pytest.raises(RuntimeError, match="new cold instance"):
        session.run("retry")
    recovered = PipEmbeddedSession(_profile(tmp_path), execution_factory=lambda *_args: FailingHandle())
    assert recovered.poisoned is False


def test_terminate_failure_poisons_cancel_and_requires_a_new_instance(tmp_path: Path) -> None:
    class FailingTerminate(_BlockingHandle):
        def terminate(self) -> None:
            super().terminate()
            raise RuntimeError("terminate failed")

    handle = FailingTerminate()
    session = PipEmbeddedSession(
        _profile(tmp_path),
        execution_factory=lambda _profile, _workflow, _staging: handle,
    )
    thread = threading.Thread(target=session.run, args=("workflow",))
    thread.start()
    assert handle.started.wait(timeout=2)
    with pytest.raises(RuntimeError, match="cleanup failed"):
        session.cancel()
    thread.join(timeout=2)
    assert session.poisoned is True


def test_backend_requires_typed_profile_and_validates_output_root(tmp_path: Path) -> None:
    backend = VibeComfyBackend()
    with pytest.raises(ValueError, match="explicit PipEmbeddedProfile"):
        backend._run_workflow(object())
    session = PipEmbeddedSession(_profile(tmp_path))
    with pytest.raises(ValueError, match="outside"):
        session.validate_output_dir(tmp_path / "elsewhere")


def test_profile_command_has_no_download_or_backend_selector() -> None:
    command = PipEmbeddedProfile.__dataclass_fields__
    assert "python_executable" in command
    # The executable command is deliberately a call description, not the
    # legacy CLI and therefore carries no ensure/download/backend flags.
    assert "--ensure-models" not in " ".join(("python", "-m", "vibecomfy.runtime.run", "run_sync"))
    assert "--ensure-packs" not in " ".join(("python", "-m", "vibecomfy.runtime.run", "run_sync"))
    assert "--backend" not in " ".join(("python", "-m", "vibecomfy.runtime.run", "run_sync"))
