"""The encoded loader masks must already be on H3's native grids."""

import subprocess
import zipfile
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.compile import compile_preparation
from astrid.packs.h3_av.src.masks import PreparedAVMask, load_prepared_av_mask
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from tests.packs.h3_av.test_h3_kernel_contract import _latent, _load_pinned_module

torch = pytest.importorskip("torch")


def _decode_mask(path: Path, *, frames: int, height: int, width: int):
    raw = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ], check=True, capture_output=True).stdout
    rgb = torch.tensor(list(raw), dtype=torch.uint8).reshape(frames, height, width, 3)
    return (rgb[..., 0].float() / 255 > 0.5).float()


def test_sparse_impulses_survive_emitted_loader_to_sampler_grid(tmp_path: Path) -> None:
    image = tmp_path / "reference.png"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", "color=c=blue:s=32x32:r=24", "-frames:v", "1", str(image),
    ], check=True)
    request = normalize_request({
        "version": 2, "prompt": "A shot.", "duration": 15,
        "media": [{"id": "ref", "asset": "reference.png", "role": "reference", "modality": "image"}],
        "settings": {},
    })
    prepared = prepare_request(request, asset_map={"reference.png": str(image)}, width=32, height=32)
    original = load_prepared_av_mask(prepared["prepared_av_mask"])
    video = torch.zeros((360, 32, 32), dtype=torch.uint8)
    for frame, row, column in ((0, 0, 0), (2, 0, 0), (16, 16, 16), (17, 31, 31), (18, 0, 31), (359, 7, 7)):
        video[frame, row, column] = 1
    audio = torch.zeros((2, 720000), dtype=torch.uint8)
    audio[1, 120000] = 1
    artifact = PreparedAVMask.from_arrays(
        video_delivery=video, audio_delivery=audio, fps=24, sample_rate=48000,
        source_baseline_digest=None, video_coverage=original.video_coverage,
        audio_coverage=original.audio_coverage, mapping=original.mapping,
        channel_layout="stereo", source_hashes=original.source_hashes,
        native_padding_trim=original.native_padding_trim,
        target_model_dimensions=original.target_model_dimensions,
        anchor_classification=original.anchor_classification,
    )
    prepared["prepared_av_mask"] = artifact.to_manifest()
    prepared["artifact_digest"] = artifact.artifact_digest
    report = compile_preparation(prepared, out_dir=tmp_path / "compiled")
    with zipfile.ZipFile(report["managed_assets"]["path"]) as archive:
        masks = {}
        for stream in ("video", "audio"):
            member = next(name for name in archive.namelist() if f"prepared-{stream}-mask" in name)
            masks[stream] = tmp_path / f"{stream}.mkv"
            masks[stream].write_bytes(archive.read(member))
    pinned = _load_pinned_module("existing_video_extension.py", "existing_video_extension")
    video_mask = _decode_mask(masks["video"], frames=107, height=2, width=2)
    audio_mask = _decode_mask(masks["audio"], frames=603, height=1, width=1)
    latent = _latent(video_mask=torch.zeros((1, 1, 107, 2, 2)), audio_mask=torch.zeros((1, 1, 2, 603)))
    result = pinned.MiniMaxH3SetAVNoiseMask().set_mask(latent, video_mask=video_mask, audio_mask=audio_mask)[0]
    out_video, out_audio = result["noise_mask"].unbind()
    assert out_video[0, 0, 1, 0, 0] == 1  # frame 2, upper-left pixel
    assert out_video[0, 0, 4, 1, 1] == 1  # frame 16
    assert out_video[0, 0, 5, 1, 1] == 1  # frame 17
    assert out_video[0, 0, 6, 0, 1] == 1  # frame 18
    assert out_video[0, 0, -1, 0, 0] == 1  # frame 359 shares a cell with the native tail
    assert out_audio[0, 0, 0, 100] == 1
    assert out_audio[0, 0, 0, 101] == 0
    assert out_audio[0, 0, 0, 600:].count_nonzero() == 0
