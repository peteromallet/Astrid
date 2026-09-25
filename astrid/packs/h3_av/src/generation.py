"""General single-pass H3 reference-to-AV adapter; no project or fixture inputs.

Node contract: ComfyUI ee71d5c4993f29086b27fde1629a945ae48425bf,
comfy_extras/nodes_minimax_h3.py, MiniMaxH3ReferenceToVideo.
"""
from __future__ import annotations

from typing import Any

from .timing import frame_index, smallest_h3_run_at_least

IMAGE_REFERENCE_CAPACITY = 9


def generation_timing(duration: float) -> dict[str, Any]:
    frames = frame_index(duration, "output.duration")
    raw = smallest_h3_run_at_least(frames)
    # Bound this adapter to the upstream documented training range.
    if frames < 5 or raw > 362:
        raise ValueError("source-free duration must request 5..362 frames at 24 fps")
    return {"fps": 24, "requested_frames": frames, "raw_frames": raw,
            "trim_tail_frames": raw - frames, "duration": frames / 24}


def build_generation_workflow(*, references: list[str], prompt: str, frames: int,
                              model: str, steps: int, seed: int,
                              sampler: str = "res_multistep", guidance: float = 0.95):
    """Build ordinary H3 nodes and one muxed sink, ready for canonical emission.

    Graph shape depends only on reference list length. Filenames remain managed
    run bindings, not graph defaults; ordered slots bind Picture 1..N without
    implicit keyframe constraints.
    """
    from vibecomfy.templates import ModelAsset, OutputSpec, ReadyMetadata, new_workflow, node
    from vibecomfy.nodes.core import (
        BasicGuider, BasicScheduler, CLIPLoader, KSamplerSelect, LoadImage,
        LoraLoaderModelOnly, RandomNoise, SamplerCustomAdvanced, UNETLoader,
        VAEDecode, VAEDecodeAudio, VAELoader,
    )
    from vibecomfy.nodes.videohelpersuite import VHS_VideoCombine

    if not 1 <= len(references) <= IMAGE_REFERENCE_CAPACITY:
        raise ValueError("this adapter requires one to nine image references")
    base = "https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main"
    names = {
        "model": ("diffusion_models", "minimax_h3_ref2va_pruned_int8_convrot.safetensors"),
        "clip": ("text_encoders", "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"),
        "video_vae": ("vae", "minimax_h3_video_vae_int8_convrot.safetensors"),
        "audio_vae": ("vae", "minimax_h3_audio_vae_fp32.safetensors"),
        "lora": ("loras", "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"),
    }
    metadata = ReadyMetadata.build(
        capability="video", template_id="h3_av_reference_generation",
        models={key: ModelAsset(url=f"{base}/{subdir}/{name}", subdir=subdir)
                for key, (subdir, name) in names.items()},
        requirements={
            "runtime": {
                "comfy_commit": "ee71d5c4993f29086b27fde1629a945ae48425bf",
                "comfy_version": "==0.36.0",
                "packages": {"torch": "==2.10.0+cu130", "comfy-kitchen": "==0.2.34", "comfy-aimdo": "==0.5.3"},
                "launch_flags": ["--use-ck-attention", "--disable-comfy-compiler"],
            },
            "custom_node_refs": [
                {"slug": "ComfyUI-H3-Motion-Context-MultiRef", "source": "git",
                 "url": "https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef.git",
                 "commit": "361624fb406b63eb6694442eac6c895fc1533a70",
                 "classes": ["MiniMaxH3AudioVAECompatibility"]},
                {"slug": "ComfyUI-VideoHelperSuite", "source": "git",
                 "url": "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git",
                 "commit": "4ee72c065db22c9d96c2427954dc69e7b908444b",
                 "classes": ["VHS_VideoCombine"]},
            ],
        },
    )
    with new_workflow(metadata, source_path=__file__) as wf:
        unet = UNETLoader(unet_name=model, weight_dtype="default", _id="model")
        clip = CLIPLoader(clip_name=names["clip"][1], type="minimax", device="default")
        video_vae = VAELoader(vae_name=names["video_vae"][1])
        audio_vae = VAELoader(vae_name=names["audio_vae"][1])
        audio = node("MiniMaxH3AudioVAECompatibility", _outputs=("audio_vae",), audio_vae=audio_vae.out("VAE"))
        attention = node("ModelAttentionBackend", _outputs=("MODEL",), model=unet.out("MODEL"), attention="comfy kitchen attention")
        lora = LoraLoaderModelOnly(model=attention.out("MODEL"), lora_name=names["lora"][1], strength_model=guidance, _id="lora")
        shifted = node("MiniMaxH3SigmaShift", _outputs=("MODEL",), model=lora.out("MODEL"), shift_audio=3.0, shift_video=12.0)
        refs = {}
        for index in range(len(references)):
            ident = f"reference_{index}"
            # Canonical emission deliberately clears media defaults. Keep the
            # template unbound and supply filenames only via managed run inputs
            # so emitting/reloading cannot change the graph's semantic digest.
            loaded = LoadImage(image="", _id=ident)
            wf.register_input(ident, ident, "image", "", type="CHOICE", default="", required=True, media_semantics="image")
            refs[f"ref_images.ref_image_{index}"] = loaded.out("IMAGE")
        target = node("MiniMaxH3ReferenceToVideo", _id="target", _outputs=("positive", "LATENT"),
                      clip=clip.out("CLIP"), vae=video_vae.out("VAE"), audio_vae=audio.out("audio_vae"),
                      prompt=prompt, width=1024, height=576, length=frames, ref_image_size="match", **refs)
        schedule = BasicScheduler(model=shifted.out("MODEL"), scheduler="simple", steps=steps, denoise=1.0, _id="schedule")
        selected = KSamplerSelect(sampler_name=sampler, _id="sampler")
        noise = RandomNoise(noise_seed=seed, _id="noise")
        guider = BasicGuider(model=shifted.out("MODEL"), conditioning=target.out("positive"))
        sampled = SamplerCustomAdvanced(guider=guider.out("GUIDER"), latent_image=target.out("LATENT"),
                                       noise=noise.out("NOISE"), sampler=selected.out("SAMPLER"), sigmas=schedule.out("SIGMAS"))
        video = VAEDecode(samples=sampled.out("OUTPUT"), vae=video_vae.out("VAE"))
        sound = VAEDecodeAudio(samples=sampled.out("OUTPUT"), vae=audio.out("audio_vae"))
        movie = VHS_VideoCombine(images=video.out("IMAGE"), audio=sound.out("AUDIO"),
                                frame_rate=24, loop_count=0, filename_prefix="h3_av/generated",
                                format="video/h264-mp4", pingpong=False, save_output=True,
                                crf=19, pix_fmt="yuv420p", save_metadata=False, trim_to_audio=False)
        for name, ident, field, value, kind in (
            ("prompt", "target", "prompt", prompt, "STRING"),
            ("model", "model", "unet_name", model, "CHOICE"),
            ("steps", "schedule", "steps", steps, "INT"),
            ("seed", "noise", "noise_seed", seed, "INT"),
            ("sampler", "sampler", "sampler_name", sampler, "COMBO"),
            ("guidance", "lora", "strength_model", guidance, "FLOAT"),
        ):
            wf.register_input(name, ident, field, value, type=kind, default=value)
        return wf.finalize({}, outputs=[OutputSpec(
            node=movie, output_type="VHS_VideoCombine", name="video", artifact_kind="video",
            mime_type="video/mp4", filename_prefix="h3_av/generated", expected_cardinality="one",
        )])
