"""Deterministic capability-row selection for remote admission."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any


def _stable_row_key(row: Mapping[str, Any]) -> tuple[str, str]:
    """Return a stable tie-break key for JSON-shaped runtime rows."""

    digest = str(row.get("definition_digest", ""))
    try:
        serialized = json.dumps(
            dict(row), sort_keys=True, separators=(",", ":"), default=str
        )
    except (TypeError, ValueError):
        serialized = repr(sorted((str(key), repr(value)) for key, value in row.items()))
    return digest, serialized


def select_capability_row(
    rows: Iterable[Any], capability_id: str
) -> Mapping[str, Any] | None:
    """Select one capability registration deterministically.

    Ready registrations win over unavailable or legacy rows. Rows without a
    status remain eligible for compatibility with older clients and test
    doubles, but explicit readiness still wins when both forms are present.
    When several rows have the same readiness class, their definition digest
    and complete JSON-shaped row determine the winner rather than listing
    order.
    """

    matching = [
        row
        for row in rows
        if isinstance(row, Mapping) and row.get("capability_id") == capability_id
    ]
    if not matching:
        return None

    def sort_key(row: Mapping[str, Any]) -> tuple[int, str, str]:
        status = row.get("status")
        if status == "ready":
            status_rank = 0
        elif status is None:
            status_rank = 1
        else:
            status_rank = 2
        digest, serialized = _stable_row_key(row)
        return status_rank, digest, serialized

    return min(matching, key=sort_key)


__all__ = ["select_capability_row"]
