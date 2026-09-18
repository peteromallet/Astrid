from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from astrid.core.timeline.duration import clip_end_frame, clip_start_frame
from astrid.core.timeline.shot_composition import MissingDependencyError
from astrid.core.timeline.shot_composition_projection import (
    ShotCompositionProjectionError,
    project_shot_composition,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "timeline" / "shot_composition.json"


def graph() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_projection_preserves_frames_trim_audio_and_occurrence_placement() -> None:
    source = graph()
    revision = next(item for item in source["shot_revisions"] if item["shot_id"] == "shot-alpha" and item["revision_id"] == "rev-a")
    revision["internal_timeline_revision"]["timeline"]["clips"][0].pop("duration_ms")
    revision["internal_timeline_revision"]["timeline"]["clips"][0].update({"from": 2, "to": 10, "speed": 2})
    occurrence = source["occurrences"][0]
    occurrence.update({"duration_ms": 1000, "source_offset": 7, "speed": 1.5, "gain": 0.5, "muted": True})

    projected = project_shot_composition(source)
    video = next(item for item in projected.config["clips"] if item["shot_occurrence_id"] == "occ-1" and item["app"]["astrid_shot_composition"]["source_clip_id"] == "alpha-video")
    assert video["at"] == 0
    assert video["from"] == 2
    assert video["to"] == 4  # one second of the two-times-speed source remains
    assert video["volume"] == 0
    assert video["app"]["astrid_shot_composition"]["source_offset"] == 7
    assert video["app"]["astrid_shot_composition"]["speed"] == 1.5
    assert video["app"]["astrid_shot_composition"]["muted"] is True
    assert clip_start_frame(video, 30) == 0
    assert clip_end_frame(video, 30) == 30

    audio = next(item for item in projected.config["clips"] if item["shot_occurrence_id"] == "occ-1" and item["app"]["astrid_shot_composition"]["source_clip_id"] == "alpha-audio")
    assert audio["track"] == "audio"
    assert audio["hold"] == 1


def test_linked_occurrences_remain_distinct_and_export_metadata_is_qualified() -> None:
    projected = project_shot_composition(graph())
    linked = [item for item in projected.config["clips"] if item.get("shot_id") == "shot-alpha"]
    assert {item["shot_occurrence_id"] for item in linked} >= {"occ-1", "occ-2", "occ-3"}
    assert len({item["id"] for item in linked}) == len(linked)
    assert projected.outputs[0]["output_identity"].endswith("occurrence/occ-1/output/final-video")
    assert projected.outputs[0]["output_identity"] != projected.outputs[1]["output_identity"]
    assert projected.config["app"]["astrid_shot_composition"]["outputs"][0]["occurrence_id"] == "occ-1"


def test_projection_reports_missing_dependency_before_downstream_reads() -> None:
    source = graph()
    source["shot_revisions"][1]["dependencies"] = [{"shot_id": "missing", "revision_id": "rev-x", "required": True}]
    with pytest.raises(MissingDependencyError):
        project_shot_composition(source)


def test_deeper_nesting_and_unsupported_compositing_fail_closed() -> None:
    nested = graph()
    nested["shot_revisions"][0]["internal_timeline_revision"]["timeline"]["clips"][0]["clip_type"] = "shot"
    with pytest.raises(ShotCompositionProjectionError, match="deeper shot nesting"):
        project_shot_composition(nested)

    compositing = graph()
    compositing["shot_revisions"][0]["internal_timeline_revision"]["timeline"]["compositing"] = "screen"
    with pytest.raises(ShotCompositionProjectionError, match="unsupported compositing"):
        project_shot_composition(compositing)


def test_blank_child_keeps_bounded_occurrence_and_blank_output_metadata() -> None:
    source = graph()
    revision = next(item for item in source["shot_revisions"] if item["shot_id"] == "shot-beta")
    revision["internal_timeline_revision"]["timeline"]["clips"] = []
    projected = project_shot_composition(source)
    output = next(item for item in projected.outputs if item["occurrence_id"] == "occ-4")
    assert output["blank"] is True
    assert output["duration_ms"] == 1200
    assert not any(item.get("shot_occurrence_id") == "occ-4" for item in projected.config["clips"])
    occurrence = next(item for item in projected.config["app"]["astrid_shot_composition"]["occurrences"] if item["occurrence_id"] == "occ-4")
    assert occurrence["blank"] is True
    assert occurrence["duration_seconds"] == 1.2
