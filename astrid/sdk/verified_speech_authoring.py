"""Build hash-bound verified speech inputs from explicit authoring data.

This module is intentionally source-only: it never calls ASR and never turns
prompt or unmarked transcript fields into speech.  Runtime ingestion is a
separate small adapter so authoring can be preflighted before any task write.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize one authoring payload into its immutable byte representation."""

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _media_digest(value: str) -> str:
    raw = value.removeprefix("sha256:")
    if not _SHA256.fullmatch(raw):
        raise ValueError("media_digest must be a sha256 digest")
    return raw


def _explicit_segments(authored: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw_segments = authored.get("spoken_segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise ValueError("authored fixture has no explicit spoken_segments")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_segments):
        if not isinstance(raw, Mapping):
            raise ValueError(f"spoken_segments[{index}] must be an object")
        segment_id = raw.get("segment_id")
        interval = raw.get("interval")
        text = raw.get("text")
        source_type = raw.get("source_type")
        if not isinstance(segment_id, str) or not segment_id.strip() or segment_id in seen:
            raise ValueError(f"spoken_segments[{index}] has an invalid or duplicate segment_id")
        if not isinstance(interval, list) or len(interval) != 2:
            raise ValueError(f"spoken_segments[{index}].interval must be [start, end]")
        start, end = interval
        if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start:
            raise ValueError(f"spoken_segments[{index}].interval must be a non-empty numeric span")
        if source_type != "verified_speech":
            raise ValueError(f"spoken_segments[{index}] is not verified_speech")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"spoken_segments[{index}].text must be non-empty")
        seen.add(segment_id)
        result.append({
            "segment_id": segment_id,
            "start": start,
            "end": end,
            "text": text,
            "source_type": "verified_speech",
        })
    return result


def build_verified_speech_materialization(
    authored_bytes: bytes,
    authored: Mapping[str, Any],
    *,
    media_digest: str,
    media_asset_key: str = "source-main",
    transcript_file: str = "transcript.json",
) -> dict[str, Any]:
    """Return transcript, render metadata, declaration, and byte digests."""

    if not isinstance(authored_bytes, bytes):
        raise TypeError("authored_bytes must be bytes")
    media_hex = _media_digest(media_digest)
    segments = _explicit_segments(authored)
    transcript = {
        "schema_version": 1,
        "segments": [
            {
                "id": item["segment_id"],
                "start": item["start"],
                "end": item["end"],
                "text": item["text"],
                "source_type": item["source_type"],
            }
            for item in segments
        ],
    }
    transcript_bytes = canonical_json_bytes(transcript)
    transcript_hex = sha256_bytes(transcript_bytes)
    annotations = [
        {
            "annotation_id": item["segment_id"],
            "start": item["start"],
            "end": item["end"],
            "text": item["text"],
            "source_type": item["source_type"],
        }
        for item in segments
    ]
    occurrences = [
        {
            "occurrence_id": f"speech-occurrence-{item['segment_id']}",
            "annotation_id": item["segment_id"],
            "from": 0,
            "to": 297,
            "placement": 0,
            "speed": 1,
            "mapping_state": "exact",
            "timing_method": "fixture-authored",
        }
        for item in segments
    ]
    annotation_bytes = canonical_json_bytes(annotations)
    annotation_hex = sha256_bytes(annotation_bytes)
    authored_hex = sha256_bytes(authored_bytes)
    declaration = {
        "schema_version": 1,
        "source_id": "transcript:main",
        "source_version": "1",
        "file": transcript_file,
        "sha256": transcript_hex,
        "media": {"asset_key": media_asset_key, "sha256": media_hex},
        "producer": "fixture.authoring",
        "producer_version": "1",
    }
    speech_inputs = {
        "speech_annotations": annotations,
        "speech_occurrences": occurrences,
        "source_audio_digest": "sha256:" + media_hex,
        "transcript_digest": "sha256:" + transcript_hex,
        # The annotation authority is the authored-structure byte stream.  Do
        # not substitute the digest of a copied projection for that source
        # identity; the projected annotation bytes remain recorded below for
        # reproducibility.
        "annotation_digest": "sha256:" + authored_hex,
        "correction_version": 0,
        "timing_method": "fixture-authored",
        "speech_coverage": {"state": "complete", "projected": len(segments), "unavailable": 0},
    }
    return {
        "transcript": transcript,
        "transcript_bytes": transcript_bytes,
        "transcript_declaration": declaration,
        "speech_inputs": speech_inputs,
        "digests": {
            "authored_bytes": authored_hex,
            "transcript_bytes": transcript_hex,
            "annotation_bytes": annotation_hex,
            "media": media_hex,
        },
        "preflight": {
            "source": "authored.spoken_segments",
            "source_type": "verified_speech",
            "shotless": all(item.get("shot_id") is None for item in authored["spoken_segments"] if isinstance(item, Mapping)),
            "segments": len(segments),
            "occurrences": len(occurrences),
            "traps_excluded": True,
        },
    }


def materialize_transcript_object(
    client: Any,
    *,
    project_id: str,
    materialization: Mapping[str, Any],
    idempotency_key: str,
) -> Mapping[str, Any]:
    """Ingest the generated bytes and prove Runtime returned the same digest."""

    data = materialization.get("transcript_bytes")
    declaration = materialization.get("transcript_declaration")
    if not isinstance(data, bytes) or not isinstance(declaration, Mapping):
        raise ValueError("invalid verified speech materialization")
    result = client.ingest_project_object(
        project_id,
        data,
        media_type="application/json",
        filename=str(declaration["file"]),
        idempotency_key=idempotency_key,
    )
    ok = bool(getattr(result, "ok", False))
    payload = getattr(result, "data", None)
    if not ok or not isinstance(payload, Mapping):
        raise ValueError("Runtime transcript ingestion failed")
    expected = str(declaration["sha256"])
    returned = next((payload.get(key) for key in ("digest", "content_sha256", "sha256", "object_id") if payload.get(key)), None)
    if not isinstance(returned, str) or returned.removeprefix("sha256:") != expected:
        raise ValueError("Runtime transcript object digest does not match transcript bytes")
    return payload


__all__ = [
    "build_verified_speech_materialization",
    "canonical_json_bytes",
    "materialize_transcript_object",
    "sha256_bytes",
]
