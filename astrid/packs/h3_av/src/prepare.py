"""Attempt-local preparation for an H3 audiovisual request."""

from __future__ import annotations

import hashlib
import json
import math
import zipfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from .kernel import classify_anchors, require_supported_anchors, temporal_cells
from .masks import MaskScheduleError, PreparedAVMask, PreparedAVMaskError, build_mask_schedule
from .request import H3Request


class PreparationError(ValueError):
    """The request or its declared assets cannot be prepared safely."""


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_ids(request: H3Request) -> list[str]:
    value = request.value
    if value.get("version") == 2:
        result = [str(item["asset"]) for item in value["media"]]
        for item in value["media"]:
            for edit in item.get("edit", []):
                mask = edit.get("mask", {})
                if isinstance(mask, Mapping) and "asset" in mask:
                    result.append(str(mask["asset"]))
        return list(dict.fromkeys(result))
    result: list[str] = []
    source = value.get("source")
    if isinstance(source, Mapping):
        result.append(source["asset"])
    result.extend(reference["asset"] for reference in value["references"])
    for domain in ("video", "audio"):
        for change in value["changes"][domain]:
            if "mask_asset" in change:
                result.append(change["mask_asset"])
            area = change.get("area", {})
            if "mask_asset" in area:
                result.append(area["mask_asset"])
    return list(dict.fromkeys(result))


def _resolve_assets(request: H3Request, asset_map: Mapping[str, str] | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for asset_id in _asset_ids(request):
        raw_path = asset_map.get(asset_id) if asset_map else None
        record: dict[str, Any] = {"asset": asset_id}
        if raw_path is None:
            record.update({"kind": "managed_asset", "status": "unresolved"})
        else:
            path = Path(raw_path).expanduser().resolve()
            if Path(raw_path).expanduser().is_symlink() or path.is_symlink():
                raise PreparationError(f"asset {asset_id!r} may not be a symlink")
            if not path.is_file():
                raise PreparationError(f"asset {asset_id!r} does not resolve to a file: {path}")
            if path.suffix.lower() == ".zip":
                try:
                    with zipfile.ZipFile(path) as archive:
                        for member in archive.infolist():
                            name = Path(member.filename)
                            if name.is_absolute() or ".." in name.parts or (member.external_attr >> 16) & 0o170000 == 0o120000:
                                raise PreparationError(f"asset archive {path} contains an unsafe member {member.filename!r}")
                except zipfile.BadZipFile as exc:
                    raise PreparationError(f"asset archive {path} is invalid") from exc
            record.update(
                {
                    "kind": "file",
                    "status": "resolved",
                    "path": str(path),
                    "size": path.stat().st_size,
                    "sha256": _file_digest(path),
                }
            )
        records.append(record)
    return records


def _rational(value: Any, path: str) -> Fraction:
    try:
        if isinstance(value, (tuple, list)) and len(value) == 2:
            result = Fraction(int(value[0]), int(value[1]))
        else:
            result = Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError):
        raise PreparationError(f"{path} must be a positive rational") from None
    if result <= 0:
        raise PreparationError(f"{path} must be a positive rational")
    return result


def _frame_count(duration: Any, fps: Fraction) -> int:
    resolved = _rational(duration, "duration") * fps
    if resolved.denominator != 1:
        raise PreparationError("duration is not representable on the video clock")
    return resolved.numerator


def _sample_count(duration: Any, sample_rate: int) -> int:
    resolved = _rational(duration, "duration") * sample_rate
    if resolved.denominator != 1:
        raise PreparationError("duration is not representable on the audio clock")
    return resolved.numerator


def _model_steps(frames: int) -> int:
    steps = 1
    while temporal_cells(steps)[-1]["end"] < frames:
        steps += 1
    return steps


def _mask_pixels(mask: Mapping[str, Any], *, height: int, width: int) -> list[list[int]]:
    if mask.get("full_frame") is True:
        return [[1] * width for _ in range(height)]
    if "rectangle" in mask:
        x, y, w, h = (float(value) for value in mask["rectangle"])
        return [[1 if x <= column < x + w and y <= row < y + h else 0 for column in range(width)] for row in range(height)]
    if "polygon" in mask:
        points = [(float(point[0]), float(point[1])) for point in mask["polygon"]]
        result: list[list[int]] = []
        for row in range(height):
            line: list[int] = []
            for column in range(width):
                inside = False
                previous = points[-1]
                for current in points:
                    if ((current[1] > row) != (previous[1] > row)) and column < (previous[0] - current[0]) * (row - current[1]) / (previous[1] - current[1]) + current[0]:
                        inside = not inside
                    previous = current
                line.append(int(inside))
            result.append(line)
        return result
    raise PreparationError("video mask geometry is not supported")


def _load_mask_json(path: Path, *, height: int, width: int) -> list[list[list[int]]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PreparationError(f"mask asset {path} must be a JSON array or object") from exc
    if isinstance(raw, Mapping):
        raw = raw.get("values", raw.get("mask"))
    if not isinstance(raw, list) or not raw:
        raise PreparationError(f"mask asset {path} has no raster values")
    if raw and isinstance(raw[0], list) and raw[0] and not isinstance(raw[0][0], list):
        raw = [raw]
    frames: list[list[list[int]]] = []
    for frame in raw:
        if not isinstance(frame, list) or len(frame) != height or any(not isinstance(row, list) or len(row) != width for row in frame):
            raise PreparationError(f"mask asset {path} does not cover the requested {height}x{width} geometry")
        normalized: list[list[int]] = []
        for row in frame:
            values: list[int] = []
            for value in row:
                if isinstance(value, bool):
                    number = int(value)
                elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                    number = int(value)
                    if float(value) not in (0.0, 1.0):
                        raise PreparationError(f"mask asset {path} must be binary")
                else:
                    raise PreparationError(f"mask asset {path} contains an invalid value")
                values.append(number)
            normalized.append(values)
        frames.append(normalized)
    return frames


def _load_mask_png(path: Path, *, height: int, width: int) -> list[list[list[int]]]:
    """Accept one exact binary still mask without resampling its pixels."""

    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(path) as image:
            if image.format != "PNG" or image.size != (width, height):
                raise PreparationError(f"mask asset {path} must be a {width}x{height} PNG")
            if "A" in image.getbands() and image.getchannel("A").getextrema() != (255, 255):
                raise PreparationError(f"mask asset {path} has ambiguous transparency")
            gray = image.convert("L")
            pixels = gray.tobytes()
    except (OSError, UnidentifiedImageError) as exc:
        raise PreparationError(f"mask asset {path} could not be decoded as PNG") from exc
    if any(value not in (0, 255) for value in pixels):
        raise PreparationError(f"mask asset {path} must be binary black/white")
    return [[[int(pixels[row * width + column] == 255) for column in range(width)] for row in range(height)]]


def _merge_int_ranges(ranges: list[list[int]], length: int) -> list[list[int]]:
    for start, end in ranges:
        if type(start) is not int or type(end) is not int or start < 0 or end <= start or end > length:
            raise PreparationError("coverage is outside its declared output domain")
    ordered = sorted((start, end) for start, end in ranges)
    merged: list[list[int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def _frame_to_sample(value: int, *, fps: Fraction, sample_rate: int, path: str) -> int:
    resolved = Fraction(value * sample_rate, 1) / fps
    if resolved.denominator != 1:
        raise PreparationError(f"{path} is not representable on the audio clock")
    return resolved.numerator


def _baseline_interval(item: Mapping[str, Any], *, frames: int, samples: int, fps: Fraction, sample_rate: int) -> tuple[list[int], list[int]]:
    occurrence = str(item.get("occurrence_id", "timeline"))
    if "resolved_range" not in item:
        raise PreparationError(f"timeline baseline {occurrence!r} is missing inspected coverage")
    resolved = item["resolved_range"]
    if not isinstance(resolved, (list, tuple)) or len(resolved) != 2 or any(type(value) is not int for value in resolved):
        raise PreparationError(f"timeline baseline {occurrence!r} has ambiguous normalized coverage")
    range_start, range_end = resolved
    if range_start < 0 or range_end <= range_start:
        raise PreparationError(f"timeline baseline {occurrence!r} has invalid normalized coverage")
    at = item.get("resolved_at", {}).get("value", 0)
    if type(at) is not int or at < 0:
        raise PreparationError(f"timeline baseline {occurrence!r} has an invalid placement")
    modality = item.get("modality")
    if modality == "video":
        video_end = at + (range_end - range_start)
        if video_end > frames:
            raise PreparationError(f"video baseline coverage for {occurrence!r} is outside the output")
        sample_start = _frame_to_sample(at, fps=fps, sample_rate=sample_rate, path=f"{occurrence}.at")
        sample_end = _frame_to_sample(video_end, fps=fps, sample_rate=sample_rate, path=f"{occurrence}.range")
        if sample_end > samples:
            raise PreparationError(f"audio baseline coverage for {occurrence!r} is outside the output")
        return [at, video_end], [sample_start, sample_end]
    if modality == "audio":
        sample_start = _frame_to_sample(at, fps=fps, sample_rate=sample_rate, path=f"{occurrence}.at")
        sample_end = sample_start + (range_end - range_start)
        if sample_end > samples:
            raise PreparationError(f"audio baseline coverage for {occurrence!r} is outside the output")
        return [], [sample_start, sample_end]
    raise PreparationError(f"timeline baseline {occurrence!r} has unsupported modality {modality!r}")


def _validate_baseline(ranges: list[list[int]], *, length: int, domain: str, require_full: bool) -> list[list[int]]:
    if not ranges:
        raise PreparationError(f"{domain} baseline coverage is missing")
    ordered = sorted(ranges)
    previous_end = 0
    for start, end in ordered:
        if start < previous_end:
            raise PreparationError(f"{domain} baseline coverage is ambiguous because intervals overlap")
        previous_end = end
    merged = _merge_int_ranges(ranges, length)
    if require_full and merged != [[0, length]]:
        raise PreparationError(f"{domain} baseline coverage is short or does not cover the output")
    return merged


def _baseline_identity(request: H3Request, source_hashes: Mapping[str, str]) -> tuple[str | None, dict[str, Any]]:
    members: list[dict[str, Any]] = []
    for item in request.value["media"]:
        if item["role"] != "timeline":
            continue
        member = {
            "occurrence_id": item["occurrence_id"],
            "asset": item["asset"],
            "modality": item.get("modality"),
            "sha256": source_hashes[item["asset"]],
            "resolved_at": item.get("resolved_at"),
            "resolved_range": item.get("resolved_range"),
        }
        members.append(member)
    if not members:
        return None, {"kind": "none", "digest": None, "members": []}
    primary = next((item for item in members if item.get("modality") in {"video", "audio"}), members[0])
    primary_digest = str(primary["sha256"])
    if len(members) == 1:
        digest = primary_digest
        kind = "source"
    else:
        digest = hashlib.sha256(_canonical_json(members)).hexdigest()
        kind = "composite"
    return primary_digest, {"kind": kind, "digest": digest, "primary_occurrence": primary["occurrence_id"], "members": members}


def _edit_ranges(request: H3Request, *, frames: int, samples: int, fps: Fraction, sample_rate: int, width: int, height: int, assets: Mapping[str, Path]) -> tuple[list[list[list[int]]], list[list[int]], list[list[int]], list[list[int]], list[dict[str, Any]]]:
    # Uncovered output is generated. Declared baseline intervals are restored
    # exactly by composition; generated edit intervals stay permitted.
    video = [[[1 for _ in range(width)] for _ in range(height)] for _ in range(frames)]
    audio = [[1 for _ in range(samples)] for _ in range(2)]
    video_coverage: list[list[int]] = []
    audio_coverage: list[list[int]] = []
    baseline_video: list[list[int]] = []
    baseline_audio: list[list[int]] = []
    baseline_audio_from_video: list[list[int]] = []
    anchors: list[dict[str, Any]] = []
    media = request.value["media"]
    has_video_baseline = any(item["role"] == "timeline" and item.get("modality") == "video" for item in media)
    has_audio_timeline = any(item["role"] == "timeline" and item.get("modality") == "audio" for item in media)
    has_baseline = has_video_baseline or has_audio_timeline
    has_explicit_edits = any(item["role"] == "timeline" and item.get("edit") for item in media)
    for item in media:
        at = int(item.get("resolved_at", {}).get("value", 0)) if item["role"] == "timeline" else 0
        if item["role"] == "timeline":
            if item.get("modality") == "image":
                anchors.append({"id": item["occurrence_id"], "frame": at, "mode": "hard" if item.get("hard") else "soft", "latent_pin": item.get("latent_pin", False), "modality": "image"})
            if item.get("modality") in {"video", "audio"}:
                video_range, audio_range = _baseline_interval(item, frames=frames, samples=samples, fps=fps, sample_rate=sample_rate)
                if item.get("modality") == "video":
                    baseline_video.extend([video_range] if video_range else [])
                    for frame in range(*video_range):
                        video[frame] = [[0 for _ in range(width)] for _ in range(height)]
                    baseline_audio_from_video.extend([audio_range] if audio_range else [])
                else:
                    baseline_audio.extend([audio_range] if audio_range else [])
                if item.get("modality") == "audio" and audio_range:
                    for channel in range(2):
                        for sample in range(*audio_range):
                            audio[channel][sample] = 0
                elif item.get("modality") == "video" and audio_range:
                    for channel in range(2):
                        for sample in range(*audio_range):
                            audio[channel][sample] = 0
            for edit in item.get("edit", []):
                if edit.get("hard") is True:
                    raise PreparationError("edit hard conditioning is not supported")
                resolved = edit["resolved"]["range"]
                if edit["stream"] == "video":
                    start, end = at + int(resolved[0]), at + int(resolved[1])
                    if start < 0 or end > frames or end <= start:
                        raise PreparationError("video edit coverage is outside the output")
                    mask = edit.get("mask", {"full_frame": True})
                    if ("range" in mask or "shape" in mask) and "asset" not in mask:
                        raise PreparationError("video mask range/shape require a supplied raster asset")
                    raster = _mask_pixels(mask, height=height, width=width) if "asset" not in mask else None
                    moving = None
                    if raster is None:
                        mask_path = assets.get(str(mask["asset"]))
                        if mask_path is None:
                            raise PreparationError("supplied mask asset is unresolved")
                        if mask_path.suffix.lower() == ".json":
                            moving = _load_mask_json(mask_path, height=height, width=width)
                        elif mask_path.suffix.lower() == ".png":
                            moving = _load_mask_png(mask_path, height=height, width=width)
                        else:
                            raise PreparationError("supplied masks must be binary JSON rasters or PNG stills")
                        declared = mask.get("shape")
                        if declared is not None and declared != {"frames": len(moving), "height": height, "width": width}:
                            raise PreparationError("declared mask shape does not match the supplied raster")
                        mask_range = mask.get("resolved_range", mask.get("range", [0, len(moving)]))
                        if not isinstance(mask_range, (list, tuple)) or len(mask_range) != 2 or any(type(value) is not int for value in mask_range):
                            raise PreparationError("video mask range must be an integer half-open frame interval")
                        mask_start, mask_end = mask_range
                        if mask_start < 0 or mask_end <= mask_start or mask_end > len(moving):
                            raise PreparationError("video mask range is outside the supplied raster")
                        moving = moving[mask_start:mask_end]
                        if len(moving) not in {1, end - start}:
                            raise PreparationError("video mask range does not match its edit interval")
                    for offset, frame in enumerate(range(start, end)):
                        current = moving[offset] if moving and len(moving) > 1 else (moving[0] if moving else raster)
                        if moving and len(moving) not in {1, end - start}:
                            raise PreparationError("moving mask coverage does not match its edit interval")
                        if edit["action"] == "generate":
                            video[frame] = [[max(video[frame][row][column], current[row][column]) for column in range(width)] for row in range(height)]
                        else:
                            baseline_ranges = baseline_video
                            if not any(base_start <= frame and frame + 1 <= base_end for base_start, base_end in baseline_ranges):
                                raise PreparationError("preserve video edit is not covered by an authoritative baseline")
                    video_coverage.append([start, end])
                else:
                    offset = (at * sample_rate) // fps.numerator if fps.denominator == 1 else int(Fraction(at * sample_rate, 1) / fps)
                    start, end = offset + int(resolved[0]), offset + int(resolved[1])
                    if start < 0 or end > samples or end <= start:
                        raise PreparationError("audio edit coverage is outside the output")
                    channels = range(2) if edit.get("channels", "all") == "all" else edit["channels"]
                    if any(channel >= 2 for channel in channels):
                        raise PreparationError("audio channel permission exceeds the declared stereo layout")
                    if edit["action"] == "generate":
                        for channel in channels:
                            for sample in range(start, end):
                                audio[channel][sample] = 1
                    elif not any(base_start <= start and end <= base_end for base_start, base_end in baseline_audio_from_video + baseline_audio):
                        raise PreparationError("preserve audio edit is not covered by an authoritative baseline")
                    audio_coverage.append([start, end])
    if has_baseline:
        # A continuation tail is an explicit generation region.  Ordinary
        # source-backed edits still require a complete authoritative baseline;
        # callers opt into a shorter source with continuation=true.
        require_full_baseline = not has_explicit_edits and not bool(request.value.get("continuation", False))
        video_coverage = _validate_baseline(baseline_video, length=frames, domain="video", require_full=require_full_baseline) if has_video_baseline else [[0, frames]]
        audio_members = baseline_audio_from_video + baseline_audio
        audio_coverage = _validate_baseline(audio_members, length=samples, domain="audio", require_full=require_full_baseline) if audio_members else [[0, samples]]
        if video_coverage != [[0, frames]] and not has_video_baseline:
            video_coverage = [[0, frames]]
        # Uncovered delivery positions were initialized as generated above.
        # They are explicit generation spans, including the tail of an ordinary
        # continuation, rather than invented protected source samples.
    else:
        video_coverage = [[0, frames]]
        audio_coverage = [[0, samples]]
    return video, audio, video_coverage, audio_coverage, anchors


def _prepare_v2(request: H3Request, *, asset_map: Mapping[str, str] | None, fps: float, width: int, height: int, sample_rate: int, target_model_dimensions: Mapping[str, int] | None = None, channel_layout: str = "stereo") -> dict[str, Any]:
    if width <= 0 or height <= 0 or sample_rate <= 0:
        raise PreparationError("width, height, and sample_rate must be positive")
    fps_value = _rational(fps, "fps")
    frames = _frame_count(request.value["duration"], fps_value)
    samples = _sample_count(request.value["duration"], sample_rate)
    records = _resolve_assets(request, asset_map)
    if any(record["status"] != "resolved" for record in records):
        raise PreparationError("v2 preparation requires every managed baseline/mask/reference asset to be resolved")
    paths = {record["asset"]: Path(record["path"]) for record in records}
    source_hashes = {record["asset"]: record["sha256"] for record in records}
    baseline_digest, baseline_identity = _baseline_identity(request, source_hashes)
    video, audio, video_coverage, audio_coverage, anchors = _edit_ranges(request, frames=frames, samples=samples, fps=fps_value, sample_rate=sample_rate, width=width, height=height, assets=paths)
    model = dict(target_model_dimensions or {"frames": _model_steps(frames), "height": max(1, (height + 3) // 4), "width": max(1, (width + 3) // 4)})
    classified = classify_anchors(anchors, latent_steps=int(model["frames"]), unsupported_hard="restoration")
    require_supported_anchors(classified)
    try:
        artifact = PreparedAVMask.from_arrays(video_delivery=video, audio_delivery=audio, fps=fps_value, sample_rate=sample_rate, source_baseline_digest=baseline_digest, video_coverage=video_coverage, audio_coverage=audio_coverage, mapping={"geometry": "identity", "orientation": "identity", "temporal_policy": "explicit_half_open", "baseline_identity": baseline_identity}, channel_layout=channel_layout, source_hashes=source_hashes, native_padding_trim={"video": {"leading": 0, "trailing": 0}, "audio": {"leading": 0, "trailing": 0}}, target_model_dimensions=model, anchor_classification=classified)
    except PreparedAVMaskError as exc:
        raise PreparationError(str(exc)) from exc
    schedule = build_mask_schedule(normalize_legacy_v2(request))
    return {"schema_version": 2, "kind": "h3_av_preparation", "request_digest": request.digest, "request": request.value, "media": {"fps": float(fps_value), "width": width, "height": height, "sample_rate": sample_rate}, "assets": records, "unresolved_assets": [], "mask_schedule": schedule, "prepared_av_mask": artifact.to_manifest(), "artifact_digest": artifact.artifact_digest, "status": "prepared", "runtime_submission": "eligible"}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def normalize_legacy_v2(request: H3Request) -> H3Request:
    """Keep old compile/compose schedule consumers on their v1 contract."""

    value = {"version": 1, "operation": "edit", "source": {"asset": request.value["media"][0]["asset"], "range": [0, request.value["duration"]]}, "output": {"duration": request.value["duration"]}, "content": {"prompt": request.value["prompt"]}, "changes": {"video": [], "audio": []}, "references": [], "overrides": {}}
    return H3Request(value=value, digest=request.digest)


def prepare_request(
    request: H3Request,
    *,
    asset_map: Mapping[str, str] | None = None,
    fps: float = 24.0,
    width: int = 1024,
    height: int = 576,
    sample_rate: int = 48000,
    target_model_dimensions: Mapping[str, int] | None = None,
    channel_layout: str = "stereo",
) -> dict[str, Any]:
    """Create a deterministic preparation manifest without touching a runtime."""

    if fps <= 0 or width <= 0 or height <= 0 or sample_rate <= 0:
        raise PreparationError("fps, width, height, and sample_rate must be positive")
    if request.value.get("version") == 2:
        return _prepare_v2(request, asset_map=asset_map, fps=fps, width=width, height=height, sample_rate=sample_rate, target_model_dimensions=target_model_dimensions, channel_layout=channel_layout)
    if any("mask_asset" in change for change in request.value["changes"]["audio"]):
        raise PreparationError("audio mask assets are not supported")
    try:
        schedule = build_mask_schedule(request)
    except MaskScheduleError as exc:
        raise PreparationError(str(exc)) from exc
    if request.value["operation"] == "continue" and not request.value["changes"]["video"] and not request.value["changes"]["audio"]:
        source_start, source_end = request.value["source"]["range"]
        protected_end = source_end - source_start
        duration = request.value["output"]["duration"]
        if protected_end < duration:
            prefix = [[0.0, protected_end]] if protected_end > 0 else []
            tail = [[protected_end, duration]]
            schedule["video"].update({"generated_intervals": tail, "protected_intervals": prefix})
            schedule["audio"].update({"generated_intervals": tail, "protected_intervals": prefix})
            schedule["source_protected"] = False
            unsigned = {key: value for key, value in schedule.items() if key != "digest"}
            schedule["digest"] = hashlib.sha256(_canonical_json(unsigned)).hexdigest()
    assets = _resolve_assets(request, asset_map)
    unresolved = [record["asset"] for record in assets if record["status"] != "resolved"]
    # Managed identifiers are intentionally retained for the runtime, but a
    # local asset map must never silently contain a missing path.
    return {
        "schema_version": 1,
        "kind": "h3_av_preparation",
        "request_digest": request.digest,
        "request": request.value,
        "media": {
            "fps": float(fps),
            "width": int(width),
            "height": int(height),
            "sample_rate": int(sample_rate),
        },
        "assets": assets,
        "unresolved_assets": unresolved,
        "mask_schedule": schedule,
        "status": "prepared" if schedule["status"] == "ready" else "requires_resolution",
        "runtime_submission": "blocked_until_resolution" if schedule["status"] != "ready" else "eligible",
    }


def write_preparation(path: str | Path, manifest: Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination


__all__ = ["PreparationError", "prepare_request", "write_preparation"]
