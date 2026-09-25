"""Derive source-only action locators from the pinned closure.

This is a coordinator audit seam, not an action target builder.  It may name
IDs and media digests that are actually present in the frozen source closure,
but it never relabels those canonical identities as destination-owned Runtime
IDs and never declares a worker-launchable edit route.  A disposable target
receipt still has to be produced by a real isolated seed before a case can be
admitted.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


PROJECTION_KIND = "astrid.timeline-eval.action-source-projection.v1"
_CASES = ("A02", "A03", "A04")


class ActionSourceProjectionError(ValueError):
    """The pinned source cannot support a trustworthy source projection."""


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _load(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ActionSourceProjectionError(f"fixture JSON is unreadable: {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise ActionSourceProjectionError(f"fixture JSON must be an object: {path}")
    return value


def _source_media_ids(baseline: Mapping[str, Any], internal_revision_ids: set[str]) -> list[str]:
    """Find verified source media referenced by selected internal timelines."""
    media = {
        str(row.get("digest"))
        for row in _rows(baseline.get("media"))
        if isinstance(row.get("digest"), str) and str(row.get("digest")).startswith("sha256:")
    }
    closure = _mapping(baseline.get("closure"))
    selected: set[str] = set()
    for row in _rows(closure.get("internal_timeline_revisions")):
        revision_id = str(row.get("revision_id", ""))
        if revision_id not in internal_revision_ids:
            continue

        def visit(value: Any) -> None:
            if isinstance(value, Mapping):
                for key, child in value.items():
                    if key in {"media_id", "source_media_id"} and isinstance(child, str) and child in media:
                        selected.add(child)
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(row.get("payload"))
    return sorted(selected)


def _closure_parts(baseline: Mapping[str, Any]) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    closure = _mapping(baseline.get("closure"))
    parent = _mapping(_mapping(closure.get("parent_revision")).get("payload"))
    occurrences = {
        str(row.get("occurrence_id")): row
        for row in _rows(parent.get("occurrences"))
        if row.get("occurrence_id")
    }
    internals = {
        str(row.get("revision_id")): row
        for row in _rows(closure.get("internal_timeline_revisions"))
        if row.get("revision_id")
    }
    return parent, occurrences, internals


def _clips(internal: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _rows(_mapping(internal.get("payload")).get("clips"))


def _has_caption(clips: list[Mapping[str, Any]]) -> bool:
    return any(
        str(clip.get("track", "")).lower() in {"caption", "title", "text"}
        or str(clip.get("clipType", "")).lower() in {"caption", "title", "text"}
        or "caption" in str(clip.get("id", "")).lower()
        for clip in clips
    )


def _manifest_case(manifest: Mapping[str, Any], case_id: str) -> Mapping[str, Any]:
    row = next((row for row in _rows(manifest.get("cases")) if row.get("id") == case_id), None)
    if row is None:
        raise ActionSourceProjectionError(f"action manifest has no {case_id} row")
    return row


def derive_action_source_projection(
    *, manifest_path: Path, baseline_path: Path, case_id: str,
) -> dict[str, Any]:
    """Derive a non-launchable source projection for A02, A03, or A04.

    The returned ``source_media_ids`` are explicitly source-owned.  They are
    useful for a future coordinator seed, but are not safe to place in a public
    target receipt until Runtime returns destination-owned IDs.
    """
    if case_id not in _CASES:
        raise ActionSourceProjectionError(f"source projection is only defined for {_CASES}: {case_id}")
    manifest = _load(manifest_path)
    baseline = _load(baseline_path)
    case = _manifest_case(manifest, case_id)
    parent, occurrences, internals = _closure_parts(baseline)
    targets = _mapping(case.get("targets"))
    missing: list[str] = []

    order = [str(value) for value in targets.get("four_occurrences_in_order", ()) if isinstance(value, str)]
    if case_id == "A02":
        remove = str(targets.get("remove_occurrence", ""))
        if len(order) != 4:
            missing.append("manifest does not identify exactly four occurrences")
        if remove not in order:
            missing.append("A02 removal occurrence is not one of the four manifest occurrences")
        selected = [occurrences.get(value) for value in order]
        if any(row is None for row in selected):
            missing.append("one or more A02 occurrences are absent from the pinned closure")
        target = occurrences.get(remove)
        target_revision = str(target.get("shot_revision_id", "")) if target else ""
        internal_id = next(
            (str(row.get("internal_timeline_revision_id", "")) for row in _rows(_mapping(baseline.get("closure")).get("shot_revisions"))
             if row.get("revision_id") == target_revision),
            "",
        )
        target_clips = _clips(internals.get(internal_id, {}))
        voice_ids = [str(clip.get("id")) for clip in target_clips
                     if str(clip.get("track", "")).lower() in {"vo", "voice", "voiceover"} and clip.get("id")]
        if not voice_ids:
            missing.append("A02 target occurrence has no pinned voice clip")
        parent_audio = [clip for clip in _rows(parent.get("clips"))
                        if str(clip.get("track", "")).lower() in {"music", "audio", "bgm"}]
        if not parent_audio:
            missing.append("pinned parent has no continuous music clip")
        missing.extend([
            "four-shot disposable derivative with parent music bytes",
            "disposable target receipt with destination-owned media and remove-occurrence route",
        ])
        locator: dict[str, Any] = {
            "remove_occurrence_id": remove,
            "remove_shot_id": target.get("shot_id") if target else None,
            "remove_voice_clip_ids": voice_ids,
            "occurrence_ids_in_order": order,
        }
        projection = "remove_occurrence_compact.v1"
        readback = {
            "removed_occurrence_absent": True,
            "remaining_occurrence_ids": [value for value in order if value != remove],
            "remaining_identity_and_voice_media_unchanged": True,
            "parent_music_media_identity_unchanged_and_trimmed": True,
        }
        selected_revision_ids = {
            str(row.get("shot_revision_id", "")) for row in selected if row
        }
        internal_ids = {
            str(row.get("internal_timeline_revision_id", ""))
            for row in _rows(_mapping(baseline.get("closure")).get("shot_revisions"))
            if str(row.get("revision_id", "")) in selected_revision_ids
        }
    elif case_id == "A03":
        closing = str(targets.get("closing_occurrence", ""))
        middle = str(targets.get("middle_occurrence", ""))
        if len(order) != 4 or any(value not in occurrences for value in order):
            missing.append("A03 four-occurrence order is not fully present in the pinned closure")
        if closing not in occurrences or middle not in occurrences:
            missing.append("A03 closing/middle target is not present in the pinned closure")
        closing_row = occurrences.get(closing)
        closing_revision = str(closing_row.get("shot_revision_id", "")) if closing_row else ""
        internal_id = next(
            (str(row.get("internal_timeline_revision_id", "")) for row in _rows(_mapping(baseline.get("closure")).get("shot_revisions"))
             if row.get("revision_id") == closing_revision),
            "",
        )
        closing_clips = _clips(internals.get(internal_id, {}))
        if not _has_caption(closing_clips):
            missing.append("pinned closing shot has no caption/title binding to move")
        missing.append("disposable reorder target receipt")
        locator = {
            "closing_occurrence_id": closing,
            "middle_occurrence_id": middle,
            "source_occurrence_ids_in_order": order,
            "expected_occurrence_ids_after": [value for value in order if value not in {closing, middle}] + [closing, middle],
        }
        projection = "move_occurrence_group.v1"
        readback = {
            "original_occurrence_identity_and_payload_unchanged": True,
            "moved_group_preserves_picture_voice_caption_bindings": True,
            "durations_and_total_duration_unchanged": True,
        }
        internal_ids = {str(row.get("internal_timeline_revision_id", "")) for row in _rows(_mapping(baseline.get("closure")).get("shot_revisions"))
                        if str(row.get("revision_id", "")) in {str(occurrences.get(value, {}).get("shot_revision_id", "")) for value in order}}
    else:
        feature = str(targets.get("feature_occurrence", ""))
        feature_row = occurrences.get(feature)
        if feature_row is None:
            missing.append("A04 feature occurrence is absent from the pinned closure")
        feature_revision = str(feature_row.get("shot_revision_id", "")) if feature_row else ""
        internal_id = next(
            (str(row.get("internal_timeline_revision_id", "")) for row in _rows(_mapping(baseline.get("closure")).get("shot_revisions"))
             if row.get("revision_id") == feature_revision),
            "",
        )
        feature_clips = _clips(internals.get(internal_id, {}))
        if not any(str(clip.get("track", "")).lower() in {"title", "text"} for clip in feature_clips):
            missing.append("pinned feature shot has no title/text binding")
        alternate = _mapping(case.get("media")).get("alternate_image_digest")
        source_media = {
            str(row.get("digest")) for row in _rows(baseline.get("media"))
            if row.get("digest") == alternate
        }
        if not source_media:
            missing.append("A04 alternate image digest is not present in pinned source bytes")
        missing.extend([
            "copy-local item/reference bindings for the feature shot",
            "disposable duplicate/edit target receipt and copy route",
        ])
        locator = {
            "feature_occurrence_id": feature,
            "feature_shot_id": targets.get("feature_shot_id"),
            "alternate_image_source_media_id": alternate,
            "destination_alias": targets.get("destination_alias"),
        }
        projection = "duplicate_then_edit_copy.v1"
        readback = {
            "original_identity_payload_and_timing_unchanged": True,
            "copy_identity_set_disjoint": True,
            "copy_uses_alternate_image_only": True,
            "copy_title_is_feature_alternate": True,
        }
        internal_ids = {internal_id} if internal_id else set()

    source_head = _mapping(baseline.get("source")).get("head")
    source_media_ids = _source_media_ids(baseline, internal_ids)
    return {
        "kind": PROJECTION_KIND,
        "case_id": case_id,
        "status": "source_projection_only",
        "launchable": False,
        "source": {
            "head": source_head,
            "closure_digest": baseline.get("closure_digest"),
            "semantic_digest": baseline.get("semantic_digest"),
        },
        "target_locator": locator,
        "source_media_ids": source_media_ids,
        "destination_owned_media_ids": [],
        "readback_projection": projection,
        "readback_contract": readback,
        "missing_prerequisites": list(dict.fromkeys(missing)),
        "reason": "source IDs are not a disposable target receipt; no worker launch is permitted",
        "projection_digest": _canonical_digest({"case_id": case_id, "target_locator": locator, "source_media_ids": source_media_ids}),
    }


__all__ = ["ActionSourceProjectionError", "PROJECTION_KIND", "derive_action_source_projection"]
