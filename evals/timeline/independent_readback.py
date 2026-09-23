"""Coordinator-side readback for a disposable timeline evaluation.

The evaluated agent may describe the edit, but it cannot grade its own target.
This module follows the committed parent head and its pinned shot/internal
revisions, then resolves the public target locator against that exact closure.
It intentionally accepts an adapter protocol so the logic can be tested
without a live Runtime.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


class IndependentReadbackError(RuntimeError):
    """The target could not be resolved from the committed current closure."""


class ClosureReader(Protocol):
    def read_current_closure(
        self, project_id: str, timeline_id: str, *, head: str | None = None,
    ) -> Mapping[str, Any]: ...


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _id(row: Mapping[str, Any]) -> str | None:
    value = row.get("id", row.get("clip_id"))
    return str(value) if value is not None else None


def _media_digest(clip: Mapping[str, Any], registries: list[Mapping[str, Any]]) -> str | None:
    for key in ("media_id", "object_id", "digest", "source_ref", "composed_ref"):
        value = clip.get(key)
        if isinstance(value, str) and value:
            return value
    asset = clip.get("asset")
    if isinstance(asset, str):
        for registry in registries:
            assets = _mapping(registry).get("assets")
            record = _mapping(assets).get(asset)
            if isinstance(record, Mapping):
                for key in ("media_id", "object_id", "digest", "content_sha256"):
                    value = record.get(key)
                    if isinstance(value, str) and value:
                        return value if key != "content_sha256" else "sha256:" + value.removeprefix("sha256:")
    return None


def _clip_snapshot(clip: Mapping[str, Any], registries: list[Mapping[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": _id(clip),
        "asset": clip.get("asset"),
        "media_digest": _media_digest(clip, registries),
    }
    for key in ("at", "hold", "from", "to", "track", "clipType", "volume", "speed"):
        if key in clip:
            result[key] = clip[key]
    return result


def read_target_snapshot(
    adapter: ClosureReader,
    target: Mapping[str, Any],
    *,
    head: str | None = None,
) -> dict[str, Any]:
    """Read one public target from the actual current committed closure."""
    project_id = target.get("project_id")
    timeline_id = target.get("timeline_id")
    locator = _mapping(target.get("target_locator"))
    occurrence_id = locator.get("occurrence_id")
    shot_id = locator.get("shot_id")
    selector_id = locator.get("selector_clip_id")
    if not all(isinstance(value, str) and value for value in (project_id, timeline_id, occurrence_id, shot_id, selector_id)):
        raise IndependentReadbackError("public target is missing project/timeline/target_locator IDs")

    closure = _mapping(adapter.read_current_closure(project_id, timeline_id, head=head))
    parent = _mapping(closure.get("parent_revision"))
    parent_payload = _mapping(parent.get("payload"))
    occurrences = _rows(parent_payload.get("occurrences"))
    occurrence = next((row for row in occurrences if row.get("occurrence_id") == occurrence_id), None)
    if occurrence is None:
        raise IndependentReadbackError(f"target occurrence is not present at committed head: {occurrence_id}")
    if occurrence.get("shot_id") != shot_id:
        raise IndependentReadbackError("target occurrence now points at a different shot identity")
    shot_revision_id = occurrence.get("shot_revision_id", occurrence.get("revision_id"))
    shots = _rows(closure.get("shot_revisions"))
    shot = next((row for row in shots if row.get("shot_id") == shot_id and row.get("revision_id") == shot_revision_id), None)
    if shot is None:
        raise IndependentReadbackError("target occurrence pins a shot revision absent from the exact closure")
    internal_revision_id = shot.get("internal_timeline_revision_id")
    internals = _rows(closure.get("internal_timeline_revisions"))
    internal = next((row for row in internals if row.get("revision_id") == internal_revision_id), None)
    if internal is None:
        raise IndependentReadbackError("target shot pins an internal revision absent from the exact closure")
    internal_payload = _mapping(internal.get("payload"))
    parent_clips = _rows(parent_payload.get("clips"))
    internal_clips = _rows(internal_payload.get("clips"))
    registries = [_mapping(parent_payload.get("registry")), _mapping(internal_payload.get("registry"))]
    selector = next((clip for clip in internal_clips if _id(clip) == selector_id), None)
    if selector is None:
        raise IndependentReadbackError(f"target selector clip is not present in the target internal timeline: {selector_id}")

    def find_clip(clip_id: Any) -> Mapping[str, Any] | None:
        if not isinstance(clip_id, str) or not clip_id:
            return None
        return next((clip for clip in [*internal_clips, *parent_clips] if _id(clip) == clip_id), None)

    voice = find_clip(locator.get("voice_clip_id"))
    overlay = find_clip(locator.get("frame_overlay_clip_id"))
    return {
        "project_id": project_id,
        "timeline_id": timeline_id,
        "head_revision_id": closure.get("head_revision_id", parent.get("revision_id")),
        "occurrence_id": occurrence_id,
        "shot_id": shot_id,
        "shot_revision_id": shot_revision_id,
        "selector_clip_id": selector_id,
        "active_media_digest": _media_digest(selector, registries),
        "selector": _clip_snapshot(selector, registries),
        "timing": {
            "at": selector.get("at"),
            "hold": selector.get("hold"),
            "occurrence_duration_ms": occurrence.get("duration_ms"),
            "occurrence_start_ms": _mapping(occurrence.get("placement")).get("start_ms"),
        },
        "voice_clip_id": _id(voice) if voice is not None else None,
        "voice": _clip_snapshot(voice, registries) if voice is not None else None,
        "frame_overlay_clip_id": _id(overlay) if overlay is not None else None,
        "frame_overlay": _clip_snapshot(overlay, registries) if overlay is not None else None,
    }


__all__ = ["ClosureReader", "IndependentReadbackError", "read_target_snapshot"]
