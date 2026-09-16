#!/usr/bin/env python3
"""Package the read-only rendered timeline filmstrip as an executor."""

# The canonical-entrypoint guard intentionally runs before imports.
# ruff: noqa: E402

from __future__ import annotations

from astrid.core.pack.entrypoint import guard_canonical_entrypoint

guard_canonical_entrypoint("rendering.timeline_visualize")

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable, Mapping

from astrid.sdk.workspace_client import page_pair
from astrid.sdk.pagination import paged_rows
from astrid.core.cli_choices import StaticChoices
from astrid.core.timeline.events.schema import TimelineActor, TimelineEvent, with_event_hash
from astrid.packs.rendering.executors.timeline_visualize.select import (
    KernelTimeline,
    ManagedTimeline,
)

_AUTHORITY_CONTEXT_ENV = "ASTRID_TIMELINE_VISUALIZE_AUTHORITY_CONTEXT"
_RUNTIME_MEDIA_PAGE_LIMIT = 50
_RUNTIME_MEDIA_MAX_PAGES = 10_000


def _runtime_media_row_value(row: Any, *keys: str) -> Any:
    """Read a generated-client row without requiring a mapping conversion."""

    if isinstance(row, Mapping):
        for key in keys:
            if key in row:
                return row[key]
        return None
    for key in keys:
        try:
            return getattr(row, key)
        except AttributeError:
            continue
    return None


def _runtime_media_page(result: Any) -> tuple[list[Any], str | None] | None:
    """Validate the generated client's canonical JSON page pair."""

    page = page_pair(result)
    if page is None:
        return None
    items, next_cursor = page
    if not isinstance(items, list):
        return None
    # The runtime call is explicitly bounded.  A response larger than the
    # requested page is malformed: accepting it would make the snapshot
    # boundary depend on an untrusted adapter rather than the pagination
    # contract we requested.
    if len(items) > _RUNTIME_MEDIA_PAGE_LIMIT:
        return None
    if next_cursor is not None:
        # ``None`` is the only terminal marker.  Empty/whitespace/control
        # strings are malformed cursors, not alternate spellings of it.
        if (
            not isinstance(next_cursor, str)
            or not next_cursor
            or any(
                character.isspace() or ord(character) < 0x20 or ord(character) == 0x7F
                for character in next_cursor
            )
        ):
            return None
    return list(items), next_cursor


def _runtime_media_snapshot_rows(
    rows: Iterable[Any], *, project_id: str, project_slug: str
) -> list[Any] | None:
    """Validate ownership and make a cursor-assembled snapshot deterministic."""

    unique: list[Any] = []
    seen_object_ids: set[str] = set()
    seen_digests: set[str] = set()
    seen_rows: set[str] = set()
    for row in rows:
        # The current ManagedObject schema is project-scoped and omits an owner
        # field.  If a newer/ test-double row includes one, fail closed rather
        # than allowing a cross-project admission into a child-process snapshot.
        row_project_id = _runtime_media_row_value(
            row, "project_id", "owner_project_id", "owning_project_id"
        )
        if row_project_id is not None and str(row_project_id) != project_id:
            return None
        row_project = _runtime_media_row_value(row, "project")
        if row_project is not None:
            if isinstance(row_project, Mapping):
                candidate = row_project.get("project_id") or row_project.get("id")
                candidate_slug = row_project.get("slug")
                if candidate is not None and str(candidate) != project_id:
                    return None
                if candidate_slug is not None and str(candidate_slug) != project_slug:
                    return None
            elif str(row_project) not in {project_id, project_slug}:
                return None

        object_id = _runtime_media_row_value(row, "object_id", "media_id", "id")
        digest = _runtime_media_row_value(row, "content_hash", "content_sha256", "sha256", "digest")
        object_key = str(object_id) if isinstance(object_id, str) and object_id else None
        digest_key = str(digest) if isinstance(digest, str) and digest else None
        if object_key is not None and object_key in seen_object_ids:
            continue
        if digest_key is not None and digest_key in seen_digests:
            continue
        if object_key is None and digest_key is None:
            # Malformed rows are retained for the resolver's existing
            # fail-closed normalization, but exact duplicates are suppressed.
            try:
                row_key = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
            except (TypeError, ValueError):
                row_key = repr(row)
            if row_key in seen_rows:
                continue
            seen_rows.add(row_key)
        if object_key is not None:
            seen_object_ids.add(object_key)
        if digest_key is not None:
            seen_digests.add(digest_key)
        unique.append(row)

    def sort_key(row: Any) -> tuple[str, str, str]:
        object_id = _runtime_media_row_value(row, "object_id", "media_id", "id")
        digest = _runtime_media_row_value(row, "content_hash", "content_sha256", "sha256", "digest")
        try:
            stable = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
        except (TypeError, ValueError):
            stable = repr(row)
        return (
            str(object_id) if object_id is not None else "",
            str(digest) if digest is not None else "",
            stable,
        )

    return sorted(unique, key=sort_key)


def _runtime_media_snapshot(project_slug: str) -> list[Any] | None:
    """Read the project's admitted media facts from the workspace runtime.

    Visualization runs in a child process and must not open the local kernel
    database.  The returned rows are an attempt-local read snapshot: callers
    pass them to the resolver, which still verifies project ownership, CAS
    location, and bytes.  Runtime unavailability is deliberately represented
    as ``None`` so ordinary project-source visualization remains usable while
    managed CAS media fails closed.
    """

    try:
        from astrid.sdk.workspace_client import WorkspaceClient, resolve_runtime_connection

        endpoint, token = resolve_runtime_connection()
        client = WorkspaceClient(endpoint, token)
        rows = paged_rows(client.list_projects)
        if rows is None:
            return None
        project = next(
            (
                row
                for row in rows or []
                if isinstance(row, Mapping) and row.get("slug") == project_slug
            ),
            None,
        )
        if not isinstance(project, Mapping):
            return None
        project_id = project.get("project_id") or project.get("id")
        if not isinstance(project_id, str) or not project_id:
            return None
        rows = paged_rows(
            client.list_project_objects,
            project_id,
            limit=_RUNTIME_MEDIA_PAGE_LIMIT,
            max_pages=_RUNTIME_MEDIA_MAX_PAGES,
        )
        if rows is None:
            return None
        return _runtime_media_snapshot_rows(rows, project_id=project_id, project_slug=project_slug)
    except Exception:  # noqa: BLE001 - managed media reads fail closed
        return None


def _execution_authority_context() -> dict[str, Any] | None:
    raw = os.environ.get(_AUTHORITY_CONTEXT_ENV)
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("timeline visualization execution authority is invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("timeline visualization execution authority must be an object")
    return value


_FORMATS = frozenset({"png", "svg", "md"})
_CROCKFORD32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _stable_kernel_event_ulid(seed: str) -> str:
    """Return a deterministic schema-valid id for a private kernel projection."""

    value = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:16], "big")
    chars = ["0"] * 26
    for index in range(25, -1, -1):
        chars[index] = _CROCKFORD32[value & 31]
        value >>= 5
    return "".join(chars)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rendering.timeline_visualize",
        description="Build a deterministic agent evidence pack from managed timeline event logs.",
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--project-slug",
        required=True,
        help="Owning project slug issued by the workspace runtime.",
    )
    parser.add_argument(
        "--view",
        choices=StaticChoices(("filmstrip",)),
        default="filmstrip",
        help="Rendered paired filmstrip (the only supported timeline view).",
    )
    parser.add_argument(
        "--sample", choices=StaticChoices(("interval", "clips", "shots", "cuts"))
    )
    parser.add_argument("--every", type=float)
    parser.add_argument("--every-frames", type=int)
    parser.add_argument(
        "--include-cuts",
        action="store_true",
        help="with interval sampling, also capture explicit visual cut-neighbor frames",
    )
    parser.add_argument("--render-run")
    parser.add_argument(
        "--columns",
        type=int,
        help="combined filmstrip output cards per paired row (default 5; max 8)",
    )
    parser.add_argument("--page-size", type=int)
    parser.add_argument("--resolution", metavar="WIDTHxHEIGHT")
    parser.add_argument("--filmstrip-authority", help=argparse.SUPPRESS)
    parser.add_argument("--timeline-slug")
    parser.add_argument(
        "--shot",
        help="authored shot id/name, or 'first' / a positive authored-order ordinal",
    )
    parser.add_argument("--range", dest="range_value")
    parser.add_argument("--at")
    parser.add_argument("--clip")
    parser.add_argument("--asset")
    parser.add_argument("--context", type=float, default=3.0)
    parser.add_argument("--neighbors", type=int, default=0)
    parser.add_argument("--show", action="append", default=None)
    parser.add_argument("--hide", action="append", default=None)
    parser.add_argument("--track", action="append", default=None)
    parser.add_argument(
        "--detail",
        action="store_true",
        default=False,
        help="use enlarged frame, waveform, and text panels for focused review",
    )
    parser.add_argument(
        "--format",
        action="append",
        type=_format_argument,
        metavar="FORMAT[,FORMAT...]",
        help="Repeatable presentation format(s): png, svg, md, or all (default all).",
    )
    # The admitted rendered video is host-injected; callers select it with
    # --render-run rather than supplying a filesystem path.
    parser.add_argument("--rendered-video", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--include-media",
        action="store_true",
        help="include a relative, digest-verified rendered video for offline filmstrip playback",
    )
    parser.add_argument("--materialized-root", type=Path)
    parser.add_argument("--materialized-objects")
    parser.add_argument("--transcript-file", type=Path)
    return parser


def _parse_time(value: str) -> float:
    raw = value.strip()
    try:
        seconds = float(raw)
    except ValueError:
        parts = raw.split(":")
        if len(parts) not in (2, 3):
            raise ValueError(f"invalid time {value!r}; use seconds or [HH:]MM:SS[.fff]") from None
        try:
            numbers = [float(part) for part in parts]
        except ValueError:
            raise ValueError(f"invalid time {value!r}; use seconds or [HH:]MM:SS[.fff]") from None
        if len(numbers) == 2:
            minutes, tail = numbers
            hours = 0.0
        else:
            hours, minutes, tail = numbers
        if hours < 0 or minutes < 0 or minutes >= 60 or tail < 0 or tail >= 60:
            raise ValueError(f"invalid time {value!r}; minute/second fields must be within 0..59")
        seconds = hours * 3600.0 + minutes * 60.0 + tail
    if seconds < 0:
        raise ValueError("time values must be non-negative")
    return seconds


def _parse_range(value: str) -> tuple[float, float]:
    start_raw, separator, end_raw = value.partition("..")
    if not separator or not start_raw or not end_raw:
        raise ValueError("range must be START..END")
    return _parse_time(start_raw), _parse_time(end_raw)


def _format_argument(value: str) -> str:
    """Validate one CLI format token while accepting comma-separated lists.

    Discovery exposes the SDK field as plural ``formats`` while the runtime
    command uses repeatable singular ``--format``.  Accepting both
    ``--format png --format svg`` and the common ``--format png,svg`` spelling
    keeps the two public forms semantically identical.
    """

    values = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not values:
        raise argparse.ArgumentTypeError("format must name one or more of png, svg, md, or all")
    invalid = sorted(set(values) - (_FORMATS | {"all"}))
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid format(s): {', '.join(invalid)}; choose png, svg, md, or all"
        )
    if "all" in values and len(values) > 1:
        raise argparse.ArgumentTypeError(
            "format 'all' cannot be combined with another format; omit the others"
        )
    return ",".join(values)


def _materialize_kernel_timeline(
    row: KernelTimeline,
    *,
    project_root: Path,
    project_slug: str,
    destination: Path,
) -> ManagedTimeline:
    """Normalize one runtime row into an attempt-local visualization input."""

    del project_root, project_slug, destination
    timeline_ulid = row.timeline_ulid.upper()
    # Compact UUID DTOs retain their historical normalization; opaque Runtime
    # IDs are preserved exactly through the materialization boundary.
    try:
        timeline_id = str(uuid.UUID(str(row.timeline_id)))
    except ValueError:
        timeline_id = row.timeline_id
    config = dict(row.config)
    if not isinstance(config.get("clips"), list) or not isinstance(config.get("tracks"), list):
        raise ValueError(
            f"kernel timeline {row.slug!r} at version {row.config_version} cannot be "
            "visualized: canonical config must contain top-level tracks and clips arrays; "
            "save a renderable timeline config and retry"
        )
    registry = row.registry.get("assets", {}) if isinstance(row.registry, Mapping) else {}
    if not isinstance(registry, dict):
        registry = {}
    actor = TimelineActor(type="system", id="astrid.kernel", display="Astrid kernel")
    timestamp = row.head_created_at
    events: list[TimelineEvent] = []
    for kind, payload in (
        ("timeline.config_replaced", {"config": config, "source": "other"}),
        ("timeline.asset_registry_replaced", {"registry": {"assets": registry}, "source": "other"}),
    ):
        event = TimelineEvent(
            event_id=_stable_kernel_event_ulid(f"{row.head_event_id}:{kind}"),
            timeline_id=timeline_id,
            ts=timestamp,
            actor=actor,
            prev_hash=None,
            hash=None,
            kind=kind,
            payload=payload,
            expected_version=len(events),
            source_backend="astrid.kernel",
            source_timeline_id=timeline_id,
            source_event_id=row.head_event_id,
            source_version=row.config_version,
            source_hash=row.head_hash,
        )
        event = with_event_hash(event, prev_hash=events[-1].hash if events else None)
        events.append(event)
    return ManagedTimeline(
        timeline_dir=None,
        timeline_id=timeline_id,
        timeline_ulid=timeline_ulid,
        slug=row.slug,
        is_default=row.is_default,
        is_tombstoned=False,
        kernel_head_version=row.config_version,
        kernel_head_event_id=_stable_kernel_event_ulid(f"kernel:{row.head_event_id}"),
        kernel_head_hash=row.head_hash,
        kernel_source_event_id=row.head_event_id,
        runtime_config=config,
        runtime_registry={"assets": registry},
        runtime_events=tuple(event.to_json_obj() for event in events),
    )


def execute(argv: list[str] | None = None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    if args.materialized_objects:
        try:
            args.materialized_objects = json.loads(args.materialized_objects)
        except json.JSONDecodeError:
            raise ValueError("--materialized-objects must be a JSON object") from None
        if not isinstance(args.materialized_objects, Mapping):
            raise ValueError("--materialized-objects must be a JSON object")
    else:
        args.materialized_objects = None
    # Filmstrip admission is the sole execution path.  Structural rendering
    # and object-manifest navigation were removed from this executor.
    from .filmstrip_execution import execute_filmstrip

    return execute_filmstrip(args, authority=_execution_authority_context())


def run_sdk(argv: list[str] | None = None) -> dict[str, Any]:
    """Return a JSON-safe executor payload without writing to stdout."""
    try:
        return execute(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        return {
            "returncode": int(code),
            "error": {"type": "SystemExit", "message": str(exc.code or "")},
        }
    except Exception as exc:  # noqa: BLE001 - executor boundary returns process-like diagnostics
        return {
            "returncode": 1,
            "error": {"type": type(exc).__name__, "message": str(exc)},
        }


def main(argv: list[str] | None = None) -> int:
    result = run_sdk(argv)
    returncode = int(result.get("returncode", 1))
    if returncode:
        error = result.get("error")
        if isinstance(error, Mapping):
            message = error.get("message") or error.get("type") or "timeline visualization failed"
        else:
            message = "timeline visualization failed"
        print(message, file=sys.stderr)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
