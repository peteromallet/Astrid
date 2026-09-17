"""Canonical shot-composition contract shared with Reigh's editor.

This module validates the T1 wire shape only. It deliberately does not read
legacy ``pinnedShotGroups`` or publish Runtime heads; those require a Runtime
revision-resolution and CAS primitive that workspace.v1 does not expose yet.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

SCHEMA_VERSION = 1
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class StaleWriteError(RuntimeError):
    status = 409
    code = "stale_write"


class ShotCompositionValidationError(ValueError):
    pass


def _fail(path: str, message: str) -> None:
    raise ShotCompositionValidationError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, "must be an object")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, "must be a non-empty string")
    return value


def _int(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        _fail(path, "must be a non-negative integer")
    return value


def _digest(value: Any, path: str) -> str:
    value = _string(value, path)
    if not _DIGEST.fullmatch(value):
        _fail(path, "must be a sha256 digest")
    return value


def _walk_for_legacy(value: Any, path: str = "contract") -> None:
    if isinstance(value, Mapping):
        if "pinnedShotGroups" in value:
            _fail(path, "pinnedShotGroups is migration-only")
        if value.get("clipType") == "shot":
            _fail(path, "clipType=shot is migration-only")
        for key, child in value.items():
            _walk_for_legacy(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_for_legacy(child, f"{path}[{index}]")


def stable_occurrence_deep_link(
    project_id: str,
    parent_document_id: str,
    shot_id: str,
    revision_id: str,
    occurrence_id: str,
) -> str:
    parts = (project_id, parent_document_id, shot_id, revision_id, occurrence_id)
    # Match JavaScript encodeURIComponent used by Reigh's contract validator.
    encoded = [quote(_string(part, "deep_link"), safe="-_.!~*'()") for part in parts]
    return (
        f"project/{encoded[0]}/document/{encoded[1]}/shot/{encoded[2]}"
        f"/revision/{encoded[3]}/occurrence/{encoded[4]}"
    )


def stable_output_identity(project_id: str, parent_document_id: str, occurrence_id: str) -> str:
    parts = (project_id, parent_document_id, occurrence_id)
    encoded = [quote(_string(part, "output_identity"), safe="-_.!~*'()") for part in parts]
    return f"project/{encoded[0]}/document/{encoded[1]}/occurrence/{encoded[2]}/output/final-video"


def assert_expected_head(expected_revision_id: str, actual_revision_id: str) -> None:
    """Apply the local contract guard; this is not Runtime CAS publication."""
    if expected_revision_id != actual_revision_id:
        raise StaleWriteError(
            f"stale shot-composition head: expected {expected_revision_id!r}, "
            f"actual {actual_revision_id!r}"
        )


def validate_shot_composition(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and return a canonical-wire-shaped shot composition mapping."""
    _walk_for_legacy(raw)
    root = _mapping(raw, "contract")
    if root.get("schema_version") != SCHEMA_VERSION:
        _fail("schema_version", f"must be {SCHEMA_VERSION}")

    project = _mapping(root.get("project"), "project")
    project_id = _string(project.get("project_id"), "project.project_id")
    document_id = _string(project.get("document_id"), "project.document_id")
    if project.get("role") != "project":
        _fail("project.role", "must be project")
    primary = _mapping(root.get("primary_timeline"), "primary_timeline")
    if primary.get("role") != "primary_timeline":
        _fail("primary_timeline.role", "must be primary_timeline")
    if primary.get("document_id") != document_id:
        _fail("primary_timeline.document_id", "must match project.document_id")
    head = _mapping(primary.get("head"), "primary_timeline.head")
    head_revision_id = _string(head.get("revision_id"), "primary_timeline.head.revision_id")
    _digest(head.get("content_digest"), "primary_timeline.head.content_digest")

    revisions = root.get("shot_revisions")
    if not isinstance(revisions, list) or not revisions:
        _fail("shot_revisions", "must be a non-empty list")
    revision_keys: set[tuple[str, str]] = set()
    revisions_by_key: dict[tuple[str, str], Mapping[str, Any]] = {}
    for index, raw_revision in enumerate(revisions):
        path = f"shot_revisions[{index}]"
        revision = _mapping(raw_revision, path)
        shot_id = _string(revision.get("shot_id"), f"{path}.shot_id")
        revision_id = _string(revision.get("revision_id"), f"{path}.revision_id")
        key = (shot_id, revision_id)
        if key in revision_keys:
            _fail(path, "duplicate shot/revision identity")
        revision_keys.add(key)
        revisions_by_key[key] = revision
        if revision.get("document_role") != "shot_revision":
            _fail(f"{path}.document_role", "must be shot_revision")
        _digest(revision.get("content_digest"), f"{path}.content_digest")
        internal = _mapping(revision.get("internal_timeline_revision"), f"{path}.internal_timeline_revision")
        _string(internal.get("revision_id"), f"{path}.internal_timeline_revision.revision_id")
        _digest(internal.get("content_digest"), f"{path}.internal_timeline_revision.content_digest")
        timeline = _mapping(internal.get("timeline"), f"{path}.internal_timeline_revision.timeline")
        if not isinstance(timeline.get("tracks"), list) or not isinstance(timeline.get("clips"), list):
            _fail(f"{path}.internal_timeline_revision.timeline", "tracks and clips must be lists")
        timing = _mapping(revision.get("timing"), f"{path}.timing")
        _int(timing.get("duration_ms"), f"{path}.timing.duration_ms")
        audio = _mapping(revision.get("audio"), f"{path}.audio")
        _string(audio.get("track_id"), f"{path}.audio.track_id")
        _string(audio.get("object_id"), f"{path}.audio.object_id")
        _digest(audio.get("digest"), f"{path}.audio.digest")
        audio_scope = _mapping(audio.get("scope"), f"{path}.audio.scope")
        if audio_scope.get("project_id") != project_id:
            _fail(f"{path}.audio.scope.project_id", "must match project.project_id")
        assets = revision.get("assets")
        if not isinstance(assets, list):
            _fail(f"{path}.assets", "must be a list")
        for asset_index, raw_asset in enumerate(assets):
            asset_path = f"{path}.assets[{asset_index}]"
            asset = _mapping(raw_asset, asset_path)
            for field in ("asset_id", "object_id"):
                _string(asset.get(field), f"{asset_path}.{field}")
            _digest(asset.get("digest"), f"{asset_path}.digest")
            _string(asset.get("role"), f"{asset_path}.role")
            scope = _mapping(asset.get("scope"), f"{asset_path}.scope")
            if scope.get("project_id") != project_id:
                _fail(f"{asset_path}.scope.project_id", "must match project.project_id")
        inputs = revision.get("generation_inputs")
        if not isinstance(inputs, list):
            _fail(f"{path}.generation_inputs", "must be a list")
        ordinals: list[int] = []
        for input_index, raw_input in enumerate(inputs):
            input_path = f"{path}.generation_inputs[{input_index}]"
            generation_input = _mapping(raw_input, input_path)
            for field in ("input_id", "object_id", "role"):
                _string(generation_input.get(field), f"{input_path}.{field}")
            _digest(generation_input.get("digest"), f"{input_path}.digest")
            ordinals.append(_int(generation_input.get("ordinal"), f"{input_path}.ordinal"))
        if ordinals != list(range(len(ordinals))):
            _fail(f"{path}.generation_inputs", "ordinals must be contiguous and ordered")
        if not isinstance(revision.get("provenance"), Mapping):
            _fail(f"{path}.provenance", "must be an object")
        for dependency_index, raw_dependency in enumerate(revision.get("dependencies", [])):
            dependency_path = f"{path}.dependencies[{dependency_index}]"
            dependency = _mapping(raw_dependency, dependency_path)
            dep_key = (_string(dependency.get("shot_id"), f"{dependency_path}.shot_id"), _string(dependency.get("revision_id"), f"{dependency_path}.revision_id"))
            if dep_key not in revisions_by_key:
                _fail(dependency_path, "dependency revision is missing")
            if not isinstance(dependency.get("required"), bool):
                _fail(f"{dependency_path}.required", "must be boolean")

    occurrences = root.get("occurrences")
    if not isinstance(occurrences, list) or not occurrences:
        _fail("occurrences", "must be a non-empty list")
    occurrence_ids: set[str] = set()
    for index, raw_occurrence in enumerate(occurrences):
        path = f"occurrences[{index}]"
        occurrence = _mapping(raw_occurrence, path)
        occurrence_id = _string(occurrence.get("occurrence_id"), f"{path}.occurrence_id")
        if occurrence_id in occurrence_ids:
            _fail(path, "duplicate occurrence_id")
        occurrence_ids.add(occurrence_id)
        if occurrence.get("parent_document_id") != document_id:
            _fail(f"{path}.parent_document_id", "must match primary timeline")
        shot_id = _string(occurrence.get("shot_id"), f"{path}.shot_id")
        revision_id = _string(occurrence.get("revision_id"), f"{path}.revision_id")
        if (shot_id, revision_id) not in revisions_by_key:
            _fail(path, "occurrence must pin an available shot revision")
        _int(occurrence.get("ordinal"), f"{path}.ordinal")
        _int(occurrence.get("at_ms"), f"{path}.at_ms")
        _int(occurrence.get("duration_ms"), f"{path}.duration_ms")
        expected_link = stable_occurrence_deep_link(project_id, document_id, shot_id, revision_id, occurrence_id)
        if occurrence.get("stable_deep_link") != expected_link:
            _fail(f"{path}.stable_deep_link", "does not match pinned identity")
        expected_output = stable_output_identity(project_id, document_id, occurrence_id)
        if occurrence.get("output_identity") != expected_output:
            _fail(f"{path}.output_identity", "must be occurrence-qualified")

    cases = _mapping(root.get("cases"), "cases")
    missing = _mapping(cases.get("missing_dependency"), "cases.missing_dependency")
    _string(missing.get("shot_id"), "cases.missing_dependency.shot_id")
    _string(missing.get("revision_id"), "cases.missing_dependency.revision_id")
    if missing.get("expected") != "missing_dependency":
        _fail("cases.missing_dependency.expected", "must be missing_dependency")
    stale = _mapping(cases.get("stale_write_rejection"), "cases.stale_write_rejection")
    _string(stale.get("expected_head_revision_id"), "cases.stale_write_rejection.expected_head_revision_id")
    _string(stale.get("submitted_head_revision_id"), "cases.stale_write_rejection.submitted_head_revision_id")
    if stale.get("expected_status") != 409:
        _fail("cases.stale_write_rejection.expected_status", "must be 409")
    assert_expected_head(head_revision_id, head_revision_id)
    return dict(raw)


def parse_shot_composition(raw: Mapping[str, Any] | str | bytes) -> dict[str, Any]:
    if isinstance(raw, (str, bytes)):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ShotCompositionValidationError("contract: invalid JSON") from exc
    if not isinstance(raw, Mapping):
        _fail("contract", "must be an object")
    return validate_shot_composition(raw)


__all__ = [
    "SCHEMA_VERSION",
    "ShotCompositionValidationError",
    "StaleWriteError",
    "assert_expected_head",
    "parse_shot_composition",
    "stable_occurrence_deep_link",
    "stable_output_identity",
    "validate_shot_composition",
]
