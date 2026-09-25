from __future__ import annotations

import json
import shutil
import struct
import zlib
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.compile import CompilationError, compile_preparation
from astrid.packs.h3_av.src.graph import (
    PINNED_SEITANISM_COMMIT,
    GraphBindingError,
    build_h3_graph_binding,
)
from astrid.packs.h3_av.src.kernel import validate_final_sampler_state
from astrid.packs.h3_av.src.masks import load_prepared_av_mask
from astrid.packs.h3_av.src.output_contract import validate_output_contract
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import H3RequestError, normalize_request
from astrid.packs.vibecomfy.asset_manifest import read_archive
from tests.packs.h3_av.test_request_contract import FIXTURE_DIGESTS, FIXTURES


def _raw_request(*, source: bool = True, edits: bool = True) -> dict[str, object]:
    media: list[dict[str, object]] = []
    if source:
        source: dict[str, object] = {
            "id": "source",
            "asset": "source.mp4",
            "role": "timeline",
            "modality": "video",
            "at": {"frame": 0},
            "range": [0, 15],
            "hard": True,
        }
        if edits:
            source["edit"] = [
                {"stream": "video", "during": [3, 6], "mask": {"full_frame": True}, "guides": ["performance"]},
                {"stream": "audio", "during": [3, 6], "text": "Exact speech.", "guides": ["voice"]},
            ]
        media.append(source)
        media.append({"id": "soft-anchor", "asset": "anchor.png", "role": "timeline", "modality": "image", "at": {"frame": 2}})
    media.extend(
        [
            {"id": "picture", "asset": "picture.png", "role": "reference", "modality": "image"},
            {"id": "voice", "asset": "voice.wav", "role": "reference", "modality": "audio"},
            {"id": "performance", "asset": "performance.mp4", "role": "reference", "modality": "video", "audio": True},
            {"id": "style", "asset": "style.png", "role": "reference", "modality": "image"},
        ]
    )
    return {"version": 2, "prompt": "One continuous audiovisual result.", "duration": 15, "media": media, "settings": {"steps": 8, "seed": 17, "sampler": "res_multistep"}}


def _prepared(tmp_path: Path, *, source: bool = True, edits: bool = False) -> tuple[dict[str, object], Path]:
    request = normalize_request(_raw_request(source=source, edits=edits))
    asset_dir = tmp_path / ("source" if source else "references")
    asset_map: dict[str, str] = {}
    for item in request.value["media"]:
        path = asset_dir / str(item["asset"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(str(item["asset"]).encode("utf-8"))
        asset_map[str(item["asset"])] = str(path)
    return (
        prepare_request(
            request,
            asset_map=asset_map,
            width=32,
            height=18,
            target_model_dimensions={"frames": 7, "height": 5, "width": 8},
        ),
        asset_dir,
    )


def _write_png(path: Path, rgb: tuple[int, int, int]) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)

    data = b"\x00" + bytes(rgb)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(data))
        + chunk(b"IEND", b"")
    )


def _prepared_fixture_a(tmp_path: Path) -> tuple[dict[str, object], Path]:
    request = normalize_request(FIXTURES["A"]())
    asset_dir = tmp_path / "fixture-a-assets"
    asset_dir.mkdir(parents=True)
    colors = ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0))
    asset_map: dict[str, str] = {}
    for item, color in zip(request.value["media"], colors, strict=True):
        path = asset_dir / str(item["asset"])
        _write_png(path, color)
        asset_map[str(item["asset"])] = str(path)
    return (
        prepare_request(
            request,
            asset_map=asset_map,
            width=32,
            height=32,
            target_model_dimensions={"frames": 107, "height": 2, "width": 2},
        ),
        asset_dir,
    )


def test_real_t2_artifact_reloads_into_t4_graph_and_relocates_as_one_bundle(tmp_path: Path) -> None:
    preparation, caller_assets = _prepared(tmp_path)
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(json.dumps(preparation, sort_keys=True), encoding="utf-8")
    reloaded_preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    artifact = load_prepared_av_mask(reloaded_preparation)

    binding = build_h3_graph_binding(reloaded_preparation)
    state = binding["sampler_state"]
    assert binding["branch"] == "source_backed_v2v"
    assert binding["prepared_artifact_digest"] == artifact.artifact_digest
    assert len(binding["inputs"]["references"]) == 4
    assert {item["modality"] for item in binding["inputs"]["references"]} == {"image", "video", "audio"}
    assert binding["inputs"]["masks"]["video"]["sampling"]["payload"]["materializer"].endswith("video_cell_mask")
    assert binding["inputs"]["masks"]["audio"]["sampling"]["shape"] == [600, 1, 1]
    assert binding["shared_components"]["settings"]["seed"] == 17
    assert binding["pinned_seitanism"]["commit"] == PINNED_SEITANISM_COMMIT
    assert binding["final_sampler_validation"]["status"] == "valid"
    assert state["sampler_sockets"]["latent_image"] == "c3-hard-anchors.0"
    assert state["sampler_sockets"]["guider"] == "121.0"
    graph = binding["executable_graph"]
    assert graph["final_sampler"] == {"node": "124", "guider": "121", "output": "946"}
    edges = {(edge["from_node"], edge["from_output"], edge["to_node"], edge["to_input"]) for edge in graph["edges"]}
    for stream in ("video", "audio"):
        assert (f"c3-{stream}-mask-loader", "0", f"c3-{stream}-image-to-mask", "image") in edges
        assert (f"c3-{stream}-image-to-mask", "0", f"c3-{stream}-threshold-mask", "mask") in edges
        assert (f"c3-{stream}-threshold-mask", "0", "c3-av-mask", f"{stream}_mask") in edges
    assert ("c3-soft-anchors", "0", "121", "conditioning") in edges
    validate_final_sampler_state(
        state,
        required_latent_kinds={"source_av_context", "nested_av_mask", "hard_anchor"},
        required_conditioning_kinds={"reference_conditioning", "soft_keyframe"},
    )

    first = compile_preparation(reloaded_preparation, out_dir=tmp_path / "compiled")
    compiled_graph = json.loads((tmp_path / "compiled" / "graph_binding.json").read_text(encoding="utf-8"))
    first_assets = json.loads(json.dumps(first["managed_assets"]["manifest"], sort_keys=True))
    relocated = tmp_path / "relocated"
    shutil.copytree(tmp_path / "compiled", relocated)
    shutil.rmtree(tmp_path / "compiled")
    shutil.rmtree(caller_assets)

    relocated_manifest = json.loads((relocated / "compilation.json").read_text(encoding="utf-8"))
    relocated_graph = json.loads((relocated / "graph_binding.json").read_text(encoding="utf-8"))
    relocated_envelope = json.loads((relocated / "graph.vibe.json").read_text(encoding="utf-8"))
    relocated_artifact = load_prepared_av_mask(relocated / "prepared-av-mask.json")
    relocated_assets = read_archive(relocated / "managed-assets.zip")
    assert relocated_manifest["compilation_digest"] == first["compilation_digest"]
    assert relocated_graph["bundle_identity"] == compiled_graph["bundle_identity"]
    assert relocated_graph["pinned_seitanism"]["commit"] == PINNED_SEITANISM_COMMIT
    assert relocated_graph["executable_graph"]["final_sampler"] == compiled_graph["executable_graph"]["final_sampler"]
    assert relocated_graph["executable_graph"]["edges"] == compiled_graph["executable_graph"]["edges"]
    assert relocated_envelope["nodes"]
    assert relocated_envelope["edges"]
    assert relocated_artifact.artifact_digest == artifact.artifact_digest
    assert relocated_assets.manifest == first_assets
    assert relocated_manifest["prepared_artifact"]["artifact_digest"] == artifact.artifact_digest
    validate_output_contract(relocated_manifest["output_contract"])


@pytest.mark.parametrize(
    ("source", "edits", "expected"),
    [(True, False, "source_backed_v2v"), (True, True, "extension_context")],
)
def test_real_preparation_exposes_all_internal_branches(tmp_path: Path, source: bool, edits: bool, expected: str) -> None:
    preparation, _ = _prepared(tmp_path, source=source, edits=edits)
    if edits:
        with pytest.raises(GraphBindingError, match="unsupported in-place source edits"):
            build_h3_graph_binding(preparation)
        return
    binding = build_h3_graph_binding(preparation)
    assert binding["branch"] == expected
    assert binding["shared_components"]["loaders"] == "shared_h3_av_media_loaders"
    assert binding["shared_components"]["sampler"]["class_type"] == "SamplerCustomAdvanced"
    assert binding["shared_components"]["finishing"]["output_contract"] == "one_public_muxed_av"
    assert binding["final_sampler_validation"]["status"] == "valid"


def test_repeated_reference_binding_reuses_one_real_public_loader(tmp_path: Path) -> None:
    raw = _raw_request(source=False)
    raw["media"][-1]["asset"] = raw["media"][0]["asset"]
    request = normalize_request(raw)
    asset_dir = tmp_path / "repeated-assets"
    asset_map: dict[str, str] = {}
    for item in request.value["media"]:
        asset = str(item["asset"])
        path = asset_dir / asset
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(asset.encode("utf-8"))
        asset_map[asset] = str(path)
    preparation = prepare_request(
        request,
        asset_map=asset_map,
        width=32,
        height=18,
        target_model_dimensions={"frames": 7, "height": 5, "width": 8},
    )

    binding = build_h3_graph_binding(preparation)
    envelope = binding["executable_graph"]["envelope"]
    assert sum(name == "picture.png" for name in envelope["inputs"]) == 1
    picture_edges = [
        edge for edge in binding["executable_graph"]["edges"]
        if edge["from_node"] == "c3-reference-image-0"
        and edge["to_node"] == "110"
    ]
    assert len(picture_edges) == 2


def test_fixture_a_prepares_serializes_reloads_compiles_and_relocates(tmp_path: Path) -> None:
    from vibecomfy.workflow import VibeWorkflow

    preparation, caller_assets = _prepared_fixture_a(tmp_path)
    assert preparation["request_digest"] == FIXTURE_DIGESTS["A"]
    assert preparation["request"]["duration"] == 15
    assert preparation["request"]["output_count"] == 1
    assert len([item for item in preparation["request"]["media"] if item["role"] == "reference"]) == 4
    assert not [item for item in preparation["request"]["media"] if item["role"] == "timeline"]
    artifact = load_prepared_av_mask(preparation)
    assert artifact.source_baseline_digest is None
    assert artifact.mapping["baseline_identity"]["kind"] == "none"
    assert artifact.mapping["baseline_identity"]["digest"] is None
    assert all(value == 1 for frame in artifact.video_delivery() for row in frame for value in row)
    assert all(value == 1 for channel in artifact.audio_delivery() for value in channel)

    compiled_dir = tmp_path / "compiled-a"
    compilation = compile_preparation(preparation, out_dir=compiled_dir)
    assert compilation["workflow_inputs"] == {}
    binding = json.loads((compiled_dir / "graph_binding.json").read_text(encoding="utf-8"))
    graph = binding["executable_graph"]
    assert binding["branch"] == "source_free"
    assert binding["source_baseline_digest"] is None
    assert graph["final_sampler"] == {"node": "124", "guider": "121", "output": "992"}
    assert len(graph["outputs"]) == 1
    assert graph["outputs"][0]["name"] == "av"
    assert graph["outputs"][0]["expected_cardinality"] == "one"
    assert compilation["output_contract"]["graph_outputs"] == [{
        "name": "av",
        "modality": "video",
        "expected_cardinality": "one",
        "sink_node": "992",
        "mime_type": "video/mp4",
        "contains_audio": True,
        "output_port": "vibecomfy_run",
        "ordinal": 0,
        "role": "primary",
    }]
    assert compilation["output_contract"]["public_generation"]["primary_outputs"][0]["selector"] == "main-0"
    assert compilation["output_contract"]["public_generation"]["internal_outputs"] == []

    envelope = json.loads((compiled_dir / "graph.vibe.json").read_text(encoding="utf-8"))
    assert set(envelope["inputs"]) == {
        "look-1.png",
        "look-2.png",
        "look-3.png",
        "look-4.png",
        "prepared_audio_mask",
        "prepared_video_mask",
        "model",
        "prompt",
        "seed",
        "steps",
    }
    media_inputs = {
        name: row
        for name, row in envelope["inputs"].items()
        if row.get("media_semantics") is not None
    }
    assert {name: row["media_semantics"] for name, row in media_inputs.items()} == {
        "look-1.png": "image",
        "look-2.png": "image",
        "look-3.png": "image",
        "look-4.png": "image",
        "prepared_audio_mask": "video",
        "prepared_video_mask": "video",
    }
    assert all(row["default"] == Path(row["default"]).name for row in media_inputs.values())
    assert not {"graph_binding", "pinned_seitanism", "prepared_av_mask"}.intersection(
        envelope["inputs"]
    )
    reloaded = VibeWorkflow.from_envelope(envelope)
    api = reloaded.compile("api")
    assert api["110"]["inputs"]["prompt"] == FIXTURES["A"]()["prompt"]
    assert api["110"]["inputs"]["ref_images.ref_image_3"] == ["c3-reference-image-3", 0]
    assert len(reloaded.outputs) == 1
    assert reloaded.outputs[0].node_id == "992"
    assert reloaded.outputs[0].name == "av"
    assert reloaded.outputs[0].mime_type == "video/mp4"
    classes = [node.class_type for node in reloaded.nodes.values()]
    assert classes.count("SamplerCustomAdvanced") == 1
    assert classes.count("MiniMaxH3ReferenceToVideo") == 1
    assert classes.count("VHS_VideoCombine") == 1
    assert "MiniMaxH3StartMaskedContext" not in classes
    assert "MiniMaxH3StreamLiveExtensionAVToVHS" not in classes

    relocated = tmp_path / "relocated-a"
    shutil.copytree(compiled_dir, relocated)
    shutil.rmtree(compiled_dir)
    shutil.rmtree(caller_assets)
    relocated_graph = json.loads((relocated / "graph_binding.json").read_text(encoding="utf-8"))
    relocated_envelope = json.loads((relocated / "graph.vibe.json").read_text(encoding="utf-8"))
    relocated_assets = read_archive(relocated / "managed-assets.zip")
    assert relocated_graph["bundle_identity"] == binding["bundle_identity"]
    assert relocated_graph["inputs"]["reference_edges"] == binding["inputs"]["reference_edges"]
    assert VibeWorkflow.from_envelope(relocated_envelope).compile("api")["110"]["inputs"]["ref_images.ref_image_3"] == ["c3-reference-image-3", 0]
    assert len(relocated_assets.manifest["assets"]) == 6  # four refs plus two managed AV masks


def test_each_fixture_a_asset_mutation_after_preparation_is_rejected(tmp_path: Path) -> None:
    preparation, _ = _prepared_fixture_a(tmp_path)
    for index, record in enumerate(preparation["assets"]):
        path = Path(record["path"])
        original = path.read_bytes()
        path.write_bytes(original + bytes([index]))
        try:
            with pytest.raises(CompilationError, match="changed after preparation"):
                compile_preparation(preparation, out_dir=tmp_path / f"tampered-{index}")
        finally:
            path.write_bytes(original)


def test_each_deliberate_fixture_a_reprepare_changes_asset_artifact_and_bundle_identity(tmp_path: Path) -> None:
    request = normalize_request(FIXTURES["A"]())
    preparation, _ = _prepared_fixture_a(tmp_path)
    baseline = build_h3_graph_binding(preparation)
    asset_map = {str(record["asset"]): str(record["path"]) for record in preparation["assets"]}
    baseline_hashes = {str(record["asset"]): str(record["sha256"]) for record in preparation["assets"]}

    for index, item in enumerate(request.value["media"]):
        path = Path(asset_map[str(item["asset"])])
        original = path.read_bytes()
        _write_png(path, (20 + index, 40 + index, 60 + index))
        try:
            reprepared = prepare_request(
                request,
                asset_map=asset_map,
                width=32,
                height=32,
                target_model_dimensions={"frames": 107, "height": 2, "width": 2},
            )
            changed_hashes = {str(record["asset"]): str(record["sha256"]) for record in reprepared["assets"]}
            changed = build_h3_graph_binding(reprepared)
            assert reprepared["request_digest"] == preparation["request_digest"]
            assert changed_hashes[str(item["asset"])] != baseline_hashes[str(item["asset"])]
            assert all(
                changed_hashes[asset] == digest
                for asset, digest in baseline_hashes.items()
                if asset != str(item["asset"])
            )
            assert reprepared["artifact_digest"] != preparation["artifact_digest"]
            assert changed["prepared_artifact_digest"] != baseline["prepared_artifact_digest"]
            assert changed["bundle_identity"] != baseline["bundle_identity"]
        finally:
            path.write_bytes(original)


def test_graph_negatives_cover_dangling_and_wrong_modality_before_compile(tmp_path: Path) -> None:
    raw = _raw_request()
    raw["media"][0]["edit"][0]["guides"] = ["missing"]  # type: ignore[index]
    with pytest.raises(H3RequestError, match="dangling"):
        normalize_request(raw)

    raw = _raw_request()
    raw["media"][0]["edit"][0]["guides"] = ["voice"]  # type: ignore[index]
    with pytest.raises(H3RequestError, match="wrong modality"):
        normalize_request(raw)
