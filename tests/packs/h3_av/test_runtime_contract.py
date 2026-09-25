from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import importlib
import zipfile
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.packs.h3_av.orchestrators.transform.run import (
    _generation_intent,
    _invoke,
    _materialize_output,
    _retrieve_compiled_workflow,
    _import_runtime_file,
)
from astrid.packs.h3_av.src.compile import compile_preparation
from astrid.packs.h3_av.src.compose import compose_candidate
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.h3_av.src.verify import VerificationError, verify_candidate
from astrid.packs.h3_av.src.input_bundle import (
    build_input_bundle, bundle_digest, materialize_input_bundle, resolve_preparation_assets,
)
from astrid.packs.vibecomfy.asset_manifest import AssetManifestError, read_archive


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


def test_generation_intent_comes_only_from_the_sealed_compilation_contract() -> None:
    compilation = {
        "capabilities": {
            "public_generation": {
                "modality": "video",
                "selectors": [{
                    "selector": "main-0",
                    "ordinal": 0,
                    "variant_key": "original",
                    "required": True,
                }],
            }
        }
    }
    intent = _generation_intent(compilation)
    assert intent["metadata"]["compiled_generation_contract"] is True
    assert intent["groups"][0]["selectors"] == compilation["capabilities"]["public_generation"]["selectors"]


def test_generation_intent_rejects_a_manifest_without_a_sealed_contract() -> None:
    with pytest.raises(RuntimeError, match="missing public_generation"):
        _generation_intent({"capabilities": {"output_contract": "muxed_av_full_timeline"}})


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


def test_protected_audio_witness_tolerates_aac_to_pcm_roundtrip(tmp_path: Path) -> None:
    """AAC source audio must verify after concat emits PCM in another container."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg is required for the media composition contract test")
    source = tmp_path / "source-32k-aac.mp4"
    generated = tmp_path / "generated-32k-aac.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=32x32:r=8", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=32000", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=32x32:r=8", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=32000", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(generated)],
        check=True,
    )
    preparation = prepare_request(_request(), asset_map={"source": str(source)})
    composition = compose_candidate(
        preparation=preparation,
        generated=generated,
        source=source,
        out_dir=tmp_path / "composition",
    )
    report = verify_candidate(preparation=preparation, composition=composition, source=source)

    audio_evidence = composition["preservation_evidence"]["protected_samples"]["audio"][0]
    assert audio_evidence["method"] == "ffmpeg-decoded-audio-similarity-v1"
    assert audio_evidence["similarity"] >= 0.985
    assert report["status"] == "verified"


def test_composition_normalizes_generated_working_resolution_to_source(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg is required for the media composition contract test")
    source = tmp_path / "source.mp4"
    generated = tmp_path / "generated.mp4"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=blue:s=64x64:r=8", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "color=c=red:s=32x32:r=8", "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(generated)],
        check=True,
    )
    preparation = prepare_request(_request(), asset_map={"source": str(source)})
    composition = compose_candidate(
        preparation=preparation,
        generated=generated,
        source=source,
        out_dir=tmp_path / "composition",
    )
    probe = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", composition["candidate"]["path"]],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )
    stream = probe["streams"][0]
    assert (stream["width"], stream["height"]) == (64, 64)


def test_input_bundle_contains_only_declared_source_refs_and_masks(tmp_path: Path):
    raw = _request().value
    raw["references"] = [{"asset": "reference", "purpose": "appearance"}]
    raw["changes"]["video"][0]["area"] = {"mask_asset": "region"}
    raw["changes"]["video"][0]["mask_asset"] = "temporal"
    raw["changes"]["audio"][0]["mask_asset"] = "audio"
    request = normalize_request(raw)
    assets = {}
    for name in ("source", "reference", "region", "temporal", "audio", "unused"):
        path = tmp_path / f"{name}.bin"
        path.write_bytes(name.encode())
        assets[name] = str(path)
    bundle = build_input_bundle(request, assets, tmp_path / "inputs.zip")
    paths, identities = materialize_input_bundle(request, bundle, tmp_path / "attempt")
    assert set(paths) == {"source", "reference", "region", "temporal", "audio"}
    assert all(Path(path).read_bytes() == name.encode() for name, path in paths.items())
    assert all("path" not in row for row in identities)
    preparation = {"request": request.value, "assets": identities, "input_bundle_sha256": bundle_digest(bundle)}
    preparation["assets"][0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="asset evidence"):
        resolve_preparation_assets(preparation, bundle, tmp_path / "compile")


def test_missing_dependency_stops_transform_before_any_import_or_submission(tmp_path: Path, monkeypatch):
    from astrid.packs.h3_av.orchestrators.transform import run as transform
    from unittest.mock import Mock

    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().value))
    asset_map = tmp_path / "asset-map.json"
    asset_map.write_text("{}")
    client = Mock()
    monkeypatch.setattr(transform.AstridClient, "open_from_launcher", lambda **kwargs: nullcontext(client))
    with pytest.raises(ValueError, match="needs a file in asset_map"):
        transform.run_transform(transform.build_parser().parse_args([
            "--request", str(request_path), "--asset-map", str(asset_map), "--out", str(tmp_path / "out"),
        ]))
    client.invoke_result.assert_not_called()
    client.media.import_file.assert_not_called()


def test_import_rejects_object_identity_different_from_uploaded_bytes(tmp_path: Path):
    path = tmp_path / "request.json"
    path.write_bytes(b"{}")
    client = SimpleNamespace(media=SimpleNamespace(import_file=lambda **kwargs: SimpleNamespace(
        ok=True, data={"object_id": "sha256:" + "0" * 64}
    )))
    with pytest.raises(RuntimeError, match="different digest"):
        _import_runtime_file(client, project="project", path=path, filename=path.name)


@pytest.mark.parametrize("mutation", ["payload", "traversal", "undeclared"])
def test_input_bundle_rejects_tampering_before_materialization(tmp_path: Path, mutation: str):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    bundle = build_input_bundle(_request(), {"source": str(source)}, tmp_path / "inputs.zip")
    resolved = read_archive(bundle)
    manifest = resolved.manifest
    member = manifest["assets"][0]["member"]
    payload = b"changed" if mutation == "payload" else b"source"
    if mutation == "traversal":
        member = "../escaped"
        manifest["assets"][0]["member"] = member
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr(member, payload)
        if mutation == "undeclared":
            archive.writestr("extra", b"undeclared")
    with pytest.raises(AssetManifestError):
        materialize_input_bundle(_request(), bundle, tmp_path / "attempt")
    assert not (tmp_path / "attempt").exists()


def _synthetic_av(path: Path, duration: float, *, color: str, muxed=True):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=32x32:r=24",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(duration), "-c:v", "libx264", "-pix_fmt", "yuv420p",
        *(["-c:a", "aac"] if muxed else ["-an"]), str(path),
    ], check=True)


@pytest.mark.parametrize("operation", ["continue", "edit", "generate"])
def test_transform_managed_handoffs_survive_removal_of_every_previous_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str,
):
    """Run the real H3 stages through admission/materialization; fake only CAS
    transport and GPU generation. No preceding directory survives a handoff.
    """
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg/ffprobe required for CPU AV regression")
    import yaml
    from astrid.core.execution.generic_host import GenericPackHost
    from astrid.packs.h3_av.orchestrators.transform import run as transform
    from astrid.sdk.invocation import _kernel_invoke

    caller = tmp_path / "caller"
    caller.mkdir()
    source = caller / "source.mp4"
    _synthetic_av(source, 2 if operation == "edit" else 1, color="blue")
    source_bytes = source.read_bytes()
    raw = _request().value
    raw["operation"] = operation
    if operation == "edit":
        raw["source"]["range"] = [0, 2]
    asset_map = {"source": str(source)}
    if operation == "generate":
        from PIL import Image
        raw["source"] = None
        raw["changes"] = {"video": [], "audio": []}
        raw["references"] = []
        raw["output"] = {"duration": 15}
        asset_map = {}
        for index in range(4):
            path = caller / f"reference-{index}.png"
            Image.new("RGB", (32, 32), (index * 50, 0, 0)).save(path)
            asset_map[path.name] = str(path)
            raw["references"].append({"asset": path.name, "purpose": "appearance"})
    (caller / "request.json").write_text(json.dumps(raw))
    (caller / "asset-map.json").write_text(json.dumps(asset_map))
    objects: dict[str, bytes] = {}
    calls = []
    attempts = []
    pack = Path(transform.__file__).resolve().parents[2]

    def settle(path, name, **extra):
        payload = Path(path).read_bytes()
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        objects[digest] = payload
        return {"name": name, "filename": Path(path).name, "object_id": digest,
                "digest": digest, "size": len(payload), **extra}

    class Media:
        def import_file(self, *, project, path, idempotency_key):
            assert project == "cpu-test"
            return SimpleNamespace(ok=True, data=settle(path, "input"))

        def read_bytes(self, digest):
            return objects[digest]

    class Tasks:
        def create(self, **kwargs):
            self.admitted = kwargs
            return SimpleNamespace(ok=True, data={"task_id": "task-cpu", "run_id": "run-cpu"})

    class Client:
        media = Media()
        tasks = Tasks()
        compilation = None

        def invoke_result(self, capability_id, *, inputs, **kwargs):
            calls.append((capability_id, inputs))
            attempt = tmp_path / f"attempt-{len(calls)}-{capability_id}"
            attempts.append(attempt)
            attempt.mkdir()
            out = attempt / "outputs"
            out.mkdir()
            if capability_id.startswith("h3_av."):
                stage = capability_id.split(".")[1]
                manifest = yaml.safe_load((pack / "executors" / stage / "executor.yaml").read_text())
                ports = [SimpleNamespace(**port) for port in manifest["inputs"]]
                capability = SimpleNamespace(id=capability_id, capability_type="executor", inputs=ports)
                _kernel_invoke(capability, kind="executor", project="cpu-test", inputs=inputs, outputs={}, _client=self)
                admission = self.tasks.admitted
                # This tests the actual SDK envelope and host materializer.
                host = GenericPackHost(pack_roots=[], client=SimpleNamespace(
                    get_object=lambda digest: objects["sha256:" + digest.removeprefix("sha256:")]
                ))
                localized = host._materialize_inputs(
                    {"spec": admission["spec"], "input_object_ids": admission["input_manifest"]}, attempt,
                    file_input_names=frozenset(port.name for port in ports if port.type == "file"),
                )
                assert "/Users/" not in json.dumps(inputs)
                assert all(isinstance(value, dict) and value.get("digest") for value in inputs.values())
                if stage == "prepare":
                    shutil.rmtree(caller)
                command = manifest["command"]
                bindings = {**localized, "out": str(out), "python_exec": "unused"}
                argv = [value.format_map(bindings) for value in command["argv"][3:]]
                for arg in command.get("input_args", []):
                    if arg["input"] in localized:
                        argv.extend([arg["flag"], str(localized[arg["input"]])])
                module = importlib.import_module(f"astrid.packs.h3_av.executors.{stage}.run")
                assert module.main(argv) == 0
                if stage == "prepare":
                    preparation = json.loads((out / "preparation.json").read_text())
                    assert all("path" not in row for row in preparation["assets"])
                if stage == "compile":
                    self.compilation = json.loads((out / "compilation.json").read_text())
                if stage in {"compose", "verify"}:
                    if operation == "generate":
                        assert "source" not in localized
                    else:
                        assert Path(localized["source"]).read_bytes() == source_bytes
                rows = [settle(Path(port["path_template"].format(out=out)), port["name"])
                        for port in manifest["outputs"]]
            elif capability_id == "vibecomfy.validate":
                # Workflow graph validation/model execution are outside this
                # transport regression; canonical bundle identity is real.
                assert set(inputs) == {"python", "companion", "source", "python_execution_consent"}
                assert inputs["python_execution_consent"] == "confirmed"
                rows = []
            else:
                assert capability_id == "vibecomfy.run"
                if operation in {"continue", "generate"}:
                    duration = (self.compilation["capabilities"]["generation_timing"]["raw_frames"] / 24
                                if operation == "generate" else
                                self.compilation["continuation_timing"]["expected_graph_output_duration"])
                    generated = out / "generated.mp4"
                    _synthetic_av(generated, duration, color="red")
                    rows = [settle(generated, "video", media_type="video/mp4")]
                else:
                    generated = out / "generated.mp4"
                    _synthetic_av(generated, 2, color="red", muxed=False)
                    audio = out / "generated.wav"
                    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                                    "sine=frequency=880:sample_rate=48000", "-t", "2", str(audio)], check=True)
                    rows = [settle(generated, "video", media_type="video/mp4"),
                            settle(audio, "audio", media_type="audio/wav")]
            shutil.rmtree(attempt)
            return SimpleNamespace(ok=True, capability_id=capability_id, outputs={"artifacts": rows},
                                   raw_result={}, kernel_task_id="task-cpu", kernel_run_id="run-cpu", kernel_attempt_id="attempt-cpu")

    client = Client()
    monkeypatch.setattr(transform.AstridClient, "open_from_launcher", lambda **kwargs: nullcontext(client))
    result = transform.run_transform(transform.build_parser().parse_args([
        "--request", str(caller / "request.json"), "--asset-map", str(caller / "asset-map.json"),
        "--out", str(tmp_path / "parent"), "--project", "cpu-test",
    ]))
    assert result["status"] == "verified"
    assert Path(result["candidate"]).is_file()
    assert Path(result["final_receipt"]).is_file()
    assert not caller.exists() and all(not attempt.exists() for attempt in attempts)
    assert [name for name, _ in calls] == ["h3_av.prepare", "h3_av.compile", "vibecomfy.validate",
                                         "vibecomfy.run", "h3_av.compose", "h3_av.verify"]
    call_inputs = {name: inputs for name, inputs in calls}
    # VibeComfy's source port is workflow provenance, not the source video.
    assert call_inputs["vibecomfy.run"]["source"]["filename"] == "source.json"
    intent = call_inputs["vibecomfy.run"]["generation_intent"]
    assert intent["groups"] == [{
        "group_key": "main",
        "selectors": client.compilation["capabilities"]["public_generation"]["selectors"],
    }]
    assert len(intent["groups"][0]["selectors"]) == 1
    assert intent["metadata"]["h3_av"]["graph"]["compilation_digest"] == client.compilation["compilation_digest"]
    assert ("source" in call_inputs["h3_av.compose"]) == (operation != "generate")
    assert ("source" in call_inputs["h3_av.verify"]) == (operation != "generate")
    report = json.loads(Path(result["verification"]).read_text())
    if operation == "generate":
        composition = json.loads(Path(result["composition"]).read_text())
        assert composition["coverage"]["candidate"]["video"]["frames"] == 360
        assert composition["coverage"]["candidate"]["requested_duration"] == 15
        assert composition["source"] is None
    else:
        assert report["preservation"]["status"] == "protected_sample_evidence"
    # Relocation cannot weaken the candidate hash check.
    composition = json.loads(Path(result["composition"]).read_text())
    preparation = json.loads(Path(result["preparation"]).read_text())
    Path(result["candidate"]).write_bytes(b"tampered")
    with pytest.raises(VerificationError, match="digest"):
        verify_candidate(preparation=preparation, composition=composition, candidate=result["candidate"])
