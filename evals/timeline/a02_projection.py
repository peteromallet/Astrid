"""Coordinator-only A02 remove-occurrence projection and oracle.

This module is a preparation seam, not an edit executor.  It can materialize
the private target/readback schema only from a real four-shot closure with
independent voice clips and a parent music clip that reaches the composition
end.  The currently pinned intro deliberately fails these checks.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping


A02_PROJECTION = "remove_occurrence_compact.v1"
A02_SCHEMA = "astrid.timeline-eval.a02-four-shot-derivative.v1"
_MUSIC_TRACKS = {"music", "audio", "bgm"}
_VOICE_TRACKS = {"vo", "voice", "voiceover"}


class A02FixtureUnavailable(ValueError):
    """The supplied closure is not an actual A02 four-shot derivative."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _number(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise A02FixtureUnavailable(f"{label} is not numeric")
    return float(value)


def _duration(row: Mapping[str, Any], label: str) -> float:
    return _number(row.get("duration_ms", _mapping(row.get("placement")).get("duration_ms")), label)


def _start(row: Mapping[str, Any], label: str) -> float:
    return _number(row.get("start_ms", _mapping(row.get("placement")).get("start_ms")), label)


def _parent_payload(closure: Mapping[str, Any]) -> Mapping[str, Any]:
    parent = _mapping(closure.get("parent_revision"))
    payload = _mapping(parent.get("payload"))
    if not payload:
        raise A02FixtureUnavailable("parent composition payload is missing")
    return payload


def _shot_voice_ids(closure: Mapping[str, Any]) -> dict[str, tuple[str, ...]]:
    shot_revisions = {
        str(row.get("revision_id")): row
        for row in _rows(closure.get("shot_revisions"))
        if row.get("revision_id")
    }
    internals = {
        str(row.get("revision_id")): row
        for row in _rows(closure.get("internal_timeline_revisions"))
        if row.get("revision_id")
    }
    result: dict[str, tuple[str, ...]] = {}
    for revision_id, shot in shot_revisions.items():
        internal_id = shot.get("internal_timeline_revision_id")
        internal = internals.get(str(internal_id))
        voice_ids = tuple(
            str(clip.get("id")) for clip in _rows(_mapping(internal).get("payload", {}).get("clips"))
            if str(clip.get("track", "")).lower() in _VOICE_TRACKS and clip.get("id")
        )
        result[revision_id] = voice_ids
    return result


def _music_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for clip in _rows(payload.get("clips")):
        if str(clip.get("track", "")).lower() not in _MUSIC_TRACKS:
            continue
        at_key = "at_ms" if "at_ms" in clip else "at" if "at" in clip else "start_ms"
        hold_key = "duration_ms" if "duration_ms" in clip else "hold"
        at = _number(clip.get(at_key), "music clip start")
        hold = _number(clip.get(hold_key), "music clip duration")
        rows.append({
            "id": str(clip.get("id", "")),
            "at_ms": at * 1000 if at_key == "at" else at,
            "duration_ms": hold * 1000 if hold_key == "hold" else hold,
            "source_from": copy.deepcopy(clip.get("from", clip.get("source_from"))),
        })
    return rows


def _snapshot(closure: Mapping[str, Any]) -> dict[str, Any]:
    payload = _parent_payload(closure)
    occurrences = _rows(payload.get("occurrences"))
    records = []
    for index, row in enumerate(occurrences):
        occurrence_id = row.get("occurrence_id")
        shot_id = row.get("shot_id")
        if not isinstance(occurrence_id, str) or not isinstance(shot_id, str):
            raise A02FixtureUnavailable(f"occurrence {index} lacks occurrence_id/shot_id")
        start = _start(row, f"occurrence {occurrence_id} start")
        duration = _duration(row, f"occurrence {occurrence_id} duration")
        records.append({
            "occurrence_id": occurrence_id, "shot_id": shot_id,
            "shot_revision_id": row.get("shot_revision_id"),
            "start_ms": start, "duration_ms": duration,
            "end_ms": start + duration,
        })
    parent_duration = payload.get("duration_ms")
    if parent_duration is None:
        parent_duration = max((row["end_ms"] for row in records), default=0)
    return {
        "occurrences": records,
        "parent_duration_ms": _number(parent_duration, "parent duration"),
        "music_clips": _music_rows(payload),
    }


def materialize_a02_derivative(
    closure: Mapping[str, Any], *, target_occurrence_id: str,
) -> dict[str, Any]:
    """Create the coordinator-private A02 schema from a real four-shot closure."""
    snapshot = _snapshot(closure)
    occurrences = snapshot["occurrences"]
    if len(occurrences) != 4:
        raise A02FixtureUnavailable(
            f"A02 requires exactly four occurrences; closure has {len(occurrences)}"
        )
    if len({row["shot_id"] for row in occurrences}) != 4:
        raise A02FixtureUnavailable("A02 requires four independently owned shot IDs")
    target = next((row for row in occurrences if row["occurrence_id"] == target_occurrence_id), None)
    if target is None:
        raise A02FixtureUnavailable("A02 target occurrence is not in the four-shot closure")
    if not snapshot["music_clips"]:
        raise A02FixtureUnavailable("A02 requires a parent music clip")
    music_end = max(row["at_ms"] + row["duration_ms"] for row in snapshot["music_clips"])
    if music_end < snapshot["parent_duration_ms"]:
        raise A02FixtureUnavailable("A02 parent music must reach the composition end")
    voice_ids = _shot_voice_ids(closure)
    target_voice_ids = voice_ids.get(str(target.get("shot_revision_id")), ())
    if not target_voice_ids:
        raise A02FixtureUnavailable("A02 target shot has no own voice clip")
    source_head = _mapping(closure.get("parent_revision")).get("revision_id")
    if not isinstance(source_head, str) or not source_head:
        raise A02FixtureUnavailable("A02 source parent revision is missing")
    return {
        "kind": A02_SCHEMA,
        "case_id": "A02",
        "source_parent_revision_id": source_head,
        "readback_projection": A02_PROJECTION,
        "target_locator": {
            "remove_occurrence_id": target_occurrence_id,
            "remove_shot_id": target["shot_id"],
            "remove_voice_clip_ids": list(target_voice_ids),
        },
        "frame_rate": {"numerator": 30, "denominator": 1},
        "before": snapshot,
    }


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_a02_readback(
    before_closure: Mapping[str, Any], after_closure: Mapping[str, Any], *,
    target_occurrence_id: str,
) -> list[str]:
    """Return deterministic semantic failures for a committed A02 readback."""
    errors: list[str] = []
    before = _snapshot(before_closure)
    after = _snapshot(after_closure)
    target = next((row for row in before["occurrences"] if row["occurrence_id"] == target_occurrence_id), None)
    if target is None:
        return ["before closure does not contain the requested removal target"]
    removed_duration = target["duration_ms"]
    remaining = [row for row in before["occurrences"] if row["occurrence_id"] != target_occurrence_id]
    actual_by_id = {row["occurrence_id"]: row for row in after["occurrences"]}
    if target_occurrence_id in actual_by_id:
        errors.append("removed occurrence remains active")
    if set(actual_by_id) != {row["occurrence_id"] for row in remaining}:
        errors.append("remaining occurrence membership differs from the four-shot removal")
    for row in remaining:
        actual = actual_by_id.get(row["occurrence_id"])
        if actual is None:
            continue
        expected_start = row["start_ms"] if row["start_ms"] < target["start_ms"] else row["start_ms"] - removed_duration
        if actual["start_ms"] != expected_start:
            errors.append(f"occurrence {row['occurrence_id']} was not compacted to {expected_start:g}ms")
        if actual["duration_ms"] != row["duration_ms"]:
            errors.append(f"occurrence {row['occurrence_id']} duration changed")
        if actual["shot_id"] != row["shot_id"]:
            errors.append(f"occurrence {row['occurrence_id']} shot identity changed")
    expected_parent_duration = before["parent_duration_ms"] - removed_duration
    if after["parent_duration_ms"] != expected_parent_duration:
        errors.append("parent duration did not shrink by the removed occurrence duration")
    before_music = {row["id"]: row for row in before["music_clips"]}
    after_music = {row["id"]: row for row in after["music_clips"]}
    if set(before_music) != set(after_music):
        errors.append("parent music clip membership changed")
    for clip_id, row in before_music.items():
        actual = after_music.get(clip_id)
        if actual is None:
            continue
        if actual["at_ms"] != row["at_ms"] or actual["source_from"] != row["source_from"]:
            errors.append(f"music clip {clip_id} source start changed")
        expected_duration = expected_parent_duration - row["at_ms"]
        if actual["duration_ms"] != expected_duration:
            errors.append(f"music clip {clip_id} was not trimmed to the new parent end")
    return errors


__all__ = ["A02FixtureUnavailable", "A02_PROJECTION", "A02_SCHEMA",
           "materialize_a02_derivative", "validate_a02_readback"]
