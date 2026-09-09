"""Pure declaration of the kernel schema-pack vocabulary."""

from __future__ import annotations

from typing import Any

from astrid.core.migrations.catalog import CORE_MIGRATIONS

CORE_PACK_ID = "core"
CORE_MANIFEST_VERSION = 1

CORE_STREAM_TYPES: tuple[str, ...] = (
    "core.project",
    "core.task",
    "core.run",
    "core.media",
)

CORE_REPOSITORIES: tuple[str, ...] = (
    "ProjectRepository",
    "TaskRepository",
    "MediaRepository",
    "RunRepository",
)

CORE_CONFORMANCE_DIMENSIONS: tuple[str, ...] = (
    "replay",
    "mismatch_before_mutation",
    "same_project",
    "vocabulary",
    "writer_ownership",
    "crash_atomicity",
    "hash_chain",
)

CORE_EVENT_KINDS: tuple[str, ...] = (
    "core.project.created",
    "core.project.updated",
    "core.task.created",
    "core.task.claimed",
    "core.task.started",
    "core.task.expired",
    "core.task.cancelled",
    "core.task.failed",
    "core.task.retried",
    "core.task.completed",
    "core.run.created",
    "core.run.cancelled",
    "core.run.retried",
    "core.run.closed",
    "core.run.continued",
    "core.evidence.recorded",
    "core.media.imported",
    "core.media.location_replaced",
    "core.media.related",
    "core.media.verified",
)

CORE_COMMAND_KINDS: tuple[str, ...] = (
    "core.project.create",
    "core.project.update",
    "core.task.create",
    "core.task.claim",
    "core.task.start",
    "core.task.expire",
    "core.task.cancel",
    "core.task.fail",
    "core.task.retry",
    "core.task.complete",
    "core.run.create",
    "core.run.cancel",
    "core.run.retry",
    "core.run.close",
    "core.run.continue",
    "core.evidence.record",
    "core.media.import",
    "core.media.replace_location",
    "core.media.relate",
    "core.media.verify",
)


def core_schema_pack_payload() -> dict[str, Any]:
    """Return the manifest-shaped kernel declaration as plain data."""
    core_migration = CORE_MIGRATIONS[0]
    return {
        "id": CORE_PACK_ID,
        "version": CORE_MANIFEST_VERSION,
        "depends_on": [],
        "migrations": [
            {
                "version": core_migration.version,
                "name": core_migration.name,
                "path": core_migration.path,
                "tables": sorted(core_migration.owned_tables),
            }
        ],
        "stream_types": list(CORE_STREAM_TYPES),
        "event_kinds": list(CORE_EVENT_KINDS),
        "command_kinds": list(CORE_COMMAND_KINDS),
        "repositories": list(CORE_REPOSITORIES),
        "conformance": list(CORE_CONFORMANCE_DIMENSIONS),
        "cli_mounts": {},
        "bridge_mounts": [],
    }


__all__ = [
    "CORE_COMMAND_KINDS",
    "CORE_CONFORMANCE_DIMENSIONS",
    "CORE_EVENT_KINDS",
    "CORE_MANIFEST_VERSION",
    "CORE_PACK_ID",
    "CORE_REPOSITORIES",
    "CORE_STREAM_TYPES",
    "core_schema_pack_payload",
]
