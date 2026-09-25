from __future__ import annotations

import copy
import json
import zipfile
from pathlib import Path

import pytest

from astrid.packs.h3_av.executors.compile.run import main as compile_executor_main
from astrid.packs.h3_av.src.compile import CompilationError, compile_preparation
from astrid.packs.h3_av.src.graph import (
    PINNED_SEITANISM_COMMIT,
    GraphBindingError,
    build_h3_graph_binding,
    validate_h3_graph_binding,
)
from astrid.packs.h3_av.src.kernel import H3KernelContractError, validate_final_sampler_state
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from tests.packs.h3_av.test_request_contract import FIXTURE_DIGESTS, FIXTURES


def _request(*, source: bool = True, mixed_refs: bool = True):
    media: list[dict[str, object]] = []
    if source:
        media.append(
            {
                "id": "source",
                "asset": "source.mp4",
                "role": "timeline",
                "modality": "video",
                "at": {"frame": 0},
                "range": [0, 15],
                "hard": True,
                "edit": [
                    {"stream": "video", "during": [3, 6], "mask": {"full_frame": True}, "guides": ["picture"]},
                    {"stream": "audio", "during": [3, 6], "text": "The exact line.", "guides": ["voice"]},
                ],
            }
        )
    media.extend(
        [
            {"id": "picture", "asset": "picture.png", "role": "reference", "modality": "image"},
            {"id": "voice", "asset": "voice.wav", "role": "reference", "modality": "audio"},
        ]
    )
    if source:
        media.append(
            {
                "id": "anchor",
                "asset": "anchor.png",
                "role": "timeline",
                "modality": "image",
                "at": {"frame": 2},
            }
        )
    if mixed_refs:
        media.extend(
            [
                {"id": "performance", "asset": "performance.mp4", "role": "reference", "modality": "video", "audio": True},
                {"id": "style", "asset": "style.png", "role": "reference", "modality": "image"},
            ]
        )
    return normalize_request(
        {
            "version": 2,
            "prompt": "One continuous audiovisual result.",
            "duration": 15,
            "media": media,
            "settings": {"steps": 8, "seed": 17, "sampler": "res_multistep"},
        }
    )


def _mask(shape: list[int], payload: str) -> dict[str, object]:
    return {"shape": shape, "payload": payload, "polarity": "black_preserve_white_edit"}


def _source_free_images(count: int, *, duplicate: bool = False):
    raw = FIXTURES["A"]()
    raw["media"] = [
        {
            "id": f"look-{index}",
            "asset": "shared.png" if duplicate and index in {1, 2} else f"look-{index}.png",
            "role": "reference",
            "modality": "image",
        }
        for index in range(count)
    ]
    return normalize_request(raw)


def _prepared(request, *, anchors=None, audio_only: bool = False, assets: bool = False, asset_dir: Path | None = None) -> dict[str, object]:
    raw = request.value
    if audio_only:
        raw = json.loads(json.dumps(raw))
        raw["media"][0]["edit"] = [raw["media"][0]["edit"][1]]
    has_timeline = any(item.get("role") == "timeline" for item in raw["media"])
    artifact = {
        "kind": "h3_av_prepared_input",
        "schema_version": 1,
        "status": "prepared",
        "request": raw,
        "request_digest": __import__("hashlib").sha256(
            json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "source_baseline_digest": "sha256:" + "b" * 64 if has_timeline else None,
        "mapping": {
            "baseline_identity": (
                {"kind": "source", "digest": "sha256:" + "b" * 64}
                if has_timeline
                else {"kind": "none", "digest": None, "members": []}
            )
        },
        "video": {
            "delivery": _mask([360, 576, 1024], "video-delivery[F,H,W]"),
            "sampling": _mask([7, 18, 32], "video-model-mask"),
        },
        "audio": {
            "delivery": _mask([2, 720000], "audio-delivery[C,S]"),
            "sampling": _mask([40, 1, 1], "audio-40hz-envelope"),
        },
        "anchors": anchors or [],
    }
    result: dict[str, object] = {"prepared_input": artifact}
    if assets:
        assert asset_dir is not None
        result["assets"] = []
        for asset_id in sorted({item["asset"] for item in raw["media"]}):
            path = asset_dir / asset_id
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(asset_id.encode("utf-8"))
            result["assets"].append(
                {
                    "asset": asset_id,
                    "status": "resolved",
                    "path": str(path),
                    "size": path.stat().st_size,
                    "sha256": __import__("hashlib").sha256(path.read_bytes()).hexdigest(),
                }
            )
    return result


def _real_prepared_for_compile(tmp_path: Path) -> dict[str, object]:
    request = _request()
    asset_dir = tmp_path / "assets"
    asset_map: dict[str, str] = {}
    for item in request.value["media"]:
        path = asset_dir / str(item["asset"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(str(item["asset"]).encode("utf-8"))
        asset_map[str(item["asset"])] = str(path)
    return prepare_request(
        request,
        asset_map=asset_map,
        width=32,
        height=18,
        target_model_dimensions={"frames": 7, "height": 5, "width": 8},
    )


def test_mixed_media_and_four_dynamic_references_bind_one_final_sampler() -> None:
    request = _request()
    prepared = _prepared(
        request,
        anchors=[{"id": "source", "frame": 0, "mode": "hard"}, {"id": "anchor", "frame": 2, "mode": "soft"}],
    )
    binding = build_h3_graph_binding(prepared)

    assert binding["branch"] == "extension_context"
    assert len(binding["inputs"]["references"]) == 4
    assert {item["modality"] for item in binding["inputs"]["references"]} == {"image", "video", "audio"}
    assert binding["pinned_seitanism"]["commit"] == PINNED_SEITANISM_COMMIT
    assert binding["inputs"]["masks"]["video"]["delivery"]["shape"] == [360, 576, 1024]
    assert binding["inputs"]["masks"]["audio"]["delivery"]["shape"] == [2, 720000]
    assert binding["final_sampler_validation"]["status"] == "valid"
    graph = binding["executable_graph"]
    assert graph["final_sampler"] == {"node": "124", "guider": "121", "output": "946"}
    assert binding["sampler_state"]["sampler_sockets"]["latent_image"] == "c3-hard-anchors.0"
    edges = {(edge["from_node"], edge["from_output"], edge["to_node"], edge["to_input"]) for edge in graph["edges"]}
    for stream in ("video", "audio"):
        assert (f"c3-{stream}-mask-loader", "0", f"c3-{stream}-image-to-mask", "image") in edges
        assert (f"c3-{stream}-image-to-mask", "0", f"c3-{stream}-threshold-mask", "mask") in edges
        assert (f"c3-{stream}-threshold-mask", "0", "c3-av-mask", f"{stream}_mask") in edges
        assert graph["compiled_api"]["c3-av-mask"]["inputs"][f"{stream}_mask"] == [f"c3-{stream}-threshold-mask", 0]
    assert ("c3-reference-image-0", "0", "110", "ref_images.ref_image_0") in edges
    assert ("c3-reference-audio-1", "0", "110", "ref_audios.ref_audio_0") in edges
    assert ("c3-reference-video-2", "0", "110", "ref_videos.ref_video_0") in edges
    assert ("c3-soft-anchors", "0", "c3-motion-guide-0", "conditioning") in edges
    assert ("c3-motion-guide-0", "0", "c3-motion-guide-1", "conditioning") in edges
    assert ("c3-motion-guide-1", "0", "121", "conditioning") in edges
    assert any(edge["to_node"] == "c3-hard-anchors" and edge["to_input"].startswith("keyframe_image_") for edge in graph["edges"])
    assert "The exact line." in next(node for node in graph["nodes"] if node["id"] == "110")["inputs"]["prompt"]


def test_fixture_a_source_free_uses_one_native_conditioner_sampler_and_mux() -> None:
    request = normalize_request(FIXTURES["A"]())
    binding = build_h3_graph_binding(_prepared(request))

    assert request.digest == FIXTURE_DIGESTS["A"]
    assert request.value["duration"] == 15
    assert [item["model_tag"] for item in binding["inputs"]["references"]] == [
        "<Picture 1>",
        "<Picture 2>",
        "<Picture 3>",
        "<Picture 4>",
    ]
    assert not [item for item in request.value["media"] if item["role"] == "timeline"]
    assert request.value["output_count"] == 1
    assert binding["branch"] == "source_free"
    assert binding["source_baseline_digest"] is None
    geometry = binding["native_geometry"]
    assert geometry["source"] is None
    assert geometry["delivery"]["video"] == {"frames": 360, "height": 576, "width": 1024, "fps": 24}
    assert geometry["delivery"]["audio"] == {"channels": 2, "samples_per_channel": 720000, "sample_rate": 48000}
    assert geometry["native"]["video_frames"] == 362
    assert geometry["native"]["audio_ticks"] == 603
    assert geometry["latent"]["video"] == [1, 24, 107, 36, 64]
    assert geometry["latent"]["audio"] == [1, 32, 2, 603]
    assert geometry["delivery_trim"]["keep_video_frames"] == [0, 360]
    assert geometry["delivery_trim"]["keep_audio_samples"] == [0, 720000]

    graph = binding["executable_graph"]
    nodes = graph["nodes"]
    classes = [node["class_type"] for node in nodes]
    assert classes.count("MiniMaxH3ReferenceToVideo") == 1
    assert classes.count("SamplerCustomAdvanced") == 1
    assert classes.count("VAEDecode") == 1
    assert classes.count("VAEDecodeAudio") == 1
    assert classes.count("VHS_VideoCombine") == 1
    assert "MiniMaxH3StartMaskedContext" not in classes
    assert "MiniMaxH3StreamLiveExtensionAVToVHS" not in classes
    assert "MiniMaxH3GeneratedAVMaskedContext" not in classes
    assert not any(node["id"].startswith("c3-timeline-") for node in nodes)
    assert graph["final_sampler"] == {"node": "124", "guider": "121", "output": "992"}
    assert graph["outputs"] == [{
        "node_id": "992",
        "output_type": "VHS_VideoCombine",
        "name": "av",
        "artifact_kind": "video",
        "mime_type": "video/mp4",
        "filename_prefix": "video/h3_source_free_av",
        "expected_cardinality": "one",
    }]
    edges = {(edge["from_node"], edge["from_output"], edge["to_node"], edge["to_input"]) for edge in graph["edges"]}
    for index in range(4):
        assert (f"c3-reference-image-{index}", "0", "110", f"ref_images.ref_image_{index}") in edges
    assert ("110", "1", "c3-av-mask", "latent") in edges
    assert ("c3-av-mask", "0", "124", "latent_image") in edges
    assert ("124", "0", "990", "samples") in edges
    assert ("124", "0", "991", "samples") in edges
    assert ("990", "0", "992", "images") in edges
    assert ("991", "0", "992", "audio") in edges
    conditioner = graph["compiled_api"]["110"]["inputs"]
    assert conditioner["prompt"] == FIXTURES["A"]()["prompt"]
    assert conditioner["length"] == 362
    assert conditioner["ref_images.ref_image_3"] == ["c3-reference-image-3", 0]
    envelope_nodes = graph["envelope"]["nodes"]
    envelope_conditioner = envelope_nodes["110"] if isinstance(envelope_nodes, dict) else next(node for node in envelope_nodes if node["id"] == "110")
    assert "ref_images.ref_image_8" in envelope_conditioner["native_input_names"]
    assert validate_h3_graph_binding(binding)["bundle_identity"] == binding["bundle_identity"]


@pytest.mark.parametrize("count", [1, 3, 4, 9])
def test_native_image_autogrow_accepts_every_legal_boundary(count: int) -> None:
    binding = build_h3_graph_binding(_prepared(_source_free_images(count)))
    ports = [row["conditioner_input"] for row in binding["inputs"]["reference_edges"]]
    assert ports == [f"ref_images.ref_image_{index}" for index in range(count)]


def test_ten_images_are_rejected_before_workflow_materialization(monkeypatch: pytest.MonkeyPatch) -> None:
    import astrid.packs.h3_av.src.graph as graph_module

    monkeypatch.setattr(graph_module, "_load_h3_workflow", lambda: pytest.fail("inference graph was loaded"))
    with pytest.raises(GraphBindingError, match="at most 9 image references"):
        build_h3_graph_binding(_prepared(_source_free_images(10)))


def test_four_images_bind_through_the_preserved_source_backed_branch() -> None:
    raw = FIXTURES["A"]()
    raw["media"].insert(
        0,
        {
            "id": "source",
            "asset": "source.mp4",
            "role": "timeline",
            "modality": "video",
            "at": {"frame": 0},
            "range": [0, 15],
        },
    )
    binding = build_h3_graph_binding(_prepared(normalize_request(raw)))
    edges = {
        (edge["from_node"], edge["from_output"], edge["to_node"], edge["to_input"])
        for edge in binding["executable_graph"]["edges"]
    }
    assert binding["branch"] == "source_backed_v2v"
    assert ("c3-reference-image-3", "0", "110", "ref_images.ref_image_3") in edges
    assert ("103", "0", "c3-av-mask", "latent") in edges
    assert binding["executable_graph"]["final_sampler"]["output"] == "946"


def test_zero_reference_placed_still_uses_source_free_latent_without_video_source() -> None:
    raw = FIXTURES["A"]()
    raw["media"] = [
        {
            "id": "placed-still",
            "asset": "placed.png",
            "role": "timeline",
            "modality": "image",
            "at": {"frame": 2},
        }
    ]
    request = normalize_request(raw)
    binding = build_h3_graph_binding(
        _prepared(request, anchors=[{"id": "placed-still", "frame": 2, "mode": "soft"}])
    )
    classes = [node["class_type"] for node in binding["executable_graph"]["nodes"]]
    edges = {
        (edge["from_node"], edge["from_output"], edge["to_node"], edge["to_input"])
        for edge in binding["executable_graph"]["edges"]
    }
    assert binding["branch"] == "source_free"
    assert binding["inputs"]["references"] == []
    assert "MiniMaxH3StartMaskedContext" not in classes
    assert ("110", "1", "c3-av-mask", "latent") in edges
    assert ("c3-soft-anchors", "0", "121", "conditioning") in edges
    assert binding["final_sampler_validation"]["conditioning_kinds"] == [
        "prompt_conditioning",
        "soft_keyframe",
    ]


def test_reference_order_duplicates_and_each_edge_are_identity_checked() -> None:
    request = _source_free_images(4, duplicate=True)
    binding = build_h3_graph_binding(_prepared(request))
    rows = binding["inputs"]["reference_edges"]
    assert [row["asset"] for row in rows] == ["look-0.png", "shared.png", "shared.png", "look-3.png"]
    assert [row["conditioner_input"] for row in rows] == [f"ref_images.ref_image_{index}" for index in range(4)]
    assert rows[1]["asset_member"] == rows[2]["asset_member"]
    assert rows[1]["id"] != rows[2]["id"]

    for index, row in enumerate(rows):
        omitted = copy.deepcopy(binding)
        omitted["executable_graph"]["edges"] = [
            edge
            for edge in omitted["executable_graph"]["edges"]
            if not (edge["from_node"] == row["loader"] and edge["to_input"] == row["conditioner_input"])
        ]
        with pytest.raises(GraphBindingError, match="reference edges"):
            validate_h3_graph_binding(omitted)

        mutated = copy.deepcopy(binding)
        loader = next(node for node in mutated["executable_graph"]["nodes"] if node["id"] == row["loader"])
        loader["inputs"]["image"] = f"mutated-{index}.png"
        with pytest.raises(GraphBindingError, match="asset identity"):
            validate_h3_graph_binding(mutated)


def test_wrong_missing_and_duplicate_output_descriptors_are_rejected() -> None:
    binding = build_h3_graph_binding(_prepared(normalize_request(FIXTURES["A"]())))
    for outputs in (
        [],
        [*binding["executable_graph"]["outputs"], *binding["executable_graph"]["outputs"]],
        [{**binding["executable_graph"]["outputs"][0], "expected_cardinality": "many"}],
    ):
        mutated = copy.deepcopy(binding)
        mutated["executable_graph"]["outputs"] = outputs
        with pytest.raises(GraphBindingError, match="one AV output"):
            validate_h3_graph_binding(mutated)


def test_audio_only_preserves_video_mask_and_still_emits_both_streams() -> None:
    request = _request()
    binding = build_h3_graph_binding(_prepared(request, audio_only=True))
    assert any(node["id"] == "c3-av-mask" and node["class_type"] == "MiniMaxH3SetAVNoiseMask" for node in binding["executable_graph"]["nodes"])
    assert any(edge["to_node"] == "c3-av-mask" and edge["to_input"] == "audio_mask" for edge in binding["executable_graph"]["edges"])


def test_fixture_c_audio_timeline_channel_edits_and_voice_reference_compile(tmp_path: Path) -> None:
    request = normalize_request(FIXTURES["C"]())
    assets: dict[str, str] = {}
    for item in request.value["media"]:
        asset = str(item["asset"])
        path = tmp_path / asset
        path.write_bytes(asset.encode("utf-8"))
        assets[asset] = str(path)

    preparation = prepare_request(request, asset_map=assets, width=8, height=8)
    artifact = preparation["prepared_av_mask"]
    assert artifact["video"]["shape"] == {"frames": 360, "height": 8, "width": 8}
    from astrid.packs.h3_av.src.masks import load_prepared_av_mask

    prepared_mask = load_prepared_av_mask(artifact)
    assert all(value == 1 for frame in prepared_mask.video_delivery() for row in frame for value in row)
    audio_permissions = prepared_mask.audio_delivery()
    assert audio_permissions[0][3 * 48000] == 1
    assert audio_permissions[1][3 * 48000] == 0
    assert audio_permissions[1][8 * 48000] == 1
    assert audio_permissions[0][8 * 48000] == 0

    compiled = compile_preparation(preparation, out_dir=tmp_path / "compiled")
    binding = json.loads(Path(compiled["graph_binding"]["path"]).read_text(encoding="utf-8"))
    assert binding["branch"] == "audio_only"
    assert binding["executable_graph"]["final_sampler"]["output"] == "992"
    edges = {
        (edge["from_node"], edge["from_output"], edge["to_node"], edge["to_input"])
        for edge in binding["executable_graph"]["edges"]
    }
    assert ("c3-timeline-audio-0", "0", "110", "ref_audios.ref_audio_0") in edges
    assert ("c3-reference-audio-0", "0", "110", "ref_audios.ref_audio_1") in edges
    with zipfile.ZipFile(compiled["managed_assets"]["path"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
    assert {row["binding"] for row in manifest["assets"]} >= {"source-c.wav", "voice-c.wav"}


@pytest.mark.parametrize("label", ["D", "E", "X"])
def test_checked_in_anchor_fixtures_prepare_and_compile_without_latent_reinterpretation(
    tmp_path: Path, label: str
) -> None:
    request = normalize_request(FIXTURES[label]())
    assets: dict[str, str] = {}
    asset_ids = {str(item["asset"]) for item in request.value["media"]}
    for item in request.value["media"]:
        for edit in item.get("edit", []):
            mask = edit.get("mask", {})
            if isinstance(mask, dict) and isinstance(mask.get("asset"), str):
                asset_ids.add(str(mask["asset"]))
    for asset in sorted(asset_ids):
        path = tmp_path / asset
        if asset.endswith(".json"):
            path.write_text(json.dumps([[0] * 16 for _ in range(16)]), encoding="utf-8")
        else:
            path.write_bytes(asset.encode("utf-8"))
        assets[asset] = str(path)
    preparation = prepare_request(
        request,
        asset_map=assets,
        width=16,
        height=16,
        target_model_dimensions={"frames": 107, "height": 4, "width": 4},
    )
    classified = preparation["prepared_av_mask"]["anchors"]
    assert all(anchor["exact_final_restoration"] for anchor in classified)
    assert any(anchor["classification"] == "restoration_only" for anchor in classified)
    compiled = compile_preparation(preparation, out_dir=tmp_path / "compiled")
    binding = json.loads(Path(compiled["graph_binding"]["path"]).read_text(encoding="utf-8"))
    assert binding["anchors"] == classified


def test_unsupported_explicit_hard_latent_pin_fails_preparation(tmp_path: Path) -> None:
    raw = FIXTURES["D"]()
    raw["media"][1]["latent_pin"] = True
    request = normalize_request(raw)
    assets: dict[str, str] = {}
    for item in request.value["media"]:
        asset = str(item["asset"])
        path = tmp_path / asset
        path.write_bytes(asset.encode("utf-8"))
        assets[asset] = str(path)
    with pytest.raises(ValueError, match="unsupported hard anchors"):
        prepare_request(
            request,
            asset_map=assets,
            width=16,
            height=16,
            target_model_dimensions={"frames": 107, "height": 4, "width": 4},
        )


def test_missing_audio_stream_fails_before_graph_admission() -> None:
    request = _request()
    prepared = _prepared(request)
    del prepared["prepared_input"]["audio"]
    with pytest.raises(GraphBindingError, match="missing audio AV mask stream"):
        build_h3_graph_binding(prepared)


def test_protected_and_colliding_hard_anchors_fail_without_shifting() -> None:
    request = _request()
    for anchors, message in (
        ([{"id": "source", "frame": 0, "mode": "hard"}], "protected"),
            ([{"id": "source", "frame": 1, "mode": "hard"}], "cell_spans_multiple_delivery_frames"),
            ([{"id": "source", "frame": 1, "mode": "hard"}, {"id": "anchor", "frame": 2, "mode": "hard"}], "hard_anchor_cell_collision"),
    ):
        prepared = _prepared(request, anchors=anchors)
        if message == "protected":
            prepared["prepared_input"]["protected_cells"] = [0]
        with pytest.raises(GraphBindingError, match=message):
            build_h3_graph_binding(prepared)


def test_late_sampler_latent_overwrite_is_rejected_by_t3_validator() -> None:
    binding = build_h3_graph_binding(_prepared(_request(), anchors=[{"id": "source", "frame": 0, "mode": "hard"}]))
    state = json.loads(json.dumps(binding["sampler_state"]))
    state["sampler_sockets"]["latent_image"] = "stale-before-mask.out"
    with pytest.raises(H3KernelContractError, match="final latent mutation"):
        validate_final_sampler_state(state, required_latent_kinds={"source_av_context", "nested_av_mask", "hard_anchor"}, required_conditioning_kinds={"reference_conditioning", "motion_context"})


def test_compile_relocation_keeps_graph_identity_and_pinned_lineage(tmp_path: Path) -> None:
    prepared = _real_prepared_for_compile(tmp_path)
    first = compile_preparation(prepared, out_dir=tmp_path / "first")
    second = compile_preparation(prepared, out_dir=tmp_path / "second")
    assert first["graph_binding"]["bundle_identity"] == second["graph_binding"]["bundle_identity"]
    assert first["compilation_digest"] == second["compilation_digest"]
    assert json.loads(Path(first["graph_binding"]["path"]).read_text())["pinned_seitanism"]["commit"] == PINNED_SEITANISM_COMMIT


def test_compile_executor_publishes_graph_boundary_outputs(tmp_path: Path) -> None:
    preparation = _real_prepared_for_compile(tmp_path)
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(json.dumps(preparation), encoding="utf-8")
    output = tmp_path / "compiled"
    assert compile_executor_main(["--preparation", str(preparation_path), "--out", str(output)]) == 0
    assert (output / "compilation.json").is_file()
    assert (output / "graph_binding.json").is_file()
    assert (output / "managed-assets.zip").is_file()


def test_compile_rejects_missing_prepared_input_instead_of_falling_back() -> None:
    with pytest.raises(CompilationError, match="prepared-input artifact"):
        compile_preparation({"kind": "h3_av_prepared_input"}, out_dir=Path("/tmp/t4-missing"))
