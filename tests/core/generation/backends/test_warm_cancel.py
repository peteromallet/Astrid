from __future__ import annotations

import io
import json
import sys
import threading
import time
import types
from dataclasses import replace
from unittest.mock import Mock

import pytest

import astrid.core.generation.backends.vibecomfy as backend_module
from astrid.core.generation.backends.vibecomfy import (
    CheckoutServerAdapter,
    GenerationResult,
    VibeComfyEngine,
)

MODEL_DIGEST = "sha256:" + "a" * 64
MODEL_DIGEST_B = "sha256:" + "b" * 64

RUNTIME_A = "a1b2c3d4-e5f6-47ab-8c9d-0123456789ab"
RUNTIME_B = "b2c3d4e5-f6a7-48bc-9d01-123456789abc"
MODEL_DIGEST_C = "sha256:" + "c" * 64
WARM_A = "sha256:" + "c" * 64
PROFILE = {"profile": "warm-fixture", "engine": "pinned"}
PROFILE_DIGEST = VibeComfyEngine._profile_identity(PROFILE, "profile")


def _adapter() -> CheckoutServerAdapter:
    binding = backend_module._CheckoutRuntimeBinding._fixture(
        origin="http://gpu.example.test",
        runtime_instance_id=RUNTIME_A,
        checkout_root="/fixture/checkout",
        listener_port=80,
        profile_digest=PROFILE_DIGEST,
        profile=PROFILE,
    )
    return CheckoutServerAdapter(
        "http://gpu.example.test",
        environment_fingerprint=PROFILE,
        _managed_binding=binding,
    )


def _warmth(adapter: CheckoutServerAdapter, fingerprint: str, model: str = MODEL_DIGEST) -> str:
    binding = adapter._managed_binding
    assert binding is not None
    session = adapter.session_fingerprint(
        model_fingerprint="z-image:image/z_image",
        model_bytes_digest=model,
        environment_fingerprint=PROFILE,
        server_url="http://gpu.example.test",
        runtime_instance_id=binding.runtime_instance_id,
        declared_root=binding.checkout_root,
        declared_port=80,
        managed_binding=binding,
    )
    return adapter.warmth_identity(
        fingerprint=session,
        model_bytes_digest=model,
        environment_fingerprint=PROFILE,
        server_url="http://gpu.example.test",
        runtime_instance_id=binding.runtime_instance_id,
        declared_root=binding.checkout_root,
        declared_port=80,
    )


def _capture_error(target: list[BaseException], callback) -> None:
    try:
        callback()
    except BaseException as exc:
        target.append(exc)


def _direct_prepare(
    engine: VibeComfyEngine,
    *,
    model: str = "model-a",
    model_digest: str = MODEL_DIGEST,
    cold: bool = False,
) -> dict[str, object]:
    binding = backend_module._CheckoutRuntimeBinding._fixture(
        origin="http://gpu.example.test",
        runtime_instance_id=RUNTIME_A,
        checkout_root="/fixture/checkout",
        listener_port=80,
        profile_digest=PROFILE_DIGEST,
        profile=PROFILE,
        model_id=model,
    )
    session = CheckoutServerAdapter.session_fingerprint(
        model_fingerprint=f"{model}:image/z_image",
        model_bytes_digest=model_digest,
        environment_fingerprint=PROFILE,
        server_url="http://gpu.example.test",
        runtime_instance_id=RUNTIME_A,
        declared_root=binding.checkout_root,
        declared_port=80,
        managed_binding=binding,
    )
    adapter = CheckoutServerAdapter(
        "http://gpu.example.test", environment_fingerprint=PROFILE, _managed_binding=binding
    )
    warmth = adapter.warmth_identity(
        fingerprint=session,
        model_bytes_digest=model_digest,
        environment_fingerprint=PROFILE,
        server_url=binding.origin,
        runtime_instance_id=RUNTIME_A,
        declared_root=binding.checkout_root,
        declared_port=80,
    )
    return engine.prepare_session(
        session,
        warmth,
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=model_digest,
        environment_fingerprint=PROFILE,
        managed_binding=binding,
        model_id=model,
        template_id="image/z_image",
        declared_root=binding.checkout_root,
        declared_port=80,
        cold=cold,
    )


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


def _published_adapter(monkeypatch) -> CheckoutServerAdapter:
    _native_http(monkeypatch)
    _runtime(monkeypatch, GenerationResult(seed_used=1, model_actual="image/z_image"))
    adapter = _adapter()
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    adapter.warm_session(
        "model-a",
        _warmth(adapter, "model-a"),
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
            _warmth(adapter, "model-a"),
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest=MODEL_DIGEST,
        )

    assert engine.warm is False
    assert engine.poisoned or engine.fence_pending

    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    result = adapter.warm_session(
        "model-a",
        _warmth(adapter, "model-a"),
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    assert result["warm_reused"] is False


def test_adapter_warm_session_reuses_published_warmth_and_recovers_cold(
    monkeypatch,
) -> None:
    calls = _native_http(monkeypatch)
    _runtime(monkeypatch, GenerationResult(seed_used=1, model_actual="image/z_image"))
    adapter = _adapter()
    adapter._probe_system_stats = Mock(  # type: ignore[method-assign]
        side_effect=[None, None, RuntimeError("probe down"), None]
    )

    first = adapter.warm_session(
        "model-a",
        _warmth(adapter, "model-a"),
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)
    second = adapter.warm_session(
        "model-a",
        _warmth(adapter, "model-a"),
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
            _warmth(adapter, "model-a"),
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
        _warmth(adapter, "model-a"),
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


def test_warm_session_digest_change_cannot_reuse_warmth(monkeypatch) -> None:
    adapter = _published_adapter(monkeypatch)
    adapter._managed_binding = backend_module._CheckoutRuntimeBinding._fixture(
        origin="http://gpu.example.test",
        runtime_instance_id=RUNTIME_A,
        checkout_root="/fixture/checkout",
        listener_port=80,
        profile_digest=PROFILE_DIGEST,
        profile=PROFILE,
        model_bytes_digest=MODEL_DIGEST_B,
    )

    with pytest.raises(ValueError, match="checkout_runtime_binding_mismatch"):
        adapter.warm_session(
            "model-a",
            _warmth(adapter, "model-a", MODEL_DIGEST_B),
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest=MODEL_DIGEST_B,
        )
    assert adapter._engine.poisoned or adapter._engine.fence_pending


class _Response(io.BytesIO):
    status = 200
    _deadline_capable = True

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
        response = _Response(b"{}")
        response.headers = {"Content-Length": "2"}
        return response

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
    adapter = _adapter()
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    adapter.warm_session(
        "model-a",
        _warmth(adapter, "model-a"),
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
        _warmth(adapter, "model-a"),
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )["lifecycle"] == "cold"


def test_running_cancel_waits_for_remote_run_to_quiesce(monkeypatch) -> None:
    entered = threading.Event()
    allow_run = threading.Event()
    run_sync = Mock(
        side_effect=lambda _workflow, **_kwargs: (
            entered.set(),
            allow_run.wait(timeout=2),
            GenerationResult(seed_used=1, model_actual="image/z_image"),
        )[-1]
    )
    runtime = types.ModuleType("vibecomfy.runtime.run")
    runtime.run_sync = run_sync  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "vibecomfy.runtime.run", runtime)
    monkeypatch.setitem(sys.modules, "vibecomfy", types.ModuleType("vibecomfy"))
    calls = _native_http(monkeypatch)
    engine = VibeComfyEngine("http://gpu.example.test")
    _direct_prepare(engine)

    errors: list[BaseException] = []
    run_thread = threading.Thread(
        target=lambda: _capture_error(errors, lambda: engine.run(object(), runtime_instance_id=RUNTIME_A))
    )
    run_thread.start()
    assert entered.wait(timeout=2)

    cancel_result: list[dict[str, object]] = []
    cancel_thread = threading.Thread(target=lambda: cancel_result.append(engine.cancel()))
    cancel_thread.start()
    time.sleep(0.05)
    assert cancel_thread.is_alive()
    allow_run.set()
    cancel_thread.join(timeout=2)
    run_thread.join(timeout=2)

    assert not errors
    assert cancel_result and cancel_result[0]["ok"] is True
    assert [path for _method, path, _body in calls] == [
        "/interrupt",
        "/queue",
        "/api/free",
    ]
    assert engine.poisoned is False
    assert engine.fence_pending is False


def test_failed_cancel_poison_blocks_run_and_cold_prepare_proves_reset(monkeypatch) -> None:
    failures = {"/interrupt"}
    calls = _native_http(monkeypatch, fail_paths=failures)
    run_sync = _runtime(monkeypatch, GenerationResult(seed_used=11, model_actual="image/z_image"))
    engine = VibeComfyEngine("http://gpu.example.test")
    _direct_prepare(engine)

    result = engine.cancel()

    assert result["ok"] is False
    assert result["status"] == "requires_fence"
    assert engine.poisoned is True
    assert engine.fence_pending is True
    with pytest.raises(RuntimeError, match="poisoned or fence-pending"):
        _direct_prepare(engine)
    with pytest.raises(RuntimeError, match="poisoned or fence-pending"):
        engine.run(object(), runtime_instance_id=RUNTIME_A)

    # /api/free succeeded during the failed sequence, but cannot clear poison
    # without the previously failed interrupt and queue-clear steps.
    assert calls[-1][1] == "/api/free"
    assert engine.poisoned is True
    failures.clear()
    cold = _direct_prepare(engine, cold=True)
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
    _direct_prepare(engine)

    result = engine.release(reason="idle drain")

    assert result["ok"] is False
    assert engine.poisoned is True
    assert engine.fence_pending is True
    with pytest.raises(RuntimeError):
        _direct_prepare(engine)
    failures.clear()
    _direct_prepare(engine, cold=True)
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
        _direct_prepare(engine)
    unblock.set()
    worker.join(timeout=2)
    assert not worker.is_alive()
    assert cancel_result[0]["ok"] is True
    assert calls == ["/interrupt", "/queue", "/api/free"]


def test_run_preserves_vibecomfy_runresult_generation_result_contract(monkeypatch) -> None:
    result = GenerationResult(seed_used=12, model_actual="image/z_image")
    run_sync = _runtime(monkeypatch, result)
    engine = VibeComfyEngine("http://gpu.example.test")
    _direct_prepare(engine)

    cold_result = engine.run(object(), runtime_instance_id=RUNTIME_A)
    warm = _direct_prepare(engine)
    warm_result = engine.run(object(), runtime_instance_id=RUNTIME_A)

    assert warm["warm_reused"] is True
    assert cold_result.to_dict() == warm_result.to_dict()
    assert run_sync.call_count == 2
    assert run_sync.call_args.kwargs == {
        "server_url": "http://gpu.example.test",
        "transport_generation": "fixture-transport-generation-1",
    }


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

    _direct_prepare(engine)
    assert engine.run(object(), runtime_instance_id=RUNTIME_A) is first
    released = engine.release(reason="idle drain")
    reopened = _direct_prepare(engine)
    assert engine.run(object(), runtime_instance_id=RUNTIME_A) is second

    assert released["released"] is True
    assert reopened["lifecycle"] == "cold"
    assert run_sync.call_count == 2


def test_model_byte_digest_isolation_for_same_model_id() -> None:
    binding = backend_module._CheckoutRuntimeBinding._fixture(
        origin="http://gpu.example.test", runtime_instance_id=RUNTIME_A,
        checkout_root="/fixture/checkout", listener_port=80,
        profile=PROFILE, profile_digest=PROFILE_DIGEST,
    )
    kwargs = {
        "model_fingerprint": "z-image:image/z_image",
        "environment_fingerprint": PROFILE,
        "server_url": "http://gpu.example.test",
        "runtime_instance_id": RUNTIME_A,
        "declared_root": binding.checkout_root,
        "declared_port": 80,
    }
    first = CheckoutServerAdapter.session_fingerprint(
        **kwargs,
        model_bytes_digest="sha256:" + "1" * 64,
        managed_binding=replace(binding, model_bytes_digest="sha256:" + "1" * 64),
    )
    second = CheckoutServerAdapter.session_fingerprint(
        **kwargs,
        model_bytes_digest="sha256:" + "2" * 64,
        managed_binding=replace(binding, model_bytes_digest="sha256:" + "2" * 64),
    )
    assert first != second


def test_restarted_runtime_isolation_for_same_fingerprint(monkeypatch) -> None:
    calls = _native_http(monkeypatch)
    _runtime(monkeypatch, GenerationResult(seed_used=1, model_actual="image/z_image"))
    adapter = _adapter()
    adapter._probe_system_stats = Mock(side_effect=[None, None])  # type: ignore[method-assign]

    first = adapter.warm_session(
        "same-fingerprint",
        _warmth(adapter, "same-fingerprint"),
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest=MODEL_DIGEST,
    )
    adapter._engine.run(object(), runtime_instance_id=RUNTIME_A)
    adapter._managed_binding = backend_module._CheckoutRuntimeBinding._fixture(
        origin="http://gpu.example.test",
        runtime_instance_id=RUNTIME_B,
        checkout_root="/fixture/checkout",
        listener_port=80,
        profile_digest=PROFILE_DIGEST,
        profile=PROFILE,
    )
    with pytest.raises(ValueError, match="checkout_runtime_binding_mismatch"):
        adapter.warm_session(
            "same-fingerprint",
            _warmth(adapter, "same-fingerprint"),
            runtime_instance_id=RUNTIME_B,
            model_bytes_digest=MODEL_DIGEST,
        )
    assert adapter.poisoned or adapter.fence_pending


def test_warm_session_requires_model_digest_and_canonical_runtime_id(monkeypatch) -> None:
    adapter = _adapter()
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="warmth_identity"):
        adapter.warm_session("model-a", runtime_instance_id=RUNTIME_A)
    with pytest.raises(ValueError, match="warmth_identity"):
        adapter.warm_session(
            "model-a",
            runtime_instance_id="probe:" + "a" * 64,
            model_bytes_digest=MODEL_DIGEST,
        )


def test_lone_free_does_not_clear_failed_containment_poison(monkeypatch) -> None:
    failures = {"/interrupt"}
    calls = _native_http(monkeypatch, fail_paths=failures)
    engine = VibeComfyEngine("http://gpu.example.test")
    _direct_prepare(engine)

    result = engine.cancel()
    assert result["ok"] is False
    assert engine.poisoned is True
    engine._post("/api/free", {})  # A lone free is not complete containment.
    assert engine.poisoned is True
    assert engine.fence_pending is True

    failures.clear()
    _direct_prepare(engine, cold=True)
    assert [path for _method, path, _body in calls[-3:]] == [
        "/interrupt",
        "/queue",
        "/api/free",
    ]
    assert engine.poisoned is False
    assert engine.fence_pending is False
