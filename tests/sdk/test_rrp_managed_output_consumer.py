from __future__ import annotations

import hashlib
import json
from pathlib import Path

from banodoco_workspace_client.generated import WorkspaceClient as GeneratedWorkspaceClient

from astrid.sdk.project_render import open_render
from astrid.sdk.remote import RemoteTasks
from astrid.sdk.workspace_client import WorkspaceClient


def _managed_output(*, project_id: str, run_id: str, task_id: str, object_id: str, size: int) -> dict:
    return {
        "association_id": "association-video",
        "project_id": project_id,
        "run_id": run_id,
        "task_id": task_id,
        "attempt_id": "attempt-video",
        "output_port": "video",
        "group_key": "main",
        "variant_key": "original",
        "selector": {"group_key": "main", "variant_key": "original"},
        "object_id": object_id,
        "digest": object_id,
        "manifest_ref": "sha256:" + "a" * 64,
        "size": size,
        "filename": "minkhole-review-v13.mp4",
        "media_type": "video/mp4",
        "ordinal": 0,
        "role": "result",
        "producer": {"id": "astrid-renderer"},
        "provenance": {"capability_id": "rendering.render", "fence": 3},
        "durability": "durable",
        "state": "available",
        "version": 1,
        "lifecycle": {"state": "available", "version": 1},
    }


def test_generated_and_astrid_wrappers_use_exact_managed_output_reads() -> None:
    wire = _managed_output(
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        object_id="sha256:" + "b" * 64,
        size=7,
    )
    calls: list[tuple[str, str]] = []

    def transport(method, path, headers, body):
        calls.append((method, path))
        if path.startswith("/v1/tasks/"):
            return 200, {}, json.dumps({"items": [wire], "next_cursor": None}).encode()
        return 200, {}, json.dumps(wire).encode()

    generated = GeneratedWorkspaceClient("http://runtime", transport=transport)
    astrid_client = object.__new__(WorkspaceClient)
    astrid_client._generated = generated

    page = astrid_client.list_managed_outputs("task-1")
    item = astrid_client.get_managed_output("association-video")
    assert page[0][0]["association_id"] == "association-video"
    assert item["object_id"] == "sha256:" + "b" * 64
    assert calls == [
        ("GET", "/v1/tasks/task-1/managed-outputs"),
        ("GET", "/v1/managed-outputs/association-video"),
    ]

    remote = object.__new__(RemoteTasks)
    remote._client = astrid_client
    assert remote.list_managed_outputs("task-1").data[0][0]["association_id"] == "association-video"
    assert remote.get_managed_output("association-video").data["object_id"] == "sha256:" + "b" * 64


class ManagedOutputRuntime:
    def __init__(self, *, use_get: bool) -> None:
        self.data = b"managed-video"
        self.digest = "sha256:" + hashlib.sha256(self.data).hexdigest()
        self.project_id = "project-1"
        self.timeline_id = "timeline-1"
        self.run_id = "run-1"
        self.task_id = "task-1"
        self.use_get = use_get
        self.list_calls: list[str] = []
        self.get_calls: list[str] = []
        self.object_calls: list[str] = []

    def get_project(self, project_id):
        return {"project_id": project_id}

    def list_timelines(self, project_id, *, cursor=None, limit=50):
        return [[{"timeline_id": self.timeline_id, "slug": "main"}], None]

    def list_project_runs(self, project_id, *, cursor=None, limit=50):
        return [[{
            "run_id": self.run_id,
            "project_id": self.project_id,
            "capability_id": "rendering.render",
            "status": "completed",
            "created_at": "2026-09-11T00:00:00Z",
            "task_ids": [self.task_id],
            "spec": {"timeline_id": self.timeline_id},
        }], None]

    def get_run(self, run_id):
        return self.list_project_runs(self.project_id)[0][0]

    def get_task(self, task_id):
        output = {"name": "video", "digest": self.digest, "size": len(self.data)}
        if self.use_get:
            output["association_id"] = "association-video"
        return {
            "task_id": task_id,
            "capability_id": "rendering.render",
            "state": "completed",
            "attempt_id": "attempt-video",
            "spec": {"timeline_id": self.timeline_id},
            "result": {"outputs": [output]},
        }

    def managed_output(self):
        return _managed_output(
            project_id=self.project_id,
            run_id=self.run_id,
            task_id=self.task_id,
            object_id=self.digest,
            size=len(self.data),
        )

    def list_managed_outputs(self, task_id):
        self.list_calls.append(task_id)
        return ([self.managed_output()], None)

    def get_managed_output(self, association_id):
        self.get_calls.append(association_id)
        return self.managed_output()

    def get_object(self, object_id):
        self.object_calls.append(object_id)
        return {"data": self.data}


def _open(runtime: ManagedOutputRuntime, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")
    opened: list[Path] = []
    result = open_render(
        runtime,
        runtime.project_id,
        runtime.timeline_id,
        cache_root=tmp_path,
        opener=opened.append,
    )
    return result, opened


def test_rrp_uses_task_scoped_managed_output_list_for_missing_association(monkeypatch, tmp_path):
    runtime = ManagedOutputRuntime(use_get=False)
    result, opened = _open(runtime, tmp_path, monkeypatch)

    assert result.ok
    assert runtime.list_calls == [runtime.task_id]
    assert runtime.get_calls == []
    assert runtime.object_calls == [runtime.digest]
    assert result.data["managed_object_reference"] == runtime.digest
    assert result.data["manifest_ref"] == "sha256:" + "a" * 64
    assert result.data["association_id"] == "association-video"
    assert result.data["filename"] == "minkhole-review-v13.mp4"
    assert opened == [Path(result.data["local_path"])]


def test_rrp_gets_named_managed_output_for_partial_association(monkeypatch, tmp_path):
    runtime = ManagedOutputRuntime(use_get=True)
    result, _ = _open(runtime, tmp_path, monkeypatch)

    assert result.ok
    assert runtime.list_calls == []
    assert runtime.get_calls == ["association-video"]
    assert runtime.object_calls == [runtime.digest]
