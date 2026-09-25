"""Portable H3 dependencies using the existing verified asset archive contract.

Only asset IDs declared by the request are resolved. JSON strings are never
scanned for paths. Each executor derives private paths from the same immutable
bundle; preparation records carry member identities, not previous-attempt paths.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping

from astrid.packs.vibecomfy.asset_manifest import read_archive

from .compile import _write_asset_bundle
from .prepare import PreparationError, _asset_ids
from .request import H3Request, normalize_request


def build_input_bundle(request: H3Request, asset_map: Mapping[str, Any], destination: Path) -> Path:
    bindings: dict[str, Path] = {}
    for asset_id in _asset_ids(request):
        value = asset_map.get(asset_id)
        if not isinstance(value, str) or not value:
            raise PreparationError(f"asset {asset_id!r} needs a file in asset_map before task submission")
        bindings[asset_id] = Path(value).expanduser().resolve(strict=True)
    _write_asset_bundle(destination, bindings)
    # Re-read the completed bytes before importing: also catches a file changed
    # between manifest construction and archive writing.
    read_archive(destination)
    return destination


def materialize_input_bundle(
    request: H3Request, bundle: Path, destination: Path,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    resolved = read_archive(bundle)
    records = resolved.manifest["assets"]
    if {row["binding"] for row in records} != set(_asset_ids(request)):
        raise PreparationError("input bundle must contain exactly the request's declared assets")
    destination = destination.resolve()
    paths: dict[str, str] = {}
    identities: list[dict[str, Any]] = []
    for row in records:
        target = (destination / row["member"]).resolve()
        if not target.is_relative_to(destination):
            raise PreparationError("input bundle member escapes its attempt directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(resolved.members[row["member"]])
        paths[row["binding"]] = str(target)
        identities.append({
            "asset": row["binding"], "member": row["member"],
            "sha256": row["sha256"], "size": row["size"],
            "kind": "bundle_member", "status": "resolved",
        })
    return paths, identities


def bundle_digest(bundle: Path) -> str:
    return hashlib.sha256(bundle.read_bytes()).hexdigest()


def resolve_preparation_assets(
    preparation: Mapping[str, Any], bundle: Path, destination: Path,
) -> dict[str, Any]:
    if preparation.get("input_bundle_sha256") != bundle_digest(bundle):
        raise PreparationError("input bundle digest does not match preparation")
    request = normalize_request(preparation["request"])
    paths, identities = materialize_input_bundle(request, bundle, destination)
    if preparation.get("assets") != identities:
        raise PreparationError("input bundle members do not match preparation asset evidence")
    return {**preparation, "assets": [
        {**record, "path": paths[record["asset"]]} for record in identities
    ]}
