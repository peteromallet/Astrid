from __future__ import annotations

from pathlib import Path

import pytest

from astrid.packs.vibecomfy.direct_image import (
    CANONICAL_CAPABILITIES,
    DirectImageExecutor,
    ImageCompileError,
    ImageExecutionError,
    compile_image_request,
    normalize_capability_id,
    portable_execution_digest,
)


def test_route_matrix_covers_retained_direct_image_families() -> None:
    assert set(CANONICAL_CAPABILITIES) == {
        "z_image_turbo",
        "z_image_turbo_i2i",
        "qwen_image",
        "qwen_image_2512",
        "qwen_image_edit",
        "qwen_image_style",
        "image_inpaint",
        "annotated_image_edit",
        "flux_klein_edit",
        "image_upscale",
    }
    assert normalize_capability_id("z_image") == "z_image_turbo"
    assert normalize_capability_id("image-upscale") == "image_upscale"
def test_every_direct_capability_compiles_on_both_profiles() -> None:
    for capability_id, spec in CANONICAL_CAPABILITIES.items():
        params = {
            field: (
                "cas/source.png"
                if field in {"image_ref", "mask_ref"}
                else "fixture prompt"
            )
            for field in spec.required
        }
        for profile in ("pip_embedded", "checkout_server"):
            compiled = compile_image_request(capability_id, params, profile=profile)
            assert compiled.capability_id == capability_id
            assert compiled.profile.name == profile
            assert compiled.execution_digest.startswith("sha256:")




def test_qwen_variants_and_flux_keep_model_identity() -> None:
    qwen = compile_image_request(
        "qwen_image", {"prompt": "a red kite"}, profile="pip_embedded"
    )
    qwen_2512 = compile_image_request(
        "qwen_image_2512", {"prompt": "a red kite"}, profile="pip_embedded"
    )
    klein = compile_image_request(
        "flux_klein_edit",
        {"prompt": "remove the sign", "image_ref": "cas/source.png"},
        profile="pip_embedded",
    )
    assert qwen.model_id != qwen_2512.model_id
    assert klein.model_id == "flux-klein-4b-edit"
    assert qwen.template_id == qwen_2512.template_id
    assert klein.template_id != qwen.template_id


def test_profiles_share_request_schema_but_have_distinct_portable_identity() -> None:
    params = {"prompt": "a blue room", "seed": 4}
    embedded = compile_image_request("z_image_turbo", params, profile="pip_embedded")
    checkout = compile_image_request("z_image_turbo", params, profile="checkout_server")
    assert embedded.profile.warm_policy == "never"
    assert checkout.profile.warm_policy == "auto"
    assert embedded.profile.session_kind != checkout.profile.session_kind
    assert embedded.execution_digest != checkout.execution_digest
    assert portable_execution_digest(embedded) == embedded.execution_digest
    assert portable_execution_digest(checkout) == checkout.execution_digest


def test_machine_local_values_do_not_change_portable_digest() -> None:
    base = compile_image_request("z_image_turbo", {"prompt": "a tree"}, profile="pip_embedded")
    moved = portable_execution_digest(
        {
            **base.to_dict(),
            "machine_path": "/other/root",
            "port": 4242,
            "gpu_uuid": "GPU-B",
            "server_url": "http://127.0.0.1:4242",
        }
    )
    assert moved == base.execution_digest


def test_compiler_rejects_unknown_fields_and_unsafe_input_refs() -> None:
    with pytest.raises(ImageCompileError, match="unknown"):
        compile_image_request(
            "z_image_turbo", {"prompt": "x", "backend": "fallback"}, profile="pip_embedded"
        )
    with pytest.raises(ImageCompileError, match="safe CAS"):
        compile_image_request(
            "z_image_turbo_i2i",
            {"prompt": "x", "image_ref": "../outside.png"},
            profile="pip_embedded",
        )
    with pytest.raises(ImageCompileError, match="unsupported Vibe profile"):
        compile_image_request("z_image_turbo", {"prompt": "x"}, profile="auto")


class _FakeEngine:
    def __init__(self, output: str = "generated.png") -> None:
        self.output = output
        self.workflow = None

    def run(self, workflow, *, task_identity, out_dir: Path):
        self.workflow = workflow
        output = out_dir / self.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fixture-png")
        return {"outputs": [output]}


def test_executor_attests_template_binds_typed_request_and_returns_relative_output(tmp_path: Path) -> None:
    engine = _FakeEngine()
    result = DirectImageExecutor().execute(
        "z_image_turbo",
        {"prompt": "a lighthouse", "seed": 11},
        profile="pip_embedded",
        engine=engine,
        out_dir=tmp_path,
        task_identity="task-1",
    )
    assert result.capability_id == "z_image_turbo"
    assert result.model_id == "z-image-turbo"
    assert result.profile == "pip_embedded"
    assert result.outputs == ("generated.png",)
    assert engine.workflow is not None
    assert result.template_digest.startswith("sha256:")
    assert engine.workflow["template_id"] == "image/z_image"
    assert engine.workflow["bindings"]["model_id"] == "z-image-turbo"


def test_executor_rejects_output_escape(tmp_path: Path) -> None:
    class EscapingEngine(_FakeEngine):
        def run(self, workflow, *, task_identity, out_dir: Path):
            return {"outputs": [tmp_path.parent / "outside.png"]}

    with pytest.raises(ImageExecutionError, match="escapes"):
        DirectImageExecutor().execute(
            "image-upscale",
            {"image_ref": "cas/source.png", "upscale_factor": 2},
            profile="checkout_server",
            engine=EscapingEngine(),
            out_dir=tmp_path,
        )
