from __future__ import annotations

import hashlib
from pathlib import Path

from astrid.sdk.remote import RemoteRuns


class _Runtime:
    def __init__(self, data: bytes = b"video-bytes") -> None:
        self.data = data
        self.digest = "sha256:" + hashlib.sha256(data).hexdigest()
        self.opened: list[list[str]] = []
        self.runs = [
            {"run_id": "R-old", "project_id": "P-1", "capability_id": "rendering.render", "status": "completed", "created_at": "2026-01-01", "task_ids": ["T-old"]},
            {"run_id": "R-failed", "project_id": "P-1", "capability_id": "rendering.render", "status": "failed", "created_at": "2026-01-03", "task_ids": ["T-failed"]},
            {"run_id": "R-new", "project_id": "P-1", "capability_id": "rendering.render", "status": "completed", "created_at": "2026-01-02", "task_ids": ["T-new"]},
        ]

    def get_project(self, ref):
        return {"project_id": "P-1", "slug": ref}

    def current_project(self):
        return {
            "project": {"project_id": "P-1", "slug": "demo"},
            "scope": "workspace",
        }

    def list_project_runs(self, project_id, *, cursor=None, limit=50):
        assert project_id == "P-1"
        return [self.runs, None]

    def get_run(self, run_id):
        return next(run for run in self.runs if run["run_id"] == run_id)

    def get_task(self, task_id):
        return {
            "task_id": task_id,
            "capability_id": "rendering.render",
            "state": "completed",
            "spec": {"inputs": {"output_name": "review.mp4"}},
            "result": {"outputs": [{"name": "video", "digest": self.digest, "size": len(self.data)}]},
        }

    def list_project_objects(self, project_id, *, cursor=None, limit=50):
        assert project_id == "P-1"
        return [[{"object_id": "O-video", "digest": self.digest, "size": len(self.data), "filename": "video"}], None]

    def get_object(self, object_id):
        assert object_id == "O-video"
        return {"data": self.data, "status": 200, "headers": {}}


def test_open_selects_latest_successful_runtime_render(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    launched: list[list[str]] = []
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")
    monkeypatch.setattr("astrid.sdk.project_render.subprocess.run", lambda argv, check: launched.append(argv))

    result = RemoteRuns(runtime).open(cache_root=tmp_path)

    assert result.ok
    assert result.data["run_id"] == "R-new"
    assert result.data["digest"] == runtime.digest
    assert Path(result.data["local_path"]).read_bytes() == runtime.data
    assert Path(result.data["local_path"]).suffix == ".mp4"
    assert launched == [["open", result.data["local_path"]]]


def test_open_exact_run_rejects_cross_project_before_download(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.runs.append({
        "run_id": "R-other", "project_id": "P-2", "capability_id": "rendering.render",
        "status": "completed", "created_at": "2026-01-04", "task_ids": ["T-other"],
    })
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")

    result = RemoteRuns(runtime).open("R-other", cache_root=tmp_path)

    assert not result.ok
    assert result.error.code == "not_found"
    assert not list(tmp_path.rglob("*.mp4"))


def test_open_fails_closed_on_ambiguous_video_outputs(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    original = runtime.get_task

    def ambiguous(task_id):
        task = original(task_id)
        task["result"]["outputs"].append(dict(task["result"]["outputs"][0]))
        return task

    runtime.get_task = ambiguous
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")

    result = RemoteRuns(runtime).open(cache_root=tmp_path)

    assert not result.ok
    assert result.error.code == "validation_error"


def test_open_verifies_downloaded_bytes(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.data = b"tampered-after-settlement"
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")

    result = RemoteRuns(runtime).open(cache_root=tmp_path)

    assert not result.ok
    assert result.error.code == "integrity_error"


def test_open_explicit_project_overrides_current_selection(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.current_project = lambda: (_ for _ in ()).throw(
        AssertionError("current selection must not be read")
    )
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")
    monkeypatch.setattr("astrid.sdk.project_render.subprocess.run", lambda argv, check: None)

    result = RemoteRuns(runtime).open(project="demo", cache_root=tmp_path)

    assert result.ok


def test_open_without_current_project_returns_typed_recovery(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.current_project = lambda: {"project": None, "scope": None}
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")

    result = RemoteRuns(runtime).open(cache_root=tmp_path)

    assert not result.ok
    assert result.error.code == "not_found"
    assert result.error.details["next_action"] == "astrid projects select <project>"


def test_open_default_timeline_uses_only_runs_with_explicit_provenance(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.runs = [
        {"run_id": "R-main-old", "project_id": "P-1", "capability_id": "rendering.render", "status": "completed", "created_at": "2026-01-01", "task_ids": ["T-main-old"], "spec": {"spec": {"timeline_ref": "TL-main"}}},
        {"run_id": "R-other-new", "project_id": "P-1", "capability_id": "rendering.render", "status": "completed", "created_at": "2026-01-04", "task_ids": ["T-other-new"], "spec": {"spec": {"timeline_ref": "TL-other"}}},
    ]
    runtime.get_project = lambda ref: {"project_id": "P-1", "slug": ref, "metadata": {"default_timeline_id": "TL-main"}}
    runtime.list_timelines = lambda project_id, *, cursor=None, limit=50: [[{"timeline_id": "TL-main", "slug": "main"}, {"timeline_id": "TL-other", "slug": "other"}], None]
    original_get_task = runtime.get_task
    runtime.get_task = lambda task_id: {**original_get_task(task_id), "spec": {"timeline_ref": "TL-main" if "main" in task_id else "TL-other"}}
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")
    monkeypatch.setattr("astrid.sdk.project_render.subprocess.run", lambda argv, check: None)

    result = RemoteRuns(runtime).open(project="demo", default_timeline=True, cache_root=tmp_path)

    assert result.ok
    assert result.data["run_id"] == "R-main-old"
    assert result.data["timeline_ref"] == "TL-main"


def test_open_timeline_rejects_render_without_authoritative_provenance(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.get_project = lambda ref: {"project_id": "P-1", "slug": ref, "metadata": {}}
    runtime.list_timelines = lambda project_id, *, cursor=None, limit=50: [[{"timeline_id": "TL-main", "slug": "main"}], None]
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")

    result = RemoteRuns(runtime).open(timeline="main", cache_root=tmp_path)

    assert not result.ok
    assert result.error.code == "not_found"
    assert "canonical timeline" in result.error.message


def test_open_default_timeline_requires_project_default(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.get_project = lambda ref: {"project_id": "P-1", "slug": ref, "metadata": {}}
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")

    result = RemoteRuns(runtime).open(project="demo", default_timeline=True, cache_root=tmp_path)

    assert not result.ok
    assert result.error.code == "not_found"
    assert "default canonical timeline" in result.error.message


def test_open_rejects_both_timeline_selectors(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")

    result = RemoteRuns(runtime).open(
        project="demo", timeline="main", default_timeline=True, cache_root=tmp_path
    )

    assert not result.ok
    assert result.error.code == "validation_error"


def test_open_hydrates_lightweight_run_rows_for_provenance(monkeypatch, tmp_path: Path) -> None:
    runtime = _Runtime()
    runtime.get_project = lambda ref: {
        "project_id": "P-1", "slug": ref,
        "metadata": {"default_timeline_id": "TL-main"},
    }
    runtime.list_timelines = lambda project_id, *, cursor=None, limit=50: [
        [{"timeline_id": "TL-main", "slug": "main"}], None
    ]
    full_run = {
        "run_id": "R-hydrated", "project_id": "P-1",
        "capability_id": "rendering.render", "status": "completed",
        "created_at": "2026-01-01", "task_ids": ["T-hydrated"],
    }
    runtime.runs = [full_run]
    runtime.list_project_runs = lambda project_id, *, cursor=None, limit=50: [
        [{key: value for key, value in full_run.items() if key != "task_ids"}], None
    ]
    original_get_run = runtime.get_run
    runtime.get_run = lambda run_id: original_get_run(run_id) | {
        "task_ids": ["T-hydrated"], "spec": {"timeline_ref": "TL-main"}
    }
    original_get_task = runtime.get_task
    runtime.get_task = lambda task_id: original_get_task(task_id) | {
        "spec": {"timeline_ref": "TL-main"}
    }
    monkeypatch.setattr("astrid.sdk.project_render.platform.system", lambda: "Darwin")
    monkeypatch.setattr("astrid.sdk.project_render.subprocess.run", lambda argv, check: None)

    result = RemoteRuns(runtime).open(project="demo", default_timeline=True, cache_root=tmp_path)

    assert result.ok
    assert result.data["run_id"] == "R-hydrated"
