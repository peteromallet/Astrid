from __future__ import annotations

import io
import hashlib
import json
import subprocess
import sys
import threading
import types
from unittest.mock import Mock

import pytest

from astrid.core.generation.backends.vibecomfy import (
    CheckoutServerAdapter,
    GenerationResult,
    VibeComfyEngine,
    _assert_process_incarnation_gone,
    _owner_session_command,
)

MODEL_DIGEST = "sha256:" + "a" * 64
MODEL_DIGEST_B = "sha256:" + "b" * 64

RUNTIME_A = "a1b2c3d4-e5f6-47ab-8c9d-0123456789ab"
RUNTIME_B = "b2c3d4e5-f6a7-48bc-9d01-123456789abc"


def test_runtime_identity_rejects_arbitrary_label() -> None:
    for value in ("runtime-a", "runtime_instance"):
        with pytest.raises(ValueError, match=r"runtime_instance_id.*UUID"):
            VibeComfyEngine._runtime_identity(value)
    with pytest.raises(ValueError, match="runtime_instance_id"):
        VibeComfyEngine._runtime_identity("probe:x")
    assert (
        VibeComfyEngine._runtime_identity("7f3a2d1e-5b4c-4a6d-9e12-0123456789ab")
        == "7f3a2d1e-5b4c-4a6d-9e12-0123456789ab"
    )


def test_owner_restart_command_uses_only_named_start_id(tmp_path) -> None:
    session_dir = tmp_path / "out" / "sessions" / "fixture"
    session_dir.mkdir(parents=True)
    (session_dir / "config.json").write_text(json.dumps({"port": 8188, "launch_flags": ["--use-ck-attention"]}), encoding="utf-8")
    command = _owner_session_command(session_dir, "start")
    assert command[command.index("session") + 1 : command.index("--runtime-root")] == [
        "start",
        "--id",
        "fixture",
    ]
    assert command.count("fixture") == 1
    assert "--launch-flag=--use-ck-attention" in command


def test_process_absence_probe_uncertainty_fails_closed(monkeypatch) -> None:
    from vibecomfy.runtime import session as runtime_session

    monkeypatch.setattr("astrid.core.generation.backends.vibecomfy.os.kill", lambda pid, sig: None)
    monkeypatch.setattr(runtime_session, "_process_start_identity", lambda pid: None)
    with pytest.raises(RuntimeError, match="cannot identify"):
        _assert_process_incarnation_gone(12345, "old-incarnation")


def test_owner_restart_timeout_uses_saved_readiness_budget(tmp_path, monkeypatch) -> None:
    from astrid.core.generation.backends import vibecomfy

    session_dir = tmp_path / "out" / "sessions" / "fixture"
    session_dir.mkdir(parents=True)
    (session_dir / "config.json").write_text(
        json.dumps({"port": 8188, "ready_timeout_sec": 900}), encoding="utf-8"
    )
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._host_session = {
        "session_dir": str(session_dir), "pid": 101, "comfy_pid": 102,
        "process_birth_id": "daemon-old", "comfy_process_birth_id": "comfy-old",
        "source_revision": "source", "source_content_digest": "sha256:" + "a" * 64,
        "config_digest": "sha256:" + "b" * 64,
    }
    monkeypatch.setattr(vibecomfy, "_verify_owned_vibe_session", lambda *args: None)
    monkeypatch.setattr(vibecomfy, "_assert_process_incarnation_gone", lambda *args: None)
    monkeypatch.setattr(vibecomfy, "_owner_session_command", lambda *args, **kwargs: ["owner"])
    calls = Mock(side_effect=[
        subprocess.CompletedProcess(["owner"], 0),
        subprocess.TimeoutExpired(["owner"], 930),
    ])
    monkeypatch.setattr(vibecomfy.subprocess, "run", calls)
    with pytest.raises(RuntimeError, match="retained for reconciliation"):
        adapter._restart_owned_session()
    assert calls.call_args_list[1].kwargs["timeout"] == 930.0


def test_owner_restart_refuses_attached_session_before_control(tmp_path, monkeypatch) -> None:
    from astrid.core.generation.backends import vibecomfy

    session_dir = tmp_path / "out" / "sessions" / "fixture"
    session_dir.mkdir(parents=True)
    (session_dir / "config.json").write_text(json.dumps({"port": 8188}), encoding="utf-8")
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._host_session = {
        "session_dir": str(session_dir), "pid": 101, "comfy_pid": 102,
        "process_birth_id": "daemon-old", "comfy_process_birth_id": "comfy-old",
        "source_revision": "source", "source_content_digest": "sha256:" + "a" * 64,
        "config_digest": "sha256:" + "b" * 64,
    }
    monkeypatch.setattr(vibecomfy, "_verify_owned_vibe_session", Mock(side_effect=ValueError("attached")))
    run = Mock()
    monkeypatch.setattr(vibecomfy.subprocess, "run", run)
    with pytest.raises(ValueError, match="attached"):
        adapter._restart_owned_session()
    run.assert_not_called()


def test_production_owner_bridge_refreshes_profile_and_registry(tmp_path, monkeypatch) -> None:
    from astrid.core.execution import generic_host
    from astrid.core.generation.backends import vibecomfy

    session_dir = tmp_path / "out" / "sessions" / "fixture"
    session_dir.mkdir(parents=True)
    config = {"port": 8188, "ready_timeout_sec": 2, "launch_flags": ["--use-ck-attention"]}
    config_bytes = json.dumps(config, sort_keys=True).encode("utf-8")
    (session_dir / "config.json").write_bytes(config_bytes)
    source_digest = "sha256:" + "c" * 64
    (session_dir / "source_revision").write_text("source-a", encoding="utf-8")
    (session_dir / "source_content_digest").write_text(source_digest, encoding="utf-8")
    profile = {
        "schema_version": "hc03-worker-readiness.v1",
        "status": "ready",
        "vibecomfy_session": {
            "session_dir": str(session_dir), "pid": 101, "comfy_pid": 102,
            "launch_token": "old-token", "process_birth_id": "daemon-old",
            "comfy_process_birth_id": "comfy-old", "server_url": "http://127.0.0.1:8188",
            "source_revision": "source-a", "source_content_digest": source_digest,
            "config_digest": "sha256:" + hashlib.sha256(config_bytes).hexdigest(),
        },
    }
    profile_path = tmp_path / "readiness.json"
    profile_path.write_text(json.dumps(profile, sort_keys=True), encoding="utf-8")
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv(
        "ASTRID_HOST_READINESS_PROFILE_HASH",
        "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest(),
    )
    start_script = (
        "from pathlib import Path; import json; "
        f"p=Path({str(session_dir)!r}); "
        "(p/'pid').write_text('201'); (p/'comfy_pid').write_text('202'); "
        "(p/'comfy_process_start_identity').write_text('comfy-new'); "
        "(p/'url').write_text('http://127.0.0.1:8188'); "
        "(p/'launch.json').write_text(json.dumps({'pid':201,'url':'http://127.0.0.1:8188','launch_token':'new-token','process_start_identity':'daemon-new','comfy_pid':202,'comfy_process_start_identity':'comfy-new'})); "
        f"(p/'config.json').write_bytes({config_bytes!r})"
    )
    stop_script = "raise SystemExit(0)"
    monkeypatch.setattr(
        vibecomfy,
        "_owner_session_command",
        lambda _path, action, **kwargs: [sys.executable, "-c", start_script if action == "start" else stop_script],
    )
    monkeypatch.setattr(vibecomfy, "_verify_owned_vibe_session", lambda *args: None)
    monkeypatch.setattr(vibecomfy, "_assert_process_incarnation_gone", lambda *args: None)
    adapter = CheckoutServerAdapter("http://127.0.0.1:8188")
    adapter._host_session = {
        **profile["vibecomfy_session"], "model_bytes_digest": MODEL_DIGEST,
    }
    adapter._host_profile = profile
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]

    evidence = adapter._restart_owned_session()
    assert evidence["released"] is True
    assert evidence["pid"] == 201
    refreshed = generic_host._read_readiness_profile_document()
    assert refreshed is not None
    assert refreshed["vibecomfy_session"]["pid"] == 201
    assert refreshed["vibecomfy_session"]["comfy_pid"] == 202
    assert refreshed["vibecomfy_session"]["launch_token"] == "new-token"


def _published_adapter(monkeypatch) -> CheckoutServerAdapter:
    _native_http(monkeypatch)
    _runtime(monkeypatch, GenerationResult(seed_used=1, model_actual="image/z_image"))
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)
    return adapter


def test_warm_session_probe_failure_fences_published_warmth(monkeypatch) -> None:
    adapter = _published_adapter(monkeypatch)
    engine = adapter._engine
    adapter._probe_system_stats = Mock(side_effect=RuntimeError("probe down"))  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="probe down"):
        adapter.warm_session(
            "model-a",
            "warm-a",
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest=MODEL_DIGEST,
        )

    assert engine.warm is False
    assert engine.poisoned or engine.fence_pending

    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    result = adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    assert result["warm_reused"] is False


def test_adapter_warm_session_reuses_published_warmth_and_recovers_cold(
    monkeypatch,
) -> None:
    calls = _native_http(monkeypatch)
    _runtime(monkeypatch, GenerationResult(seed_used=1, model_actual="image/z_image"))
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._probe_system_stats = Mock(  # type: ignore[method-assign]
        side_effect=[None, None, RuntimeError("probe down"), None]
    )

    first = adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)
    second = adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )

    assert first["warm_reused"] is False
    assert second["warm_reused"] is True
    assert second["lifecycle"] == "warm"
    assert calls == []

    with pytest.raises(RuntimeError, match="probe down"):
        adapter.warm_session(
            "model-a",
            "warm-a",
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest=MODEL_DIGEST,
        )
    assert adapter.poisoned is True
    assert adapter.fence_pending is True
    assert adapter._engine.warm is False
    assert adapter._engine.fingerprint is None
    assert adapter._engine.warmth_identity is None
    assert adapter._engine.model_bytes_digest is None
    assert adapter.runtime_instance_id is None

    recovery = adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    assert recovery["warm_reused"] is False
    assert recovery["lifecycle"] == "cold"
    assert [path for _method, path, _body in calls] == [
        "/interrupt",
        "/queue",
        "/api/free",
    ]


def test_adapter_cancel_probe_failure_poison_clears_published_warmth(monkeypatch) -> None:
    adapter = _published_adapter(monkeypatch)
    adapter._probe_system_stats = Mock(side_effect=RuntimeError("probe failed"))  # type: ignore[method-assign]

    result = adapter.cancel()

    assert result["ok"] is False
    assert adapter.poisoned is True
    assert adapter.fence_pending is True
    assert adapter._engine.warm is False
    with pytest.raises(RuntimeError, match="poisoned or fence-pending"):
        adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)


def test_adapter_release_probe_failure_poison_clears_published_warmth(monkeypatch) -> None:
    adapter = _published_adapter(monkeypatch)
    adapter._probe_system_stats = Mock(side_effect=RuntimeError("probe failed"))  # type: ignore[method-assign]

    result = adapter.release()

    assert result["ok"] is False
    assert adapter.poisoned is True
    assert adapter.fence_pending is True
    assert adapter._engine.warm is False
    with pytest.raises(RuntimeError, match="poisoned or fence-pending"):
        adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)


def test_warmth_hint_is_permission_not_hot_proof_and_release_invalidates_it(monkeypatch) -> None:
    _native_http(monkeypatch)
    engine = VibeComfyEngine("http://gpu.example.test")
    engine.adopt_warmth(
        fingerprint="fingerprint-a",
        warmth_identity="warmth-a",
        model_bytes_digest=MODEL_DIGEST,
        runtime_instance_id=RUNTIME_A,
    )

    assert engine.warm is False
    retained = engine.prepare_session(
        "fingerprint-a",
        "warmth-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    assert retained["warm_reused"] is False
    assert retained["retention_permitted"] is True
    assert retained["warm_observed"] is False

    released = engine.release(reason="intervening eviction")
    assert released["ok"] is True
    cold = engine.prepare_session(
        "fingerprint-a",
        "warmth-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    assert cold["lifecycle"] == "cold"
    assert cold["retention_permitted"] is False


def test_managed_release_requires_explicit_backend_completion(monkeypatch) -> None:
    _native_http(monkeypatch)
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._host_session = {"managed": True}
    adapter._revalidate_host_session = Mock(return_value=None)  # type: ignore[method-assign]
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]

    result = adapter.release(reason="replacement")

    assert result["ok"] is False
    assert "completion observation" in result["error"]
    assert adapter.poisoned is True


def test_managed_release_accepts_only_explicit_model_unload_observation(monkeypatch) -> None:
    _native_http(monkeypatch)
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._host_session = {"managed": True}
    adapter._revalidate_host_session = Mock(return_value=None)  # type: ignore[method-assign]
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    adapter._engine._post = Mock(  # type: ignore[method-assign]
        side_effect=[{}, {"status": "success", "models_unloaded": True}]
    )

    result = adapter.release(reason="replacement")

    assert result["ok"] is True
    assert result["released"] is True


def test_managed_cleanup_sends_no_control_calls_after_ownership_failure(monkeypatch) -> None:
    calls = _native_http(monkeypatch)
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._host_session = {"managed": True}
    adapter._revalidate_host_session = Mock(  # type: ignore[method-assign]
        side_effect=RuntimeError("listener ownership changed")
    )
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]

    result = adapter.release(reason="replacement")

    assert result["ok"] is False
    assert calls == []
    assert adapter.poisoned is True


def test_warm_session_digest_change_cannot_reuse_warmth(monkeypatch) -> None:
    adapter = _published_adapter(monkeypatch)

    second = adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST_B,
    )

    assert second["lifecycle"] == "cold"
    assert second["warm_reused"] is False
    assert second["model_bytes_digest"] == MODEL_DIGEST_B
    assert adapter._engine.warm is False
    assert adapter._engine.model_bytes_digest == MODEL_DIGEST_B
    assert adapter._engine._prepared_model_bytes_digest == MODEL_DIGEST_B
    adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)
    assert adapter._engine.model_bytes_digest == MODEL_DIGEST_B


class _Response(io.BytesIO):
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def _native_http(monkeypatch, *, fail_paths: set[str] | None = None):
    calls: list[tuple[str, str, dict[str, object]]] = []
    failures = fail_paths or set()

    def open_remote(request, *, timeout: float) -> _Response:
        del timeout
        body = json.loads(request.data.decode("utf-8")) if request.data else {}
        path = request.full_url.removeprefix("http://gpu.example.test")
        calls.append((request.method, path, body))
        if path in failures:
            raise OSError(f"forced failure: {path}")
        return _Response(b"{}")

    monkeypatch.setattr(
        "astrid.core.generation.backends.vibecomfy._open_checkout_http",
        open_remote,
    )
    return calls


def _runtime(monkeypatch, result: GenerationResult) -> Mock:
    run_sync = Mock(return_value=result)
    runtime = types.ModuleType("vibecomfy.runtime.run")
    runtime.run_sync = run_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vibecomfy.runtime.run", runtime)
    monkeypatch.setitem(sys.modules, "vibecomfy", types.ModuleType("vibecomfy"))
    return run_sync


def test_native_cancel_uses_pinned_api_free_and_allows_next_warm_session(monkeypatch) -> None:
    calls = _native_http(monkeypatch)
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )

    result = adapter.cancel({"reason": "user stop"})

    assert result == {
        "ok": True,
        "status": "cancelled",
        "contained": True,
        "cancelled": True,
        "released": False,
        "results": {"interrupt": {}, "queue_clear": {}, "free": {}},
    }
    assert [(method, path, body) for method, path, body in calls] == [
        ("POST", "/interrupt", {}),
        ("POST", "/queue", {"clear": True}),
        ("POST", "/api/free", {"free_memory": True, "unload_models": True}),
    ]
    assert adapter.poisoned is False
    assert adapter.fence_pending is False
    assert adapter.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )["lifecycle"] == "cold"


def test_failed_cancel_poison_blocks_run_and_cold_prepare_proves_reset(monkeypatch) -> None:
    failures = {"/interrupt"}
    calls = _native_http(monkeypatch, fail_paths=failures)
    run_sync = _runtime(monkeypatch, GenerationResult(seed_used=11, model_actual="image/z_image"))
    engine = VibeComfyEngine("http://gpu.example.test")
    engine.prepare_session(
        "model-a", runtime_instance_id=RUNTIME_A, model_bytes_digest=MODEL_DIGEST
    )

    result = engine.cancel()

    assert result["ok"] is False
    assert result["status"] == "requires_fence"
    assert engine.poisoned is True
    assert engine.fence_pending is True
    with pytest.raises(RuntimeError, match="poisoned or fence-pending"):
        engine.prepare_session(
            "model-a", runtime_instance_id=RUNTIME_A, model_bytes_digest=MODEL_DIGEST
        )
    with pytest.raises(RuntimeError, match="poisoned or fence-pending"):
        engine.run(object(), runtime_instance_id=RUNTIME_A)

    # /api/free succeeded during the failed sequence, but cannot clear poison
    # without the previously failed interrupt and queue-clear steps.
    assert calls[-1][1] == "/api/free"
    assert engine.poisoned is True
    failures.clear()
    cold = engine.prepare_session(
        "model-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
        cold=True,
    )
    generated = engine.run(object(), runtime_instance_id=RUNTIME_A)

    assert cold["lifecycle"] == "cold"
    assert generated.to_dict()["seed_used"] == 11
    assert run_sync.call_count == 1
    assert [path for _method, path, _body in calls[-3:]] == [
        "/interrupt",
        "/queue",
        "/api/free",
    ]
    assert engine.poisoned is False
    assert engine.fence_pending is False


def test_failed_release_poison_fences_prepare_until_cold_reset(monkeypatch) -> None:
    failures = {"/queue"}
    _native_http(monkeypatch, fail_paths=failures)
    engine = VibeComfyEngine("http://gpu.example.test")
    engine.prepare_session(
        "model-a", "warm-a", runtime_instance_id=RUNTIME_A, model_bytes_digest=MODEL_DIGEST
    )

    result = engine.release(reason="idle drain")

    assert result["ok"] is False
    assert engine.poisoned is True
    assert engine.fence_pending is True
    with pytest.raises(RuntimeError):
        engine.warm_session(
            "model-a",
            "warm-a",
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest=MODEL_DIGEST,
        )
    failures.clear()
    engine.warm_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
        cold=True,
    )
    assert engine.poisoned is False
    assert engine.fence_pending is False


def test_prepare_cannot_publish_warmth_during_inflight_cancel(monkeypatch) -> None:
    entered = threading.Event()
    unblock = threading.Event()
    calls: list[str] = []

    def blocking_post(path: str, payload: dict[str, object]):
        del payload
        calls.append(path)
        if path == "/interrupt":
            entered.set()
            assert unblock.wait(2)
        return {}

    engine = VibeComfyEngine("http://gpu.example.test")
    monkeypatch.setattr(engine, "_post", blocking_post)
    cancel_result: list[dict[str, object]] = []
    worker = threading.Thread(target=lambda: cancel_result.append(engine.cancel()))
    worker.start()
    assert entered.wait(2)
    with pytest.raises(RuntimeError, match="already in progress|poisoned or fence-pending"):
        engine.prepare_session(
            "model-a",
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest=MODEL_DIGEST,
        )
    unblock.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert cancel_result[0]["ok"] is True
    assert calls == ["/interrupt", "/queue", "/api/free"]


def test_run_preserves_vibecomfy_runresult_generation_result_contract(monkeypatch) -> None:
    result = GenerationResult(seed_used=12, model_actual="image/z_image")
    run_sync = _runtime(monkeypatch, result)
    engine = VibeComfyEngine("http://gpu.example.test")
    engine.prepare_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )

    cold_result = engine.run(object(), runtime_instance_id=RUNTIME_A)
    warm = engine.prepare_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    warm_result = engine.run(object(), runtime_instance_id=RUNTIME_A)

    assert warm["warm_reused"] is True
    assert cold_result.to_dict() == warm_result.to_dict()
    assert run_sync.call_count == 2
    assert run_sync.call_args.kwargs == {"server_url": "http://gpu.example.test"}


def test_completed_run_after_cancel_is_rejected_as_stale(monkeypatch) -> None:
    entered = threading.Event()
    unblock = threading.Event()
    result = GenerationResult(seed_used=12, model_actual="image/z_image")

    def run_sync(_workflow, *, server_url):
        assert server_url == "http://gpu.example.test"
        entered.set()
        assert unblock.wait(2)
        return result

    runtime = types.ModuleType("vibecomfy.runtime.run")
    runtime.run_sync = run_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vibecomfy.runtime.run", runtime)
    monkeypatch.setitem(sys.modules, "vibecomfy", types.ModuleType("vibecomfy"))
    _native_http(monkeypatch)
    engine = VibeComfyEngine("http://gpu.example.test")
    engine.prepare_session(
        "model-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    errors: list[BaseException] = []
    worker = threading.Thread(
        target=lambda: _capture_error(
            errors,
            lambda: engine.run(object(), runtime_instance_id=RUNTIME_A),
        )
    )
    worker.start()
    assert entered.wait(2)
    cancelled = engine.cancel()
    assert cancelled["ok"] is True
    unblock.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "lifecycle fence" in str(errors[0])


def _capture_error(errors: list[BaseException], callback) -> None:
    try:
        callback()
    except BaseException as exc:  # noqa: BLE001 - test captures stale completion.
        errors.append(exc)


def test_post_release_subsequent_run_is_cold_and_executes(monkeypatch) -> None:
    first = GenerationResult(seed_used=1, model_actual="image/z_image")
    second = GenerationResult(seed_used=2, model_actual="image/z_image")
    run_sync = Mock(side_effect=[first, second])
    runtime = types.ModuleType("vibecomfy.runtime.run")
    runtime.run_sync = run_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vibecomfy.runtime.run", runtime)
    monkeypatch.setitem(sys.modules, "vibecomfy", types.ModuleType("vibecomfy"))
    _native_http(monkeypatch)
    engine = VibeComfyEngine("http://gpu.example.test")

    engine.prepare_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    assert engine.run(object(), runtime_instance_id=RUNTIME_A) is first
    released = engine.release(reason="idle drain")
    reopened = engine.prepare_session(
        "model-a",
        "warm-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    assert engine.run(object(), runtime_instance_id=RUNTIME_A) is second

    assert released["released"] is True
    assert reopened["lifecycle"] == "cold"
    assert run_sync.call_count == 2


def test_model_byte_digest_isolation_for_same_model_id() -> None:
    kwargs = {
        "model_fingerprint": "z-image:image/z_image",
        "environment_fingerprint": "env-a",
        "server_url": "http://gpu.example.test",
        "runtime_instance_id": RUNTIME_A,
    }
    first = CheckoutServerAdapter.session_fingerprint(
        **kwargs, model_bytes_digest="sha256:" + "1" * 64
    )
    second = CheckoutServerAdapter.session_fingerprint(
        **kwargs, model_bytes_digest="sha256:" + "2" * 64
    )
    assert first != second


def test_restarted_runtime_isolation_for_same_fingerprint(monkeypatch) -> None:
    calls = _native_http(monkeypatch)
    _runtime(monkeypatch, GenerationResult(seed_used=1, model_actual="image/z_image"))
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._probe_system_stats = Mock(side_effect=[None, None])  # type: ignore[method-assign]

    first = adapter.warm_session(
        "same-fingerprint",
        "same-warmth",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)
    second = adapter.warm_session(
        "same-fingerprint",
        "same-warmth",
        runtime_instance_id=RUNTIME_B,
        model_bytes_digest=MODEL_DIGEST,
    )

    assert first["lifecycle"] == "cold"
    assert second["lifecycle"] == "cold"
    assert second["warm_reused"] is False
    assert [path for _method, path, _body in calls] == [
        "/interrupt",
        "/queue",
        "/api/free",
    ]


def test_warm_session_requires_model_digest_and_canonical_runtime_id(monkeypatch) -> None:
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="model_bytes_digest"):
        adapter.warm_session("model-a", runtime_instance_id=RUNTIME_A)
    with pytest.raises(ValueError, match="canonical health/bootstrap"):
        adapter.warm_session(
            "model-a",
            runtime_instance_id="probe:" + "a" * 64,
            model_bytes_digest=MODEL_DIGEST,
        )


def test_lone_free_does_not_clear_failed_containment_poison(monkeypatch) -> None:
    failures = {"/interrupt"}
    calls = _native_http(monkeypatch, fail_paths=failures)
    engine = VibeComfyEngine("http://gpu.example.test")
    engine.prepare_session(
        "model-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )

    result = engine.cancel()
    assert result["ok"] is False
    assert engine.poisoned is True
    engine._post("/api/free", {})  # A lone free is not complete containment.
    assert engine.poisoned is True
    assert engine.fence_pending is True

    failures.clear()
    engine.prepare_session(
        "model-a",
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
        cold=True,
    )
    assert [path for _method, path, _body in calls[-3:]] == [
        "/interrupt",
        "/queue",
        "/api/free",
    ]
    assert engine.poisoned is False
    assert engine.fence_pending is False
