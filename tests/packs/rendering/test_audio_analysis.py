from __future__ import annotations

import hashlib
import shutil
import struct
import subprocess
import wave

import pytest

from astrid.packs.rendering.executors.timeline_visualize.audio_analysis import (
    AudioAnalysisError,
    analyze_audio,
)


def _stereo_wav(path, frames: list[tuple[float, float]], rate: int = 1000) -> str:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(2)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"".join(struct.pack("<hh", int(left * 32767), int(right * 32767)) for left, right in frames))
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg and ffprobe required")
def test_analysis_preserves_channels_and_measures_rational_quiet_gaps(tmp_path):
    frames = (
        [(0.0, 0.0)] * 200
        + [(0.5, -0.5)] * 200  # must not disappear through a mono sum
        + [(0.0, 0.0)] * 200
        + [(0.5, 0.5)] * 200
        + [(0.0, 0.0)] * 200
    )
    path = tmp_path / "render.wav"
    digest = _stereo_wav(path, frames)
    result = analyze_audio(path, render_digest=digest, settings={"threshold": 0.05, "min_gap_seconds": 0.1, "levels": [4, 8]})
    assert result["status"] == "ok"
    assert result["stream"]["channels"] == 2
    assert result["stream"]["channel_policy"].startswith("preserve channels")
    assert [(gap["start_sample"], gap["end_sample"]) for gap in result["quiet_gaps"]] == [(0, 200), (400, 600), (800, 1000)]
    assert result["quiet_gaps"][1]["measurement"] == "low_amplitude"
    assert result["quiet_gaps"][1]["duration"] == [1, 5]
    assert len(result["waveform"]["levels"]) == 2
    loud_bin = result["waveform"]["levels"][0]["bins"][1]
    assert loud_bin["peak"][0] > 0.4 and loud_bin["peak"][1] > 0.4
    assert result["presentation_origin"]["seconds"] == [0, 1]


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg and ffprobe required")
def test_analysis_has_explicit_no_stream_and_digest_identity(tmp_path):
    path = tmp_path / "video.mp4"
    subprocess.run([
        "ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:size=32x32:rate=2:duration=1",
        "-c:v", "libx264", "-y", str(path)
    ], check=True)
    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    result = analyze_audio(path, render_digest=digest)
    assert result["status"] == "no_audio_stream"
    assert result["coverage"]["state"] == "no_audio_stream"
    assert result["waveform"]["levels"] == []
    assert result["analysis_identity"] != analyze_audio(path, render_digest=digest, settings={"threshold": 0.2})["analysis_identity"]
    with pytest.raises(AudioAnalysisError, match="digest"):
        analyze_audio(path, render_digest="sha256:" + "0" * 64)


@pytest.mark.skipif(shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None, reason="ffmpeg and ffprobe required")
def test_analysis_bounds_gap_sidecar(tmp_path):
    path = tmp_path / "gaps.wav"
    digest = _stereo_wav(path, [(0.0, 0.0), (0.5, 0.5)] * 100, rate=100)
    result = analyze_audio(path, render_digest=digest, settings={"threshold": 0.05, "min_gap_seconds": 0, "max_gap_count": 1, "levels": [2]})
    assert len(result["quiet_gaps"]) == 1
    assert result["coverage"]["quiet_gaps"] == "truncated"
    assert result["coverage"]["state"] == "partial"
