from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from astrid.core.generation.backends.vibecomfy import (
    _PIP_EMBEDDED_SCRIPT,
    PipEmbeddedProfile,
    PipEmbeddedSession,
    PipEmbeddedTimeouts,
    VibeComfyBackend,
    _ChildResult,
    _strict_json_value,
    _strict_load_json,
)

REVISION = "dc8d962a8e330015bbb209080292fad248f1ceb3"


def digest(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def kwargs(profile: PipEmbeddedProfile) -> dict[str, Any]:
    return {field.name: getattr(profile, field.name) for field in dataclasses.fields(profile)}


def workflow() -> Any:
    sys.path.insert(0, "/Users/peteromalley/Documents/reigh-workspace/vibecomfy")
    from vibecomfy.workflow import VibeWorkflow, WorkflowSource

    return VibeWorkflow(
        id="fixture", source=WorkflowSource(id="fixture", path="fixture", source_type="ready")
    )


def make_profile(tmp_path: Path) -> PipEmbeddedProfile:
    root = tmp_path / "layout"
    env, exe = root / "venv", root / "venv" / "bin" / "python"
    source, pack, engine = root / "Astrid", root / "Astrid" / "astrid" / "packs", root / "vibecomfy"
    nodes, models, output, scratch, cas, support = (
        engine / "custom_nodes",
        root / "models",
        root / "output",
        root / "scratch",
        root / "cas",
        root / "support",
    )
    for path in (pack, nodes, models, output, scratch, cas, support):
        path.mkdir(parents=True, exist_ok=True)
    exe.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(sys.executable, exe)
    exe.chmod(0o755)
    engine.mkdir(parents=True, exist_ok=True)
    lock = engine / "uv.lock"
    lock.write_bytes(b"pinned engine lock")
    model_manifest, node_manifest = root / "models.json", root / "nodes.json"
    model_manifest.write_text('{"files":[]}', encoding="utf-8")
    node_manifest.write_text('{"files":[]}', encoding="utf-8")
    roots = {
        name: digest({"path": str(path)})
        for name, path in (
            ("source", source),
            ("model", models),
            ("custom_node", nodes),
            ("scratch", scratch),
            ("cas", cas),
        )
    }
    host, child = str(Path(sys.executable).resolve()), str(exe.resolve())
    version = ".".join(str(x) for x in sys.version_info[:3])
    facts = {
        "exact": {
            "interpreter": json.dumps(
                [
                    {"path": host, "version": version, "sha256": file_digest(Path(sys.executable))},
                    {"path": child, "version": version, "sha256": file_digest(exe)},
                ],
                separators=(",", ":"),
            ),
            "runtime_lock": "sha256:" + "1" * 64,
            "engine_lock": file_digest(lock),
            "model_digest": "sha256:" + "3" * 64,
            "custom_node_digest": "sha256:" + "4" * 64,
            "driver": "fixture-driver",
            "root": digest(dict(sorted(roots.items()))),
            "port": 18765,
        },
        "minimum": {"vram_bytes": 1, "scratch_bytes": 1},
    }
    readiness = {
        "schema_version": "hc03-worker-readiness.v1",
        "status": "ready",
        "verified_facts": facts,
        "verified_facts_digest": digest(facts),
        "runtime": {
            "endpoint": "http://127.0.0.1:18765",
            "port": 18765,
            "pid": 1,
            "process_birth_id": "fixture-process",
            "runtime_instance_id": "fixture-runtime",
            "runtime_epoch": 1,
            "schema_digest": "sha256:" + "6" * 64,
            "coordinator_epoch": "fixture-coordinator",
            "active_realm": "fixture-realm",
            "credential_reference": str(support / "credential"),
            "discovery_digest": "sha256:" + "7" * 64,
        },
        "launch": {
            "host_interpreter": host,
            "source_checkout": str(source),
            "engine_interpreter": child,
            "output_root": str(output),
            "pack_root": str(pack),
            "support_root": str(support),
            "ready_file": str(support / "ready.json"),
            "state_file": str(support / "state.json"),
            "boot_manifest_path": str(support / "boot.json"),
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
    evidence = {
        "engine_lock_path": str(lock),
        "vibecomfy_root": str(engine),
        "vibecomfy_revision": REVISION,
        "python_sha256": file_digest(exe),
        "python_version": version,
        "python_prefix": str(env),
        "root_map": roots,
        "model_manifest": {
            "path": str(model_manifest),
            "digest": facts["exact"]["model_digest"],
            "sha256": file_digest(model_manifest),
        },
        "custom_node_manifest": {
            "path": str(node_manifest),
            "digest": facts["exact"]["custom_node_digest"],
            "sha256": file_digest(node_manifest),
        },
    }
    return PipEmbeddedProfile.from_hc03(
        python_executable=exe,
        python_environment=env,
        vibecomfy_revision=REVISION,
        package_lock_digest=file_digest(lock),
        astrid_source_root=source,
        astrid_pack_root=pack,
        engine_root=engine,
        custom_nodes_root=nodes,
        model_root=models,
        output_root=output,
        scratch_root=scratch,
        cas_root=cas,
        hc03_profile=readiness,
        installation_evidence=evidence,
        hc03_handoff_hash="sha256:" + "9" * 64,
    )


class Handle:
    def __init__(self, staging: Path, block: bool = False) -> None:
        self.output_dir, self.block = staging / "engine-output", block
        self.nonce = "nonce"
        self.started, self.release = threading.Event(), threading.Event()
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")
        self.output_dir.mkdir()

    def wait_ready(self, timeout: float) -> None:
        self.calls.append("ready")

    def go(self) -> None:
        self.calls.append("go")
        self.started.set()

    def run(self, timeout: float) -> _ChildResult:
        self.calls.append("run")
        if self.block:
            self.release.wait(timeout=timeout)
        path = self.output_dir / "frame.bin"
        path.write_bytes(b"frame")
        return _ChildResult(self.nonce, "run", None, ((path.name, 5, file_digest(path)),))

    def terminate(self, term: float, kill: float, reap: float) -> None:
        self.calls.append("terminate")
        self.release.set()

    def cleanup(self) -> None:
        self.calls.append("cleanup")


def test_profile_freezes_nested_readiness_and_actual_command_flags(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    before = profile.profile_digest
    exported = profile.identity
    exported["hc03"]["runtime"]["port"] = 1
    assert profile.profile_digest == before
    with pytest.raises(TypeError):
        profile.hc03_profile["runtime"]["port"] = 1  # type: ignore[index]
    assert profile.command[:4] == (str(profile.python_executable), "-I", "-B", "-c")
    assert not {"--backend", "--ensure-models", "--ensure-packs"}.intersection(profile.command)


def test_hc03_and_installation_mismatches_fail_closed(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    raw = json.loads(json.dumps(profile.to_dict()["readiness"]))
    raw["runtime"]["port"] = 18766
    with pytest.raises(ValueError, match="endpoint/port"):
        PipEmbeddedProfile.from_hc03(**{**kwargs(profile), "hc03_profile": raw})
    evidence = dict(profile.installation_evidence)
    evidence["vibecomfy_revision"] = "0" * 40
    with pytest.raises(ValueError, match="revision"):
        PipEmbeddedProfile.from_hc03(**{**kwargs(profile), "installation_evidence": evidence})


def test_reservation_busy_and_factory_cancel_race(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    entered, release, holder = threading.Event(), threading.Event(), []

    def factory(_p: PipEmbeddedProfile, _r: Any, staging: Path) -> Handle:
        entered.set()
        release.wait(timeout=2)
        handle = Handle(staging)
        handle.nonce = _r["nonce"]
        holder.append(handle)
        return handle

    session = PipEmbeddedSession(profile, execution_factory=factory)
    run_error: list[BaseException] = []

    def run_once() -> None:
        try:
            session.run(workflow(), task_identity="race", out_dir=Path(profile.output_root))
        except BaseException as exc:
            run_error.append(exc)

    thread = threading.Thread(target=run_once)
    thread.start()
    assert entered.wait(timeout=1)
    with pytest.raises(RuntimeError, match="already in progress"):
        session.run(workflow(), task_identity="other", out_dir=Path(profile.output_root))
    control_result: list[dict[str, Any]] = []
    control = threading.Thread(
        target=lambda: control_result.append(session.cancel(task_identity="race"))
    )
    control.start()
    time.sleep(0.05)
    release.set()
    control.join(timeout=3)
    thread.join(timeout=3)
    assert run_error and "cancelled" in str(run_error[0])
    assert control_result and control_result[0]["reaped"] is True
    assert holder[0].calls == ["terminate", "cleanup"]


def test_wrong_identity_and_repeated_control_are_deterministic(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    holder: list[Handle] = []

    def factory(_p: PipEmbeddedProfile, _r: Any, staging: Path) -> Handle:
        handle = Handle(staging, block=True)
        handle.nonce = _r["nonce"]
        holder.append(handle)
        return handle

    session = PipEmbeddedSession(profile, execution_factory=factory)

    def run_once() -> None:
        try:
            session.run(workflow(), out_dir=Path(profile.output_root))
        except RuntimeError:
            pass

    thread = threading.Thread(target=run_once)
    thread.start()
    while not holder:
        time.sleep(0.01)
    assert holder[0].started.wait(timeout=2)
    with pytest.raises(RuntimeError, match="identity mismatch"):
        session.cancel(task_identity="wrong")
    holder[0].release.set()
    thread.join(timeout=3)
    assert session.poisoned


def test_output_symlink_and_partial_copy_rollback(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    session = PipEmbeddedSession(profile)
    source = Path(profile.scratch_root) / "source"
    source.mkdir()
    (source / "good").write_bytes(b"good")
    (source / "escape").symlink_to(tmp_path / "outside")
    handle = type("OutputHandle", (), {"output_dir": source})()
    result = _ChildResult(
        "n",
        "r",
        None,
        (("good", 4, file_digest(source / "good")), ("missing", 1, "sha256:" + "0" * 64)),
    )
    with pytest.raises(ValueError):
        session._collect_outputs(handle, result, Path(profile.output_root))
    assert not list(Path(profile.output_root).glob("pip-embedded-*"))
    with pytest.raises(ValueError):
        session._collect_outputs(
            handle,
            _ChildResult("n", "r", None, (("escape", 1, "sha256:" + "0" * 64),)),
            Path(profile.output_root),
        )


def test_real_child_transport_argv_env_pgid_and_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from astrid.core.generation.backends import vibecomfy as backend

    script = r"""import hashlib,json,os,time
from pathlib import Path
request=json.loads(Path(__import__("sys").argv[1]).read_text()); a=__import__("sys").argv
ready={"schema":"astrid.vibecomfy.ready.v1","nonce":request["nonce"],"request_digest":request["request_digest"],"profile_digest":request["profile_digest"],"config_digest":request["config_digest"],"ok":True,"interpreter":{"executable":__import__("sys").executable,"prefix":os.environ["VIRTUAL_ENV"],"version":"3.11.11"},"flags":["-I","-B"],"pythonpath":os.environ.get("PYTHONPATH"),"pgid":os.getpgid(os.getpid())}; Path(a[2]).write_text(json.dumps(ready,separators=(",",":")))
while not Path(a[3]).exists(): time.sleep(.01)
out=Path(request["config"]["extra"]["output_directory"]); out.mkdir(parents=True,exist_ok=True); p=out/"child.bin"; p.write_bytes(b"child"); payload={"schema":"astrid.vibecomfy.result.v1","nonce":request["nonce"],"request_digest":request["request_digest"],"profile_digest":request["profile_digest"],"config_digest":request["config_digest"],"status":"succeeded","run_id":"child-run","prompt_id":None,"outputs":[{"relative_path":"child.bin","size_bytes":5,"sha256":"sha256:"+hashlib.sha256(b"child").hexdigest()}]}; Path(a[4]).write_text(json.dumps(payload,separators=(",",":")))"""
    monkeypatch.setattr(backend, "_PIP_EMBEDDED_SCRIPT", script)
    profile = make_profile(tmp_path)
    staging = Path(profile.scratch_root) / "transport"
    staging.mkdir()
    handle = backend._SubprocessEmbeddedExecution(
        profile,
        {
            "schema": "astrid.vibecomfy.request.v1",
            "nonce": "transport",
            "profile_digest": profile.profile_digest,
            "workflow": {},
            "workflow_digest": digest({}),
        },
        staging,
    )
    handle.start()
    assert handle._process is not None and os.getpgid(handle._process.pid) == handle._process.pid
    handle.wait_ready(2)
    ready = json.loads(handle.ready_path.read_text())
    assert (
        ready["flags"] == ["-I", "-B"]
        and ready["pythonpath"] is None
        and ready["pgid"] == handle._process.pid
    )
    handle.go()
    assert handle.run(2).run_id == "child-run"
    handle.terminate(1, 1, 1)
    handle.cleanup()


def test_missing_profile_and_nonfinite_timeout_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit PipEmbeddedProfile"):
        VibeComfyBackend()._run_workflow(object())
    with pytest.raises(ValueError):
        PipEmbeddedTimeouts(execution_seconds=float("inf"))
    session = PipEmbeddedSession(make_profile(tmp_path))
    with pytest.raises(ValueError, match="outside"):
        session.validate_output_dir(tmp_path / "elsewhere")


def test_transport_is_strict_and_never_follows_result_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text('{"ok":true}', encoding="utf-8")
    link = tmp_path / "result.json"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="safely openable"):
        _strict_load_json(link, limit=1024)
    with pytest.raises(ValueError, match="duplicate"):
        duplicate = tmp_path / "duplicate.json"
        duplicate.write_text('{"x":1,"x":2}', encoding="utf-8")
        _strict_load_json(duplicate, limit=1024)
    nested: object = "leaf"
    for _ in range(66):
        nested = [nested]
    with pytest.raises(ValueError, match="nesting limit"):
        _strict_json_value(nested)


def test_destination_symlink_and_legacy_transport_are_rejected(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    session = PipEmbeddedSession(profile)
    source = Path(profile.scratch_root) / "source"
    source.mkdir()
    output = source / "frame.bin"
    output.write_bytes(b"frame")
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = Path(profile.output_root) / "alias"
    destination.symlink_to(outside, target_is_directory=True)
    handle = type("OutputHandle", (), {"output_dir": source})()
    result = _ChildResult("n", "r", None, (("frame.bin", 5, file_digest(output)),))
    with pytest.raises(ValueError, match="symlink"):
        session._collect_outputs(handle, result, destination)
    assert "run_embedded_sync" in _PIP_EMBEDDED_SCRIPT
    assert "run_sync" not in _PIP_EMBEDDED_SCRIPT
    assert "pickle" not in _PIP_EMBEDDED_SCRIPT
