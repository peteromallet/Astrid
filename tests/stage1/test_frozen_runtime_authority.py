from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from astrid.packs.rendering.executors.timeline_visualize import frozen


def test_frozen_view_has_no_local_run_authority_import() -> None:
    source = Path(frozen.__file__).read_text(encoding="utf-8")
    assert "astrid.core.project.run" not in source
    assert "load_run_record" not in source
    assert "resolve_record_path" not in source


def test_frozen_view_fails_closed_when_runtime_run_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "demo"
    manifest = project / "runs" / "run-1" / "agent-view" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(frozen, "_kernel_frozen_run_info", lambda *_args: None)

    with pytest.raises(frozen.ContainmentError, match="runtime run ownership is unavailable"):
        frozen._verify_run_ownership(
            manifest,
            project,
            {"inputs": {"timeline_source": ["demo"]}},
            "timeline-1",
        )


def test_managed_pack_rehydration_uses_settled_filename_and_manifest_binding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "demo"
    manifest = project / "runs" / "run-1" / "agent-view" / "manifest.json"
    manifest.parent.mkdir(parents=True)
    members = {
        "manifest.json": json.dumps(
            {
                "schema_version": 1,
                "kind": "timeline_visualize",
                "inputs": {},
                "outputs": [
                    {
                        "path": "structure.md",
                        "content_hash": "sha256:" + "0" * 64,
                        "bytes": 0,
                    }
                ],
            },
            sort_keys=True,
        ).encode(),
        "structure.md": b"# frozen structure\n",
        "pack-hashes.json": b"{}\n",
    }
    # Rebuild the manifest's declared member hash after the fixture bytes are
    # known; the test is about runtime output identity, not hand-authored
    # digest values.
    manifest_document = json.loads(members["manifest.json"])
    structure = members["structure.md"]
    manifest_document["outputs"][0]["content_hash"] = (
        "sha256:" + hashlib.sha256(structure).hexdigest()
    )
    manifest_document["outputs"][0]["bytes"] = len(structure)
    members["manifest.json"] = json.dumps(
        manifest_document, sort_keys=True
    ).encode()
    for name, data in members.items():
        (manifest.parent / name).write_bytes(data)
    objects = {
        hashlib.sha256(data).hexdigest(): data for data in members.values()
    }
    outputs = [
        {
            "name": "pack_root",
            "filename": f"agent-view/{name}",
            "digest": "sha256:" + hashlib.sha256(data).hexdigest(),
            "size": len(data),
        }
        for name, data in members.items()
    ]

    class Runtime:
        def list_projects(self, **_kwargs):
            return ([{"slug": "demo", "project_id": "project-1"}], None)

        def list_project_runs(self, _project_id, **_kwargs):
            return ([{
                "run_id": "run-1",
                "capability": "rendering.timeline_visualize",
                "status": "completed",
            }], None)

        def list_run_events(self, _run_id, **_kwargs):
            return ([{
                "event_type": "task.completed",
                "payload": {"result": {"outputs": outputs}},
            }], None)

        def get_object(self, digest):
            return objects[digest.removeprefix("sha256:")]

    monkeypatch.setattr(frozen, "_workspace_runtime_client", lambda: Runtime())
    rehydrated = frozen._rehydrate_managed_pack(
        manifest, project_root=project
    )
    assert rehydrated is not None
    assert rehydrated.read_bytes() == members["manifest.json"]
    assert (rehydrated.parent / "structure.md").read_bytes() == structure
    frozen._verify_runtime_output_binding(
        manifest,
        manifest_document,
        runtime_outputs=outputs,
    )
    frozen.discard_rehydrated_pack(rehydrated)
