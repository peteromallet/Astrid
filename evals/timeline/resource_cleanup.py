"""Recoverable cleanup for disposable timeline-evaluation resources.

The evaluator deliberately keeps attempt evidence (briefs, traces, results and
receipts) outside the resources it may quarantine.  This module records the
exact resource path and marker before setup, then moves only resources whose
marker, realm and ownership still agree with that receipt.  It never deletes
anything and never treats a name such as ``eval-*`` as ownership proof.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


RESOURCE_MANIFEST_KIND = "astrid.timeline-eval-resources.v1"
QUARANTINE_RECEIPT_KIND = "astrid.timeline-eval-quarantine.v1"
RESOURCE_MARKER_KIND = "astrid.timeline-eval-resource.v1"
WORKSPACE_MARKER_NAME = ".astrid-timeline-eval-workspace.json"


class ResourceCleanupError(ValueError):
    """The manifest or target is not safe to quarantine."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _digest_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ResourceCleanupError(f"cannot read resource marker: {path}") from exc
    return "sha256:" + digest.hexdigest()


def _absolute(path: str | Path, label: str, *, require_exists: bool = False) -> Path:
    try:
        value = Path(path).expanduser()
    except (TypeError, ValueError) as exc:
        raise ResourceCleanupError(f"{label} must be a valid path") from exc
    if not value.is_absolute():
        raise ResourceCleanupError(f"{label} must be an absolute path")
    absolute = value.absolute()
    current = absolute if require_exists or absolute.exists() else absolute.parent
    while True:
        if current.is_symlink():
            raise ResourceCleanupError(f"{label} must not traverse a symlink")
        if current == current.parent:
            break
        current = current.parent
    if require_exists and not absolute.exists():
        raise ResourceCleanupError(f"{label} does not exist: {absolute}")
    return absolute


def _relative_child(root: Path, value: str | Path, label: str) -> Path:
    try:
        child = Path(value)
    except (TypeError, ValueError) as exc:
        raise ResourceCleanupError(f"{label} must be a relative marker name") from exc
    if child.is_absolute() or not child.parts or ".." in child.parts:
        raise ResourceCleanupError(f"{label} must be a relative marker name")
    if len(child.parts) != 1 or child.name in {".", ".."}:
        raise ResourceCleanupError(f"{label} must name one marker file")
    return root / child


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _read_marker(path: Path, label: str) -> tuple[Mapping[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ResourceCleanupError(f"{label} marker is missing or is not a regular file")
    try:
        raw = path.read_bytes()
        marker = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResourceCleanupError(f"{label} marker is not valid JSON") from exc
    if not isinstance(marker, Mapping):
        raise ResourceCleanupError(f"{label} marker must be a JSON object")
    return marker, _digest_bytes(raw)


def _marker_identity(marker: Mapping[str, Any], expected: Mapping[str, Any], label: str) -> None:
    for key, value in expected.items():
        if marker.get(key) != value:
            raise ResourceCleanupError(
                f"{label} marker identity mismatch for {key}: expected {value!r}"
            )


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_resource_manifest(
    manifest_path: str | Path,
    *,
    attempt_id: str,
    realm_id: str,
    evidence_root: str | Path,
    canonical_root: str | Path,
    canonical_realm_id: str,
    resources: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Record exact disposable resources before cleanup is authorized.

    Each resource mapping requires ``name``, ``kind``, ``path`` and ``marker``.
    ``marker`` is one filename relative to ``path``.  A resource may be
    ``planned`` when setup can be interrupted before the directory exists; a
    ``ready`` resource must exist and carry the declared marker identity.
    ``marker_identity`` is deliberately explicit so a matching filename alone
    can never authorize quarantine.
    """

    if not isinstance(attempt_id, str) or not attempt_id or Path(attempt_id).name != attempt_id:
        raise ResourceCleanupError("attempt_id must be a non-empty path-safe name")
    if not isinstance(realm_id, str) or not realm_id or realm_id == canonical_realm_id:
        raise ResourceCleanupError("disposable realm_id must differ from the canonical realm")
    manifest = _absolute(manifest_path, "resource manifest")
    evidence = _absolute(evidence_root, "evidence root", require_exists=True).resolve()
    canonical = _absolute(canonical_root, "canonical root", require_exists=True).resolve()
    if evidence == canonical or _inside(evidence, canonical) or _inside(canonical, evidence):
        raise ResourceCleanupError("evidence and canonical roots must be separate")
    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for raw in resources:
        if not isinstance(raw, Mapping):
            raise ResourceCleanupError("resource entries must be objects")
        name = raw.get("name")
        kind = raw.get("kind")
        if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."}:
            raise ResourceCleanupError("resource name must be a path-safe basename")
        if name in names:
            raise ResourceCleanupError(f"duplicate resource name: {name}")
        names.add(name)
        if not isinstance(kind, str) or not kind:
            raise ResourceCleanupError(f"resource {name} has no kind")
        root = _absolute(raw.get("path"), f"resource {name} path")
        marker_name = raw.get("marker")
        marker_path = _relative_child(root, marker_name, f"resource {name} marker")
        state = raw.get("state", "ready")
        if state not in {"planned", "ready"}:
            raise ResourceCleanupError(f"resource {name} state must be planned or ready")
        marker_identity = raw.get("marker_identity")
        if not isinstance(marker_identity, Mapping) or not marker_identity:
            raise ResourceCleanupError(f"resource {name} requires marker_identity")
        marker_digest = None
        if state == "ready":
            root = _absolute(root, f"resource {name} path", require_exists=True).resolve()
            marker, marker_digest = _read_marker(marker_path, f"resource {name}")
            _marker_identity(marker, marker_identity, f"resource {name}")
        else:
            # Planned resources may not exist yet, but if an early setup step
            # created one, capture its exact marker and treat it as ready.
            if root.exists():
                root = _absolute(root, f"resource {name} path", require_exists=True).resolve()
                marker, marker_digest = _read_marker(marker_path, f"resource {name}")
                _marker_identity(marker, marker_identity, f"resource {name}")
                state = "ready"
        if root == canonical or _inside(root, canonical) or _inside(canonical, root):
            raise ResourceCleanupError(f"resource {name} overlaps canonical root")
        if root == evidence or _inside(evidence, root) or _inside(root, evidence):
            raise ResourceCleanupError(f"resource {name} overlaps evidence root")
        normalized.append({
            "name": name,
            "kind": kind,
            "path": str(root),
            "marker": str(marker_name),
            "marker_identity": dict(marker_identity),
            "marker_sha256": marker_digest,
            "realm_id": raw.get("realm_id", realm_id),
            "state": state,
        })
    payload = {
        "kind": RESOURCE_MANIFEST_KIND,
        "version": 1,
        "attempt_id": attempt_id,
        "realm_id": realm_id,
        "evidence_root": str(evidence),
        "canonical_root": str(canonical),
        "canonical_realm_id": canonical_realm_id,
        "resources": normalized,
    }
    _write_json(manifest, payload)
    return payload


def _load_manifest(path: Path) -> tuple[dict[str, Any], str]:
    if path.is_symlink() or not path.is_file():
        raise ResourceCleanupError("resource manifest is missing or is not a regular file")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ResourceCleanupError("resource manifest is not valid JSON") from exc
    if not isinstance(payload, dict) or payload.get("kind") != RESOURCE_MANIFEST_KIND or payload.get("version") != 1:
        raise ResourceCleanupError("resource manifest kind/version is unsupported")
    return payload, _digest_bytes(raw)


def cleanup_attempt_resources(
    manifest_path: str | Path,
    *,
    quarantine_root: str | Path,
) -> dict[str, Any]:
    """Move verified disposable resources to a recoverable quarantine.

    The operation is idempotent: an already-quarantined resource is reported
    as such, while a planned-but-never-created resource is reported as
    ``not_created``.  A ready resource missing from both source and quarantine
    is an error, not a reason to guess that it was deleted.  No evidence path
    is ever moved or deleted.
    """

    manifest_file = _absolute(manifest_path, "resource manifest", require_exists=True)
    payload, manifest_digest = _load_manifest(manifest_file)
    attempt_id = payload.get("attempt_id")
    realm_id = payload.get("realm_id")
    canonical_realm_id = payload.get("canonical_realm_id")
    if not isinstance(attempt_id, str) or Path(attempt_id).name != attempt_id:
        raise ResourceCleanupError("resource manifest has an unsafe attempt_id")
    if not isinstance(realm_id, str) or not realm_id or realm_id == canonical_realm_id:
        raise ResourceCleanupError("resource manifest has an ambiguous/canonical realm")
    evidence = _absolute(payload.get("evidence_root"), "evidence root", require_exists=True).resolve()
    canonical = _absolute(payload.get("canonical_root"), "canonical root", require_exists=True).resolve()
    quarantine = _absolute(quarantine_root, "quarantine root")
    if quarantine == canonical or _inside(quarantine, canonical) or _inside(canonical, quarantine):
        raise ResourceCleanupError("quarantine root overlaps canonical root")
    if quarantine == evidence or _inside(quarantine, evidence) or _inside(evidence, quarantine):
        raise ResourceCleanupError("quarantine root overlaps evidence root")
    destination_root = (quarantine / attempt_id).absolute()
    if _inside(destination_root, canonical) or _inside(destination_root, evidence):
        raise ResourceCleanupError("quarantine destination overlaps protected roots")
    receipt_path = destination_root / "quarantine-receipt.json"
    if receipt_path.exists():
        try:
            existing = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ResourceCleanupError("quarantine receipt is not valid JSON") from exc
        if (
            not isinstance(existing, Mapping)
            or existing.get("kind") != QUARANTINE_RECEIPT_KIND
            or existing.get("manifest_sha256") != manifest_digest
            or existing.get("attempt_id") != attempt_id
        ):
            raise ResourceCleanupError("quarantine receipt does not match the current manifest")
        existing_rows = existing.get("resources")
        if not isinstance(existing_rows, list):
            raise ResourceCleanupError("quarantine receipt resources are malformed")
        for existing_row in existing_rows:
            if not isinstance(existing_row, Mapping) or existing_row.get("status") not in {"quarantined", "already_quarantined"}:
                continue
            name = existing_row.get("name")
            if not isinstance(name, str) or Path(name).name != name:
                raise ResourceCleanupError("quarantine receipt contains an unsafe resource name")
            destination = destination_root / name
            marker_row = next((row for row in payload.get("resources", []) if isinstance(row, Mapping) and row.get("name") == name), None)
            if marker_row is None:
                raise ResourceCleanupError(f"quarantine receipt has an unknown resource: {name}")
            marker_path = _relative_child(destination, marker_row.get("marker"), f"quarantined resource {name} marker")
            marker, marker_digest = _read_marker(marker_path, f"quarantined resource {name}")
            _marker_identity(marker, marker_row.get("marker_identity", {}), f"quarantined resource {name}")
            if marker_digest != marker_row.get("marker_sha256"):
                raise ResourceCleanupError(f"quarantined resource {name} marker digest changed")
        return dict(existing)
    rows = payload.get("resources")
    if not isinstance(rows, list):
        raise ResourceCleanupError("resource manifest resources must be a list")
    outcomes: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ResourceCleanupError("resource manifest contains a malformed entry")
        name = row.get("name")
        if not isinstance(name, str) or Path(name).name != name or name in seen_names:
            raise ResourceCleanupError("resource manifest contains a duplicate/unsafe name")
        seen_names.add(name)
        source = _absolute(row.get("path"), f"resource {name} path")
        destination = destination_root / name
        if source == canonical or _inside(source, canonical) or _inside(canonical, source):
            raise ResourceCleanupError(f"resource {name} overlaps canonical root")
        if source == evidence or _inside(source, evidence) or _inside(evidence, source):
            raise ResourceCleanupError(f"resource {name} overlaps evidence root")
        if source == quarantine or _inside(source, quarantine) or _inside(quarantine, source):
            raise ResourceCleanupError(f"resource {name} overlaps quarantine root")
        if destination.exists() and source.exists():
            raise ResourceCleanupError(f"resource {name} exists at both source and quarantine destination")
        if destination.exists():
            dest_marker = _relative_child(destination, row.get("marker"), f"resource {name} marker")
            marker, digest = _read_marker(dest_marker, f"quarantined resource {name}")
            _marker_identity(marker, row.get("marker_identity", {}), f"quarantined resource {name}")
            if digest != row.get("marker_sha256"):
                raise ResourceCleanupError(f"quarantined resource {name} marker digest changed")
            outcomes.append({"name": name, "status": "already_quarantined", "path": str(destination)})
            continue
        if not source.exists():
            if row.get("state") == "planned":
                outcomes.append({"name": name, "status": "not_created", "path": str(source)})
                continue
            raise ResourceCleanupError(f"ready resource {name} is missing from source and quarantine")
        source = _absolute(source, f"resource {name} path", require_exists=True).resolve()
        marker_path = _relative_child(source, row.get("marker"), f"resource {name} marker")
        marker, digest = _read_marker(marker_path, f"resource {name}")
        _marker_identity(marker, row.get("marker_identity", {}), f"resource {name}")
        if digest != row.get("marker_sha256"):
            raise ResourceCleanupError(f"resource {name} marker digest changed")
        row_realm = row.get("realm_id")
        if row_realm is not None and row_realm != realm_id:
            raise ResourceCleanupError(f"resource {name} realm does not match manifest")
        if destination.exists():
            raise ResourceCleanupError(f"resource {name} quarantine destination appeared during cleanup")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        outcomes.append({"name": name, "status": "quarantined", "path": str(destination)})
    receipt = {
        "kind": QUARANTINE_RECEIPT_KIND,
        "version": 1,
        "attempt_id": attempt_id,
        "realm_id": realm_id,
        "manifest_sha256": manifest_digest,
        "quarantine_root": str(destination_root),
        "resources": outcomes,
        "evidence_root": str(evidence),
    }
    _write_json(receipt_path, receipt)
    return receipt


__all__ = [
    "QUARANTINE_RECEIPT_KIND",
    "RESOURCE_MANIFEST_KIND",
    "RESOURCE_MARKER_KIND",
    "WORKSPACE_MARKER_NAME",
    "ResourceCleanupError",
    "cleanup_attempt_resources",
    "write_resource_manifest",
]
