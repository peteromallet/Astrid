from pathlib import Path
from types import SimpleNamespace
import hashlib
import shutil
import subprocess
import sys
import pytest

import astrid.sdk as sdk
from astrid.sdk.invocation import _kernel_invoke
from astrid.core.execution.generic_host import GenericPackHost, _assert_fixed_request_scope
from astrid.core.contracts.binding import expand_command, assert_provided_inputs_bound


def test_canonical_codex_admission_materializes_all_roles_and_binds_command(tmp_path):
    captured = {}

    class Tasks:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(ok=False, error={"message": "captured"}, data=None)

    payloads = {hashlib.sha256(name.encode()).hexdigest(): name.encode()
                for name in ("source", "style", "brand")}
    refs = [{"digest": digest, "filename": "guide.png", "media_type": "image/png", "size_bytes": len(data)}
            for digest, data in payloads.items()]
    inputs = dict(zip(("image_ref", "style_ref", "brand_ref"), refs))
    inputs.update(model="qwen-image-edit", mode="edit", execution="codex", prompt="edit with guides", count=1)
    cap = sdk.get_capability("generation.generate_image_codex", kind="executor")
    _kernel_invoke(cap, kind="executor", project="project-id", inputs=inputs, outputs={},
                   _client=SimpleNamespace(tasks=Tasks()),
                   storage_estimate={"scratch_bytes": 536870912, "output_bytes": 269484032})
    assert "inputs" not in captured["spec"]
    assert captured["spec"]["params"] == inputs
    assert captured["input_manifest"] == ["sha256:" + digest for digest in payloads]
    runtime = SimpleNamespace(get_object=lambda digest: payloads[digest])
    host = GenericPackHost(pack_roots=[Path("astrid/packs")], client=runtime)
    host.discover()
    record = host.capabilities[cap.id]
    task = {"spec": {"spec": captured["spec"], "input_object_ids": captured["input_manifest"]}}
    _assert_fixed_request_scope(record, task)
    meta = record.definition.metadata
    values = host._materialize_inputs(
        task["spec"], tmp_path / "attempt", task_param_ports=meta["hc04_param_ports"],
        cas_param_ports=meta["hc04_cas_param_ports"],
        optional_cas_param_ports=meta["hc04_optional_cas_param_ports"],
        input_size_limits=meta["storage_input_max_bytes"],
        storage_estimate=captured["storage_estimate"],
        file_input_names=frozenset(("image_ref", "style_ref", "brand_ref")),
    )
    for role, data in zip(("image_ref", "style_ref", "brand_ref"), payloads.values()):
        assert Path(values[role]).read_bytes() == data
    values.update(out=str(tmp_path / "outputs"), python_exec="python")
    for port in record.definition.inputs:
        if port.name not in values and port.default is not None:
            values[port.name] = port.default
    binding = expand_command(record.definition.command, record.definition.inputs, values, meta)
    assert_provided_inputs_bound(binding, record.definition.inputs, values, meta)
    assert "--style-ref" in binding.argv and "--brand-ref" in binding.argv


def test_generation_publication_resolves_project_slug_once():
    from astrid.sdk.remote import RemoteTasks
    captured = {}

    class Runtime:
        def list_capabilities(self, **kwargs):
            return [[{"capability_id": "generation.generate_image_codex", "definition_digest": "abc", "status": "ready"}], None]

        def get_project(self, ref):
            assert ref == "astrid-intro"
            return {"project_id": "canonical-id", "slug": ref}

        def admit_task(self, **kwargs):
            captured.update(kwargs)
            return {"task_id": "task"}

    result = RemoteTasks(Runtime()).create(
        project_id="astrid-intro", capability="generation.generate_image_codex", spec={},
        settlement_effect={"effect_type": "generation.publish_v1", "target_id": "astrid-intro", "payload": {}},
    )
    assert result.ok
    assert captured["project_id"] == "canonical-id"
    assert captured["settlement_effect"]["target_id"] == "canonical-id"


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("codex"), reason="requires macOS Codex CLI")
def test_codex_native_binary_starts_in_host_sandbox(tmp_path):
    from astrid.core.execution.generic_host import _network_sandbox_argv
    command = _network_sandbox_argv([shutil.which("codex"), "--version"], tmp_path, "http://127.0.0.1:12345")
    result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "codex-cli" in result.stdout
