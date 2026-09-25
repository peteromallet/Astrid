"""Deterministic H3 composition and preservation-evidence boundary."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping

from .masks import PreparedAVMask, PreparedAVMaskError, load_prepared_av_mask
from .request import read_prepared_request


class CompositionError(ValueError):
    """A generated candidate cannot be safely composed."""


_EXACT_SCHEMA_VERSION = 1
_EXACT_VIDEO_PIXEL_FORMAT = "rgba"
_EXACT_AUDIO_SAMPLE_FORMAT = "s32le"
_EXACT_MASTER_CONTAINER = "matroska"
_EXACT_VIDEO_CODEC = "ffv1"
_EXACT_AUDIO_CODEC = "pcm_s32le"


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
            [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
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
def _generated_inputs(path: Path | None):
    """Yield verified generated video/audio paths and their role manifest."""

    if path is None:
        yield None, None, {}
        return
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


def _prepared_artifact(preparation: Mapping[str, Any]) -> PreparedAVMask | None:
    candidate = preparation.get("prepared_av_mask")
    if not isinstance(candidate, Mapping):
        for key in ("prepared_input", "prepared"):
            nested = preparation.get(key)
            if isinstance(nested, Mapping) and nested.get("kind") == "h3_prepared_av_mask":
                candidate = nested
                break
    if not isinstance(candidate, Mapping) or candidate.get("kind") != "h3_prepared_av_mask":
        return None
    try:
        return load_prepared_av_mask(candidate)
    except PreparedAVMaskError as exc:
        raise CompositionError(str(exc)) from exc


def _probe_stream(path: Path, codec_type: str) -> Mapping[str, Any]:
    probe = _probe(path)
    streams = probe.get("streams") if isinstance(probe, Mapping) else None
    matches = [item for item in streams or [] if isinstance(item, Mapping) and item.get("codec_type") == codec_type]
    if len(matches) != 1:
        raise CompositionError(f"expected exactly one {codec_type} stream in {path}")
    return matches[0]


def _probe_rate(stream: Mapping[str, Any], field: str, *, path: Path) -> Fraction:
    value = stream.get(field)
    try:
        rate = Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        raise CompositionError(f"{path} has no usable {field}") from None
    if rate <= 0:
        raise CompositionError(f"{path} has an invalid {field}")
    return rate


def _exact_clock(artifact: PreparedAVMask) -> tuple[Fraction, int]:
    try:
        fps_raw = artifact.video_clock["fps"]
        fps = Fraction(int(fps_raw["num"]), int(fps_raw["den"]))
        sample_raw = artifact.audio_clock["sample_rate"]
        sample_rate = int(sample_raw["num"]) // int(sample_raw["den"])
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        raise CompositionError("prepared AV mask has an invalid media clock") from None
    if fps <= 0 or sample_rate <= 0:
        raise CompositionError("prepared AV mask has a non-positive media clock")
    return fps, sample_rate


def _exact_offsets(preparation: Mapping[str, Any], fps: Fraction, sample_rate: int) -> tuple[int, int]:
    """Return source offsets in decoded frames/samples.

    The accepted v2 artifact is an output-domain artifact: its baseline starts
    at output frame/sample zero.  The legacy seconds-based offset is retained
    only for callers that do not carry a PreparedAVMask.
    """

    request = preparation.get("request")
    if isinstance(request, Mapping) and request.get("version") == 2:
        return 0, 0
    source = request.get("source") if isinstance(request, Mapping) else None
    value = source.get("range") if isinstance(source, Mapping) else None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return 0, 0
    try:
        seconds = Fraction(str(value[0]))
        frame_offset = seconds * fps
        sample_offset = seconds * sample_rate
    except (TypeError, ValueError, ZeroDivisionError):
        raise CompositionError("source range is not a rational media offset") from None
    if frame_offset.denominator != 1 or sample_offset.denominator != 1:
        raise CompositionError("source range is not aligned to both media clocks")
    return frame_offset.numerator, sample_offset.numerator


def _validate_exact_stream(
    path: Path,
    *,
    codec_type: str,
    width: int | None = None,
    height: int | None = None,
    fps: Fraction | None = None,
    sample_rate: int | None = None,
    channels: int | None = None,
) -> Mapping[str, Any]:
    stream = _probe_stream(path, codec_type)
    if codec_type == "video":
        if stream.get("width") != width or stream.get("height") != height:
            raise CompositionError(
                f"{path} video geometry {stream.get('width')}x{stream.get('height')} "
                f"does not match prepared {width}x{height}"
            )
        actual = _probe_rate(stream, "r_frame_rate", path=path)
        if fps is not None and actual != fps:
            raise CompositionError(f"{path} video rate {actual} does not match prepared {fps}")
    else:
        actual_rate = stream.get("sample_rate")
        try:
            actual_rate = int(actual_rate)
        except (TypeError, ValueError):
            actual_rate = 0
        if actual_rate != sample_rate or stream.get("channels") != channels:
            raise CompositionError(
                f"{path} audio format {actual_rate}Hz/{stream.get('channels')}ch "
                f"does not match prepared {sample_rate}Hz/{channels}ch"
            )
    return stream


def _decode_exact_video(
    path: Path,
    destination: Path,
    *,
    frames: int,
    width: int,
    height: int,
    fps: Fraction,
    start_frame: int = 0,
) -> None:
    _validate_exact_stream(path, codec_type="video", width=width, height=height, fps=fps)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise CompositionError("exact composition requires ffmpeg")
    if frames < 1 or start_frame < 0:
        raise CompositionError("exact video decode bounds are invalid")
    end_frame = start_frame + frames - 1
    filters = f"select=between(n\\,{start_frame}\\,{end_frame}),setpts=N/({fps.numerator}/{fps.denominator})/TB"
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-map", "0:v:0", "-vf", filters, "-an", "-sn", "-dn",
        "-frames:v", str(frames), "-f", "rawvideo", "-pix_fmt", _EXACT_VIDEO_PIXEL_FORMAT, str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise CompositionError(f"could not decode exact video samples: {detail[-500:]}") from exc
    expected = frames * width * height * 4
    if destination.stat().st_size != expected:
        raise CompositionError(
            f"{path} video is short or corrupt: expected {expected} RGBA bytes, found {destination.stat().st_size}"
        )


def _decode_exact_audio(
    path: Path,
    destination: Path,
    *,
    samples: int,
    sample_rate: int,
    channels: int,
    start_sample: int = 0,
) -> None:
    _validate_exact_stream(path, codec_type="audio", sample_rate=sample_rate, channels=channels)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise CompositionError("exact composition requires ffmpeg")
    if samples < 1 or start_sample < 0:
        raise CompositionError("exact audio decode bounds are invalid")
    end_sample = start_sample + samples
    filters = f"atrim=start_sample={start_sample}:end_sample={end_sample},asetpts=PTS-STARTPTS"
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-map", "0:a:0", "-af", filters, "-vn", "-sn", "-dn", "-frames:a", str(samples),
        "-ar", str(sample_rate), "-ac", str(channels), "-f", "s32le", str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise CompositionError(f"could not decode exact PCM samples: {detail[-500:]}") from exc
    expected = samples * channels * 4
    if destination.stat().st_size != expected:
        raise CompositionError(
            f"{path} audio is short or corrupt: expected {expected} PCM bytes, found {destination.stat().st_size}"
        )


def _anchor_items(preparation: Mapping[str, Any], artifact: PreparedAVMask) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    request = preparation.get("request")
    media = request.get("media") if isinstance(request, Mapping) else None
    by_id = {
        str(item.get("occurrence_id", item.get("id"))): item
        for item in media or []
        if isinstance(item, Mapping)
    }
    result: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for anchor in artifact.anchor_classification:
        item = by_id.get(str(anchor.get("id")))
        if item is not None and item.get("modality") in {"image", "video"}:
            result.append((anchor, item))
    return result


def _decode_anchor(path: Path, destination: Path, *, width: int, height: int) -> None:
    _validate_exact_stream(path, codec_type="video", width=width, height=height, fps=None)
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise CompositionError("exact anchor restoration requires ffmpeg")
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:v:0",
        "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", _EXACT_VIDEO_PIXEL_FORMAT, str(destination),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise CompositionError(f"could not decode anchor {path}: {detail[-500:]}") from exc
    if destination.stat().st_size != width * height * 4:
        raise CompositionError(f"anchor {path} is short or corrupt")


def _asset_paths(preparation: Mapping[str, Any]) -> dict[str, Path]:
    records = preparation.get("assets")
    if not isinstance(records, list):
        return {}
    result: dict[str, Path] = {}
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("asset"), str):
            continue
        raw = record.get("path")
        if isinstance(raw, str):
            path = Path(raw).expanduser().resolve()
            if path.is_file():
                result[str(record["asset"])] = path
    return result


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _baseline_identity_contract(
    preparation: Mapping[str, Any], artifact: PreparedAVMask
) -> dict[str, Any]:
    """Validate and return C2's unchanged authoritative baseline identity."""

    mapping = artifact.mapping
    identity = mapping.get("baseline_identity") if isinstance(mapping, Mapping) else None
    if not isinstance(identity, Mapping):
        raise ValueError("prepared AV mask is missing the C2 baseline identity contract")
    kind = identity.get("kind")
    digest = identity.get("digest")
    members = identity.get("members")
    if kind not in {"none", "source", "composite"} or not isinstance(members, list):
        raise ValueError("prepared AV mask has an invalid C2 baseline identity contract")
    if kind == "none":
        if members or digest is not None or artifact.source_baseline_digest is not None:
            raise ValueError("source-free baseline identity is not empty")
        return dict(identity)
    if not members:
        raise ValueError("authoritative baseline identity has no members")
    records = {
        str(record.get("asset")): record
        for record in preparation.get("assets", [])
        if isinstance(record, Mapping) and isinstance(record.get("asset"), str)
    }
    source_hashes = artifact.source_hashes
    seen_occurrences: set[str] = set()
    normalized_members: list[dict[str, Any]] = []
    for member in members:
        if not isinstance(member, Mapping):
            raise ValueError("authoritative baseline identity contains a malformed member")
        occurrence = member.get("occurrence_id")
        asset = member.get("asset")
        member_digest = member.get("sha256")
        if (
            not isinstance(occurrence, str)
            or not occurrence
            or occurrence in seen_occurrences
            or not isinstance(asset, str)
            or not asset
            or not isinstance(member_digest, str)
            or len(member_digest) != 64
        ):
            raise ValueError("authoritative baseline identity contains an invalid member")
        seen_occurrences.add(occurrence)
        record = records.get(asset)
        if not isinstance(record, Mapping) or record.get("status") != "resolved":
            raise ValueError(f"authoritative baseline asset {asset!r} is not resolved")
        record_digest = record.get("sha256")
        raw_path = record.get("path")
        if not isinstance(record_digest, str) or record_digest != member_digest or not isinstance(raw_path, str):
            raise ValueError(f"authoritative baseline asset {asset!r} does not match its manifest hash")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_file() or _sha256(path) != member_digest:
            raise ValueError(f"authoritative baseline asset {asset!r} changed after preparation")
        if source_hashes.get(asset) != member_digest:
            raise ValueError(f"authoritative baseline asset {asset!r} disagrees with source_hashes")
        normalized_members.append(dict(member))

    primary_occurrence = identity.get("primary_occurrence")
    primary = next((item for item in normalized_members if item["occurrence_id"] == primary_occurrence), None)
    if primary is None:
        raise ValueError("authoritative baseline identity has no declared primary member")
    primary_digest = str(primary["sha256"])
    if kind == "source":
        if len(normalized_members) != 1 or digest != primary_digest:
            raise ValueError("source baseline identity is inconsistent")
        expected_digest = primary_digest
    else:
        if len(normalized_members) < 2:
            raise ValueError("composite baseline identity needs multiple members")
        expected_digest = hashlib.sha256(_canonical_json(normalized_members)).hexdigest()
        if digest != expected_digest:
            raise ValueError("composite baseline identity digest does not match its members")
    declared_source = artifact.source_baseline_digest
    if not isinstance(declared_source, str) or declared_source.removeprefix("sha256:") != primary_digest:
        raise ValueError("source_baseline_digest does not match the C2 primary baseline member")
    return dict(identity)


def _primary_baseline_asset(preparation: Mapping[str, Any], artifact: PreparedAVMask) -> str | None:
    identity = _baseline_identity_contract(preparation, artifact)
    occurrence = identity.get("primary_occurrence")
    for member in identity.get("members", []):
        if isinstance(member, Mapping) and member.get("occurrence_id") == occurrence:
            return str(member["asset"])
    return None


def _apply_exact_anchors(
    *,
    preparation: Mapping[str, Any],
    artifact: PreparedAVMask,
    source_video_raw: Path | None,
    video_raw: Path,
    width: int,
    height: int,
    frames: int,
    temp_dir: Path,
) -> list[dict[str, Any]]:
    assets = _asset_paths(preparation)
    request = preparation.get("request")
    source_asset = _primary_baseline_asset(preparation, artifact)
    records: list[dict[str, Any]] = []
    frame_bytes = width * height * 4
    with video_raw.open("r+b") as handle:
        for index, (anchor, item) in enumerate(_anchor_items(preparation, artifact)):
            frame = anchor.get("frame")
            if type(frame) is not int or not 0 <= frame < frames:
                raise CompositionError(f"anchor {anchor.get('id')!r} is outside the prepared video domain")
            if anchor.get("exact_final_restoration") is not True or anchor.get("classification") == "rejected":
                raise CompositionError(f"anchor {anchor.get('id')!r} is not accepted for exact restoration")
            asset_id = str(item.get("asset"))
            anchor_raw = temp_dir / f"anchor-{index}.rgba"
            if source_video_raw is not None and asset_id == source_asset and item.get("modality") == "video":
                with source_video_raw.open("rb") as source_handle:
                    source_handle.seek(frame * frame_bytes)
                    payload = source_handle.read(frame_bytes)
                if len(payload) != frame_bytes:
                    raise CompositionError(f"source anchor {anchor.get('id')!r} is unavailable")
                anchor_raw.write_bytes(payload)
            else:
                anchor_path = assets.get(asset_id)
                if anchor_path is None:
                    raise CompositionError(f"anchor asset {asset_id!r} is unavailable")
                _decode_anchor(anchor_path, anchor_raw, width=width, height=height)
            expected = anchor_raw.read_bytes()
            handle.seek(frame * frame_bytes)
            handle.write(expected)
            records.append({
                "id": str(anchor.get("id")),
                "frame": frame,
                "classification": anchor.get("classification"),
                "source_asset": asset_id,
                "restored": True,
            })
    return records


def _compose_exact_media(
    *,
    preparation: Mapping[str, Any],
    artifact: PreparedAVMask,
    source: Path | None,
    generated_video: Path | None,
    generated_audio: Path | None,
    destination: Path,
) -> dict[str, Any]:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise CompositionError("exact composition requires ffmpeg")
    try:
        baseline_identity = _baseline_identity_contract(preparation, artifact)
    except ValueError as exc:
        raise CompositionError(str(exc)) from exc
    fps, sample_rate = _exact_clock(artifact)
    frames, height, width = artifact.video_shape
    channels, samples = artifact.audio_shape
    video_permissions = artifact.video_delivery()
    audio_permissions = artifact.audio_delivery()
    protected_video = sum(1 for frame in video_permissions for row in frame for value in row if value == 0)
    protected_audio = sum(1 for channel in audio_permissions for value in channel if value == 0)
    editable_video = frames * height * width - protected_video
    editable_audio = channels * samples - protected_audio
    if not baseline_identity.get("members") and (protected_video or protected_audio):
        raise CompositionError("exact protected composition requires an authoritative source baseline")
    if source is not None and artifact.source_baseline_digest:
        if artifact.source_baseline_digest.removeprefix("sha256:") != _sha256(source):
            raise CompositionError("authoritative source does not match the C2 baseline identity")
    if generated_video is None and editable_video:
        raise CompositionError("generated video output is required for editable delivery pixels")
    if generated_audio is None and editable_audio:
        raise CompositionError("generated audio output is required for editable delivery samples")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="h3-av-exact-") as raw_root:
        temp_dir = Path(raw_root)
        source_video_raw = temp_dir / "source-video.rgba"
        source_audio_raw = temp_dir / "source-audio.s32le"
        generated_video_raw = temp_dir / "generated-video.rgba"
        generated_audio_raw = temp_dir / "generated-audio.s32le"
        composed_video_raw = temp_dir / "composed-video.rgba"
        composed_audio_raw = temp_dir / "composed-audio.s32le"
        if baseline_identity.get("members"):
            from .baseline import BaselineError, render_timeline_baseline

            try:
                render_timeline_baseline(preparation, artifact, temp_dir, primary_source=source)
            except (BaselineError, CompositionError) as exc:
                raise CompositionError(f"could not resolve delivery-clock baseline: {exc}") from exc
            source_video_raw = temp_dir / "baseline.rgba"
            source_audio_raw = temp_dir / "baseline.s32le"
        source_asset = _primary_baseline_asset(preparation, artifact)
        anchor_needs_source_video = any(
            str(item.get("asset")) == source_asset and item.get("modality") == "video"
            for _anchor, item in _anchor_items(preparation, artifact)
        )
        if not baseline_identity.get("members") and source is not None and (protected_video or anchor_needs_source_video):
            source_frame_offset, _ = _exact_offsets(preparation, fps, sample_rate)
            _decode_exact_video(source, source_video_raw, frames=frames, width=width, height=height, fps=fps, start_frame=source_frame_offset)
        if not baseline_identity.get("members") and source is not None and protected_audio:
            _, source_sample_offset = _exact_offsets(preparation, fps, sample_rate)
            _decode_exact_audio(source, source_audio_raw, samples=samples, sample_rate=sample_rate, channels=channels, start_sample=source_sample_offset)
        if generated_video is not None:
            _decode_exact_video(generated_video, generated_video_raw, frames=frames, width=width, height=height, fps=fps)
        if generated_audio is not None:
            _decode_exact_audio(generated_audio, generated_audio_raw, samples=samples, sample_rate=sample_rate, channels=channels)

        frame_bytes = width * height * 4
        composed_video_raw.touch()
        with composed_video_raw.open("wb") as output:
            source_handle = source_video_raw.open("rb") if source_video_raw.exists() else None
            generated_handle = generated_video_raw.open("rb") if generated_video_raw.exists() else None
            try:
                for frame_index, frame in enumerate(video_permissions):
                    source_frame = source_handle.read(frame_bytes) if source_handle is not None else None
                    generated_frame = generated_handle.read(frame_bytes) if generated_handle is not None else None
                    if source_frame is not None and len(source_frame) != frame_bytes:
                        raise CompositionError("decoded source video became short during composition")
                    if generated_frame is not None and len(generated_frame) != frame_bytes:
                        raise CompositionError("decoded generated video became short during composition")
                    merged = bytearray(frame_bytes)
                    for row_index, row in enumerate(frame):
                        for column_index, permission in enumerate(row):
                            offset = (row_index * width + column_index) * 4
                            payload = generated_frame if permission else source_frame
                            if payload is None:
                                raise CompositionError(f"video frame {frame_index} lacks its required source/generated payload")
                            merged[offset : offset + 4] = payload[offset : offset + 4]
                    output.write(merged)
            finally:
                if source_handle is not None:
                    source_handle.close()
                if generated_handle is not None:
                    generated_handle.close()

        sample_bytes = channels * 4
        with composed_audio_raw.open("wb") as output:
            source_handle = source_audio_raw.open("rb") if source_audio_raw.exists() else None
            generated_handle = generated_audio_raw.open("rb") if generated_audio_raw.exists() else None
            try:
                for sample_index in range(samples):
                    source_frame = source_handle.read(sample_bytes) if source_handle is not None else None
                    generated_frame = generated_handle.read(sample_bytes) if generated_handle is not None else None
                    if source_frame is not None and len(source_frame) != sample_bytes:
                        raise CompositionError("decoded source audio became short during composition")
                    if generated_frame is not None and len(generated_frame) != sample_bytes:
                        raise CompositionError("decoded generated audio became short during composition")
                    merged = bytearray(sample_bytes)
                    for channel in range(channels):
                        offset = channel * 4
                        payload = generated_frame if audio_permissions[channel][sample_index] else source_frame
                        if payload is None:
                            raise CompositionError(f"audio sample {sample_index} lacks its required source/generated payload")
                        merged[offset : offset + 4] = payload[offset : offset + 4]
                    output.write(merged)
            finally:
                if source_handle is not None:
                    source_handle.close()
                if generated_handle is not None:
                    generated_handle.close()

        anchors = _apply_exact_anchors(
            preparation=preparation,
            artifact=artifact,
            source_video_raw=source_video_raw if source_video_raw.exists() else None,
            video_raw=composed_video_raw,
            width=width,
            height=height,
            frames=frames,
            temp_dir=temp_dir,
        )
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "rawvideo", "-pixel_format", _EXACT_VIDEO_PIXEL_FORMAT,
            "-video_size", f"{width}x{height}", "-framerate", f"{fps.numerator}/{fps.denominator}",
            "-i", str(composed_video_raw), "-f", _EXACT_AUDIO_SAMPLE_FORMAT,
            "-ar", str(sample_rate), "-ac", str(channels), "-i", str(composed_audio_raw),
            "-map", "0:v:0", "-map", "1:a:0", "-frames:v", str(frames), "-frames:a", str(samples),
            "-map_metadata", "-1", "-c:v", _EXACT_VIDEO_CODEC, "-level", "3", "-coder", "1", "-context", "1",
            "-pix_fmt", _EXACT_VIDEO_PIXEL_FORMAT, "-c:a", _EXACT_AUDIO_CODEC,
            "-metadata:s:v:0", "astrid.decoded_pixel_format=rgba;top-left_display_orientation",
            "-metadata:s:a:0", f"astrid.decoded_pcm_format=s32le;rate={sample_rate};channel_order=source",
            str(destination),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise CompositionError(f"lossless master encoding failed: {detail[-500:]}") from exc

    return {
        "method": "cpu-exact-delivery-compose-v1",
        "container": _EXACT_MASTER_CONTAINER,
        "lossless": True,
        "video_codec": _EXACT_VIDEO_CODEC,
        "audio_codec": _EXACT_AUDIO_CODEC,
        "video_pixel_format": _EXACT_VIDEO_PIXEL_FORMAT,
        "audio_pcm_format": _EXACT_AUDIO_SAMPLE_FORMAT,
        "video_orientation": "top-left_display_orientation",
        "audio_channel_order": "prepared_channel_order",
        "video_shape": [frames, height, width],
        "audio_shape": [channels, samples],
        "fps": [fps.numerator, fps.denominator],
        "sample_rate": sample_rate,
        "protected_counts": {"video_pixels": protected_video, "audio_samples": protected_audio},
        "editable_counts": {"video_pixels": editable_video, "audio_samples": editable_audio},
        "anchors": anchors,
        "baseline_identity": baseline_identity,
    }


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
                filters.append(
                    f"[{input_index}:v:0]trim=start={trim_start}:end={trim_end},setpts=PTS-STARTPTS[{piece}]"
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
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path),
            "-ss", str(start), "-t", str(duration), "-map", "0:a:0", "-vn", "-ar", "48000", "-ac", "2", "-f", "s16le", "-",
        ]
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
    if not completed.stdout:
        raise CompositionError(f"protected {stream_type} interval produced no samples")
    # AAC and similar source codecs can differ by a few least-significant
    # bits when the same samples pass through a filter graph. Keep the
    # witness sample-based, but use deterministic 10ms per-channel amplitude
    # buckets so codec/container plumbing does not turn an unchanged source
    # into a false negative while a changed passage still produces a witness
    # mismatch.
    values = [
        int.from_bytes(completed.stdout[offset : offset + 2], "little", signed=True)
        for offset in range(0, len(completed.stdout) - 1, 2)
    ]
    metrics: list[int] = []
    channels = 2
    block_frames = 480
    for start in range(0, len(values), block_frames * channels):
        block = values[start : start + block_frames * channels]
        for channel in range(channels):
            metrics.append(sum(abs(value) for value in block[channel::channels]) // 4096)
    payload = json.dumps(metrics, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(payload).hexdigest(), len(values)


def _auto_sample_evidence(
    *, source: Path, candidate: Path, schedule: Mapping[str, Any], source_offset: float
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {"video": [], "audio": []}
    for stream_type in ("video", "audio"):
        for interval in schedule[stream_type]["protected_intervals"]:
            start, end = float(interval[0]), float(interval[1])
            source_hash, sample_count = _sample_digest(source, stream_type, source_offset + start, end - start)
            candidate_hash, candidate_count = _sample_digest(candidate, stream_type, start, end - start)
            result[stream_type].append(
                {
                    "interval": [start, end],
                    "source_sha256": source_hash,
                    "candidate_sha256": candidate_hash,
                    "sample_count": min(sample_count, candidate_count),
                    "method": "ffmpeg-decoded-samples-v1",
                }
            )
    return result


def compose_candidate(
    *,
    preparation: Mapping[str, Any],
    generated: str | Path | None,
    source: str | Path | None = None,
    baseline: str | Path | None = None,
    out_dir: str | Path,
    preservation_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose one candidate and publish custody plus preservation evidence."""

    try:
        read_prepared_request(
            preparation.get("request"),
            preparation.get("request_digest"),
            require_normalized_v2=True,
        )
    except (TypeError, ValueError) as exc:
        raise CompositionError(f"preparation request is invalid: {exc}") from exc

    generated_path = None if generated is None else Path(generated).expanduser().resolve()
    if generated_path is not None and not generated_path.is_file():
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
    artifact = _prepared_artifact(preparation)
    if artifact is not None:
        try:
            baseline_identity = _baseline_identity_contract(preparation, artifact)
        except ValueError as exc:
            raise CompositionError(str(exc)) from exc
        destination = Path(out_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        with _generated_inputs(generated_path) as (generated_video, generated_audio, generated_manifest):
            if generated_audio is None and generated_video is not None and _stream_types(_probe(generated_video)) & {"audio"}:
                generated_audio = generated_video
            candidate = destination / "h3-av-master.mkv"
            composition_method = _compose_exact_media(
                preparation=preparation,
                artifact=artifact,
                source=source_path,
                generated_video=generated_video,
                generated_audio=generated_audio,
                destination=candidate,
            )
            provenance = preparation.get("provenance")
            manifest: dict[str, Any] = {
                "schema_version": 1,
                "kind": "h3_av_composition",
                "request_digest": preparation.get("request_digest"),
                "schedule_digest": schedule.get("digest"),
                "prepared_av_mask_digest": artifact.artifact_digest,
                "candidate": {"path": str(candidate), "sha256": _sha256(candidate), "size": candidate.stat().st_size, "media_type": "video/x-matroska", "output_port": "candidate", "ordinal": 0},
                "source": None if source_path is None else {"path": str(source_path), "sha256": _sha256(source_path), "size": source_path.stat().st_size},
                "generated_outputs": generated_manifest.get("outputs", []),
                "changed_permissions": {"video": composition_method["editable_counts"]["video_pixels"], "audio": composition_method["editable_counts"]["audio_samples"]},
                "protected_permissions": {"video": composition_method["protected_counts"]["video_pixels"], "audio": composition_method["protected_counts"]["audio_samples"]},
                "preservation_evidence": {"method": "independent-decoded-domain-verification-required"},
                "composition": composition_method,
                "delivery_contract": {
                    "schema_version": _EXACT_SCHEMA_VERSION,
                    "prepared_av_mask_digest": artifact.artifact_digest,
                    "baseline_representation": {
                        "identity": baseline_identity,
                        "video": {"decoded_pixel_format": _EXACT_VIDEO_PIXEL_FORMAT, "orientation": "top-left_display_orientation", "geometry": list(artifact.video_shape[1:])},
                        "audio": {"decoded_pcm_format": _EXACT_AUDIO_SAMPLE_FORMAT, "sample_rate": composition_method["sample_rate"], "channels": artifact.audio_shape[0], "channel_order": "prepared_channel_order"},
                    },
                    "lossless_master": {"container": _EXACT_MASTER_CONTAINER, "video_codec": _EXACT_VIDEO_CODEC, "audio_codec": _EXACT_AUDIO_CODEC, "preview": None},
                    "codec_semantics": "FFV1 and PCM encode the composed canonical decoded domain; no resize, resample, channel mix, or temporal shift is permitted.",
                    "anchors": composition_method["anchors"],
                },
                "provenance": dict(provenance) if isinstance(provenance, Mapping) else {},
                "status": "composed",
            }
            manifest_path = destination / "composition-manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
            manifest["manifest_path"] = str(manifest_path)
            return manifest
    protected = any(schedule[domain]["protected_intervals"] for domain in ("video", "audio"))
    if protected and source_path is None:
        raise CompositionError("protected composition requires an authoritative source baseline")

    destination = Path(out_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if generated_path is None:
        raise CompositionError("legacy composition requires a generated candidate")
    with _generated_inputs(generated_path) as (generated_video, generated_audio, generated_manifest):
        composition_method: dict[str, Any] = {"method": "candidate-custody-v1"}
        # Every managed compose result has one stable media filename.  The
        # bytes are copied/muxed as produced; the name is not used to claim a
        # codec or container that was not actually produced.
        candidate = destination / "h3-av-master.mkv"
        if source_path is not None and protected and any(
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
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "kind": "h3_av_composition",
            "request_digest": preparation.get("request_digest"),
            "schedule_digest": schedule.get("digest"),
            "candidate": {"path": str(candidate), "sha256": _sha256(candidate), "size": candidate.stat().st_size, "media_type": "video/x-matroska", "output_port": "candidate", "ordinal": 0},
            "source": None if source_path is None else {"path": str(source_path), "sha256": _sha256(source_path), "size": source_path.stat().st_size},
            "generated_outputs": generated_manifest.get("outputs", []),
            "changed_permissions": {"video": schedule["video"]["generated_intervals"], "audio": schedule["audio"]["generated_intervals"]},
            "protected_permissions": {"video": schedule["video"]["protected_intervals"], "audio": schedule["audio"]["protected_intervals"]},
            "preservation_evidence": evidence,
            "composition": {**composition_method, "output_roles": ["video", "audio"] if generated_audio is not None else ["video"]},
            "provenance": dict(provenance) if isinstance(provenance, Mapping) else {},
            "status": "composed",
        }
        manifest_path = destination / "composition-manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        manifest["manifest_path"] = str(manifest_path)
        return manifest


__all__ = ["CompositionError", "compose_candidate", "_probe", "_sample_digest"]
