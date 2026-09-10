"""CPU composition proof for the typed Astrid image-generation admission.

This is deliberately a CPU substitute for the generator backend.  It keeps the
real Runtime daemon, GenericPackHost command boundary, HC-04 parameter binding,
lease/fence path, output harvesting, and CAS settlement.  It does not claim
native VibeComfy or provider readiness; those remain separate acceptance gates.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path

import pytest

RUNTIME_ROOT = Path(
    os.environ.get("BANODOCO_RUNTIME_CHECKOUT")
    or "/Users/hannahomalley/Documents/Codex/2026-09-09/can-you-see-the-poms-skills/work/astrid-prep/repos/Runtime"
).resolve()
sys.path.insert(0, str(RUNTIME_ROOT))

from banodoco_workspace_client import WorkspaceClient  # noqa: E402
from runtime_protocol.daemon import RuntimeDaemon  # noqa: E402

from astrid.core.execution.generic_host import GenericPackHost, HostError, RuntimeProtocolClient  # noqa: E402


_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="


def _fixture_pack(root: Path) -> Path:
    pack = root / "typed-image-cpu"
    executor = pack / "executors" / "generate_image"
    executor.mkdir(parents=True)
    (pack / "pack.yaml").write_text(
        "schema_version: 1\n"
        "id: typed_image_cpu\n"
        "name: Typed Image CPU Fixture\n"
        "version: 1.0\n"
        "capabilities: [generate_image]\n"
        "content:\n  executors: executors\n",
        encoding="utf-8",
    )
    script = f"""
import base64, hashlib, json, sys
from pathlib import Path
envelope = json.loads(sys.argv[1])
params = envelope['spec']['params']
bound = {{'model': sys.argv[3], 'mode': sys.argv[4], 'execution': sys.argv[5], 'prompt': sys.argv[6], 'count': int(sys.argv[7]), 'seed': int(sys.argv[8]), 'size': sys.argv[9]}}
assert envelope['capability_id'] == 'generation.generate_image'
assert params == {{'execution': 'cloud', 'mode': 't2i', 'model': 'z-image', 'prompt': 'cpu proof', 'count': 2, 'seed': 77, 'size': '1536x1024'}}
assert bound == params
out = Path(sys.argv[2])
(out / 'images').mkdir(parents=True, exist_ok=True)
image_bytes = base64.b64decode('{_PNG}')
images = [out / 'images' / 'cpu-0.png', out / 'images' / 'cpu-1.png']
for image in images:
    image.write_bytes(image_bytes + bytes([images.index(image)]))
request = out / 'request.json'
request.write_text(json.dumps({{'capability_id': envelope['capability_id'], 'params': params}}, sort_keys=True), encoding='utf-8')
def descriptor(name, path, ordinal=0, primary=False):
    data = path.read_bytes()
    return {{'name': name, 'path': str(path.relative_to(out)), 'content_hash': 'sha256:' + hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'ordinal': ordinal, 'is_primary': primary}}
image_entries = [descriptor('generated_images', image, ordinal=index, primary=index == 0) for index, image in enumerate(images)]
image_group = {{'name': 'generated_images', 'artifact_type': 'image/png', 'path': 'images', 'entries': [{{**{{key: value for key, value in entry.items() if key != 'path'}}, 'path': Path(entry['path']).name}} for entry in image_entries]}}
(out / 'manifest.json').write_text(json.dumps({{'outputs': [image_group, descriptor('request_receipt', request, ordinal=2)]}}, sort_keys=True), encoding='utf-8')
"""
    (executor / "executor.yaml").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "generation.generate_image",
                "name": "Generate Image (CPU substitute)",
                "kind": "external",
                "version": "2.0",
                "inputs": [
                    {
                        "name": "task_spec_json",
                        "required": True,
                        "type": "string",
                    },
                    {"name": "model", "required": True, "type": "string"},
                    {"name": "mode", "required": True, "type": "string"},
                    {"name": "execution", "required": True, "type": "string"},
                    {"name": "prompt", "required": True, "type": "string"},
                    {"name": "count", "default": "1", "required": False, "type": "integer"},
                    {"name": "seed", "default": "", "required": False, "type": "integer"},
                    {"name": "size", "default": "", "required": False, "type": "string"},
                ],
                "command": {
                    "argv": [
                        "{python_exec}",
                        "-c",
                        script,
                        "{task_spec_json}",
                        "{out}",
                        "{model}",
                        "{mode}",
                        "{execution}",
                        "{prompt}",
                        "{count}",
                        "{seed}",
                        "{size}",
                    ]
                },
                "outputs": [
                    {
                        "name": "generated_images",
                        "type": "file",
                        "path_template": "{out}/images/cpu-0.png",
                        "artifact_type": "image/png",
                    },
                    {
                        "name": "request_receipt",
                        "type": "file",
                        "path_template": "{out}/request.json",
                        "artifact_type": "application/json",
                    },
                ],
                "metadata": {
                    "resource_keys": ["cpu"],
                    "estimated_scratch_bytes": 1024 * 1024,
                    "estimated_output_bytes": 1024,
                    "hc04_param_ports": [
                        "mode",
                        "prompt",
                        "model",
                        "execution",
                        "count",
                        "seed",
                        "size",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    return pack


def _registered_image_executor_fixture(
    root: Path,
    *,
    manifest_name: str = "generate_image",
    oversized_output: bool = False,
) -> Path:
    """Copy the registered image manifest with a deterministic CPU backend.

    The child still runs the production ``generate_image.run`` command. The
    fixture wrapper uses the production Fal backend with only its HTTP
    transport substituted, so no provider request leaves the test process.
    """
    pack = root / "typed_image_cpu"
    executor = pack / "executors" / "generate_image"
    executor.mkdir(parents=True)
    (pack / "__init__.py").write_text("", encoding="utf-8")
    (pack / "pack.yaml").write_text(
        "schema_version: 1\n"
        "id: typed_image_cpu\n"
        "name: Typed Image CPU Transport Fixture\n"
        "version: 1.0\n"
        "capabilities: [generate_image]\n"
        "content:\n  executors: executors\n",
        encoding="utf-8",
    )
    definition = json.loads(
        (
            Path(__file__).resolve().parents[2]
            / f"astrid/packs/generation/executors/{manifest_name}/executor.yaml"
        ).read_text(encoding="utf-8")
    )
    definition["kind"] = "external"
    definition["command"]["argv"][2] = "typed_image_cpu.runtime"
    definition["isolation"] = {"mode": "subprocess", "network": False}
    metadata = dict(definition["metadata"])
    metadata.pop("env", None)
    metadata.pop("network_policy", None)
    metadata["adapter_family"] = "cpu"
    if manifest_name == "generate_image":
        # The broad fixture is retained for the legacy composition proof.  The
        # dedicated bounded manifest must keep its production estimates.
        metadata["estimated_scratch_bytes"] = 8 * 1024 * 1024
        metadata["estimated_output_bytes"] = 64 * 1024 * 1024
    definition["metadata"] = metadata
    definition.pop("scoped_configs", None)
    (executor / "executor.yaml").write_text(
        json.dumps(definition), encoding="utf-8"
    )
    (pack / "runtime.py").write_text(
        f"""
import base64
import json
import os
import sys

from astrid.core.generation.backends.fal import FalBackend
from astrid.core.util.http import HttpClient
from astrid.packs.generation.executors.generate_image import run as image_run

_PNG = base64.b64decode({_PNG!r})
_OVERSIZED_OUTPUT = {oversized_output!r}
_RESULT = _PNG


def _transport(request):
    global _RESULT
    url = request.full_url if hasattr(request, \"full_url\") else str(request)
    method = request.method if hasattr(request, \"method\") else \"GET\"
    if method == \"POST\" and \"queue.fal.run\" in url:
        payload = json.loads((request.data or b\"{{}}\").decode())
        image_urls = payload.get(\"image_urls\")
        refs = image_urls if isinstance(image_urls, list) else [payload.get(\"image_url\", \"\")]
        assert refs and all(isinstance(ref, str) for ref in refs)
        assert all(ref.startswith(\"data:image/png;base64,\") for ref in refs)
        assert all(base64.b64decode(ref.split(\",\", 1)[1]) == _PNG for ref in refs)
        _RESULT = b"x" * (64 * 1024 * 1024 + 1) if _OVERSIZED_OUTPUT else _PNG
        return 200, json.dumps({{
            \"request_id\": \"cpu-fal-request\",
            \"status_url\": \"https://queue.fal.run/status/cpu-fal-request\",
            \"response_url\": \"https://queue.fal.run/response/cpu-fal-request\",
        }}).encode()
    if url.endswith(\"/status/cpu-fal-request\"):
        return 200, b\"{{\\\"status\\\":\\\"COMPLETED\\\"}}\"
    if url.endswith(\"/response/cpu-fal-request\"):
        return 200, b\"{{\\\"images\\\":[{{\\\"url\\\":\\\"https://fal.media/cpu-result.png\\\"}}]}}\"
    if \"fal.media/cpu-result.png\" in url:
        return 200, _RESULT
    raise AssertionError(f\"unexpected CPU Fal transport request: {{method}} {{url}}\")


class _Registry:
    def create(self, backend_id, **kwargs):
        assert backend_id == \"cloud\"
        os.environ[\"FAL_KEY\"] = \"cpu-test-key\"
        return FalBackend(client=HttpClient(transport=_transport))


image_run.load_default_generation_backend_registry = lambda: _Registry()


if __name__ == \"__main__\":
    raise SystemExit(image_run.main(sys.argv[1:]))
""",
        encoding="utf-8",
    )
    return pack


def test_typed_image_admission_crosses_runtime_host_and_cas(tmp_path: Path) -> None:
    pack = _fixture_pack(tmp_path)
    daemon = RuntimeDaemon(
        tmp_path / "realm",
        support_root=tmp_path / "support",
        production_worker_credentials=True,
    ).start()
    host = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        owner.handshake("typed-image-cpu-test", "0.1.0", ["projects:read", "worker:execute"])
        client = RuntimeProtocolClient(daemon.endpoint, daemon.token)
        probe = GenericPackHost(pack_roots=[pack])
        record = probe.discover()[0]
        assert record.id == "generation.generate_image"

        host = GenericPackHost(
            pack_roots=[pack],
            client=client,
            executor_id="typed-image-cpu-host",
        )
        host.discover()
        host.preflight()
        assert host.capabilities[record.id].ready
        registration = host.register()
        assert registration["registration"].executor_id == "typed-image-cpu-host"

        project = owner.create_project(
            "Typed image CPU", slug="typed-image-cpu", idempotency_key="typed-image-project"
        )
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=[],
            project_id=project.project_id,
            idempotency_key="typed-image-task",
            spec={
                "family": "generation.generate_image",
                "params": {
                    "execution": "cloud",
                    "mode": "t2i",
                    "model": "z-image",
                    "prompt": "cpu proof",
                    "count": 2,
                    "seed": 77,
                    "size": "1536x1024",
                },
                "output_policy": {},
            },
            storage_estimate={"scratch_bytes": 1024 * 1024, "output_bytes": 2 * 1024},
        )
        settled = host.run(once=True)
        assert len(settled) == 1 and settled[0].state == "succeeded"
        completed = owner.get_task(task.task_id)
        assert completed.state == "succeeded"
        outputs = completed.result["outputs"]
        assert [output["name"] for output in outputs].count("generated_images") == 2
        assert [output["name"] for output in outputs].count("request_receipt") == 1

        manifest_output = next(output for output in outputs if output["name"] == "request_receipt")
        manifest = json.loads(owner.get_object(manifest_output["digest"]).data)
        assert manifest == {
            "capability_id": "generation.generate_image",
            "params": {
                "count": 2,
                "execution": "cloud",
                "mode": "t2i",
                "model": "z-image",
                "prompt": "cpu proof",
                "seed": 77,
                "size": "1536x1024",
            },
        }
        image_outputs = [output for output in outputs if output["name"] == "generated_images"]
        assert [owner.get_object(output["digest"]).data for output in image_outputs] == [
            base64.b64decode(_PNG) + b"\x00",
            base64.b64decode(_PNG) + b"\x01",
        ]
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()


@pytest.mark.parametrize(
    ("manifest_name", "expected_capability", "model", "mode"),
    [
        ("generate_image", "generation.generate_image", "z-image", "i2i"),
        ("generate_image_cloud_i2i", "generation.generate_image_cloud_i2i", "z-image", "i2i"),
        ("generate_image_edit", "generation.generate_image_edit", "qwen-image-edit-2511", "edit"),
    ],
)
def test_registered_image_executor_consumes_cas_image_and_cleans_attempt(
    tmp_path: Path,
    manifest_name: str,
    expected_capability: str,
    model: str,
    mode: str,
) -> None:
    pack = _registered_image_executor_fixture(tmp_path, manifest_name=manifest_name)
    daemon = RuntimeDaemon(
        tmp_path / "realm",
        support_root=tmp_path / "support",
        production_worker_credentials=True,
    ).start()
    host = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        owner.handshake(
            "typed-image-registered-test",
            "0.1.0",
            [
                "projects:read",
                "projects:write",
                "objects:read",
                "objects:write",
                "worker:execute",
            ],
        )
        client = RuntimeProtocolClient(daemon.endpoint, daemon.token)
        host = GenericPackHost(
            pack_roots=[pack],
            client=client,
            executor_id="typed-image-registered-host",
        )
        record = host.discover()[0]
        assert record.id == expected_capability
        host.preflight()
        assert host.capabilities[record.id].ready
        registration = host.register()
        assert registration["registration"].executor_id == "typed-image-registered-host"
        assert registration["capabilities"][0]["estimated_scratch_bytes"] > 0
        assert registration["capabilities"][0]["estimated_output_bytes"] > 0

        project = owner.create_project(
            "Typed registered image",
            slug="typed-registered-image",
            idempotency_key="registered-project",
        )
        source = tmp_path / "source.png"
        source.write_bytes(base64.b64decode(_PNG))
        source_row = owner.ingest_project_object(
            project.project_id,
            source.read_bytes(),
            media_type="image/png",
            filename="source.png",
            idempotency_key="registered-source",
        )
        source_id = str(
            getattr(source_row, "object_id", None)
            or getattr(source_row, "digest")
        )
        params = {
            "execution": "cloud",
            "mode": mode,
            "model": model,
            "prompt": "cpu i2i proof" if mode == "i2i" else "cpu edit proof",
            "count": 1,
            "seed": 11,
            "size": "1024x1024",
            "image_ref": {
                "digest": source_id,
                "filename": "source.png",
                "media_type": "image/png",
            },
        }
        if mode == "i2i":
            params["strength"] = 0.5
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=[source_id],
            project_id=project.project_id,
            idempotency_key="registered-task",
            spec={
                "family": expected_capability,
                "params": params,
                "output_policy": {},
            },
            storage_estimate={
                "scratch_bytes": record.estimated_scratch_bytes,
                "output_bytes": record.estimated_output_bytes,
            },
        )
        settled = host.run(once=True)
        assert len(settled) == 1 and settled[0].state == "succeeded"
        completed = owner.get_task(task.task_id)
        assert completed.state == "succeeded"
        outputs = completed.result["outputs"]
        assert any(output["name"] == "generated_images" for output in outputs)
        image_output = next(output for output in outputs if output["name"] == "generated_images")
        image_bytes = owner.get_object(image_output["digest"]).data
        assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        # ``generate_image.run`` embeds the submitted prompt after the real
        # Fal backend returns; the transport also checked the staged CAS bytes
        # in the request's data URI before returning this result.
        assert b"astrid_prompt" in image_bytes
        assert (b"cpu i2i proof" if mode == "i2i" else b"cpu edit proof") in image_bytes
        cleanup_path = completed.result["execution_guards"]["cleanup_path"]
        assert not Path(cleanup_path).exists()
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()


@pytest.mark.parametrize("failure", ["oversized_input", "oversized_output", "scope", "estimate"])
def test_registered_qwen_edit_failure_is_terminal_and_does_not_settle(
    tmp_path: Path,
    failure: str,
) -> None:
    pack = _registered_image_executor_fixture(
        tmp_path,
        manifest_name="generate_image_edit",
        oversized_output=failure == "oversized_output",
    )
    daemon = RuntimeDaemon(
        tmp_path / "realm",
        support_root=tmp_path / "support",
        production_worker_credentials=True,
    ).start()
    host = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        owner.handshake(
            "typed-image-qwen-failure-test",
            "0.1.0",
            [
                "projects:read",
                "projects:write",
                "objects:read",
                "objects:write",
                "worker:execute",
            ],
        )
        client = RuntimeProtocolClient(daemon.endpoint, daemon.token)
        host = GenericPackHost(
            pack_roots=[pack],
            client=client,
            executor_id="typed-image-qwen-failure-host",
        )
        record = host.discover()[0]
        host.preflight()
        host.register()
        project = owner.create_project(
            "Typed Qwen failure",
            slug=f"typed-qwen-failure-{failure}",
            idempotency_key=f"qwen-failure-project-{failure}",
        )
        source_bytes = (
            b"x" * (512_000 + 1)
            if failure == "oversized_input"
            else base64.b64decode(_PNG)
        )
        source_row = owner.ingest_project_object(
            project.project_id,
            source_bytes,
            media_type="image/png",
            filename="source.png",
            idempotency_key=f"qwen-failure-source-{failure}",
        )
        source_id = str(
            getattr(source_row, "object_id", None)
            or getattr(source_row, "digest")
        )
        params: dict[str, object] = {
            "execution": "cloud",
            "mode": "edit",
            "model": "qwen-image-edit-2511",
            "prompt": "qwen failure proof",
            "count": 1,
            "seed": 11,
            "size": "1024x1024",
            "image_ref": {
                "digest": source_id,
                "filename": "source.png",
                "media_type": "image/png",
            },
        }
        if failure == "scope":
            params["model"] = "qwen-image-edit"
        estimate = {
            "scratch_bytes": record.estimated_scratch_bytes,
            "output_bytes": record.estimated_output_bytes,
        }
        if failure == "estimate":
            estimate["output_bytes"] += 1
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=[source_id],
            project_id=project.project_id,
            idempotency_key=f"qwen-failure-task-{failure}",
            spec={
                "family": record.id,
                "params": params,
                "output_policy": {},
            },
            storage_estimate=estimate,
        )
        with pytest.raises(HostError):
            host.run(once=True)
        failed = owner.get_task(task.task_id)
        assert failed.state == "failed"
        assert not failed.result.get("outputs", [])
        assert not getattr(host, "_active_processes", {})
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()
