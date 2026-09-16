"""Shared timeline inspection grammar, status projection, and input geometry.

This module is deliberately pure.  It is used by the product CLI, SDK
admission, and the executor so the three entry points cannot disagree about
component names or half-open time semantics.  It does not render, retry, or
read media bytes.
"""
from __future__ import annotations

import math
import shlex
from collections import defaultdict
from fractions import Fraction
from typing import Any, Iterable, Mapping

from astrid.core.timeline.duration import clip_end_frame, clip_start_frame

COMPONENTS = ("output", "text", "audio", "inputs")
DEFAULT_COMPONENTS = ("output", "text", "audio")
_COMPONENT_ALIASES = {"input": "inputs", "video": "output", "waveform": "audio"}


def _tokens(value: Any) -> list[str]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    result: list[str] = []
    for item in values:
        if not isinstance(item, str):
            raise ValueError("components must be comma-separated names")
        result.extend(part.strip().lower() for part in item.split(",") if part.strip())
    return result


def normalize_components(show: Any = None, hide: Any = None) -> dict[str, Any]:
    """Resolve the small public component grammar into a stable ordered set."""
    shown: list[str] = []
    hidden: list[str] = []
    for source, target in ((_tokens(show), shown), (_tokens(hide), hidden)):
        for token in source:
            token = _COMPONENT_ALIASES.get(token, token)
            if token not in COMPONENTS:
                raise ValueError(
                    f"unknown inspection component {token!r}; choose {', '.join(COMPONENTS)}"
                )
            if token not in target:
                target.append(token)
    conflict = sorted(set(shown) & set(hidden), key=COMPONENTS.index)
    if conflict:
        raise ValueError("component requested by both show and hide: " + ", ".join(conflict))
    resolved = [name for name in COMPONENTS if name in DEFAULT_COMPONENTS]
    for name in shown:
        if name not in resolved:
            resolved.append(name)
    resolved = [name for name in resolved if name not in hidden]
    return {
        "show": shown,
        "hide": hidden,
        "resolved": resolved,
        "default": not shown and not hidden,
    }


def _finite(value: Any, label: str, *, nonnegative: bool = True) -> Fraction:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number")
    try:
        raw = str(value).strip()
        if ":" in raw:
            fields = raw.split(":")
            if len(fields) > 3:
                raise ValueError
            nums = [Fraction(part) for part in fields]
            if any(item >= 60 for item in nums[1:]):
                raise ValueError
            result = Fraction(0)
            for item in nums:
                result = result * 60 + item
        else:
            result = Fraction(raw)
    except (TypeError, ValueError, ZeroDivisionError):
        raise ValueError(f"{label} must be a finite number") from None
    if nonnegative and result < 0:
        raise ValueError(f"{label} must be non-negative")
    return result


def normalize_input_window(
    *, range_value: Any = None, at: Any = None, context: Any = 2,
) -> dict[str, Any] | None:
    """Normalize an exact half-open seconds window without float rounding."""
    if range_value is not None and at is not None:
        raise ValueError("choose range or at/context, not both")
    if range_value is None and at is None:
        return None
    if at is not None:
        center = _finite(at, "at")
        radius = _finite(context, "context")
        if radius <= 0:
            raise ValueError("context must be positive when focusing a timestamp")
        start, end, selected = max(Fraction(0), center - radius), center + radius, center
    else:
        if isinstance(range_value, str):
            pieces = range_value.split("..")
        else:
            pieces = range_value
        if not isinstance(pieces, (list, tuple)) or len(pieces) != 2:
            raise ValueError("range must be START..END")
        start, end = (_finite(part, "range bound") for part in pieces)
        if end <= start:
            raise ValueError("range end must follow its start")
        selected = None
    return {
        "start": [start.numerator, start.denominator],
        "end": [end.numerator, end.denominator],
        "half_open": True,
        **({"selected": [selected.numerator, selected.denominator]} if selected is not None else {}),
    }


def inspection_options(values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize all U1 selectors while retaining old fields."""
    components = normalize_components(values.get("show"), values.get("hide"))
    tracks = _tokens(values.get("track"))
    if any(not item or any(ord(char) < 32 for char in item) for item in tracks):
        raise ValueError("track must be a non-empty identifier")
    window = normalize_input_window(
        range_value=values.get("range"), at=values.get("at"),
        context=values.get("context") if values.get("context") is not None else 3.0,
    )
    detail = values.get("detail", False)
    if not isinstance(detail, bool):
        raise ValueError("detail must be a boolean")
    return {
        "components": components,
        "tracks": tracks,
        "clip": values.get("clip") or None,
        "shot": values.get("shot") or None,
        "window": window,
        "detail": detail,
    }


def action_argv(*argv: str) -> dict[str, Any]:
    """Return a copyable action in both argv and shell forms."""
    args = [str(item) for item in argv]
    return {"argv": args, "command": shlex.join(args)}


def render_status(
    *, lifecycle: Any = None, output: Mapping[str, Any] | None = None,
    expected_digest: str | None = None, owner_ok: bool | None = None,
    fresh: bool | None = None, project: str | None = None,
) -> dict[str, Any]:
    """Classify render lifecycle/output independently and add next actions.

    The caller supplies already-admitted runtime facts.  No state here starts
    work or treats a missing output as a successful render.
    """
    state = str(lifecycle or "absent").lower().strip()
    record = dict(output or {})
    if owner_ok is False:
        kind, label = "wrong_owner", "rendered output is not owned by the selected project"
    elif expected_digest and record.get("digest") and record.get("digest") != expected_digest:
        kind, label = "integrity_mismatch", "output digest does not match the admitted render"
    elif state in {"queued", "pending", "admitted", "starting"}:
        kind, label = "pending", "render is pending"
    elif state in {"running", "started", "in_progress", "stopped", "timeout", "timed_out"}:
        kind, label = "running", "render is still running or waiting; timeout is not failure"
    elif state in {"failed", "error", "cancelled", "canceled"}:
        kind, label = "failed", "render did not complete successfully"
    elif state in {"completed", "succeeded", "success"} and not record.get("available", record.get("object_id")):
        kind, label = "lifecycle_success_missing_output", "render lifecycle succeeded but video output is unavailable"
    elif state in {"completed", "succeeded", "success"} and fresh is False:
        kind, label = "stale", "successful render is stale relative to current inputs"
    elif state in {"completed", "succeeded", "success"}:
        kind, label = "succeeded", "verified rendered output is available"
    else:
        kind, label = "absent", "No successful render is available (no successful managed render is available)"
    project_arg = str(project or "<project>")
    timeline_arg = str(record.get("timeline") or "<timeline>")
    run_id = str(record.get("run_id") or "<run>")
    actions: list[dict[str, Any]] = []
    if kind in {"absent", "lifecycle_success_missing_output"}:
        actions += [
            {"id": "inspect_inputs", **action_argv("astrid", "timelines", "visualize", "--project", project_arg, "--timeline-slug", timeline_arg, "--show", "inputs", "--hide", "output")},
            {"id": "render", **action_argv("astrid", "timelines", "render", timeline_arg, "--project", project_arg)},
        ]
    elif kind in {"pending", "running"}:
        actions += [
            {"id": "follow", **action_argv("astrid", "tasks", "follow", str(record.get("task_id") or "<task>"), "--project", project_arg)},
            {"id": "events", **action_argv("astrid", "tasks", "events", str(record.get("task_id") or "<task>"), "--project", project_arg)},
        ]
    elif kind == "failed":
        actions += [
            {"id": "inspect_frozen_inputs", **action_argv("astrid", "timelines", "visualize", "--project", project_arg, "--render-run", run_id, "--show", "inputs", "--hide", "output")},
            {"id": "retry", **action_argv("astrid", "runs", "retry", run_id, "--project", project_arg)},
        ]
    elif kind == "stale":
        actions += [{"id": "inspect_old_render", **action_argv("astrid", "timelines", "visualize", "--project", project_arg, "--render-run", run_id)}]
    elif kind in {"wrong_owner", "integrity_mismatch"}:
        actions += [{"id": "inspect_inputs", **action_argv("astrid", "timelines", "visualize", "--project", project_arg, "--timeline-slug", timeline_arg, "--show", "inputs", "--hide", "output")}]
    return {
        "kind": kind, "status": kind, "label": label, "lifecycle": state,
        "output": {"available": bool(record.get("available", record.get("object_id"))),
                    "digest": record.get("digest"), "run_id": record.get("run_id")},
        "fresh": fresh, "owner_ok": owner_ok, "actions": actions,
        "next_actions": actions,
    }


def _rational(value: Any) -> Fraction:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return Fraction(int(value[0]), int(value[1]))
    return Fraction(str(value))


def _source_preview(clip: Mapping[str, Any], integrity: Mapping[str, Any] | Any | None) -> dict[str, Any]:
    if integrity is not None and not isinstance(integrity, Mapping):
        integrity = {name: getattr(integrity, name, None) for name in ("state", "observed_sha256", "expected_sha256", "reason")}
    integrity = integrity or {}
    state = str(integrity.get("state") or "missing")
    digest = integrity.get("observed_sha256") or integrity.get("expected_sha256")
    if state == "verified_original":
        # ``path`` is an attempt-local preview locator only.  It is never used
        # as authority (the digest/managed identity admission is the authority)
        # and is copied into the result pack before a browser consumes it.
        result = {
            "status": "verified", "digest": digest, "source_time": None,
            "media_type": integrity.get("media_type"),
        }
        if integrity.get("path"):
            result["path"] = integrity.get("path")
        return result
    return {"status": "placeholder", "reason": str((integrity or {}).get("reason") or state), "digest": digest}


def _audio_signifier(
    clip: Mapping[str, Any], track: str, *, start_frame: int, end_frame: int,
    overlap_start: int, overlap_end: int, fps: Fraction, speed: Fraction,
    source_start: Fraction, source_end: Fraction,
) -> dict[str, Any] | None:
    """Describe source audio presence on the clip's actual timeline window."""
    track_name = str(track).lower()
    kind = str(clip.get("kind") or clip.get("clipType") or "").lower()
    declared = clip.get("audio_source")
    if declared is None:
        declared = clip.get("source_audio")
    if declared is None and "audio" in clip:
        declared = clip.get("audio")
    if declared is False or (isinstance(declared, Mapping) and declared.get("enabled") is False):
        declared = None
    audio_track = track_name in {"audio", "vo", "voiceover", "music", "sound", "sfx"}
    audio_kind = kind in {"audio", "voiceover", "music", "sound", "sfx"}
    has_audio = audio_track or audio_kind or declared is not None or clip.get("has_audio") is True or clip.get("audio_enabled") is True
    if not has_audio:
        return None
    volume = clip.get("volume")
    muted = clip.get("muted") is True or (isinstance(volume, (int, float)) and not isinstance(volume, bool) and volume <= 0)
    def frame_seconds(frame: int) -> list[int]:
        value = Fraction(int(frame), 1) / fps
        return [value.numerator, value.denominator]

    if muted:
        return {
            "present": False, "reason": "muted", "source": declared,
            "window": [overlap_start, overlap_end],
            "window_seconds": [
                frame_seconds(overlap_start), frame_seconds(overlap_end),
            ],
            "visual_encoding": "timing_rail",
        }
    source_label = "embedded source audio" if declared is None else (
        str(declared.get("pool_id") or declared.get("asset") or declared.get("source") or "declared source audio")
        if isinstance(declared, Mapping) else str(declared)
    )
    return {
        "present": True, "source": source_label,
        "window": [overlap_start, overlap_end],
        "window_seconds": [
            frame_seconds(overlap_start), frame_seconds(overlap_end),
        ],
        "basis": "clip_placement",
        "visual_encoding": "timing_rail",
        "source_window": [
            [source_start.numerator, source_start.denominator],
            [source_end.numerator, source_end.denominator],
        ],
        "speed": [speed.numerator, speed.denominator],
    }


def project_input_window(
    clips: Iterable[Mapping[str, Any]], *, start_frame: int, end_frame: int, fps: Any,
    track_ids: Iterable[str] = (), clip_id: str | None = None,
    shot_id: str | None = None, asset_id: str | None = None,
    integrity: Mapping[str, Mapping[str, Any]] | None = None,
    shot_groups: Iterable[Mapping[str, Any]] = (),
    max_tracks: int = 10,
) -> dict[str, Any]:
    """Project every clip intersecting ``[start_frame,end_frame)``.

    Occurrence ids are never collapsed by shot id.  Subrows use greedy
    interval coloring in canonical input order, making overlap layout stable.
    """
    if start_frame < 0 or end_frame <= start_frame:
        raise ValueError("input window must be a non-empty half-open frame interval")
    fps_value = _rational(fps)
    wanted = set(str(item) for item in track_ids)
    # Canonical input snapshots retain pinned groups separately from the
    # flattened clip list.  Build a local membership index so shot filtering
    # works for inputs as well as render-admitted clips, without mutating the
    # frozen snapshot.
    shot_by_clip: dict[str, tuple[str, str | None]] = {}
    for group in shot_groups or ():
        if not isinstance(group, Mapping):
            continue
        group_id = group.get("shotId") or group.get("shot_id")
        if not isinstance(group_id, str) or not group_id:
            continue
        group_name = group.get("name") or group.get("shotName") or group.get("shot_name") or group.get("label")
        group_name = group_name if isinstance(group_name, str) and group_name else None
        members = group.get("clipIds") or group.get("clip_ids") or ()
        for member in members if isinstance(members, (list, tuple, set)) else ():
            if isinstance(member, str) and member:
                shot_by_clip.setdefault(member, (group_id, group_name))
    selected = []
    for index, raw in enumerate(clips):
        if not isinstance(raw, Mapping):
            continue
        track = str(raw.get("track") or raw.get("track_id") or "")
        if wanted and track not in wanted:
            continue
        if clip_id and str(raw.get("id") or raw.get("clip_id") or raw.get("occurrence_id")) != str(clip_id):
            continue
        raw_clip_id = str(raw.get("id") or raw.get("clip_id") or raw.get("occurrence_id") or f"clip-{index}")
        membership = shot_by_clip.get(raw_clip_id)
        raw_shot_id = str(raw.get("shot_id") or raw.get("shot")) if raw.get("shot_id") or raw.get("shot") else (membership[0] if membership else None)
        if shot_id and raw_shot_id != str(shot_id):
            continue
        if asset_id and str(raw.get("asset") or raw.get("asset_id") or raw.get("source")) != str(asset_id):
            continue
        timing = dict(raw)
        # Render snapshots normalize a clip's presented duration into
        # ``duration``; canonical authored clips use from/to/hold. Preserve
        # both forms instead of letting a missing source trim collapse a clip
        # to its one-frame placement.
        if raw.get("duration") is not None and raw.get("from") is None and raw.get("to") is None and raw.get("hold") is None:
            timing["hold"] = raw.get("duration")
            timing["speed"] = 1
        start = clip_start_frame(timing, float(fps_value))
        end = clip_end_frame(timing, float(fps_value))
        overlap_start, overlap_end = max(start, start_frame), min(end, end_frame)
        if overlap_start >= overlap_end:
            continue
        selected.append((index, raw, track, start, end, overlap_start, overlap_end))
    selected.sort(key=lambda item: (item[2], item[5], item[6], str(item[1].get("id", "")), item[0]))
    by_track: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, raw, track, start, end, overlap_start, overlap_end in selected:
        rows = by_track[track]
        subrow = 0
        while any(existing["subrow"] == subrow and existing["window"][0] < overlap_end and existing["window"][1] > overlap_start for existing in rows):
            subrow += 1
        asset_key = raw.get("asset") or raw.get("source")
        integrity_row = integrity.get(str(asset_key), {}) if integrity else {}
        speed = _rational(raw.get("speed", 1))
        trim_start = _rational(raw.get("from", raw.get("from_", 0)))
        source_start = trim_start + max(Fraction(0), Fraction(overlap_start - start, 1) / fps_value) * speed
        source_end = trim_start + max(Fraction(0), Fraction(overlap_end - start, 1) / fps_value) * speed
        occurrence = raw.get("occurrence_id") or raw.get("occurrenceId") or raw.get("id")
        row = {
            "clip_id": str(raw.get("id") or f"clip-{index}"), "occurrence_id": str(occurrence),
            "track_id": track, "asset_key": str(asset_key) if asset_key is not None else None,
            "window": [overlap_start, overlap_end],
            "window_seconds": [[(Fraction(overlap_start, 1) / fps_value).numerator, (Fraction(overlap_start, 1) / fps_value).denominator], [(Fraction(overlap_end, 1) / fps_value).numerator, (Fraction(overlap_end, 1) / fps_value).denominator]],
            "source_time": [[source_start.numerator, source_start.denominator], [source_end.numerator, source_end.denominator]],
            "speed": [speed.numerator, speed.denominator], "trim": {"from": [trim_start.numerator, trim_start.denominator]},
            "subrow": subrow, "continuation": overlap_start > start or overlap_end < end,
            "source_preview": _source_preview(raw, integrity_row),
        }
        if raw_shot_id is not None:
            row["shot_id"] = raw_shot_id
        raw_shot_name = raw.get("shot_name") or raw.get("shotName")
        if raw_shot_name is None and membership:
            raw_shot_name = membership[1]
        if isinstance(raw_shot_name, str) and raw_shot_name:
            row["shot_name"] = raw_shot_name
        audio = _audio_signifier(
            raw, track, start_frame=start, end_frame=end,
            overlap_start=overlap_start, overlap_end=overlap_end, fps=fps_value, speed=speed,
            source_start=source_start, source_end=source_end,
        )
        if audio is not None:
            row["audio_signifier"] = audio
        rows.append(row)
    ordered_tracks = sorted(by_track)
    visible_tracks = ordered_tracks[:max_tracks]
    # Bands paginate the complete ordered track set.  Slicing the first-page
    # ``visible_tracks`` here made every band after page one empty for dense
    # timelines, even though the projection itself retained those tracks.
    bands = [{"track_ids": ordered_tracks[i:i + max_tracks], "label": f"tracks {i + 1}–{min(i + max_tracks, len(ordered_tracks))} of {len(ordered_tracks)}"} for i in range(0, len(ordered_tracks), max_tracks)]
    return {
        "window": {"start_frame": start_frame, "end_frame": end_frame, "fps": [fps_value.numerator, fps_value.denominator], "half_open": True},
        "tracks": [{"track_id": track, "clips": by_track[track], "band": index // max_tracks} for index, track in enumerate(ordered_tracks)],
        "track_bands": bands, "visible_track_ids": visible_tracks,
        "hidden_track_count": max(0, len(ordered_tracks) - len(visible_tracks)),
        "source_preview_policy": "verified managed original only; missing, tampered, and unsupported media are labelled placeholders",
    }


__all__ = ["COMPONENTS", "DEFAULT_COMPONENTS", "normalize_components", "normalize_input_window", "inspection_options", "action_argv", "render_status", "project_input_window"]
