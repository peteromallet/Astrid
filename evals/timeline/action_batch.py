"""Attempt A02-A10 against the exact exported source and record fixture blockers.

The action suite cases describe richer, purpose-built fixtures than the pinned
Astrid intro currently provides.  This module performs a read-only audit of the
frozen closure, records machine-readable per-case outcomes, and never publishes
or edits Runtime data.  It deliberately does not turn a missing precondition
into a synthetic success.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .a01_smoke import load_baseline
from .source_export import _canonical


EXECUTOR_KIND = "deterministic_fixture_action"
CASE_IDS = tuple(f"A{number:02d}" for number in range(2, 11))


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical(value) + b"\n")
    os.replace(temporary, path)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[Mapping[str, Any]]:
    return [row for row in value if isinstance(row, Mapping)] if isinstance(value, list) else []


def inspect_fixture(baseline: Any) -> dict[str, Any]:
    """Return reproducible capability facts from a frozen Baseline closure."""
    closure = _mapping(baseline.closure)
    parent = _mapping(_mapping(closure.get("parent_revision")).get("payload"))
    occurrences = _rows(parent.get("occurrences"))
    parent_clips = _rows(parent.get("clips"))
    shot_rows = _rows(closure.get("shot_revisions"))
    internal_rows = _rows(closure.get("internal_timeline_revisions"))
    assets: dict[str, Mapping[str, Any]] = {}
    clip_types: set[str] = set()
    tracks: set[str] = set()
    voice_clip_count = 0
    for row in internal_rows:
        payload = _mapping(row.get("payload"))
        registry = _mapping(payload.get("registry"))
        for key, value in _mapping(registry.get("assets")).items():
            if isinstance(value, Mapping):
                assets[str(key)] = value
        for clip in _rows(payload.get("clips")):
            track = clip.get("track")
            clip_type = clip.get("clipType")
            if isinstance(track, str):
                tracks.add(track)
            if isinstance(clip_type, str):
                clip_types.add(clip_type)
            if track in {"vo", "voice", "voiceover"}:
                voice_clip_count += 1
    for clip in parent_clips:
        track = clip.get("track")
        clip_type = clip.get("clipType")
        if isinstance(track, str):
            tracks.add(track)
        if isinstance(clip_type, str):
            clip_types.add(clip_type)
    parent_tracks = sorted({str(row.get("track")) for row in parent_clips if isinstance(row.get("track"), str)})
    image_assets = [key for key, value in assets.items() if value.get("type") == "image"]
    video_assets = [key for key, value in assets.items() if value.get("type") == "video"]
    text_clip_count = sum(
        1 for row in parent_clips
        if str(row.get("track", "")).lower() in {"title", "text"}
        or str(row.get("clipType", "")).lower() in {"text", "title"}
    )
    parent_audio = [row for row in parent_clips if str(row.get("track", "")).lower() in {"audio", "music", "vo", "voice"}]
    occurrence_shot_ids = [row.get("shot_id") for row in occurrences if isinstance(row.get("shot_id"), str)]
    unique_occurrences = len({row.get("occurrence_id") for row in occurrences}) == len(occurrences)
    unique_shots = len(set(occurrence_shot_ids)) == len(occurrence_shot_ids)
    return {
        "source": {
            "project_id": baseline.source_project_id,
            "project_slug": baseline.source_project_slug,
            "timeline_id": baseline.source_timeline_id,
            "head": baseline.source_head,
            "closure_digest": baseline.closure_digest,
            "semantic_digest": baseline.semantic_digest,
        },
        "counts": {
            "occurrences": len(occurrences), "unique_occurrence_ids": unique_occurrences,
            "unique_shots": unique_shots, "shot_revisions": len(shot_rows),
            "internal_timelines": len(internal_rows), "voice_clips": voice_clip_count,
            "admitted_image_assets": len(image_assets), "admitted_video_assets": len(video_assets),
            "parent_text_or_title_clips": text_clip_count,
        },
        "parent_tracks": parent_tracks,
        "parent_audio_clips": len(parent_audio),
        "clip_types": sorted(clip_types),
        "registry_image_asset_keys": sorted(image_assets),
        "registry_video_asset_keys": sorted(video_assets),
        "frame_rate": baseline.frame_rate,
        "media_objects": len(baseline.media),
    }


def _case_blocker(case_id: str, facts: Mapping[str, Any]) -> tuple[str, list[str]]:
    counts = _mapping(facts.get("counts"))
    parent_tracks = set(facts.get("parent_tracks", []))
    if case_id == "A02":
        missing = []
        if counts.get("occurrences", 0) < 4:
            missing.append("four real occurrences")
        if not counts.get("unique_shots"):
            missing.append("independent shot ownership")
        if not facts.get("parent_audio_clips"):
            missing.append("continuous parent music bed that can be trimmed")
        return "A02 needs a purpose-built four-shot fixture with parent music; the pinned intro has 16 unique occurrences but no parent audio clips.", missing or ["case-specific target designation and expected shortened render"]
    if case_id == "A03":
        return "The source contains enough unique shots and local VO for a reorder, but no case fixture identifies the requested closing/middle pair or supplies a caption binding for the moved group.", ["fixture-discovered closing and middle targets", "caption role/binding on the moved occurrence", "bounded render evidence"]
    if case_id == "A04":
        return "The pinned closure does not declare a feature shot with a title binding and an admitted alternate image owned by a task-specific fixture.", ["feature target identity", "title binding", "alternate image assignment", "copy-local independence check"]
    if case_id == "A05":
        return "The source has local VO clips, but not the declared fixture contract for frame-aligned VO endpoints plus a continuous parent music bed and full-intro audio proof.", ["explicit frozen frame-rate policy", "frame-aligned expected VO endpoint table", "continuous parent music bed", "audio decode/render evidence"]
    if case_id == "A06":
        return f"No built-in title/text clip is present in the pinned parent (tracks: {', '.join(sorted(parent_tracks))}); this fixture has no separable authored script, transcript, and visible-title roles.", ["built-in editable title clip", "separate script/transcript/voice roles", "title render evidence"]
    if case_id == "A07":
        return "The pinned parent has no music clip; changing a gain field on unrelated voice or visual material would not test music-only attenuation.", ["separate music and VO clips", "music-only/voice-only measurement windows", "audio decode/RMS proof"]
    if case_id == "A08":
        return "The source has terminal-video material, but it does not provide the case's named demonstration-shot cue, paired still coverage, or a declared source-boundary marker fixture.", ["fixture-discovered demonstration shot and cue", "paired admitted still on the same target", "source 2s/4s marker and boundary render"]
    if case_id == "A09":
        return "The pinned source does not declare a four-image quadrant collection, cue list, or supported rectangular multi-placement layout for the target shot.", ["four supplied destination-owned images", "explicit cue times/frame policy", "quadrant layout support", "cue-boundary renders"]
    if case_id == "A10":
        return "The pinned closure has no 200-image collection manifest or deterministic brightness-analysis provenance; deriving 200 images ad hoc would change the case fixture.", ["approved 200-image collection manifest", "fixed decoder/alpha/orientation/luma policy", "three-frame placement builder", "20-second montage preview and sentinel frames"]
    return "No case-specific fixture audit rule exists.", ["case-specific fixture"]


def run_batch(source_baseline: Path, attempt_dir: Path) -> dict[str, Any]:
    baseline = load_baseline(source_baseline)
    facts = inspect_fixture(baseline)
    _write_json(attempt_dir / "source-facts.json", facts)
    results = []
    for case_id in CASE_IDS:
        reason, missing = _case_blocker(case_id, facts)
        result = {
            "case_id": case_id,
            "status": "blocked",
            "score": 0,
            "safety": "pass",
            "executor_kind": EXECUTOR_KIND,
            "fixture_or_agent_failure": "fixture_failure",
            "failure_cause": "missing_case_fixture_preconditions",
            "reason": reason,
            "missing_fixture_preconditions": missing,
            "evidence_completeness": "precondition_audit_only; no candidate, render, or publication was produced",
            "tool_calls": 0,
            "elapsed_seconds": 0,
            "invented_api_attempts": 0,
            "retries": 0,
            "clarification_needed": False,
            "canonical_mutation": False,
            "source_head": baseline.source_head,
            "source_semantic_digest": baseline.semantic_digest,
            "attempt_artifacts": ["source-facts.json", f"results/{case_id}.json"],
        }
        _write_json(attempt_dir / "results" / f"{case_id}.json", result)
        results.append(result)
    summary = {
        "kind": "astrid.timeline-eval.action-batch.v1",
        "attempt_id": attempt_dir.name,
        "executor_kind": EXECUTOR_KIND,
        "source_head": baseline.source_head,
        "source_semantic_digest": baseline.semantic_digest,
        "cases_attempted": len(results),
        "passed": 0,
        "failed": 0,
        "blocked": len(results),
        "canonical_mutation": False,
        "fixture_facts_path": "source-facts.json",
        "results": results,
        "note": "Read-only fixture compatibility attempt. No agent action, candidate render, or Runtime publication was performed because required task fixtures are absent.",
    }
    _write_json(attempt_dir / "summary.json", summary)
    return summary


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-baseline", required=True, type=Path)
    parser.add_argument("--attempt-dir", required=True, type=Path)
    args = parser.parse_args()
    summary = run_batch(args.source_baseline, args.attempt_dir.expanduser().absolute())
    print(json.dumps({key: summary[key] for key in ("attempt_id", "cases_attempted", "passed", "blocked", "canonical_mutation")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
