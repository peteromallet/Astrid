"""Resolve, verify, materialize, and request opening one runtime render.

This is the Astrid-side read-only opening lane. Runtime remains authoritative
for project, run, task, publication, and managed-object state; this module
only selects within an explicit scope and materializes verified bytes into the
user cache. It deliberately has no filesystem/database/CAS discovery path.
"""

from __future__ import annotations

import hashlib
import os
import platform
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .contracts import DomainResult, ErrorObject
from .pagination import paged_rows
from .workspace_client import WorkspaceClientError

__all__ = ["open_project_render", "open_render"]

_SUCCESS_STATES = frozenset({"completed", "succeeded", "success"})
_VIDEO_SUFFIXES = frozenset({".mp4", ".mov", ".webm", ".mkv"})
_VIDEO_MEDIA_TYPES = frozenset(
    {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska"}
)
_SAFE_FILENAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_LOCAL_REFERENCE_PREFIXES = ("/", "\\", "file:", "cas:", "sqlite:")


def _failure(code: str, message: str, **details: Any) -> DomainResult[Any]:
    return DomainResult.failure(ErrorObject(code, message, details))


def _identifier(row: Mapping[str, Any], *names: str) -> str:
    for name in names:
        value = row.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _state(row: Mapping[str, Any]) -> str:
    return _identifier(row, "status", "state").lower()


def _render_capability(row: Mapping[str, Any]) -> str:
    return _identifier(row, "capability_id", "capability")


def _legacy_output_name(spec: Any) -> str | None:
    """Read the producing task's bounded historical output-name fallback."""

    if not isinstance(spec, Mapping):
        return None
    value = spec.get("output_name")
    if isinstance(value, str) and _validate_filename(value):
        return value
    for key in ("inputs", "params", "spec"):
        nested = _legacy_output_name(spec.get(key))
        if nested:
            return nested
    return None


def _timeline_provenance(value: Any) -> set[str]:
    """Return explicit canonical timeline references in a run/task spec."""

    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key in ("timeline_ref", "timeline_id"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                refs.add(candidate.strip())
        # These are the documented admission envelopes. Arbitrary metadata
        # and legacy file inputs are intentionally not treated as provenance.
        for key in ("spec", "inputs", "params"):
            if key in value:
                refs.update(_timeline_provenance(value[key]))
    elif isinstance(value, list):
        for child in value:
            refs.update(_timeline_provenance(child))
    return refs


def _default_cache_root() -> Path:
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Caches" / "Astrid" / "renders"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "astrid" / "renders"


def _normalize_digest(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    digest = value.strip().lower().removeprefix("sha256:")
    if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        return None
    return digest


def _safe_managed_reference(value: Any) -> str | None:
    """Validate an opaque Runtime managed-object reference."""

    if not isinstance(value, str):
        return None
    reference = value.strip()
    if not reference or any(reference.lower().startswith(prefix) for prefix in _LOCAL_REFERENCE_PREFIXES):
        return None
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in reference):
        return None
    return reference


def _mapping_value(container: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in container:
            return container[name]
    return None


_MANAGED_OUTPUT_FIELDS = (
    "association_id", "project_id", "run_id", "task_id", "attempt_id",
    "output_port", "group_key", "variant_key", "selector", "object_id",
    "digest", "manifest_ref", "size", "filename", "media_type", "ordinal",
    "role", "producer", "provenance", "durability", "state", "version",
    "lifecycle", "generation_id", "regeneration", "coverage", "expires_at",
    "pinned_at", "lease_id", "lease_owner", "lease_expires_at",
    "lifecycle_updated_at",
)


def _record_mapping(value: Any) -> dict[str, Any] | None:
    """Make generated dataclasses and wire mappings equally readable."""

    if isinstance(value, Mapping):
        return dict(value)
    fields = {
        name: getattr(value, name)
        for name in _MANAGED_OUTPUT_FIELDS
        if hasattr(value, name)
    }
    return fields or None


def _managed_output_association(value: Any) -> Mapping[str, Any] | None:
    """Adapt one exact DB ManagedOutput into the existing publication shape."""

    record = _record_mapping(value)
    if record is None:
        return None
    association = dict(record)
    # object_id is the Runtime managed byte reference accepted by get_object;
    # manifest_ref is a distinct path-independent publication identity.
    association.update(
        {
            "output_port": record.get("output_port"),
            "managed_object_reference": record.get("object_id"),
            "actual_filename": record.get("filename"),
            "media_type": record.get("media_type"),
        }
    )
    return association


def _association_needs_managed_lookup(association: Mapping[str, Any]) -> bool:
    """Return whether a task association is absent or incomplete."""

    return any(
        value in (None, "")
        for value in (
            _identifier(association, "output_port", "port", "name"),
            _nested_reference(association),
            _mapping_value(association, "digest", "content_sha256", "sha256"),
            _mapping_value(association, "actual_filename", "filename", "output_filename"),
            _mapping_value(association, "media_type", "mime_type", "content_type"),
            _mapping_value(association, "size", "byte_size", "bytes"),
            _mapping_value(association, "ordinal", "output_ordinal"),
            _identifier(association, "role", "semantic_role"),
        )
    )


def _managed_output_matches(
    record: Mapping[str, Any],
    *,
    project_id: str,
    run_id: str,
    task_id: str,
    output: Mapping[str, Any],
    association: Mapping[str, Any] | None,
) -> bool:
    """Keep managed association selection inside the explicit render scope."""

    if _identifier(record, "project_id") != project_id:
        return False
    if _identifier(record, "run_id", "id") != run_id:
        return False
    if _identifier(record, "task_id") != task_id:
        return False
    if _identifier(record, "output_port", "port", "name") != "video":
        return False
    if association is not None:
        expected_id = _identifier(association, "association_id", "managed_output_id")
        if expected_id and _identifier(record, "association_id") != expected_id:
            return False
    for names in (
        ("digest", "content_sha256", "sha256"),
        ("size", "byte_size", "bytes"),
        ("ordinal", "output_ordinal"),
        ("role", "semantic_role"),
    ):
        expected = _mapping_value(output, *names)
        actual = _mapping_value(record, *names)
        if expected is not None and actual is not None:
            if names[0] == "digest":
                if _normalize_digest(expected) != _normalize_digest(actual):
                    return False
            elif expected != actual:
                return False
    return True


def _managed_output_rows(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        items = value.get("items")
        return list(items) if isinstance(items, list) else []
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and isinstance(value[0], list):
            return value[0]
        return list(value)
    return []


def _lookup_managed_output(
    *,
    client: Any,
    project_id: str,
    run_id: str,
    task_id: str,
    output: Mapping[str, Any],
    association: Mapping[str, Any] | None,
) -> Mapping[str, Any] | None:
    """Read only list/get managed associations when task output is incomplete."""

    list_outputs = getattr(client, "list_managed_outputs", None)
    get_output = getattr(client, "get_managed_output", None)
    if not callable(list_outputs):
        return None
    expected_id = _identifier(association or {}, "association_id", "managed_output_id")
    values: list[Any]
    if expected_id and callable(get_output):
        values = [get_output(expected_id)]
    else:
        values = _managed_output_rows(list_outputs(task_id))
    matches: list[Mapping[str, Any]] = []
    for value in values:
        normalized = _managed_output_association(value)
        if normalized is not None and _managed_output_matches(
            normalized,
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            output=output,
            association=association,
        ):
            matches.append(normalized)
    return matches[0] if len(matches) == 1 else None


def _association_candidates(value: Any) -> list[Mapping[str, Any]]:
    """Find publication-association mappings without inventing a new store."""

    if not isinstance(value, Mapping):
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
        return []
    candidates = [value]
    for key in (
        "publication_association",
        "publication",
        "association",
        "output_association",
        "published_output",
    ):
        nested = value.get(key)
        if isinstance(nested, Mapping):
            candidates.append(nested)
        elif isinstance(nested, list):
            candidates.extend(item for item in nested if isinstance(item, Mapping))
    for key in ("outputs", "output_objects", "published_outputs", "associations"):
        nested = value.get(key)
        if isinstance(nested, list):
            candidates.extend(item for item in nested if isinstance(item, Mapping))
    return candidates


def _find_publication_association(
    *, task: Mapping[str, Any], run: Mapping[str, Any], output: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    result = task.get("result")
    values = [
        output,
        task.get("publication_association"),
        task.get("publication"),
        result,
        run.get("publication_association"),
        run.get("publication"),
        run.get("result"),
    ]
    candidates: list[Mapping[str, Any]] = []
    for value in values:
        candidates.extend(_association_candidates(value))
    video = [
        candidate
        for candidate in candidates
        if _identifier(candidate, "output_port", "port", "name") == "video"
        and any(
            key in candidate
            for key in (
                "managed_object_reference",
                "managed_object_ref",
                "managed_reference",
                "object_reference",
                "object_ref",
                "managed_object",
                "association_id",
                "object_id",
                "actual_filename",
                "filename",
                "media_type",
                "ordinal",
                "role",
            )
        )
    ]
    if not video:
        return None
    # A publication association is a single durable association for the
    # product's video port. Ambiguity must not become a filename/object guess.
    unique: list[Mapping[str, Any]] = []
    fingerprints: set[str] = set()
    for candidate in video:
        fingerprint = repr(sorted((str(key), repr(value)) for key, value in candidate.items()))
        if fingerprint not in fingerprints:
            fingerprints.add(fingerprint)
            unique.append(candidate)
    return unique[0] if len(unique) == 1 else None


def _nested_reference(association: Mapping[str, Any]) -> Any:
    direct = _mapping_value(
        association,
        "managed_object_reference",
        "managed_object_ref",
        "managed_reference",
        "object_reference",
        "object_ref",
        "managed_object_id",
        "object_id",
    )
    if direct is not None:
        if isinstance(direct, Mapping):
            return _mapping_value(direct, "reference", "object_id", "id", "ref")
        return direct
    managed = association.get("managed_object")
    if isinstance(managed, Mapping):
        return _mapping_value(managed, "reference", "object_id", "id", "ref")
    return managed


def _validate_filename(value: Any) -> str | None:
    if not isinstance(value, str) or not value or value != Path(value).name:
        return None
    if value in {".", ".."} or not _SAFE_FILENAME.fullmatch(value):
        return None
    if Path(value).suffix.lower() not in _VIDEO_SUFFIXES:
        return None
    return value


def _publication_metadata(
    *,
    association: Mapping[str, Any],
    output: Mapping[str, Any],
    task: Mapping[str, Any],
    run: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Validate and normalize the agreed association into a read model."""

    port = _identifier(association, "output_port", "port", "name")
    reference = _safe_managed_reference(_nested_reference(association))
    digest = _normalize_digest(
        _mapping_value(association, "digest", "content_sha256", "sha256")
    )
    filename = _validate_filename(
        _mapping_value(association, "actual_filename", "filename", "output_filename")
    )
    media_type = _mapping_value(association, "media_type", "mime_type", "content_type")
    raw_size = _mapping_value(association, "size", "byte_size", "bytes")
    raw_ordinal = _mapping_value(association, "ordinal", "output_ordinal")
    role = _identifier(association, "role", "semantic_role")
    missing = [
        name
        for name, value in (
            ("output_port", port),
            ("managed_object_reference", reference),
            ("digest", digest),
            ("actual_filename", filename),
            ("media_type", media_type),
            ("size", raw_size),
            ("ordinal", raw_ordinal),
            ("role", role),
        )
        if value in (None, "")
    ]
    if missing:
        return {}, "publication association is missing required fields: " + ", ".join(missing)
    if port != "video":
        return {}, "publication association output port must be video"
    if not isinstance(media_type, str) or media_type.lower() not in _VIDEO_MEDIA_TYPES:
        return {}, "publication association has an invalid video media type"
    if isinstance(raw_size, bool) or not isinstance(raw_size, int) or raw_size < 0:
        return {}, "publication association has an invalid byte size"
    if isinstance(raw_ordinal, bool) or not isinstance(raw_ordinal, int) or raw_ordinal < 0:
        return {}, "publication association has an invalid output ordinal"

    # If the association is present, contradictory duplicate fields are a
    # protocol error; silently preferring one would hide a settlement bug.
    duplicate_digest = _mapping_value(output, "digest", "content_sha256", "sha256")
    if duplicate_digest is not None and _normalize_digest(duplicate_digest) != digest:
        return {}, "publication association conflicts with output digest"
    object_digest = _normalize_digest(association.get("object_id"))
    if object_digest is not None and object_digest != digest:
        return {}, "publication association conflicts with managed object digest"
    duplicate_size = _mapping_value(output, "size", "byte_size", "bytes")
    if duplicate_size is not None and duplicate_size != raw_size:
        return {}, "publication association conflicts with output size"

    provenance = association.get("provenance")
    provenance_map = provenance if isinstance(provenance, Mapping) else {}
    task_id = _identifier(association, "task_id") or _identifier(provenance_map, "task_id") or _identifier(task, "task_id", "id")
    producer = association.get("producer")
    producer_map = producer if isinstance(producer, Mapping) else {}
    producer_id = _identifier(association, "producer_id") or _identifier(provenance_map, "producer_id") or _identifier(producer_map, "producer_id", "id", "name")
    if not producer_id and isinstance(producer, str) and producer.strip():
        producer_id = producer.strip()
    attempt_id = _identifier(association, "attempt_id") or _identifier(provenance_map, "attempt_id") or _identifier(task, "attempt_id")
    run_id = _identifier(association, "run_id") or _identifier(provenance_map, "run_id") or _identifier(run, "run_id", "id")
    metadata = {
        "output_port": port,
        "managed_object_reference": reference,
        "digest": "sha256:" + digest,
        "filename": filename,
        "media_type": media_type.lower(),
        "size": raw_size,
        "ordinal": raw_ordinal,
        "role": role,
        "task_id": task_id,
        "run_id": run_id,
    }
    for field in (
        "association_id", "object_id", "manifest_ref", "selector", "group_key",
        "variant_key", "producer", "provenance", "durability", "state", "version",
        "lifecycle", "generation_id", "regeneration", "coverage",
    ):
        if field in association:
            metadata[field] = association[field]
    if producer_id:
        metadata["producer_id"] = producer_id
    if attempt_id:
        metadata["attempt_id"] = attempt_id
    return metadata, None


def _legacy_publication_metadata(
    *,
    client: Any,
    project_id: str,
    output: Mapping[str, Any],
    task: Mapping[str, Any],
    run: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """Adapt only the known historical generic-``video`` output shape.

    This is a bounded compatibility read for old settlements. It requires the
    producing task's own safe filename and a project-scoped managed object
    record; it never consults a global digest name and never accepts a local
    storage path. New publications must carry the full association instead.
    """

    if _identifier(output, "output_port", "port", "name") != "video":
        return {}, None
    digest = _normalize_digest(_mapping_value(output, "digest", "content_sha256", "sha256"))
    filename = _legacy_output_name(task.get("spec"))
    raw_size = _mapping_value(output, "size", "byte_size", "bytes")
    if digest is None or filename is None or isinstance(raw_size, bool) or not isinstance(raw_size, int) or raw_size < 0:
        return {}, None
    objects = paged_rows(client.list_project_objects, project_id, limit=50)
    if objects is None:
        return {}, "Runtime publication association is unavailable for this historical render"
    media = next(
        (
            item for item in objects
            if isinstance(item, Mapping)
            and digest in {
                (_normalize_digest(item.get("digest")) or ""),
                (_normalize_digest(item.get("object_id")) or ""),
            }
        ),
        None,
    )
    if media is None:
        return {}, "historical render output is not owned by the selected project"
    reference = _safe_managed_reference(_identifier(media, "object_id"))
    if reference is None:
        return {}, "historical render has no managed object reference"
    media_type = _mapping_value(media, "media_type", "mime_type") or "video/mp4"
    raw_media_size = _mapping_value(media, "size", "byte_size", "bytes")
    if raw_media_size is not None and raw_media_size != raw_size:
        return {}, "historical render media metadata conflicts with output size"
    size = raw_size
    if not isinstance(media_type, str) or media_type.lower() not in _VIDEO_MEDIA_TYPES:
        return {}, "historical render has an invalid video media type"
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        return {}, "historical render has an invalid byte size"
    task_id = _identifier(task, "task_id", "id")
    return {
        "output_port": "video",
        "managed_object_reference": reference,
        "digest": "sha256:" + digest,
        "filename": filename,
        "media_type": media_type.lower(),
        "size": size,
        "ordinal": 0,
        "role": "result",
        "task_id": task_id,
        "run_id": _identifier(run, "run_id", "id"),
    }, None


def _materialize(
    data: bytes, *, digest: str, size: int, filename: str, cache_root: Path
) -> Path:
    """Publish verified bytes atomically and independently verify reuse."""

    root = cache_root.expanduser().absolute()
    destination = root / digest / filename
    destination.parent.mkdir(parents=True, exist_ok=True)

    def valid(path: Path) -> bool:
        try:
            return (
                path.is_file()
                and not path.is_symlink()
                and path.stat().st_size == size
                and hashlib.sha256(path.read_bytes()).hexdigest() == digest
            )
        except OSError:
            return False

    if valid(destination):
        return destination
    handle, temporary_name = tempfile.mkstemp(prefix=".astrid-render-", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.stat().st_size != size or hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
            raise ValueError("staged render failed digest or size verification")
        os.replace(temporary, destination)
        try:
            directory_fd = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            # The rename is still atomic on filesystems without directory fsync.
            pass
        if not valid(destination):
            raise ValueError("materialized render failed post-publication verification")
        return destination
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _verified_cached_path(
    *, digest: str, size: int, filename: str, cache_root: Path
) -> Path | None:
    """Return a cache hit only after independently checking its bytes."""

    path = cache_root.expanduser().absolute() / digest / filename
    try:
        if (
            not path.is_file()
            or path.is_symlink()
            or path.stat().st_size != size
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            return None
    except OSError:
        return None
    return path


def _request_open(path: Path, opener: Callable[[Path], Any] | None) -> None:
    if opener is not None:
        opener(path)
        return
    subprocess.run(["open", str(path)], check=True)


def _resolve_project(
    client: Any, project_id: str | None
) -> tuple[Mapping[str, Any] | None, DomainResult[Any] | None]:
    try:
        if project_id is None:
            current = client.current_project()
            project = current.get("project") if isinstance(current, Mapping) else None
            if project is None:
                return None, _failure(
                    "not_found",
                    "no current project is selected",
                    next_action="astrid projects select <project>",
                )
        else:
            project = client.get_project(project_id)
    except WorkspaceClientError as exc:
        return None, _failure(exc.code, exc.message, **dict(exc.details))
    if not isinstance(project, Mapping):
        return None, _failure("protocol_error", "runtime project response is malformed")
    resolved_id = _identifier(project, "project_id", "id")
    if not resolved_id:
        return None, _failure("protocol_error", "runtime project response has no project id")
    return project, None


def open_render(
    client: Any,
    project_id: str,
    timeline_id: str | None = None,
    *,
    run_id: str | None = None,
    cache_root: Path | None = None,
    opener: Callable[[Path], Any] | None = None,
    _resolved_project: Mapping[str, Any] | None = None,
) -> DomainResult[Any]:
    """Open an exact/latest render in one explicit project/timeline scope."""

    if platform.system() != "Darwin":
        return _failure("unsupported_platform", "opening renders is currently supported on macOS only")
    if not isinstance(project_id, str) or not project_id.strip():
        return _failure("validation_error", "render opening requires an explicit project_id", field="project_id")
    if timeline_id is not None and (not isinstance(timeline_id, str) or not timeline_id.strip()):
        return _failure("validation_error", "timeline_id must be a non-empty string when provided", field="timeline_id")
    if _resolved_project is None:
        project, project_error = _resolve_project(client, project_id.strip())
        if project_error is not None:
            return project_error
        assert project is not None
    else:
        project = _resolved_project
    resolved_project_id = _identifier(project, "project_id", "id")
    selected_timeline = timeline_id.strip() if isinstance(timeline_id, str) else None
    timeline_refs = {selected_timeline} if selected_timeline else set()
    if selected_timeline:
        if not callable(getattr(client, "list_timelines", None)):
            return _failure("unavailable", "runtime cannot resolve canonical timelines for render opening", project_id=resolved_project_id)
        timeline_rows = paged_rows(client.list_timelines, resolved_project_id, limit=50)
        if timeline_rows is None:
            return _failure("protocol_error", "runtime timeline listing is malformed", project_id=resolved_project_id)
        match = next(
            (
                row for row in timeline_rows
                if isinstance(row, Mapping)
                and selected_timeline in {_identifier(row, "timeline_id", "id"), _identifier(row, "slug")}
            ),
            None,
        )
        if match is None:
            return _failure("not_found", "canonical timeline is not in the selected project", timeline_id=selected_timeline, project_id=resolved_project_id)
        timeline_refs.update({_identifier(match, "timeline_id", "id"), _identifier(match, "slug")})

    try:
        if run_id is not None:
            run = client.get_run(run_id)
            if not isinstance(run, Mapping):
                return _failure("protocol_error", "runtime run response is malformed", run_id=run_id)
            if _identifier(run, "project_id", "project") != resolved_project_id:
                return _failure("not_found", "render run is not owned by the selected project", run_id=run_id, project_id=resolved_project_id)
            candidates = [run]
        else:
            rows = paged_rows(client.list_project_runs, resolved_project_id, limit=50)
            if rows is None:
                return _failure("protocol_error", "runtime project run listing is malformed", project_id=resolved_project_id)
            candidates = [
                row for row in rows
                if isinstance(row, Mapping)
                and _render_capability(row) == "rendering.render"
                and _state(row) in _SUCCESS_STATES
            ]
            candidates.sort(
                key=lambda row: (str(row.get("created_at") or row.get("updated_at") or ""), _identifier(row, "run_id", "id")),
                reverse=True,
            )

        if selected_timeline and run_id is None:
            associated: list[Mapping[str, Any]] = []
            for candidate in candidates:
                hydrated = candidate
                if not isinstance(hydrated.get("task_ids"), list):
                    refreshed = client.get_run(_identifier(hydrated, "run_id", "id"))
                    if isinstance(refreshed, Mapping):
                        hydrated = refreshed
                run_refs = _timeline_provenance(hydrated.get("spec"))
                if run_refs and not run_refs <= timeline_refs:
                    continue
                if run_refs & timeline_refs:
                    associated.append(hydrated)
                    continue
                task_ids = hydrated.get("task_ids")
                if isinstance(task_ids, list):
                    task_refs: set[str] = set()
                    for task_id in task_ids:
                        task = client.get_task(task_id)
                        if isinstance(task, Mapping):
                            task_refs.update(_timeline_provenance(task.get("spec")))
                    if task_refs and task_refs <= timeline_refs and task_refs & timeline_refs:
                        associated.append(hydrated)
            candidates = associated
        if not candidates:
            message = "project has no successful rendering.render run for the selected canonical timeline" if selected_timeline else "project has no successful rendering.render run"
            return _failure("not_found", message, project_id=resolved_project_id, **({"timeline_id": selected_timeline} if selected_timeline else {}))

        run = candidates[0]
        selected_run_id = _identifier(run, "run_id", "id")
        if not selected_run_id:
            return _failure("protocol_error", "runtime render run has no id")
        if _render_capability(run) != "rendering.render" or _state(run) not in _SUCCESS_STATES:
            return _failure("validation_error", "selected run is not a successful rendering.render run", run_id=selected_run_id)
        task_ids = run.get("task_ids")
        if not isinstance(task_ids, list):
            run = client.get_run(selected_run_id)
            task_ids = run.get("task_ids") if isinstance(run, Mapping) else None
        if not isinstance(task_ids, list) or not all(isinstance(item, str) and item for item in task_ids):
            return _failure("protocol_error", "runtime render run has no valid task ids", run_id=selected_run_id)

        render_tasks: list[Mapping[str, Any]] = []
        for task_id in task_ids:
            task = client.get_task(task_id)
            if isinstance(task, Mapping) and _render_capability(task) == "rendering.render" and _state(task) in _SUCCESS_STATES:
                render_tasks.append(task)
        if len(render_tasks) != 1:
            return _failure("validation_error", "render run must contain exactly one successful render task", run_id=selected_run_id, count=len(render_tasks))
        task = render_tasks[0]

        if selected_timeline:
            run_refs = _timeline_provenance(run.get("spec"))
            task_refs = _timeline_provenance(task.get("spec"))
            all_refs = run_refs | task_refs
            if not all_refs or not all_refs <= timeline_refs or not all_refs & timeline_refs:
                return _failure("validation_error", "selected render has missing or conflicting authoritative timeline provenance", run_id=selected_run_id, timeline_id=selected_timeline)

        result = task.get("result")
        outputs = result.get("outputs") if isinstance(result, Mapping) else None
        if not isinstance(outputs, list):
            outputs = result.get("output_objects") if isinstance(result, Mapping) else None
        video_outputs = [
            item for item in (outputs or [])
            if isinstance(item, Mapping)
            and _identifier(item, "output_port", "port", "name") == "video"
        ]
        if len(video_outputs) > 1:
            return _failure("validation_error", "render task must publish exactly one video output association", run_id=selected_run_id, count=len(video_outputs))
        output = video_outputs[0] if video_outputs else {}
        association = _find_publication_association(task=task, run=run, output=output)
        managed_association = None
        if association is None or _association_needs_managed_lookup(association):
            managed_association = _lookup_managed_output(
                client=client,
                project_id=resolved_project_id,
                run_id=selected_run_id,
                task_id=_identifier(task, "task_id", "id"),
                output=output,
                association=association,
            )
        if managed_association is not None:
            metadata, metadata_error = _publication_metadata(
                association=managed_association,
                output=output,
                task=task,
                run=run,
            )
        elif association is None and output:
            metadata, metadata_error = _legacy_publication_metadata(
                client=client,
                project_id=resolved_project_id,
                output=output,
                task=task,
                run=run,
            )
            if not metadata:
                return _failure(
                    "unavailable",
                    "Runtime publication association is unavailable; Astrid cannot safely open this render",
                    dependency="runtime_publication_association",
                    run_id=selected_run_id,
                    **({"detail": metadata_error} if metadata_error else {}),
                )
        elif association is not None:
            metadata, metadata_error = _publication_metadata(association=association, output=output, task=task, run=run)
        else:
            return _failure(
                "unavailable",
                "Runtime publication association is unavailable; Astrid cannot safely open this render",
                dependency="runtime_publication_association",
                run_id=selected_run_id,
            )
        if metadata_error:
            return _failure("protocol_error", metadata_error, run_id=selected_run_id)
        digest = str(metadata["digest"])
        normalized_digest = digest.removeprefix("sha256:")
        reference = str(metadata["managed_object_reference"])
        expected_size = int(metadata["size"])
        selected_cache_root = cache_root or _default_cache_root()
        path = _verified_cached_path(
            digest=normalized_digest,
            size=expected_size,
            filename=str(metadata["filename"]),
            cache_root=selected_cache_root,
        )
        if path is None:
            response = client.get_object(reference)
            data = response if isinstance(response, bytes) else response.get("data") if isinstance(response, Mapping) else None
            if not isinstance(data, bytes):
                return _failure("protocol_error", "managed object download returned no bytes", managed_object_reference=reference)
            actual_digest = hashlib.sha256(data).hexdigest()
            if actual_digest != normalized_digest or len(data) != expected_size:
                return _failure("integrity_error", "downloaded render does not match its runtime digest and size", managed_object_reference=reference)
            path = _materialize(data, digest=normalized_digest, size=expected_size, filename=str(metadata["filename"]), cache_root=selected_cache_root)
        _request_open(path, opener)
        return DomainResult.success(
            {
                "project_id": resolved_project_id,
                "run_id": selected_run_id,
                "task_id": metadata["task_id"],
                "managed_object_reference": reference,
                "digest": digest,
                "size": expected_size,
                "filename": metadata["filename"],
                "media_type": metadata["media_type"],
                "output_port": metadata["output_port"],
                "ordinal": metadata["ordinal"],
                "role": metadata["role"],
                **{
                    field: metadata[field]
                    for field in (
                        "association_id", "object_id", "manifest_ref", "selector",
                        "group_key", "variant_key", "producer", "provenance",
                        "durability", "state", "version", "lifecycle",
                        "generation_id", "regeneration", "coverage",
                    )
                    if field in metadata
                },
                **({"producer_id": metadata["producer_id"]} if "producer_id" in metadata else {}),
                **({"attempt_id": metadata["attempt_id"]} if "attempt_id" in metadata else {}),
                "local_path": str(path),
                "open_requested": True,
                "playback_confirmed": False,
                "opened": False,
                **(
                    {
                        "timeline_id": selected_timeline,
                        "timeline_ref": selected_timeline,
                    }
                    if selected_timeline
                    else {}
                ),
            }
        )
    except WorkspaceClientError as exc:
        return _failure(exc.code, exc.message, **dict(exc.details))
    except ValueError as exc:
        return _failure("integrity_error", str(exc))
    except (OSError, subprocess.SubprocessError) as exc:
        return _failure("open_failed", "could not materialize or request opening the render", detail=str(exc))


def open_project_render(
    client: Any,
    project_ref: str | None = None,
    *,
    run_id: str | None = None,
    timeline_ref: str | None = None,
    default_timeline: bool = False,
    cache_root: Path | None = None,
    opener: Callable[[Path], Any] | None = None,
) -> DomainResult[Any]:
    """Compatibility wrapper resolving the selected project once."""

    if default_timeline and isinstance(timeline_ref, str) and timeline_ref.strip():
        return _failure("validation_error", "timeline_ref and default_timeline are mutually exclusive")
    project, error = _resolve_project(client, project_ref.strip() if isinstance(project_ref, str) and project_ref.strip() else None)
    if error is not None:
        return error
    assert project is not None
    project_id = _identifier(project, "project_id", "id")
    selected_timeline = timeline_ref.strip() if isinstance(timeline_ref, str) and timeline_ref.strip() else None
    if selected_timeline is None and default_timeline:
        metadata = project.get("metadata")
        if isinstance(metadata, Mapping):
            default = metadata.get("default_timeline_id")
            if isinstance(default, str) and default.strip():
                selected_timeline = default.strip()
        if selected_timeline is None:
            return _failure("not_found", "project has no configured default canonical timeline", project_id=project_id)
    return open_render(
        client,
        project_id,
        selected_timeline,
        run_id=run_id,
        cache_root=cache_root,
        opener=opener,
        _resolved_project=project,
    )
