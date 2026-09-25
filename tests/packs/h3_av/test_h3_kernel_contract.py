from __future__ import annotations

import ast
import copy
import hashlib
import importlib.util
import math
import os
import subprocess
import sys
import types
import urllib.request
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.graph import build_h3_graph_binding
from astrid.packs.h3_av.src.kernel import (
    H3KernelContractError,
    classify_anchors,
    conservative_audio_tick_envelope,
    conservative_video_cell_mask,
    conservative_video_frame_mask,
    frame_cell,
    intersect_sampling_permissions,
    require_supported_anchors,
    temporal_cells,
    validate_final_sampler_state,
)
from astrid.packs.h3_av.src.request import normalize_request
from tests.packs.h3_av.test_request_contract import FIXTURES

torch = pytest.importorskip("torch")


PINNED_SEITANISM_COMMIT = "361624fb406b63eb6694442eac6c895fc1533a70"
PINNED_COMFY_COMMIT = "ee71d5c4993f29086b27fde1629a945ae48425bf"
PINNED_NATIVE_SHA256 = "62ec72d4f3b879640dbd41b959a6c1112a82b77478509323094f49dae17fffdb"


def _pinned_source() -> Path:
    candidates = [
        Path(os.environ["ASTRID_H3_SEITANISM_SOURCE"])
        if os.environ.get("ASTRID_H3_SEITANISM_SOURCE")
        else None,
        Path("/private/tmp/h3-seitanism-361624fb"),
        Path(__file__).resolve().parents[3].parent
        / "vibecomfy/ready_templates/sources/custom_nodes/ComfyUI-H3-Motion-Context-MultiRef",
    ]
    for candidate in candidates:
        if candidate is None or not (candidate / "h3_v2v_fractional.py").is_file():
            continue
        try:
            commit = subprocess.run(
                ["git", "-C", str(candidate), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            continue
        if commit != PINNED_SEITANISM_COMMIT:
            continue
        return candidate
    pytest.skip("pinned Seitanism source checkout is unavailable")


def _install_comfy_stubs() -> None:
    comfy = types.ModuleType("comfy")
    nested = types.ModuleType("comfy.nested_tensor")
    utils = types.ModuleType("comfy.utils")

    class NestedTensor:
        def __init__(self, values):
            self.values = list(values)

        def unbind(self):
            return tuple(self.values)

    nested.NestedTensor = NestedTensor
    utils.common_upscale = lambda samples, width, height, mode, crop: samples
    comfy.nested_tensor = nested
    comfy.utils = utils
    sys.modules["comfy"] = comfy
    sys.modules["comfy.nested_tensor"] = nested
    sys.modules["comfy.utils"] = utils


def _load_pinned_module(filename: str, module_name: str):
    root = _pinned_source()
    package = "astrid_h3_pinned_source"
    if package not in sys.modules:
        package_module = types.ModuleType(package)
        package_module.__path__ = [str(root)]
        sys.modules[package] = package_module
    _install_comfy_stubs()
    compatibility = types.ModuleType(f"{package}.h3_compat")
    compatibility.ensure_existing_video_compat = lambda: True
    sys.modules[f"{package}.h3_compat"] = compatibility
    key = f"{package}.{module_name}"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, root / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


def _load_pinned_reference_execute():
    url = (
        "https://raw.githubusercontent.com/comfyanonymous/ComfyUI/"
        f"{PINNED_COMFY_COMMIT}/comfy_extras/nodes_minimax_h3.py"
    )
    source = urllib.request.urlopen(url, timeout=30).read()  # noqa: S310 - immutable pinned source
    assert hashlib.sha256(source).hexdigest() == PINNED_NATIVE_SHA256
    tree = ast.parse(source)
    selected: list[ast.stmt] = []
    constants = {"CANVAS_MULTIPLE", "REF_IMAGE_SHORT_EDGE", "FPS", "AUDIO_LATENT_FPS"}
    functions = {"align_frame_count", "video_latent_t", "temporal_shape", "_resize", "_empty_av_latent"}
    execute = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in constants for target in node.targets):
            selected.append(copy.deepcopy(node))
        elif isinstance(node, ast.FunctionDef) and node.name in functions:
            selected.append(copy.deepcopy(node))
        elif isinstance(node, ast.ClassDef) and node.name == "MiniMaxH3ReferenceToVideo":
            execute = next(copy.deepcopy(item) for item in node.body if isinstance(item, ast.FunctionDef) and item.name == "execute")
    assert execute is not None
    execute.decorator_list = []
    execute.name = "reference_execute"
    selected.append(execute)

    class NodeOutput:
        def __init__(self, *values):
            self.values = values

    class NestedTensor:
        def __init__(self, values):
            self.values = tuple(values)

        def unbind(self):
            return self.values

    comfy = types.SimpleNamespace(
        model_management=types.SimpleNamespace(intermediate_device=lambda: torch.device("cpu")),
        nested_tensor=types.SimpleNamespace(NestedTensor=NestedTensor),
        utils=types.SimpleNamespace(common_upscale=lambda samples, width, height, mode, crop: samples),
    )

    def conditioning_set_values(conditioning, values):
        result = copy.deepcopy(conditioning)
        result[0][1].update(values)
        return result

    namespace = {
        "math": math,
        "torch": torch,
        "comfy": comfy,
        "io": types.SimpleNamespace(NodeOutput=NodeOutput),
        "node_helpers": types.SimpleNamespace(conditioning_set_values=conditioning_set_values),
    }
    ast.fix_missing_locations(tree := ast.Module(body=selected, type_ignores=[]))
    exec(compile(tree, url, "exec"), namespace)
    return namespace["reference_execute"]


def _latent(*, video_mask: torch.Tensor, audio_mask: torch.Tensor) -> dict:
    nested = sys.modules["comfy.nested_tensor"].NestedTensor
    video = torch.zeros((1, 24, video_mask.shape[2], video_mask.shape[3], video_mask.shape[4]))
    audio = torch.zeros((1, 32, 2, audio_mask.shape[-1]))
    return {
        "samples": nested((video, audio)),
        "noise_mask": nested((video_mask, audio_mask)),
    }


def test_temporal_mapping_frames_zero_one_two_and_boundaries() -> None:
    assert [frame_cell(frame, 11)["cell"] for frame in (0, 1, 2)] == [0, 1, 1]
    assert [frame_cell(frame, 11)["cell"] for frame in (16, 17, 18)] == [4, 5, 6]
    assert temporal_cells(7) == [
        {"cell": 0, "start": 0, "end": 1, "span": 1},
        {"cell": 1, "start": 1, "end": 5, "span": 4},
        {"cell": 2, "start": 5, "end": 9, "span": 4},
        {"cell": 3, "start": 9, "end": 13, "span": 4},
        {"cell": 4, "start": 13, "end": 17, "span": 4},
        {"cell": 5, "start": 17, "end": 18, "span": 1},
        {"cell": 6, "start": 18, "end": 22, "span": 4},
    ]


@pytest.mark.parametrize("row,column", [(0, 0), (3, 7), (7, 15)])
def test_one_pixel_video_mask_survives_actual_pinned_v2v_boundary(row: int, column: int) -> None:
    pinned = _load_pinned_module("h3_v2v_fractional.py", "h3_v2v_fractional")
    delivery = torch.zeros((22, 8, 16), dtype=torch.float32)
    delivery[2, row, column] = 1.0
    frame_mask = conservative_video_frame_mask(
        delivery, latent_steps=7, latent_height=2, latent_width=4
    )
    fitted = pinned._fit_mask_frames(
        frame_mask,
        int(frame_mask.shape[0]),
        torch.arange(int(frame_mask.shape[0])),
        0,
        int(frame_mask.shape[0]),
    )
    assert torch.equal(fitted, frame_mask)
    actual = pinned._mask_to_video_latent(frame_mask, 7, 2, 4, "max")
    expected = conservative_video_cell_mask(
        delivery, latent_steps=7, latent_height=2, latent_width=4
    )
    assert torch.equal(actual[0, 0], expected)
    assert actual[0, 0, 1].amax().item() == 1.0


def test_small_region_expands_only_by_declared_spatial_and_temporal_support() -> None:
    delivery = torch.zeros((22, 8, 16), dtype=torch.float32)
    delivery[16, 2:4, 6:9] = 1.0
    cells = conservative_video_cell_mask(
        delivery, latent_steps=7, latent_height=2, latent_width=4
    )
    assert torch.count_nonzero(cells[4]).item() >= 1
    assert torch.count_nonzero(cells[:4]).item() == 0
    assert torch.count_nonzero(cells[5:]).item() == 0


@pytest.mark.parametrize("sample_rate", [44100, 48000])
def test_one_sample_one_channel_audio_permission_becomes_joint_tick_envelope(sample_rate: int) -> None:
    pinned = _load_pinned_module("existing_video_extension.py", "existing_video_extension")
    permissions = torch.zeros((2, sample_rate), dtype=torch.bool)
    permissions[0, sample_rate // 2] = True
    frame_mask = conservative_audio_tick_envelope(
        permissions, sample_rate=sample_rate, audio_ticks=40
    )
    actual = pinned._mask_to_audio_stream(frame_mask, 40)
    assert actual.shape == (1, 1, 2, 40)
    assert torch.equal(actual[0, 0, 0], actual[0, 0, 1])
    assert torch.count_nonzero(actual).item() >= 2
    assert permissions[1].count_nonzero().item() == 0


def test_mask_plus_extension_and_audio_only_set_preserve_existing_video_mask() -> None:
    pinned = _load_pinned_module("existing_video_extension.py", "existing_video_extension")
    extension_video_mask = torch.ones((1, 1, 7, 2, 4))
    extension_video_mask[:, :, 1] = 0.0
    edit_video_mask = torch.zeros((1, 1, 7, 2, 4))
    edit_video_mask[:, :, 1:3, 0, 0] = 1.0
    video_mask = intersect_sampling_permissions(extension_video_mask, edit_video_mask)
    assert torch.count_nonzero(video_mask[:, :, 1]).item() == 0
    assert video_mask[0, 0, 2, 0, 0].item() == 1.0
    old_audio = torch.zeros((1, 1, 2, 40))
    latent = _latent(video_mask=video_mask, audio_mask=old_audio)
    permissions = torch.zeros((2, 48000), dtype=torch.bool)
    permissions[1, 12000:12001] = True
    audio_envelope = conservative_audio_tick_envelope(
        permissions, sample_rate=48000, audio_ticks=40
    )

    output = pinned.MiniMaxH3SetAVNoiseMask().set_mask(
        latent, video_mask=None, audio_mask=audio_envelope
    )[0]
    out_video, out_audio = output["noise_mask"].unbind()
    assert out_video is video_mask
    assert out_audio.shape == (1, 1, 2, 40)
    assert torch.equal(out_audio[0, 0, 0], out_audio[0, 0, 1])


def test_anchor_default_soft_restoration_and_phase_zero_hard_rule() -> None:
    classified = classify_anchors(
        [
            {"id": "f0", "frame": 0},
            {"id": "f1", "frame": 1},
            {"id": "f2", "frame": 2},
            {"id": "f17", "frame": 17, "mode": "hard"},
            {"id": "f18", "frame": 18, "mode": "restoration"},
        ],
        latent_steps=11,
    )
    assert [item["classification"] for item in classified] == [
        "soft_conditioned",
        "soft_conditioned",
        "soft_conditioned",
        "hard_conditioned",
        "restoration_only",
    ]
    assert all(item["exact_final_restoration"] for item in classified)


def test_colliding_or_nonrepresentable_hard_anchors_are_never_shifted() -> None:
    classified = classify_anchors(
        [
            {"id": "f1", "frame": 1, "mode": "hard"},
            {"id": "f2", "frame": 2, "mode": "hard"},
        ],
        latent_steps=7,
    )
    assert [item["frame"] for item in classified] == [1, 2]
    assert {item["classification"] for item in classified} == {"rejected"}
    assert all("hard_anchor_cell_collision" in item["reasons"] for item in classified)
    with pytest.raises(H3KernelContractError, match="f1, f2"):
        require_supported_anchors(classified)

    soft = classify_anchors(
        [{"id": "f2", "frame": 2, "mode": "hard"}],
        latent_steps=7,
        unsupported_hard="soft",
    )
    assert soft[0]["frame"] == 2
    assert soft[0]["classification"] == "soft_conditioned"
    assert "declared_soft_fallback" in soft[0]["reasons"]


def _mixed_sampler_state() -> dict:
    return {
        "sampler": "sampler-final",
        "sampler_sockets": {
            "noise": "noise.out",
            "guider": "guider.out",
            "sampler": "sampler-select.out",
            "sigmas": "scheduler.out",
            "latent_image": "hard-anchors.out",
        },
        "latent_lineage": [
            {"node": "fractional-v2v", "input_source": None, "output": "fractional-v2v.out", "kind": "source_av_context"},
            {"node": "set-av-mask", "input_source": "fractional-v2v.out", "output": "set-av-mask.out", "kind": "nested_av_mask"},
            {"node": "hard-anchors", "input_source": "set-av-mask.out", "output": "hard-anchors.out", "kind": "hard_anchor"},
        ],
        "conditioning_lineage": [
            {"node": "reference-to-video", "input_source": None, "output": "reference-to-video.out", "kind": "reference"},
            {"node": "soft-keyframes", "input_source": "reference-to-video.out", "output": "soft-keyframes.out", "kind": "soft_anchor"},
            {"node": "motion-context", "input_source": "soft-keyframes.out", "output": "motion-context.out", "kind": "motion_context"},
        ],
        "guider": {"node": "guider", "conditioning_source": "motion-context.out", "output": "guider.out"},
    }


def test_complete_mixed_state_reaches_final_sampler_sockets() -> None:
    report = validate_final_sampler_state(
        _mixed_sampler_state(),
        required_latent_kinds={"source_av_context", "nested_av_mask", "hard_anchor"},
        required_conditioning_kinds={"reference", "soft_anchor", "motion_context"},
    )
    assert report["status"] == "valid"
    assert report["sockets"]["latent_image"] == "hard-anchors.out"


def test_later_sampler_overwrite_is_rejected() -> None:
    state = _mixed_sampler_state()
    state["sampler_sockets"]["latent_image"] = "stale-before-mask.out"
    with pytest.raises(H3KernelContractError, match="final latent mutation"):
        validate_final_sampler_state(state)


def test_pinned_native_four_image_payload_is_ordered_and_drives_masked_cpu_substitute() -> None:
    execute = _load_pinned_reference_execute()

    class FakeClip:
        def __init__(self):
            self.presentations: list[list[float]] = []

        def tokenize(self, prompt, *, minimax_ref_items):
            assert prompt == "Four ordered pictures."
            self.presentations.append([float(item["data"][0, 0, 0, 0]) for item in minimax_ref_items])
            return {"items": minimax_ref_items}

        def encode_from_tokens_scheduled(self, tokens):
            return [[torch.tensor([1.0]), {}]]

    class FakeVAE:
        def encode(self, image):
            sentinel = float(image[0, 0, 0, 0])
            return torch.full((1, 24, 1, 2, 2), sentinel)

    def run(sentinels: list[float]):
        clip = FakeClip()
        images = {
            f"ref_image_{index}": torch.full((1, 32, 32, 3), sentinel)
            for index, sentinel in enumerate(sentinels)
        }
        result = execute(
            None,
            clip,
            "Four ordered pictures.",
            32,
            32,
            362,
            ref_image_size="match",
            vae=FakeVAE(),
            audio_vae=None,
            ref_images=images,
            ref_videos=None,
            ref_video_audios=None,
            ref_audios=None,
        )
        conditioning, latent = result.values
        refs = conditioning[0][1].get("minimax_refs", [])
        video, audio = latent["samples"].unbind()
        assert tuple(video.shape) == (1, 24, 107, 2, 2)
        assert tuple(audio.shape) == (1, 32, 2, 603)
        payload = [float(item["latent"][0, 0, 0, 0, 0]) for item in refs]
        assert clip.presentations[-1] == sentinels
        assert payload == sentinels
        return payload, video, audio

    def substitute(payload, video, audio):
        # This consumes the resolved conditioning blocks and the final nested
        # all-generate masks that reach the sampler, never request metadata.
        video_mask = torch.ones((1, 1, video.shape[2], video.shape[3], video.shape[4]))
        audio_mask = torch.ones((1, 1, 2, audio.shape[-1]))
        score = sum((index + 1) * value for index, value in enumerate(payload))
        score += float(video_mask.mean()) + float(audio_mask.mean())
        return torch.tensor([score, score * 2], dtype=torch.float32)

    sentinels = [11.0, 22.0, 33.0, 44.0]
    payload, video, audio = run(sentinels)
    request = normalize_request(FIXTURES["A"]())
    prepared = {
        "prepared_input": {
            "kind": "h3_av_prepared_input",
            "status": "prepared",
            "request": request.value,
            "request_digest": request.digest,
            "source_baseline_digest": None,
            "mapping": {"baseline_identity": {"kind": "none", "digest": None, "members": []}},
            "video": {
                "delivery": {"shape": [360, 32, 32], "payload": "all-one-video", "polarity": "black_preserve_white_edit"},
                "sampling": {"shape": [107, 2, 2], "payload": "all-one-video-latent", "polarity": "black_preserve_white_edit"},
            },
            "audio": {
                "delivery": {"shape": [2, 720000], "payload": "all-one-audio", "polarity": "black_preserve_white_edit"},
                "sampling": {"shape": [603, 1, 1], "payload": "all-one-audio-latent", "polarity": "black_preserve_white_edit"},
            },
            "anchors": [],
        }
    }
    binding = build_h3_graph_binding(prepared)
    from vibecomfy.workflow import VibeWorkflow

    reloaded = VibeWorkflow.from_envelope(copy.deepcopy(binding["executable_graph"]["envelope"]))
    api = reloaded.compile("api")
    resolved_payload = []
    for index in range(4):
        loader, output = api["110"]["inputs"][f"ref_images.ref_image_{index}"]
        assert output == 0
        assert loader == f"c3-reference-image-{index}"
        resolved_payload.append(payload[int(loader.rsplit("-", 1)[-1])])
    graph_edges = {(edge.from_node, edge.from_output, edge.to_node, edge.to_input) for edge in reloaded.edges}
    assert ("110", "0", "121", "conditioning") in graph_edges
    assert ("121", "0", "124", "guider") in graph_edges
    assert ("110", "1", "c3-av-mask", "latent") in graph_edges
    assert ("c3-av-mask", "0", "124", "latent_image") in graph_edges
    assert ("c3-video-mask-loader", "1", "c3-av-mask", "video_mask") in graph_edges
    assert ("c3-audio-mask-loader", "1", "c3-av-mask", "audio_mask") in graph_edges
    baseline = substitute(resolved_payload, video, audio)
    assert payload == sentinels

    for index in range(4):
        omitted_values = sentinels[:index] + sentinels[index + 1 :]
        omitted = run(omitted_values)
        assert len(omitted[0]) == 3
        assert not torch.equal(substitute(*omitted), baseline)

        mutated_values = list(sentinels)
        mutated_values[index] += 100.0
        mutated = run(mutated_values)
        assert mutated[0][index] == sentinels[index] + 100.0
        assert not torch.equal(substitute(*mutated), baseline)

    reordered = run(list(reversed(sentinels)))
    assert reordered[0] == list(reversed(sentinels))
    assert not torch.equal(substitute(*reordered), baseline)
