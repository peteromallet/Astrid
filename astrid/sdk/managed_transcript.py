"""Validation helpers for a Runtime-owned, hash-bound transcript input."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _digest(value: Any, *, label: str) -> str:
    raw = str(value or "").removeprefix("sha256:")
    if not _SHA256.fullmatch(raw):
        raise ValueError(f"transcript {label} must be a sha256 digest")
    return raw


def transcript_input_from_snapshot(
    config: Mapping[str, Any],
    registry: Mapping[str, Any] | None = None,
) -> dict[str, str] | None:
    """Return the host-managed transcript input for ``config.app.transcript``.

    The returned digest is derived only from the canonical Runtime snapshot.
    The host later fetches those bytes from Runtime CAS and the visualizer
    verifies them against the declaration; there is intentionally no local
    filename or sidecar discovery here.
    """

    app = config.get("app")
    if not isinstance(app, Mapping) or "transcript" not in app:
        return None
    declaration = app.get("transcript")
    if not isinstance(declaration, Mapping):
        raise ValueError("config.app.transcript must be an object")
    for key in ("source_id", "source_version", "producer", "file"):
        if not isinstance(declaration.get(key), str) or not declaration[key].strip():
            raise ValueError(f"config.app.transcript.{key} is required")
    media = declaration.get("media")
    if not isinstance(media, Mapping):
        raise ValueError("config.app.transcript.media is required")
    identities = [key for key in ("asset_key", "source_id") if isinstance(media.get(key), str) and media[key].strip()]
    if len(identities) != 1:
        raise ValueError("config.app.transcript.media requires exactly one identity")
    digest = _digest(declaration.get("sha256"), label="sha256")
    media_digest = media.get("sha256")
    if media_digest is not None:
        media_digest = _digest(media_digest, label="media.sha256")
        if identities == ["asset_key"] and isinstance(registry, Mapping):
            assets = registry.get("assets")
            asset = assets.get(media["asset_key"]) if isinstance(assets, Mapping) else None
            if not isinstance(asset, Mapping):
                raise ValueError(
                    f"config.app.transcript.media.asset_key {media['asset_key']!r} is not in the canonical registry"
                )
            admitted = next(
                (asset.get(key) for key in ("content_sha256", "digest", "sha256", "hash") if asset.get(key)),
                None,
            )
            if admitted is not None and _digest(admitted, label="registry media") != media_digest:
                raise ValueError("config.app.transcript.media.sha256 does not match the canonical media hash")
    return {
        "digest": "sha256:" + digest,
        "object_id": "sha256:" + digest,
    }


__all__ = ["transcript_input_from_snapshot"]
