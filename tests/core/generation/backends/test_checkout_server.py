from __future__ import annotations

import hashlib
import io
import json
import socket
import sys
import threading
import time
import traceback
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
        profile=PROFILE,
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
    session = adapter.session_fingerprint(
        model_fingerprint="z-image:image/z_image",
        model_bytes_digest=model,
        environment_fingerprint=PROFILE,
        server_url=binding.origin,
        runtime_instance_id=binding.runtime_instance_id,
        declared_root=binding.checkout_root,
        declared_port=binding.listener_port,
        managed_binding=binding,
    )
    return adapter.warmth_identity(
        fingerprint=session,
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
    _deadline_capable = True

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
        "server_url": "https://gpu.example.test:8888",
        "transport_generation": "fixture-transport-generation-1",
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
    del tmp_path
    kwargs = {
        "model_fingerprint": "z-image:image/z_image",
        "model_bytes_digest": "sha256:" + "a" * 64,
        "environment_fingerprint": {"profile": "checkout-a", "engine": "pinned"},
        "server_url": "http://gpu.example.test:8188",
        "runtime_instance_id": RUNTIME_A,
        "declared_port": 8188,
    }
    binding_a = backend_module._CheckoutRuntimeBinding._fixture(
        origin=kwargs["server_url"], runtime_instance_id=RUNTIME_A,
        checkout_root="/fixture/checkout-a", listener_port=8188,
        profile=kwargs["environment_fingerprint"],
        profile_digest=backend_module.VibeComfyEngine._profile_identity(
            kwargs["environment_fingerprint"], "profile"
        ),
    )
    binding_b = replace(binding_a, checkout_root="/fixture/checkout-b")
    first = CheckoutServerAdapter.session_fingerprint(
        **kwargs, declared_root=binding_a.checkout_root, managed_binding=binding_a
    )
    second = CheckoutServerAdapter.session_fingerprint(
        **kwargs, declared_root=binding_b.checkout_root, managed_binding=binding_b
    )
    assert first != second

    adapter = CheckoutServerAdapter(
        "HTTP://GPU.EXAMPLE.TEST:8188/",
        environment_fingerprint={"profile": "checkout-a", "engine": "pinned"},
        declared_root="/fixture/checkout-a",
        declared_port=8188,
    )
    assert adapter.declared_root == str(Path("/fixture/checkout-a").resolve())
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
    assert adapter._engine.prepared_fingerprint is None


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
            engine._prepared_fingerprint or "sha256:" + "0" * 64,
            None,
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest="sha256:" + "a" * 64,
            environment_fingerprint=PROFILE,
            managed_binding=adapter._managed_binding,
            model_id="z-image",
            template_id="image/z_image",
            declared_root="/fixture/checkout",
            declared_port=80,
        )
    assert engine.warm is True
    assert engine.last_warm_reused is False


def test_correction_f01_invocation_identity_is_in_both_direct_digests_and_prepare_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding_one = backend_module._CheckoutRuntimeBinding._fixture(
        origin="http://gpu.example.test",
        runtime_instance_id=RUNTIME_A,
        checkout_root="/fixture/checkout",
        listener_port=80,
        profile_digest=PROFILE_DIGEST,
        profile=PROFILE,
        invocation_identity="invocation-one",
    )
    binding_two = replace(binding_one, invocation_identity="invocation-two")

    session_one = CheckoutServerAdapter.session_fingerprint(
        model_fingerprint="z-image:image/z_image",
        model_bytes_digest="sha256:" + "a" * 64,
        environment_fingerprint=PROFILE,
        server_url=binding_one.origin,
        runtime_instance_id=RUNTIME_A,
        declared_root=binding_one.checkout_root,
        declared_port=80,
        managed_binding=binding_one,
    )
    adapter_one = CheckoutServerAdapter(
        binding_one.origin, environment_fingerprint=PROFILE, _managed_binding=binding_one
    )
    warmth_one = adapter_one.warmth_identity(
        fingerprint=session_one,
        model_bytes_digest="sha256:" + "a" * 64,
        environment_fingerprint=PROFILE,
        server_url=binding_one.origin,
        runtime_instance_id=RUNTIME_A,
        declared_root=binding_one.checkout_root,
        declared_port=80,
    )
    session_two = CheckoutServerAdapter.session_fingerprint(
        model_fingerprint="z-image:image/z_image",
        model_bytes_digest="sha256:" + "a" * 64,
        environment_fingerprint=PROFILE,
        server_url=binding_two.origin,
        runtime_instance_id=RUNTIME_A,
        declared_root=binding_two.checkout_root,
        declared_port=80,
        managed_binding=binding_two,
    )
    adapter_two = CheckoutServerAdapter(
        binding_two.origin, environment_fingerprint=PROFILE, _managed_binding=binding_two
    )
    warmth_two = adapter_two.warmth_identity(
        fingerprint=session_two,
        model_bytes_digest="sha256:" + "a" * 64,
        environment_fingerprint=PROFILE,
        server_url=binding_two.origin,
        runtime_instance_id=RUNTIME_A,
        declared_root=binding_two.checkout_root,
        declared_port=80,
    )
    assert session_one != session_two
    assert warmth_one != warmth_two

    engine = backend_module.VibeComfyEngine(binding_one.origin)
    engine.prepare_session(
        session_one,
        warmth_one,
        runtime_instance_id=RUNTIME_A,
        model_bytes_digest="sha256:" + "a" * 64,
        environment_fingerprint=PROFILE,
        managed_binding=binding_one,
        model_id="z-image",
        template_id="image/z_image",
        declared_root=binding_one.checkout_root,
        declared_port=80,
    )
    with pytest.raises(ValueError, match="checkout_session_identity_mismatch"):
        engine.prepare_session(
            session_one,
            warmth_one,
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest="sha256:" + "a" * 64,
            environment_fingerprint=PROFILE,
            managed_binding=binding_two,
            model_id="z-image",
            template_id="image/z_image",
            declared_root=binding_two.checkout_root,
            declared_port=80,
        )
    assert engine.prepared_fingerprint == session_one


@pytest.mark.parametrize("failure", ["scan", "parser"])
def test_correction_f02_decoder_failures_are_fresh_fixed_errors(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    canary = "SECRET_CANARY_SHOULD_NOT_ESCAPE"
    if failure == "scan":
        monkeypatch.setattr(
            backend_module,
            "_scan_json_depth",
            Mock(side_effect=MemoryError(canary)),
        )
    else:
        monkeypatch.setattr(
            backend_module.json,
            "loads",
            Mock(side_effect=RecursionError(canary)),
        )
    with pytest.raises(ValueError) as caught:
        backend_module._checkout_json(b"{}")
    error = caught.value
    assert getattr(error, "code", None) == "checkout_response_malformed"
    assert error.__context__ is None
    assert error.__cause__ is None
    assert canary not in repr(error.args)
    assert canary not in traceback.format_exc()


def test_correction_f03_hostname_resolution_fails_closed_before_unbounded_resolver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolver_called = False

    def slow_getaddrinfo(*_args: object, **_kwargs: object) -> object:
        nonlocal resolver_called
        resolver_called = True
        time.sleep(0.2)
        return []

    monkeypatch.setattr(socket, "getaddrinfo", slow_getaddrinfo)
    request = backend_module.urllib_request.Request("http://slow.example.test/view")
    deadline = time.monotonic_ns() + 20_000_000
    started = time.monotonic()
    with pytest.raises(ValueError) as caught:
        backend_module._open_checkout_http_bounded(request, deadline)
    assert getattr(caught.value, "code", None) == "checkout_deadline_transport_unavailable"
    assert resolver_called is False
    assert time.monotonic() - started < 0.1


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("runtime_epoch", 2),
        ("coordinator_epoch", 2),
        ("engine_birth_id", "replacement-birth"),
        ("engine_lifetime_id", "replacement-lifetime"),
        ("listener_owner", "replacement-owner"),
        ("listener_address", "127.0.0.2"),
        ("transport_generation", "replacement-transport"),
        ("invocation_identity", "replacement-invocation"),
        ("checkout_root", "/replacement/checkout"),
    ],
)
def test_correction_f01_every_latched_binding_field_is_exact(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    adapter = _prepared_adapter(monkeypatch)
    engine = adapter._engine
    binding = adapter._managed_binding
    assert binding is not None
    replacement = replace(binding, **{field: value})
    with pytest.raises(ValueError, match="checkout_(runtime_binding|session_identity)_"):
        engine.prepare_session(
            engine._prepared_fingerprint,
            engine._prepared_warmth_identity,
            runtime_instance_id=engine._prepared_runtime_instance_id,
            model_bytes_digest=engine._prepared_model_bytes_digest,
            environment_fingerprint=PROFILE,
            managed_binding=replacement,
            model_id=replacement.model_id,
            template_id=replacement.template_id,
            declared_root=engine._prepared_declared_root,
            declared_port=engine._prepared_declared_port,
        )


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


@pytest.mark.parametrize("body", [b'{"status":"[REDACTED]"}', b'{"nested":{"key":"***"}}'])
def test_correction_f02_redaction_and_deep_documents_are_fixed_local_errors(body: bytes) -> None:
    with pytest.raises(ValueError) as caught:
        backend_module._checkout_json(body)
    assert getattr(caught.value, "code", None) == "checkout_response_secret_shaped"
    deep = b'{"a":' * (backend_module._MAX_CHECKOUT_JSON_DEPTH + 2) + b"null" + b"}" * (
        backend_module._MAX_CHECKOUT_JSON_DEPTH + 2
    )
    with pytest.raises(ValueError) as deep_error:
        backend_module._checkout_json(deep)
    assert getattr(deep_error.value, "code", None) == "checkout_response_malformed"
    assert not isinstance(deep_error.value, (RecursionError, MemoryError))


def test_correction_f03_real_loopback_slow_drip_stops_at_absolute_deadline() -> None:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    ready = threading.Event()

    def serve() -> None:
        ready.set()
        conn, _address = listener.accept()
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                request += conn.recv(4096)
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nx")
            time.sleep(0.15)
            try:
                conn.sendall(b"y")
            except OSError:
                pass
        finally:
            conn.close()
            listener.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    assert ready.wait(1)
    request = backend_module.urllib_request.Request(f"http://127.0.0.1:{port}/view")
    deadline = time.monotonic_ns() + 50_000_000
    started = time.monotonic()
    with pytest.raises(ValueError) as caught:
        with backend_module._open_checkout_http_bounded(request, deadline) as response:
            backend_module._read_framed_response(
                response, limit=8, timeout=0.05, deadline_ns=deadline
            )
    elapsed = time.monotonic() - started
    thread.join(timeout=1)
    assert getattr(caught.value, "code", None) == "checkout_response_deadline_expired"
    assert elapsed < 0.12


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
    with pytest.raises(ValueError, match="checkout_runtime_binding_mismatch"):
        matching.warm_session(
            "probe",
            _warmth(matching, "probe"),
            runtime_instance_id=RUNTIME_A,
            model_bytes_digest="sha256:" + "a" * 64,
            declared_root=lie_root,
        )
