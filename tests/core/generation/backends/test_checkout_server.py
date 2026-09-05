from __future__ import annotations

import hashlib
import io
import json
import sys
import threading
import types
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

import astrid.core.generation.backends.vibecomfy as backend_module
from astrid.core.generation.backends.vibecomfy import (
    COMFYUI_VERSION,
    VIBECOMFY_ENGINE_REVISION,
    CheckoutServerAdapter,
    _validate_checkout_server_url,
)
from astrid.core.model_catalog.schema import BackendSpec, ModelEntry, ModeSpec

RUNTIME_A = "c3d4e5f6-a7b8-49cd-8e01-23456789abcd"
PROFILE = {"profile": "checkout-fixture", "engine": "pinned"}
PROFILE_DIGEST = backend_module.VibeComfyEngine._profile_identity(PROFILE, "profile")


def _adapter(server_url: str, **kwargs: object) -> CheckoutServerAdapter:
    origin = _validate_checkout_server_url(server_url)
    binding = backend_module._CheckoutRuntimeBinding._fixture(
        origin=origin,
        runtime_instance_id=RUNTIME_A,
        checkout_root="/fixture/checkout",
        listener_port=backend_module._origin_port(origin),
        profile_digest=PROFILE_DIGEST,
    )
    return CheckoutServerAdapter(
        server_url,
        environment_fingerprint=PROFILE,
        _managed_binding=binding,
        **kwargs,
    )


def _warmth(adapter: CheckoutServerAdapter, fingerprint: str, model: str = "sha256:" + "a" * 64) -> str:
    binding = adapter._managed_binding
    assert binding is not None
    return adapter.warmth_identity(
        fingerprint=fingerprint,
        model_bytes_digest=model,
        environment_fingerprint=PROFILE,
        server_url=binding.origin,
        runtime_instance_id=binding.runtime_instance_id,
        declared_root=binding.checkout_root,
        declared_port=binding.listener_port,
    )
class _Workflow:
    def __init__(self) -> None:
        self.metadata: dict[str, object] = {"unbound_inputs": {}}
        self.inputs: dict[str, object] = {}

    def set_input(self, name: str, value: object) -> None:
        self.inputs[name] = value


class _Response(io.BytesIO):
    status = 200

    def __init__(self, body: bytes, *, payload: object | None = None) -> None:
        super().__init__(body)
        self._payload = payload
        self.headers = {"Content-Length": str(len(body))}

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def json(self) -> object:
        if self._payload is None:
            raise AssertionError("json() was not configured")
        return self._payload


def _entry(template_hash: str, template: str = "image/z_image") -> ModelEntry:
    return ModelEntry(
        id="z-image",
        modality="image",
        modes={
            "t2i": ModeSpec(
                supports=("prompt", "seed", "size"),
                requires=("prompt",),
                backends={
                    "local": BackendSpec(
                        template=template,
                        template_hash=template_hash,
                    )
                },
            )
        },
    )


def _fake_vibe_modules(
    workflow: _Workflow,
    result: object,
    *,
    record: object,
    discovery: object,
) -> dict[str, types.ModuleType]:
    root = types.ModuleType("vibecomfy")
    ready = types.ModuleType("vibecomfy.registry.ready")
    runtime = types.ModuleType("vibecomfy.runtime.run")
    ready.repo_ready_template_discovery = Mock(return_value=discovery)  # type: ignore[attr-defined]
    ready.resolve_ready_template = Mock(return_value=record)  # type: ignore[attr-defined]
    ready.workflow_from_ready = Mock(return_value=workflow)  # type: ignore[attr-defined]
    runtime.run_sync = Mock(return_value=result)  # type: ignore[attr-defined]
    return {
        "vibecomfy": root,
        "vibecomfy.registry": types.ModuleType("vibecomfy.registry"),
        "vibecomfy.registry.ready": ready,
        "vibecomfy.runtime": types.ModuleType("vibecomfy.runtime"),
        "vibecomfy.runtime.run": runtime,
    }


def _template_record(tmp_path: Path, *, template_id: str = "image/z_image", source_scope: str = "repo") -> tuple[object, str]:
    template_path = tmp_path / "ready_templates" / "image" / "z_image.py"
    template_path.parent.mkdir(parents=True)
    template_path.write_bytes(b"def build():\n    return object()\n")
    digest = hashlib.sha256(template_path.read_bytes()).hexdigest()
    return (
        SimpleNamespace(
            template_id=template_id,
            path=template_path,
            root=template_path.parents[2],
            source_scope=source_scope,
        ),
        digest,
    )


def _patch_remote_open(monkeypatch: pytest.MonkeyPatch, *, output: bytes = b"png") -> list[str]:
    calls: list[str] = []

    def open_remote(request: object, *, timeout: float) -> _Response:
        del timeout
        url = request.full_url  # type: ignore[attr-defined]
        calls.append(url)
        if url.endswith("/system_stats"):
            return _Response(
                b'{"system":{"comfyui_version":"0.26.0"}}',
                payload={"system": {"comfyui_version": COMFYUI_VERSION}},
            )
        if getattr(request, "method", "GET") == "POST":
            return _Response(b"{}")
        return _Response(output)

    monkeypatch.setattr(backend_module, "_open_checkout_http", open_remote)
    return calls


def test_repo_loader_requires_canonical_repo_record_and_verifies_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, digest = _template_record(tmp_path)
    workflow = _Workflow()
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "comfy_outputs": [
                    {"filename": "x.png", "subfolder": "renders", "type": "output"}
                ]
            }
        ),
        encoding="utf-8",
    )
    result = SimpleNamespace(metadata_path=metadata_path, outputs=["/must/not/read"])
    discovery = object()
    modules = _fake_vibe_modules(
        workflow, result, record=record, discovery=discovery
    )
    calls = _patch_remote_open(monkeypatch)
    with patch.dict(sys.modules, modules):
        adapter = _adapter("HTTPS://GPU.EXAMPLE.TEST:8888/")
        generated = adapter.generate(
            entry=_entry(f"sha256:{digest}"),
            mode="t2i",
            params={"prompt": "a cat", "seed": 7, "size": "512x384"},
            out_dir=tmp_path / "out",
            model_bytes_digest="sha256:" + "a" * 64,
            runtime_instance_id=RUNTIME_A,
        )
        assert generated.ok
    ready = modules["vibecomfy.registry.ready"]
    assert ready.resolve_ready_template.call_args.args == ("image/z_image", discovery)
    assert ready.workflow_from_ready.call_args.args == ("image/z_image",)
    assert ready.workflow_from_ready.call_args.kwargs["_discovery"] is discovery
    assert calls[0] == "https://gpu.example.test:8888/system_stats"
    assert calls[1] == "https://gpu.example.test:8888/system_stats"
    assert calls[2].endswith("/view?filename=x.png&subfolder=renders&type=output")


def test_repo_loader_rejects_wrong_hash_before_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, _digest = _template_record(tmp_path)
    modules = _fake_vibe_modules(
        _Workflow(),
        SimpleNamespace(metadata_path=tmp_path / "unused.json"),
        record=record,
        discovery=object(),
    )
    _patch_remote_open(monkeypatch)
    with patch.dict(sys.modules, modules):
        with pytest.raises(ValueError, match="sha256 pin"):
            _adapter("https://gpu.example.test").generate(
                entry=_entry("sha256:" + "0" * 64),
                mode="t2i",
                params={"prompt": "a cat"},
                out_dir=tmp_path / "out",
                model_bytes_digest="sha256:" + "a" * 64,
                runtime_instance_id=RUNTIME_A,
            )
    assert not modules["vibecomfy.registry.ready"].workflow_from_ready.called



@pytest.mark.parametrize("record_id", ["z_image", "../z_image", "image/../z_image"])
def test_repo_loader_rejects_non_category_record(
    tmp_path: Path, record_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, digest = _template_record(tmp_path, template_id=record_id)
    modules = _fake_vibe_modules(
        _Workflow(),
        SimpleNamespace(metadata_path=tmp_path / "unused.json"),
        record=record,
        discovery=object(),
    )
    _patch_remote_open(monkeypatch)
    with patch.dict(sys.modules, modules):
        with pytest.raises(ValueError, match="canonical repo template"):
            _adapter("https://gpu.example.test").generate(
                entry=_entry(f"sha256:{digest}"),
                mode="t2i",
                params={"prompt": "a cat"},
                out_dir=tmp_path / "out",
                model_bytes_digest="sha256:" + "a" * 64,
                runtime_instance_id=RUNTIME_A,
            )

def test_repo_loader_rejects_dynamic_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, digest = _template_record(tmp_path, source_scope="dynamic")
    modules = _fake_vibe_modules(
        _Workflow(),
        SimpleNamespace(metadata_path=tmp_path / "unused.json"),
        record=record,
        discovery=object(),
    )
    _patch_remote_open(monkeypatch)
    with patch.dict(sys.modules, modules):
        with pytest.raises(ValueError, match="canonical repo template"):
            _adapter("https://gpu.example.test").generate(
                entry=_entry(f"sha256:{digest}"),
                mode="t2i",
                params={"prompt": "a cat"},
                out_dir=tmp_path / "out",
                model_bytes_digest="sha256:" + "a" * 64,
                runtime_instance_id=RUNTIME_A,
            )


def test_remote_output_custody_downloads_metadata_descriptors_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record, digest = _template_record(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "comfy_outputs": {"9": {"images": [
                    {"filename": "remote.png", "subfolder": "", "type": "output"}
                ]}}}
        ),
        encoding="utf-8",
    )
    result = SimpleNamespace(metadata_path=metadata_path, outputs=[str(tmp_path / "local.png")])
    modules = _fake_vibe_modules(
        _Workflow(), result, record=record, discovery=object()
    )
    calls = _patch_remote_open(monkeypatch)
    from unittest.mock import patch

    with patch.dict(sys.modules, modules):
        generated = _adapter("https://GPU.EXAMPLE.TEST:8888/").generate(
            entry=_entry(f"sha256:{digest}"),
            mode="t2i",
            params={"prompt": "a cat"},
            out_dir=tmp_path / "out",
            model_bytes_digest="sha256:" + "a" * 64,
            runtime_instance_id=RUNTIME_A,
        )
    assert len(calls) == 3
    assert calls[0] == "https://gpu.example.test:8888/system_stats"
    assert calls[1] == "https://gpu.example.test:8888/system_stats"
    query = parse_qs(urlsplit(calls[2]).query, keep_blank_values=True)
    assert query == {"filename": ["remote.png"], "subfolder": [""], "type": ["output"]}
    assert generated.image_paths[0].read_bytes() == b"png"
    assert generated.image_paths[0].parent.name.startswith("checkout-batch-")
    assert not list((tmp_path / "out").glob(".checkout-download-*"))
    assert modules["vibecomfy.runtime.run"].run_sync.call_args.kwargs == {
        "server_url": "https://gpu.example.test:8888"
    }


@pytest.mark.parametrize(
    "descriptors",
    [
        [],
        [{"filename": "../escape.png", "subfolder": "", "type": "output"}],
        [{"filename": "ok.png", "subfolder": "../escape", "type": "output"}],
        [{"filename": "ok.png", "subfolder": "", "type": "input"}],
        [{"filename": "ok.png", "subfolder": "", "type": "output", "extra": "x"}],
    ],
)
def test_remote_output_custody_rejects_empty_or_malformed_descriptors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    descriptors: list[dict[str, str]],
) -> None:
    record, digest = _template_record(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps({"comfy_outputs": descriptors}), encoding="utf-8")
    result = SimpleNamespace(metadata_path=metadata_path)
    modules = _fake_vibe_modules(_Workflow(), result, record=record, discovery=object())
    _patch_remote_open(monkeypatch)
    from unittest.mock import patch

    with patch.dict(sys.modules, modules):
        with pytest.raises(ValueError):
            _adapter("https://gpu.example.test").generate(
                entry=_entry(f"sha256:{digest}"),
                mode="t2i",
                params={"prompt": "a cat"},
                out_dir=tmp_path / "out",
                model_bytes_digest="sha256:" + "a" * 64,
                runtime_instance_id=RUNTIME_A,
            )


@pytest.mark.parametrize(
    "value",
    [
        "https://user:pass@example.test",
        "https://example.test?token=secret",
        "https://example.test#fragment",
        "https://example.test/path",
        "https:// example.test",
        "https://example.test\\path",
        "https://example.test:notaport",
        "https://example.test:0",
        "https://example.test:65536",
        "https://example..test",
        "https://-example.test",
    ],
)
def test_checkout_server_url_rejects_unsafe_origins(value: str) -> None:
    with pytest.raises(ValueError):
        _validate_checkout_server_url(value)


def test_checkout_server_url_accepts_canonical_origin() -> None:
    assert _validate_checkout_server_url("HTTPS://GPU.EXAMPLE.TEST:8888/") == (
        "https://gpu.example.test:8888"
    )


def test_checkout_identity_binds_profile_root_and_declared_port(tmp_path: Path) -> None:
    root_a = tmp_path / "checkout-a"
    root_b = tmp_path / "checkout-b"
    kwargs = {
        "model_fingerprint": "z-image:image/z_image",
        "model_bytes_digest": "sha256:" + "a" * 64,
        "environment_fingerprint": {"profile": "checkout-a", "engine": "pinned"},
        "server_url": "http://gpu.example.test:8188",
        "runtime_instance_id": RUNTIME_A,
        "declared_port": 8188,
    }
    first = CheckoutServerAdapter.session_fingerprint(**kwargs, declared_root=root_a)
    second = CheckoutServerAdapter.session_fingerprint(**kwargs, declared_root=root_b)
    assert first != second

    adapter = CheckoutServerAdapter(
        "HTTP://GPU.EXAMPLE.TEST:8188/",
        environment_fingerprint={"profile": "checkout-a", "engine": "pinned"},
        declared_root=root_a,
        declared_port=8188,
    )
    assert adapter.declared_root == str(root_a.resolve())
    assert adapter.declared_port == 8188
    with pytest.raises(ValueError, match="declared_port"):
        CheckoutServerAdapter("http://gpu.example.test:8188", declared_port=8189)


def test_checkout_profile_rejects_secret_shaped_values() -> None:
    with pytest.raises(ValueError, match="secret-shaped"):
        CheckoutServerAdapter(
            "http://gpu.example.test", environment_fingerprint={"token": "must-not-enter"}
        )


def test_system_stats_probe_requires_exact_version_and_bounds_body(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _adapter("https://gpu.example.test")
    monkeypatch.setattr(
        backend_module,
        "_open_checkout_http",
        lambda request, *, timeout: _Response(
            b"x" * (64 * 1024 + 1),
            payload={"system": {"comfyui_version": COMFYUI_VERSION}},
        ),
    )
    with pytest.raises(ValueError, match="too large"):
        adapter._probe_system_stats()
    assert not adapter._system_stats_verified
    assert not any(
        path.is_file() and b"x" * 64 in path.read_bytes()
        for path in tmp_path.rglob("*")
    )

    monkeypatch.setattr(
        backend_module,
        "_open_checkout_http",
        lambda request, *, timeout: _Response(
            b'{"system":{"comfyui_version":"0.25.0"}}',
            payload={"system": {"comfyui_version": "0.25.0"}},
        ),
    )
    with pytest.raises(ValueError, match="0.26.0"):
        adapter._probe_system_stats()
    assert not adapter._system_stats_verified
    monkeypatch.setattr(
        backend_module,
        "_open_checkout_http",
        lambda request, *, timeout: _Response(
            b'{"system":{"comfyui_version":"0.26.0"}}',
            payload={"system": {"comfyui_version": COMFYUI_VERSION}},
        ),
    )
    adapter._probe_system_stats()
    assert adapter.runtime_instance_id is None


@pytest.mark.parametrize(
    "response_body",
    [b"not-json", b'{"system":{"comfyui_version":"0.26.0"},"system":{}}'],
)
def test_checkout_post_rejects_malformed_response(response_body: bytes, monkeypatch) -> None:
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    monkeypatch.setattr(
        backend_module,
        "_open_checkout_http",
        lambda request, *, timeout: _Response(response_body),
    )
    with pytest.raises(ValueError, match="malformed"):
        adapter._engine._post("/queue", {"clear": True})


def test_generate_requires_digest_and_canonical_runtime_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "vibecomfy", types.ModuleType("vibecomfy"))
    adapter = _adapter("https://gpu.example.test")
    entry = _entry("sha256:" + "a" * 64)
    with pytest.raises(ValueError, match="model_bytes_digest"):
        adapter.generate(
            entry=entry,
            mode="t2i",
            params={"prompt": "a cat"},
            out_dir=tmp_path / "out",
            runtime_instance_id=RUNTIME_A,
        )
    with pytest.raises(ValueError, match="runtime_instance_id"):
        adapter.generate(
            entry=entry,
            mode="t2i",
            params={"prompt": "a cat"},
            out_dir=tmp_path / "out",
            model_bytes_digest="sha256:" + "a" * 64,
        )


def test_generate_rejects_unscoped_fingerprint_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "vibecomfy", types.ModuleType("vibecomfy"))
    with pytest.raises(ValueError, match="canonical session fingerprint"):
        _adapter("https://gpu.example.test").generate(
            entry=_entry("sha256:" + "a" * 64),
            mode="t2i",
            params={"prompt": "a cat"},
            out_dir=tmp_path / "out",
            fingerprint="caller-override",
            model_bytes_digest="sha256:" + "a" * 64,
            runtime_instance_id=RUNTIME_A,
        )


def test_checkout_server_records_pinned_engine_contract() -> None:
    assert VIBECOMFY_ENGINE_REVISION == "dc8d962a8e330015bbb209080292fad248f1ceb3"
    assert COMFYUI_VERSION == "0.26.0"

def test_generate_failure_discards_prepared_warmth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    adapter = _adapter("https://gpu.example.test")
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    with patch.object(
        backend_module.VibeComfyBackend,
        "generate",
        side_effect=RuntimeError("template preflight failed"),
    ):
        with pytest.raises(RuntimeError, match="template preflight failed"):
            adapter.generate(
                entry=_entry("sha256:" + "a" * 64),
                mode="t2i",
                params={"prompt": "a cat"},
                out_dir=tmp_path / "out",
                model_bytes_digest="sha256:" + "a" * 64,
                runtime_instance_id=RUNTIME_A,
            )

    assert adapter._engine.warm is False
    assert adapter._engine.last_warm_reused is False
    second = adapter._engine.prepare_session(
        "same-fingerprint",
        "sha256:" + "c" * 64,
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest="sha256:" + "a" * 64,
    )
    assert second["lifecycle"] == "cold"
    assert second["warm_reused"] is False


def test_remote_output_failure_poisons_and_cold_reset_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record, digest = _template_record(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {"comfy_outputs": [{"filename": "x.png", "subfolder": "", "type": "output"}]}
        ),
        encoding="utf-8",
    )
    result = SimpleNamespace(metadata_path=metadata_path)
    modules = _fake_vibe_modules(_Workflow(), result, record=record, discovery=object())
    calls = _patch_remote_open(monkeypatch)
    adapter = _adapter("http://gpu.example.test")
    with patch.dict(sys.modules, modules), patch.object(
        backend_module.CheckoutServerAdapter,
        "_collect_outputs",
        side_effect=ValueError("malformed remote output"),
    ):
        with pytest.raises(ValueError, match="malformed remote output"):
            adapter.generate(
                entry=_entry(f"sha256:{digest}"),
                mode="t2i",
                params={"prompt": "a cat"},
                out_dir=tmp_path / "out",
                model_bytes_digest="sha256:" + "a" * 64,
                runtime_instance_id=RUNTIME_A,
            )
    assert adapter.poisoned is True
    assert adapter.fence_pending is True

    recovered = adapter.warm_session(
        "recovered",
        _warmth(adapter, "recovered"),
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest="sha256:" + "a" * 64,
    )
    assert recovered["warm_reused"] is False
    assert adapter.poisoned is False
    assert [url.removeprefix("http://gpu.example.test") for url in calls[-3:]] == [
        "/interrupt",
        "/queue",
        "/api/free",
    ]


def _prepared_adapter(monkeypatch: pytest.MonkeyPatch, *, fingerprint: str = "probe") -> CheckoutServerAdapter:
    adapter = _adapter("http://gpu.example.test")
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    adapter.warm_session(
        fingerprint,
        _warmth(adapter, fingerprint),
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest="sha256:" + "a" * 64,
    )
    return adapter


def _output_metadata(tmp_path: Path) -> SimpleNamespace:
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(
        json.dumps({"comfy_outputs": [{"filename": "x.png", "subfolder": "", "type": "output"}]}),
        encoding="utf-8",
    )
    return SimpleNamespace(metadata_path=metadata_path)


def test_correction_f01_omitted_warmth_identity_cannot_reuse_published_warmth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _prepared_adapter(monkeypatch)
    engine = adapter._engine
    engine._warm = True
    engine._fingerprint = engine._prepared_fingerprint
    engine._warmth_identity = engine._prepared_warmth_identity
    engine._model_bytes_digest = engine._prepared_model_bytes_digest
    engine._runtime_instance_id = engine._prepared_runtime_instance_id
    engine._warm_declared_root = engine._prepared_declared_root
    engine._warm_declared_port = engine._prepared_declared_port
    with pytest.raises(ValueError, match="checkout_warmth_identity_incomplete"):
        engine.prepare_session(
            "probe", None, runtime_instance_id=RUNTIME_A, model_bytes_digest="sha256:" + "a" * 64
        )
    assert engine.warm is True
    assert engine.last_warm_reused is False


def test_correction_f02_secret_control_response_is_typed_and_not_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    response = _Response(b'{"nested":{"api_token":"CONTROL_SECRET_SENTINEL"}}')
    monkeypatch.setattr(backend_module, "_open_checkout_http", lambda request, *, timeout: response)
    with pytest.raises(ValueError) as caught:
        adapter._engine._post("/queue", {"clear": True})
    assert getattr(caught.value, "code", None) == "checkout_response_secret_shaped"
    assert "CONTROL_SECRET_SENTINEL" not in str(caught.value)
    assert "CONTROL_SECRET_SENTINEL" not in repr(caught.value.args)


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ({}, b"x"),
        ({"Content-Length": "2"}, b"x"),
        ({"Content-Length": ["1", "1"]}, b"x"),
        ({"Content-Length": "1", "Transfer-Encoding": "chunked"}, b"x"),
        ({"Content-Length": "1", "Content-Range": "bytes 0-0/1"}, b"x"),
    ],
)
def test_correction_f03_view_requires_unambiguous_complete_framing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, object],
    body: bytes,
) -> None:
    adapter = _prepared_adapter(monkeypatch)
    result = _output_metadata(tmp_path)
    response = _Response(body)
    response.headers = headers
    monkeypatch.setattr(backend_module, "_open_checkout_http", lambda request, *, timeout: response)
    with pytest.raises(ValueError):
        adapter._collect_outputs(result, tmp_path / "out")
    assert not list((tmp_path / "out").glob("checkout-batch-*"))
    assert adapter.poisoned is True


def test_correction_f03_fragmented_exact_length_succeeds_and_deadline_expires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _prepared_adapter(monkeypatch)
    result = _output_metadata(tmp_path)

    class Fragmented(_Response):
        def read(self, size: int = -1) -> bytes:
            return super().read(min(size, 1))

    response = Fragmented(b"png")
    response.headers = {"Content-Length": "3"}
    monkeypatch.setattr(backend_module, "_open_checkout_http", lambda request, *, timeout: response)
    paths = adapter._collect_outputs(result, tmp_path / "out")
    assert paths[0].read_bytes() == b"png"
    assert paths[0].parent.name.startswith("checkout-batch-")

    slow = _Response(b"x")
    slow.headers = {"Content-Length": "1"}
    # The production reader's absolute deadline is exercised directly with a
    # transport that never returns before the deadline.
    with pytest.raises((TimeoutError, ValueError)):
        backend_module._read_framed_response(slow, limit=8, timeout=0.0)


def test_correction_f04_concurrent_publishers_have_one_atomic_winner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _prepared_adapter(monkeypatch)
    second = _prepared_adapter(monkeypatch)
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    metadata = _output_metadata(tmp_path)
    monkeypatch.setattr(
        backend_module,
        "_open_checkout_http",
        lambda request, *, timeout: _Response(b"png"),
    )
    barrier = threading.Barrier(2)
    native = backend_module._publish_directory_noreplace

    def gated(*args: object, **kwargs: object) -> None:
        barrier.wait(timeout=2)
        native(*args, **kwargs)

    monkeypatch.setattr(backend_module, "_publish_directory_noreplace", gated)
    outcomes: list[object] = []
    def publish(adapter: CheckoutServerAdapter) -> None:
        try:
            outcomes.append(adapter._collect_outputs(metadata, out_dir))
        except BaseException as exc:
            outcomes.append(exc)
    threads = [threading.Thread(target=publish, args=(first,)), threading.Thread(target=publish, args=(second,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)
    assert sum(isinstance(item, list) for item in outcomes) == 1, repr(outcomes)
    conflicts = [item for item in outcomes if isinstance(item, ValueError)]
    assert len(conflicts) == 1
    assert getattr(conflicts[0], "code", None) == "publication_conflict"
    batches = list(out_dir.glob("checkout-batch-*/x.png"))
    assert len(batches) == 1 and batches[0].read_bytes() == b"png"


def test_correction_f05_only_matching_independent_binding_is_admitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = CheckoutServerAdapter("http://gpu.example.test")
    adapter._probe_system_stats = Mock(return_value=None)  # type: ignore[method-assign]
    with pytest.raises(ValueError, match="checkout_runtime_binding_unproven"):
        adapter.warm_session(
            "probe",
            "sha256:" + "c" * 64,
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest="sha256:" + "a" * 64,
        )
    matching = _prepared_adapter(monkeypatch)
    assert matching._engine.prepared_runtime_instance_id == RUNTIME_A
    binding = matching._managed_binding
    assert binding is not None
    lie_root = "/caller/lie"
    lied_warmth = matching.warmth_identity(
        fingerprint="probe",
        model_bytes_digest="sha256:" + "a" * 64,
        environment_fingerprint=PROFILE,
        server_url=binding.origin,
        runtime_instance_id=binding.runtime_instance_id,
        declared_root=lie_root,
        declared_port=binding.listener_port,
    )
    with pytest.raises(ValueError, match="checkout_runtime_binding_mismatch"):
        matching.warm_session(
            "probe",
            lied_warmth,
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest="sha256:" + "a" * 64,
            declared_root=lie_root,
        )
