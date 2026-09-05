from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import shutil
import subprocess
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
    _census_owned_group,
    _ChildResult,
    _normalize_hc03_profile,
    _PipEmbeddedError,
    _ProcessOwnership,
    _retain_hc03_validation,
    _revalidate_launch_evidence,
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
    producer_source = root / "producer-repo"
    nodes, models, output, scratch, cas, support = (
        engine / "custom_nodes",
        root / "models",
        root / "output",
        root / "scratch",
        root / "cas",
        root / "support",
    )
    for path in (pack, nodes, models, output, scratch, cas, support, producer_source):
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
            ("source", producer_source),
            ("model", models),
            ("custom_node", nodes),
            ("scratch", scratch),
            ("cas", cas),
        )
    }
    host, child = str(Path(sys.executable).resolve()), str(exe.resolve())
    version = ".".join(str(x) for x in sys.version_info[:3])
    model_digest = digest({"files": []})
    node_digest = digest({"files": []})
    facts = {
        "exact": {
            "interpreter": json.dumps(
                [
                    json.dumps({"path": host, "version": version, "sha256": file_digest(Path(sys.executable))}, separators=(",", ":")),
                    json.dumps({"path": child, "version": version, "sha256": file_digest(exe)}, separators=(",", ":")),
                ],
                separators=(",", ":"),
            ),
            "runtime_lock": "sha256:" + "1" * 64,
            "engine_lock": file_digest(lock),
            "model_digest": model_digest,
            "custom_node_digest": node_digest,
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
            "digest": model_digest,
            "sha256": file_digest(model_manifest),
        },
        "custom_node_manifest": {
            "path": str(node_manifest),
            "digest": node_digest,
            "sha256": file_digest(node_manifest),
        },
        "producer_source_root": str(producer_source),
        "package_inventory": [
            {"path": str(exe), "sha256": file_digest(exe)},
            {"path": str(lock), "sha256": file_digest(lock)},
        ],
        "resolver_roots": [str(models), str(nodes)],
        "resolver_digest": digest({"roots": [str(models), str(nodes)]}),
    }
    handoff = support / "hc03-handoff.json"
    handoff.write_bytes(json.dumps(readiness, sort_keys=True, separators=(",", ":")).encode())
    normalized = _normalize_hc03_profile(readiness)
    normalized.pop("_interpreter_identities")
    handoff_hash = file_digest(handoff)
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
        hc03_handoff_hash=handoff_hash,
        hc03_handoff_path=handoff,
        hc03_trust=_retain_hc03_validation(readiness, handoff),
    )


class Handle:
    def __init__(self, staging: Path, block: bool = False) -> None:
        self.output_dir, self.block = staging / "engine-output", block
        self.nonce = "nonce"
        self.started, self.release = threading.Event(), threading.Event()
        self.calls: list[str] = []

    def start(self) -> None:
        self.calls.append("start")
        self.output_dir.mkdir(exist_ok=True)

    def wait_ready(self, timeout: float) -> None:
        self.calls.append("ready")

    def go(self) -> None:
        self.calls.append("go")
        self.started.set()

    def wait_completed(self, timeout: float, cancel_event: threading.Event | None = None) -> None:
        self.calls.append("wait")
        if self.block:
            while not self.release.wait(timeout=0.01):
                if cancel_event is not None and cancel_event.is_set():
                    continue

    def read_result(self) -> _ChildResult:
        path = self.output_dir / "frame.bin"
        path.write_bytes(b"frame")
        return _ChildResult(self.nonce, "run", None, ((path.name, 5, file_digest(path)),))

    def terminate(self, term: float, kill: float, reap: float) -> None:
        self.calls.append("terminate")
        self.release.set()
        return {"ok": True, "terminated": True, "reaped": True, "group_quiescent": True}

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


def test_idle_control_disposes_session_and_blocks_resurrection(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    session = PipEmbeddedSession(profile)
    disposed = session.release()
    assert disposed["status"] == "disposed"
    with pytest.raises(_PipEmbeddedError, match="session_disposed"):
        session._reserve("never")
    with pytest.raises(_PipEmbeddedError, match="session_disposed"):
        session.run(workflow(), out_dir=Path(profile.output_root))


def test_active_controls_require_exact_task_and_nonce(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    holder: list[Handle] = []

    def factory(_p: PipEmbeddedProfile, request: Any, staging: Path) -> Handle:
        handle = Handle(staging, block=True)
        handle.nonce = request["nonce"]
        holder.append(handle)
        return handle

    session = PipEmbeddedSession(profile, execution_factory=factory)
    errors: list[BaseException] = []
    thread = threading.Thread(
        target=lambda: _capture_error(
            errors, lambda: session.run(workflow(), task_identity="exact", out_dir=Path(profile.output_root))
        )
    )
    thread.start()
    while not holder or not holder[0].started.wait(timeout=0.02):
        pass
    nonce = session.active_invocation()["nonce"]
    for identity, supplied_nonce in (("exact", None), ("exact", "wrong"), ("wrong", nonce)):
        with pytest.raises(_PipEmbeddedError, match="identity mismatch"):
            session.cancel(task_identity=identity, invocation_nonce=supplied_nonce)
    outcome = session.cancel(task_identity="exact", invocation_nonce=nonce)
    thread.join(timeout=3)
    assert outcome["status"] == "identity-mismatch"
    assert holder[0].calls.count("terminate") == 1
    assert errors


def test_normal_session_uses_admitted_custody_and_publishes_durable_output(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    session = PipEmbeddedSession(profile, execution_factory=lambda _p, request, staging: _request_handle(request, staging))
    result = session.run(workflow(), task_identity="publish", out_dir=Path(profile.output_root))
    assert result.published_outputs and result.published_outputs[0].is_file()
    assert session.active_invocation() is None
    assert list(Path(profile.output_root).glob(".pip-embedded-staging-*")) == []


def test_reaped_owned_group_uses_retained_birth_and_unknown_is_not_quiescent(tmp_path: Path) -> None:
    del tmp_path
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(.05)"],
        start_new_session=True,
    )
    deadline = time.monotonic() + 2
    census = _census_owned_group(process, deadline)
    while not census.known or census.leader_birth is None:
        if time.monotonic() >= deadline:
            pytest.fail(f"could not capture child census: {census}")
        time.sleep(.01)
        census = _census_owned_group(process, deadline)
    process.wait(timeout=2)
    ownership = dataclasses.replace(
        _ProcessOwnership(process.pid, process.pid, census.leader_birth),
        pre_reap_quiescent=True,
        reaped=True,
    )
    final = _census_owned_group(process, time.monotonic() + 1, reaped=True, ownership=ownership)
    assert final.known and final.live == ()
    unproven = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    unproven.wait(timeout=2)
    assert not _census_owned_group(unproven, time.monotonic() + 1, reaped=True).known


def test_lock_drift_is_readiness_mismatch_before_spawn(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    lock = Path(profile.installation_evidence["engine_lock_path"])
    lock.write_bytes(b"mutated lock")
    with pytest.raises(_PipEmbeddedError, match="installation_inventory"):
        _revalidate_launch_evidence(profile)


def _request_handle(request: Any, staging: Path) -> Handle:
    handle = Handle(staging)
    handle.nonce = request["nonce"]
    return handle


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
        target=lambda: control_result.append(session.cancel(
            task_identity="race", invocation_nonce=session.active_invocation()["nonce"]
        ))
    )
    control.start()
    time.sleep(0.05)
    release.set()
    control.join(timeout=3)
    thread.join(timeout=3)
    assert run_error and "cancelled" in str(run_error[0])
    assert control_result and control_result[0]["reaped"] is True
    assert holder[0].calls[-2:] == ["terminate", "cleanup"]


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
        session.cancel(task_identity="wrong", invocation_nonce="wrong")
    holder[0].release.set()
    thread.join(timeout=3)
    assert session.poisoned


def test_output_symlink_and_partial_copy_rollback(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    session = PipEmbeddedSession(profile)
    source = Path(profile.scratch_root) / "source" / "engine-output"
    source.parent.mkdir()
    source.mkdir()
    (source / "good").write_bytes(b"good")
    (source / "escape").symlink_to(tmp_path / "outside")
    source_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    destination = Path(profile.output_root)
    destination_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    record = {
        "staging": source.parent,
        "source_dir_fd": source_fd,
        "source_identity": (os.fstat(source_fd).st_dev, os.fstat(source_fd).st_ino),
        "destination_fd": destination_fd,
    }
    result = _ChildResult(
        "n",
        "r",
        None,
        (("good", 4, file_digest(source / "good")), ("missing", 1, "sha256:" + "0" * 64)),
    )
    with pytest.raises(ValueError):
        session._collect_outputs(record, result, destination)
    assert not list(Path(profile.output_root).glob("pip-embedded-*"))
    with pytest.raises(ValueError):
        session._collect_outputs(
            record,
            _ChildResult("n", "r", None, (("escape", 1, "sha256:" + "0" * 64),)),
            destination,
        )
    os.close(source_fd)
    os.close(destination_fd)


def test_real_child_transport_argv_env_pgid_and_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from astrid.core.generation.backends import vibecomfy as backend

    script = r"""import hashlib,json,os,time
from pathlib import Path
request=json.loads(Path(__import__("sys").argv[1]).read_text()); a=__import__("sys").argv
ready={"schema":"astrid.vibecomfy.ready.v1","nonce":request["nonce"],"request_digest":request["request_digest"],"profile_digest":request["profile_digest"],"config_digest":request["config_digest"],"launch_digest":request["launch_digest"],"ok":True,"interpreter":{"executable":__import__("sys").executable,"prefix":os.environ["VIRTUAL_ENV"],"version":"3.11.11"},"package":request["package_facts"],"resolver":request["resolver_facts"]}; Path(a[2]).write_text(json.dumps(ready,separators=(",",":")))
os.set_blocking(int(a[3]), False)
while True:
 try:
  if os.read(int(a[3]), 4096): break
 except BlockingIOError: time.sleep(.01)
out=Path(request["config"]["extra"]["output_directory"]); out.mkdir(parents=True,exist_ok=True); p=out/"child.bin"; p.write_bytes(b"child"); payload={"schema":"astrid.vibecomfy.result.v1","nonce":request["nonce"],"request_digest":request["request_digest"],"profile_digest":request["profile_digest"],"config_digest":request["config_digest"],"status":"succeeded","run_id":"child-run","prompt_id":None,"outputs":[{"relative_path":"child.bin","size_bytes":5,"sha256":"sha256:"+hashlib.sha256(b"child").hexdigest()}]}; Path(a[4]).write_text(json.dumps(payload,separators=(",",":")))"""
    monkeypatch.setattr(backend, "_PIP_EMBEDDED_SCRIPT", script)
    profile = make_profile(tmp_path)
    staging = Path(profile.scratch_root) / "transport"
    staging.mkdir()
    (staging / "paths.yaml").write_text("vibecomfy: {}\n", encoding="utf-8")
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
        ready["package"] == handle._measured_package_facts()
        and ready["resolver"]["roots"] == list(profile.installation_evidence["resolver_roots"])
    )
    handle.go()
    handle.wait_completed(2)
    assert handle.read_result().run_id == "child-run"
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
    source = Path(profile.scratch_root) / "source" / "engine-output"
    source.parent.mkdir()
    source.mkdir()
    output = source / "frame.bin"
    output.write_bytes(b"frame")
    outside = tmp_path / "outside"
    outside.mkdir()
    destination = Path(profile.output_root) / "alias"
    destination.symlink_to(outside, target_is_directory=True)
    source_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    destination_fd = os.open(Path(profile.output_root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    record = {
        "staging": source.parent,
        "source_dir_fd": source_fd,
        "source_identity": (os.fstat(source_fd).st_dev, os.fstat(source_fd).st_ino),
        "destination_fd": destination_fd,
    }
    result = _ChildResult("n", "r", None, (("frame.bin", 5, file_digest(output)),))
    with pytest.raises(ValueError):
        session._collect_outputs(record, result, destination)
    os.close(source_fd)
    os.close(destination_fd)
    assert "run_embedded_sync" in _PIP_EMBEDDED_SCRIPT
    assert "run_sync" not in _PIP_EMBEDDED_SCRIPT
    assert "pickle" not in _PIP_EMBEDDED_SCRIPT


def test_simultaneous_cancel_release_share_first_terminal_outcome(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    holder: list[Handle] = []

    def factory(_p: PipEmbeddedProfile, request: Any, staging: Path) -> Handle:
        handle = Handle(staging, block=True)
        handle.nonce = request["nonce"]
        holder.append(handle)
        return handle

    session = PipEmbeddedSession(profile, execution_factory=factory)
    errors: list[BaseException] = []

    def run_once() -> None:
        try:
            session.run(workflow(), task_identity="racing", out_dir=Path(profile.output_root))
        except BaseException as exc:
            errors.append(exc)

    run_thread = threading.Thread(target=run_once)
    run_thread.start()
    while not holder or not holder[0].started.wait(timeout=0.02):
        pass
    active_nonce = session.active_invocation()["nonce"]
    results: list[dict[str, Any]] = []
    controls = [
        threading.Thread(target=lambda: results.append(session.cancel(task_identity="racing", invocation_nonce=active_nonce))),
        threading.Thread(target=lambda: results.append(session.release(task_identity="racing", invocation_nonce=active_nonce))),
    ]
    for thread in controls:
        thread.start()
    for thread in controls:
        thread.join(timeout=3)
    run_thread.join(timeout=3)
    assert len(results) == 2
    assert {item["status"] for item in results} == {results[0]["status"]}
    assert holder[0].calls.count("terminate") == 1
    assert errors and "cancelled" in str(errors[0])


def test_executable_replacement_after_profile_construction_fails_before_factory(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    executable = Path(profile.python_executable)
    with executable.open("ab") as stream:
        stream.write(b"drift")
    called = []

    def factory(_p: PipEmbeddedProfile, _r: Any, _s: Path) -> Handle:
        called.append(True)
        raise AssertionError("factory must not run after executable drift")

    with pytest.raises(_PipEmbeddedError, match="interpreter_bytes"):
        PipEmbeddedSession(profile, execution_factory=factory).run(
            workflow(), out_dir=Path(profile.output_root)
        )
    assert not called


def test_unbound_and_mismatched_hc03_hashes_fail_closed(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    raw = kwargs(profile)
    raw["hc03_trust"] = None
    with pytest.raises(_PipEmbeddedError, match="hc03_unbound"):
        PipEmbeddedProfile.from_hc03(**raw)
    raw = kwargs(profile)
    raw["hc03_handoff_hash"] = "sha256:" + "a" * 64
    with pytest.raises(_PipEmbeddedError, match="hc03_trust_hash"):
        PipEmbeddedProfile.from_hc03(**raw)


def test_outside_hardlink_and_traversal_sources_fail_closed(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    session = PipEmbeddedSession(profile)
    staging = Path(profile.scratch_root) / "owned"
    source = staging / "engine-output"
    source.mkdir(parents=True)
    original = source / "frame.bin"
    original.write_bytes(b"frame")
    hardlink = source / "hardlink.bin"
    hardlink.hardlink_to(original)
    source_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    destination = Path(profile.output_root)
    destination_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    record = {
        "staging": staging,
        "source_dir_fd": source_fd,
        "source_identity": (os.fstat(source_fd).st_dev, os.fstat(source_fd).st_ino),
        "destination_fd": destination_fd,
    }
    with pytest.raises(ValueError):
        session._collect_outputs(
            record,
            _ChildResult("n", "r", None, (("hardlink.bin", 5, file_digest(original)),)),
            destination,
        )
    with pytest.raises(ValueError):
        session._collect_outputs(
            record,
            _ChildResult("n", "r", None, (("../escape", 1, "sha256:" + "0" * 64),)),
            destination,
        )
    os.close(source_fd)
    os.close(destination_fd)


def test_ready_package_resolver_mismatch_blocks_go_and_unknown_census_poison(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)
    holder: list[Handle] = []

    class BadReady(Handle):
        def wait_ready(self, timeout: float) -> None:
            self.calls.append("ready")
            raise _PipEmbeddedError("readiness_mismatch", "resolver_facts", phase="ready")

    def factory(_p: PipEmbeddedProfile, request: Any, staging: Path) -> BadReady:
        handle = BadReady(staging)
        handle.nonce = request["nonce"]
        holder.append(handle)
        return handle

    session = PipEmbeddedSession(profile, execution_factory=factory)
    with pytest.raises(_PipEmbeddedError, match="resolver_facts"):
        session.run(workflow(), out_dir=Path(profile.output_root))
    assert "go" not in holder[0].calls

    def poisoned_factory(_p: PipEmbeddedProfile, request: Any, staging: Path) -> Handle:
        class UnknownCensus(Handle):
            def wait_completed(self, timeout: float, cancel_event: threading.Event | None = None) -> None:
                while cancel_event is None or not cancel_event.is_set():
                    time.sleep(0.005)
                raise RuntimeError("cancelled")

            def terminate(self, term: float, kill: float, reap: float) -> None:
                raise _PipEmbeddedError("containment_pending", "unknown-census", phase="containment")

        handle = UnknownCensus(staging)
        handle.nonce = request["nonce"]
        holder.append(handle)
        return handle

    session = PipEmbeddedSession(profile, execution_factory=poisoned_factory)
    errors: list[BaseException] = []
    thread = threading.Thread(
        target=lambda: _capture_error(
            errors, lambda: session.run(workflow(), out_dir=Path(profile.output_root))
        )
    )
    thread.start()
    while len(holder) < 2:
        time.sleep(0.005)
    active_nonce = session.active_invocation()["nonce"]
    outcome = session.cancel(task_identity="task-unspecified", invocation_nonce=active_nonce)
    thread.join(timeout=3)
    assert outcome["fence_pending"] is True
    assert session.poisoned
    assert errors


def _capture_error(target: list[BaseException], callback: Any) -> None:
    try:
        callback()
    except BaseException as exc:
        target.append(exc)
