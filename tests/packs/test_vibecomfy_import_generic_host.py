from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
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


def _write_fake_vibecomfy_package(pack_root: Path) -> None:
    package_root = pack_root / "vibecomfy"
    executor_root = package_root / "executors" / "import"
    service_root = package_root / "porting"
    executor_root.mkdir(parents=True)
    service_root.mkdir(parents=True)
    shutil.copyfile(IMPORT_CAPABILITY, executor_root / "executor.yaml")
    (package_root / "pack.yaml").write_text(
        "schema_version: 2\nid: vibecomfy\nname: Fixture VibeComfy\nversion: 1.0.0\n"
        "capabilities: [import_workflow]\ncontent:\n  executors: executors\n",
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
        "        'workflow_identity': 'workflow:' + workflow_id, 'revision_id': 'origin-revision',\n"
        "        'parent_revision': None, 'parent_task_id': None, 'origin_task_id': None, 'before': None,\n"
        "        'after': {'revision_id': 'origin-revision', 'members': digests}, 'members': digests,\n"
        "        'readiness': {'status': 'ready'}, 'validation': {'status': 'structural'}}\n"
        "    return SimpleNamespace(source_bytes=source_bytes, python_bytes=python,\n"
        "        companion_bytes=companion, report=report)\n",
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


def test_import_capability_runs_as_one_runtime_task_and_settles_origin_artifacts(
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
        record = host.discover()[0]
        assert record.id == "vibecomfy.import"
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
        object_bytes = {
            "python": b"workflow = load('fixture')\n",
            "companion": b'{"revision_id":"origin-revision"}\n',
            "source": source_bytes,
        }
        for item in output_manifest:
            if item["name"] in object_bytes:
                assert client.media.read_bytes(item["digest"]) == object_bytes[item["name"]]
        report_output = next(item for item in output_manifest if item["name"] == "report")
        report_bytes = client.media.read_bytes(report_output["digest"])
        report = json.loads(report_bytes)
        assert report["transition_kind"] == "origin"
        assert report["parent_task_id"] is None
        assert report["origin_task_id"] is None
        assert report["members"]["source.json"] == source_digest

        events = client.tasks.events(task_id)
        assert events.ok
        event_records = events.data
        if isinstance(event_records, dict):
            event_records = event_records.get("items", event_records.get("events", []))
        elif (
            isinstance(event_records, (list, tuple))
            and len(event_records) == 2
            and isinstance(event_records[0], list)
        ):
            event_records = event_records[0]
        event_types = [
            (
                item.get("event_type", item.get("kind"))
                if isinstance(item, dict)
                else getattr(item, "event_type", None)
                or getattr(item, "kind", None)
                or getattr(item, "payload", {}).get("kind")
            )
            for item in event_records
        ]
        assert event_types.count("task.admitted") == 1
        assert event_types.count("task.completed") == 1
    finally:
        daemon.stop()
