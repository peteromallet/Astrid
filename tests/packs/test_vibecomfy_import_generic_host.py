from __future__ import annotations

import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from astrid.core.execution.generic_host import GenericPackHost, RuntimeProtocolClient
from astrid.sdk.client import AstridClient

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
RUNTIME_ROOT = Path(tempfile.mkdtemp(prefix="vibecomfy-import-runtime-"))
if RUNTIME_WORKTREE.is_dir():
    archive = subprocess.run(
        ["git", "-C", str(RUNTIME_WORKTREE), "archive", "--format=tar", RUNTIME_COMMIT],
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        tar.extractall(RUNTIME_ROOT)
    sys.path.insert(0, str(RUNTIME_ROOT))

runtime_daemon = pytest.importorskip("runtime_protocol.daemon")
RuntimeDaemon = runtime_daemon.RuntimeDaemon

ROOT = Path(__file__).resolve().parents[2]
IMPORT_CAPABILITY = (
    ROOT / "astrid" / "packs" / "vibecomfy" / "executors" / "import" / "executor.yaml"
)
EDIT_CAPABILITY = (
    ROOT / "astrid" / "packs" / "vibecomfy" / "executors" / "edit" / "executor.yaml"
)


def _write_fake_vibecomfy_package(pack_root: Path) -> None:
    package_root = pack_root / "vibecomfy"
    executor_root = package_root / "executors" / "import"
    edit_executor_root = package_root / "executors" / "edit"
    service_root = package_root / "porting"
    edit_service_root = service_root / "edit"
    executor_root.mkdir(parents=True)
    edit_executor_root.mkdir(parents=True)
    service_root.mkdir(parents=True)
    edit_service_root.mkdir(parents=True)
    shutil.copyfile(IMPORT_CAPABILITY, executor_root / "executor.yaml")
    shutil.copyfile(EDIT_CAPABILITY, edit_executor_root / "executor.yaml")
    (package_root / "pack.yaml").write_text(
        "schema_version: 2\nid: vibecomfy\nname: Fixture VibeComfy\nversion: 1.0.0\n"
        "capabilities: [import_workflow, edit_workflow_ir]\ncontent:\n  executors: executors\n",
        encoding="utf-8",
    )
    (package_root / "__init__.py").write_text("\n", encoding="utf-8")
    (service_root / "__init__.py").write_text("\n", encoding="utf-8")
    (service_root / "import_service.py").write_text(
        "import hashlib\n"
        "from types import SimpleNamespace\n"
        "def _digest(data): return 'sha256:' + hashlib.sha256(data).hexdigest()\n"
        "def import_workflow_bytes(source_bytes, *, workflow_id):\n"
        "    python = b\"workflow = load('fixture')\\n\"\n"
        "    companion = b'{\\\"revision_id\\\":\\\"origin-revision\\\"}\\n'\n"
        "    members = {'workflow.py': python, 'workflow.vibe.json': companion, 'source.json': source_bytes}\n"
        "    digests = {name: _digest(data) for name, data in members.items()}\n"
        "    report = {'schema_version': 1, 'transition_kind': 'origin', 'workflow_id': workflow_id,\n"
        "        'workflow_identity': workflow_id, 'revision_id': 'origin-revision',\n"
        "        'parent_revision': None, 'parent_task_id': None, 'origin_task_id': None, 'before': None,\n"
        "        'after': {'revision_id': 'origin-revision', 'members': digests}, 'members': digests,\n"
        "        'readiness': {'status': 'ready'}, 'validation': {'status': 'structural'}}\n"
        "    return SimpleNamespace(source_bytes=source_bytes, python_bytes=python,\n"
        "        companion_bytes=companion, report=report)\n",
        encoding="utf-8",
    )
    (edit_service_root / "__init__.py").write_text("\n", encoding="utf-8")
    (edit_service_root / "bundle_service.py").write_text(
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n"
        "def transition_bundle(reference, *, output, expected_parent_revision, tool_calls=None, capture=False, candidate_python=None, **kwargs):\n"
        "    if capture:\n"
        "        from vibecomfy.security import _active_gate\n"
        "        gate = _active_gate.get()\n"
        "        assert gate is not None and gate.non_interactive and gate.assume_yes\n"
        "        gate.audit.append({'kind': 'explicit_manual_capture', 'non_interactive': gate.non_interactive, 'assume_yes': gate.assume_yes})\n"
        "        ops = []\n"
        "        python = Path(candidate_python).read_bytes()\n"
        "        revision = 'captured-revision'\n"
        "    else:\n"
        "        ops = tool_calls[0]['args']['ops']\n"
        "        if expected_parent_revision == 'origin-revision':\n"
        "            assert len(ops) == 2\n"
        "            python = b\"workflow = load('edited')\\n\"\n"
        "            revision = 'edited-revision'\n"
        "        else:\n"
        "            assert expected_parent_revision == 'edited-revision' and len(ops) == 1\n"
        "            python = b\"workflow = load('edited-twice')\\n\"\n"
        "            revision = 'edited-twice-revision'\n"
        "    output = Path(output)\n"
        "    output.parent.mkdir(parents=True, exist_ok=True)\n"
        "    output.write_bytes(python)\n"
        "    output.with_name('workflow.vibe.json').write_text('{\"revision_id\":\"' + revision + '\"}\\n')\n"
        "    output.with_name('source.json').write_bytes(Path(reference).with_name('source.json').read_bytes())\n"
        "    return SimpleNamespace(status='saved', revision_id=revision, to_dict=lambda: {\n"
        "        'status': 'saved', 'kind': 'edit', 'parent_revision': expected_parent_revision,\n"
        "        'revision': revision, 'operations': ops, 'diff': ops, 'diagnostics': []})\n",
        encoding="utf-8",
    )
    (package_root / "security.py").write_text(
        "from contextvars import ContextVar\n"
        "_active_gate = ContextVar('fixture_gate', default=None)\n"
        "class GateContext:\n"
        "    def __init__(self, *, non_interactive, assume_yes):\n"
        "        self.non_interactive = non_interactive\n"
        "        self.assume_yes = assume_yes\n"
        "        self.audit = []\n"
        "def set_gate_context(context): return _active_gate.set(context)\n",
        encoding="utf-8",
    )
    (package_root / "workflow_bundle.py").write_text(
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n"
        "def load_bundle(path, schema_provider=None):\n"
        "    current = Path(path).read_bytes()\n"
        "    captured = b'captured' in current\n"
        "    edited_twice = b'edited-twice' in current\n"
        "    edited = b'edited' in current\n"
        "    return SimpleNamespace(workflow_identity='portrait',\n"
        "        revision_id='captured-revision' if captured else ('edited-twice-revision' if edited_twice else ('edited-revision' if edited else 'origin-revision')),\n"
        "        parent_revision='edited-twice-revision' if captured else ('edited-revision' if edited_twice else ('origin-revision' if edited else None)),\n"
        "        semantic_digest='semantic:captured' if captured else ('semantic:edited-twice' if edited_twice else ('semantic:edited' if edited else 'semantic:origin')),\n"
        "        ui_digest='ui:captured' if captured else ('ui:edited-twice' if edited_twice else ('ui:edited' if edited else 'ui:origin')))\n",
        encoding="utf-8",
    )


def _open_client(daemon) -> AstridClient:
    return AstridClient.open(
        endpoint=daemon.endpoint,
        credential=daemon.credential_path,
        realm_id=daemon.service.realm["id"],
        actor_id="owner",
        client_name="astrid-vibecomfy-import-test",
        client_version="test",
        protocol_version="workspace.v1",
    )


def _task_events(client: AstridClient, task_id: str) -> list[dict[str, object]]:
    events = client.tasks.events(task_id)
    assert events.ok
    rows = events.data
    if isinstance(rows, dict):
        rows = rows.get("items", rows.get("events", []))
    elif isinstance(rows, (list, tuple)) and len(rows) == 2 and isinstance(rows[0], list):
        rows = rows[0]
    assert isinstance(rows, list)
    return [dict(row) for row in rows if isinstance(row, dict)]


def _assert_lifecycle_events(client: AstridClient, task_id: str) -> None:
    records = _task_events(client, task_id)
    event_types = [
        item.get("event_type", item.get("kind"))
        or (item.get("payload", {}).get("kind") if isinstance(item.get("payload"), dict) else None)
        for item in records
    ]
    assert event_types.count("task.admitted") == 1
    assert event_types.count("task.completed") == 1


def _project_task_ids(client: AstridClient, project_id: str) -> set[str]:
    listed = client.tasks.list(project_id)
    assert listed.ok
    rows = listed.data
    if (
        isinstance(rows, (list, tuple))
        and len(rows) == 2
        and isinstance(rows[0], list)
    ):
        rows, cursor = rows
        assert cursor is None
    elif isinstance(rows, dict):
        cursor = rows.get("next_cursor")
        rows = rows.get("items", [])
        assert cursor is None
    while isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], list):
        rows = rows[0]
    assert isinstance(rows, list)
    task_ids = {
        row.get("task_id", row.get("id"))
        if isinstance(row, Mapping)
        else getattr(row, "task_id", None)
        for row in rows
    }
    assert None not in task_ids
    return {str(task_id) for task_id in task_ids}


def test_import_edit_capture_history_runs_as_runtime_tasks_and_settles_lineage(
    tmp_path: Path,
) -> None:
    pack_root = tmp_path / "packs"
    pack_root.mkdir()
    _write_fake_vibecomfy_package(pack_root)
    daemon = RuntimeDaemon(tmp_path / "realm", support_root=tmp_path / "support").start()
    try:
        client = _open_client(daemon)
        project = client.projects.create(
            slug="vibecomfy-origin",
            name="VibeComfy Origin",
            idempotency_key="vibecomfy-origin-project",
        )
        assert project.ok
        project_id = project.data["project_id"]

        host = GenericPackHost(
            pack_roots=[pack_root],
            attempt_root=tmp_path / "attempt",
            client=RuntimeProtocolClient(daemon.endpoint, daemon.credential_path.read_text().strip()),
            executor_id="vibecomfy-import-test-host",
        )
        records = host.discover()
        assert {record.id for record in records} == {"vibecomfy.import", "vibecomfy.edit"}
        host.register()

        source_bytes = b'{"nodes":[],"links":[]}\r\n'
        source_path = tmp_path / "source.json"
        source_path.write_bytes(source_bytes)
        imported = client.media.import_file(
            project=project_id,
            path=source_path,
            idempotency_key="vibecomfy-origin-source",
        )
        assert imported.ok
        source_digest = imported.data["digest"]
        task_result = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.import",
            spec={
                "inputs": {"workflow_id": "portrait"},
                "input_digests": [{"name": "source", "digest": source_digest}],
                "transition_kind": "origin",
                "parent_task_id": None,
                "origin_task_id": None,
            },
            input_manifest=[imported.data["object_id"]],
            idempotency_key="vibecomfy-origin-task",
        )
        assert task_result.ok
        task_id = task_result.data["task_id"]

        settled = host.run(once=True)
        assert len(settled) == 1 and settled[0].state == "succeeded"
        task = client.tasks.show(task_id)
        assert task.ok
        assert task.data["state"] == "succeeded"

        output_manifest = task.data["result"]["outputs"]
        assert [item["name"] for item in output_manifest] == [
            "python",
            "companion",
            "source",
            "report",
        ]
        origin_outputs = {item["name"]: item for item in output_manifest}
        object_bytes = {
            "python": b"workflow = load('fixture')\n",
            "companion": b'{"revision_id":"origin-revision"}\n',
            "source": source_bytes,
        }
        for item in output_manifest:
            if item["name"] in object_bytes:
                assert client.media.read_bytes(item["digest"]) == object_bytes[item["name"]]
        report_output = origin_outputs["report"]
        report_bytes = client.media.read_bytes(report_output["digest"])
        assert "sha256:" + hashlib.sha256(report_bytes).hexdigest() == report_output["digest"]
        report = json.loads(report_bytes)
        assert report["transition_kind"] == "origin"
        assert report["parent_task_id"] is None
        assert report["origin_task_id"] is None
        assert report["members"]["source.json"] == source_digest
        assert report["after"]["members"] == {
            "workflow.py": origin_outputs["python"]["digest"],
            "workflow.vibe.json": origin_outputs["companion"]["digest"],
            "source.json": origin_outputs["source"]["digest"],
        }

        _assert_lifecycle_events(client, task_id)

        # A downstream edit consumes the exact project-owned artifacts settled
        # by the origin task. Its two typed operations run as one atomic batch.
        operation_bytes = json.dumps(
            {
                "schema_version": 1,
                "expected_revision": 0,
                "ops": [
                    {"op": "add_node", "class_type": "FixtureNode", "uid": "new-node"},
                    {"op": "edit_node", "target": "new-node", "field": "value", "value": 7},
                ],
            },
            sort_keys=True,
        ).encode()
        operations_path = tmp_path / "operations.json"
        operations_path.write_bytes(operation_bytes)
        operations_media = client.media.import_file(
            project=project_id,
            path=operations_path,
            idempotency_key="vibecomfy-edit-operations",
        )
        assert operations_media.ok

        edit_input_digests = {
            "python": origin_outputs["python"]["digest"],
            "companion": origin_outputs["companion"]["digest"],
            "source": origin_outputs["source"]["digest"],
            "operations": operations_media.data["digest"],
        }
        edit_task_result = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.edit",
            spec={
                "inputs": {
                    "workflow_id": "portrait",
                    "parent_revision": "origin-revision",
                    "parent_task_id": task_id,
                    "origin_task_id": task_id,
                    "transition_kind": "typed_edit",
                    "python_execution_consent": "confirmed",
                },
                "input_digests": [
                    {"name": name, "digest": digest}
                    for name, digest in edit_input_digests.items()
                ],
                "workflow_id": "portrait",
                "parent_revision": "origin-revision",
                "parent_task_id": task_id,
                "origin_task_id": task_id,
                "transition_kind": "typed_edit",
            },
            input_manifest=list(edit_input_digests.values()),
            idempotency_key="vibecomfy-typed-edit-task",
        )
        assert edit_task_result.ok
        edit_task_id = edit_task_result.data["task_id"]
        edit_host = GenericPackHost(
            pack_roots=[pack_root],
            attempt_root=tmp_path / "edit-attempt",
            client=RuntimeProtocolClient(
                daemon.endpoint, daemon.credential_path.read_text().strip()
            ),
            executor_id="vibecomfy-import-test-host",
        )
        edit_host.discover()
        edit_host.register()
        edit_settled = edit_host.run(once=True)
        assert len(edit_settled) == 1 and edit_settled[0].state == "succeeded"

        edit_task = client.tasks.show(edit_task_id)
        assert edit_task.ok and edit_task.data["state"] == "succeeded"
        edit_outputs = {item["name"]: item for item in edit_task.data["result"]["outputs"]}
        assert set(edit_outputs) == {"python", "companion", "source", "report"}
        edit_report_output = edit_outputs["report"]
        edit_report_bytes = client.media.read_bytes(edit_report_output["digest"])
        assert "sha256:" + hashlib.sha256(edit_report_bytes).hexdigest() == edit_report_output["digest"]
        edit_report = json.loads(edit_report_bytes)
        assert edit_report["transition_kind"] == "typed_edit"
        assert edit_report["python_execution_consent"] == "confirmed"
        assert edit_report["workflow_id"] == "portrait"
        assert edit_report["revision_id"] == "edited-revision"
        assert edit_report["parent_revision"] == "origin-revision"
        assert edit_report["parent_task_id"] == task_id
        assert edit_report["origin_task_id"] == task_id
        assert edit_report["before"]["members"] == {
            "workflow.py": origin_outputs["python"]["digest"],
            "workflow.vibe.json": origin_outputs["companion"]["digest"],
            "source.json": origin_outputs["source"]["digest"],
        }
        assert edit_report["after"]["members"] == {
            "workflow.py": edit_outputs["python"]["digest"],
            "workflow.vibe.json": edit_outputs["companion"]["digest"],
            "source.json": edit_outputs["source"]["digest"],
        }
        assert edit_report["requested_operations"] == json.loads(operation_bytes)["ops"]
        assert len(edit_report["operations"]) == 2
        assert edit_report["requested_operations"][1]["target"] == edit_report[
            "requested_operations"
        ][0]["uid"]
        _assert_lifecycle_events(client, edit_task_id)

        edit_two_operations = {
            "schema_version": 1,
            "expected_revision": 0,
            "ops": [
                {"op": "edit_node", "target": "new-node", "field": "value", "value": 9}
            ],
        }
        edit_two_operations_bytes = json.dumps(
            edit_two_operations, sort_keys=True
        ).encode()
        edit_two_operations_path = tmp_path / "operations-edit-two.json"
        edit_two_operations_path.write_bytes(edit_two_operations_bytes)
        edit_two_operations_media = client.media.import_file(
            project=project_id,
            path=edit_two_operations_path,
            idempotency_key="vibecomfy-edit-two-operations",
        )
        assert edit_two_operations_media.ok
        edit_two_input_digests = {
            "python": edit_outputs["python"]["digest"],
            "companion": edit_outputs["companion"]["digest"],
            "source": edit_outputs["source"]["digest"],
            "operations": edit_two_operations_media.data["digest"],
        }
        edit_two_result = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.edit",
            spec={
                "inputs": {
                    "workflow_id": "portrait",
                    "parent_revision": "edited-revision",
                    "parent_task_id": edit_task_id,
                    "origin_task_id": task_id,
                    "transition_kind": "typed_edit",
                    "python_execution_consent": "confirmed",
                },
                "input_digests": [
                    {"name": name, "digest": digest}
                    for name, digest in edit_two_input_digests.items()
                ],
                "workflow_id": "portrait",
                "parent_revision": "edited-revision",
                "parent_task_id": edit_task_id,
                "origin_task_id": task_id,
                "transition_kind": "typed_edit",
            },
            input_manifest=list(edit_two_input_digests.values()),
            idempotency_key="vibecomfy-typed-edit-two-task",
        )
        assert edit_two_result.ok
        edit_two_task_id = edit_two_result.data["task_id"]
        edit_two_host = GenericPackHost(
            pack_roots=[pack_root],
            attempt_root=tmp_path / "edit-two-attempt",
            client=RuntimeProtocolClient(
                daemon.endpoint, daemon.credential_path.read_text().strip()
            ),
            executor_id="vibecomfy-import-test-host",
        )
        edit_two_host.discover()
        edit_two_host.register()
        edit_two_settled = edit_two_host.run(once=True)
        assert len(edit_two_settled) == 1 and edit_two_settled[0].state == "succeeded"

        edit_two_task = client.tasks.show(edit_two_task_id)
        assert edit_two_task.ok and edit_two_task.data["state"] == "succeeded"
        edit_two_outputs = {
            item["name"]: item for item in edit_two_task.data["result"]["outputs"]
        }
        edit_two_report_bytes = client.media.read_bytes(edit_two_outputs["report"]["digest"])
        assert (
            "sha256:" + hashlib.sha256(edit_two_report_bytes).hexdigest()
            == edit_two_outputs["report"]["digest"]
        )
        edit_two_report = json.loads(edit_two_report_bytes)
        assert edit_two_report["transition_kind"] == "typed_edit"
        assert edit_two_report["python_execution_consent"] == "confirmed"
        assert edit_two_report["revision_id"] == "edited-twice-revision"
        assert edit_two_report["parent_revision"] == "edited-revision"
        assert edit_two_report["parent_task_id"] == edit_task_id
        assert edit_two_report["origin_task_id"] == task_id
        assert edit_two_report["before"]["members"] == {
            "workflow.py": edit_outputs["python"]["digest"],
            "workflow.vibe.json": edit_outputs["companion"]["digest"],
            "source.json": edit_outputs["source"]["digest"],
        }
        assert edit_two_report["after"]["members"] == {
            "workflow.py": edit_two_outputs["python"]["digest"],
            "workflow.vibe.json": edit_two_outputs["companion"]["digest"],
            "source.json": edit_two_outputs["source"]["digest"],
        }
        assert edit_two_report["requested_operations"] == edit_two_operations["ops"]
        _assert_lifecycle_events(client, edit_two_task_id)

        # Manual Python capture is a separate, explicitly admitted successor.
        candidate_path = tmp_path / "capture-candidate.py"
        candidate_path.write_bytes(b"workflow = load('captured')\n")
        candidate_media = client.media.import_file(
            project=project_id,
            path=candidate_path,
            idempotency_key="vibecomfy-capture-candidate",
        )
        assert candidate_media.ok
        capture_inputs = {
            "python": edit_two_outputs["python"]["digest"],
            "companion": edit_two_outputs["companion"]["digest"],
            "source": edit_two_outputs["source"]["digest"],
            "capture_python": candidate_media.data["digest"],
        }
        capture_result = client.tasks.create(
            project_id=project_id,
            capability="vibecomfy.edit",
            spec={
                "inputs": {
                    "workflow_id": "portrait",
                    "parent_revision": "edited-twice-revision",
                    "parent_task_id": edit_two_task_id,
                    "origin_task_id": task_id,
                    "transition_kind": "manual_capture",
                    "python_execution_consent": "confirmed",
                },
                "input_digests": [
                    {"name": name, "digest": digest}
                    for name, digest in capture_inputs.items()
                ],
                "workflow_id": "portrait",
                "parent_revision": "edited-twice-revision",
                "parent_task_id": edit_two_task_id,
                "origin_task_id": task_id,
                "transition_kind": "manual_capture",
            },
            input_manifest=list(capture_inputs.values()),
            idempotency_key="vibecomfy-manual-capture-task",
        )
        assert capture_result.ok
        capture_task_id = capture_result.data["task_id"]
        capture_host = GenericPackHost(
            pack_roots=[pack_root],
            attempt_root=tmp_path / "capture-attempt",
            client=RuntimeProtocolClient(
                daemon.endpoint, daemon.credential_path.read_text().strip()
            ),
            executor_id="vibecomfy-import-test-host",
        )
        capture_host.discover()
        capture_host.register()
        capture_settled = capture_host.run(once=True)
        assert len(capture_settled) == 1 and capture_settled[0].state == "succeeded"
        capture_task = client.tasks.show(capture_task_id)
        assert capture_task.ok and capture_task.data["state"] == "succeeded"
        capture_outputs = {
            item["name"]: item for item in capture_task.data["result"]["outputs"]
        }
        capture_report_output = capture_outputs["report"]
        capture_report_bytes = client.media.read_bytes(capture_report_output["digest"])
        assert (
            "sha256:" + hashlib.sha256(capture_report_bytes).hexdigest()
            == capture_report_output["digest"]
        )
        capture_report = json.loads(capture_report_bytes)
        assert capture_report["transition_kind"] == "manual_capture"
        assert capture_report["python_execution_consent"] == "confirmed"
        assert capture_report["revision_id"] == "captured-revision"
        assert capture_report["parent_revision"] == "edited-twice-revision"
        assert capture_report["parent_task_id"] == edit_two_task_id
        assert capture_report["origin_task_id"] == task_id
        assert capture_report["security_gate_audit"] == [
            {
                "kind": "explicit_manual_capture",
                "non_interactive": True,
                "assume_yes": True,
            }
        ]
        assert capture_report["before"]["members"] == {
            "workflow.py": edit_two_outputs["python"]["digest"],
            "workflow.vibe.json": edit_two_outputs["companion"]["digest"],
            "source.json": edit_two_outputs["source"]["digest"],
        }
        assert capture_report["after"]["members"] == {
            "workflow.py": capture_outputs["python"]["digest"],
            "workflow.vibe.json": capture_outputs["companion"]["digest"],
            "source.json": capture_outputs["source"]["digest"],
        }
        _assert_lifecycle_events(client, capture_task_id)
        assert _project_task_ids(client, project_id) == {
            task_id,
            edit_task_id,
            edit_two_task_id,
            capture_task_id,
        }
    finally:
        daemon.stop()
