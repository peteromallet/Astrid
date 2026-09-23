"""Read and freeze the pinned Astrid Intro authoring closure for eval attempts.

This is a read-only source adapter. It reads only the revision named by
``fixture.EXPECTED_SOURCE_HEAD`` and exports all media selected by active
parent/child clip and item records into an attempt-local, digest-checked folder.
It never writes to Runtime and requires explicit connection/output arguments.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .fixture import (
    EXPECTED_SOURCE_HEAD,
    SOURCE_PROJECT_ID,
    SOURCE_PROJECT_SLUG,
    SOURCE_TIMELINE_ID,
    Baseline,
    FixtureError,
    MediaRequirement,
    export_baseline,
)


class SourceExportError(FixtureError):
    """Pinned source or media could not be exported faithfully."""


def _plain(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__") and not isinstance(value, type):
        from dataclasses import asdict
        return _plain(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(child) for child in value]
    return value


def _data(value: Any, label: str) -> Mapping[str, Any]:
    value = _plain(value)
    data = value.get("data", value) if isinstance(value, Mapping) else None
    if not isinstance(data, Mapping):
        raise SourceExportError(f"Runtime {label} response has no record")
    return data


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _sha(_canonical(value))


def _media_digest(entry: Mapping[str, Any]) -> str | None:
    for key in ("content_sha256", "media_id", "object_id", "digest"):
        value = entry.get(key)
        if isinstance(value, str) and value:
            if value.startswith("sha256:"):
                return value
            if len(value) == 64 and all(ch in "0123456789abcdef" for ch in value.lower()):
                return "sha256:" + value.lower()
    return None


def _active_media_records(payload: Mapping[str, Any], owner: str) -> list[tuple[str, str, str]]:
    """Yield (digest, media type, active selector path), excluding registry history."""
    registry = payload.get("registry", {})
    assets = registry.get("assets", {}) if isinstance(registry, Mapping) else {}
    if not isinstance(assets, Mapping):
        assets = {}
    found: list[tuple[str, str, str]] = []

    def add(entry: Any, path: str, fallback_type: str | None = None) -> None:
        if isinstance(entry, str):
            entry = assets.get(entry)
        if not isinstance(entry, Mapping):
            return
        digest = _media_digest(entry)
        if not digest:
            return
        media_type = entry.get("type") or fallback_type or "application/octet-stream"
        media_type = str(media_type)
        if "/" not in media_type:
            media_type = {"image": "image/png", "video": "video/mp4", "audio": "audio/wav"}.get(media_type, "application/octet-stream")
        found.append((digest, media_type, f"{owner}:{path}"))

    for index, clip in enumerate(payload.get("clips", []) if isinstance(payload.get("clips"), list) else []):
        if isinstance(clip, Mapping):
            add(clip.get("asset"), f"clips[{index}].asset")
            # Some transport forms keep direct references under explicit media fields.
            for key in ("media_id", "object_id", "source_ref"):
                if clip.get(key):
                    add({key: clip[key], "type": clip.get("media_type")}, f"clips[{index}].{key}")
    for field in ("items", "audio_bindings"):
        rows = payload.get(field, [])
        if isinstance(rows, list):
            for index, row in enumerate(rows):
                if isinstance(row, Mapping):
                    add(row, f"{field}[{index}]")
    return found


def _closure_media_records(payload: Mapping[str, Any], owner: str) -> list[tuple[str, str, str]]:
    """Collect every authoritative media_id/object_id in the immutable bytes.

    Runtime validates dependency ownership by walking the full published
    payload, including media alternatives in registries. Keep their usage path
    visible in ``required_by`` so they cannot be confused with selected media.
    """
    found: list[tuple[str, str, str]] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if key in {"media_id", "object_id"} and isinstance(child, str):
                    digest = child.removeprefix("sha256:")
                    if len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest.lower()):
                        found.append(("sha256:" + digest.lower(), "application/octet-stream", f"{owner}:{child_path}"))
                walk(child, child_path)
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "")
    return found


def collect_active_media(
    parent: Mapping[str, Any],
    shots: list[Mapping[str, Any]],
    internal_timelines: list[Mapping[str, Any]],
) -> tuple[MediaRequirement, ...]:
    references: dict[str, dict[str, Any]] = defaultdict(lambda: {"types": set(), "uses": set()})
    payloads: list[tuple[str, Mapping[str, Any]]] = [("parent", parent["payload"])]
    payloads.extend((f"shot:{row['revision_id']}", row["payload"]) for row in shots)
    payloads.extend((f"internal:{row['revision_id']}", row["payload"]) for row in internal_timelines)
    for owner, payload in payloads:
        for digest, media_type, path in _active_media_records(payload, owner) + _closure_media_records(payload, owner):
            ref = references[digest]
            ref["types"].add(media_type)
            ref["uses"].add(path)

    rows = []
    for digest in sorted(references):
        types = references[digest]["types"]
        concrete_types = types - {"application/octet-stream"}
        if len(concrete_types) > 1:
            raise SourceExportError(f"active object {digest} has conflicting media types: {sorted(concrete_types)}")
        rows.append(MediaRequirement(
            digest=digest,
            source_object_id=digest,
            media_type=next(iter(concrete_types or types)),
            required_by=tuple(sorted(references[digest]["uses"])),
            source_handle=f"media/{digest.removeprefix('sha256:')}",
        ))
    return tuple(rows)


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise SourceExportError(f"refusing to overwrite symlink: {path}")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _download_bytes(workspace: Any, digest: str) -> bytes:
    response = _plain(workspace.get_object(digest))
    data = response.get("data") if isinstance(response, Mapping) else None
    if not isinstance(data, bytes):
        raise SourceExportError(f"Runtime object read returned no bytes for {digest}")
    if _sha(data) != digest:
        raise SourceExportError(f"Runtime object bytes do not match requested digest {digest}")
    return data


def export_pinned_baseline(workspace: Any, output_dir: str | Path) -> tuple[Baseline, Mapping[str, Any]]:
    """Read the immutable pinned closure and verified bytes to ``output_dir``.

    ``head_observation`` records the live mutable timeline pointer separately
    from the pinned authoring revision. The pinned revision remains the source
    fixture even if the legacy editor pointer has advanced.
    """
    output = Path(output_dir).expanduser().absolute()
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink():
        raise SourceExportError("export output directory must not be a symlink")
    timeline = _data(workspace.get_timeline(SOURCE_TIMELINE_ID, project_id=SOURCE_PROJECT_ID), "get_timeline")
    if timeline.get("project_id") != SOURCE_PROJECT_ID or timeline.get("timeline_id") != SOURCE_TIMELINE_ID:
        raise SourceExportError("live timeline identity differs from the pinned source")
    current_timeline_head = timeline.get("head_revision_id")

    parent = _data(workspace.get_project_parent_composition_revision(
        SOURCE_PROJECT_ID, SOURCE_TIMELINE_ID, EXPECTED_SOURCE_HEAD,
    ), "get_project_parent_composition_revision")
    if parent.get("revision_id") != EXPECTED_SOURCE_HEAD:
        raise SourceExportError("Runtime did not return the exact pinned parent revision")
    if parent.get("project_id") != SOURCE_PROJECT_ID or parent.get("timeline_id") != SOURCE_TIMELINE_ID:
        raise SourceExportError("pinned parent revision belongs to a different project or timeline")
    payload = parent.get("payload")
    if not isinstance(payload, Mapping):
        raise SourceExportError("pinned parent revision has no payload")
    occurrences = payload.get("occurrences")
    if not isinstance(occurrences, list) or not occurrences:
        raise SourceExportError("pinned parent revision has no occurrence list")

    shots_by_revision: dict[str, Mapping[str, Any]] = {}
    internals_by_revision: dict[str, Mapping[str, Any]] = {}
    for index, occurrence in enumerate(occurrences):
        if not isinstance(occurrence, Mapping):
            raise SourceExportError(f"parent occurrence {index} is malformed")
        shot_id = occurrence.get("shot_id")
        shot_revision_id = occurrence.get("shot_revision_id")
        if not isinstance(shot_id, str) or not isinstance(shot_revision_id, str):
            raise SourceExportError(f"parent occurrence {index} lacks pinned shot identity")
        if shot_revision_id not in shots_by_revision:
            shot = _data(workspace.get_project_shot_revision(
                SOURCE_PROJECT_ID, shot_id, shot_revision_id,
            ), "get_project_shot_revision")
            if shot.get("revision_id") != shot_revision_id or shot.get("shot_id") != shot_id:
                raise SourceExportError(f"Runtime returned the wrong shot revision for occurrence {index}")
            shots_by_revision[shot_revision_id] = shot
        shot = shots_by_revision[shot_revision_id]
        internal_revision_id = shot.get("internal_timeline_revision_id")
        if not isinstance(internal_revision_id, str):
            internal_revision_id = shot.get("payload", {}).get("internal_timeline_revision_id")
        if not isinstance(internal_revision_id, str):
            raise SourceExportError(f"shot revision {shot_revision_id} lacks its internal-timeline pin")
        if internal_revision_id not in internals_by_revision:
            internal = _data(workspace.get_project_timeline_revision(
                SOURCE_PROJECT_ID, SOURCE_TIMELINE_ID, internal_revision_id,
            ), "get_project_timeline_revision")
            if internal.get("revision_id") != internal_revision_id:
                raise SourceExportError(f"Runtime returned the wrong internal revision for shot {shot_revision_id}")
            internals_by_revision[internal_revision_id] = internal

    shots = sorted(shots_by_revision.values(), key=lambda row: str(row["revision_id"]))
    internals = sorted(internals_by_revision.values(), key=lambda row: str(row["revision_id"]))
    media = collect_active_media(parent, shots, internals)
    # Resolve the exact Runtime content type and verify every historical
    # registry reference is project-owned before exporting bytes.
    from astrid.sdk.workspace_client import paged_rows
    source_objects = paged_rows(workspace.list_project_objects, SOURCE_PROJECT_ID, limit=100) or []
    object_by_digest = {
        str(row.get("object_id") or row.get("digest")): row
        for row in source_objects if isinstance(row, Mapping)
    }
    normalized_media: list[MediaRequirement] = []
    for requirement in media:
        source_object = object_by_digest.get(requirement.digest)
        if source_object is None:
            raise SourceExportError(f"pinned closure media dependency is not owned by the source project: {requirement.digest}")
        normalized_media.append(MediaRequirement(
            digest=requirement.digest,
            source_object_id=str(source_object.get("object_id") or source_object.get("digest")),
            media_type=str(source_object.get("media_type") or requirement.media_type),
            required_by=requirement.required_by,
            source_handle=requirement.source_handle,
        ))
    media = tuple(normalized_media)
    source_hashes = {
        f"parent:{EXPECTED_SOURCE_HEAD}": _digest(parent),
        **{f"shot:{row['revision_id']}": _digest(row) for row in shots},
        **{f"internal:{row['revision_id']}": _digest(row) for row in internals},
    }
    fps = payload.get("frame_rate") or payload.get("fps") or {"numerator": 30, "denominator": 1}
    if not isinstance(fps, Mapping) or not isinstance(fps.get("numerator"), int) or not isinstance(fps.get("denominator"), int):
        raise SourceExportError("pinned parent has no interpretable frame rate")
    baseline = export_baseline(
        project_id=SOURCE_PROJECT_ID,
        project_slug=SOURCE_PROJECT_SLUG,
        timeline_id=SOURCE_TIMELINE_ID,
        observed_head=EXPECTED_SOURCE_HEAD,
        parent_revision=parent,
        shot_revisions=shots,
        internal_timeline_revisions=internals,
        media=media,
        frame_rate=fps,
        source_hashes=source_hashes,
    )

    for requirement in media:
        data = _download_bytes(workspace, requirement.source_object_id)
        _atomic_write(output / requirement.source_handle, data)
    _atomic_write(output / "baseline.json", _canonical(baseline.as_dict()) + b"\n")
    _atomic_write(output / "head-observation.json", _canonical({
        "source_project_id": SOURCE_PROJECT_ID,
        "source_timeline_id": SOURCE_TIMELINE_ID,
        "mutable_timeline_head_before": current_timeline_head,
        "pinned_authoring_revision": EXPECTED_SOURCE_HEAD,
        "pinned_parent_content_digest": parent.get("content_digest"),
        "source_head_is_current_timeline_pointer": current_timeline_head == EXPECTED_SOURCE_HEAD,
    }) + b"\n")
    return baseline, {
        "project_id": SOURCE_PROJECT_ID,
        "timeline_id": SOURCE_TIMELINE_ID,
        "mutable_timeline_head_before": current_timeline_head,
        "pinned_authoring_revision": EXPECTED_SOURCE_HEAD,
        "closure_digest": baseline.closure_digest,
        "semantic_digest": baseline.semantic_digest,
        "media_count": len(media),
        "media_bytes": sum((output / row.source_handle).stat().st_size for row in media),
        "output_dir": str(output),
    }


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True, help="explicit loopback Runtime endpoint")
    parser.add_argument("--credential-file", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    from astrid.sdk.workspace_client import WorkspaceClient

    workspace = WorkspaceClient(args.endpoint, args.credential_file)
    health = _data(workspace.health(), "health")
    if health.get("status") != "ok":
        raise SourceExportError("Runtime health check failed")
    workspace.handshake("timeline-eval-source-export", "1", ["projects:read", "objects:read"])
    baseline, report = export_pinned_baseline(workspace, args.output_dir)
    print(json.dumps({"ok": True, "baseline": report}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["SourceExportError", "collect_active_media", "export_pinned_baseline"]
