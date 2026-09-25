"""Resolve v2 timeline members onto the delivery AV clock.

This is a decoded-domain input to H3 and to exact restoration.  Empty spans are
neutral canvas, never claimed as protected source.  Verification renders it again
from the declared members instead of trusting composition's output bytes.
"""

from __future__ import annotations

import hashlib
import mmap
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping


class BaselineError(ValueError):
    pass


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render_timeline_baseline(
    preparation: Mapping[str, Any], artifact: Any, destination: Path,
    *, native_frames: int | None = None, primary_source: Path | None = None,
) -> tuple[Path, Path]:
    """Write raw RGBA/PCM baseline files from exact ranges and placements."""

    # Reuse the strict decoder/format boundary, while resolving every occurrence
    # from the request independently of any composed candidate.
    from .compose import _decode_exact_audio, _decode_exact_video, _exact_clock

    request = preparation.get("request")
    identity = artifact.mapping.get("baseline_identity")
    if not isinstance(request, Mapping) or not isinstance(identity, Mapping):
        raise BaselineError("timeline baseline request or identity is missing")
    declared = {str(item.get("occurrence_id")): item for item in request.get("media", []) if isinstance(item, Mapping) and item.get("role") == "timeline"}
    members = identity.get("members", [])
    if not isinstance(members, list) or set(declared) != {str(member.get("occurrence_id")) for member in members if isinstance(member, Mapping)}:
        raise BaselineError("baseline members do not match the normalized timeline")
    records = {str(row.get("asset")): row for row in preparation.get("assets", []) if isinstance(row, Mapping)}
    fps, sample_rate = _exact_clock(artifact)
    if fps != 24 or sample_rate != 48000:
        raise BaselineError("H3 baseline requires 24 fps and 48 kHz")
    delivery_frames, height, width = artifact.video_shape
    channels, delivery_samples = artifact.audio_shape
    target_frames = native_frames or delivery_frames
    if target_frames < delivery_frames:
        raise BaselineError("native baseline is shorter than delivery")
    target_samples = max(delivery_samples, target_frames * sample_rate // 24)
    destination.mkdir(parents=True, exist_ok=True)
    video_path = destination / "baseline.rgba"
    audio_path = destination / "baseline.s32le"
    frame_bytes = height * width * 4
    sample_bytes = channels * 4
    with video_path.open("wb") as stream:
        stream.truncate(target_frames * frame_bytes)
    with audio_path.open("wb") as stream:
        stream.truncate(target_samples * sample_bytes)
    video_ranges: list[tuple[int, int]] = []
    audio_ranges: dict[str, list[tuple[int, int]]] = {"video": [], "audio": []}
    with video_path.open("r+b") as video_stream, audio_path.open("r+b") as audio_stream:
        video_map = mmap.mmap(video_stream.fileno(), 0)
        audio_map = mmap.mmap(audio_stream.fileno(), 0)
        try:
            # Standalone audio is an explicit override of a video soundtrack.
            # Within each modality, placements must remain unambiguous.
            ordered = sorted(enumerate(members), key=lambda pair: pair[1].get("modality") == "audio")
            for index, member in ordered:
                occurrence = str(member["occurrence_id"])
                item = declared[occurrence]
                for field in ("asset", "modality", "resolved_range", "resolved_at"):
                    if member.get(field) != item.get(field):
                        raise BaselineError(f"baseline {occurrence!r} disagrees with the normalized request")
                asset = str(member["asset"])
                row = records.get(asset)
                if row is None or not isinstance(row.get("path"), str):
                    raise BaselineError(f"baseline asset {asset!r} is unavailable")
                path = Path(row["path"]).expanduser().resolve()
                if primary_source is not None and occurrence == identity.get("primary_occurrence"):
                    path = primary_source.resolve()
                if not path.is_file() or _hash(path) != member.get("sha256"):
                    raise BaselineError(f"baseline asset {asset!r} failed identity check")
                start, end = item["resolved_range"]
                at = item["resolved_at"]["value"]
                if item["modality"] == "video":
                    count = end - start
                    if not (0 <= at < delivery_frames and 0 < count <= delivery_frames - at):
                        raise BaselineError(f"video placement for {occurrence!r} exceeds delivery")
                    if any(at < prior_end and prior_start < at + count for prior_start, prior_end in video_ranges):
                        raise BaselineError("video timeline members overlap")
                    video_ranges.append((at, at + count))
                    decoded = destination / f"video-{index}.rgba"
                    _decode_exact_video(path, decoded, frames=count, width=width, height=height, fps=fps, start_frame=start)
                    with decoded.open("rb") as stream:
                        video_map[at * frame_bytes:(at + count) * frame_bytes] = stream.read()
                    source_sample = start * sample_rate // 24
                    placed_sample = at * sample_rate // 24
                    audio_count = count * sample_rate // 24
                elif item["modality"] == "audio":
                    source_sample = start
                    placed_sample = at * sample_rate // 24
                    audio_count = end - start
                else:
                    continue
                if placed_sample < 0 or audio_count < 1 or placed_sample + audio_count > delivery_samples:
                    raise BaselineError(f"audio placement for {occurrence!r} exceeds delivery")
                track_ranges = audio_ranges[item["modality"]]
                if any(placed_sample < prior_end and prior_start < placed_sample + audio_count for prior_start, prior_end in track_ranges):
                    raise BaselineError("audio timeline members overlap")
                track_ranges.append((placed_sample, placed_sample + audio_count))
                decoded = destination / f"audio-{index}.s32le"
                _decode_exact_audio(path, decoded, samples=audio_count, sample_rate=sample_rate, channels=channels, start_sample=source_sample)
                with decoded.open("rb") as stream:
                    audio_map[placed_sample * sample_bytes:(placed_sample + audio_count) * sample_bytes] = stream.read()
        finally:
            video_map.close()
            audio_map.close()
    return video_path, audio_path


def encode_native_baseline(video: Path, audio: Path, destination: Path, *, frames: int, width: int, height: int) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise BaselineError("ffmpeg is required for the H3 source baseline")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pixel_format", "rgba", "-video_size", f"{width}x{height}", "-framerate", "24", "-i", str(video),
        "-f", "s32le", "-ar", "48000", "-ac", "2", "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-frames:v", str(frames),
        "-c:v", "ffv1", "-pix_fmt", "bgra", "-c:a", "pcm_s32le", str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise BaselineError(f"could not encode the H3 source baseline: {exc}") from exc
    return destination
