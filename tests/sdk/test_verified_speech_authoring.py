from __future__ import annotations

import hashlib

from astrid.sdk.verified_speech_authoring import build_verified_speech_materialization
from astrid.sdk.managed_transcript import transcript_input_from_snapshot
from astrid.packs.rendering.executors.timeline_visualize.speech_projection import project_speech_annotations


def test_authoring_materialization_uses_explicit_fixture_bytes_and_projects_shotless_line() -> None:
    authored_bytes = b'{"spoken_segments": [{"interval": [248.0, 252.5], "segment_id": "speech-shotless-01", "shot_id": null, "source_type": "verified_speech", "text": "We stay with the ending."}]}'
    authored = {
        "spoken_segments": [{
            "interval": [248.0, 252.5],
            "segment_id": "speech-shotless-01",
            "shot_id": None,
            "source_type": "verified_speech",
            "text": "We stay with the ending.",
            "traps": ["do not project"],
        }],
    }
    media = "c" * 64
    result = build_verified_speech_materialization(
        authored_bytes,
        authored,
        media_digest=media,
    )
    assert result["digests"]["authored_bytes"] == hashlib.sha256(authored_bytes).hexdigest()
    declaration = result["transcript_declaration"]
    assert declaration["sha256"] == hashlib.sha256(result["transcript_bytes"]).hexdigest()
    assert declaration["media"] == {"asset_key": "source-main", "sha256": media}
    assert result["speech_inputs"]["annotation_digest"] == (
        "sha256:" + hashlib.sha256(authored_bytes).hexdigest()
    )
    assert result["preflight"] == {
        "source": "authored.spoken_segments",
        "source_type": "verified_speech",
        "shotless": True,
        "segments": 1,
        "occurrences": 1,
        "traps_excluded": True,
    }
    projection = project_speech_annotations(**{
        "annotations": result["speech_inputs"]["speech_annotations"],
        "occurrences": result["speech_inputs"]["speech_occurrences"],
        **{
            key: result["speech_inputs"][key]
            for key in (
                "source_audio_digest", "transcript_digest", "annotation_digest",
                "correction_version", "timing_method",
            )
        },
        "coverage": result["speech_inputs"]["speech_coverage"],
    })
    assert projection["status"] == "available"
    assert projection["phrases"][0]["canonical_text"] == "We stay with the ending."
    assert projection["phrases"][0]["mapping_state"] == "exact"


def test_config_transcript_becomes_only_a_hash_bound_runtime_input() -> None:
    config = {
        "app": {
            "transcript": {
                "source_id": "transcript:main",
                "source_version": "1",
                "producer": "fixture.authoring",
                "file": "transcript.json",
                "sha256": "d" * 64,
                "media": {"asset_key": "source-main", "sha256": "e" * 64},
            }
        }
    }
    result = transcript_input_from_snapshot(
        config,
        {"assets": {"source-main": {"content_sha256": "e" * 64}}},
    )
    assert result == {"digest": "sha256:" + "d" * 64, "object_id": "sha256:" + "d" * 64}
