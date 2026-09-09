"""Bounded, deterministic audio facts for a verified rendered media file.

This module deliberately has no timeline or runtime dependencies.  Admission is
represented by the caller supplying the render digest; ffprobe/ffmpeg are only
ever pointed at that already-admitted absolute file.  PCM is consumed in small
chunks and reduced directly into bounded integer-sample bins.
"""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
from array import array
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

ANALYSIS_VERSION = "astrid.audio-analysis.v1"
DEFAULT_SETTINGS: dict[str, Any] = {
    "threshold": 0.01,
    "min_gap_seconds": 0.25,
    "levels": (256, 1024, 4096),
    "max_duration_seconds": 3600.0,
    "max_samples": 48_000 * 3600,
    "max_gap_count": 10_000,
    "chunk_frames": 4096,
}


class AudioAnalysisError(ValueError):
    """The admitted media cannot produce a trustworthy bounded analysis."""


def _digest(value: object) -> str:
    raw = str(value or "").removeprefix("sha256:")
    if len(raw) != 64 or any(c not in "0123456789abcdef" for c in raw):
        raise AudioAnalysisError("render_digest must be a sha256 digest")
    return "sha256:" + raw


def _rational(value: object, *, label: str, positive: bool = False) -> Fraction:
    try:
        result = Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise AudioAnalysisError(f"{label} must be rational") from exc
    if not math.isfinite(float(result)) or (positive and result <= 0):
        raise AudioAnalysisError(f"{label} is invalid")
    return result


def _ratio(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def _seconds(sample: int, sample_rate: int, origin: Fraction) -> Fraction:
    return origin + Fraction(sample, sample_rate)


def _safe_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    result = dict(DEFAULT_SETTINGS)
    if settings:
        result.update(settings)
    threshold = result.get("threshold", 0.01)
    if "threshold_db" in result:
        threshold = 10 ** (float(result["threshold_db"]) / 20.0)
        result["threshold"] = threshold
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= float(threshold) <= 1:
        raise AudioAnalysisError("threshold must be between 0 and 1")
    result["threshold"] = float(threshold)
    minimum = result.get("min_gap_seconds", 0.25)
    if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or float(minimum) < 0:
        raise AudioAnalysisError("min_gap_seconds must be non-negative")
    result["min_gap_seconds"] = float(minimum)
    levels = result.get("levels", DEFAULT_SETTINGS["levels"])
    if not isinstance(levels, (list, tuple)) or not levels or any(type(x) is not int or x <= 0 for x in levels):
        raise AudioAnalysisError("levels must contain positive integer bin budgets")
    result["levels"] = tuple(sorted(set(levels)))
    for name in ("max_samples", "chunk_frames"):
        value = result.get(name)
        if type(value) is not int or value <= 0:
            raise AudioAnalysisError(f"{name} must be a positive integer")
    if type(result.get("max_gap_count")) is not int or result["max_gap_count"] <= 0:
        raise AudioAnalysisError("max_gap_count must be a positive integer")
    maximum_duration = result.get("max_duration_seconds")
    if isinstance(maximum_duration, bool) or not isinstance(maximum_duration, (int, float)) or float(maximum_duration) <= 0:
        raise AudioAnalysisError("max_duration_seconds must be positive")
    result["max_duration_seconds"] = float(maximum_duration)
    return result


def _run_json(command: Sequence[str], *, error: str) -> Mapping[str, Any]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise AudioAnalysisError(f"{error}: {result.stderr[-2000:]}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AudioAnalysisError(f"{error} returned invalid JSON") from exc
    if not isinstance(value, Mapping):
        raise AudioAnalysisError(f"{error} returned a non-object")
    return value


def _probe(path: Path, ffprobe: str) -> tuple[dict[str, Any] | None, Mapping[str, Any]]:
    document = _run_json(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        error="ffprobe failed",
    )
    streams = document.get("streams", [])
    if not isinstance(streams, list):
        raise AudioAnalysisError("ffprobe returned malformed streams")
    audio = next((stream for stream in streams if isinstance(stream, Mapping) and stream.get("codec_type") == "audio"), None)
    return (dict(audio) if isinstance(audio, Mapping) else None), document


def _origin(stream: Mapping[str, Any]) -> tuple[Fraction, str | None]:
    time_base = stream.get("time_base") or "1/1"
    base = _rational(time_base, label="audio time_base", positive=True)
    start_pts = stream.get("start_pts")
    if start_pts is not None:
        try:
            pts = int(start_pts)
        except (TypeError, ValueError) as exc:
            raise AudioAnalysisError("audio start_pts is invalid") from exc
        return pts * base, str(time_base)
    if stream.get("start_time") not in (None, "N/A"):
        return _rational(stream["start_time"], label="audio start_time"), str(time_base)
    return Fraction(0), str(time_base)


def _channel_names(channels: int, layout: object) -> list[str]:
    if isinstance(layout, str) and layout:
        known = [part for part in layout.replace("(", "").replace(")", "").split("+") if part]
        if len(known) == channels:
            return known
    return [f"channel_{index + 1}" for index in range(channels)]


def audio_analysis_identity(
    render_digest: str,
    stream: Mapping[str, Any] | None,
    settings: Mapping[str, Any] | None = None,
    *,
    status: str = "ok",
) -> str:
    """Return the cache/provenance identity for one render analysis."""
    admitted = _digest(render_digest)
    config = _safe_settings(settings)
    stream_identity = {
        "index": stream.get("index") if stream else None,
        "codec": stream.get("codec_name") if stream else None,
        "sample_rate": stream.get("sample_rate") if stream else None,
        "channels": stream.get("channels") if stream else None,
        "channel_layout": stream.get("channel_layout") if stream else None,
        "time_base": stream.get("time_base") if stream else None,
        "start_pts": stream.get("start_pts") if stream else None,
    }
    payload = {
        "version": ANALYSIS_VERSION,
        "status": status,
        "render_digest": admitted,
        "stream": stream_identity,
        "settings": {key: (list(value) if isinstance(value, tuple) else value) for key, value in config.items()},
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _empty_bin(index: int, start: int, end: int, channels: int) -> dict[str, Any]:
    return {
        "index": index,
        "start_sample": start,
        "end_sample": end,
        "sample_count": 0,
        "min": [1.0] * channels,
        "max": [-1.0] * channels,
        "peak": [0.0] * channels,
        "rms": [0.0] * channels,
        "_sum_squares": [0.0] * channels,
    }


def _finish_bin(item: dict[str, Any]) -> dict[str, Any]:
    count = item.pop("sample_count")
    sums = item.pop("_sum_squares")
    item["sample_count"] = count
    if count:
        item["rms"] = [math.sqrt(value / count) for value in sums]
    else:
        item["min"] = []
        item["max"] = []
        item["peak"] = []
        item["rms"] = []
    return item


def _bins(
    samples: Iterable[tuple[int, Sequence[float]]],
    *,
    channels: int,
    estimated_samples: int,
    level_budgets: Sequence[int],
) -> tuple[list[dict[str, Any]], dict[int, dict[int, dict[str, Any]]]]:
    widths = {budget: max(1, math.ceil(max(1, estimated_samples) / budget)) for budget in level_budgets}
    levels: dict[int, dict[int, dict[str, Any]]] = {budget: {} for budget in level_budgets}
    sample_count = 0
    for index, values in samples:
        sample_count = max(sample_count, index + 1)
        for budget, width in widths.items():
            bin_index = index // width
            current = levels[budget].setdefault(
                bin_index, _empty_bin(bin_index, bin_index * width, (bin_index + 1) * width, channels)
            )
            current["sample_count"] += 1
            for channel, value in enumerate(values):
                current["min"][channel] = min(current["min"][channel], value)
                current["max"][channel] = max(current["max"][channel], value)
                current["peak"][channel] = max(current["peak"][channel], abs(value))
                current["_sum_squares"][channel] += value * value
    result: list[dict[str, Any]] = []
    for budget in level_budgets:
        width = widths[budget]
        result.append({
            "id": f"level-{budget}",
            "target_bins": budget,
            "bin_width_samples": width,
            "bins": [_finish_bin(levels[budget][index]) for index in sorted(levels[budget])],
        })
    return result, levels


def _bin_state(channels: int, estimated_samples: int, level_budgets: Sequence[int]) -> tuple[dict[int, int], dict[int, dict[int, dict[str, Any]]]]:
    widths = {budget: max(1, math.ceil(max(1, estimated_samples) / budget)) for budget in level_budgets}
    return widths, {budget: {} for budget in level_budgets}


def _update_bin_state(
    levels: dict[int, dict[int, dict[str, Any]]], widths: Mapping[int, int],
    index: int, values: Sequence[float], channels: int,
) -> None:
    for budget, width in widths.items():
        bin_index = index // width
        current = levels[budget].setdefault(
            bin_index, _empty_bin(bin_index, bin_index * width, (bin_index + 1) * width, channels)
        )
        current["sample_count"] += 1
        for channel, value in enumerate(values):
            current["min"][channel] = min(current["min"][channel], value)
            current["max"][channel] = max(current["max"][channel], value)
            current["peak"][channel] = max(current["peak"][channel], abs(value))
            current["_sum_squares"][channel] += value * value


def _finish_bins(levels: dict[int, dict[int, dict[str, Any]]], widths: Mapping[int, int]) -> list[dict[str, Any]]:
    return [
        {
            "id": f"level-{budget}",
            "target_bins": budget,
            "bin_width_samples": widths[budget],
            "bins": [_finish_bin(levels[budget][index]) for index in sorted(levels[budget])],
        }
        for budget in widths
    ]


def _gap(start: int, end: int, *, sample_rate: int, origin: Fraction, threshold: float, aggregation: str) -> dict[str, Any]:
    start_time, end_time = _seconds(start, sample_rate, origin), _seconds(end, sample_rate, origin)
    return {
        "id": f"gap-{start}-{end}",
        "start_sample": start,
        "end_sample": end,
        "start": _ratio(start_time),
        "end": _ratio(end_time),
        "duration": _ratio(end_time - start_time),
        "duration_seconds": float(end_time - start_time),
        "threshold": threshold,
        "aggregation": aggregation,
        "measurement": "low_amplitude",
    }


def analyze_audio(
    path: str | Path,
    *,
    render_digest: str,
    settings: Mapping[str, Any] | None = None,
    ffprobe: str = "ffprobe",
    ffmpeg: str = "ffmpeg",
) -> dict[str, Any]:
    """Analyze the first audio stream of an admitted absolute render.

    The returned object is JSON-ready.  Every time range is half-open and all
    sample boundaries are integer indices; rational seconds retain the stream
    presentation origin without accumulating float offsets.
    """
    admitted = _digest(render_digest)
    candidate = Path(path)
    if not candidate.is_absolute():
        raise AudioAnalysisError("audio analysis requires the admitted absolute render path")
    try:
        media = candidate.resolve(strict=True)
    except OSError as exc:
        raise AudioAnalysisError("admitted render file is unavailable") from exc
    if not media.is_file():
        raise AudioAnalysisError("admitted render path is not a regular file")
    with media.open("rb") as stream:
        actual = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != admitted:
        raise AudioAnalysisError("render digest does not match the admitted file")
    config = _safe_settings(settings)
    stream_info, probe_document = _probe(media, ffprobe)
    analysis_identity = audio_analysis_identity(admitted, stream_info, config)
    base: dict[str, Any] = {
        "schema_version": 1,
        "analysis_version": ANALYSIS_VERSION,
        "analysis_identity": analysis_identity,
        "render_digest": admitted,
        "settings": {key: (list(value) if isinstance(value, tuple) else value) for key, value in config.items()},
        "probe": {"format_name": (probe_document.get("format") or {}).get("format_name") if isinstance(probe_document.get("format"), Mapping) else None},
    }
    if stream_info is None:
        base.update({
            "status": "no_audio_stream",
            "stream": None,
            "presentation_origin": {"seconds": [0, 1], "time_base": None},
            "waveform": {"levels": [], "sample_count": 0},
            "quiet_gaps": [],
            "coverage": {"state": "no_audio_stream", "sample_count": 0},
        })
        return base

    try:
        sample_rate = int(stream_info.get("sample_rate"))
        channels = int(stream_info.get("channels"))
    except (TypeError, ValueError) as exc:
        raise AudioAnalysisError("selected audio stream lacks sample rate/channels") from exc
    if sample_rate <= 0 or channels <= 0 or channels > 64:
        raise AudioAnalysisError("selected audio stream has invalid channel metadata")
    origin, time_base = _origin(stream_info)
    names = _channel_names(channels, stream_info.get("channel_layout"))
    stream_metadata = {
        "index": stream_info.get("index"),
        "codec": stream_info.get("codec_name"),
        "sample_rate": sample_rate,
        "channels": channels,
        "channel_layout": stream_info.get("channel_layout"),
        "channel_names": names,
        "channel_policy": "preserve channels; quiet gaps use max(abs(channel))",
    }
    try:
        duration_seconds = float(stream_info.get("duration") or 0)
    except (TypeError, ValueError):
        duration_seconds = 0
    estimated = max(1, int(duration_seconds * sample_rate)) if duration_seconds > 0 else config["max_samples"]
    estimated = min(estimated, config["max_samples"])
    command = [ffmpeg, "-v", "error", "-nostdin", "-copyts", "-i", str(media), "-map", f"0:{stream_info.get('index')}",
               "-vn", "-sn", "-dn", "-f", "f32le", "-acodec", "pcm_f32le"]
    if config["max_duration_seconds"]:
        command += ["-t", repr(config["max_duration_seconds"])]
    command.append("pipe:1")
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    sample_index = 0
    gap_start: int | None = None
    gaps: list[dict[str, Any]] = []
    gaps_truncated = False
    widths, level_bins = _bin_state(channels, estimated, config["levels"])
    try:
        assert process.stdout is not None
        while True:
            raw = process.stdout.read(config["chunk_frames"] * channels * 4)
            if not raw:
                break
            if len(raw) % (channels * 4):
                raise AudioAnalysisError("ffmpeg returned partial float PCM")
            values = array("f")
            values.frombytes(raw)
            for offset in range(0, len(values), channels):
                frame = tuple(float(values[offset + channel]) for channel in range(channels))
                if any(not math.isfinite(value) for value in frame):
                    raise AudioAnalysisError("ffmpeg returned non-finite float PCM")
                if sample_index >= config["max_samples"]:
                    raise AudioAnalysisError("audio analysis exceeds bounded sample limit")
                _update_bin_state(level_bins, widths, sample_index, frame, channels)
                loud = max(abs(value) for value in frame)
                if loud < config["threshold"]:
                    if gap_start is None:
                        gap_start = sample_index
                elif gap_start is not None:
                    if sample_index - gap_start >= math.ceil(config["min_gap_seconds"] * sample_rate):
                        if len(gaps) < config["max_gap_count"]:
                            gaps.append(_gap(gap_start, sample_index, sample_rate=sample_rate, origin=origin,
                                             threshold=config["threshold"], aggregation="max_channel_abs"))
                        else:
                            gaps_truncated = True
                    gap_start = None
                sample_index += 1
            # Reduce one chunk at a time; the decoder never creates a
            # whole-file PCM object and only bounded bin state survives.
        if gap_start is not None and sample_index - gap_start >= math.ceil(config["min_gap_seconds"] * sample_rate):
            if len(gaps) < config["max_gap_count"]:
                gaps.append(_gap(gap_start, sample_index, sample_rate=sample_rate, origin=origin,
                                 threshold=config["threshold"], aggregation="max_channel_abs"))
            else:
                gaps_truncated = True
        stderr = process.stderr.read().decode("utf-8", "replace") if process.stderr else ""
        returncode = process.wait()
        if returncode:
            raise AudioAnalysisError(f"ffmpeg audio decode failed: {stderr[-2000:]}")
    except Exception:
        process.kill()
        process.wait()
        raise
    levels = _finish_bins(level_bins, widths)
    base.update({
        "status": "ok",
        "stream": stream_metadata,
        "presentation_origin": {"seconds": _ratio(origin), "time_base": time_base},
        "waveform": {
            "sample_count": sample_index,
            "duration": _ratio(Fraction(sample_index, sample_rate)),
            "duration_seconds": sample_index / sample_rate,
            "sample_bounds": [0, sample_index],
            "levels": levels,
        },
        "quiet_gaps": gaps,
        "coverage": {"state": "complete" if not gaps_truncated else "partial",
                     "sample_count": sample_index, "sample_bounds": [0, sample_index],
                     "quiet_gaps": "complete" if not gaps_truncated else "truncated",
                     "max_gap_count": config["max_gap_count"]},
    })
    return base


# Descriptive aliases make the helper easy to discover without adding another
# owner or capability surface.
analyze_render_audio = analyze_audio
build_audio_analysis = analyze_audio

__all__ = [
    "ANALYSIS_VERSION", "AudioAnalysisError", "audio_analysis_identity",
    "analyze_audio", "analyze_render_audio", "build_audio_analysis",
]
