"""Deterministic video/audio permission schedules for H3 requests.

The H3 graph may need a larger latent context than the user asked to change.
This module deliberately keeps the user-facing delivery permissions separate
from that implementation detail.  Nothing here guesses a track, region, or
duration: ambiguous requests are rejected or marked for explicit resolution.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping

from .request import H3Request


class MaskScheduleError(ValueError):
    """A request cannot be represented as a safe permission schedule."""


class PreparedAVMaskError(ValueError):
    """A delivery-domain AV mask is malformed or cannot be reloaded safely."""


def _interval(value: Iterable[float], *, path: str) -> tuple[float, float]:
    values = tuple(float(item) for item in value)
    if len(values) != 2 or values[0] < 0 or values[1] <= values[0]:
        raise MaskScheduleError(f"{path} must be a positive half-open interval")
    return values


def merge_intervals(intervals: Iterable[Iterable[float]]) -> list[list[float]]:
    """Merge touching/overlapping intervals without changing their meaning."""

    ordered = sorted((_interval(item, path="interval") for item in intervals), key=lambda item: item[0])
    merged: list[list[float]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return merged


def interval_difference(interval: Iterable[float], covered: Iterable[Iterable[float]]) -> list[list[float]]:
    """Return portions of *interval* not covered by *covered* intervals."""

    start, end = _interval(interval, path="interval")
    cursor = start
    result: list[list[float]] = []
    for other_start, other_end in merge_intervals(covered):
        if other_end <= cursor:
            continue
        if other_start >= end:
            break
        if other_start > cursor:
            result.append([cursor, min(other_start, end)])
        cursor = max(cursor, other_end)
        if cursor >= end:
            break
    if cursor < end:
        result.append([cursor, end])
    return result


def _area_key(area: Mapping[str, Any]) -> str:
    if area.get("full_frame") is True:
        return "full_frame"
    for key in ("mask_asset", "subjects", "rectangle", "polygon"):
        if key in area:
            return key + ":" + json.dumps(area[key], sort_keys=True, separators=(",", ":"))
    raise MaskScheduleError("area has no supported selector")


def _area_record(area: Mapping[str, Any], *, path: str) -> dict[str, Any]:
    key = _area_key(area)
    record: dict[str, Any] = {"key": key, "selector": dict(area)}
    if key == "full_frame":
        record["resolution"] = "exact"
    elif key.startswith("mask_asset:"):
        record["resolution"] = "supplied_mask"
    elif key.startswith("subjects:"):
        # Subject tracking is a separate, runtime-specific operation.  Never
        # claim pixel accuracy before it has produced a mask artifact.
        record["resolution"] = "requires_resolution"
        record["requires_resolution"] = True
    else:
        record["resolution"] = "geometry"
    record["path"] = path
    return record


def _bounded_duration(request: H3Request) -> float:
    value = request.value
    if "duration" in value.get("output", {}):
        return float(value["output"]["duration"])
    candidates: list[float] = []
    source = value.get("source")
    if isinstance(source, Mapping) and source.get("range"):
        candidates.append(float(source["range"][1]))
    for domain in ("video", "audio"):
        candidates.extend(float(change["during"][1]) for change in value["changes"][domain])
    if candidates:
        return max(candidates)
    raise MaskScheduleError(
        "output.duration is required when the request has no source range or bounded change"
    )


def build_mask_schedule(request: H3Request) -> dict[str, Any]:
    """Compile normalized request changes into explicit delivery permissions."""

    value = request.value
    duration = _bounded_duration(request)
    video_changes: list[dict[str, Any]] = []
    audio_changes: list[dict[str, Any]] = []
    requires_resolution: list[str] = []

    for index, change in enumerate(value["changes"]["video"]):
        interval = _interval(change["during"], path=f"changes.video[{index}].during")
        if interval[1] > duration:
            raise MaskScheduleError(f"changes.video[{index}].during ends after output.duration")
        area = _area_record(change["area"], path=f"changes.video[{index}].area")
        if area.get("requires_resolution"):
            requires_resolution.append(area["path"])
        video_changes.append(
            {
                "index": index,
                "during": [interval[0], interval[1]],
                "area": area,
                "action": change["action"],
                **({"mask_asset": change["mask_asset"]} if "mask_asset" in change else {}),
            }
        )

    for index, change in enumerate(value["changes"]["audio"]):
        interval = _interval(change["during"], path=f"changes.audio[{index}].during")
        if interval[1] > duration:
            raise MaskScheduleError(f"changes.audio[{index}].during ends after output.duration")
        audio_changes.append(
            {
                "index": index,
                "during": [interval[0], interval[1]],
                "action": change["action"],
                **{key: change[key] for key in ("dialogue", "mask_asset", "stem") if key in change},
            }
        )

    # Source-free generation has no protected source.  For edits and
    # continuation, an empty schedule means preserve the whole source.
    source_protected = value["operation"] in {"edit", "continue"} and not video_changes and not audio_changes
    generated_video = merge_intervals(
        change["during"] for change in video_changes if change["action"] == "generate"
    )
    generated_audio = merge_intervals(
        change["during"] for change in audio_changes if change["action"] == "generate"
    )
    if value["operation"] == "generate" and not video_changes:
        generated_video = [[0.0, duration]]
    if value["operation"] == "generate" and not audio_changes:
        generated_audio = [[0.0, duration]]

    protected_video = merge_intervals(
        change["during"] for change in video_changes if change["action"] == "preserve"
    )
    protected_audio = merge_intervals(
        change["during"] for change in audio_changes if change["action"] == "preserve"
    )
    # A source-backed request protects every unmentioned part of each domain.
    # This is the key fail-closed rule: a caller must opt a region/time range
    # into generation; it is never implicitly allowed to drift.
    if value["operation"] in {"edit", "continue"}:
        protected_video = merge_intervals(
            [*protected_video, *interval_difference([0.0, duration], generated_video)]
        )
        protected_audio = merge_intervals(
            [*protected_audio, *interval_difference([0.0, duration], generated_audio)]
        )
    if source_protected:
        protected_video = [[0.0, duration]]
        protected_audio = [[0.0, duration]]

    schedule = {
        "schema_version": 1,
        "request_digest": request.digest,
        "operation": value["operation"],
        "duration": duration,
        "video": {
            "changes": video_changes,
            "generated_intervals": generated_video,
            "protected_intervals": protected_video,
        },
        "audio": {
            "changes": audio_changes,
            "generated_intervals": generated_audio,
            "protected_intervals": protected_audio,
        },
        "source_protected": source_protected,
        "requires_resolution": sorted(requires_resolution),
        "status": "requires_resolution" if requires_resolution else "ready",
    }
    encoded = json.dumps(schedule, sort_keys=True, separators=(",", ":")).encode("utf-8")
    schedule["digest"] = hashlib.sha256(encoded).hexdigest()
    return schedule


# --- prepared delivery-domain AV mask ------------------------------------

_POLARITY = "black_preserve_white_edit"
_BITPACK_ENCODING = "bitpack-msb-v1"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _as_python(value: Any) -> Any:
    """Convert torch/numpy-like CPU values without making them managed state."""

    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    return value


def _binary_payload(value: Any, *, ndim: int, path: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    raw = _as_python(value)
    flat: list[int] = []

    def visit(node: Any, depth: int, shape: list[int]) -> None:
        if depth == ndim:
            if isinstance(node, bool):
                numeric = int(node)
            elif isinstance(node, (int, float)):
                numeric = node
            else:
                raise PreparedAVMaskError(f"{path} contains a non-numeric permission")
            if isinstance(numeric, float) and not math.isfinite(numeric):
                raise PreparedAVMaskError(f"{path} permissions must be finite")
            if numeric not in (0, 1, 0.0, 1.0):
                raise PreparedAVMaskError(f"{path} permissions must be binary 0/1")
            flat.append(int(numeric))
            return
        if not isinstance(node, (list, tuple)) or not node:
            raise PreparedAVMaskError(f"{path} must be a non-empty {ndim}D rectangular array")
        if len(shape) <= depth:
            shape.append(len(node))
        elif shape[depth] != len(node):
            raise PreparedAVMaskError(f"{path} must be rectangular")
        for child in node:
            visit(child, depth + 1, shape)

    shape: list[int] = []
    visit(raw, 0, shape)
    return tuple(shape), tuple(flat)


def _pack_bits(values: Iterable[int]) -> bytes:
    items = tuple(int(value) for value in values)
    packed = bytearray((len(items) + 7) // 8)
    for index, value in enumerate(items):
        if value:
            packed[index // 8] |= 1 << (7 - index % 8)
    return bytes(packed)


def _unpack_bits(payload: bytes, length: int, *, path: str) -> tuple[int, ...]:
    expected = (length + 7) // 8
    if len(payload) != expected:
        raise PreparedAVMaskError(f"{path} payload length does not match its declared shape")
    if length and expected and length % 8:
        unused = 8 - length % 8
        if payload[-1] & ((1 << unused) - 1):
            raise PreparedAVMaskError(f"{path} payload has non-zero trailing padding bits")
    return tuple((payload[index // 8] >> (7 - index % 8)) & 1 for index in range(length))


def _shape_product(shape: Iterable[int]) -> int:
    result = 1
    for value in shape:
        result *= int(value)
    return result


def _fraction(value: Any, *, path: str) -> Fraction:
    if isinstance(value, bool):
        raise PreparedAVMaskError(f"{path} must be a rational number")
    try:
        if isinstance(value, Fraction):
            result = value
        elif isinstance(value, (tuple, list)) and len(value) == 2:
            result = Fraction(int(value[0]), int(value[1]))
        elif isinstance(value, int):
            result = Fraction(value)
        elif isinstance(value, float) and math.isfinite(value):
            result = Fraction(str(value))
        elif isinstance(value, str):
            result = Fraction(value.replace(" ", ""))
        else:
            raise ValueError
    except (TypeError, ValueError, ZeroDivisionError):
        raise PreparedAVMaskError(f"{path} must be a rational number") from None
    if result <= 0:
        raise PreparedAVMaskError(f"{path} must be positive")
    return result


def _clock_manifest(*, kind: str, rate: Fraction, start: int, rate_key: str, start_key: str) -> dict[str, Any]:
    return {
        "kind": kind,
        rate_key: {"num": rate.numerator, "den": rate.denominator},
        start_key: int(start),
    }


def _coverage(value: Iterable[Iterable[int]] | None, *, length: int, path: str) -> tuple[tuple[int, int], ...]:
    if value is None:
        raise PreparedAVMaskError(f"{path} is required; coverage may not be inferred")
    result: list[tuple[int, int]] = []
    for index, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise PreparedAVMaskError(f"{path}[{index}] must be a half-open [start,end] interval")
        start, end = item
        if type(start) is not int or type(end) is not int or start < 0 or end <= start or end > length:
            raise PreparedAVMaskError(f"{path}[{index}] is outside its declared coverage")
        if result and start < result[-1][1]:
            raise PreparedAVMaskError(f"{path} must be ordered and non-overlapping")
        result.append((start, end))
    if not result:
        raise PreparedAVMaskError(f"{path} must not be empty")
    return tuple(result)


def _payload_manifest(payload: bytes, *, shape: tuple[int, ...]) -> dict[str, Any]:
    return {
        "encoding": _BITPACK_ENCODING,
        "shape": list(shape),
        "length": _shape_product(shape),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "data": base64.b64encode(payload).decode("ascii"),
    }


def _read_payload(item: Mapping[str, Any], *, path: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    if item.get("encoding") != _BITPACK_ENCODING:
        raise PreparedAVMaskError(f"{path} uses an unsupported payload encoding")
    shape = item.get("shape")
    if not isinstance(shape, list) or not shape or any(type(value) is not int or value < 1 for value in shape):
        raise PreparedAVMaskError(f"{path}.shape is invalid")
    expected_length = _shape_product(shape)
    if item.get("length") != expected_length or not isinstance(item.get("data"), str):
        raise PreparedAVMaskError(f"{path} has an invalid payload length")
    try:
        payload = base64.b64decode(item["data"], validate=True)
    except (ValueError, TypeError):
        raise PreparedAVMaskError(f"{path}.data is not valid base64") from None
    if item.get("sha256") != hashlib.sha256(payload).hexdigest():
        raise PreparedAVMaskError(f"{path}.sha256 does not match the payload")
    return tuple(shape), _unpack_bits(payload, expected_length, path=path)


def _default_model_dimensions(frame_count: int) -> dict[str, int]:
    from .kernel import temporal_cells

    steps = 1
    while temporal_cells(steps)[-1]["end"] < frame_count:
        steps += 1
    return {"frames": steps}


def _audio_envelope(values: tuple[int, ...], shape: tuple[int, int], sample_rate: int, ticks: int) -> tuple[int, ...]:
    channels, samples = shape
    result: list[int] = []
    for tick in range(ticks):
        start = min(samples, (tick * sample_rate) // 40)
        end = min(samples, math.ceil((tick + 1) * sample_rate / 40))
        result.append(1 if any(values[channel * samples + sample] for channel in range(channels) for sample in range(start, end)) else 0)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class PreparedAVMask:
    """Immutable output-domain AV permissions and their managed metadata.

    The two authoritative payloads are binary, lossless bit-packed arrays.  No
    H3 latent tensor is stored here; conversion is explicit at ``h3_masks``.
    """

    source_baseline_digest: str | None
    video_clock: Mapping[str, Any]
    audio_clock: Mapping[str, Any]
    video_shape: tuple[int, int, int]
    audio_shape: tuple[int, int]
    video_payload: bytes
    audio_payload: bytes
    video_coverage: tuple[tuple[int, int], ...]
    audio_coverage: tuple[tuple[int, int], ...]
    mapping: Mapping[str, Any]
    channel_layout: str
    source_hashes: Mapping[str, str]
    native_padding_trim: Mapping[str, Any]
    target_model_dimensions: Mapping[str, int]
    anchor_classification: tuple[Mapping[str, Any], ...]
    audio_envelope_payload: bytes
    audio_envelope_shape: tuple[int, int, int]

    def __post_init__(self) -> None:
        object.__setattr__(self, "video_clock", dict(_json_safe(self.video_clock)))
        object.__setattr__(self, "audio_clock", dict(_json_safe(self.audio_clock)))
        object.__setattr__(self, "mapping", dict(_json_safe(self.mapping)))
        object.__setattr__(self, "source_hashes", dict(_json_safe(self.source_hashes)))
        object.__setattr__(self, "native_padding_trim", dict(_json_safe(self.native_padding_trim)))
        object.__setattr__(self, "target_model_dimensions", dict(_json_safe(self.target_model_dimensions)))
        object.__setattr__(self, "anchor_classification", tuple(dict(_json_safe(item)) for item in self.anchor_classification))

    @classmethod
    def from_arrays(
        cls,
        *,
        video_delivery: Any,
        audio_delivery: Any,
        fps: Any = (24, 1),
        sample_rate: int = 48000,
        source_baseline_digest: str | None,
        video_coverage: Iterable[Iterable[int]] | None = None,
        audio_coverage: Iterable[Iterable[int]] | None = None,
        mapping: Mapping[str, Any] | None = None,
        channel_layout: str = "stereo",
        source_hashes: Mapping[str, str] | None = None,
        native_padding_trim: Mapping[str, Any] | None = None,
        target_model_dimensions: Mapping[str, int] | None = None,
        anchor_classification: Iterable[Mapping[str, Any]] = (),
        audio_ticks: int | None = None,
    ) -> "PreparedAVMask":
        video_shape, video_values = _binary_payload(video_delivery, ndim=3, path="video_delivery")
        audio_shape, audio_values = _binary_payload(audio_delivery, ndim=2, path="audio_delivery")
        fps_value = _fraction(fps, path="fps")
        if type(sample_rate) is not int or sample_rate <= 0:
            raise PreparedAVMaskError("sample_rate must be a positive integer")
        if not isinstance(channel_layout, str) or not channel_layout.strip():
            raise PreparedAVMaskError("channel_layout must be a non-empty string")
        channels, samples = audio_shape
        if channel_layout == "mono" and channels != 1:
            raise PreparedAVMaskError("mono channel_layout requires one audio channel")
        if channel_layout == "stereo" and channels != 2:
            raise PreparedAVMaskError("stereo channel_layout requires two audio channels")
        if audio_ticks is None:
            audio_ticks = max(1, math.ceil(samples * 40 / sample_rate))
        if type(audio_ticks) is not int or audio_ticks < 1:
            raise PreparedAVMaskError("audio_ticks must be a positive integer")
        model_dimensions = dict(target_model_dimensions or _default_model_dimensions(video_shape[0]))
        for key, value in model_dimensions.items():
            if type(value) is not int or value < 1:
                raise PreparedAVMaskError(f"target_model_dimensions.{key} must be a positive integer")
        return cls(
            source_baseline_digest=source_baseline_digest,
            video_clock=_clock_manifest(kind="video", rate=fps_value, start=0, rate_key="fps", start_key="start_frame"),
            audio_clock=_clock_manifest(kind="audio", rate=Fraction(sample_rate), start=0, rate_key="sample_rate", start_key="start_sample"),
            video_shape=video_shape,  # type: ignore[arg-type]
            audio_shape=audio_shape,  # type: ignore[arg-type]
            video_payload=_pack_bits(video_values),
            audio_payload=_pack_bits(audio_values),
            video_coverage=_coverage(video_coverage, length=video_shape[0], path="video.coverage"),
            audio_coverage=_coverage(audio_coverage, length=audio_shape[1], path="audio.coverage"),
            mapping=dict(mapping or {"geometry": "identity", "orientation": "identity", "temporal_policy": "explicit_half_open"}),
            channel_layout=channel_layout,
            source_hashes=dict(source_hashes or {}),
            native_padding_trim=dict(native_padding_trim or {"video": {"leading": 0, "trailing": 0}, "audio": {"leading": 0, "trailing": 0}}),
            target_model_dimensions=model_dimensions,
            anchor_classification=tuple(anchor_classification),
            audio_envelope_payload=_pack_bits(_audio_envelope(audio_values, audio_shape, sample_rate, audio_ticks)),
            audio_envelope_shape=(audio_ticks, 1, 1),
        )

    def video_delivery(self) -> tuple[tuple[tuple[int, ...], ...], ...]:
        values = _unpack_bits(self.video_payload, _shape_product(self.video_shape), path="video.payload")
        frames, height, width = self.video_shape
        return tuple(tuple(tuple(values[(frame * height + row) * width + column] for column in range(width)) for row in range(height)) for frame in range(frames))

    def audio_delivery(self) -> tuple[tuple[int, ...], ...]:
        values = _unpack_bits(self.audio_payload, _shape_product(self.audio_shape), path="audio.payload")
        channels, samples = self.audio_shape
        return tuple(tuple(values[channel * samples + sample] for sample in range(samples)) for channel in range(channels))

    def audio_sampling_envelope(self) -> tuple[int, ...]:
        return _unpack_bits(self.audio_envelope_payload, _shape_product(self.audio_envelope_shape), path="audio.sampling_envelope")

    def to_manifest(self) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "kind": "h3_prepared_av_mask",
            "domain": "output_delivery",
            "source_baseline_digest": self.source_baseline_digest,
            "video": {
                "clock": _json_safe(self.video_clock),
                "shape": {"frames": self.video_shape[0], "height": self.video_shape[1], "width": self.video_shape[2]},
                "polarity": _POLARITY,
                "coverage": [list(item) for item in self.video_coverage],
                "payload": _payload_manifest(self.video_payload, shape=self.video_shape),
            },
            "audio": {
                "clock": _json_safe(self.audio_clock),
                "shape": {"channels": self.audio_shape[0], "samples": self.audio_shape[1]},
                "polarity": _POLARITY,
                "coverage": [list(item) for item in self.audio_coverage],
                "channel_layout": self.channel_layout,
                "payload": _payload_manifest(self.audio_payload, shape=self.audio_shape),
                "sampling_envelope": _payload_manifest(self.audio_envelope_payload, shape=self.audio_envelope_shape),
                "sampling_policy": "union_all_channels_at_40hz;not_independent_latent_channels",
            },
            "mapping": _json_safe(self.mapping),
            "source_hashes": _json_safe(self.source_hashes),
            "native_padding_trim": _json_safe(self.native_padding_trim),
            "target_model_dimensions": _json_safe(self.target_model_dimensions),
            "anchors": _json_safe(self.anchor_classification),
        }
        manifest["artifact_digest"] = hashlib.sha256(_canonical_bytes(manifest)).hexdigest()
        return manifest

    @property
    def artifact_digest(self) -> str:
        return str(self.to_manifest()["artifact_digest"])

    @classmethod
    def from_manifest(cls, raw: Mapping[str, Any]) -> "PreparedAVMask":
        if raw.get("kind") != "h3_prepared_av_mask" or raw.get("schema_version") != 1:
            raise PreparedAVMaskError("unsupported prepared AV mask manifest")
        manifest = dict(raw)
        supplied_digest = manifest.pop("artifact_digest", None)
        if supplied_digest != hashlib.sha256(_canonical_bytes(manifest)).hexdigest():
            raise PreparedAVMaskError("prepared AV mask artifact digest does not match")
        video = manifest.get("video")
        audio = manifest.get("audio")
        if not isinstance(video, Mapping) or not isinstance(audio, Mapping):
            raise PreparedAVMaskError("prepared AV mask is missing video or audio metadata")
        if video.get("polarity") != _POLARITY or audio.get("polarity") != _POLARITY:
            raise PreparedAVMaskError("prepared AV mask polarity is unsupported")
        video_payload = video.get("payload")
        audio_payload = audio.get("payload")
        envelope_payload = audio.get("sampling_envelope")
        if not isinstance(video_payload, Mapping) or not isinstance(audio_payload, Mapping) or not isinstance(envelope_payload, Mapping):
            raise PreparedAVMaskError("prepared AV mask payloads are missing")
        video_shape, _ = _read_payload(video_payload, path="video.payload")
        audio_shape, _ = _read_payload(audio_payload, path="audio.payload")
        envelope_shape, _ = _read_payload(envelope_payload, path="audio.sampling_envelope")
        if video_shape != (video["shape"].get("frames"), video["shape"].get("height"), video["shape"].get("width")):
            raise PreparedAVMaskError("video payload shape does not match video metadata")
        if audio_shape != (audio["shape"].get("channels"), audio["shape"].get("samples")):
            raise PreparedAVMaskError("audio payload shape does not match audio metadata")
        if envelope_shape != (envelope_shape[0], 1, 1):
            raise PreparedAVMaskError("audio sampling envelope shape is invalid")
        video_bytes = base64.b64decode(video_payload["data"], validate=True)
        audio_bytes = base64.b64decode(audio_payload["data"], validate=True)
        envelope_bytes = base64.b64decode(envelope_payload["data"], validate=True)
        video_coverage = _coverage(video.get("coverage"), length=video_shape[0], path="video.coverage")
        audio_coverage = _coverage(audio.get("coverage"), length=audio_shape[1], path="audio.coverage")
        return cls(
            source_baseline_digest=manifest.get("source_baseline_digest"),
            video_clock=video.get("clock", {}),
            audio_clock=audio.get("clock", {}),
            video_shape=video_shape,  # type: ignore[arg-type]
            audio_shape=audio_shape,  # type: ignore[arg-type]
            video_payload=video_bytes,
            audio_payload=audio_bytes,
            video_coverage=video_coverage,
            audio_coverage=audio_coverage,
            mapping=manifest.get("mapping", {}),
            channel_layout=str(audio.get("channel_layout", "")),
            source_hashes=manifest.get("source_hashes", {}),
            native_padding_trim=manifest.get("native_padding_trim", {}),
            target_model_dimensions=manifest.get("target_model_dimensions", {}),
            anchor_classification=tuple(manifest.get("anchors", [])),
            audio_envelope_payload=envelope_bytes,
            audio_envelope_shape=envelope_shape,  # type: ignore[arg-type]
        )

    def h3_masks(
        self,
        *,
        latent_steps: int | None = None,
        latent_height: int | None = None,
        latent_width: int | None = None,
        audio_ticks: int | None = None,
        existing_video_mask: Any | None = None,
        existing_audio_mask: Any | None = None,
    ) -> dict[str, Any]:
        """Materialize only the graph-bound masks using T3's public helpers."""

        import torch

        from .kernel import (
            conservative_audio_tick_envelope,
            conservative_video_cell_mask,
            conservative_video_frame_mask,
            intersect_sampling_permissions,
        )

        dimensions = self.target_model_dimensions
        steps = latent_steps or int(dimensions.get("frames", 0))
        height = latent_height or int(dimensions.get("height", 0))
        width = latent_width or int(dimensions.get("width", 0))
        if min(steps, height, width) < 1:
            raise PreparedAVMaskError("target model video dimensions are required at the H3 boundary")
        ticks = audio_ticks or self.audio_envelope_shape[0]
        if ticks < 1:
            raise PreparedAVMaskError("target model audio ticks must be positive")
        video_delivery = torch.tensor(self.video_delivery(), dtype=torch.float32)
        video_frame = conservative_video_frame_mask(
            video_delivery,
            latent_steps=steps,
            latent_height=height,
            latent_width=width,
        )
        video_cell = conservative_video_cell_mask(
            video_delivery,
            latent_steps=steps,
            latent_height=height,
            latent_width=width,
        )
        audio_delivery = torch.tensor(self.audio_delivery(), dtype=torch.bool)
        sample_rate = int(self.audio_clock["sample_rate"]["num"]) // int(self.audio_clock["sample_rate"]["den"])
        audio_envelope = conservative_audio_tick_envelope(
            audio_delivery,
            sample_rate=sample_rate,
            audio_ticks=ticks,
        )
        if existing_video_mask is not None:
            video_cell = intersect_sampling_permissions(video_cell, existing_video_mask)
        if existing_audio_mask is not None:
            audio_envelope = intersect_sampling_permissions(audio_envelope, existing_audio_mask)
        return {
            "video_delivery": video_delivery,
            "audio_delivery": audio_delivery,
            "video_frame_mask": video_frame,
            "video_cell_mask": video_cell,
            "audio_envelope": audio_envelope,
            "audio_policy": "union_all_channels_at_40hz;not_independent_latent_channels",
        }


def load_prepared_av_mask(value: str | Path | Mapping[str, Any]) -> PreparedAVMask:
    """Reload a prepared artifact from its manifest or a preparation wrapper."""

    if isinstance(value, (str, Path)):
        path = Path(value).expanduser().resolve(strict=True)
        if path.is_symlink():
            raise PreparedAVMaskError("prepared AV mask path may not be a symlink")
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        raw = dict(value)
    if isinstance(raw.get("prepared_av_mask"), Mapping):
        raw = dict(raw["prepared_av_mask"])
    return PreparedAVMask.from_manifest(raw)


__all__ = [
    "MaskScheduleError",
    "build_mask_schedule",
    "interval_difference",
    "merge_intervals",
]
