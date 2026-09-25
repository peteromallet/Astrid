"""Portable, hash-verified H3 input bundles.

The request owns the list and order of logical assets.  The bundle owns the
bytes and their hashes; preparation and compilation may therefore be moved to
another attempt without reopening the caller's filesystem.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any, Mapping

from astrid.packs.vibecomfy.asset_manifest import (
    AssetManifestError,
    build_asset_manifest,
    read_archive,
)

from .prepare import PreparationError, _asset_ids
from .request import H3Request, normalize_request, read_prepared_request


_HEX_PREFIX = re.compile(r"^[0-9a-f]{16}-(.*)$")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _regular_file(value: Any, *, asset_id: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise PreparationError(f"asset {asset_id!r} needs a file in asset_map before task submission")
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise PreparationError(f"asset {asset_id!r} may not be a symlink")
    try:
        path = raw.resolve(strict=True)
    except OSError as exc:
        raise PreparationError(f"asset {asset_id!r} does not resolve to a file: {raw}") from exc
    if path.is_symlink() or not path.is_file():
        raise PreparationError(f"asset {asset_id!r} does not resolve to a regular file: {path}")
    return path


def _write_archive(destination: Path, manifest: Mapping[str, Any], members: Mapping[str, bytes]) -> None:
    destination = destination.expanduser()
    if destination.exists() and destination.is_symlink():
        raise PreparationError(f"input bundle destination may not be a symlink: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        archive.writestr(
            zipfile.ZipInfo("manifest.json", date_time=(1980, 1, 1, 0, 0, 0)),
            _canonical(manifest),
        )
        for member in sorted(members):
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, members[member])


def build_input_bundle(
    request: H3Request,
    asset_map: Mapping[str, Any],
    destination: str | Path,
) -> Path:
    """Freeze exactly the request-declared assets into a deterministic ZIP."""

    if not isinstance(asset_map, Mapping):
        raise PreparationError("asset_map must be an object of logical asset ids to files")
    bindings: dict[str, Path] = {}
    for asset_id in _asset_ids(request):
        bindings[asset_id] = _regular_file(asset_map.get(asset_id), asset_id=asset_id)

    # Do not include caller paths or filenames in lineage.  Semantic identity
    # is the logical binding plus content digest, so relocation does not alter
    # the bundle merely because the caller directory changed.
    lineage: dict[str, dict[str, str]] = {}
    for binding, path in bindings.items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lineage[binding] = {"kind": "source_bytes", "sha256": "sha256:" + digest}
    try:
        manifest = build_asset_manifest(bindings, lineage=lineage)
    except (AssetManifestError, OSError) as exc:
        raise PreparationError(str(exc)) from exc
    members = {
        str(record["member"]): bindings[str(record["binding"])].read_bytes()
        for record in manifest["assets"]
    }
    raw_destination = Path(destination).expanduser()
    if raw_destination.is_symlink():
        raise PreparationError(f"input bundle destination may not be a symlink: {raw_destination}")
    path = raw_destination.resolve()
    _write_archive(path, manifest, members)
    try:
        read_archive(path)
    except AssetManifestError as exc:
        raise PreparationError(f"created H3 input bundle failed verification: {exc}") from exc
    return path


def bundle_digest(bundle: str | Path) -> str:
    """Return the digest of one regular managed input bundle."""

    path = Path(bundle).expanduser()
    if path.is_symlink() or not path.is_file():
        raise PreparationError(f"input bundle is not a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _logical_filename(member: str, digest: str) -> str:
    name = Path(member).name
    prefix = digest[:16] + "-"
    if name.startswith(prefix):
        name = name[len(prefix):]
    return name or (digest[:16] + ".asset")


def materialize_input_bundle(
    request: H3Request | None,
    bundle: str | Path,
    destination: str | Path,
    *,
    expected_assets: list[str] | tuple[str, ...] | None = None,
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    """Verify and extract request assets into a new attempt-local directory."""

    try:
        resolved = read_archive(bundle)
    except AssetManifestError:
        raise
    expected = list(expected_assets) if expected_assets is not None else _asset_ids(request)
    records = resolved.manifest["assets"]
    if [str(record["binding"]) for record in records] != sorted(expected):
        raise PreparationError("input bundle must contain exactly the request's declared assets")

    root = Path(destination).expanduser()
    if root.exists() and root.is_symlink():
        raise PreparationError("input bundle extraction destination may not be a symlink")
    root = root.resolve()
    paths: dict[str, str] = {}
    identities: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        binding = str(record["binding"])
        # Keep each binding in its own directory.  The file basename remains
        # the source-derived semantic basename, so a later compile emits the
        # same managed member names without exposing the caller path.
        target = root / f"{index:04d}" / _logical_filename(str(record["member"]), str(record["sha256"]))
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.is_symlink() or not target.is_file() or target.read_bytes() != resolved.members[str(record["member"])]:
                raise PreparationError(f"input bundle extraction collides at {target}")
        else:
            target.write_bytes(resolved.members[str(record["member"])])
        if not target.resolve().is_relative_to(root):
            raise PreparationError("input bundle member escapes its attempt directory")
        paths[binding] = str(target)
        identities.append(
            {
                "asset": binding,
                "member": str(record["member"]),
                "sha256": str(record["sha256"]),
                "size": int(record["size"]),
                "kind": "bundle_member",
                "status": "resolved",
            }
        )
    return paths, identities


def resolve_preparation_assets(
    preparation: Mapping[str, Any],
    bundle: str | Path,
    destination: str | Path,
) -> dict[str, Any]:
    """Replace preparation's caller paths with verified bundle-local paths."""

    expected_digest = preparation.get("input_bundle_sha256")
    actual_digest = bundle_digest(bundle)
    if expected_digest != actual_digest:
        raise PreparationError("input bundle digest does not match preparation")
    raw_request = preparation.get("request")
    if not isinstance(raw_request, Mapping):
        raise PreparationError("preparation is missing its normalized request")
    supplied = preparation.get("assets")
    if not isinstance(supplied, list):
        raise PreparationError("preparation asset evidence is missing")
    expected_assets = [
        str(row.get("asset"))
        for row in supplied
        if isinstance(row, Mapping) and isinstance(row.get("asset"), str)
    ]
    if len(expected_assets) != len(supplied) or len(set(expected_assets)) != len(expected_assets):
        raise PreparationError("preparation asset evidence is malformed")
    try:
        request_assets = _asset_ids(
            read_prepared_request(
                raw_request,
                preparation.get("request_digest"),
                require_normalized_v2=True,
            )
        )
    except (TypeError, ValueError) as exc:
        raise PreparationError("preparation request is invalid") from exc
    if expected_assets != request_assets:
        raise PreparationError("preparation asset order does not match its request")
    paths, identities = materialize_input_bundle(
        None,
        bundle,
        destination,
        expected_assets=expected_assets,
    )
    expected_by_asset = {str(row.get("asset")): row for row in supplied if isinstance(row, Mapping)}
    if len(expected_by_asset) != len(supplied):
        raise PreparationError("preparation asset evidence is malformed")
    identity_by_asset = {str(identity["asset"]): identity for identity in identities}
    for prior in supplied:
        asset = str(prior["asset"])
        identity = identity_by_asset.get(asset)
        if (
            identity is None
            or prior.get("status") != "resolved"
            or prior.get("sha256") != identity["sha256"]
            or prior.get("size") != identity["size"]
        ):
            raise PreparationError("input bundle members do not match preparation asset evidence")
        kind = prior.get("kind")
        if kind == "file":
            if "member" in prior:
                raise PreparationError("file preparation assets may not assert a bundle member")
        elif kind == "bundle_member":
            if prior.get("member") != identity["member"]:
                raise PreparationError("input bundle member identity does not match preparation")
        else:
            raise PreparationError("preparation asset kind is unsupported")
    if set(expected_by_asset) != {str(identity["asset"]) for identity in identities}:
        raise PreparationError("input bundle members do not match preparation asset evidence")
    return {
        **dict(preparation),
        "assets": [
            {**dict(record), "path": paths[str(record["asset"])]}
            for record in supplied
        ],
    }


__all__ = [
    "build_input_bundle",
    "bundle_digest",
    "materialize_input_bundle",
    "resolve_preparation_assets",
]
