from __future__ import annotations

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path
from typing import Any

import pytest

from astrid.core.execution.generic_host import (
    GenericPackHost,
    HostError,
    RuntimeProtocolClient,
)
from astrid.sdk.client import AstridClient

pytest.importorskip("vibecomfy.porting.import_service")


ASTRID_SOURCE = Path(
    subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
).parent
RUNTIME_WORKTREE = ASTRID_SOURCE.parent / "banodoco-workspace-runtime-execution-20260909"
RUNTIME_COMMIT = "afccb430e2a983c968b6a8a96fd630ba3a6262fc"
ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = ROOT / "astrid" / "packs" / "vibecomfy"


def _runtime_daemon_class(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    runtime_root = tmp_path / "runtime-source"
    runtime_root.mkdir()
    if RUNTIME_WORKTREE.is_dir():
        archive = subprocess.run(
            ["git", "-C", str(RUNTIME_WORKTREE), "archive", "--format=tar", RUNTIME_COMMIT],
            check=True,
            capture_output=True,
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(runtime_root)
        monkeypatch.syspath_prepend(str(runtime_root))
    runtime_daemon = pytest.importorskip("runtime_protocol.daemon")
    return runtime_daemon.RuntimeDaemon


def _open_client(daemon: Any) -> AstridClient:
    return AstridClient.open(
        endpoint=daemon.endpoint,
        credential=daemon.credential_path,
        realm_id=daemon.service.realm["id"],
        actor_id="owner",
        client_name="vibecomfy-real-integration-test",
        client_version="test",
        protocol_version="workspace.v1",
    )


def _events(client: AstridClient, task_id: str) -> list[dict[str, Any]]:
    result = client.tasks.events(task_id)
    assert result.ok
    rows = result.data
    if isinstance(rows, dict):
        rows = rows.get("items", rows.get("events", []))
    elif isinstance(rows, (list, tuple)) and len(rows) == 2 and isinstance(rows[0], list):
        rows = rows[0]
    assert isinstance(rows, list)
    return [dict(row) for row in rows if isinstance(row, dict)]


def _event_types(rows: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for row in rows:
        value = row.get("event_type", row.get("kind"))
        if value is None and isinstance(row.get("payload"), dict):
            value = row["payload"].get("kind")
        if value is not None:
            values.append(str(value))
    return values


def _project_task_ids(client: AstridClient, project_id: str) -> set[str]:
    listed = client.tasks.list(project_id)
    assert listed.ok
    rows = listed.data
    if isinstance(rows, dict):
        assert rows.get("next_cursor") is None
        rows = rows.get("items", [])
    elif isinstance(rows, (list, tuple)) and len(rows) == 2 and isinstance(rows[0], list):
        rows, cursor = rows
        assert cursor is None
    while isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], list):
        rows = rows[0]
    assert isinstance(rows, list)
    task_ids = {
        row.get("task_id", row.get("id"))
        if isinstance(row, dict)
        else getattr(row, "task_id", None)
        for row in rows
    }
    assert None not in task_ids
    return {str(task_id) for task_id in task_ids}


def _node_index_bytes() -> bytes:
    return json.dumps(
        [
            {
                "class_type": "LoadImage",
                "pack": "core",
                "inputs": {"image": {"type": "STRING", "required": True}},
                "outputs": [{"type": "IMAGE", "name": "image"}],
            },
            {
                "class_type": "SaveImage",
                "pack": "core",
                "inputs": {
                    "images": {"type": "IMAGE", "required": True},
                    "filename_prefix": {"type": "STRING", "required": True},
                },
                "outputs": [{"type": "IMAGE", "name": "IMAGES"}],
            },
        ],
        sort_keys=True,
    ).encode()


def _new_host(
    daemon: Any,
    *,
    attempt_root: Path,
    executor_id: str,
) -> GenericPackHost:
    attempt_root.mkdir(parents=True, exist_ok=True)
    # The real import service resolves this offline node index from the task's
    # working directory. It is test input, not a mutation of the VibeComfy
    # checkout or the live Astrid host.
    (attempt_root / "node_index.json").write_bytes(_node_index_bytes())
    host = GenericPackHost(
        pack_roots=[PACK_ROOT],
        attempt_root=attempt_root,
        client=RuntimeProtocolClient(
            daemon.endpoint,
            daemon.credential_path.read_text(encoding="utf-8").strip(),
        ),
        executor_id=executor_id,
    )
    records = host.discover()
    assert {"vibecomfy.import", "vibecomfy.edit", "vibecomfy.validate"}.issubset(
        {record.id for record in records}
    )
    host.register()
    return host


def test_real_vibecomfy_runtime_requires_explicit_python_consent_and_tracks_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove consent rejection and consented import → edit → validate history.

    This uses a disposable RuntimeDaemon and real VibeComfy services. The test
    never starts a generation task, contacts ComfyUI, or touches a live host.
    """
    RuntimeDaemon = _runtime_daemon_class(monkeypatch, tmp_path)
    daemon = RuntimeDaemon(tmp_path / "realm", support_root=tmp_path / "support").start()
    try:
        client = _open_client(daemon)
        project = client.projects.create(
            slug="vibecomfy-real-c7",
            name="VibeComfy Real C7",
            idempotency_key="vibecomfy-real-c7-project",
        )
        assert project.ok
        project_id = project.data["project_id"]

        source_bytes = json.dumps(
            {
                "1": {"class_type": "LoadImage", "inputs": {"image": "input.png"}},
                "2": {
                    "class_type": "SaveImage",
                    "inputs": {
                        "images": ["1", 0],
                        "filename_prefix": "out/c7-origin",
                    },
                },
            },
            sort_keys=True,
        ).encode()
        source_path = tmp_path / "source.json"
        source_path.write_bytes(source_bytes)
        source_media = client.media.import_file(
            project=project_id,
            path=source_path,
            idempotency_key="vibecomfy-real-c7-source",
        )
        assert source_media.ok

        origin_host = _new_host(
            daemon,
            attempt_root=tmp_path / "origin-attempt",
            executor_id="vibecomfy-real-c7-host",
        )

        origin = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.import",
            spec={
                "inputs": {"workflow_id": "c7-origin"},
                "input_digests": [{"name": "source", "digest": source_media.data["digest"]}],
                "transition_kind": "origin",
                "parent_task_id": None,
                "origin_task_id": None,
            },
            input_manifest=[source_media.data["object_id"]],
            idempotency_key="vibecomfy-real-c7-origin-task",
        )
        assert origin.ok
        origin_task_id = origin.data["task_id"]

        origin_settled = origin_host.run(once=True)
        assert len(origin_settled) == 1 and origin_settled[0].state == "succeeded"

        origin_task = client.tasks.show(origin_task_id)
        assert origin_task.ok and origin_task.data["state"] == "succeeded"
        origin_outputs = {
            item["name"]: item for item in origin_task.data["result"]["outputs"]
        }
        assert set(origin_outputs) == {"python", "companion", "source", "report"}
        assert client.media.read_bytes(origin_outputs["source"]["digest"]) == source_bytes
        origin_report_bytes = client.media.read_bytes(origin_outputs["report"]["digest"])
        assert "sha256:" + hashlib.sha256(origin_report_bytes).hexdigest() == origin_outputs[
            "report"
        ]["digest"]
        origin_report = json.loads(origin_report_bytes)
        assert origin_report["transition_kind"] == "origin"
        assert origin_report["workflow_identity"] == "c7-origin"
        assert origin_report["parent_task_id"] is None
        assert origin_report["origin_task_id"] is None
        assert origin_report["after"]["members"] == {
            "workflow.py": origin_outputs["python"]["digest"],
            "workflow.vibe.json": origin_outputs["companion"]["digest"],
            "source.json": origin_outputs["source"]["digest"],
        }
        origin_event_types = _event_types(_events(client, origin_task_id))
        assert origin_event_types.count("task.admitted") == 1
        assert origin_event_types.count("task.completed") == 1

        operation_bytes = json.dumps(
            {
                "schema_version": 1,
                "expected_revision": 0,
                "ops": [
                    {
                        "op": "edit_node",
                        # Imported source id ``2`` is preserved as the
                        # custody node's canonical VibeComfy uid ``n2``.
                        "target": "n2",
                        "field": "filename_prefix",
                        "value": "out/c7-edited",
                    }
                ],
            },
            sort_keys=True,
        ).encode()
        operation_path = tmp_path / "operations.json"
        operation_path.write_bytes(operation_bytes)
        operation_media = client.media.import_file(
            project=project_id,
            path=operation_path,
            idempotency_key="vibecomfy-real-c7-operations",
        )
        assert operation_media.ok
        edit_inputs = {
            "python": origin_outputs["python"]["digest"],
            "companion": origin_outputs["companion"]["digest"],
            "source": origin_outputs["source"]["digest"],
            "operations": operation_media.data["digest"],
        }
        edit_host = _new_host(
            daemon,
            attempt_root=tmp_path / "edit-no-consent-attempt",
            executor_id="vibecomfy-real-c7-host",
        )
        edit_without_consent = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.edit",
            spec={
                "inputs": {
                    "workflow_id": "c7-origin",
                    "parent_revision": origin_report["revision_id"],
                    "parent_task_id": origin_task_id,
                    "origin_task_id": origin_task_id,
                    "transition_kind": "typed_edit",
                    "python_execution_consent": "",
                },
                "input_digests": [
                    {"name": name, "digest": digest}
                    for name, digest in edit_inputs.items()
                ],
                "workflow_id": "c7-origin",
                "parent_revision": origin_report["revision_id"],
                "parent_task_id": origin_task_id,
                "origin_task_id": origin_task_id,
                "transition_kind": "typed_edit",
            },
            input_manifest=list(edit_inputs.values()),
            idempotency_key="vibecomfy-real-c7-edit-task",
        )
        assert edit_without_consent.ok
        edit_no_consent_id = edit_without_consent.data["task_id"]
        with pytest.raises(HostError, match="python_execution_consent.*confirmed") as edit_error:
            edit_host.run(once=True)
        assert "python_execution_consent" in str(edit_error.value)
        edit_no_consent_task = client.tasks.show(edit_no_consent_id)
        assert edit_no_consent_task.ok and edit_no_consent_task.data["state"] == "failed"
        edit_task_spec = edit_no_consent_task.data["spec"]["spec"]
        assert edit_task_spec["inputs"]["parent_task_id"] == origin_task_id
        assert edit_task_spec["inputs"]["origin_task_id"] == origin_task_id
        assert edit_task_spec["inputs"]["parent_revision"] == origin_report["revision_id"]
        assert edit_task_spec["inputs"]["python_execution_consent"] == ""
        edit_failure = json.dumps(edit_no_consent_task.data, sort_keys=True, default=str)
        assert "must be exactly 'confirmed'" in edit_failure
        edit_no_consent_events = _event_types(_events(client, edit_no_consent_id))
        assert edit_no_consent_events.count("task.admitted") == 1
        assert edit_no_consent_events.count("task.failed") == 1

        edit_host = _new_host(
            daemon,
            attempt_root=tmp_path / "edit-consented-attempt",
            executor_id="vibecomfy-real-c7-host",
        )
        edit = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.edit",
            spec={
                "inputs": {
                    "workflow_id": "c7-origin",
                    "parent_revision": origin_report["revision_id"],
                    "parent_task_id": origin_task_id,
                    "origin_task_id": origin_task_id,
                    "transition_kind": "typed_edit",
                    "python_execution_consent": "confirmed",
                },
                "input_digests": [
                    {"name": name, "digest": digest}
                    for name, digest in edit_inputs.items()
                ],
                "workflow_id": "c7-origin",
                "parent_revision": origin_report["revision_id"],
                "parent_task_id": origin_task_id,
                "origin_task_id": origin_task_id,
                "transition_kind": "typed_edit",
            },
            input_manifest=list(edit_inputs.values()),
            idempotency_key="vibecomfy-real-c7-consented-edit-task",
        )
        assert edit.ok
        edit_task_id = edit.data["task_id"]
        edit_settled = edit_host.run(once=True)
        assert len(edit_settled) == 1 and edit_settled[0].state == "succeeded"
        edit_task = client.tasks.show(edit_task_id)
        assert edit_task.ok and edit_task.data["state"] == "succeeded"
        edit_outputs = {
            item["name"]: item for item in edit_task.data["result"]["outputs"]
        }
        assert set(edit_outputs) == {"python", "companion", "source", "report"}
        edit_report_bytes = client.media.read_bytes(edit_outputs["report"]["digest"])
        assert "sha256:" + hashlib.sha256(edit_report_bytes).hexdigest() == edit_outputs[
            "report"
        ]["digest"]
        edit_report = json.loads(edit_report_bytes)
        assert edit_report["python_execution_consent"] == "confirmed"
        assert isinstance(edit_report["security_gate_audit"], list)
        assert edit_report["parent_task_id"] == origin_task_id
        assert edit_report["origin_task_id"] == origin_task_id
        assert edit_report["parent_revision"] == origin_report["revision_id"]
        assert edit_report["after"]["members"] == {
            "workflow.py": edit_outputs["python"]["digest"],
            "workflow.vibe.json": edit_outputs["companion"]["digest"],
            "source.json": edit_outputs["source"]["digest"],
        }
        edit_event_types = _event_types(_events(client, edit_task_id))
        assert edit_event_types.count("task.admitted") == 1
        assert edit_event_types.count("task.completed") == 1

        # The no-consent validation task is admitted and then refused by the
        # adapter before it invokes the CLI's audited --yes gate.
        validate_inputs = {
            name: edit_outputs[name]["digest"]
            for name in ("python", "companion", "source")
        }
        validate_host = _new_host(
            daemon,
            attempt_root=tmp_path / "validate-no-consent-attempt",
            executor_id="vibecomfy-real-c7-host",
        )
        validate_without_consent = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.validate",
            spec={
                "inputs": {},
                "input_digests": [
                    {"name": name, "digest": digest}
                    for name, digest in validate_inputs.items()
                ],
            },
            input_manifest=list(validate_inputs.values()),
            idempotency_key="vibecomfy-real-c7-validate-task",
        )
        assert validate_without_consent.ok
        validate_no_consent_id = validate_without_consent.data["task_id"]
        with pytest.raises(HostError, match="python_execution_consent.*confirmed") as error:
            validate_host.run(once=True)
        assert "python_execution_consent" in str(error.value)
        validate_no_consent_task = client.tasks.show(validate_no_consent_id)
        assert validate_no_consent_task.ok
        assert validate_no_consent_task.data["state"] == "failed"
        failure_payload = json.dumps(validate_no_consent_task.data, sort_keys=True, default=str)
        assert "must be exactly 'confirmed'" in failure_payload
        validate_no_consent_events = _event_types(_events(client, validate_no_consent_id))
        assert validate_no_consent_events.count("task.admitted") == 1
        assert validate_no_consent_events.count("task.failed") == 1

        validate_host = _new_host(
            daemon,
            attempt_root=tmp_path / "validate-consented-attempt",
            executor_id="vibecomfy-real-c7-host",
        )
        validate = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.validate",
            spec={
                "inputs": {"python_execution_consent": "confirmed"},
                "input_digests": [
                    {"name": name, "digest": digest}
                    for name, digest in validate_inputs.items()
                ],
            },
            input_manifest=list(validate_inputs.values()),
            idempotency_key="vibecomfy-real-c7-consented-validate-task",
        )
        assert validate.ok
        validate_task_id = validate.data["task_id"]
        validate_settled = validate_host.run(once=True)
        assert len(validate_settled) == 1 and validate_settled[0].state == "succeeded"
        validate_task = client.tasks.show(validate_task_id)
        assert validate_task.ok and validate_task.data["state"] == "succeeded"
        validate_outputs = {
            item["name"]: item for item in validate_task.data["result"]["outputs"]
        }
        assert set(validate_outputs) == {"validation"}
        validation_bytes = client.media.read_bytes(validate_outputs["validation"]["digest"])
        assert "sha256:" + hashlib.sha256(validation_bytes).hexdigest() == validate_outputs[
            "validation"
        ]["digest"]
        validation_report = json.loads(validation_bytes)
        assert validation_report["status"] == "ok"
        assert validation_report["python_execution_consent"] == "confirmed"
        assert isinstance(validation_report["security_gate_audit"], list)
        assert validation_report["authority"] == "canonical_workflow_bundle"
        validate_event_types = _event_types(_events(client, validate_task_id))
        assert validate_event_types.count("task.admitted") == 1
        assert validate_event_types.count("task.completed") == 1

        assert _event_types(_events(client, origin_task_id)).count("task.completed") == 1
        assert _project_task_ids(client, project_id) == {
            origin_task_id,
            edit_no_consent_id,
            edit_task_id,
            validate_no_consent_id,
            validate_task_id,
        }
    finally:
        daemon.stop()
