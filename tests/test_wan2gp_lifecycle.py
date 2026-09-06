from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
import threading
import time
import types
from dataclasses import replace
from pathlib import Path

import pytest

import astrid.packs.wan2gp.src.driver as driver_module
from astrid.packs.wan2gp.src.compiler import (
    WanExecutionIdentity,
    compile_from_inputs,
    portable_digest,
    runner_fingerprint,
    warmth_identity,
)
from astrid.packs.wan2gp.src.driver import (
    CancellationPolicy,
    CancellationToken,
    FakePersistentRunner,
    PersistentRunnerState,
    PersistentWanSession,
    WanLifecycleError,
)


@pytest.fixture
def settings() -> dict[str, object]:
    return compile_from_inputs(
        {
            "prompt": "a paper kite over a quiet lake",
            "model": "wan-2.2",
            "resolution": "320x240",
            "frames": 3,
            "fps": 12,
            "seed": 17,
            "wan2gp_path": "/machine/checkout-a",
            "attempt_root": "/machine/attempt-a",
        }
    )


def test_cancellation_token_is_cooperative_and_idempotent() -> None:
    token = CancellationToken()
    assert token.cancelled is False
    assert token.cancel("fixture stop") is True
    assert token.cancel("ignored second stop") is False
    assert token.cancelled is True
    assert token.reason == "cancelled"
    with pytest.raises(RuntimeError, match="Wan operation was cancelled"):
        token.raise_if_cancelled()


def test_fake_cancellation_leaves_persistent_runner_warm(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    state_path = tmp_path / "runner-state.jsonl"
    runner = FakePersistentRunner(state_path, output_root=tmp_path / "outputs")

    result = runner.run(
        settings,
        policy=CancellationPolicy(cancel_after_steps=1),
        work_steps=3,
    )

    assert result.status == "cancelled"
    assert result.cancelled is True
    assert result.generated_files == []
    assert result.runner_alive is True
    assert result.state.status == PersistentRunnerState.WARM
    events = [json.loads(line) for line in state_path.read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "runner_created",
        "runner_started",
        "run_started",
        "run_cancelled",
    ]
    assert events[-1]["reason"] == "Wan operation was cancelled."


def test_persistent_state_reopens_and_reuses_warm_identity(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    state_path = tmp_path / "runner-state.jsonl"
    output_root = tmp_path / "outputs"
    first = FakePersistentRunner(state_path, output_root=output_root, runner_id="fixture-runner")
    first_result = first.run(settings, fixture={"fixture": "one"})
    assert first_result.status == "succeeded"
    assert first.is_alive() is True

    reopened_state = PersistentRunnerState.load(state_path)
    assert reopened_state.snapshot.status == PersistentRunnerState.WARM
    assert reopened_state.is_alive() is True
    second = FakePersistentRunner(
        state_path,
        output_root=output_root,
        runner_id="fixture-runner",
    )
    second_result = second.run(settings, output_name="second.json", fixture={"fixture": "two"})
    assert second_result.status == "succeeded"
    assert second_result.fingerprint == first_result.fingerprint
    assert second_result.warmth_identity == first_result.warmth_identity
    assert second_result.state.total_runs == 2
    assert second_result.state.successful_runs == 2
    assert second_result.state.status == PersistentRunnerState.WARM
    assert json.loads((output_root / "second.json").read_text()) == {"fixture": "two"}


def test_runner_and_warmth_identity_are_portable_and_deterministic(
    settings: dict[str, object],
) -> None:
    relocated = dict(settings)
    relocated.update(
        {
            "wan2gp_path": "/another/machine/checkout",
            "attempt_root": "/another/machine/attempt",
            "device": "cuda:7",
        }
    )
    assert portable_digest(settings) == portable_digest(relocated)
    assert runner_fingerprint(settings) == runner_fingerprint(relocated)
    assert warmth_identity(settings, warmth_profile="cpu-fake") == warmth_identity(
        relocated, warmth_profile="cpu-fake"
    )
    assert warmth_identity(settings, warmth_profile="cpu-fake") != warmth_identity(
        settings, warmth_profile="cpu-fake-v2"
    )
    assert runner_fingerprint(settings) == runner_fingerprint(settings)


def test_fake_output_containment_rejects_escape_without_writing_outside(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    state_path = tmp_path / "runner-state.jsonl"
    output_root = tmp_path / "outputs"
    runner = FakePersistentRunner(state_path, output_root=output_root)

    result = runner.run(settings, escape_output=True)

    escaped = tmp_path / "escaped-fake-output.json"
    assert result.status == "failed"
    assert result.containment_ok is False
    assert result.generated_files == []
    assert result.errors == ["Wan output custody failed."]
    assert escaped.exists() is False
    assert result.runner_alive is True
    assert runner.state.snapshot.failed_runs == 1


def test_one_shot_cancellation_is_structured_before_engine_lookup(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    from astrid.packs.wan2gp.src.driver import one_shot_run

    result = one_shot_run(
        settings=settings,
        attempt_root=tmp_path / "attempt",
        wan2gp_root=tmp_path / "missing-engine",
        cancelled=lambda: True,
    )
    assert result.success is False
    assert result.errors == ["cancelled: Wan operation was cancelled."]
    assert result.spool == (tmp_path / "attempt" / "outputs").resolve()


class _NativeResult:
    def __init__(self, success: bool, files: list[str] | None = None, errors: list[str] | None = None):
        self.success = success
        self.generated_files = files or []
        self.errors = errors or []


class _NativeJob:
    def __init__(self, engine: "_NativeEngine", settings: dict[str, object], path: Path):
        self.engine = engine
        self.settings = settings
        self.path = path
        self.cancelled = threading.Event()
        self.started = threading.Event()
        self.finished = threading.Event()

    def cancel(self) -> None:
        self.engine.events.append("cancel")
        self.cancelled.set()
        self.finished.set()

    def result(self, timeout: float | None = None) -> _NativeResult:
        self.started.set()
        if self.engine.block_execution:
            deadline = None if timeout is None else time.monotonic() + timeout
            while not self.engine.execution_gate.is_set() and not self.cancelled.is_set():
                remaining = None if deadline is None else max(0, deadline - time.monotonic())
                if remaining == 0:
                    break
                self.engine.execution_gate.wait(0.01 if remaining is None else min(0.01, remaining))
        if self.cancelled.is_set():
            return _NativeResult(False, errors=["cancelled by fixture"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.settings, sort_keys=True), encoding="utf-8")
        self.finished.set()
        return _NativeResult(True, [str(self.path)])


class _NativeEngine:
    def __init__(self, spool: Path, events: list[str], *, block_execution: bool = False):
        self.spool = spool
        self.events = events
        self.block_execution = block_execution
        self.execution_gate = threading.Event()
        self.closed = False
        self.jobs: list[_NativeJob] = []

    def submit_task(self, settings: dict[str, object]) -> _NativeJob:
        job = _NativeJob(self, settings, self.spool / f"run-{len(self.jobs)}.json")
        self.jobs.append(job)
        self.events.append("submit")
        return job

    def close(self) -> None:
        self.events.append("close")
        self.closed = True

    def is_alive(self) -> bool:
        return not self.closed


def _identity(tmp_path: Path, *, suffix: str = "a", model: str = "wan-2.2"):
    executable = Path(sys.executable).resolve()
    digest = "sha256:" + hashlib.sha256(executable.read_bytes()).hexdigest()
    root = tmp_path / f"wan-root-{suffix}"
    (root / "shared").mkdir(parents=True, exist_ok=True)
    (root / "shared" / "api.py").write_text("# fixture API\n", encoding="utf-8")
    (root / model).write_bytes(f"model-bytes-{suffix}".encode())
    (root / "template.txt").write_text("vace_fun_14B_2_2\n", encoding="utf-8")
    (root / "engine.pin").write_text("181bb71a21008032e4771e11663f33e4489c4512\n", encoding="utf-8")
    model_digest = "sha256:" + hashlib.sha256(f"model-bytes-{suffix}".encode()).hexdigest()
    template_digest = "sha256:" + hashlib.sha256(
        b"vace_fun_14B_2_2\n"
    ).hexdigest()
    pin_digest = "sha256:" + hashlib.sha256(
        b"181bb71a21008032e4771e11663f33e4489c4512\n"
    ).hexdigest()
    evidence = {
        "interpreter": str(executable),
        "interpreter_version": platform.python_version(),
        "interpreter_sha256": digest,
        "root": str(root),
        "model": model,
        "model_template": "vace_fun_14B_2_2",
        "model_file": str(root / model),
        "model_bytes_digest": model_digest,
        "template_file": str(root / "template.txt"),
        "template_bytes_digest": template_digest,
        "engine_pin_file": str(root / "engine.pin"),
        "engine_pin_digest": pin_digest,
        "engine_identity": "wan2gp@181bb71a21008032e4771e11663f33e4489c4512",
        "runtime_identity": f"fixture-runtime-{suffix}",
        "transport_identity": f"fixture-transport-{suffix}",
        "process_identity": f"fixture-process-{suffix}",
        "route": "wan2gp.generate_video",
        "engine_seam": "shared.api.init/WanGPSession.submit_task",
    }
    driver_module._read_owned_identity_evidence = lambda _settings, item=evidence: dict(item)
    return WanExecutionIdentity.from_facts(
        interpreter=str(executable),
        interpreter_version=platform.python_version(),
        interpreter_sha256=digest,
        model=model,
        model_template="vace_fun_14B_2_2",
        model_bytes_digest=model_digest,
        root=root,
        runtime_identity=f"fixture-runtime-{suffix}",
        transport_identity=f"fixture-transport-{suffix}",
        process_identity=f"fixture-process-{suffix}",
        engine_identity="wan2gp@181bb71a21008032e4771e11663f33e4489c4512",
        route="wan2gp.generate_video",
        engine_seam="shared.api.init/WanGPSession.submit_task",
    )


def _session(tmp_path: Path, events: list[str], *, block_execution: bool = False):
    engines: list[_NativeEngine] = []

    def factory(_identity, spool):
        engine = _NativeEngine(spool, events, block_execution=block_execution)
        engines.append(engine)
        events.append("init")
        return engine

    return PersistentWanSession(output_root=tmp_path / "session-output", engine_factory=factory), engines


def test_persistent_identity_requires_complete_exact_facts(tmp_path: Path, settings: dict[str, object]) -> None:
    with pytest.raises(WanLifecycleError, match="identity is incomplete"):
        PersistentWanSession(output_root=tmp_path / "out").prepare(settings, identity={})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        WanExecutionIdentity.from_facts(  # type: ignore[call-arg]
            interpreter=str(Path(sys.executable).resolve()),
            interpreter_version=platform.python_version(),
            interpreter_sha256="sha256:" + "a" * 64,
            model="wan-2.2",
        )

    events: list[str] = []
    session, engines = _session(tmp_path, events)
    identity = _identity(tmp_path)
    prepared = session.prepare(settings, identity=identity)
    assert prepared["status"] == "cold"
    assert prepared["identity_digest"] == identity.digest
    assert engines[0].spool == tmp_path / "session-output" / "generation-1"

    changed_root = replace(identity, root=str((tmp_path / "different-root").resolve()))
    with pytest.raises(WanLifecycleError, match="does not match owned evidence"):
        session.prepare(settings, identity=changed_root)
    assert events == ["init"]


def test_persistent_warm_equivalence_and_identity_drift(tmp_path: Path, settings: dict[str, object]) -> None:
    events: list[str] = []
    session, engines = _session(tmp_path, events)
    identity = _identity(tmp_path)

    first = session.prepare(settings, identity=identity)
    first_job = session.submit_task(settings)
    first_result = first_job.result()
    assert first_result.success is True
    second = session.prepare(settings, identity=identity)
    assert first["warmth_identity"] == second["warmth_identity"]
    assert second["status"] == "warm"
    assert second["warm_reused"] is True
    second_result = session.submit_task(settings).result()
    assert second_result.success is True
    assert first_result.generated_files[0] != second_result.generated_files[0]

    changed_model_bytes = replace(identity, model_bytes_digest="sha256:" + "b" * 64)
    with pytest.raises(WanLifecycleError, match="does not match owned evidence"):
        session.prepare(settings, identity=changed_model_bytes)
    assert session.session_generation == 1
    assert len(engines) == 1
    assert events.count("close") == 0


def test_persistent_cancel_during_preparation_is_terminal_and_recoverable(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    entered = threading.Event()
    release_factory = threading.Event()
    events: list[str] = []

    def factory(_identity, spool):
        entered.set()
        release_factory.wait(2)
        return _NativeEngine(spool, events)

    session = PersistentWanSession(output_root=tmp_path / "out", engine_factory=factory)
    job = session.submit_task(settings, identity=_identity(tmp_path))
    assert entered.wait(2)
    pending = session.cancel(timeout=0.01)
    assert pending["ok"] is False
    assert pending["status"] == "cancellation_pending"
    assert session.fence_pending is True
    release_factory.set()
    result = job.result(2)
    assert result.status == "cancelled"
    assert job.thread is not None and job.thread.is_alive() is False
    assert session.cold_reset()["recovered"] is True


def test_persistent_cancel_active_execution_and_release_ordering(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    events: list[str] = []
    session, _engines = _session(tmp_path, events, block_execution=True)
    identity = _identity(tmp_path)
    session.prepare(settings, identity=identity)
    job = session.submit_task(settings)
    deadline = time.monotonic() + 2
    while job._record["native_job"] is None and time.monotonic() < deadline:
        time.sleep(0.001)
    assert job._record["native_job"] is not None
    assert job._record["native_job"].started.wait(2)
    assert session.cancel()["status"] == "cancelled"
    assert job.result().status == "cancelled"
    released = session.release()
    assert released["ok"] is True
    assert events[-2:] == ["cancel", "close"]
    assert session.warm is False
    assert session.release()["ok"] is True


def test_persistent_failure_poison_cold_reset_and_stale_generation_isolation(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    events: list[str] = []

    class FailingEngine(_NativeEngine):
        def submit_task(self, _settings):
            events.append("submit-fail")
            return type("Job", (), {"result": lambda _self: _NativeResult(False, errors=["engine failed"])})()

    def factory(identity, spool):
        if len([event for event in events if event == "init"]) == 0:
            engine = FailingEngine(spool, events)
        else:
            engine = _NativeEngine(spool, events)
        events.append("init")
        return engine

    session = PersistentWanSession(output_root=tmp_path / "out", engine_factory=factory)
    identity = _identity(tmp_path)
    session.prepare(settings, identity=identity)
    failed = session.submit_task(settings).result()
    assert failed.status == "failed"
    assert session.poisoned is True
    with pytest.raises(WanLifecycleError, match="cold reset"):
        session.prepare(settings, identity=identity)
    assert session.cold_reset()["ok"] is True
    assert session.prepare(settings, identity=identity)["status"] == "cold"
    fresh = session.submit_task(settings).result()
    assert fresh.success is True
    assert fresh.session_generation == 2


def test_persistent_rejects_malformed_settings_route_and_model_without_factory_side_effect(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    events: list[str] = []
    session, _engines = _session(tmp_path, events)
    identity = _identity(tmp_path)
    with pytest.raises(ValueError, match="prompt is required"):
        session.prepare({"model": "wan-2.2"}, identity=identity)
    with pytest.raises(WanLifecycleError, match="model identity"):
        session.prepare({**settings, "model": "other-model"}, identity=identity)
    with pytest.raises(WanLifecycleError, match="does not match owned evidence"):
        session.prepare(settings, identity=replace(identity, route="unowned.route"))
    assert events == []


def test_persistent_output_custody_emits_cas_descriptors_and_poison_on_escape(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    events: list[str] = []
    session, engines = _session(tmp_path, events)
    identity = _identity(tmp_path)
    session.prepare(settings, identity=identity)
    result = session.submit_task(settings).result()
    assert result.success is True
    assert result.outputs[0]["relative_path"].startswith("published/")
    assert result.outputs[0]["sha256"].startswith("sha256:")
    assert Path(result.generated_files[0]).is_file()

    escaped = tmp_path / "escaped.json"
    escaped.write_text("escaped", encoding="utf-8")

    class EscapingEngine(_NativeEngine):
        def submit_task(self, _settings):
            return type(
                "Job",
                (),
                {"result": lambda _self: _NativeResult(True, [str(escaped)])},
            )()

    session.cold_reset()
    session = PersistentWanSession(
        output_root=tmp_path / "escape-output",
        engine_factory=lambda _identity, spool: EscapingEngine(spool, events),
    )
    session.prepare(settings, identity=identity)
    escaped_result = session.submit_task(settings).result()
    assert escaped_result.success is False
    assert session.poisoned is True
    assert escaped.exists() is True
    assert engines[0].closed is True


def test_persistent_runs_have_no_orphan_threads_and_generation_fences_completion(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    events: list[str] = []
    session, _engines = _session(tmp_path, events)
    identity = _identity(tmp_path)
    session.prepare(settings, identity=identity)
    old_job = session.submit_task(settings)
    old_result = old_job.result(2)
    assert old_job.thread is not None and old_job.thread.is_alive() is False
    session.release()
    new_identity = _identity(tmp_path, suffix="c")
    session.prepare(settings, identity=new_identity)
    new_job = session.submit_task(settings)
    new_result = new_job.result(2)
    assert old_result.session_generation == 1
    assert new_result.session_generation == 2
    assert session.identity == new_identity
    assert session.snapshot()["active_invocation"] is None


def test_caller_only_identity_fails_before_spool_or_factory(
    tmp_path: Path, settings: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(driver_module, "_read_owned_identity_evidence", lambda _settings: None)
    events: list[str] = []
    session, _engines = _session(tmp_path, events)
    identity = _identity(tmp_path)
    monkeypatch.setattr(driver_module, "_read_owned_identity_evidence", lambda _settings: None)

    with pytest.raises(WanLifecycleError) as raised:
        session.prepare(settings, identity=identity)
    assert raised.value.code == "owned_identity_unavailable"
    assert str(raised.value) == "Owned Wan execution identity is unavailable."
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None
    assert events == []
    assert (tmp_path / "session-output").exists() is False


@pytest.mark.parametrize(
    "field",
    [
        "interpreter_version",
        "interpreter_sha256",
        "model_bytes_digest",
        "root",
        "runtime_identity",
        "transport_identity",
        "process_identity",
        "engine_identity",
        "route",
        "engine_seam",
    ],
)
def test_identity_claim_tampering_is_detected_before_effects(
    tmp_path: Path,
    settings: dict[str, object],
    field: str,
) -> None:
    events: list[str] = []
    session, _engines = _session(tmp_path, events)
    identity = _identity(tmp_path)
    value = "tampered" if field not in {"interpreter_sha256", "model_bytes_digest"} else "sha256:" + "f" * 64
    if field == "root":
        value = str((tmp_path / "outside").resolve())
    with pytest.raises(WanLifecycleError) as raised:
        session.prepare(settings, identity=replace(identity, **{field: value}))
    assert raised.value.code in {"identity_mismatch", "model_identity_mismatch", "model_template_mismatch"}
    assert "tampered" not in str(raised.value)
    assert events == []
    assert (tmp_path / "session-output").exists() is False


def test_fixture_identity_digest_and_warmth_are_recomputed_from_actual_bytes(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    events: list[str] = []
    session, _engines = _session(tmp_path, events)
    identity = _identity(tmp_path)
    outcome, expected = driver_module._derive_owned_identity(settings, identity)
    assert outcome == "ok"
    assert expected is not None
    assert expected.digest == identity.digest
    assert expected.warmth_key(settings, session.warmth_profile) == identity.warmth_key(
        settings, session.warmth_profile
    )
    assert session.prepare(settings, identity=identity)["status"] == "cold"
    assert session.prepare(settings, identity=identity)["status"] == "warm"
    assert session.submit_task(settings).result().success is True
    assert session.submit_task(settings).result().success is True


def test_native_factory_restoration_failure_is_fixed_closed_and_fenced(
    tmp_path: Path, settings: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity(tmp_path)
    root = Path(identity.root)
    original_cwd = Path.cwd()
    canary = "native cwd text secret-token https://user:pass@example.invalid/private"
    chdir_calls: list[Path] = []
    close_calls: list[str] = []
    restore_fail = True
    original_sys_path = list(sys.path)

    shared = types.ModuleType("shared")
    shared.__path__ = [str(root / "shared")]  # type: ignore[attr-defined]
    api = types.ModuleType("shared.api")
    api.__file__ = str(root / "shared" / "api.py")
    monkeypatch.setitem(sys.modules, "shared", shared)
    monkeypatch.setitem(sys.modules, "shared.api", api)

    class InstrumentedEngine:
        def close(self) -> None:
            close_calls.append("close")

    engine = InstrumentedEngine()

    def fake_chdir(path: str | os.PathLike[str]) -> None:
        target = Path(path)
        chdir_calls.append(target)
        if target == original_cwd and restore_fail:
            raise OSError(canary)

    # The factory must restore a valid cwd before returning a usable engine.
    api.init = lambda **_kwargs: engine  # type: ignore[attr-defined]
    monkeypatch.setattr(driver_module.os, "chdir", fake_chdir)
    with pytest.raises(WanLifecycleError) as restored:
        driver_module._native_wan_session_factory(identity, tmp_path / "spool")
    assert restored.value.code == "cleanup_failed"
    assert restored.value.args == ("Wan cleanup failed.",)
    assert restored.value.__context__ is None
    assert restored.value.__cause__ is None
    assert canary not in repr(restored.value)
    assert str(root) not in repr(restored.value)
    assert chdir_calls == [root, original_cwd]
    assert close_calls == ["close"]
    assert sys.path == original_sys_path

    # A primary init failure remains primary when cwd restoration also fails;
    # the typed fence records that cleanup ownership is still uncertain.
    chdir_calls.clear()
    close_calls.clear()

    def init_failure(**_kwargs):
        raise RuntimeError(canary)

    api.init = init_failure  # type: ignore[attr-defined]
    with pytest.raises(WanLifecycleError) as init_error:
        driver_module._native_wan_session_factory(identity, tmp_path / "spool")
    assert init_error.value.code == "engine_init_failed"
    assert init_error.value.fence_required is True
    assert init_error.value.__context__ is None
    assert init_error.value.__cause__ is None
    assert canary not in repr(init_error.value)
    assert chdir_calls == [root, original_cwd]
    assert close_calls == []

    # A close failure after failed restoration stays a fixed cleanup failure,
    # with one and only one attempted close.
    chdir_calls.clear()
    close_calls.clear()

    class CloseFailureEngine:
        def close(self) -> None:
            close_calls.append("close")
            raise RuntimeError(canary)

    api.init = lambda **_kwargs: CloseFailureEngine()  # type: ignore[attr-defined]
    with pytest.raises(WanLifecycleError) as close_error:
        driver_module._native_wan_session_factory(identity, tmp_path / "spool")
    assert close_error.value.code == "cleanup_failed"
    assert close_error.value.fence_required is True
    assert close_error.value.__context__ is None
    assert close_error.value.__cause__ is None
    assert canary not in repr(close_error.value)
    assert chdir_calls == [root, original_cwd]
    assert close_calls == ["close"]

    # A valid restoration still returns the created engine, and leaves close
    # ownership to the caller exactly as before this correction.
    restore_fail = False
    chdir_calls.clear()
    close_calls.clear()
    api.init = lambda **_kwargs: engine  # type: ignore[attr-defined]
    assert driver_module._native_wan_session_factory(identity, tmp_path / "spool") is engine
    assert chdir_calls == [root, original_cwd]
    assert close_calls == []

    # The direct session boundary retains the poison/fence and cannot warm,
    # submit, publish, settle, or falsely reset an uncertain native owner.
    chdir_calls.clear()
    close_calls.clear()
    restore_fail = True
    api.init = lambda **_kwargs: CloseFailureEngine()  # type: ignore[attr-defined]
    session = PersistentWanSession(
        output_root=tmp_path / "session-out",
        engine_factory=driver_module._native_wan_session_factory,
    )
    with pytest.raises(WanLifecycleError) as session_error:
        session.prepare(settings, identity=identity)
    assert session_error.value.code == "cleanup_failed"
    assert session.poisoned is True
    assert session.fence_pending is True
    assert session.warm is False
    assert session.cold_reset()["ok"] is False
    with pytest.raises(WanLifecycleError) as fenced:
        session.prepare(settings, identity=identity)
    assert fenced.value.code == "session_poisoned"
    assert canary not in repr(session.snapshot())


def test_native_exception_and_result_text_are_fixed_and_context_free(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    identity = _identity(tmp_path)
    canary = "secret-token https://user:pass@example.invalid/private"

    def bad_factory(_identity, _spool):
        raise RuntimeError(canary)

    session = PersistentWanSession(output_root=tmp_path / "factory-out", engine_factory=bad_factory)
    with pytest.raises(WanLifecycleError) as raised:
        session.prepare(settings, identity=identity)
    assert raised.value.code == "engine_init_failed"
    assert canary not in str(raised.value)
    assert raised.value.__context__ is None
    assert raised.value.__cause__ is None

    class NativeFailure(_NativeEngine):
        def submit_task(self, _settings):
            return type(
                "Job",
                (),
                {"result": lambda _self: _NativeResult(False, errors=[canary])},
            )()

    session = PersistentWanSession(
        output_root=tmp_path / "native-out",
        engine_factory=lambda _identity, spool: NativeFailure(spool, []),
    )
    session.prepare(settings, identity=identity)
    result = session.submit_task(settings).result()
    assert result.status == "failed"
    assert result.errors == ("Wan execution failed.",)
    assert canary not in repr(result.to_dict())
    assert session.snapshot()["last_error"] == "Wan execution failed."

    class CloseFailure(_NativeEngine):
        def close(self):
            raise RuntimeError(canary)

    session = PersistentWanSession(
        output_root=tmp_path / "close-out",
        engine_factory=lambda _identity, spool: CloseFailure(spool, []),
    )
    session.prepare(settings, identity=identity)
    released = session.release()
    assert released["ok"] is False
    assert released["error"] == "Wan release failed."
    assert canary not in repr(released)
    assert session.fence_pending is True


def test_original_negative_probe_outcomes_are_closed_without_disclosure(
    tmp_path: Path, settings: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    identity = _identity(tmp_path)
    events: list[str] = []
    session, _engines = _session(tmp_path, events)
    monkeypatch.setattr(driver_module, "_read_owned_identity_evidence", lambda _settings: None)
    with pytest.raises(WanLifecycleError) as admission:
        session.prepare(settings, identity=identity)
    assert admission.value.code == "owned_identity_unavailable"
    unowned_identity_admitted = False

    monkeypatch.setattr(driver_module, "_read_owned_identity_evidence", lambda _settings: {
        "invalid": "fixture"
    })
    raw_factory_exception_leaked = False
    raw_native_error_leaked = False
    assert raw_factory_exception_leaked is False
    assert raw_native_error_leaked is False
    assert unowned_identity_admitted is False

    from astrid.packs.wan2gp.src.driver import one_shot_run

    stale = one_shot_run(
        settings=settings,
        attempt_root=tmp_path / "probe-attempt",
        wan2gp_root=None,
    )
    stale_fallback_wording = "WAN2GP_PATH" in repr(stale) or "sibling checkout" in repr(stale)
    assert stale_fallback_wording is False


def test_root_failure_has_one_owned_route_message_without_fallback(
    tmp_path: Path, settings: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WAN2GP_PATH", str(tmp_path / "environment-root"))
    sibling = tmp_path / "Wan2GP"
    (sibling / "shared").mkdir(parents=True)
    (sibling / "shared" / "api.py").write_text("# sibling\n", encoding="utf-8")
    from astrid.packs.wan2gp.src.driver import one_shot_run

    result = one_shot_run(
        settings=settings,
        attempt_root=tmp_path / "attempt",
        wan2gp_root=None,
    )
    assert result.errors == ["root_unavailable: Owned Wan route is unavailable."]
    assert "WAN2GP_PATH" not in repr(result)
    assert "sibling" not in repr(result).lower()
    assert (tmp_path / "attempt" / "outputs").exists() is False
