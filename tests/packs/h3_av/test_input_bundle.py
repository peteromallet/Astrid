from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.compile import compile_preparation
from astrid.packs.h3_av.src.input_bundle import (
    build_input_bundle,
    bundle_digest,
    materialize_input_bundle,
    resolve_preparation_assets,
)
from astrid.packs.h3_av.src.prepare import PreparationError, prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.vibecomfy.asset_manifest import AssetManifestError, read_archive


def _request():
    return normalize_request(
        {
            "version": 1,
            "operation": "edit",
            "source": {"asset": "source", "range": [0, 2]},
            "output": {"duration": 2},
            "content": {"prompt": "portable H3 input"},
            "changes": {
                "video": [{"during": [1, 2], "area": {"full_frame": True}, "action": "generate"}],
                "audio": [{"during": [1, 2], "action": "generate"}],
            },
            "references": [],
            "overrides": {},
        }
    )


def test_bundle_is_deterministic_and_contains_only_declared_assets(tmp_path: Path) -> None:
    request = _request()
    source = tmp_path / "source.mp4"
    unused = tmp_path / "unused.bin"
    source.write_bytes(b"source")
    unused.write_bytes(b"unused")
    first = build_input_bundle(request, {"source": source, "unused": unused}, tmp_path / "first.zip")
    second = build_input_bundle(request, {"source": source, "unused": unused}, tmp_path / "second.zip")
    assert first.read_bytes() == second.read_bytes()
    assert bundle_digest(first) == bundle_digest(second)
    assert [row["binding"] for row in read_archive(first).manifest["assets"]] == ["source"]


def test_bundle_relocation_does_not_reopen_caller_path(tmp_path: Path) -> None:
    request = _request()
    caller = tmp_path / "caller"
    caller.mkdir()
    source = caller / "source.mp4"
    source.write_bytes(b"source")
    bundle = build_input_bundle(request, {"source": source}, tmp_path / "bundle.zip")
    paths, identities = materialize_input_bundle(request, bundle, tmp_path / "prepare-assets")
    preparation = prepare_request(request, asset_map=paths)
    preparation["assets"] = identities
    preparation["input_bundle_sha256"] = bundle_digest(bundle)
    direct = compile_preparation(
        prepare_request(request, asset_map={"source": str(source)}),
        out_dir=tmp_path / "direct",
    )
    shutil.rmtree(caller)
    relocated = compile_preparation(preparation, out_dir=tmp_path / "relocated", input_bundle=bundle)
    assert direct["managed_assets"]["sha256"] == relocated["managed_assets"]["sha256"]


def test_public_prepare_and_compile_use_staged_bundle_after_caller_asset_changes(tmp_path: Path) -> None:
    from astrid.packs.h3_av.executors.compile.run import main as compile_main
    from astrid.packs.h3_av.executors.prepare.run import main as prepare_main

    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request.value), encoding="utf-8")
    caller = tmp_path / "caller"
    caller.mkdir()
    source = caller / "source.mp4"
    source.write_bytes(b"managed original source")
    bundle = build_input_bundle(request, {"source": source}, tmp_path / "managed.zip")

    preparation_path = tmp_path / "prepare" / "preparation.json"
    assert prepare_main([
        "--request", str(request_path), "--input-bundle", str(bundle),
        "--out", str(preparation_path),
    ]) == 0
    source.write_bytes(b"caller asset changed after staging")

    compile_dir = tmp_path / "compile"
    assert compile_main([
        "--preparation", str(preparation_path), "--input-bundle", str(bundle),
        "--out", str(compile_dir),
    ]) == 0
    compiled = json.loads((compile_dir / "compilation.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(compile_dir / "managed-assets.zip") as archive:
        source_members = [
            name for name in archive.namelist()
            if name.endswith("source.mp4")
        ]
        assert len(source_members) == 1
        assert archive.read(source_members[0]) == b"managed original source"
    assert compiled["workflow_inputs"]["source_video"] == Path(source_members[0]).name


def _normalized_v2_request():
    return normalize_request(
        {
            "version": 2,
            "prompt": "serialized v2 bundle handoff",
            "duration": 1,
            "media": [
                {
                    "id": "source",
                    "asset": "source",
                    "role": "timeline",
                    "modality": "video",
                    "at": {"frame": 0},
                    "range": [0, 1],
                    "edit": [{"stream": "video", "during": [0, 1], "mask": {"asset": "mask-raster.json", "shape": {"frames": 1, "height": 2, "width": 2}}}],
                },
                {"id": "look-z", "asset": "z-look", "role": "reference", "modality": "image"},
                {"id": "look-a", "asset": "a-look", "role": "reference", "modality": "image"},
                {"id": "look-z-again", "asset": "z-look", "role": "reference", "modality": "image"},
            ],
            "settings": {"seed": 42},
        }
    )


def test_v2_preparation_serialization_resolves_ordered_bundle_members(tmp_path: Path) -> None:
    request = _normalized_v2_request()
    caller = tmp_path / "caller"
    caller.mkdir()
    asset_map = {}
    for asset in ("source", "z-look", "a-look", "mask-raster.json"):
        path = caller / (f"{asset}.json" if asset == "mask-raster.json" else f"{asset}.bin")
        path.write_text("[[[1,0],[0,1]]]" if asset == "mask-raster.json" else asset, encoding="utf-8")
        asset_map[asset] = path
    bundle = build_input_bundle(request, asset_map, tmp_path / "input.zip")
    preparation = prepare_request(request, asset_map=asset_map, width=2, height=2, target_model_dimensions={"frames": 1, "height": 1, "width": 1})
    preparation["input_bundle_sha256"] = bundle_digest(bundle)
    serialized = json.loads(json.dumps(preparation))
    shutil.rmtree(caller)

    resolved = resolve_preparation_assets(serialized, bundle, tmp_path / "resolved")

    assert [row["asset"] for row in resolved["assets"]] == ["source", "z-look", "a-look", "mask-raster.json"]
    assert [row["kind"] for row in resolved["assets"]] == ["file"] * 4
    assert [Path(row["path"]).read_bytes() for row in resolved["assets"]] == [
        b"source", b"z-look", b"a-look", b"[[[1,0],[0,1]]]"
    ]
    assert resolved["request"] == serialized["request"]

    bundle_paths, bundle_identities = materialize_input_bundle(
        None, bundle, tmp_path / "bundle-members", expected_assets=["source", "z-look", "a-look", "mask-raster.json"]
    )
    identity_by_asset = {row["asset"]: row for row in bundle_identities}
    member_preparation = {
        **serialized,
        "assets": [
            {**row, **identity_by_asset[row["asset"]], "path": bundle_paths[row["asset"]]}
            for row in serialized["assets"]
        ],
    }
    members_resolved = resolve_preparation_assets(member_preparation, bundle, tmp_path / "bundle-members-again")
    assert [row["kind"] for row in members_resolved["assets"]] == ["bundle_member"] * 4
    assert [row["member"] for row in members_resolved["assets"]] == [
        identity_by_asset[asset]["member"] for asset in ("source", "z-look", "a-look", "mask-raster.json")
    ]


@pytest.mark.parametrize("mutation", ["missing-derived", "contradictory-derived", "contradictory-edit-coordinate"])
def test_v2_bundle_resolver_rejects_incomplete_or_contradictory_derived_fields(
    tmp_path: Path, mutation: str
) -> None:
    request = _normalized_v2_request()
    asset_map = {}
    for asset in ("source", "z-look", "a-look", "mask-raster.json"):
        path = tmp_path / (f"{asset}" if asset == "mask-raster.json" else f"{asset}.bin")
        path.write_text("[[[1,0],[0,1]]]" if asset == "mask-raster.json" else asset, encoding="utf-8")
        asset_map[asset] = path
    bundle = build_input_bundle(request, asset_map, tmp_path / "input.zip")
    preparation = prepare_request(request, asset_map=asset_map, width=2, height=2, target_model_dimensions={"frames": 1, "height": 1, "width": 1})
    preparation["input_bundle_sha256"] = bundle_digest(bundle)
    if mutation == "missing-derived":
        preparation["request"].pop("profile")
    elif mutation == "contradictory-derived":
        preparation["request"]["media"][1]["occurrence_id"] = "wrong-occurrence"
    else:
        preparation["request"]["media"][0]["edit"][0]["resolved"]["range"] = [0, 23]

    with pytest.raises(PreparationError, match="preparation request is invalid"):
        resolve_preparation_assets(preparation, bundle, tmp_path / "resolved")


def _references_request():
    return normalize_request(
        {
            "version": 1,
            "operation": "edit",
            "source": {"asset": "source", "range": [0, 2]},
            "output": {"duration": 2},
            "content": {"prompt": "preserve reference identity"},
            "changes": {"video": [], "audio": []},
            "references": [
                {"asset": "z-look", "purpose": "appearance"},
                {"asset": "a-look", "purpose": "style"},
                {"asset": "m-look", "purpose": "pose"},
                {"asset": "b-look", "purpose": "motion"},
            ],
            "overrides": {},
        }
    )


def test_resolver_preserves_serialized_preparation_identities_and_order(tmp_path: Path) -> None:
    request = _references_request()
    caller = tmp_path / "caller"
    caller.mkdir()
    asset_map = {}
    for asset in ("source", "z-look", "a-look", "m-look", "b-look"):
        path = caller / f"{asset}.bin"
        path.write_bytes(b"same bytes" if asset != "source" else b"source bytes")
        asset_map[asset] = path
    bundle = build_input_bundle(request, asset_map, tmp_path / "input.zip")
    preparation = prepare_request(request, asset_map={key: str(value) for key, value in asset_map.items()})
    preparation["input_bundle_sha256"] = bundle_digest(bundle)
    preparation["provenance"] = {"assets": preparation["assets"]}
    serialized = json.loads(json.dumps(preparation))
    original_assets = json.loads(json.dumps(serialized["assets"]))
    shutil.rmtree(caller)

    first = resolve_preparation_assets(serialized, bundle, tmp_path / "resolve-one")
    second = resolve_preparation_assets(serialized, bundle, tmp_path / "resolve-two")

    assert [row["asset"] for row in first["assets"]] == [
        "source", "z-look", "a-look", "m-look", "b-look"
    ]
    for before, after, relocated in zip(original_assets, first["assets"], second["assets"]):
        assert {key: value for key, value in after.items() if key != "path"} == {
            key: value for key, value in before.items() if key != "path"
        }
        assert Path(after["path"]).read_bytes() == (b"source bytes" if before["asset"] == "source" else b"same bytes")
        assert after["path"] != relocated["path"]
    assert serialized["assets"] == original_assets
    assert first["provenance"] == serialized["provenance"]

    paths, bundle_identities = materialize_input_bundle(
        request, bundle, tmp_path / "bundle-member", expected_assets=[row["asset"] for row in original_assets]
    )
    identity_by_asset = {row["asset"]: row for row in bundle_identities}
    already_bundled = {
        **serialized,
        "assets": [
            {**row, **identity_by_asset[row["asset"]], "path": paths[row["asset"]]}
            for row in original_assets
        ],
    }
    already_bundled["provenance"] = {"assets": already_bundled["assets"]}
    relocated_bundle_members = resolve_preparation_assets(already_bundled, bundle, tmp_path / "bundle-member-again")
    assert [row["kind"] for row in relocated_bundle_members["assets"]] == ["bundle_member"] * 5
    assert [row["member"] for row in relocated_bundle_members["assets"]] == [
        identity_by_asset[row["asset"]]["member"] for row in original_assets
    ]
    assert relocated_bundle_members["provenance"] == already_bundled["provenance"]


@pytest.mark.parametrize("mutation", ["digest", "order", "kind", "member"])
def test_resolver_rejects_preparation_identity_tampering(tmp_path: Path, mutation: str) -> None:
    request = _references_request()
    paths = {}
    for asset in ("source", "z-look", "a-look", "m-look", "b-look"):
        path = tmp_path / f"{asset}.bin"
        path.write_bytes(b"same bytes" if asset != "source" else b"source bytes")
        paths[asset] = path
    bundle = build_input_bundle(request, paths, tmp_path / "input.zip")
    preparation = prepare_request(request, asset_map={key: str(value) for key, value in paths.items()})
    preparation["input_bundle_sha256"] = bundle_digest(bundle)
    if mutation == "digest":
        preparation["assets"][1]["sha256"] = "0" * 64
    elif mutation == "order":
        preparation["assets"][1], preparation["assets"][2] = preparation["assets"][2], preparation["assets"][1]
    elif mutation == "kind":
        preparation["assets"][1]["kind"] = "unrecognized"
    else:
        preparation["assets"][1]["kind"] = "bundle_member"
        preparation["assets"][1]["member"] = "assets/wrong-member.png"

    with pytest.raises(PreparationError):
        resolve_preparation_assets(preparation, bundle, tmp_path / "resolve")


@pytest.mark.parametrize("mutation", ["payload", "traversal", "undeclared"])
def test_tampered_bundle_is_rejected_before_extraction(tmp_path: Path, mutation: str) -> None:
    request = _request()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    original = build_input_bundle(request, {"source": source}, tmp_path / "original.zip")
    resolved = read_archive(original)
    manifest = resolved.manifest
    member = manifest["assets"][0]["member"]
    if mutation == "payload":
        payload = b"tampered"
    elif mutation == "traversal":
        member = "../escaped"
        manifest["assets"][0]["member"] = member
        payload = b"source"
    else:
        payload = b"source"
    tampered = tmp_path / f"{mutation}.zip"
    with zipfile.ZipFile(tampered, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest).encode())
        archive.writestr(member, payload)
        if mutation == "undeclared":
            archive.writestr("extra", b"undeclared")
    with pytest.raises(AssetManifestError):
        materialize_input_bundle(request, tampered, tmp_path / "attempt")
    assert not (tmp_path / "attempt").exists()
