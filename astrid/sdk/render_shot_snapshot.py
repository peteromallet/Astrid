"""Pin canonical shot text identities for immutable render provenance."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .exceptions import CapabilityValidationError
from .pagination import page_pair


def shot_text_snapshot(
    client: Any,
    project: str,
    shot_id: str,
    *,
    include_text: bool = False,
) -> list[dict[str, Any]]:
    """Read the complete canonical binding set without creating a text authority.

    The runtime validates each bound text object. Its immutable media identity,
    content hash, binding head, and verified text bytes pin the exact text,
    including after rebinding.
    This endpoint currently returns every matching binding and no cursor; never
    accept a partial page as complete provenance.
    """
    # Review renders need the exact authored speech bytes as well as their
    # immutable identity. The remote facade verifies the CAS digest before
    # returning ``text``; this remains an admission read, never a new text
    # authority. Clean renders retain the identity-only path.
    result = client.shots.list_text_bindings(
        project, shot_id=shot_id, include_text=include_text
    )
    page = page_pair(result.data) if result.ok else None
    if page is None or page[1] is not None:
        raise CapabilityValidationError(f"cannot pin complete text bindings for shot {shot_id!r}")
    records = []
    seen: set[str] = set()
    for row in page[0]:
        if not isinstance(row, Mapping):
            raise CapabilityValidationError(f"invalid text binding for shot {shot_id!r}")
        binding_id = row.get('binding_id')
        head = row.get('head')
        media_id = row.get('media_id')
        content_hash = row.get('content_hash')
        if (not isinstance(binding_id, str) or not binding_id or binding_id in seen
                or row.get('shot_id') != shot_id or type(head) is not int or head < 1
                or not isinstance(media_id, str) or not media_id.startswith('sha256:')
                or content_hash != media_id):
            raise CapabilityValidationError(f"invalid text binding identity for shot {shot_id!r}")
        seen.add(binding_id)
        records.append(deepcopy(dict(row)))
    return sorted(records, key=lambda row: row['binding_id'])
