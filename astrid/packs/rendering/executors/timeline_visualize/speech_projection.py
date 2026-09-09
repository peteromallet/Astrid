"""Pure projection of immutable speech annotations into render time.

The helper accepts the small JSON-shaped records used by render snapshots and
does not discover transcripts, call an ASR provider, or consult current
timeline state.  Source and render ranges are closed-open and represented as
fractions until the final JSON conversion.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from fractions import Fraction
from typing import Any, Mapping, Sequence

PROJECTION_VERSION = "astrid.speech-projection.v1"


class SpeechProjectionError(ValueError):
    """An annotation or occurrence cannot be projected without guessing."""


def _fraction(value: object, label: str, *, allow_none: bool = False) -> Fraction | None:
    if value is None and allow_none:
        return None
    if isinstance(value, bool):
        raise SpeechProjectionError(f"{label} must be rational")
    try:
        result = Fraction(str(value))
    except (TypeError, ValueError, ZeroDivisionError) as exc:
        raise SpeechProjectionError(f"{label} must be rational") from exc
    if result < 0 or not math.isfinite(float(result)):
        raise SpeechProjectionError(f"{label} must be finite and non-negative")
    return result


def _ratio(value: Fraction) -> list[int]:
    return [value.numerator, value.denominator]


def _first(record: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in record:
            return record[key]
    return default


def _digest(value: object, label: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    raw = str(value or "").removeprefix("sha256:")
    if not re.fullmatch(r"[0-9a-f]{64}", raw):
        raise SpeechProjectionError(f"{label} must be a sha256 digest")
    return "sha256:" + raw


def speech_annotation_identity(
    *,
    source_audio_digest: str | None,
    annotation_digest: str | None,
    transcript_digest: str | None = None,
    correction_version: object = 0,
    timing_method: str | None = None,
) -> str:
    """Return the immutable identity of one frozen annotation set."""
    payload = {
        "version": PROJECTION_VERSION,
        "source_audio_digest": _digest(source_audio_digest, "source_audio_digest", optional=True),
        "annotation_digest": _digest(annotation_digest, "annotation_digest", optional=True),
        "transcript_digest": _digest(transcript_digest, "transcript_digest", optional=True),
        "correction_version": correction_version,
        "timing_method": timing_method,
    }
    return "sha256:" + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _source_window(occurrence: Mapping[str, Any]) -> tuple[Fraction, Fraction]:
    trim = occurrence.get("trim") if isinstance(occurrence.get("trim"), Mapping) else occurrence
    # ``start``/``end`` on an admitted shot occurrence are render placement;
    # accepting them as source bounds would silently project against the wrong
    # clock.  Source bounds must be explicit (or supplied as a duration).
    source_start = _fraction(_first(trim, "source_start", "from", default=0), "occurrence source start")
    source_end_raw = _first(trim, "source_end", "to")
    if source_end_raw is None:
        duration = _fraction(_first(occurrence, "source_duration", "duration", "hold"), "occurrence duration")
        if duration is None:
            raise SpeechProjectionError("occurrence needs source end or duration")
        source_end = source_start + duration
    else:
        source_end = _fraction(source_end_raw, "occurrence source end")
    assert source_start is not None and source_end is not None
    if source_end <= source_start:
        raise SpeechProjectionError("occurrence source interval must be non-empty")
    return source_start, source_end


def _placement(occurrence: Mapping[str, Any]) -> Fraction:
    value = _first(occurrence, "placement", "timeline_start", "at", "start", default=0)
    result = _fraction(value, "occurrence placement")
    assert result is not None
    return result


def _speed(occurrence: Mapping[str, Any]) -> Fraction:
    result = _fraction(_first(occurrence, "speed", "rate", default=1), "occurrence speed")
    assert result is not None
    if result <= 0:
        raise SpeechProjectionError("occurrence speed must be positive")
    return result


def _warp_state(occurrence: Mapping[str, Any]) -> str:
    warp = occurrence.get("time_warp", occurrence.get("warp"))
    if warp in (None, "linear", "affine", "constant_speed"):
        return "supported"
    if isinstance(warp, Mapping) and warp.get("kind") in (None, "linear", "affine", "constant_speed"):
        return "supported"
    return "unavailable"


def _annotation_text(annotation: Mapping[str, Any]) -> tuple[str, str | None]:
    canonical = _first(annotation, "canonical_text", "text", "canonical", default="")
    recognized = _first(annotation, "recognized_text", "recognized", "asr_text")
    if not isinstance(canonical, str) or not isinstance(recognized, (str, type(None))):
        raise SpeechProjectionError("speech annotation text fields must be strings")
    return canonical, recognized


def _annotation_interval(annotation: Mapping[str, Any]) -> tuple[Fraction, Fraction] | None:
    start = _first(annotation, "source_start", "start", "onset")
    end = _first(annotation, "source_end", "end", "offset")
    if start is None or end is None:
        return None
    left, right = _fraction(start, "annotation start"), _fraction(end, "annotation end")
    assert left is not None and right is not None
    if right <= left:
        return None
    return left, right


def _project_one(annotation: Mapping[str, Any], occurrence: Mapping[str, Any], occurrence_index: int, identity: str) -> dict[str, Any]:
    canonical, recognized = _annotation_text(annotation)
    annotation_id = str(_first(annotation, "annotation_id", "id", "segment_id", default=f"annotation-{occurrence_index:04d}"))
    occurrence_id = str(_first(occurrence, "occurrence_id", "id", default=f"occurrence-{occurrence_index:04d}"))
    common = {
        "id": f"phrase:{identity.removeprefix('sha256:')}:{occurrence_id}:{annotation_id}",
        "annotation_id": annotation_id,
        "occurrence_id": occurrence_id,
        "canonical_text": canonical,
        "recognized_text": recognized,
        "text": canonical,
        "uncertainty": _first(annotation, "uncertainty", "confidence", default=None),
        "timing_method": _first(annotation, "timing_method", "timing_basis", default="frozen_annotation"),
        "coverage": _first(annotation, "coverage", default="complete"),
        "correction_version": _first(annotation, "correction_version", default=0),
        "annotation_identity": identity,
    }
    if _warp_state(occurrence) == "unavailable":
        return {**common, "status": "unavailable", "mapping_state": "unsupported_non_linear_time_warp", "render_interval": None}
    source_interval = _annotation_interval(annotation)
    if source_interval is None:
        return {**common, "status": "unavailable", "mapping_state": "missing_timing_span", "render_interval": None}
    source_start, source_end = _source_window(occurrence)
    overlap_start, overlap_end = max(source_start, source_interval[0]), min(source_end, source_interval[1])
    if overlap_end <= overlap_start:
        return {**common, "status": "unavailable", "mapping_state": "outside_occurrence", "render_interval": None}
    placement, speed = _placement(occurrence), _speed(occurrence)
    render_start = placement + (overlap_start - source_start) / speed
    render_end = placement + (overlap_end - source_start) / speed
    return {
        **common,
        "status": "projected",
        "mapping_state": "clipped" if (overlap_start != source_interval[0] or overlap_end != source_interval[1]) else "exact",
        "source_interval": {"start": _ratio(overlap_start), "end": _ratio(overlap_end)},
        "render_interval": {"start": _ratio(render_start), "end": _ratio(render_end), "half_open": True},
        "start": _ratio(render_start),
        "end": _ratio(render_end),
        "duration": _ratio(render_end - render_start),
    }


def project_speech_annotations(
    annotations: Sequence[Mapping[str, Any]] | None,
    occurrences: Sequence[Mapping[str, Any]] | None,
    *,
    source_audio_digest: str | None = None,
    transcript_digest: str | None = None,
    annotation_digest: str | None = None,
    correction_version: object = 0,
    timing_method: str | None = None,
    coverage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project frozen source annotations through every linear occurrence."""
    source_digest = _digest(source_audio_digest, "source_audio_digest", optional=True)
    frozen_digest = _digest(annotation_digest or transcript_digest, "annotation_digest", optional=True)
    annotation_identity = speech_annotation_identity(
        source_audio_digest=source_digest,
        annotation_digest=frozen_digest,
        transcript_digest=transcript_digest,
        correction_version=correction_version,
        timing_method=timing_method,
    )
    raw_annotations = list(annotations or [])
    raw_occurrences = list(occurrences or [])
    if not raw_annotations:
        status = "no_transcript"
    elif not raw_occurrences:
        status = "no_occurrences"
    else:
        status = "available"
    phrases: list[dict[str, Any]] = []
    for occurrence_index, occurrence in enumerate(raw_occurrences):
        if not isinstance(occurrence, Mapping):
            raise SpeechProjectionError("occurrences must contain objects")
        for annotation in raw_annotations:
            if not isinstance(annotation, Mapping):
                raise SpeechProjectionError("annotations must contain objects")
            annotation_key = str(_first(annotation, "annotation_id", "id", "segment_id", default=""))
            linked_key = _first(occurrence, "annotation_id", "segment_id", "annotation_ref")
            linked_keys = occurrence.get("annotation_ids")
            if linked_key is not None and str(linked_key) != annotation_key:
                continue
            if isinstance(linked_keys, Sequence) and not isinstance(linked_keys, (str, bytes)) and annotation_key not in {str(value) for value in linked_keys}:
                continue
            phrases.append(_project_one(annotation, occurrence, occurrence_index, annotation_identity))
    projected = [item for item in phrases if item["status"] == "projected"]
    missing = [item for item in phrases if item["status"] != "projected"]
    return {
        "schema_version": 1,
        "projection_version": PROJECTION_VERSION,
        "status": status,
        "source_audio_digest": source_digest,
        "transcript_digest": frozen_digest,
        "annotation_digest": frozen_digest,
        "annotation_identity": annotation_identity,
        "correction_version": correction_version,
        "timing_contract": "rational half-open source and render intervals",
        "timing_method": timing_method,
        "coverage": dict(coverage or {"state": "complete" if projected else status, "projected": len(projected), "unavailable": len(missing)}),
        "phrases": phrases,
        "unavailable": missing,
    }


# Short aliases are kept in this owner for callers using the plan's vocabulary.
project_speech = project_speech_annotations
build_speech_projection = project_speech_annotations

__all__ = [
    "PROJECTION_VERSION", "SpeechProjectionError", "speech_annotation_identity",
    "project_speech_annotations", "project_speech", "build_speech_projection",
]
