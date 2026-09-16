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
        range_value=values.get("range"), at=values.get("at"), context=values.get("context", 2)
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
        kind, label = "wrong_owner", "output belongs to another project"
    elif expected_digest and record.get("digest") and record.get("digest") != expected_digest:
        kind, label = "integrity_mismatch", "output digest does not match the admitted render"
    elif state in {"queued", "pending", "admitted", "starting"}:
        kind, label = "pending", "render is pending"
    elif state in {"running", "started", "in_progress"}:
        kind, label = "running", "render is running"
    elif state in {"failed", "error", "cancelled", "canceled", "stopped"}:
        kind, label = "failed", "render did not complete successfully"
    elif state in {"completed", "succeeded", "success"} and not record.get("available", record.get("object_id")):
        kind, label = "lifecycle_success_missing_output", "render lifecycle succeeded but video output is unavailable"
    elif state in {"completed", "succeeded", "success"} and fresh is False:
        kind, label = "stale", "successful render is stale relative to current inputs"
    elif state in {"completed", "succeeded", "success"}:
        kind, label = "succeeded", "verified rendered output is available"
    else:
        kind, label = "absent", "no successful managed render is available"
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
    return {
        "kind": kind, "label": label, "lifecycle": state,
        "output": {"available": bool(record.get("available", record.get("object_id"))),
                    "digest": record.get("digest"), "run_id": record.get("run_id")},
        "fresh": fresh, "owner_ok": owner_ok, "actions": actions,
    }


def _rational(value: Any) -> Fraction:
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return Fraction(int(value[0]), int(value[1]))
    return Fraction(str(value))


def _source_preview(clip: Mapping[str, Any], integrity: Mapping[str, Any] | None) -> dict[str, Any]:
    state = str((integrity or {}).get("state") or "missing")
    digest = (integrity or {}).get("observed_sha256") or (integrity or {}).get("expected_sha256")
    if state == "verified_original":
        return {"status": "verified", "digest": digest, "source_time": None}
    return {"status": "placeholder", "reason": str((integrity or {}).get("reason") or state), "digest": digest}


def project_input_window(
    clips: Iterable[Mapping[str, Any]], *, start_frame: int, end_frame: int, fps: Any,
    track_ids: Iterable[str] = (), integrity: Mapping[str, Mapping[str, Any]] | None = None,
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
    selected = []
    for index, raw in enumerate(clips):
        if not isinstance(raw, Mapping):
            continue
        track = str(raw.get("track") or raw.get("track_id") or "")
        if wanted and track not in wanted:
            continue
        start = clip_start_frame(raw, float(fps_value))
        end = clip_end_frame(raw, float(fps_value))
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
            "track_id": track, "window": [overlap_start, overlap_end],
            "window_seconds": [[overlap_start, 1], [overlap_end, 1]],
            "source_time": [[source_start.numerator, source_start.denominator], [source_end.numerator, source_end.denominator]],
            "speed": [speed.numerator, speed.denominator], "trim": {"from": [trim_start.numerator, trim_start.denominator]},
            "subrow": subrow, "continuation": overlap_start > start or overlap_end < end,
            "source_preview": _source_preview(raw, integrity_row),
        }
        rows.append(row)
    ordered_tracks = sorted(by_track)
    visible_tracks = ordered_tracks[:max_tracks]
    bands = [{"track_ids": visible_tracks[i:i + max_tracks], "label": f"tracks {i + 1}–{min(i + max_tracks, len(ordered_tracks))} of {len(ordered_tracks)}"} for i in range(0, len(ordered_tracks), max_tracks)]
    return {
        "window": {"start_frame": start_frame, "end_frame": end_frame, "fps": [fps_value.numerator, fps_value.denominator], "half_open": True},
        "tracks": [{"track_id": track, "clips": by_track[track], "band": index // max_tracks} for index, track in enumerate(ordered_tracks)],
        "track_bands": bands, "hidden_track_count": max(0, len(ordered_tracks) - len(visible_tracks)),
        "source_preview_policy": "verified managed original only; missing, tampered, and unsupported media are labelled placeholders",
    }


__all__ = ["COMPONENTS", "DEFAULT_COMPONENTS", "normalize_components", "normalize_input_window", "inspection_options", "action_argv", "render_status", "project_input_window"]
