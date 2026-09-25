"""Deterministic H3 composition and preservation-evidence boundary."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
import zipfile
from array import array
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping

from .timing import ContinuationTiming, ContinuationTimingError, plan_from_preparation


class CompositionError(ValueError):
    """A generated candidate cannot be safely composed."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe(path: Path) -> dict[str, Any] | None:
    """Return ffprobe data, or ``None`` for a non-media fixture."""

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        return None
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-count_frames",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        value = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _stream_types(probe: Mapping[str, Any] | None) -> set[str]:
    streams = probe.get("streams") if isinstance(probe, Mapping) else None
    if not isinstance(streams, list):
        return set()
    return {
        str(stream.get("codec_type"))
        for stream in streams
        if isinstance(stream, Mapping) and isinstance(stream.get("codec_type"), str)
    }


def _video_dimensions(probe: Mapping[str, Any] | None, *, role: str) -> tuple[int, int]:
    videos = _streams(probe, "video")
    if len(videos) != 1:
        raise CompositionError(f"{role} media must contain exactly one video stream")
    try:
        width = int(videos[0]["width"])
        height = int(videos[0]["height"])
    except (KeyError, TypeError, ValueError):
        raise CompositionError(f"{role} video stream has no usable dimensions") from None
    if width <= 0 or height <= 0:
        raise CompositionError(f"{role} video stream has no usable dimensions")
    return width, height


def _streams(probe: Mapping[str, Any] | None, stream_type: str) -> list[Mapping[str, Any]]:
    values = probe.get("streams") if isinstance(probe, Mapping) else None
    if not isinstance(values, list):
        return []
    return [
        item
        for item in values
        if isinstance(item, Mapping) and item.get("codec_type") == stream_type
    ]


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _duration(probe: Mapping[str, Any], stream: Mapping[str, Any]) -> float | None:
    direct = _number(stream.get("duration"))
    if direct is not None:
        return direct
    fmt = probe.get("format")
    return _number(fmt.get("duration")) if isinstance(fmt, Mapping) else None


def _video_coverage(path: Path) -> dict[str, Any]:
    probe = _probe(path)
    video = _streams(probe, "video")
    if probe is None or len(video) != 1:
        raise CompositionError("generated/candidate media must contain exactly one video stream")
    stream = video[0]
    rate_text = stream.get("avg_frame_rate") or stream.get("r_frame_rate")
    try:
        rate = Fraction(str(rate_text))
    except (ValueError, ZeroDivisionError):
        raise CompositionError("video stream has no usable frame rate") from None
    if rate <= 0:
        raise CompositionError("video stream has no usable frame rate")
    raw_frames = stream.get("nb_read_frames") or stream.get("nb_frames")
    try:
        frames = int(raw_frames)
    except (TypeError, ValueError):
        observed_duration = _duration(probe, stream)
        if observed_duration is None:
            raise CompositionError("video stream has no measurable frame coverage") from None
        frames = round(observed_duration * float(rate))
    if frames <= 0:
        raise CompositionError("video stream contains no frames")
    return {
        "path": str(path),
        "frames": frames,
        "fps": float(rate),
        "duration": frames / float(rate),
        "stream_count": 1,
    }


def _audio_coverage(path: Path) -> dict[str, Any]:
    probe = _probe(path)
    audio = _streams(probe, "audio")
    if probe is None or len(audio) != 1:
        raise CompositionError("generated/candidate media must contain exactly one audio stream")
    observed_duration = _duration(probe, audio[0])
    if observed_duration is None or observed_duration <= 0:
        raise CompositionError("audio stream has no measurable duration")
    return {
        "path": str(path),
        "duration": observed_duration,
        "sample_rate": int(audio[0]["sample_rate"]) if str(audio[0].get("sample_rate", "")).isdigit() else None,
        "stream_count": 1,
    }


def _continuation_timing(preparation: Mapping[str, Any]) -> ContinuationTiming | None:
    try:
        return plan_from_preparation(preparation)
    except ContinuationTimingError as exc:
        raise CompositionError(str(exc)) from exc


def _validate_generated_coverage(
    *,
    preparation: Mapping[str, Any],
    generated_video: Path,
    generated_audio: Path | None,
) -> dict[str, Any]:
    """Reject a no-op/short H3 result before attempting final composition."""

    if preparation.get("request", {}).get("operation") == "generate":
        from .generation import generation_timing
        plan = generation_timing(preparation["request"]["output"]["duration"])
        video = _video_coverage(generated_video)
        audio = _audio_coverage(generated_audio or generated_video)
        if video["fps"] != plan["fps"] or video["frames"] != plan["raw_frames"]:
            raise CompositionError("H3 generation frame coverage does not match the compiled plan")
        if abs(audio["duration"] - plan["raw_frames"] / plan["fps"]) > 1 / plan["fps"]:
            raise CompositionError("H3 generation audio does not cover the compiled timeline")
        return {"video": video, "audio": audio, "timing": plan}
    timing = _continuation_timing(preparation)
    if timing is None:
        return {}
    video = _video_coverage(generated_video)
    audio = _audio_coverage(generated_audio or generated_video)
    if abs(video["fps"] - timing.fps) > 1e-6:
        raise CompositionError(f"H3 continuation output must be {timing.fps} fps")
    if video["frames"] <= timing.source_frames:
        raise CompositionError(
            "H3 continuation produced no net new frames "
            f"({video['frames']} observed, {timing.source_frames} source)"
        )
    if video["frames"] != timing.expected_graph_output_frames:
        raise CompositionError(
            "H3 continuation frame coverage does not match the compiled raw/context plan: "
            f"observed {video['frames']}, expected {timing.expected_graph_output_frames}"
        )
    tolerance = 1.0 / timing.fps
    if abs(audio["duration"] - timing.expected_graph_output_duration) > tolerance:
        raise CompositionError(
            "H3 continuation audio does not cover the compiled raw/context timeline: "
            f"observed {audio['duration']:.6f}s, expected {timing.expected_graph_output_duration:.6f}s"
        )
    return {"video": video, "audio": audio, "timing": timing.to_dict()}


def _validate_candidate_coverage(
    *, preparation: Mapping[str, Any], candidate: Path
) -> dict[str, Any]:
    """Prove final duration and AV stream coverage from delivered bytes."""

    video = _video_coverage(candidate)
    audio = _audio_coverage(candidate)
    timing = _continuation_timing(preparation)
    if preparation.get("request", {}).get("operation") == "generate":
        from .generation import generation_timing
        plan = generation_timing(preparation["request"]["output"]["duration"])
        if video["fps"] != plan["fps"] or video["frames"] != plan["requested_frames"]:
            raise CompositionError("H3 generation candidate does not match requested frame coverage")
        requested_duration = plan["duration"]
    elif timing is not None:
        if abs(video["fps"] - timing.fps) > 1e-6:
            raise CompositionError(f"composed H3 candidate must be {timing.fps} fps")
        if video["frames"] != timing.requested_output_frames:
            raise CompositionError(
                "composed H3 candidate does not match requested frame coverage: "
                f"observed {video['frames']}, expected {timing.requested_output_frames}"
            )
        requested_duration = timing.requested_output_duration
    else:
        schedule = preparation.get("mask_schedule")
        if not isinstance(schedule, Mapping):
            raise CompositionError("preparation is missing mask_schedule")
        requested_duration = float(schedule["duration"])
        tolerance = max(1.0 / video["fps"], 0.05)
        if abs(video["duration"] - requested_duration) > tolerance:
            raise CompositionError(
                "composed candidate video does not cover output.duration: "
                f"observed {video['duration']:.6f}s, expected {requested_duration:.6f}s"
            )
    if abs(audio["duration"] - requested_duration) > max(1.0 / video["fps"], 0.05):
        raise CompositionError(
            "composed candidate audio does not cover output.duration: "
            f"observed {audio['duration']:.6f}s, expected {requested_duration:.6f}s"
        )
    return {
        "requested_duration": requested_duration,
        "video": video,
        "audio": audio,
        "status": "covered",
    }


def _source_offset(preparation: Mapping[str, Any]) -> float:
    request = preparation.get("request")
    source = request.get("source") if isinstance(request, Mapping) else None
    value = source.get("range") if isinstance(source, Mapping) else None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0])
    return 0.0


def _generated_at(intervals: list[list[float]], start: float, end: float) -> bool:
    midpoint = (start + end) / 2.0
    return any(float(item[0]) <= midpoint < float(item[1]) for item in intervals)


def _segments(duration: float, generated: list[list[float]]) -> list[tuple[float, float, bool]]:
    boundaries = {0.0, float(duration)}
    for interval in generated:
        boundaries.add(max(0.0, min(float(duration), float(interval[0]))))
        boundaries.add(max(0.0, min(float(duration), float(interval[1]))))
    ordered = sorted(boundaries)
    return [
        (start, end, _generated_at(generated, start, end))
        for start, end in zip(ordered, ordered[1:])
        if end > start
    ]


@contextmanager
def _generated_inputs(path: Path):
    """Yield verified generated video/audio paths and their role manifest."""

    if path.suffix.lower() != ".zip":
        yield path, None, {}
        return
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise CompositionError("generated audiovisual bundle is not a readable ZIP") from exc
    with archive:
        names = archive.namelist()
        if names.count("manifest.json") != 1 or len(names) != len(set(names)):
            raise CompositionError("generated audiovisual bundle has an invalid member inventory")
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CompositionError("generated audiovisual bundle manifest is unreadable") from exc
        if not isinstance(manifest, Mapping) or manifest.get("schema_version") != 1 or manifest.get("kind") != "h3_av_generated_av":
            raise CompositionError("generated audiovisual bundle has an unsupported contract")
        records = manifest.get("outputs")
        if not isinstance(records, list) or {item.get("role") for item in records if isinstance(item, Mapping)} != {"video", "audio"} or len(records) != 2:
            raise CompositionError("generated audiovisual bundle must declare one video and one audio output")
        parsed: dict[str, Mapping[str, Any]] = {}
        for record in records:
            if not isinstance(record, Mapping):
                raise CompositionError("generated audiovisual output record is malformed")
            role = record.get("role")
            member = record.get("member")
            digest = record.get("sha256")
            size = record.get("size")
            member_path = PurePosixPath(str(member))
            if (
                role not in {"video", "audio"}
                or role in parsed
                or not isinstance(member, str)
                or member_path.is_absolute()
                or ".." in member_path.parts
                or not member_path.name
                or member_path.as_posix() != member
                or not isinstance(digest, str)
                or len(digest) != 64
                or not isinstance(size, int)
                or size < 0
            ):
                raise CompositionError("generated audiovisual output record is invalid")
            if member not in names or member == "manifest.json":
                raise CompositionError(f"generated audiovisual member {member!r} is missing")
            data = archive.read(member)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise CompositionError(f"generated audiovisual member {member!r} failed integrity validation")
            parsed[str(role)] = record
        declared_members = {"manifest.json", *(str(record["member"]) for record in records)}
        if set(names) != declared_members:
            raise CompositionError("generated audiovisual bundle contains undeclared members")
        with tempfile.TemporaryDirectory(prefix="h3-av-generated-") as raw_root:
            root = Path(raw_root)
            paths: dict[str, Path] = {}
            for role in ("video", "audio"):
                record = parsed[role]
                member = str(record["member"])
                target = root / PurePosixPath(member).name
                target.write_bytes(archive.read(member))
                paths[role] = target
            yield paths["video"], paths["audio"], {"outputs": [dict(record) for record in records]}


def _compose_media(
    *,
    source: Path,
    generated: Path,
    generated_audio_path: Path | None = None,
    destination: Path,
    duration: float,
    generated_video: list[list[float]],
    generated_audio: list[list[float]],
    source_offset: float,
) -> dict[str, Any]:
    """Compose source and generated streams into a lossless MKV candidate."""

    ffmpeg = shutil.which("ffmpeg")
    source_probe = _probe(source)
    generated_probe = _probe(generated)
    generated_audio_probe = _probe(generated_audio_path) if generated_audio_path is not None else generated_probe
    if ffmpeg is None or source_probe is None or generated_probe is None or generated_audio_probe is None:
        raise CompositionError("media composition requires ffmpeg and decodable source/video/audio files")
    source_types = _stream_types(source_probe)
    generated_types = _stream_types(generated_probe)
    generated_audio_types = _stream_types(generated_audio_probe)
    output_width, output_height = _video_dimensions(source_probe, role="source")
    video_segments = _segments(duration, generated_video)
    audio_segments = _segments(duration, generated_audio)
    for stream_type, segments in (("video", video_segments), ("audio", audio_segments)):
        for _start, _end, use_generated in segments:
            available = (
                (generated_types if stream_type == "video" else generated_audio_types)
                if use_generated
                else source_types
            )
            if stream_type not in available:
                raise CompositionError(
                    f"{stream_type} stream is missing from the {'generated candidate' if use_generated else 'source baseline'}"
                )

    filters: list[str] = []
    maps: list[str] = []
    input_paths = [source, generated]
    if generated_audio_path is not None:
        input_paths.append(generated_audio_path)
    for stream_type, segments, label in (("video", video_segments, "v"), ("audio", audio_segments, "a")):
        pieces: list[str] = []
        for index, (start, end, use_generated) in enumerate(segments):
            input_index = (
                0
                if not use_generated
                else (1 if stream_type == "video" or generated_audio_path is None else 2)
            )
            trim_start = start if use_generated else source_offset + start
            trim_end = end if use_generated else source_offset + end
            piece = f"{label}{index}"
            if stream_type == "video":
                # H3 intentionally runs at its working resolution.  The source
                # timeline remains authoritative, so normalize every segment to
                # its dimensions before concat; otherwise ffmpeg rejects a
                # perfectly valid low-resolution generated continuation.
                filters.append(
                    f"[{input_index}:v:0]trim=start={trim_start}:end={trim_end},"
                    f"scale={output_width}:{output_height}:flags=lanczos,setsar=1,"
                    f"setpts=PTS-STARTPTS[{piece}]"
                )
            else:
                filters.append(
                    f"[{input_index}:a:0]atrim=start={trim_start}:end={trim_end},asetpts=PTS-STARTPTS[{piece}]"
                )
            pieces.append(f"[{piece}]")
        output_label = f"{label}out"
        if len(pieces) == 1:
            filters.append(f"{pieces[0]}null[{output_label}]")
        else:
            filters.append(
                "".join(pieces)
                + f"concat=n={len(pieces)}:v={'1' if stream_type == 'video' else '0'}:a={'1' if stream_type == 'audio' else '0'}[{output_label}]"
            )
        maps.append(f"[{output_label}]")

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        *sum((["-i", str(path)] for path in input_paths), []),
        "-filter_complex", ";".join(filters),
        "-map", maps[0], "-map", maps[1], "-map_metadata", "-1",
        "-c:v", "libx264", "-qp", "0", "-preset", "medium",
        "-c:a", "pcm_s16le", "-t", str(duration), str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise CompositionError(f"ffmpeg composition failed: {detail[-500:]}") from exc
    return {
        "method": "ffmpeg-stream-compose-v1",
        "container": "matroska",
        "video_segments": [
            {"during": [start, end], "source": "generated" if use_generated else "source"}
            for start, end, use_generated in video_segments
        ],
        "audio_segments": [
            {"during": [start, end], "source": "generated" if use_generated else "source"}
            for start, end, use_generated in audio_segments
        ],
    }


def _mux_generated(video: Path, audio: Path, destination: Path) -> None:
    """Create one candidate container without dropping LanPaint's audio role."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None or _probe(video) is None or _probe(audio) is None:
        raise CompositionError("paired audiovisual composition requires ffmpeg and decodable video/audio files")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(video), "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0", "-map_metadata", "-1",
        "-c:v", "libx264", "-qp", "0", "-preset", "medium",
        "-c:a", "pcm_s16le", str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise CompositionError(f"ffmpeg audiovisual mux failed: {detail[-500:]}") from exc


def _decode_audio_samples(path: Path, start: float, duration: float) -> tuple[list[int], int]:
    """Decode one interval to a stable comparison format."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise CompositionError("ffmpeg is required for protected audio evidence")
    if duration <= 0:
        raise CompositionError("protected audio interval must be positive")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-ss", str(start), "-t", str(duration), "-map", "0:a:0", "-vn",
        "-ar", "48000", "-ac", "2", "-f", "s16le", "-",
    ]
    try:
        completed = subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", b"") or str(exc).encode()
        raise CompositionError(f"could not decode protected audio samples: {detail[-500:]!r}") from exc
    if not completed.stdout or len(completed.stdout) % 2:
        raise CompositionError("protected audio interval produced no complete PCM samples")
    values = array("h")
    values.frombytes(completed.stdout)
    if sys.byteorder != "little":
        values.byteswap()
    decoded = list(values)
    return decoded, len(decoded)


def _audio_witness(
    *, source: Path, candidate: Path, source_start: float, candidate_start: float, duration: float
) -> dict[str, float | int]:
    """Compare decoded protected audio without requiring codec-identical PCM."""

    source_values, source_count = _decode_audio_samples(source, source_start, duration)
    candidate_values, candidate_count = _decode_audio_samples(candidate, candidate_start, duration)
    source_frames = len(source_values) // 2
    candidate_frames = len(candidate_values) // 2
    frame_count = min(source_frames, candidate_frames)
    if frame_count <= 0:
        raise CompositionError("protected audio interval produced no complete stereo frames")
    if frame_count < max(source_frames, candidate_frames) * 0.98:
        raise CompositionError("protected audio interval has insufficient sample overlap")

    source_mono = [
        (source_values[offset] + source_values[offset + 1]) / 2.0
        for offset in range(0, frame_count * 2, 2)
    ]
    candidate_mono = [
        (candidate_values[offset] + candidate_values[offset + 1]) / 2.0
        for offset in range(0, frame_count * 2, 2)
    ]
    source_mean = sum(source_mono) / frame_count
    candidate_mean = sum(candidate_mono) / frame_count
    source_energy = sum((value - source_mean) ** 2 for value in source_mono)
    candidate_energy = sum((value - candidate_mean) ** 2 for value in candidate_mono)
    if source_energy <= 1.0 or candidate_energy <= 1.0:
        similarity = 1.0 if max(abs(value) for value in source_mono) < 8 and max(abs(value) for value in candidate_mono) < 8 else 0.0
    else:
        covariance = sum(
            (source_mono[index] - source_mean) * (candidate_mono[index] - candidate_mean)
            for index in range(frame_count)
        )
        similarity = covariance / math.sqrt(source_energy * candidate_energy)
    return {
        "similarity": float(similarity),
        "source_sample_count": source_count,
        "candidate_sample_count": candidate_count,
        "sample_count": min(source_count, candidate_count),
    }


def _sample_digest(path: Path, stream_type: str, start: float, duration: float) -> tuple[str, int]:
    """Hash decoded video frames or PCM samples for one protected interval."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise CompositionError("ffmpeg is required for protected-sample evidence")
    if duration <= 0:
        raise CompositionError("protected sample interval must be positive")
    if stream_type == "video":
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
            "-ss", str(start), "-t", str(duration), "-map", "0:v:0", "-an", "-f", "framemd5", "-",
        ]
    elif stream_type == "audio":
        values, sample_count = _decode_audio_samples(path, start, duration)
        if not values:
            raise CompositionError("protected audio interval produced no samples")
        # This digest remains useful diagnostic evidence, but is not the
        # acceptance criterion because codec/container plumbing can change a
        # few decoded PCM values without changing the protected content.
        payload = json.dumps(values, separators=(",", ":")).encode("ascii")
        return hashlib.sha256(payload).hexdigest(), sample_count
    else:
        raise CompositionError(f"unsupported protected sample stream: {stream_type}")
    try:
        completed = subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", b"") or str(exc).encode()
        raise CompositionError(f"could not decode protected {stream_type} samples: {detail[-500:]!r}") from exc
    if stream_type == "video":
        hashes = [
            line.rsplit(b",", 1)[-1].strip()
            for line in completed.stdout.splitlines()
            if line and not line.startswith(b"#") and b"," in line
        ]
        if not hashes:
            raise CompositionError(f"protected {stream_type} interval produced no samples")
        return hashlib.sha256(b"\n".join(hashes)).hexdigest(), len(hashes)
    raise CompositionError(f"unsupported protected sample stream: {stream_type}")


def _auto_sample_evidence(
    *, source: Path, candidate: Path, schedule: Mapping[str, Any], source_offset: float
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"video": [], "audio": []}
    for stream_type in ("video", "audio"):
        for interval in schedule[stream_type]["protected_intervals"]:
            start, end = float(interval[0]), float(interval[1])
            source_hash, sample_count = _sample_digest(source, stream_type, source_offset + start, end - start)
            candidate_hash, candidate_count = _sample_digest(candidate, stream_type, start, end - start)
            entry: dict[str, Any] = {
                "interval": [start, end],
                "source_sha256": source_hash,
                "candidate_sha256": candidate_hash,
                "sample_count": min(sample_count, candidate_count),
                "method": "ffmpeg-decoded-samples-v1",
            }
            if stream_type == "audio":
                entry.update(
                    _audio_witness(
                        source=source,
                        candidate=candidate,
                        source_start=source_offset + start,
                        candidate_start=start,
                        duration=end - start,
                    )
                )
                entry["method"] = "ffmpeg-decoded-audio-similarity-v1"
            result[stream_type].append(entry)
    return result


def compose_candidate(
    *,
    preparation: Mapping[str, Any],
    generated: str | Path,
    source: str | Path | None = None,
    baseline: str | Path | None = None,
    out_dir: str | Path,
    preservation_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose one candidate and publish custody plus preservation evidence."""

    generated_path = Path(generated).expanduser().resolve()
    if not generated_path.is_file():
        raise CompositionError(f"generated candidate does not exist: {generated_path}")
    schedule = preparation.get("mask_schedule")
    if not isinstance(schedule, Mapping):
        raise CompositionError("preparation is missing mask_schedule")
    if preparation.get("status") == "requires_resolution":
        raise CompositionError("cannot compose a request whose mask schedule requires resolution")
    if source is not None and baseline is not None:
        raise CompositionError("source and baseline are mutually exclusive")
    if source is None:
        source = baseline
    source_path: Path | None = None
    if source is not None:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise CompositionError(f"source does not exist: {source_path}")
    protected = any(schedule[domain]["protected_intervals"] for domain in ("video", "audio"))
    if protected and source_path is None:
        raise CompositionError("protected composition requires an authoritative source baseline")

    destination = Path(out_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    with _generated_inputs(generated_path) as (generated_video, generated_audio, generated_manifest):
        generated_coverage = _validate_generated_coverage(
            preparation=preparation,
            generated_video=generated_video,
            generated_audio=generated_audio,
        )
        composition_method: dict[str, Any] = {"method": "candidate-custody-v1"}
        candidate = destination / generated_video.name
        if preparation.get("request", {}).get("operation") == "generate":
            plan = generated_coverage["timing"]
            candidate = destination / "candidate.mp4"
            command = ["ffmpeg", "-v", "error", "-y", "-i", str(generated_video),
                       "-map", "0:v:0", "-map", "0:a:0",
                       "-vf", f"trim=end_frame={plan['requested_frames']},setpts=N/(24*TB)",
                       "-af", f"atrim=end={plan['duration']},asetpts=PTS-STARTPTS",
                       "-r", "24", "-fps_mode", "cfr",
                       "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
                       "-c:a", "aac", str(candidate)]
            subprocess.run(command, check=True, capture_output=True)
            composition_method = {"method": "h3-generation-tail-trim-v1", **plan}
        elif source_path is not None and protected and any(
            schedule[domain]["generated_intervals"] for domain in ("video", "audio")
        ):
            if _probe(source_path) is not None and _probe(generated_video) is not None:
                candidate = destination / f"{generated_video.stem}.composed.mkv"
                composition_method = _compose_media(
                    source=source_path,
                    generated=generated_video,
                    generated_audio_path=generated_audio,
                    destination=candidate,
                    duration=float(schedule["duration"]),
                    generated_video=list(schedule["video"]["generated_intervals"]),
                    generated_audio=list(schedule["audio"]["generated_intervals"]),
                    source_offset=_source_offset(preparation),
                )
            else:
                # Non-media fixtures remain composable for legacy unit coverage,
                # but verification will not accept interval-only preservation.
                shutil.copy2(generated_video, candidate)
        elif generated_audio is not None:
            # A paired LanPaint result must never silently discard its audio
            # stream, even when no protected source interval needs splicing.
            candidate = destination / f"{generated_video.stem}.muxed.mkv"
            _mux_generated(generated_video, generated_audio, candidate)
        elif candidate.resolve() != generated_video:
            shutil.copy2(generated_video, candidate)

        candidate_coverage: dict[str, Any] = {}
        if _probe(candidate) is not None:
            candidate_coverage = _validate_candidate_coverage(
                preparation=preparation,
                candidate=candidate,
            )
        elif _continuation_timing(preparation) is not None:
            raise CompositionError("H3 continuation result is not decodable audiovisual media")

        evidence = dict(preservation_evidence or {})
        if source_path is not None and protected and _probe(source_path) is not None and _probe(candidate) is not None:
            try:
                auto = _auto_sample_evidence(
                    source=source_path,
                    candidate=candidate,
                    schedule=schedule,
                    source_offset=_source_offset(preparation),
                )
            except CompositionError:
                auto = {"video": [], "audio": []}
            if any(auto.values()):
                evidence["protected_samples"] = auto

        provenance = preparation.get("provenance")
        generated_types = _stream_types(_probe(generated_video))
        output_roles = (
            ["video", "audio"]
            if generated_audio is not None
            else (["muxed_av"] if {"video", "audio"}.issubset(generated_types) else ["video"])
        )
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "kind": "h3_av_composition",
            "request_digest": preparation.get("request_digest"),
            "schedule_digest": schedule.get("digest"),
            "candidate": {"path": str(candidate), "sha256": _sha256(candidate), "size": candidate.stat().st_size},
            "source": None if source_path is None else {"path": str(source_path), "sha256": _sha256(source_path), "size": source_path.stat().st_size},
            "generated_outputs": generated_manifest.get("outputs", []),
            "changed_permissions": {"video": schedule["video"]["generated_intervals"], "audio": schedule["audio"]["generated_intervals"]},
            "protected_permissions": {"video": schedule["video"]["protected_intervals"], "audio": schedule["audio"]["protected_intervals"]},
            "preservation_evidence": evidence,
            "composition": {**composition_method, "output_roles": output_roles},
            "coverage": {
                "generated": generated_coverage,
                "candidate": candidate_coverage,
            },
            "provenance": dict(provenance) if isinstance(provenance, Mapping) else {},
            "status": "composed",
        }
        manifest_path = destination / "composition-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest


__all__ = ["CompositionError", "compose_candidate", "_probe", "_sample_digest"]
