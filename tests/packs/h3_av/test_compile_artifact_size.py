from __future__ import annotations

import hashlib
import json
import base64
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
from banodoco_workspace_client.generated import WorkspaceClient as GeneratedWorkspaceClient
from astrid.core._shared.result_manifest import harvest_staged_outputs
from astrid.core.execution.generic_host import GenericPackHost
from astrid.core.execution.managed_tool_session import (
    CapabilityDescriptor,
    ManagedToolSession,
    SessionBinding,
)
from astrid.core.execution.executor.folder import load_folder_executor
from astrid.packs.h3_av.executors.compile.run import main as compile_executor_main
from astrid.packs.h3_av.orchestrators.transform.run import _retrieve_v2_workflow
from astrid.packs.h3_av.src.graph import (
    GraphBindingError,
    build_h3_graph_binding,
    validate_h3_graph_binding,
    validate_prepared_mask_references,
)
from astrid.packs.h3_av.src.masks import load_prepared_av_mask
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.h3_av.src.compile import _member_by_binding
from tests.packs.h3_av.test_integrated_graph_bundle import _prepared_fixture_a
from tests.packs.h3_av.test_request_contract import FIXTURE_DIGESTS, FIXTURES


_SETTLEMENT_LIMIT = 64 * 1024 * 1024
_FULL_A_VIDEO_SHAPE = [360, 576, 1024]
_FULL_A_AUDIO_SHAPE = [2, 720000]


class _ManagedMedia:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.reads: list[str] = []

    def read_bytes(self, object_id: str) -> bytes:
        self.reads.append(object_id)
        return self.objects[object_id]


@pytest.fixture(scope="module")
def full_a_compile(tmp_path_factory):
    cached_output = os.environ.get("ASTRID_T9_FULL_A_COMPILE_OUTPUT")
    if cached_output:
        output_root = Path(cached_output).expanduser().resolve(strict=True)
        preparation_path = output_root.parent.parent / "preparation.json"
        preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
        return preparation, output_root.parent, output_root
    tmp_path = tmp_path_factory.mktemp("full-resolution-a")
    small_preparation, _assets = _prepared_fixture_a(tmp_path)
    request = normalize_request(FIXTURES["A"]())
    asset_map = {
        str(row["asset"]): str(row["path"])
        for row in small_preparation["assets"]
    }
    preparation = prepare_request(
        request,
        asset_map=asset_map,
        width=1024,
        height=576,
        target_model_dimensions={"frames": 107, "height": 144, "width": 256},
    )
    assert preparation["request_digest"] == FIXTURE_DIGESTS["A"]
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(json.dumps(preparation, sort_keys=True), encoding="utf-8")
    attempt = tmp_path / "attempt"
    output_root = attempt / "outputs"
    compile_executor_main(["--preparation", str(preparation_path), "--out", str(output_root)])
    artifact = load_prepared_av_mask(output_root / "prepared-av-mask.json")
    assert artifact.to_manifest()["video"]["payload"]["shape"] == _FULL_A_VIDEO_SHAPE
    assert artifact.to_manifest()["audio"]["payload"]["shape"] == _FULL_A_AUDIO_SHAPE
    return preparation, attempt, output_root


def _managed_objects(output_root: Path) -> tuple[dict[str, bytes], list[dict[str, object]]]:
    objects: dict[str, bytes] = {}
    rows: list[dict[str, object]] = []
    for name, filename in (
        ("compilation", "compilation.json"),
        ("managed_assets", "managed-assets.zip"),
        ("graph_binding", "graph_binding.json"),
        ("graph", "graph.vibe.json"),
        ("prepared_artifact", "prepared-av-mask.json"),
    ):
        payload = (output_root / filename).read_bytes()
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        objects[digest] = payload
        rows.append(
            {
                "name": name,
                "object_id": digest,
                "digest": digest,
                "size": len(payload),
                "filename": filename,
                "role": "result" if name == "compilation" else "auxiliary",
            }
        )
    return objects, rows


def test_reference_binding_resolves_losslessly_and_recompiles_semantically(full_a_compile, tmp_path: Path) -> None:
    preparation, _attempt, output_root = full_a_compile
    binding = json.loads((output_root / "graph_binding.json").read_text(encoding="utf-8"))
    prepared_manifest = json.loads((output_root / "prepared-av-mask.json").read_text(encoding="utf-8"))
    artifact = load_prepared_av_mask(prepared_manifest)

    validate_prepared_mask_references(binding, prepared_manifest)
    validate_h3_graph_binding(binding)
    for stream in ("video", "audio"):
        reference = binding["inputs"]["masks"][stream]["delivery"]["payload"]
        payload = prepared_manifest[stream]["payload"]
        assert reference == {
            "kind": "h3_prepared_av_mask_reference",
            "managed_output": "prepared_artifact",
            "artifact_digest": artifact.artifact_digest,
            "member": f"{stream}.payload",
            "stream": stream,
            "payload_sha256": payload["sha256"],
            "encoding": payload["encoding"],
            "shape": payload["shape"],
            "length": payload["length"],
            "polarity": prepared_manifest[stream]["polarity"],
        }
        assert "data" not in reference
        assert binding["inputs"]["masks"][stream]["delivery"]["shape"] == payload["shape"]
        assert binding["inputs"]["masks"][stream]["delivery"]["polarity"] == prepared_manifest[stream]["polarity"]
        assert binding["inputs"]["masks"][stream]["delivery"]["clock"] == prepared_manifest[stream]["clock"]
        assert binding["inputs"]["masks"][stream]["delivery"]["coverage"] == prepared_manifest[stream]["coverage"]
        assert reference["payload_sha256"] == hashlib.sha256(base64.b64decode(payload["data"])).hexdigest()
    assert all(
        not isinstance(value, str) or len(value) < 100_000
        for value in _walk_values(binding)
    )

    compilation = json.loads((output_root / "compilation.json").read_text(encoding="utf-8"))
    members = _member_by_binding(compilation["managed_assets"]["manifest"])
    asset_members = {
        str(row["asset"]): members[str(row["asset"])]
        for row in preparation["assets"]
        if str(row["asset"]) in members
    }
    repeated = build_h3_graph_binding(
        preparation,
        asset_members=asset_members,
        mask_members={
            "video": members["prepared_video_mask"],
            "audio": members["prepared_audio_mask"],
        },
    )
    assert repeated["bundle_identity"] == binding["bundle_identity"]
    assert repeated["executable_graph"] == binding["executable_graph"]
    assert repeated["inputs"]["masks"] == binding["inputs"]["masks"]
    assert binding["prepared_artifact_digest"] == artifact.artifact_digest
    assert binding["delivery_domains"] == {
        "video": {"frames": 360, "height": 576, "width": 1024},
        "audio": {"channels": 2, "samples": 720000},
    }


def _walk_values(value):
    if isinstance(value, dict):
        for nested in value.values():
            yield from _walk_values(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_values(nested)
    else:
        yield value


def test_real_a_five_output_generated_settlement_stays_below_runtime_limit(full_a_compile) -> None:
    _preparation, attempt, output_root = full_a_compile
    executor_root = Path(__file__).resolve().parents[3] / "astrid/packs/h3_av/executors/compile"
    definition = load_folder_executor(executor_root)
    harvested = harvest_staged_outputs(
        output_root,
        definition=definition,
        declared_outputs=definition.outputs,
        values={"out": str(output_root)},
        require=True,
    )
    host = SimpleNamespace(client=GeneratedWorkspaceClient("http://runtime", "token", transport=lambda *_args: (200, {}, b'{"data":{},"receipt":{}}')))
    host.client.INLINE_SETTLEMENT_OUTPUTS = True
    host.client.upload_object = lambda *_args, **_kwargs: SimpleNamespace(digest="sha256:" + "0" * 64, size=0)
    typed = GenericPackHost._typed_outputs(host, SimpleNamespace(definition=definition), harvested, attempt)
    captured: list[tuple[str, str, bytes]] = []

    def transport(method, path, _headers, body):
        assert body is not None
        captured.append((method, path, body))
        return 200, {}, b'{"data":{},"receipt":{}}'

    host.client = GeneratedWorkspaceClient("http://runtime", "token", transport=transport)
    host.client.INLINE_SETTLEMENT_OUTPUTS = True
    host.client.upload_object = lambda *_args, **_kwargs: SimpleNamespace(digest="sha256:" + "0" * 64, size=0)
    uploaded = GenericPackHost._upload_outputs(
        host,
        typed,
        project_id="project",
        run_id="run",
        task_id="task",
        attempt_id="attempt",
        lease_id="lease",
        fence=1,
        runtime_epoch=1,
    )
    session = ManagedToolSession(manager_id="generic-pack-host:cpu")
    capability = CapabilityDescriptor(capability_id="h3_av.compile")
    binding = SessionBinding(
        session_id="session",
        runtime_instance_id="runtime-instance",
        process_birth_id="process-birth",
        endpoint="http://runtime",
        source_digest="sha256:" + "a" * 64,
        config_digest="sha256:" + "b" * 64,
        runtime_epoch=1,
    )
    session.open(capability=capability, binding=binding, adapter=object())
    token = session.admit(capability_id="h3_av.compile", invocation_id="invocation")
    managed_envelope = session.settle(
        token,
        result_evidence={
            "generation": token.generation,
            "binding_identity": list(token.binding_identity),
            "outputs": uploaded,
        },
    )
    result = {
        "returncode": 0,
        "capability_digest": "sha256:" + "c" * 64,
        "process_id": 12345,
        "process_evidence": {
            "attempt_id": "attempt",
            "fence": 1,
            "returncode": 0,
            "process_id": 12345,
        },
        "managed_tool_session": managed_envelope.to_dict(),
        "execution_guards": {
            "evidence": {"schema_version": 1, "status": "complete"},
            "deadline_seconds": 3600,
            "collection_seconds": 30,
            "warm_expectation": None,
            "evidence_budget": {"run_observed_bytes": 0, "cap_bytes": 67108864},
            "scratch_disposition": "cleanup_pending",
            "cleanup_path": str(attempt),
            "retained_owner": "generic-pack-host",
            "retained_bytes": 0,
            "storage_envelope": {"status": "within_bounds"},
        },
    }
    host.client.settle_attempt(
        "attempt",
        {
            "attempt_id": "attempt",
            "lease_id": "lease",
            "fence": 1,
            "runtime_epoch": 1,
            "outputs": uploaded,
            "effect": None,
            "result": result,
        },
        idempotency_key="settle-attempt-1",
    )

    assert len(captured) == 1
    method, path, body = captured[0]
    assert method == "POST"
    assert path.endswith("/v1/attempts/attempt/settle")
    decoded = json.loads(body)
    assert len(decoded["outputs"]) == 5
    assert sorted(row["name"] for row in decoded["outputs"]) == [
        "compilation", "graph", "graph_binding", "managed_assets", "prepared_artifact"
    ]
    assert len({row["name"] for row in decoded["outputs"]}) == 5
    assert len(body) < _SETTLEMENT_LIMIT
    metrics = {
        "method": method,
        "path": path,
        "serialized_bytes": len(body),
        "result_bytes": len(json.dumps(decoded["result"], separators=(",", ":")).encode("utf-8")),
        "outputs": {
            row["name"]: {
                "file_bytes": row["size"],
                "base64_bytes": len(row["data_base64"].encode("ascii")),
            }
            for row in decoded["outputs"]
        },
    }
    (output_root.parent / "settlement-metrics.json").write_text(
        json.dumps(metrics, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def test_managed_compilation_outputs_read_after_producer_scratch_cleanup(full_a_compile, tmp_path: Path) -> None:
    _preparation, _attempt, output_root = full_a_compile
    producer = tmp_path / "attempt"
    shutil.copytree(output_root.parent, producer)
    scratch_root = producer / "outputs"
    compilation = json.loads((scratch_root / "compilation.json").read_text(encoding="utf-8"))
    objects, rows = _managed_objects(scratch_root)
    result = SimpleNamespace(capability_id="h3_av.compile", outputs={"managed_outputs": rows}, raw_result={})
    # The managed object bytes above are independent of this producer tree.
    for item in scratch_root.iterdir():
        if item.is_file():
            item.unlink()
    shutil.rmtree(producer)
    descriptor = _retrieve_v2_workflow(
        SimpleNamespace(media=_ManagedMedia(objects)), result, compilation, tmp_path / "retrieved"
    )
    assert descriptor["filename"] == "graph.vibe.json"
    assert len(objects) == 5


def test_managed_readback_rejects_invalid_binding_identity_even_with_valid_file_hashes(full_a_compile, tmp_path: Path) -> None:
    _preparation, _attempt, source_root = full_a_compile
    producer = tmp_path / "outputs"
    shutil.copytree(source_root, producer)
    output_root = producer
    compilation = json.loads((output_root / "compilation.json").read_text(encoding="utf-8"))
    binding_path = output_root / "graph_binding.json"
    binding = json.loads(binding_path.read_text(encoding="utf-8"))
    binding["bundle_identity"] = "0" * 64
    binding_path.write_text(json.dumps(binding, sort_keys=True), encoding="utf-8")
    binding_bytes = binding_path.read_bytes()
    objects, rows = _managed_objects(output_root)
    binding_row = next(row for row in rows if row["name"] == "graph_binding")
    new_digest = "sha256:" + hashlib.sha256(binding_bytes).hexdigest()
    objects[new_digest] = binding_bytes
    binding_row.update(object_id=new_digest, digest=new_digest, size=len(binding_bytes))
    compilation["graph_binding"]["sha256"] = hashlib.sha256(binding_bytes).hexdigest()
    result = SimpleNamespace(capability_id="h3_av.compile", outputs={"managed_outputs": rows}, raw_result={})
    with pytest.raises(RuntimeError, match="semantic identity"):
        _retrieve_v2_workflow(
            SimpleNamespace(media=_ManagedMedia(objects)), result, compilation, tmp_path / "retrieved"
        )


def test_reference_rejections_cover_identity_member_hash_shape_encoding_and_polarity(full_a_compile) -> None:
    _preparation, _attempt, output_root = full_a_compile
    binding = json.loads((output_root / "graph_binding.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_root / "prepared-av-mask.json").read_text(encoding="utf-8"))
    changes = (
        ("artifact_digest", "0" * 64),
        ("member", "audio.payload"),
        ("payload_sha256", "0" * 64),
        ("shape", [1, 1]),
        ("encoding", "raw"),
        ("polarity", "white_preserve_black_edit"),
    )
    for field, value in changes:
        changed = json.loads(json.dumps(binding))
        changed["inputs"]["masks"]["video"]["delivery"]["payload"][field] = value
        with pytest.raises(GraphBindingError):
            validate_prepared_mask_references(changed, manifest)


@pytest.mark.parametrize("failure", ["missing_output", "missing_member", "tampered_payload", "valid_substitute"])
def test_managed_readback_rejects_missing_or_substituted_prepared_artifact(
    full_a_compile, tmp_path: Path, failure: str
) -> None:
    _preparation, _attempt, source_root = full_a_compile
    producer = tmp_path / "outputs"
    shutil.copytree(source_root, producer)
    compilation = json.loads((producer / "compilation.json").read_text(encoding="utf-8"))
    objects, rows = _managed_objects(producer)
    result = SimpleNamespace(capability_id="h3_av.compile", outputs={"managed_outputs": rows}, raw_result={})
    media = _ManagedMedia(objects)
    prepared_row = next(row for row in rows if row["name"] == "prepared_artifact")

    if failure == "missing_output":
        rows.remove(prepared_row)
    else:
        manifest_path = producer / "prepared-av-mask.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if failure == "missing_member":
            manifest["video"].pop("payload")
        elif failure == "tampered_payload":
            data = manifest["video"]["payload"]["data"]
            manifest["video"]["payload"]["data"] = ("A" if data[0] != "A" else "B") + data[1:]
        else:
            manifest["video"]["coverage"] = [[0, 359]]
            unsigned = {key: value for key, value in manifest.items() if key != "artifact_digest"}
            manifest["artifact_digest"] = hashlib.sha256(
                json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        payload = manifest_path.read_bytes()
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        objects[digest] = payload
        prepared_row.update(object_id=digest, digest=digest, size=len(payload))
        compilation["prepared_artifact"]["sha256"] = digest.removeprefix("sha256:")
        if failure == "valid_substitute":
            compilation["prepared_artifact"]["artifact_digest"] = manifest["artifact_digest"]

    with pytest.raises(RuntimeError):
        _retrieve_v2_workflow(
            SimpleNamespace(media=media), result, compilation, tmp_path / "retrieved"
        )
