"""Validation and deterministic normalization for the public H3 request."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping


class H3RequestError(ValueError):
    """A fail-closed request error with a user-facing path."""


@dataclass(frozen=True)
class H3Request:
    value: dict[str, Any]
    digest: str


# The generalized request vocabulary once included ``generate``, but this pack
# currently ships only source-backed executable graphs.  Keep that operation
# out of normalization so it cannot reach preparation or runtime admission.
_OPERATIONS = {"edit", "continue"}
_ACTIONS = {"generate", "preserve"}
_PURPOSES = {"appearance", "motion", "pose", "keyframe", "audio", "style"}
_STEMS = {"mix", "voice", "effects", "music"}
_OVERRIDES = {"model", "steps", "seed", "sampler", "guidance"}
_V2_PROFILE = {
    "id": "h3_av.native.v2",
    "fps": Fraction(24, 1),
    "sample_rate": 48000,
    "defaults": {
        "model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "steps": 8,
        "sampler": "res_multistep",
        "seed": 123456789,
        "guidance_scale": 0.95,
    },
}
_V2_MODALITIES = {"image", "video", "audio"}
_V2_ROLES = {"timeline", "reference"}
_V2_POLARITIES = {
    "black_preserve_white_edit",
    "black=preserve_white=editable",
    "black_protected_white_editable",
}
_V2_PLACEHOLDER = re.compile(
    r"(?:\{\{?[^{}]+\}?\}|<[^>]+>|\b(?:TODO|FIXME|PLACEHOLDER|INSERT[_ ]?TEXT)\b)",
    re.IGNORECASE,
)


def _object(value: Any, path: str, *, nullable: bool = False) -> dict[str, Any] | None:
    if value is None and nullable:
        return None
    if not isinstance(value, Mapping):
        raise H3RequestError(f"{path} must be an object")
    return dict(value)


def _unknown(value: Mapping[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise H3RequestError(f"{path} contains unsupported field(s): {', '.join(unknown)}")


def _nonblank(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise H3RequestError(f"{path} must be a non-empty string")
    return value.strip()


def _number(value: Any, path: str, *, minimum: float | None = None, exclusive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise H3RequestError(f"{path} must be a number")
    result = float(value)
    if minimum is not None and (result <= minimum if exclusive else result < minimum):
        operator = ">" if exclusive else ">="
        raise H3RequestError(f"{path} must be {operator} {minimum}")
    return result


def _interval(value: Any, path: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise H3RequestError(f"{path} must be [start, end]")
    start = _number(value[0], f"{path}[0]", minimum=0)
    end = _number(value[1], f"{path}[1]", minimum=0)
    if end <= start:
        raise H3RequestError(f"{path} must have end > start")
    return [start, end]


def _area(value: Any, path: str) -> dict[str, Any]:
    area = _object(value, path) or {}
    allowed = {"full_frame", "mask_asset", "subjects", "rectangle", "polygon"}
    _unknown(area, allowed, path)
    if not area:
        raise H3RequestError(f"{path} must select a region")
    if area.get("full_frame") is True:
        if len(area) != 1:
            raise H3RequestError(f"{path}.full_frame cannot be combined with another selector")
        return {"full_frame": True}
    if area.get("full_frame") not in (None, False):
        raise H3RequestError(f"{path}.full_frame must be true when present")
    selectors = [key for key in ("mask_asset", "subjects", "rectangle", "polygon") if key in area]
    if len(selectors) != 1:
        raise H3RequestError(f"{path} must contain exactly one non-full-frame selector")
    selector = selectors[0]
    if selector == "mask_asset":
        result = {selector: _nonblank(area[selector], f"{path}.mask_asset")}
    elif selector == "subjects":
        subjects = area[selector]
        if not isinstance(subjects, list) or not subjects or not all(isinstance(item, str) and item.strip() for item in subjects):
            raise H3RequestError(f"{path}.subjects must be a non-empty list of strings")
        result = {selector: [item.strip() for item in subjects]}
    elif selector == "rectangle":
        points = area[selector]
        if not isinstance(points, list) or len(points) != 4:
            raise H3RequestError(f"{path}.rectangle must be [x, y, width, height]")
        result = {selector: [_number(item, f"{path}.rectangle[{index}]") for index, item in enumerate(points)]}
    else:
        points = area[selector]
        if not isinstance(points, list) or len(points) < 3:
            raise H3RequestError(f"{path}.polygon must contain at least three points")
        result = {selector: [[_number(coord, f"{path}.polygon[{index}][{axis}]") for axis, coord in enumerate(point)] for index, point in enumerate(points)]}
    return result


def _video_change(value: Any, index: int) -> dict[str, Any]:
    path = f"changes.video[{index}]"
    item = _object(value, path) or {}
    _unknown(item, {"during", "area", "action", "mask_asset"}, path)
    result: dict[str, Any] = {
        "during": _interval(item.get("during"), f"{path}.during"),
        "area": _area(item.get("area"), f"{path}.area"),
        "action": item.get("action"),
    }
    if result["action"] not in _ACTIONS:
        raise H3RequestError(f"{path}.action must be generate or preserve")
    if "mask_asset" in item:
        result["mask_asset"] = _nonblank(item["mask_asset"], f"{path}.mask_asset")
    return result


def _audio_change(value: Any, index: int) -> dict[str, Any]:
    path = f"changes.audio[{index}]"
    item = _object(value, path) or {}
    _unknown(item, {"during", "action", "dialogue", "mask_asset", "stem"}, path)
    result: dict[str, Any] = {
        "during": _interval(item.get("during"), f"{path}.during"),
        "action": item.get("action"),
    }
    if result["action"] not in _ACTIONS:
        raise H3RequestError(f"{path}.action must be generate or preserve")
    for field in ("dialogue", "mask_asset"):
        if field in item:
            result[field] = _nonblank(item[field], f"{path}.{field}")
    if "stem" in item:
        stem = item["stem"]
        if stem not in _STEMS:
            raise H3RequestError(f"{path}.stem must be one of {sorted(_STEMS)}")
        result["stem"] = stem
    return result


def _normalize_v1(raw: Mapping[str, Any]) -> H3Request:
    if not isinstance(raw, Mapping):
        raise H3RequestError("request must be an object")
    _unknown(raw, {"version", "operation", "source", "output", "content", "changes", "references", "overrides"}, "request")
    if raw.get("version") != 1:
        raise H3RequestError("version must be 1")
    operation = raw.get("operation")
    if operation == "generate":
        raise H3RequestError(
            "source-free operation=generate is not admitted: this pack has no "
            "verified source-free H3 graph"
        )
    if operation not in _OPERATIONS:
        raise H3RequestError("operation must be edit or continue")

    source_raw = _object(raw.get("source"), "source", nullable=True)
    source: dict[str, Any] | None = None
    if source_raw is not None:
        _unknown(source_raw, {"asset", "range"}, "source")
        source = {"asset": _nonblank(source_raw.get("asset"), "source.asset")}
        if "range" in source_raw:
            source["range"] = _interval(source_raw["range"], "source.range")
    if operation in {"edit", "continue"} and source is None:
        raise H3RequestError(f"source is required for {operation}")
    if operation == "generate" and source is not None:
        raise H3RequestError("source must be null or omitted for generate")

    output_raw = _object(raw.get("output", {}), "output") or {}
    _unknown(output_raw, {"duration"}, "output")
    output: dict[str, Any] = {}
    if "duration" in output_raw:
        output["duration"] = _number(output_raw["duration"], "output.duration", minimum=0, exclusive=True)

    content_raw = _object(raw.get("content"), "content") or {}
    _unknown(content_raw, {"prompt"}, "content")
    content = {"prompt": _nonblank(content_raw.get("prompt"), "content.prompt")}

    changes_raw = _object(raw.get("changes"), "changes") or {}
    _unknown(changes_raw, {"video", "audio"}, "changes")
    video = changes_raw.get("video", [])
    audio = changes_raw.get("audio", [])
    if not isinstance(video, list) or not isinstance(audio, list):
        raise H3RequestError("changes.video and changes.audio must be arrays")
    changes = {
        "video": [_video_change(item, index) for index, item in enumerate(video)],
        "audio": [_audio_change(item, index) for index, item in enumerate(audio)],
    }

    references_raw = raw.get("references", [])
    if not isinstance(references_raw, list):
        raise H3RequestError("references must be an array")
    references: list[dict[str, str]] = []
    for index, value in enumerate(references_raw):
        path = f"references[{index}]"
        item = _object(value, path) or {}
        _unknown(item, {"asset", "purpose"}, path)
        purpose = item.get("purpose")
        if purpose not in _PURPOSES:
            raise H3RequestError(f"{path}.purpose must be one of {sorted(_PURPOSES)}")
        references.append({"asset": _nonblank(item.get("asset"), f"{path}.asset"), "purpose": purpose})

    overrides_raw = _object(raw.get("overrides", {}), "overrides") or {}
    _unknown(overrides_raw, _OVERRIDES, "overrides")
    overrides: dict[str, Any] = {}
    if "model" in overrides_raw:
        overrides["model"] = _nonblank(overrides_raw["model"], "overrides.model")
    if "steps" in overrides_raw:
        steps = overrides_raw["steps"]
        if type(steps) is not int or not 1 <= steps <= 200:
            raise H3RequestError("overrides.steps must be an integer from 1 to 200")
        overrides["steps"] = steps
    if "seed" in overrides_raw:
        seed = overrides_raw["seed"]
        if type(seed) is not int or seed < 0:
            raise H3RequestError("overrides.seed must be a non-negative integer")
        overrides["seed"] = seed
    if "sampler" in overrides_raw:
        overrides["sampler"] = _nonblank(overrides_raw["sampler"], "overrides.sampler")
    if "guidance" in overrides_raw:
        overrides["guidance"] = _number(overrides_raw["guidance"], "overrides.guidance", minimum=0)

    value = {
        "version": 1,
        "operation": operation,
        "source": source,
        "output": output,
        "content": content,
        "changes": changes,
        "references": references,
        "overrides": overrides,
    }
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return H3Request(value=value, digest=hashlib.sha256(encoded).hexdigest())


def load_request(path: str | Path, *, asset_modalities: Mapping[str, str] | None = None) -> H3Request:
    source = Path(path).expanduser().resolve(strict=True)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise H3RequestError(f"cannot read request {source}: {exc}") from exc
    try:
        if source.suffix.lower() in {".yaml", ".yml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:
                raise H3RequestError("YAML requests require PyYAML; use JSON or install PyYAML") from exc
            raw = yaml.safe_load(text)
        else:
            raw = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise H3RequestError(f"request is not valid JSON/YAML: {exc}") from exc
    return normalize_request(raw, asset_modalities=asset_modalities)


# --- v2 media-list normalization -----------------------------------------

def _request(value: dict[str, Any]) -> H3Request:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return H3Request(value=value, digest=hashlib.sha256(encoded).hexdigest())

def _v2_fraction(value: Any, path: str, *, minimum: Fraction = Fraction(0)) -> Fraction:
    if isinstance(value, bool):
        raise H3RequestError(f"{path} must be a rational number")
    try:
        if isinstance(value, int):
            result = Fraction(value)
        elif isinstance(value, float) and math.isfinite(value):
            result = Fraction(str(value))
        elif isinstance(value, str) and re.fullmatch(r"\s*[+-]?\d+(?:/\d+)?\s*", value):
            result = Fraction(value.replace(" ", ""))
        else:
            raise ValueError
    except (ValueError, ZeroDivisionError):
        raise H3RequestError(f"{path} must be a rational number") from None
    if result < minimum:
        raise H3RequestError(f"{path} must be >= {float(minimum):g}")
    return result


def _v2_json_number(value: Fraction) -> int | float:
    return value.numerator if value.denominator == 1 else float(value)


def _v2_fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _v2_clock(value: Fraction, unit: str, path: str) -> int:
    clock = _V2_PROFILE["fps"] if unit == "frames" else Fraction(_V2_PROFILE["sample_rate"])
    resolved = value * clock
    if resolved.denominator != 1:
        raise H3RequestError(f"{path} is not representable on the {unit[:-1]} clock")
    return resolved.numerator


def _v2_interval(value: Any, path: str, unit: str) -> tuple[list[int | float], list[int]]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise H3RequestError(f"{path} must be [start, end]")
    start = _v2_fraction(value[0], f"{path}[0]")
    end = _v2_fraction(value[1], f"{path}[1]")
    if end <= start:
        raise H3RequestError(f"{path} must have end > start")
    resolved = [_v2_clock(start, unit, f"{path}[0]"), _v2_clock(end, unit, f"{path}[1]")]
    return [_v2_json_number(start), _v2_json_number(end)], resolved


def _v2_asset(value: Any, path: str, asset_modalities: Mapping[str, str] | None) -> tuple[str, str | None]:
    modality: str | None = None
    if isinstance(value, Mapping):
        _unknown(value, {"id", "asset", "modality", "inspection"}, path)
        asset = value.get("id", value.get("asset"))
        inspection = value.get("inspection")
        if isinstance(inspection, Mapping):
            modality = inspection.get("modality")
        modality = value.get("modality", modality)
    else:
        asset = value
    asset_id = _nonblank(asset, path)
    if modality is None and asset_modalities is not None:
        modality = asset_modalities.get(asset_id)
    if modality is not None and modality not in _V2_MODALITIES:
        raise H3RequestError(f"{path}.modality must be image, video, or audio")
    return asset_id, modality


def _v2_at(value: Any, path: str) -> tuple[dict[str, int | float], int]:
    item = _object(value, path) or {}
    _unknown(item, {"frame", "seconds"}, path)
    if len(item) != 1:
        raise H3RequestError(f"{path} must contain exactly one of frame or seconds")
    if "frame" in item:
        frame = _v2_fraction(item["frame"], f"{path}.frame")
        if frame.denominator != 1:
            raise H3RequestError(f"{path}.frame must be an integer")
        return {"frame": frame.numerator}, frame.numerator
    seconds = _v2_fraction(item["seconds"], f"{path}.seconds")
    return {"seconds": _v2_json_number(seconds)}, _v2_clock(seconds, "frames", f"{path}.seconds")


def _v2_geometry(value: Mapping[str, Any], path: str) -> dict[str, Any]:
    selectors = [key for key in ("full_frame", "rectangle", "polygon") if key in value]
    if len(selectors) != 1:
        raise H3RequestError(f"{path} must select exactly one full-frame or geometry region")
    selector = selectors[0]
    if selector == "full_frame":
        if value[selector] is not True:
            raise H3RequestError(f"{path}.full_frame must be true")
        return {"full_frame": True}
    if selector == "rectangle":
        coords = value[selector]
        if not isinstance(coords, (list, tuple)) or len(coords) != 4:
            raise H3RequestError(f"{path}.rectangle must be [x, y, width, height]")
        result = [_number(item, f"{path}.rectangle[{i}]", minimum=0) for i, item in enumerate(coords)]
        if result[2] <= 0 or result[3] <= 0:
            raise H3RequestError(f"{path}.rectangle width and height must be > 0")
        return {"rectangle": result}
    points = value[selector]
    if not isinstance(points, (list, tuple)) or len(points) < 3:
        raise H3RequestError(f"{path}.polygon must contain at least three points")
    if any(not isinstance(point, (list, tuple)) or len(point) != 2 for point in points):
        raise H3RequestError(f"{path}.polygon points must be [x, y]")
    return {"polygon": [[_number(coord, f"{path}.polygon[{i}][{axis}]") for axis, coord in enumerate(point)] for i, point in enumerate(points)]}


def _v2_mask(value: Any, path: str, asset_modalities: Mapping[str, str] | None) -> dict[str, Any]:
    if isinstance(value, str):
        asset, modality = _v2_asset(value, path, asset_modalities)
        if modality is not None and modality not in {"image", "video"}:
            raise H3RequestError(f"{path} must reference an image/video mask")
        return {"asset": asset, "polarity": "black_preserve_white_edit"}
    item = _object(value, path) or {}
    _unknown(item, {"asset", "full_frame", "rectangle", "polygon", "geometry", "range", "polarity", "shape"}, path)
    if "geometry" in item:
        geometry = _object(item["geometry"], f"{path}.geometry") or {}
        _unknown(geometry, {"full_frame", "rectangle", "polygon"}, f"{path}.geometry")
        item = {**{key: val for key, val in item.items() if key != "geometry"}, **geometry}
    geometry_keys = {"full_frame", "rectangle", "polygon"}
    if "asset" in item and geometry_keys.intersection(item):
        raise H3RequestError(f"{path} cannot combine a supplied asset with geometry")
    if "asset" not in item and not geometry_keys.intersection(item):
        raise H3RequestError(f"{path} must contain an asset or geometry")
    result = {}
    if "asset" in item:
        asset, modality = _v2_asset(item["asset"], f"{path}.asset", asset_modalities)
        if modality is not None and modality not in {"image", "video"}:
            raise H3RequestError(f"{path}.asset must reference an image/video mask")
        result["asset"] = asset
    else:
        result.update(_v2_geometry(item, path))
    if "range" in item:
        result["range"], _ = _v2_interval(item["range"], f"{path}.range", "frames")
    if "shape" in item:
        shape = _object(item["shape"], f"{path}.shape") or {}
        _unknown(shape, {"frames", "height", "width"}, f"{path}.shape")
        if set(shape) != {"frames", "height", "width"} or any(type(shape[key]) is not int or shape[key] <= 0 for key in shape):
            raise H3RequestError(f"{path}.shape must contain positive integer frames, height, and width")
        result["shape"] = {key: shape[key] for key in ("frames", "height", "width")}
    if item.get("polarity", "black_preserve_white_edit") not in _V2_POLARITIES:
        raise H3RequestError(f"{path}.polarity must be black-preserve/white-edit")
    result["polarity"] = "black_preserve_white_edit"
    return result


def _v2_guides(value: Any, path: str) -> list[str]:
    if isinstance(value, str):
        return [_nonblank(value, path)]
    if not isinstance(value, list) or not value:
        raise H3RequestError(f"{path} must be a non-empty ordered list of reference ids")
    return [_nonblank(item, f"{path}[{i}]") for i, item in enumerate(value)]


def _v2_dialogue(value: Any, path: str) -> str:
    text = _nonblank(value, path)
    if _V2_PLACEHOLDER.search(text):
        raise H3RequestError(f"{path} must be literal dialogue; unresolved placeholder found")
    return text


def _v2_settings(value: Any) -> dict[str, Any]:
    item = _object(value, "settings") or {}
    _unknown(item, {"model", "steps", "sampler", "seed", "guidance_scale", "guidance"}, "settings")
    if "guidance" in item and "guidance_scale" in item:
        raise H3RequestError("settings.guidance is an alias for guidance_scale, not a second setting")
    result = dict(_V2_PROFILE["defaults"])
    if "model" in item:
        result["model"] = _nonblank(item["model"], "settings.model")
    if "sampler" in item:
        result["sampler"] = _nonblank(item["sampler"], "settings.sampler")
    if "steps" in item:
        if type(item["steps"]) is not int or not 1 <= item["steps"] <= 200:
            raise H3RequestError("settings.steps must be an integer from 1 to 200")
        result["steps"] = item["steps"]
    if "seed" in item:
        if type(item["seed"]) is not int or item["seed"] < 0:
            raise H3RequestError("settings.seed must be a non-negative integer")
        result["seed"] = item["seed"]
    if "guidance_scale" in item or "guidance" in item:
        result["guidance_scale"] = _number(item.get("guidance_scale", item.get("guidance")), "settings.guidance_scale", minimum=0)
    return result


def _normalize_v2(raw: Mapping[str, Any], *, asset_modalities: Mapping[str, str] | None = None) -> H3Request:
    _unknown(raw, {"version", "prompt", "duration", "media", "settings"}, "request")
    if raw.get("version") != 2:
        raise H3RequestError("version must be 1 or 2")
    prompt = _nonblank(raw.get("prompt"), "prompt")
    media_raw = raw.get("media")
    if not isinstance(media_raw, list) or not media_raw:
        raise H3RequestError("media must be a non-empty array")
    duration = None if raw.get("duration") is None else _v2_json_number(_v2_fraction(raw["duration"], "duration"))
    if duration == 0:
        raise H3RequestError("duration must be > 0 when supplied")
    settings = _v2_settings(raw.get("settings", {}))
    ids: set[str] = set()
    occurrences: list[dict[str, Any]] = []
    model_counts = {"image": 0, "video": 0, "audio": 0}
    for index, raw_item in enumerate(media_raw):
        path = f"media[{index}]"
        item = _object(raw_item, path) or {}
        _unknown(item, {"id", "asset", "role", "modality", "at", "range", "edit", "audio", "hard", "latent_pin"}, path)
        role = item.get("role")
        if role not in _V2_ROLES:
            raise H3RequestError(f"{path}.role must be timeline or reference")
        asset, inspected = _v2_asset(item.get("asset"), f"{path}.asset", asset_modalities)
        modality = item.get("modality", inspected)
        if modality is not None and modality not in _V2_MODALITIES:
            raise H3RequestError(f"{path}.modality must be image, video, or audio")
        identifier = item.get("id")
        if identifier is not None:
            identifier = _nonblank(identifier, f"{path}.id")
            if identifier in ids:
                raise H3RequestError(f"{path}.id is duplicated")
            ids.add(identifier)
        occurrence_id = identifier or f"occurrence-{index + 1}"
        occurrence: dict[str, Any] = {"occurrence_id": occurrence_id, "asset": asset, "role": role}
        if identifier is not None:
            occurrence["id"] = identifier
        if modality is not None:
            model_counts[modality] += 1
            label = {"image": "Picture", "video": "Video", "audio": "Audio"}[modality]
            occurrence.update({"modality": modality, "model_tag": f"<{label} {model_counts[modality]}>"})
        else:
            occurrence["inspection"] = "deferred"
        if "range" in item:
            occurrence["range"], occurrence["resolved_range"] = _v2_interval(item["range"], f"{path}.range", "frames" if modality != "audio" else "samples")
        if role == "timeline":
            if "at" not in item:
                raise H3RequestError(f"{path}.at is required for timeline media")
            at, at_frame = _v2_at(item["at"], f"{path}.at")
            occurrence.update({"at": at, "resolved_at": {"unit": "frames", "value": at_frame}, "hard": item.get("hard", False)})
            if type(occurrence["hard"]) is not bool:
                raise H3RequestError(f"{path}.hard must be boolean")
            if "latent_pin" in item:
                if type(item["latent_pin"]) is not bool:
                    raise H3RequestError(f"{path}.latent_pin must be boolean")
                if item["latent_pin"] and not occurrence["hard"]:
                    raise H3RequestError(f"{path}.latent_pin requires hard=true")
                occurrence["latent_pin"] = item["latent_pin"]
            edits_raw = item.get("edit", [])
            if not isinstance(edits_raw, list):
                raise H3RequestError(f"{path}.edit must be an array")
            edits: list[dict[str, Any]] = []
            streams: dict[str, list[list[int]]] = {"video": [], "audio": []}
            for edit_index, raw_edit in enumerate(edits_raw):
                edit_path = f"{path}.edit[{edit_index}]"
                edit = _object(raw_edit, edit_path) or {}
                _unknown(edit, {"stream", "during", "mask", "guides", "text", "dialogue", "channels", "action", "keep", "hard"}, edit_path)
                stream = edit.get("stream")
                if stream not in {"video", "audio"}:
                    raise H3RequestError(f"{edit_path}.stream must be video or audio")
                action = edit.get("action", "generate")
                if edit.get("keep") is True:
                    if "action" in edit and action != "preserve":
                        raise H3RequestError(f"{edit_path}.keep conflicts with action")
                    action = "preserve"
                if action not in {"generate", "preserve"}:
                    raise H3RequestError(f"{edit_path}.action must be generate or preserve")
                if "text" in edit and "dialogue" in edit:
                    raise H3RequestError(f"{edit_path} cannot contain both text and dialogue")
                if "during" in edit:
                    during, resolved = _v2_interval(edit["during"], edit_path + ".during", "frames" if stream == "video" else "samples")
                elif occurrence.get("range"):
                    during = [0, occurrence["range"][1] - occurrence["range"][0]]
                    _, resolved = _v2_interval(during, edit_path + ".during", "frames" if stream == "video" else "samples")
                else:
                    raise H3RequestError(f"{edit_path}.during is required when the timeline item has no range")
                for previous in streams[stream]:
                    if resolved[0] < previous[1] and previous[0] < resolved[1]:
                        raise H3RequestError(f"{edit_path} conflicts with another {stream} edit")
                streams[stream].append(resolved)
                normalized: dict[str, Any] = {"stream": stream, "during": during, "resolved": {"unit": "frames" if stream == "video" else "samples", "range": resolved}, "action": action}
                if stream == "video":
                    normalized["mask"] = _v2_mask(edit.get("mask", {"full_frame": True}), edit_path + ".mask", asset_modalities)
                if "channels" in edit or stream == "audio":
                    channels = edit.get("channels", "all")
                    if channels != "all" and (not isinstance(channels, list) or not channels or any(type(channel) is not int or channel < 0 for channel in channels) or len(set(channels)) != len(channels)):
                        raise H3RequestError(f"{edit_path}.channels must be 'all' or unique non-negative indexes")
                    normalized["channels"] = channels
                if "text" in edit or "dialogue" in edit:
                    if stream != "audio":
                        raise H3RequestError(f"{edit_path}.text/dialogue is only valid for audio edits")
                    normalized["text"] = _v2_dialogue(edit.get("text", edit.get("dialogue")), edit_path + ".text")
                if "guides" in edit:
                    normalized["guides"] = _v2_guides(edit["guides"], edit_path + ".guides")
                edits.append(normalized)
            occurrence["edit"] = edits
        else:
            if any(key in item for key in ("at", "edit", "hard", "latent_pin")):
                raise H3RequestError(f"{path} reference entries cannot contain placement or edit fields")
            if "audio" in item:
                if modality != "video" or type(item["audio"]) is not bool:
                    raise H3RequestError(f"{path}.audio is only valid for video references")
                occurrence["audio"] = item["audio"]
            elif modality == "video":
                occurrence["audio"] = True
        occurrences.append(occurrence)

    by_id = {item.get("id", item["occurrence_id"]): item for item in occurrences}
    placement_keys: set[int] = set()
    for item in occurrences:
        if item["role"] != "timeline":
            continue
        if item["resolved_at"]["value"] in placement_keys:
            raise H3RequestError("conflicting hard anchors share the same placement")
        placement_keys.add(item["resolved_at"]["value"])
        for edit in item["edit"]:
            guides = edit.get("guides", [])
            for guide in guides:
                target = by_id.get(guide)
                if target is None:
                    raise H3RequestError(f"guide {guide!r} is dangling")
                if target["role"] != "reference":
                    raise H3RequestError(f"guide {guide!r} points to timeline media, not a reference")
                guide_modality = target.get("modality")
                allowed = {"image", "video"} if edit["stream"] == "video" else {"audio", "video"}
                if guide_modality is not None and guide_modality not in allowed:
                    raise H3RequestError(f"guide {guide!r} has the wrong modality for a {edit['stream']} edit")
        if item.get("modality") is not None:
            for edit in item["edit"]:
                allowed = {"image", "video"} if edit["stream"] == "video" else {"audio", "video"}
                if item["modality"] not in allowed:
                    raise H3RequestError(f"media source has the wrong modality for a {edit['stream']} edit")

    if duration is None:
        ends: list[Fraction] = []
        for item in occurrences:
            if item["role"] == "timeline":
                start = Fraction(item["resolved_at"]["value"], _V2_PROFILE["fps"])
                span = Fraction(str(item["range"][1])) - Fraction(str(item["range"][0])) if item.get("range") else Fraction(1, _V2_PROFILE["fps"])
                ends.append(start + span)
        if not ends:
            raise H3RequestError("duration is required for a wholly generative request")
        duration = _v2_json_number(max(ends))
    duration_fraction = _v2_fraction(duration, "duration")
    if duration_fraction <= 0:
        raise H3RequestError("duration must be > 0")
    _v2_clock(duration_fraction, "frames", "duration")
    value = {
        "version": 2,
        "prompt": prompt,
        "duration": duration,
        "media": occurrences,
        "settings": settings,
        "profile": _V2_PROFILE["id"],
        "output_count": 1,
        "model_tags": {item["occurrence_id"]: item["model_tag"] for item in occurrences if "model_tag" in item},
    }
    return _request(value)


def normalize_request(raw: Mapping[str, Any], *, asset_modalities: Mapping[str, str] | None = None) -> H3Request:
    if not isinstance(raw, Mapping):
        raise H3RequestError("request must be an object")
    if raw.get("version") == 1:
        return _normalize_v1(raw)
    if raw.get("version") == 2:
        return _normalize_v2(raw, asset_modalities=asset_modalities)
    raise H3RequestError("version must be 1 or 2")


def read_prepared_request(
    raw: Mapping[str, Any],
    expected_digest: Any,
    *,
    require_normalized_v2: bool = False,
) -> H3Request:
    """Read a public request or validate the canonical value emitted by prepare.

    Prepared v2 values contain derived scheduling and occurrence identities.
    Reconstructing their public projection and normalizing it again verifies
    every derived value without widening the public request vocabulary.
    """

    if not isinstance(raw, Mapping):
        raise H3RequestError("prepared request must be an object")
    if not isinstance(expected_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
        raise H3RequestError("prepared request digest is missing or malformed")

    if raw.get("version") == 2:
        normalized_keys = {"profile", "output_count", "model_tags"}
        media = raw.get("media")
        has_derived = bool(normalized_keys.intersection(raw)) or (
            isinstance(media, list)
            and any(
                isinstance(item, Mapping)
                and bool({"occurrence_id", "model_tag", "resolved_range", "resolved_at"}.intersection(item))
                for item in media
            )
        )
        if has_derived:
            if not normalized_keys.issubset(raw):
                raise H3RequestError("normalized v2 request is missing derived profile fields")
            projected = dict(raw)
            for key in normalized_keys:
                projected.pop(key, None)
            projected_media: list[Any] = []
            if not isinstance(media, list):
                raise H3RequestError("normalized v2 request media must be an array")
            duration_fraction = _v2_fraction(raw.get("duration"), "duration")
            duration_ticks = round(duration_fraction * _V2_PROFILE["fps"])
            projected["duration"] = _v2_fraction_text(Fraction(duration_ticks, 1) / _V2_PROFILE["fps"])
            for index, value in enumerate(media):
                if not isinstance(value, Mapping):
                    raise H3RequestError(f"media[{index}] must be an object")
                item = dict(value)
                modality = item.get("modality")
                range_ticks = item.get("resolved_range")
                if isinstance(range_ticks, (list, tuple)) and len(range_ticks) == 2 and all(type(tick) is int for tick in range_ticks):
                    clock = Fraction(_V2_PROFILE["sample_rate"]) if modality == "audio" else _V2_PROFILE["fps"]
                    item["range"] = [_v2_fraction_text(Fraction(tick, 1) / clock) for tick in range_ticks]
                resolved_at = item.get("resolved_at")
                at = item.get("at")
                if (
                    isinstance(resolved_at, Mapping)
                    and type(resolved_at.get("value")) is int
                    and isinstance(at, Mapping)
                    and "seconds" in at
                ):
                    item["at"] = {
                        "seconds": _v2_fraction_text(Fraction(resolved_at["value"], 1) / _V2_PROFILE["fps"])
                    }
                for key in ("occurrence_id", "model_tag", "inspection", "resolved_range", "resolved_at"):
                    item.pop(key, None)
                edits = item.get("edit")
                if isinstance(edits, list):
                    projected_edits = []
                    for edit in edits:
                        if not isinstance(edit, Mapping):
                            projected_edits.append(edit)
                            continue
                        projected_edit = dict(edit)
                        resolved = edit.get("resolved")
                        if isinstance(resolved, Mapping):
                            ticks = resolved.get("range")
                            if isinstance(ticks, (list, tuple)) and len(ticks) == 2 and all(type(tick) is int for tick in ticks):
                                clock = Fraction(_V2_PROFILE["sample_rate"]) if edit.get("stream") == "audio" else _V2_PROFILE["fps"]
                                projected_edit["during"] = [_v2_fraction_text(Fraction(tick, 1) / clock) for tick in ticks]
                        mask = projected_edit.get("mask")
                        if isinstance(mask, Mapping) and isinstance(mask.get("range"), (list, tuple)) and len(mask["range"]) == 2:
                            mask_range = [_v2_fraction(part, f"media[{index}].edit.mask.range") for part in mask["range"]]
                            mask_ticks = [round(part * _V2_PROFILE["fps"]) for part in mask_range]
                            projected_edit["mask"] = {
                                **dict(mask),
                                "range": [_v2_fraction_text(Fraction(tick, 1) / _V2_PROFILE["fps"]) for tick in mask_ticks],
                            }
                        projected_edit.pop("resolved", None)
                        projected_edits.append(projected_edit)
                    item["edit"] = projected_edits
                projected_media.append(item)
            projected["media"] = projected_media
            request = normalize_request(projected)
            if request.value != dict(raw):
                raise H3RequestError("normalized v2 request contains contradictory derived fields")
            if _request(dict(raw)).digest != request.digest:
                raise H3RequestError("normalized v2 request is not in canonical serialized form")
        else:
            if require_normalized_v2:
                raise H3RequestError("prepared v2 request is missing normalized derived fields")
            request = normalize_request(raw)
    else:
        request = normalize_request(raw)

    if request.digest != expected_digest:
        raise H3RequestError("prepared request digest does not match its normalized request")
    return request
