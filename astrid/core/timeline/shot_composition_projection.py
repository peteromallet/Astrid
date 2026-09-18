"""Project one prepared shot-composition graph into renderer input.

The editor/Travel lane stores a shot as an immutable revision and places it in
the parent with an occurrence.  Renderers and inspection tools still consume
the ordinary Astrid timeline shape, so this module is the one deliberately
boring bridge between those two representations:

* the graph is validated before it is read;
* internal media, effects, text, and audio clips are copied losslessly;
* occurrence placement is applied in memory, with the same trim/speed rules
  as the timeline duration helpers;
* occurrence identity is retained in ``app.astrid_shot_composition`` rather
  than being inferred from overlapping time ranges; and
* empty children remain visible as metadata and as a bounded blank window.

It never reads or writes legacy ``pinnedShotGroups`` or ``clipType: shot``
data.  Legacy interpretation belongs exclusively to the explicit migration
module.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .duration import clip_timeline_duration
from .shot_composition import validate_shot_composition


class ShotCompositionProjectionError(ValueError):
    """The canonical graph cannot be represented by a flat timeline."""

    code = "unsupported_shot_composition"


@dataclass(frozen=True)
class ShotCompositionProjection:
    """Detached renderer-facing projection and its occurrence proof."""

    config: Mapping[str, Any]
    registry: Mapping[str, Any]
    occurrences: tuple[Mapping[str, Any], ...]
    outputs: tuple[Mapping[str, Any], ...]
    graph: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "config": copy.deepcopy(dict(self.config)),
            "registry": copy.deepcopy(dict(self.registry)),
            "occurrences": copy.deepcopy(list(self.occurrences)),
            "outputs": copy.deepcopy(list(self.outputs)),
            "graph": copy.deepcopy(dict(self.graph)),
        }


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ShotCompositionProjectionError(f"{path} must be an object")
    return value


def _number(value: Any, path: str, *, default: float | None = None) -> float:
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ShotCompositionProjectionError(f"{path} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ShotCompositionProjectionError(f"{path} must be finite")
    return result


def _seconds(value: Any, path: str, *, default: float = 0.0) -> float:
    """Read canonical milliseconds or renderer seconds deterministically."""
    if value is None:
        return default
    raw = _number(value, path)
    return raw / 1000.0 if path.endswith("_ms") else raw


def _clip_type(raw: Mapping[str, Any]) -> str:
    value = raw.get("clipType", raw.get("clip_type", raw.get("type", "media")))
    if not isinstance(value, str) or not value:
        raise ShotCompositionProjectionError("internal timeline clip type must be a non-empty string")
    if value == "shot":
        raise ShotCompositionProjectionError("deeper shot nesting is unsupported")
    return value


def _timeline_clip(raw: Mapping[str, Any], *, path: str) -> dict[str, Any]:
    """Convert canonical snake-case fields while preserving ordinary fields."""
    result = copy.deepcopy(dict(raw))
    aliases = {
        "clip_type": "clipType",
        "asset_id": "asset",
        "from_ms": "from",
        "to_ms": "to",
    }
    for source, target in aliases.items():
        if source in result and target not in result:
            value = result.pop(source)
            result[target] = value / 1000.0 if source.endswith("_ms") else value
    if "at_ms" in result and "at" not in result:
        result["at"] = _seconds(result.pop("at_ms"), f"{path}.at_ms")
    if "duration_ms" in result and "hold" not in result and "to" not in result:
        result["hold"] = _seconds(result.pop("duration_ms"), f"{path}.duration_ms")
    result["clipType"] = _clip_type(result)
    if "id" not in result or not isinstance(result.get("id"), str) or not result["id"]:
        raise ShotCompositionProjectionError(f"{path}.id must be a non-empty string")
    if "at" not in result:
        result["at"] = 0.0
    if "track" not in result or not isinstance(result.get("track"), str) or not result["track"]:
        raise ShotCompositionProjectionError(f"{path}.track must be a non-empty string")
    # Canonical clip_type is a source spelling, not an extra renderer field.
    result.pop("clip_type", None)
    return result


def _duration(clip: Mapping[str, Any], *, path: str) -> float:
    try:
        return clip_timeline_duration(clip)
    except (TypeError, ValueError) as exc:
        raise ShotCompositionProjectionError(f"{path} has invalid timing: {exc}") from exc


def _base_parts(
    graph: Mapping[str, Any],
    *,
    base_config: Mapping[str, Any] | None,
    base_registry: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parent = graph.get("parent_composition")
    if isinstance(parent, Mapping):
        config_value = parent.get("config", parent.get("timeline"))
        registry_value = parent.get("registry")
    else:
        config_value = None
        registry_value = None
    if config_value is None:
        config_value = base_config
    if config_value is None:
        config_value = graph.get("config", graph.get("timeline", {}))
    if registry_value is None:
        registry_value = base_registry
    if registry_value is None:
        registry_value = graph.get("registry", {"assets": {}})
    config = copy.deepcopy(dict(_mapping(config_value, "base_config")))
    registry = copy.deepcopy(dict(_mapping(registry_value, "base_registry")))
    if not isinstance(config.get("clips", []), list):
        raise ShotCompositionProjectionError("base_config.clips must be a list")
    if not isinstance(config.get("tracks", []), list):
        raise ShotCompositionProjectionError("base_config.tracks must be a list")
    return config, registry


def _add_assets(registry: dict[str, Any], revision: Mapping[str, Any]) -> None:
    assets = registry.setdefault("assets", {})
    if not isinstance(assets, dict):
        raise ShotCompositionProjectionError("registry.assets must be an object")
    for raw in revision.get("assets", []):
        asset = _mapping(raw, "shot_revision.assets[]")
        asset_id = asset.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id:
            continue
        if asset_id in assets:
            continue
        digest = asset.get("digest")
        object_id = asset.get("object_id")
        entry = copy.deepcopy(dict(asset.get("source", {}))) if isinstance(asset.get("source"), Mapping) else {}
        if isinstance(object_id, str):
            entry.setdefault("media_id", object_id)
        if isinstance(digest, str):
            entry.setdefault("content_sha256", digest.removeprefix("sha256:"))
        entry.setdefault("type", "video")
        assets[asset_id] = entry


def _track_merge(config: dict[str, Any], timeline: Mapping[str, Any]) -> None:
    tracks = config.setdefault("tracks", [])
    by_id = {row.get("id"): row for row in tracks if isinstance(row, Mapping)}
    for raw in timeline.get("tracks", []):
        track = _mapping(raw, "internal_timeline_revision.timeline.tracks[]")
        track_id = track.get("id")
        if not isinstance(track_id, str) or not track_id:
            raise ShotCompositionProjectionError("internal track id must be a non-empty string")
        if track_id not in by_id:
            tracks.append(copy.deepcopy(dict(track)))
            by_id[track_id] = tracks[-1]


def _occurrence_window(occurrence: Mapping[str, Any], *, path: str) -> tuple[float, float, float]:
    start_raw = occurrence.get("at_ms", occurrence.get("placement", {}).get("start_ms") if isinstance(occurrence.get("placement"), Mapping) else occurrence.get("at"))
    duration_raw = occurrence.get("duration_ms", occurrence.get("duration"))
    start = _seconds(start_raw, f"{path}.at_ms" if "at_ms" in occurrence else f"{path}.at")
    duration = _seconds(duration_raw, f"{path}.duration_ms" if "duration_ms" in occurrence else f"{path}.duration", default=0.0)
    if duration < 0:
        raise ShotCompositionProjectionError(f"{path}.duration must not be negative")
    return start, start + duration, duration


def _project_clip(
    raw: Mapping[str, Any],
    *,
    occurrence: Mapping[str, Any],
    revision: Mapping[str, Any],
    occurrence_start: float,
    occurrence_end: float,
    occurrence_speed: float,
    path: str,
) -> dict[str, Any] | None:
    clip = _timeline_clip(raw, path=path)
    relative_at = _number(clip.get("at", 0), f"{path}.at", default=0.0)
    source_duration = _duration(clip, path=path)
    # The occurrence speed is a placement property.  Keep the authored child
    # speed intact and expose the placement value in the immutable app
    # namespace; timing remains the authored child window, as in the editor.
    absolute_at = occurrence_start + relative_at
    absolute_end = absolute_at + source_duration
    if absolute_at >= occurrence_end or absolute_end <= occurrence_start:
        return None
    clipped_end = min(absolute_end, occurrence_end)
    visible_duration = max(0.0, clipped_end - absolute_at)
    if visible_duration <= 0:
        return None
    if "hold" in clip:
        clip["hold"] = visible_duration
    elif "to" in clip:
        source_from = _number(clip.get("from", 0), f"{path}.from", default=0.0)
        child_speed = _number(clip.get("speed", 1), f"{path}.speed", default=1.0)
        clip["to"] = source_from + visible_duration * child_speed
    clip["at"] = absolute_at
    original_id = str(clip["id"])
    occurrence_id = occurrence["occurrence_id"]
    clip["id"] = f"{occurrence_id}:{original_id}"
    clip["shot_id"] = revision["shot_id"]
    clip["shot_occurrence_id"] = occurrence_id
    name = occurrence.get("name")
    if isinstance(name, str) and name:
        clip["shot_name"] = name
    # ``app`` is an existing schema escape hatch for immutable provenance and
    # keeps output identity/source-offset/gain/mute available to every
    # downstream consumer without widening ordinary clip authoring fields.
    app = clip.setdefault("app", {})
    if not isinstance(app, dict):
        app = {}
        clip["app"] = app
    app["astrid_shot_composition"] = {
        "project_id": occurrence.get("project_id"),
        "timeline_id": occurrence.get("timeline_id"),
        "shot_id": revision["shot_id"],
        "shot_revision_id": revision["revision_id"],
        "internal_timeline_revision_id": _mapping(revision["internal_timeline_revision"], f"{path}.revision").get("revision_id"),
        "occurrence_id": occurrence_id,
        "output_identity": occurrence.get("output_identity"),
        "stable_deep_link": occurrence.get("stable_deep_link"),
        "source_offset": copy.deepcopy(occurrence.get("source_offset", 0)),
        "speed": occurrence_speed,
        "gain": occurrence.get("gain", 1),
        "muted": bool(occurrence.get("muted", occurrence.get("mute", False))),
        "source_clip_id": original_id,
    }
    gain = occurrence.get("gain", 1)
    if isinstance(gain, (int, float)) and not isinstance(gain, bool):
        clip["volume"] = float(clip.get("volume", 1)) * float(gain)
    if bool(occurrence.get("muted", occurrence.get("mute", False))):
        clip["volume"] = 0
    return clip


def project_shot_composition(
    graph: Mapping[str, Any],
    *,
    base_config: Mapping[str, Any] | None = None,
    base_registry: Mapping[str, Any] | None = None,
) -> ShotCompositionProjection:
    """Project a prepared canonical graph into ordinary timeline input."""
    prepared = validate_shot_composition(graph)
    config, registry = _base_parts(prepared, base_config=base_config, base_registry=base_registry)
    revisions = {
        (row["shot_id"], row["revision_id"]): row
        for row in prepared["shot_revisions"]
    }
    config_clips = [copy.deepcopy(dict(item)) for item in config.get("clips", [])]
    occurrences: list[dict[str, Any]] = []
    outputs: list[dict[str, Any]] = []
    for index, raw_occurrence in enumerate(prepared["occurrences"]):
        occurrence = dict(_mapping(raw_occurrence, f"occurrences[{index}]"))
        key = (occurrence["shot_id"], occurrence["revision_id"])
        revision = revisions.get(key)
        if revision is None:
            raise ShotCompositionProjectionError(
                f"occurrences[{index}] references missing dependency {key[0]!r}/{key[1]!r}"
            )
        internal = _mapping(revision["internal_timeline_revision"], f"shot_revisions[{index}].internal_timeline_revision")
        timeline = _mapping(internal.get("timeline"), f"shot_revisions[{index}].internal_timeline_revision.timeline")
        if timeline.get("compositing") not in (None, "source_over", "normal"):
            raise ShotCompositionProjectionError("unsupported compositing mode in internal timeline")
        _track_merge(config, timeline)
        start, end, duration = _occurrence_window(occurrence, path=f"occurrences[{index}]")
        occurrence["project_id"] = prepared["project"]["project_id"]
        occurrence["timeline_id"] = prepared["primary_timeline"]["document_id"]
        occurrence["duration_seconds"] = duration
        occurrence["blank"] = not bool(timeline.get("clips"))
        occurrences.append(copy.deepcopy(occurrence))
        outputs.append({
            "occurrence_id": occurrence["occurrence_id"],
            "output_identity": occurrence["output_identity"],
            "stable_deep_link": occurrence["stable_deep_link"],
            "shot_id": occurrence["shot_id"],
            "revision_id": occurrence["revision_id"],
            "internal_timeline_revision_id": internal.get("revision_id"),
            "at_ms": occurrence.get("at_ms", round(start * 1000)),
            "duration_ms": occurrence.get("duration_ms", round(duration * 1000)),
            "blank": occurrence["blank"],
        })
        speed = _number(occurrence.get("speed", 1), f"occurrences[{index}].speed", default=1.0)
        if speed <= 0:
            raise ShotCompositionProjectionError(f"occurrences[{index}].speed must be positive")
        for clip_index, raw_clip in enumerate(timeline.get("clips", [])):
            clip = _mapping(raw_clip, f"shot_revisions[{index}].timeline.clips[{clip_index}]")
            projected = _project_clip(
                clip,
                occurrence=occurrence,
                revision=revision,
                occurrence_start=start,
                occurrence_end=end,
                occurrence_speed=speed,
                path=f"shot_revisions[{index}].timeline.clips[{clip_index}]",
            )
            if projected is not None:
                config_clips.append(projected)
        _add_assets(registry, revision)

    config["clips"] = config_clips
    app = config.setdefault("app", {})
    if not isinstance(app, dict):
        app = {}
        config["app"] = app
    app["astrid_shot_composition"] = {
        "schema_version": 1,
        "project_id": prepared["project"]["project_id"],
        "timeline_id": prepared["primary_timeline"]["document_id"],
        "occurrences": copy.deepcopy(occurrences),
        "outputs": copy.deepcopy(outputs),
    }
    return ShotCompositionProjection(
        config=config,
        registry=registry,
        occurrences=tuple(occurrences),
        outputs=tuple(outputs),
        graph=copy.deepcopy(prepared),
    )


project_canonical_shot_composition = project_shot_composition


__all__ = [
    "ShotCompositionProjection",
    "ShotCompositionProjectionError",
    "project_canonical_shot_composition",
    "project_shot_composition",
]
