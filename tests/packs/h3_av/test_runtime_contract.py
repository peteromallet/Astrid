from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.packs.h3_av.orchestrators.transform.run import (
    _invoke,
    _materialize_output,
    _retrieve_compiled_workflow,
    run_transform,
)
from astrid.packs.h3_av.src.compile import compile_preparation
from astrid.packs.h3_av.src.compose import compose_candidate
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.h3_av.src.verify import VerificationError, verify_candidate
from astrid.core.execution.orchestrator.registry import OrchestratorRegistry
from astrid.core.execution.orchestrator.runner import OrchestratorRunRequest, build_orchestrator_command
from astrid.core.execution.orchestrator.schema import load_orchestrator_manifest


def _request():
    return normalize_request(
        {
            "version": 1,
            "operation": "edit",
            "source": {"asset": "source", "range": [0, 1]},
            "output": {"duration": 2},
            "content": {"prompt": "preserve the protected source"},
            "changes": {
                "video": [{"during": [1, 2], "area": {"full_frame": True}, "action": "generate"}],
                "audio": [{"during": [1, 2], "action": "generate"}],
            },
            "references": [],
            "overrides": {},
        }
    )


def test_transform_invokes_children_through_the_connected_client(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    class Client:
        def invoke_result(self, capability_id: str, **kwargs: object):
            calls.append({"capability_id": capability_id, **kwargs})
            return SimpleNamespace(ok=True, capability_id=capability_id)

    result = _invoke(Client(), "h3_av.prepare", inputs={}, out=tmp_path, project="project-1")
    assert result.ok is True
    assert calls[0]["capability_id"] == "h3_av.prepare"
    assert calls[0]["wait"] is True


def test_transform_command_forwards_execution_request_and_keeps_default(tmp_path: Path) -> None:
    manifest = Path(__file__).resolve().parents[3] / "astrid/packs/h3_av/orchestrators/transform/orchestrator.yaml"
    registry = OrchestratorRegistry([load_orchestrator_manifest(manifest)])
    execution_request = tmp_path / "execution-request.json"

    supplied = build_orchestrator_command(
        OrchestratorRunRequest(
            orchestrator_id="h3_av.transform",
            out=tmp_path / "out",
            inputs={
                "request": "request.json",
                "input_bundle": "assets.zip",
                "execution_request": str(execution_request),
            },
        ),
        registry,
    )
    assert supplied[supplied.index("--execution-request") + 1] == str(execution_request.resolve())

    defaulted = build_orchestrator_command(
        OrchestratorRunRequest(
            orchestrator_id="h3_av.transform",
            out=tmp_path / "out",
            inputs={"request": "request.json", "input_bundle": "assets.zip"},
        ),
        registry,
    )
    assert defaulted[defaulted.index("--execution-request") + 1] == ""
    from astrid.packs.h3_av.orchestrators.transform.run import build_parser

    assert build_parser().parse_args(
        ["--request", "request.json", "--asset-map", "assets.json", "--out", "out"]
    ).execution_request == ""


def test_transform_reaches_default_canonical_sdk_before_prepare(monkeypatch, tmp_path: Path) -> None:
    import astrid.packs.h3_av.orchestrators.transform.run as transform
    from astrid.packs.h3_av.src.input_bundle import build_input_bundle

    order: list[str] = []
    child_inputs: list[dict[str, object]] = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def invoke_result(self, capability_id: str, **kwargs):
            order.append(f"invoke:{capability_id}")
            child_inputs.append(kwargs["inputs"])
            return SimpleNamespace(ok=False, error="stop after first admission boundary")

    def open_default(cls, **kwargs):
        assert kwargs == {}
        order.append("sdk-open-from-launcher")
        return Client()

    monkeypatch.setattr(transform.AstridClient, "open_from_launcher", classmethod(open_default))
    request = _request()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request.value), encoding="utf-8")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture source")
    bundle = build_input_bundle(request, {"source": source}, tmp_path / "input-bundle.zip")
    monkeypatch.setattr(
        transform, "_import_runtime_file",
        lambda *_args, **kwargs: {"object_id": kwargs["filename"], "filename": kwargs["filename"]},
    )
    args = SimpleNamespace(
        out=tmp_path / "out", dry_run=False, execution_request=None,
        request=request_path, asset_map=bundle,
        project="fixture-project",
    )

    with pytest.raises(RuntimeError, match="h3_av.prepare failed"):
        run_transform(args)

    assert order == ["sdk-open-from-launcher", "invoke:h3_av.prepare"]
    assert child_inputs == [{
        "request": {"object_id": "request.json", "filename": "request.json"},
        "input_bundle": {"object_id": "h3-input-bundle.zip", "filename": "h3-input-bundle.zip"},
    }]


@pytest.mark.parametrize("label", ["B", "E", "F", "X"])
def test_transform_rejects_legacy_asset_maps_before_child_client(label: str, monkeypatch, tmp_path: Path) -> None:
    import astrid.packs.h3_av.orchestrators.transform.run as transform
    from tests.packs.h3_av.test_request_contract import FIXTURES

    request = tmp_path / "request.json"
    request.write_text(json.dumps(FIXTURES[label]()), encoding="utf-8")
    asset_map = tmp_path / "asset-map.json"
    asset_map.write_text(json.dumps({"source": "/caller/source.mp4"}), encoding="utf-8")
    monkeypatch.setattr(transform.AstridClient, "open_from_launcher", lambda: pytest.fail("child client opened"))
    with pytest.raises(RuntimeError, match="prebuilt managed input bundle; JSON asset-map paths are unsupported"):
        run_transform(SimpleNamespace(
            out=tmp_path / "out", dry_run=False, execution_request="",
            request=request, asset_map=asset_map, project=None,
        ))


def test_public_prepare_rejects_asset_map_without_bundle(tmp_path: Path) -> None:
    from astrid.packs.h3_av.executors.prepare.run import main as prepare_main

    request = tmp_path / "request.json"
    request.write_text(json.dumps(_request().value), encoding="utf-8")
    asset_map = tmp_path / "asset-map.json"
    asset_map.write_text(json.dumps({"source": "/caller/source.mp4"}), encoding="utf-8")
    with pytest.raises(ValueError, match="import declared assets as a managed --input-bundle"):
        prepare_main([
            "--request", str(request), "--asset-map", str(asset_map),
            "--out", str(tmp_path / "preparation.json"),
        ])
    assert not (tmp_path / "preparation.json").exists()


def test_compile_definition_revision_changes_nested_identity_without_touching_transform() -> None:
    from astrid.core.execution.executor.folder import load_folder_executor

    pack_root = Path(__file__).resolve().parents[3] / "astrid/packs/h3_av"
    compile_definition = load_folder_executor(pack_root / "executors/compile")
    assert compile_definition.version == "0.1.1"
    transform_text = (pack_root / "orchestrators/transform/orchestrator.yaml").read_text(encoding="utf-8")
    assert "version: 0.1.1" in transform_text


def test_managed_output_retrieval_reads_object_and_verifies_digest(tmp_path: Path) -> None:
    payload = b"settled-output"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()

    class Media:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def read_bytes(self, object_id: str) -> bytes:
            self.calls.append(object_id)
            return payload

    media = Media()
    result = SimpleNamespace(
        capability_id="vibecomfy.run",
        outputs={"managed_outputs": [{"name": "vibecomfy_run", "object_id": digest, "size": len(payload), "filename": "candidate.mp4", "role": "result"}]},
        raw_result={},
    )
    path, row = _materialize_output(SimpleNamespace(media=media), result, "vibecomfy_run", tmp_path)
    assert path.read_bytes() == payload
    assert row["object_id"] == digest
    assert media.calls == [digest]
    receipt_path = Path(row["receipt_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["verified"] is True
    assert receipt["managed_object_id"] == digest
    assert receipt["sha256"] == hashlib.sha256(payload).hexdigest()
    assert receipt["size"] == len(payload)
    assert receipt["local_path"] == str(path.resolve())


def _lanpaint_preparation(tmp_path: Path) -> dict[str, object]:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source-video")
    request = normalize_request(
        {
            "version": 1,
            "operation": "edit",
            "source": {"asset": "source", "range": [0, 4]},
            "output": {"duration": 4},
            "content": {"prompt": "Replace the spoken line."},
            "changes": {
                "video": [{"during": [1, 3], "area": {"full_frame": True}, "action": "generate"}],
                "audio": [{"during": [1, 2], "action": "generate", "dialogue": "Say hello."}],
            },
            "references": [],
            "overrides": {"seed": 7, "steps": 12},
        }
    )
    return prepare_request(request, asset_map={"source": str(source)})


class _FakeManagedMedia:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.reads: list[str] = []

    def read_bytes(self, object_id: str) -> bytes:
        self.reads.append(object_id)
        return self.objects[object_id]


def _compile_result_with_managed_bundle(tmp_path: Path):
    compiled = compile_preparation(_lanpaint_preparation(tmp_path), out_dir=tmp_path / "compiled")
    objects: dict[str, bytes] = {}
    rows: list[dict[str, object]] = []
    outputs = {
        "compilation": (Path(compiled["manifest_path"]).read_bytes(), "compilation.json"),
        "managed_assets": (Path(compiled["managed_assets"]["path"]).read_bytes(), "managed-assets.zip"),
        "python": (Path(compiled["workflow"]["workflow.py"]["path"]).read_bytes(), "workflow.py"),
        "companion": (Path(compiled["workflow"]["workflow.vibe.json"]["path"]).read_bytes(), "workflow.vibe.json"),
        "source": (Path(compiled["workflow"]["source.json"]["path"]).read_bytes(), "source.json"),
    }
    for name, (payload, filename) in outputs.items():
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        objects[digest] = payload
        rows.append({"name": name, "object_id": digest, "digest": digest, "size": len(payload), "filename": filename, "role": "result"})
    return compiled, SimpleNamespace(capability_id="h3_av.compile", outputs={"managed_outputs": rows}, raw_result={}), _FakeManagedMedia(objects)


def test_connected_client_uses_selected_lanpaint_bundle_and_attests_provenance(tmp_path: Path) -> None:
    compiled, result, media = _compile_result_with_managed_bundle(tmp_path)

    inputs = _retrieve_compiled_workflow(
        SimpleNamespace(media=media),
        result,
        json.loads(Path(compiled["manifest_path"]).read_text(encoding="utf-8")),
        tmp_path / "retrieved",
    )

    assert set(inputs) == {"python", "companion", "source"}
    assert b"LanPaint_VideoMaskEditor" in media.objects[inputs["python"]["object_id"]]
    assert media.reads == [
        inputs["python"]["object_id"],
        inputs["companion"]["object_id"],
        inputs["source"]["object_id"],
    ]


@pytest.mark.parametrize("mismatch", ["payload", "manifest"])
def test_connected_client_fails_closed_on_workflow_hash_or_provenance_mismatch(tmp_path: Path, mismatch: str) -> None:
    compiled, result, media = _compile_result_with_managed_bundle(tmp_path)
    compilation = json.loads(Path(compiled["manifest_path"]).read_text(encoding="utf-8"))
    if mismatch == "payload":
        python_digest = next(row["object_id"] for row in result.outputs["managed_outputs"] if row["name"] == "python")
        media.objects[python_digest] = b"tampered-lanpaint-workflow"
    else:
        compilation["workflow"]["workflow.py"]["sha256"] = "0" * 64

    with pytest.raises(RuntimeError, match="digest|hash/provenance"):
        _retrieve_compiled_workflow(SimpleNamespace(media=media), result, compilation, tmp_path / "retrieved")


def test_interval_lists_cannot_certify_a_copied_non_media_candidate(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    candidate = tmp_path / "candidate.bin"
    source.write_bytes(b"source-bytes")
    candidate.write_bytes(source.read_bytes())
    preparation = prepare_request(_request(), asset_map={"source": str(source)})
    composition = compose_candidate(
        preparation=preparation,
        generated=candidate,
        source=source,
        out_dir=tmp_path / "composition",
        preservation_evidence={
            "unchanged_permissions": {
                "video": preparation["mask_schedule"]["video"]["protected_intervals"],
                "audio": preparation["mask_schedule"]["audio"]["protected_intervals"],
            }
        },
    )
    with pytest.raises(VerificationError, match="byte-identical|decodable media|protected_samples"):
        verify_candidate(preparation=preparation, composition=composition, source=source)


def test_composition_carries_provenance_and_decoded_protected_samples(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg is required for the media composition contract test")
    source = tmp_path / "source.mp4"
    generated = tmp_path / "generated.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=32x32:r=8", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=32x32:r=8", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(generated)],
        check=True,
    )
    preparation = prepare_request(_request(), asset_map={"source": str(source)})
    preparation["provenance"] = {
        "request_digest": preparation["request_digest"],
        "assets": preparation["assets"],
        "graph": {"compilation_digest": "graph-digest"},
    }
    composition = compose_candidate(preparation=preparation, generated=generated, source=source, out_dir=tmp_path / "composition")
    report = verify_candidate(preparation=preparation, composition=composition, source=source)
    assert report["preservation"]["status"] == "protected_sample_evidence"
    assert composition["provenance"]["graph"]["compilation_digest"] == "graph-digest"
    assert composition["preservation_evidence"]["protected_samples"]["video"]


def test_serialized_prepare_compile_canonical_run_compose_verify_with_bundle_assets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg is required for the serialized media contract test")

    from astrid.packs.h3_av.src.input_bundle import build_input_bundle, bundle_digest
    from astrid.packs.h3_av.src.request import normalize_request
    from astrid.packs.h3_av.executors.prepare.run import main as prepare_main
    from astrid.packs.h3_av.executors.compile.run import main as compile_main
    from astrid.packs.h3_av.executors.compose.run import main as compose_main
    from astrid.packs.h3_av.executors.verify.run import main as verify_main
    from astrid.packs.vibecomfy.executors.run.run import main as vibecomfy_run_main
    from astrid.packs.vibecomfy import production_engine
    from astrid.packs.vibecomfy import invocation_preflight

    caller = tmp_path / "caller"
    caller.mkdir()
    source = caller / "source.mp4"
    reference = caller / "reference.png"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=32x32:r=24", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=yellow:s=16x16", "-frames:v", "1", str(reference)],
        check=True,
    )
    request_value = {
        "version": 1,
        "operation": "continue",
        "source": {"asset": "source", "range": [0, 2]},
        "output": {"duration": 5},
        "content": {"prompt": "continue the source"},
        "changes": {
            "video": [{"during": [2, 5], "area": {"full_frame": True}, "action": "generate"}],
            "audio": [{"during": [2, 5], "action": "generate"}],
        },
        "references": [{"asset": "look", "purpose": "appearance"}],
        "overrides": {},
    }
    request = normalize_request(request_value)
    input_bundle = build_input_bundle(
        request,
        {"source": source, "look": reference},
        tmp_path / "input-bundle.zip",
    )
    request_path = tmp_path / "request.json"
    asset_map_path = tmp_path / "asset-map.json"
    preparation_path = tmp_path / "preparation.json"
    request_path.write_text(json.dumps(request_value), encoding="utf-8")
    asset_map_path.write_text(
        json.dumps({"source": str(source), "look": str(reference)}), encoding="utf-8"
    )

    assert prepare_main([
        "--request", str(request_path), "--input-bundle", str(input_bundle),
        "--out", str(preparation_path),
    ]) == 0
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    preparation["input_bundle_sha256"] = bundle_digest(input_bundle)
    preparation["provenance"] = {"request_digest": preparation["request_digest"], "assets": preparation["assets"]}
    preparation_path.write_text(json.dumps(preparation), encoding="utf-8")

    compilation_dir = tmp_path / "compile"
    assert compile_main([
        "--preparation", str(preparation_path), "--input-bundle", str(input_bundle),
        "--out", str(compilation_dir),
    ]) == 0
    compilation = json.loads((compilation_dir / "compilation.json").read_text(encoding="utf-8"))
    assert compilation["output_contract"]["graph_outputs"][0]["modality"] == "video"

    session = tmp_path / "session"
    input_dir = tmp_path / "comfy-input"
    session.mkdir()
    (session / "config.json").write_text(json.dumps({"input_directory": str(input_dir)}), encoding="utf-8")
    readiness_path = tmp_path / "readiness.json"
    readiness_path.write_text(json.dumps({"vibecomfy_session": {"session_dir": str(session)}}), encoding="utf-8")
    readiness_hash = "sha256:" + hashlib.sha256(readiness_path.read_bytes()).hexdigest()
    generated = tmp_path / "unused-generated.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=32x32:r=24", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(generated)],
        check=True,
    )

    def fake_canonical_engine(_workflow: Path, output_root: Path, **_kwargs: object):
        result = output_root / "engine-output" / "generated.mp4"
        result.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generated, result)
        return (result,)

    monkeypatch.setattr(invocation_preflight, "preflight_invocation", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(production_engine, "run_workflow_path", fake_canonical_engine)
    run_dir = tmp_path / "canonical-run"
    assert vibecomfy_run_main(
        [
            "run", "--python", str(compilation_dir / "workflow.py"),
            "--companion", str(compilation_dir / "workflow.vibe.json"),
            "--source", str(compilation_dir / "source.json"),
            "--managed-assets", str(compilation_dir / "managed-assets.zip"),
            "--output-contract", json.dumps(compilation["output_contract"]),
            "--task-identity", "asset-provenance-regression",
            "--readiness-profile-path", str(readiness_path),
            "--readiness-profile-hash", readiness_hash,
            "--out", str(run_dir),
        ]
    ) == 0
    run_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert run_manifest["kind"] == "vibecomfy.run"
    generated_path = run_dir / run_manifest["outputs"][0]["path"]

    shutil.rmtree(caller)
    compose_dir = tmp_path / "compose"
    assert compose_main(
        ["--preparation", str(preparation_path), "--generated", str(generated_path), "--input-bundle", str(input_bundle), "--out", str(compose_dir)]
    ) == 0
    composition = json.loads((compose_dir / "composition-manifest.json").read_text(encoding="utf-8"))
    portable_assets = [
        {key: value for key, value in row.items() if key != "path"}
        for row in preparation["assets"]
    ]
    assert composition["provenance"]["assets"] == portable_assets
    compose_manifest = json.loads((compose_dir / "manifest.json").read_text(encoding="utf-8"))
    candidate_path = compose_dir / compose_manifest["outputs"][0]["path"]

    verify_dir = tmp_path / "verify"
    assert verify_main(
        ["--preparation", str(preparation_path), "--composition", str(compose_dir / "composition-manifest.json"), "--candidate", str(candidate_path), "--input-bundle", str(input_bundle), "--out", str(verify_dir)]
    ) == 0
    verify_manifest = json.loads((verify_dir / "manifest.json").read_text(encoding="utf-8"))
    assert verify_manifest["kind"] == "h3_av_verify_result"
    assert verify_manifest["outputs"][0]["output_port"] == "verified_candidate"
