from __future__ import annotations

from astrid.packs.rendering.executors.timeline_visualize.speech_projection import (
    project_speech_annotations,
    speech_annotation_identity,
)


def test_projection_maps_trimmed_repeated_and_retimed_occurrences_without_float_drift():
    result = project_speech_annotations(
        [{"id": "line", "start": "1/2", "end": "3/2", "text": "Canonical", "recognized_text": "Recognized", "uncertainty": 0.2}],
        [
            {"id": "one", "from": 0, "to": 2, "placement": 10, "speed": 2},
            {"id": "two", "from": 0, "to": 2, "placement": 20, "speed": 1},
        ],
        source_audio_digest="sha256:" + "a" * 64,
        transcript_digest="sha256:" + "b" * 64,
        annotation_digest="sha256:" + "c" * 64,
        correction_version=3,
        timing_method="word_alignment",
    )
    assert [phrase["render_interval"] for phrase in result["phrases"]] == [
        {"start": [41, 4], "end": [43, 4], "half_open": True},
        {"start": [41, 2], "end": [43, 2], "half_open": True},
    ]
    assert result["phrases"][0]["canonical_text"] == "Canonical"
    assert result["phrases"][0]["recognized_text"] == "Recognized"
    assert result["phrases"][0]["uncertainty"] == 0.2
    assert result["annotation_identity"].startswith("sha256:")
    assert result["timing_method"] == "word_alignment"
    assert result["phrases"][0]["id"] != result["phrases"][1]["id"]


def test_projection_never_guesses_missing_or_non_linear_timing_and_honors_links():
    result = project_speech_annotations(
        [{"id": "line", "start": 0, "end": 1, "text": "Line"}, {"id": "missing", "text": "Unknown"}],
        [
            {"id": "linear", "from": 0, "to": 2, "placement": 3, "segment_id": "line"},
            {"id": "warp", "from": 0, "to": 2, "placement": 9, "time_warp": {"kind": "elastic"}, "segment_id": "line"},
        ],
        annotation_digest="sha256:" + "d" * 64,
    )
    assert len(result["phrases"]) == 2
    assert result["phrases"][0]["status"] == "projected"
    assert result["phrases"][1]["mapping_state"] == "unsupported_non_linear_time_warp"
    assert all(phrase["annotation_id"] == "line" for phrase in result["phrases"])
    no_occurrence = project_speech_annotations([{"id": "line", "start": 0, "end": 1, "text": "Line"}], [])
    assert no_occurrence["status"] == "no_occurrences"
    assert no_occurrence["phrases"] == []


def test_projection_identity_changes_for_each_frozen_input():
    base = dict(source_audio_digest="sha256:" + "a" * 64, annotation_digest="sha256:" + "b" * 64, transcript_digest="sha256:" + "c" * 64)
    identities = {
        speech_annotation_identity(**base),
        speech_annotation_identity(**base, correction_version=1),
        speech_annotation_identity(**base, timing_method="word_alignment"),
        speech_annotation_identity(**{**base, "transcript_digest": "sha256:" + "d" * 64}),
        speech_annotation_identity(**{**base, "annotation_digest": "sha256:" + "e" * 64}),
        speech_annotation_identity(**{**base, "source_audio_digest": "sha256:" + "f" * 64}),
    }
    assert len(identities) == 6
