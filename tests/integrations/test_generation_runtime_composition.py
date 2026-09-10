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
import socket
import ssl
import subprocess
import sys
import threading
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlsplit

import pytest

RUNTIME_ROOT = Path(
    os.environ.get("BANODOCO_RUNTIME_CHECKOUT")
    or "/Users/hannahomalley/Documents/Codex/2026-09-09/can-you-see-the-poms-skills/work/astrid-prep/repos/Runtime"
).resolve()
sys.path.insert(0, str(RUNTIME_ROOT))

from banodoco_workspace_client import WorkspaceClient  # noqa: E402
from runtime_protocol.daemon import RuntimeDaemon  # noqa: E402

from astrid.core.execution.generic_host import GenericPackHost, HostError, RuntimeProtocolClient  # noqa: E402
from astrid.core.execution.network_broker import _BrokerHandler  # noqa: E402


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
    oversized_output_index: int | None = None,
    preserve_production_metadata: bool = False,
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
    if manifest_name == "generate_image" and not preserve_production_metadata:
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
_OVERSIZED_OUTPUT_INDEX = {0 if oversized_output else oversized_output_index!r}
_CALL_INDEX = 0
_RESULT = _PNG


def _transport(request):
    global _CALL_INDEX, _RESULT
    url = request.full_url if hasattr(request, \"full_url\") else str(request)
    method = request.method if hasattr(request, \"method\") else \"GET\"
    if method == \"POST\" and \"queue.fal.run\" in url:
        payload = json.loads((request.data or b\"{{}}\").decode())
        image_urls = payload.get(\"image_urls\")
        refs = image_urls if isinstance(image_urls, list) else [payload.get(\"image_url\", \"\")]
        if any(ref for ref in refs):
            assert all(isinstance(ref, str) for ref in refs)
            assert all(ref.startswith(\"data:image/png;base64,\") for ref in refs)
            assert all(base64.b64decode(ref.split(\",\", 1)[1]) == _PNG for ref in refs)
        else:
            assert payload[\"prompt\"] == \"cpu t2i proof\"
            assert payload[\"seed\"] in (19, 20)
            assert payload[\"num_inference_steps\"] == 28
            assert payload[\"image_size\"] == \"1536x1024\"
        _RESULT = b"x" * (64 * 1024 * 1024 + 1) if _CALL_INDEX == _OVERSIZED_OUTPUT_INDEX else _PNG
        _CALL_INDEX += 1
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


def test_production_t2i_command_runs_through_host_broker_http_substitute(tmp_path: Path) -> None:
    """Run the shipped command/manifest with only upstream HTTP substituted."""
    generation_root = Path(__file__).resolve().parents[2] / "astrid/packs/generation"
    original_forward = _BrokerHandler._forward_http
    png = base64.b64decode(_PNG)

    def fake_forward(handler, line, headers):
        method, target, _version = line.split(" ", 2)
        if "queue.fal.run" in target:
            assert headers.get("authorization") == "Key cpu-test-key"
        if method == "POST":
            body = json.dumps(
                {
                    "request_id": "broker-fal-request",
                    "status_url": "https://queue.fal.run/status/broker-fal-request",
                    "response_url": "https://queue.fal.run/response/broker-fal-request",
                }
            ).encode()
        elif "/status/broker-fal-request" in target:
            body = b'{"status":"COMPLETED"}'
        elif "/response/broker-fal-request" in target:
            body = b'{"images":[{"url":"https://fal.media/cpu-result.png"}]}'
        elif "fal.media" in target:
            body = png
        else:
            handler._response(HTTPStatus.NOT_FOUND, b"unknown broker fixture route")
            return
        handler._response(HTTPStatus.OK, body)

    class ProductionHost(GenericPackHost):
        def _child_environment(self, record, attempt, **kwargs):
            env, secrets = super()._child_environment(record, attempt, **kwargs)
            hook_root = attempt / ".astrid-network-hook"
            patch_module = hook_root / "t2i_http_fixture.py"
            patch_module.write_text(
                """
import base64
import json
import os
import socket
from http.client import HTTPResponse
from urllib.parse import urlsplit

from astrid.core.generation.backends import fal as fal_module
from astrid.core.util.http import HttpClient

_PNG = __PNG__


def _transport(request):
    target = request.full_url
    parsed = urlsplit(target)
    if request.method == "POST":
        payload = json.loads((request.data or b"{}").decode())
        assert parsed.hostname == "queue.fal.run"
        assert request.get_header("Authorization") == "Key cpu-test-key"
        assert payload["prompt"] == "broker t2i proof"
        assert payload["seed"] in (19, 20)
        assert payload["num_inference_steps"] == 28
        assert payload["image_size"] == "1536x1024"
    proxy = urlsplit(os.environ["ASTRID_BROKER_PROXY"])
    with socket.create_connection((proxy.hostname, proxy.port), timeout=5) as connection:
        body = request.data or b""
        request_headers = "".join(
            f"{name}: {value}\\r\\n"
            for name, value in request.header_items()
            if name.lower() not in {"host", "content-length", "connection"}
        )
        wire = (
            f"{request.method} {target} HTTP/1.1\\r\\n"
            f"Host: {parsed.netloc}\\r\\n"
            f"Content-Length: {len(body)}\\r\\n"
            f"{request_headers}"
            "Connection: close\\r\\n\\r\\n"
        ).encode() + body
        connection.sendall(wire)
        response = HTTPResponse(connection)
        response.begin()
        response_body = response.read()
        if parsed.hostname != "fal.media":
            assert response_body.startswith(b"{"), (response.status, response_body)
        return response.status, response_body


fal_module.default_client = lambda: HttpClient(transport=_transport)
""".replace("__PNG__", repr(png)),
                encoding="utf-8",
            )
            (hook_root / "sitecustomize.py").write_text(
                "from astrid.core.execution.network_policy import install_from_environment\n"
                "install_from_environment()\n"
                "import t2i_http_fixture\n",
                encoding="utf-8",
            )
            return env, secrets

    _BrokerHandler._forward_http = fake_forward
    daemon = RuntimeDaemon(
        tmp_path / "realm",
        support_root=tmp_path / "support",
        production_worker_credentials=True,
    ).start()
    host = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        owner.handshake(
            "production-t2i-command-test",
            "0.1.0",
            ["projects:read", "projects:write", "objects:read", "objects:write", "worker:execute"],
        )
        client = RuntimeProtocolClient(daemon.endpoint, daemon.token)
        host = ProductionHost(
            pack_roots=[generation_root],
            client=client,
            executor_id="production-t2i-command-host",
            credential_source={"FAL_KEY": "cpu-test-key"},
        )
        host.discover()
        record = host.capabilities["generation.generate_image"]
        assert record.definition.kind == "built_in"
        assert record.definition.command.argv[2:5] == (
            "astrid.packs.generation.executors.generate_image.run",
            "--model",
            "{model}",
        )
        assert record.definition.isolation.network is True
        assert record.definition.metadata["fixed_inputs"] == {"mode": "t2i", "execution": "cloud"}
        host.preflight("generation.generate_image")
        record = host.capabilities["generation.generate_image"]
        assert record.ready
        host.register()
        project = owner.create_project(
            "Production t2i command",
            slug="production-t2i-command",
            idempotency_key="production-t2i-project",
        )
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=[],
            project_id=project.project_id,
            idempotency_key="production-t2i-task",
            spec={
                "family": record.id,
                "params": {
                    "execution": "cloud",
                    "mode": "t2i",
                    "model": "flux-dev",
                    "prompt": "broker t2i proof",
                    "count": 2,
                    "seed": 19,
                    "steps": 28,
                    "size": "1536x1024",
                },
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
        images = [output for output in completed.result["outputs"] if output["name"] == "generated_images"]
        assert len(images) == 2
        assert all(owner.get_object(output["digest"]).data.startswith(b"\x89PNG") for output in images)
        evidence = completed.result["network_evidence"]
        assert any(event["kind"] == "broker_route" and event["allowed"] for event in evidence["events"])
        assert not Path(completed.result["execution_guards"]["cleanup_path"]).exists()
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()
        _BrokerHandler._forward_http = original_forward


@pytest.mark.parametrize("oversized_output_index", [None, 0, 1])
def test_production_t2i_command_uses_https_connect_and_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    oversized_output_index: int | None,
) -> None:
    """Exercise the shipped command through the broker's real CONNECT path."""
    import astrid.core.execution.network_broker as broker_module

    generation_root = Path(__file__).resolve().parents[2] / "astrid/packs/generation"
    png = base64.b64decode(_PNG)
    cert_dir = tmp_path / "provider-cert"
    cert_dir.mkdir()
    cert_path = cert_dir / "provider.pem"
    key_path = cert_dir / "provider.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key_path), "-out", str(cert_path), "-days", "1",
            "-subj", "/CN=queue.fal.run",
            "-addext", "subjectAltName=DNS:queue.fal.run,DNS:fal.media",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tls_listener = socket.socket()
    tls_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tls_listener.bind(("127.0.0.1", 0))
    tls_listener.listen(8)
    tls_listener.settimeout(0.2)
    tls_port = tls_listener.getsockname()[1]
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    stop = threading.Event()
    provider_errors: list[BaseException] = []
    submitted_seeds: list[int] = []
    image_download_index = 0

    def provider_loop() -> None:
        nonlocal image_download_index
        while not stop.is_set():
            try:
                raw, _address = tls_listener.accept()
            except TimeoutError:
                continue
            try:
                with tls_context.wrap_socket(raw, server_side=True) as connection:
                    wire = b""
                    while b"\r\n\r\n" not in wire:
                        wire += connection.recv(65536)
                    header, body = wire.split(b"\r\n\r\n", 1)
                    lines = header.decode("iso-8859-1").split("\r\n")
                    method, target, _version = lines[0].split(" ", 2)
                    headers = {
                        name.lower(): value.strip()
                        for name, value in (
                            line.split(":", 1) for line in lines[1:] if ":" in line
                        )
                    }
                    content_length = int(headers.get("content-length", "0"))
                    while len(body) < content_length:
                        body += connection.recv(65536)
                    host = headers.get("host", "").split(":", 1)[0]
                    path = target.split("?", 1)[0]
                    response_length: int | None = None
                    if host == "queue.fal.run":
                        assert headers.get("authorization") == "Key cpu-test-key"
                        if method == "POST":
                            payload = json.loads(body[:content_length].decode())
                            assert payload["prompt"] == "https connect t2i proof"
                            assert payload["seed"] in (19, 20)
                            assert payload["num_inference_steps"] == 28
                            assert payload["image_size"] == "1536x1024"
                            submitted_seeds.append(payload["seed"])
                            request_id = f"https-connect-{len(submitted_seeds)}"
                            response_body = json.dumps(
                                {
                                    "request_id": request_id,
                                    "status_url": f"https://queue.fal.run/status/{request_id}",
                                    "response_url": f"https://queue.fal.run/response/{request_id}",
                                }
                            ).encode()
                        elif path.startswith("/status/"):
                            response_body = b'{"status":"COMPLETED"}'
                        elif path.startswith("/response/"):
                            response_body = b'{"images":[{"url":"https://fal.media/cpu-result.png"}]}'
                        else:
                            response_body = b"{}"
                    elif host == "fal.media" and method == "GET":
                        if image_download_index == oversized_output_index:
                            response_body = b""
                            response_length = 64 * 1024 * 1024 + 1
                        else:
                            response_body = png
                            response_length = len(response_body)
                        image_download_index += 1
                    else:
                        response_body = b"unknown provider route"
                        response_length = len(response_body)
                    if response_length is None:
                        response_length = len(response_body)
                    status = HTTPStatus.OK if response_body != b"unknown provider route" else HTTPStatus.NOT_FOUND
                    connection.sendall(
                        f"HTTP/1.1 {status.value} {status.phrase}\r\n"
                        f"Content-Length: {response_length}\r\n"
                        "Connection: close\r\n\r\n".encode() + response_body
                    )
            except BaseException as exc:
                provider_errors.append(exc)

    provider_thread = threading.Thread(target=provider_loop, daemon=True)
    provider_thread.start()
    original_connect = broker_module.socket.create_connection

    def route_provider_connection(address, timeout=None, source_address=None):
        host, port = address
        if host in {"queue.fal.run", "fal.media", "fal.run"} and int(port) == 443:
            return original_connect(("127.0.0.1", tls_port), timeout, source_address)
        return original_connect(address, timeout, source_address)

    monkeypatch.setattr(broker_module.socket, "create_connection", route_provider_connection)

    class ProductionHost(GenericPackHost):
        def _child_environment(self, record, attempt, **kwargs):
            env, secrets = super()._child_environment(record, attempt, **kwargs)
            child_cert = attempt / "provider-ca.pem"
            child_cert.write_bytes(cert_path.read_bytes())
            env["SSL_CERT_FILE"] = str(child_cert)
            return env, secrets

    daemon = RuntimeDaemon(
        tmp_path / "realm",
        support_root=tmp_path / "support",
        production_worker_credentials=True,
    ).start()
    host = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        owner.handshake(
            "production-t2i-https-test",
            "0.1.0",
            ["projects:read", "projects:write", "objects:read", "objects:write", "worker:execute"],
        )
        client = RuntimeProtocolClient(daemon.endpoint, daemon.token)
        host = ProductionHost(
            pack_roots=[generation_root],
            client=client,
            executor_id="production-t2i-https-host",
            credential_source={"FAL_KEY": "cpu-test-key"},
        )
        host.discover()
        host.preflight("generation.generate_image")
        record = host.capabilities["generation.generate_image"]
        assert record.ready
        host.register()
        project = owner.create_project(
            "Production t2i HTTPS command",
            slug="production-t2i-https-command",
            idempotency_key="production-t2i-https-project",
        )
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=[],
            project_id=project.project_id,
            idempotency_key="production-t2i-https-task",
            spec={
                "family": record.id,
                "params": {
                    "execution": "cloud",
                    "mode": "t2i",
                    "model": "flux-dev",
                    "prompt": "https connect t2i proof",
                    "count": 2,
                    "seed": 19,
                    "steps": 28,
                    "size": "1536x1024",
                },
                "output_policy": {},
            },
            storage_estimate={
                "scratch_bytes": record.estimated_scratch_bytes,
                "output_bytes": record.estimated_output_bytes,
            },
        )
        completed = owner.get_task(task.task_id)
        if oversized_output_index is None:
            settled = host.run(once=True)
            assert len(settled) == 1 and settled[0].state == "succeeded"
            completed = owner.get_task(task.task_id)
            assert completed.state == "succeeded"
            assert submitted_seeds == [19, 20]
            evidence = completed.result["network_evidence"]
            routes = [
                event["detail"]
                for event in evidence["events"]
                if event["kind"] == "broker_route" and event["allowed"]
            ]
            assert any("queue.fal.run" in route for route in routes)
            assert any("fal.media" in route for route in routes)
        else:
            with pytest.raises(HostError, match="bounded body limit"):
                host.run(once=True)
            completed = owner.get_task(task.task_id)
            assert completed.state == "failed"
            assert not completed.result.get("outputs", [])
            assert submitted_seeds == ([19] if oversized_output_index == 0 else [19, 20])
        assert not provider_errors
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()
        stop.set()
        tls_listener.close()
        provider_thread.join(timeout=2)


@pytest.mark.parametrize("oversized_output", [False, True])
def test_production_i2i_command_uses_ordered_cas_through_https_connect_and_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    oversized_output: bool,
) -> None:
    """Exercise the shipped bounded i2i command with a CAS-owned source.

    The provider is a local TLS fixture reached through the same host-owned
    CONNECT broker used by a production executor.  The child command,
    GenericPackHost CAS materialization, Runtime admission, Fal adapter, and
    output settlement remain the shipped production paths.
    """
    import astrid.core.execution.network_broker as broker_module

    generation_root = Path(__file__).resolve().parents[2] / "astrid/packs/generation"
    png = base64.b64decode(_PNG)
    cert_dir = tmp_path / "provider-cert"
    cert_dir.mkdir()
    cert_path = cert_dir / "provider.pem"
    key_path = cert_dir / "provider.key"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key_path), "-out", str(cert_path), "-days", "1",
            "-subj", "/CN=queue.fal.run",
            "-addext", "subjectAltName=DNS:queue.fal.run,DNS:fal.media",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    tls_listener = socket.socket()
    tls_listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tls_listener.bind(("127.0.0.1", 0))
    tls_listener.listen(8)
    tls_listener.settimeout(0.2)
    tls_port = tls_listener.getsockname()[1]
    tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
    stop = threading.Event()
    provider_errors: list[BaseException] = []
    submitted_payloads: list[dict[str, object]] = []
    source_payloads: list[bytes] = []

    def provider_loop() -> None:
        while not stop.is_set():
            try:
                raw, _address = tls_listener.accept()
            except TimeoutError:
                continue
            try:
                with tls_context.wrap_socket(raw, server_side=True) as connection:
                    wire = b""
                    while b"\r\n\r\n" not in wire:
                        wire += connection.recv(65536)
                    header, body = wire.split(b"\r\n\r\n", 1)
                    lines = header.decode("iso-8859-1").split("\r\n")
                    method, target, _version = lines[0].split(" ", 2)
                    headers = {
                        name.lower(): value.strip()
                        for name, value in (
                            line.split(":", 1) for line in lines[1:] if ":" in line
                        )
                    }
                    content_length = int(headers.get("content-length", "0"))
                    while len(body) < content_length:
                        body += connection.recv(65536)
                    host = headers.get("host", "").split(":", 1)[0]
                    path = target.split("?", 1)[0]
                    response_length: int | None = None
                    if host == "queue.fal.run":
                        assert headers.get("authorization") == "Key cpu-test-key"
                        if method == "POST":
                            assert path == "/fal-ai/z-image/turbo/image-to-image"
                            payload = json.loads(body[:content_length].decode())
                            assert payload["prompt"] == "https connect i2i proof"
                            assert payload["image_size"] == {"width": 1024, "height": 1024}
                            assert payload["seed"] == 19
                            assert payload["strength"] == 0.5
                            image_url = payload["image_url"]
                            assert image_url.startswith("data:image/png;base64,")
                            source_bytes = base64.b64decode(image_url.split(",", 1)[1])
                            source_payloads.append(source_bytes)
                            submitted_payloads.append(payload)
                            response_body = (
                                b'{"request_id":"https-connect-i2i",'
                                b'"status_url":"https://queue.fal.run/status/https-connect-i2i",'
                                b'"response_url":"https://queue.fal.run/response/https-connect-i2i"}'
                            )
                        elif path == "/status/https-connect-i2i":
                            response_body = b'{"status":"COMPLETED"}'
                        elif path == "/response/https-connect-i2i":
                            response_body = b'{"images":[{"url":"https://fal.media/cpu-i2i-result.png"}]}'
                        else:
                            response_body = b"{}"
                    elif host == "fal.media" and method == "GET":
                        if oversized_output:
                            response_body = b""
                            response_length = 64 * 1024 * 1024 + 1
                        else:
                            response_body = png
                            response_length = len(response_body)
                    else:
                        response_body = b"unknown provider route"
                        response_length = len(response_body)
                    if response_length is None:
                        response_length = len(response_body)
                    status = HTTPStatus.OK if response_body != b"unknown provider route" else HTTPStatus.NOT_FOUND
                    connection.sendall(
                        f"HTTP/1.1 {status.value} {status.phrase}\r\n"
                        f"Content-Length: {response_length}\r\n"
                        "Connection: close\r\n\r\n".encode() + response_body
                    )
            except BaseException as exc:
                provider_errors.append(exc)

    provider_thread = threading.Thread(target=provider_loop, daemon=True)
    provider_thread.start()
    original_connect = broker_module.socket.create_connection

    def route_provider_connection(address, timeout=None, source_address=None):
        host, port = address
        if host in {"queue.fal.run", "fal.media", "fal.run"} and int(port) == 443:
            return original_connect(("127.0.0.1", tls_port), timeout, source_address)
        return original_connect(address, timeout, source_address)

    monkeypatch.setattr(broker_module.socket, "create_connection", route_provider_connection)

    class ProductionHost(GenericPackHost):
        def _child_environment(self, record, attempt, **kwargs):
            env, secrets = super()._child_environment(record, attempt, **kwargs)
            child_cert = attempt / "provider-ca.pem"
            child_cert.write_bytes(cert_path.read_bytes())
            env["SSL_CERT_FILE"] = str(child_cert)
            return env, secrets

    daemon = RuntimeDaemon(
        tmp_path / "realm",
        support_root=tmp_path / "support",
        production_worker_credentials=True,
    ).start()
    host = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        owner.handshake(
            "production-i2i-https-test",
            "0.1.0",
            ["projects:read", "projects:write", "objects:read", "objects:write", "worker:execute"],
        )
        client = RuntimeProtocolClient(daemon.endpoint, daemon.token)
        host = ProductionHost(
            pack_roots=[generation_root],
            client=client,
            executor_id="production-i2i-https-host",
            credential_source={"FAL_KEY": "cpu-test-key"},
        )
        host.discover()
        record = host.capabilities["generation.generate_image_cloud_i2i"]
        assert record.definition.kind == "built_in"
        assert record.definition.isolation.network is True
        assert record.definition.metadata["secrets_required"] == ["FAL_KEY"]
        assert record.definition.metadata["fixed_inputs"] == {
            "model": "z-image",
            "mode": "i2i",
            "execution": "cloud",
        }
        assert record.definition.metadata["hc04_cas_param_ports"] == ["image_ref"]
        assert "fal.media:443" in record.definition.metadata["network_policy"]["allowed_destinations"]
        host.preflight("generation.generate_image_cloud_i2i")
        assert host.capabilities["generation.generate_image_cloud_i2i"].ready
        host.register()
        project = owner.create_project(
            "Production i2i command",
            slug="production-i2i-command",
            idempotency_key="production-i2i-project",
        )
        source_row = owner.ingest_project_object(
            project.project_id,
            png,
            media_type="image/png",
            filename="source.png",
            idempotency_key="production-i2i-source",
        )
        source_id = str(
            getattr(source_row, "object_id", None)
            or getattr(source_row, "digest")
        )
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=[source_id],
            project_id=project.project_id,
            idempotency_key="production-i2i-task",
            spec={
                "family": record.id,
                "params": {
                    "execution": "cloud",
                    "mode": "i2i",
                    "model": "z-image",
                    "prompt": "https connect i2i proof",
                    "image_ref": {
                        "digest": source_id,
                        "filename": "source.png",
                        "media_type": "image/png",
                    },
                    "count": 1,
                    "size": "1024x1024",
                    "strength": 0.5,
                    "seed": 19,
                },
                "output_policy": {},
            },
            storage_estimate={
                "scratch_bytes": record.estimated_scratch_bytes,
                "output_bytes": record.estimated_output_bytes,
            },
        )
        if oversized_output:
            with pytest.raises(HostError, match="bounded body limit"):
                host.run(once=True)
            completed = owner.get_task(task.task_id)
            assert completed.state == "failed"
            assert not completed.result.get("outputs", [])
        else:
            settled = host.run(once=True)
            assert len(settled) == 1 and settled[0].state == "succeeded"
            completed = owner.get_task(task.task_id)
            assert completed.state == "succeeded"
            assert source_payloads == [png]
            assert len(submitted_payloads) == 1
            images = [
                output for output in completed.result["outputs"]
                if output["name"] == "generated_images"
            ]
            assert len(images) == 1
            image_bytes = owner.get_object(images[0]["digest"]).data
            assert image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
            assert b"https connect i2i proof" in image_bytes
            evidence = completed.result["network_evidence"]
            routes = [
                event["detail"]
                for event in evidence["events"]
                if event["kind"] == "broker_route" and event["allowed"]
            ]
            assert any("queue.fal.run" in route for route in routes)
            assert any("fal.media" in route for route in routes)
            assert not Path(completed.result["execution_guards"]["cleanup_path"]).exists()
        assert not provider_errors
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()
        stop.set()
        tls_listener.close()
        provider_thread.join(timeout=2)


def test_production_i2i_rejects_extra_or_misordered_single_cas_inputs(tmp_path: Path) -> None:
    """A single CAS port is still an ordered one-element input contract."""
    pack = _registered_image_executor_fixture(
        tmp_path,
        manifest_name="generate_image_cloud_i2i",
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
            "production-i2i-cas-order-test",
            "0.1.0",
            ["projects:read", "projects:write", "objects:read", "objects:write", "worker:execute"],
        )
        host = GenericPackHost(
            pack_roots=[pack],
            client=RuntimeProtocolClient(daemon.endpoint, daemon.token),
            executor_id="production-i2i-cas-order-host",
            credential_source={"FAL_KEY": "fixture-key"},
        )
        record = host.discover()[0]
        host.preflight()
        host.register()
        project = owner.create_project(
            "Production i2i CAS order",
            slug="production-i2i-cas-order",
            idempotency_key="production-i2i-cas-order-project",
        )
        source_row = owner.ingest_project_object(
            project.project_id,
            base64.b64decode(_PNG),
            media_type="image/png",
            filename="source.png",
            idempotency_key="production-i2i-cas-order-source",
        )
        extra_row = owner.ingest_project_object(
            project.project_id,
            b"extra-cas-object",
            media_type="application/octet-stream",
            filename="extra.bin",
            idempotency_key="production-i2i-cas-order-extra",
        )
        source_id = str(getattr(source_row, "object_id", None) or getattr(source_row, "digest"))
        extra_id = str(getattr(extra_row, "object_id", None) or getattr(extra_row, "digest"))
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=[extra_id, source_id],
            project_id=project.project_id,
            idempotency_key="production-i2i-cas-order-task",
            spec={
                "family": record.id,
                "params": {
                    "execution": "cloud",
                    "mode": "i2i",
                    "model": "z-image",
                    "prompt": "misordered source proof",
                    "image_ref": {
                        "digest": source_id,
                        "filename": "source.png",
                        "media_type": "image/png",
                    },
                    "count": 1,
                    "size": "1024x1024",
                    "strength": 0.5,
                },
                "output_policy": {},
            },
            storage_estimate={
                "scratch_bytes": record.estimated_scratch_bytes,
                "output_bytes": record.estimated_output_bytes,
            },
        )
        with pytest.raises(HostError, match="ordered CAS inputs"):
            host.run(once=True)
        failed = owner.get_task(task.task_id)
        assert failed.state == "failed"
        assert not failed.result.get("outputs", [])
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()


@pytest.mark.parametrize(
    ("manifest_name", "expected_capability", "model", "mode", "oversized_output_index"),
    [
        ("generate_image", "generation.generate_image", "flux-dev", "t2i", None),
        ("generate_image", "generation.generate_image", "flux-dev", "t2i", 0),
        ("generate_image", "generation.generate_image", "flux-dev", "t2i", 1),
        ("generate_image_cloud_i2i", "generation.generate_image_cloud_i2i", "z-image", "i2i", None),
        ("generate_image_edit", "generation.generate_image_edit", "qwen-image-edit-2511", "edit", None),
    ],
)
def test_registered_image_executor_consumes_cas_image_and_cleans_attempt(
    tmp_path: Path,
    manifest_name: str,
    expected_capability: str,
    model: str,
    mode: str,
    oversized_output_index: int | None,
) -> None:
    pack = _registered_image_executor_fixture(
        tmp_path,
        manifest_name=manifest_name,
        oversized_output_index=oversized_output_index,
        preserve_production_metadata=mode == "t2i",
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
            credential_source={"FAL_KEY": "fixture-key"},
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
        params = {
            "execution": "cloud",
            "mode": mode,
            "model": model,
            "prompt": "cpu t2i proof" if mode == "t2i" else ("cpu i2i proof" if mode == "i2i" else "cpu edit proof"),
            "count": 2 if mode == "t2i" else 1,
            "seed": 19 if mode == "t2i" else 11,
            "size": "1536x1024" if mode == "t2i" else "1024x1024",
        }
        input_object_ids: list[str] = []
        source_id: str | None = None
        if mode != "t2i":
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
            params["image_ref"] = {
                "digest": source_id,
                "filename": "source.png",
                "media_type": "image/png",
            }
            input_object_ids = [source_id]
        if mode == "i2i":
            params["strength"] = 0.5
        if mode == "t2i":
            params["steps"] = 28
        task = owner.admit_task(
            capability_id=record.id,
            capability_digest=record.capability_digest,
            input_object_ids=input_object_ids,
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
        completed = owner.get_task(task.task_id)
        if oversized_output_index is not None:
            with pytest.raises(HostError):
                host.run(once=True)
            completed = owner.get_task(task.task_id)
            assert completed.state == "failed"
            assert not completed.result.get("outputs", [])
        else:
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
            assert (b"cpu t2i proof" if mode == "t2i" else (b"cpu i2i proof" if mode == "i2i" else b"cpu edit proof")) in image_bytes
        if oversized_output_index is not None:
            cleanup_receipt = host.last_cleanup_receipt
            assert cleanup_receipt is not None
            assert cleanup_receipt["status"] == "deleted"
            assert cleanup_receipt["observed_absent"] is True
        else:
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
