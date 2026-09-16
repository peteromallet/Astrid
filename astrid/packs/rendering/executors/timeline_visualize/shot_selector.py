"""Friendly, deterministic shot selectors for filmstrip inspection.

Canonical shot ids and names are checked first.  Only when there is no exact
match do the human-friendly aliases ``first`` and positive one-based ordinals
resolve against authored shot order.  This keeps an authored id such as ``1``
unambiguous while making ``--shot first`` and ``--shot 1`` useful in scripts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


_ORDINAL = re.compile(r"[1-9][0-9]*\Z")


def _records(snapshot: Mapping[str, Any]) -> list[tuple[str, str | None]]:
    """Return unique ``(shot_id, name)`` records in authored order."""

    result: list[tuple[str, str | None]] = []
    seen: set[str] = set()

    def add(raw: Mapping[str, Any]) -> None:
        shot_id = raw.get("shot_id") or raw.get("shotId") or raw.get("shot")
        name = raw.get("shot_name") or raw.get("shotName") or raw.get("name") or raw.get("label")
        if not isinstance(shot_id, str) or not shot_id or shot_id in seen:
            return
        seen.add(shot_id)
        result.append((shot_id, name if isinstance(name, str) and name else None))

    # Admission-owned occurrences are the strongest ordering signal for a
    # rendered snapshot.  Input-only snapshots carry pinned_shots instead.
    for key in ("occurrences", "pinned_shots", "pinnedShotGroups", "shot_groups"):
        rows = snapshot.get(key)
        if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes, bytearray)):
            for row in rows:
                if isinstance(row, Mapping):
                    add(row)
    for row in snapshot.get("clips") or ():
        if isinstance(row, Mapping):
            add(row)
    return result


def resolve_shot_selector(value: Any, snapshot: Mapping[str, Any]) -> str | None:
    """Resolve a public ``--shot`` value to its canonical shot id.

    Exact id/name matching wins.  ``first`` and positive one-based ordinals
    then resolve in the snapshot's authored order.  ``None`` means no shot
    selector was supplied.  Unknown aliases fail with a useful error rather
    than silently producing an empty filmstrip.
    """

    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("shot must be an identifier, name, 'first', or a positive ordinal")
    records = _records(snapshot)
    for shot_id, name in records:
        if value == shot_id or (name is not None and value == name):
            return shot_id
    lowered = value.strip().lower()
    ordinal = 1 if lowered == "first" else int(value) if _ORDINAL.fullmatch(value.strip()) else None
    if ordinal is not None:
        if ordinal > len(records):
            raise ValueError(
                f"shot ordinal {ordinal} is out of range; timeline has {len(records)} authored shot(s)"
            )
        if not records:
            raise ValueError("shot alias requires authored shot metadata in the frozen snapshot")
        return records[ordinal - 1][0]
    return value


__all__ = ["resolve_shot_selector"]
