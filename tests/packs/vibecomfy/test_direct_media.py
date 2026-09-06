from __future__ import annotations

import pytest

from astrid.packs.vibecomfy.media import (
    CharacterAnimationRequest,
    DirectVibeMediaExecutor,
    MediaCompileError,
    MediaExecutionError,
    VideoEnhanceRequest,
    WanI2VRequest,
    WanT2IRequest,
    compile_character_animation,
    compile_video_enhance,
    compile_wan_2_2_i2v,
    compile_wan_2_2_t2i,
    profile_semantics,
)


@pytest.mark.parametrize("profile", ["pip_embedded", "checkout_server"])
def test_direct_wan_capabilities_are_typed_and_profile_bound(profile: str) -> None:
    t2i = compile_wan_2_2_t2i(
        WanT2IRequest(prompt="a red kite over a lake"), profile=profile
    )
    i2v = compile_wan_2_2_i2v(
        WanI2VRequest(image_ref="media://start", prompt="the kite moves"),
        profile=profile,
    )

    assert t2i.capability_id == "vibecomfy.wan_2_2_t2i"
    assert t2i.model_identity == "wan-2.2-a14b-t2v"
    assert t2i.inputs["frames"] == 1
    assert t2i.workflow["nodes"]["latent"]["inputs"]["frames"] == 1
    assert t2i.template_id != "wan2gp.generate_video"
    assert i2v.capability_id == "vibecomfy.wan_2_2_i2v"
    assert i2v.model_identity == "wan-2.2-a14b-i2v"
    assert i2v.workflow["nodes"]["image"]["inputs"]["image"] == "media://start"
    assert i2v.profile.profile_id == profile


def test_profile_semantics_are_explicit_and_distinct() -> None:
    embedded = profile_semantics("pip_embedded")
    checkout = profile_semantics("checkout_server")

    assert embedded.engine_identity != checkout.engine_identity
    assert embedded.lifecycle == "embedded_session"
    assert checkout.lifecycle == "managed_checkout_session"
    assert "runtime_instance_id" not in embedded.required_runtime_fields
    assert "runtime_instance_id" in checkout.required_runtime_fields
    assert embedded.output_transport != checkout.output_transport


@pytest.mark.parametrize("profile", ["pip_embedded", "checkout_server"])
def test_remaining_media_family_compilers_preserve_input_semantics(profile: str) -> None:
    enhance = compile_video_enhance(
        VideoEnhanceRequest(video_ref="media://source"), profile=profile
    )
    animate = compile_character_animation(
        CharacterAnimationRequest(
            reference_image_ref="media://character",
            driving_video_ref="media://motion",
            prompt="walk forward",
        ),
        profile=profile,
    )

    assert enhance.capability_id == "vibecomfy.video_enhance"
    assert enhance.inputs["preserve_audio"] is True
    assert enhance.inputs["preserve_source_fps"] is True
    assert enhance.workflow["nodes"]["input"]["inputs"]["video"] == "media://source"
    assert animate.capability_id == "vibecomfy.character_animation"
    assert animate.model_identity == "wan-2.2-animate-14b"
    assert animate.workflow["nodes"]["reference"]["inputs"]["image"] == "media://character"
    assert animate.workflow["nodes"]["driving"]["inputs"]["video"] == "media://motion"


def test_video_enhance_requires_one_enabled_operation() -> None:
    with pytest.raises(MediaCompileError, match="enable_interpolation or enable_upscale"):
        compile_video_enhance(
            VideoEnhanceRequest(
                video_ref="media://source",
                enable_interpolation=False,
                enable_upscale=False,
            )
        )


def test_compilation_is_deterministic_and_rejects_native_wan_confusion() -> None:
    request = WanT2IRequest(prompt="a quiet lake")
    first = compile_wan_2_2_t2i(request)
    second = compile_wan_2_2_t2i(request)

    assert first.to_dict() == second.to_dict()
    assert first.request_digest.startswith("sha256:")
    assert first.capability_id != "wan2gp.generate_video"

    with pytest.raises(MediaCompileError, match="unsupported Vibe profile"):
        compile_wan_2_2_t2i(request, profile="wan2gp")


def test_executor_requires_profile_identity_and_does_not_fallback() -> None:
    seen: list[tuple[str, str, str]] = []

    def runner(workflow, *, capability_id, model_identity, profile_id, task_identity):
        seen.append((capability_id, model_identity, profile_id))
        assert workflow["nodes"]
        return {"artifact": "media://output"}

    executor = DirectVibeMediaExecutor("checkout_server", runner)
    request = WanT2IRequest(prompt="a quiet lake")
    with pytest.raises(MediaExecutionError, match="runtime identity is incomplete"):
        executor.execute_wan_2_2_t2i(
            request,
            task_identity="task-1",
            runtime_context={"model_bytes_digest": "sha256:" + "a" * 64},
        )
    assert seen == []

    result = executor.execute_wan_2_2_t2i(
        request,
        task_identity="task-1",
        runtime_context={
            "profile_digest": "sha256:" + "b" * 64,
            "runtime_instance_id": "runtime-1",
            "environment_fingerprint": "env-1",
            "model_bytes_digest": "sha256:" + "a" * 64,
            "declared_root": "/worker/vibecomfy",
            "declared_port": 8188,
        },
    )
    assert result.profile_id == "checkout_server"
    assert result.output_transport == "checkout_server_publication"
    assert result.outputs == {"artifact": "media://output"}
    assert seen == [("vibecomfy.wan_2_2_t2i", "wan-2.2-a14b-t2v", "checkout_server")]
