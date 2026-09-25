from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.sdk.remote import RemoteTasks
from astrid.sdk import invocation
from astrid.sdk.workspace_client import WorkspaceClientError, resolve_runtime_connection


def test_explicit_credential_file_needs_no_parent_metadata_probe(tmp_path: Path, monkeypatch):
    credential = tmp_path / "credentials" / "owner.token"
    credential.parent.mkdir()
    credential.write_text("disposable-token\n", encoding="utf-8")
    parent_link = tmp_path / "credentials-link"
    parent_link.symlink_to(credential.parent, target_is_directory=True)
    original = Path.is_symlink

    def deny_parent_probe(path):
        if path in {credential.parent, parent_link}:
            raise PermissionError("parent metadata is denied")
        return original(path)

    monkeypatch.setattr(Path, "is_symlink", deny_parent_probe)
    assert resolve_runtime_connection("http://127.0.0.1:8123", credential) == (
        "http://127.0.0.1:8123", "disposable-token"
    )

    link = tmp_path / "owner-link.token"
    link.symlink_to(credential)
    with pytest.raises(WorkspaceClientError):
        resolve_runtime_connection("http://127.0.0.1:8123", link)

    with pytest.raises(WorkspaceClientError, match="must not contain a symlink"):
        resolve_runtime_connection("http://127.0.0.1:8123", parent_link / "owner.token")


def test_deterministic_admission_reports_missing_registration():
    transport = SimpleNamespace(list_capabilities=lambda **_: [[], None])
    result = RemoteTasks(transport).create(
        project_id="project-1", capability="rendering.render", spec={"inputs": {}},
        input_manifest=[], deterministic_idempotency=True,
    )
    assert not result.ok
    assert result.error.code == "not_found"
    assert result.error.message == "capability is not registered"
    assert result.idempotency_key == ""


def test_unexpected_wait_failure_keeps_cause_and_admitted_run(monkeypatch):
    capability = SimpleNamespace(
        id="example.executor", capability_type="executor", native_kind="built_in",
        inputs=(), definition={},
    )
    definition = SimpleNamespace(to_dict=lambda: {"id": capability.id})
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **_: ({capability.id: definition}, None, None),
        get_capability=lambda *_, **__: capability,
    )
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)
    monkeypatch.setattr(
        invocation, "_kernel_invoke",
        lambda *_, **__: ("run-1", "task-1", "attempt-1", None, {"ok": True}, True, None),
    )
    monkeypatch.setattr(
        invocation, "_wait_for_kernel_task",
        lambda *_, **__: (_ for _ in ()).throw(RuntimeError("status read failed")),
    )
    result = invocation.invoke_result(
        capability.id, kind="executor", project="project-1", client=SimpleNamespace(),
        wait=True,
    )
    assert not result.ok
    assert result.run_id == result.kernel_run_id == "run-1"
    assert result.kernel_task_id == "task-1"
    assert result.kernel_attempt_id == "attempt-1"
    assert result.error["details"]["cause_type"] == "RuntimeError"
    assert "status read failed" in result.error["details"]["cause_message"]
