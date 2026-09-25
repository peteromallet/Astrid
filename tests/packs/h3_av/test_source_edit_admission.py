"""Delivery-clock source edits use the pinned full-source H3 V2V primitive."""

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.compile import compile_preparation
from astrid.packs.h3_av.src.graph import build_h3_graph_binding
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from tests.packs.h3_av.test_graph_binding import _prepared
from tests.packs.h3_av.test_request_contract import FIXTURES


@pytest.mark.parametrize("label", ["B", "E", "F", "X"])
def test_required_source_edit_graphs_have_one_delivery_clock_sampler(label: str) -> None:
    binding = build_h3_graph_binding(_prepared(normalize_request(FIXTURES[label]())))
    api = binding["executable_graph"]["compiled_api"]
    assert binding["branch"] == "source_backed_v2v"
    assert [row["node_id"] for row in binding["executable_graph"]["outputs"]] == ["992"]
    assert api["c3-full-source-v2v"]["class_type"] == "H3V2VGranularFractionalDenoise"
    assert api["c3-full-source-v2v"]["inputs"]["source_frames"] == ["99", 0]
    assert api["c3-full-source-v2v"]["inputs"]["source_audio"] == ["99", 2]
    assert api["c3-av-mask"]["inputs"]["latent"] == ["c3-full-source-v2v", 0]
    assert api["124"]["inputs"]["latent_image"] in (["c3-av-mask", 0], ["c3-hard-anchors", 0])


def test_unedited_prefix_keeps_real_continuation_sink() -> None:
    raw = FIXTURES["B"]()
    raw["media"][0]["edit"] = []
    binding = build_h3_graph_binding(_prepared(normalize_request(raw)))
    assert binding["branch"] == "extension_context"
    assert binding["executable_graph"]["outputs"][0]["node_id"] == "946"


def test_compiled_shifted_source_uses_packaged_full_length_av_baseline(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=32x32:r=24:d=4",
        "-f", "lavfi", "-i", "aevalsrc=0.25:s=48000:d=4",
        "-ac", "2", "-c:v", "ffv1", "-pix_fmt", "bgra", "-c:a", "pcm_s32le", str(source),
    ], check=True)
    request = normalize_request({
        "version": 2, "prompt": "Edit the placed image.", "duration": 4,
        "media": [{"id": "placed", "asset": "source.mkv", "role": "timeline", "modality": "video",
                   "range": [1, 3], "at": {"seconds": 1},
                   "edit": [{"stream": "video", "during": [0, 0.5], "mask": {"full_frame": True}}]}],
        "settings": {},
    })
    prepared = prepare_request(request, asset_map={"source.mkv": str(source)}, width=32, height=32)
    report = compile_preparation(prepared, out_dir=tmp_path / "compiled")
    with zipfile.ZipFile(report["managed_assets"]["path"]) as archive:
        baseline_name = next(name for name in archive.namelist() if "prepared-source-baseline" in name)
        baseline = tmp_path / "packaged-baseline.mkv"
        baseline.write_bytes(archive.read(baseline_name))
    probe = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=nb_read_frames", "-of", "json", str(baseline),
    ], check=True, capture_output=True, text=True)
    assert int(json.loads(probe.stdout)["streams"][0]["nb_read_frames"]) == 107
    raw = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(baseline),
        "-map", "0:v:0", "-frames:v", "49", "-f", "rawvideo", "-pix_fmt", "rgba", "pipe:1",
    ], check=True, capture_output=True).stdout
    frame_bytes = 32 * 32 * 4
    assert raw[:frame_bytes] == bytes(frame_bytes)
    assert raw[24 * frame_bytes:25 * frame_bytes] != bytes(frame_bytes)


def test_binary_png_still_mask_is_admitted_for_source_edit(tmp_path: Path) -> None:
    from PIL import Image

    source = tmp_path / "source.mkv"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=32x32:r=24:d=2",
        "-f", "lavfi", "-i", "aevalsrc=0.25:s=48000:d=2",
        "-ac", "2", "-c:v", "ffv1", "-pix_fmt", "bgra", "-c:a", "pcm_s32le", str(source),
    ], check=True)
    mask = tmp_path / "mouth.png"
    image = Image.new("L", (32, 32), 0)
    image.putpixel((7, 9), 255)
    image.save(mask)
    request = normalize_request({
        "version": 2, "prompt": "Edit the mouth.", "duration": 2,
        "media": [{"id": "source", "asset": "source.mkv", "role": "timeline", "modality": "video",
                   "at": {"frame": 0}, "range": [0, 2], "edit": [{"stream": "video", "during": [0, 1], "mask": "mouth.png"}]}],
        "settings": {},
    })
    prepared = prepare_request(request, asset_map={"source.mkv": str(source), "mouth.png": str(mask)}, width=32, height=32)
    from astrid.packs.h3_av.src.masks import load_prepared_av_mask

    delivery = load_prepared_av_mask(prepared["prepared_av_mask"]).video_delivery()
    assert delivery[0][9][7] == 1
    assert delivery[0][9][8] == 0
    assert delivery[24][9][7] == 0
    compiled = compile_preparation(prepared, out_dir=tmp_path / "png-compiled")
    assert compiled["status"] == "compiled"
    binding = json.loads((tmp_path / "png-compiled" / "graph_binding.json").read_text())
    assert binding["branch"] == "source_backed_v2v"


def test_continuation_tail_is_declared_generated() -> None:
    request = normalize_request({
        "version": 1, "operation": "continue", "source": {"asset": "source.mp4", "range": [0, 2]},
        "output": {"duration": 4}, "content": {"prompt": "Continue the shot."},
        "changes": {"video": [], "audio": []}, "references": [], "overrides": {},
    })
    preparation = prepare_request(request)
    schedule = preparation["mask_schedule"]
    assert schedule["video"]["protected_intervals"] == [[0.0, 2.0]]
    assert schedule["video"]["generated_intervals"] == [[2.0, 4.0]]
    assert schedule["audio"]["generated_intervals"] == [[2.0, 4.0]]


def test_audio_mask_is_rejected_instead_of_discarded() -> None:
    request = normalize_request({
        "version": 1, "operation": "edit", "source": {"asset": "source.mp4", "range": [0, 2]},
        "output": {"duration": 2}, "content": {"prompt": "Edit the audio."},
        "changes": {"video": [], "audio": [{"during": [0, 1], "action": "generate", "mask_asset": "mask.wav"}]},
        "references": [], "overrides": {},
    })
    with pytest.raises(ValueError, match="audio mask assets are not supported"):
        prepare_request(request)
