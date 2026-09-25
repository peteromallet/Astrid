from __future__ import annotations

import hashlib
import json

from astrid.core.timeline.authoring_bundle import (
    open_authoring_bundle,
    preview_authoring_candidate,
    validate_authoring_candidate,
)
from astrid.core.timeline.shot_composition_projection import project_runtime_parent_composition
from examples.timeline_authoring_recipes import (
    audio_reactive_arrangement,
    brightness_sequence,
    source_offset_beats,
    timed_quadrants,
)


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()


def _work():
    return {"timeline_id": "timeline", "shots": {}, "placements": [], "source_mapping": {"shots": {}, "placements": {}}}


def _candidate():
    internal_payload = {"tracks": [], "clips": []}
    shot_payload = {"items": [], "internal_timeline_revision_id": "internal-1"}
    parent_payload = {
        "config": {"tracks": [], "clips": []},
        "registry": {"assets": {}},
        "clips": [],
        "occurrences": [
            {
                "occurrence_id": "base-occurrence",
                "shot_id": "base-shot",
                "shot_revision_id": "base-shot-revision",
                "placement": {"start_ms": 0},
                "source_offset": {"start": 0, "end": 0},
                "duration_ms": 1,
                "speed": {"numerator": 1, "denominator": 1},
                "track": "picture",
                "transform": {},
                "gain": 1,
                "muted": False,
                "provenance": {},
            }
        ],
    }
    return open_authoring_bundle(
        {
            "project_id": "recipe-project",
            "timeline_id": "main",
            "revision_id": "base-parent",
            "content_digest": _digest(parent_payload),
            "payload": parent_payload,
        },
        shot_revisions=[
            {
                "project_id": "recipe-project",
                "shot_id": "base-shot",
                "revision_id": "base-shot-revision",
                "internal_timeline_revision_id": "internal-1",
                "content_digest": _digest(shot_payload),
                "payload": shot_payload,
            }
        ],
        internal_timeline_revisions=[
            {
                "project_id": "recipe-project",
                "timeline_id": "main",
                "revision_id": "internal-1",
                "content_digest": _digest(internal_payload),
                "payload": internal_payload,
            }
        ],
    )


def test_brightness_recipe_is_deterministic_and_uses_one_candidate():
    work = _work()
    shot = brightness_sequence(work, ["dark", "bright"], lambda value: {"dark": 0.1, "bright": 0.9}[value])
    assert [clip["asset"] for clip in shot["internal_timeline"]["clips"]] == ["dark", "bright"]
    assert [(clip["at"], clip["from"], clip["to"]) for clip in shot["internal_timeline"]["clips"]] == [(0, 0, 0.1), (0.1, 0, 0.1)]
    assert work["placements"][0]["duration_ms"] == 200


def test_quadrant_beats_and_audio_recipes_preserve_explicit_structure():
    work = _work()
    brightness_sequence(work, ["still"], lambda _: 1)
    shot_id = "brightness-montage"
    quadrants = timed_quadrants(work, shot_id, ["a", "b", "c", "d"], [0, 1, 2, 3])
    beats = source_offset_beats(
        work,
        shot_id,
        [{"media_id": "beat", "start": 4, "source_start": 2, "source_end": 2.5}],
    )
    audio = audio_reactive_arrangement(work, shot_id, "audio", duration=5, analysis_seed=7)
    assert [clip["rect"]["x"] for clip in quadrants] == [0.0, 0.5, 0.0, 0.5]
    assert beats[0]["from"] == 2 and beats[0]["to"] == 2.5
    assert "source_start" not in beats[0] and "source_end" not in beats[0]
    assert audio["analysis"] == {"frozen": True, "seed": 7}


def test_all_four_recipes_execute_through_one_candidate_validation_path():
    image_ids = ["sha256:" + character * 64 for character in "abcd"]
    cases = []
    for recipe_name in ("brightness", "quadrants", "beats", "audio"):
        work = _candidate()
        shot = brightness_sequence(
            work,
            image_ids[:2],
            lambda value: {image_ids[0]: 0.1, image_ids[1]: 0.9}[value],
        )
        shot_id = shot["shot_id"]
        if recipe_name == "quadrants":
            timed_quadrants(work, shot_id, image_ids, [0, 1, 2, 3])
        elif recipe_name == "beats":
            source_offset_beats(
                work,
                shot_id,
                [{"media_id": image_ids[2], "start": 4, "source_start": 2, "source_end": 2.5}],
            )
        elif recipe_name == "audio":
            audio_reactive_arrangement(
                work,
                shot_id,
                "sha256:" + "e" * 64,
                duration=5,
                analysis_seed=7,
            )
        cases.append((recipe_name, validate_authoring_candidate(work)))

    assert [name for name, _ in cases] == ["brightness", "quadrants", "beats", "audio"]
    assert all(result["valid"] is True for _, result in cases)


def test_brightness_bundle_projects_200_images_at_three_frames_each():
    work = _candidate()
    work["placements"] = []
    image_ids = ["sha256:" + format(index + 1, "064x") for index in range(200)]
    brightness_sequence(work, image_ids, lambda media_id: int(media_id[-4:], 16), duration=0.1)
    publication = preview_authoring_candidate(work)["publication"]
    projected = project_runtime_parent_composition(
        {
            "project_id": publication["project_id"],
            "timeline_id": publication["timeline_id"],
            "revision_id": publication["parent_revision_id"],
            "payload": publication["parent_composition"],
        },
        shot_revisions=publication["shot_revisions"],
        internal_timeline_revisions=publication["internal_timeline_revisions"],
    )
    clips = projected.config["clips"]
    assert len(clips) == 200
    assert all(round((clip["to"] - clip.get("from", 0)) * 30) == 3 for clip in clips)
    assert projected.occurrences[0]["duration_seconds"] == 20
