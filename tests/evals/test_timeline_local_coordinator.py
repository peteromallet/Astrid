from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.timeline.local_coordinator import (
    LOCAL_EVIDENCE_KIND,
    LocalCoordinatorError,
    capture_local_after,
    capture_local_before,
    capture_local_entrypoint_before,
    runtime_action_evidence_ready,
    write_local_evidence,
)
from evals.timeline.fixture_manifest import build_readiness


def test_runtime_adapter_connects_to_a_real_loopback_realm_owned_by_the_test(tmp_path):
    pytest.importorskip(
        "runtime_protocol.daemon",
        reason="local Runtime checkout is optional in Astrid-only test environments",
    )
    from evals.timeline.runtime_adapter import local_disposable_runtime

    repo_root = Path(__file__).resolve().parents[2]
    temp_parent = repo_root / ".tmp"
    temp_parent.mkdir(exist_ok=True)
    canonical_root = tmp_path.resolve() / "canonical-sentinel"
    canonical_root.mkdir()
    with local_disposable_runtime(
        scratch_parent=temp_parent,
        canonical_endpoint="http://127.0.0.1:1",
        canonical_realm_id="canonical-sentinel",
        canonical_root=canonical_root,
    ) as session:
        adapter = session.adapter
        project = adapter.create_suite_project(
            "timeline-eval-smoke-" + session.realm_id[-8:],
            idempotency_key="timeline-eval-smoke-" + session.realm_id,
        )

        assert adapter.proof.realm_id == session.realm_id
        assert adapter.proof.runtime_epoch >= 1
        assert project["reused"] is False
        listed = adapter._plain(adapter.workspace.list_projects(limit=100))
        if isinstance(listed, dict):
            listed_rows = listed.get("items", [])
        elif isinstance(listed, list) and len(listed) == 2 and isinstance(listed[0], list):
            listed_rows = listed[0]
        else:
            listed_rows = listed
        assert any(row.get("project_id") == project["project_id"] for row in listed_rows)
        assert session.root.is_dir()
        assert not any(canonical_root.iterdir())
        disposable_root = session.root
    assert not disposable_root.exists()
    assert not any(canonical_root.iterdir())


def _project(root, project_id: str) -> None:
    root.mkdir(parents=True)
    (root / "project.json").write_text(json.dumps({"project_id": project_id, "slug": project_id}), encoding="utf-8")
    (root / "payload.bin").write_bytes(b"before")


def test_local_coordinator_records_tree_readback_and_does_not_claim_target_only(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _project(source, "source-project")
    _project(target, "case-project")
    before = capture_local_before(case_id="A01", source_root=source, target_root=target)

    (target / "payload.bin").write_bytes(b"after")
    evidence = capture_local_after(before)
    path = write_local_evidence(tmp_path / "attempt", evidence)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["kind"] == LOCAL_EVIDENCE_KIND
    assert saved["readback"] == {
        "before_observed": True,
        "after_observed": True,
        "status": "fail",
        "scope": "filesystem_tree_unchanged",
        "runtime_closure_observed": False,
        "semantic_task_grade": None,
    }
    assert saved["safety"] == {
        "source_unchanged": True,
        "read_only_target": False,
        "test_target_only": None,
    }
    assert saved["after"]["target"]["files"]["payload.bin"] != saved["before"]["target"]["files"]["payload.bin"]


def test_local_coordinator_kind_cannot_satisfy_runtime_admission(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _project(source, "source-project")
    _project(target, "case-project")
    before = capture_local_before(case_id="A01", source_root=source, target_root=target)
    evidence = capture_local_after(before)
    write_local_evidence(tmp_path / "attempt", evidence)

    rows = {row.case_id: row for row in build_readiness(attempt_root=tmp_path / "attempt")}
    assert rows["A01"].operational_ready is False
    assert runtime_action_evidence_ready(
        case={"id": "A01", "kind": "action"},
        target_path=target / "project.json",
        attempt_root=tmp_path / "attempt",
    )[0] is False


def test_runtime_action_evidence_predicate_requires_current_case_scoped_pack(tmp_path):
    case_id = "A01"
    target_dir = tmp_path / "targets" / case_id
    target_dir.mkdir(parents=True)
    target = {
        "kind": "astrid.timeline-eval.public-target.v1", "case_id": case_id,
        "endpoint": "http://127.0.0.1:50999", "project_id": "disposable-project",
        "timeline_id": "disposable-timeline", "head_revision_id": "head-before",
        "scope": "selected-case-only", "read_only": False,
        "capabilities": {"edit": {"status": "available", "route": "timelines replace-parent-media"}},
        "occurrence_ids": ["occ-1"], "shot_ids": ["shot-1"],
        "shot_revision_ids": ["shot-rev-1"], "internal_revision_ids": ["internal-1"],
        "owned_media_ids": ["media-1"],
        "target_locator": {
            "readback_projection": "active_media_replacement.v1",
            "occurrence_id": "occ-1", "shot_id": "shot-1", "shot_revision_id": "shot-rev-1",
            "selector_clip_id": "clip-selector", "voice_clip_id": "clip-voice",
            "frame_overlay_clip_id": "clip-overlay", "replacement_asset_key": "replacement",
            "preserve_roles": ["timing", "voiceover", "frame-overlay"],
        },
    }
    target_path = target_dir / "target.json"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    import hashlib
    target_digest = hashlib.sha256(json.dumps(target, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    attempt_root = tmp_path / "attempt-ready"
    case_root = attempt_root / "cases" / case_id
    coordinator_root = attempt_root / "coordinator" / "cases" / case_id
    case_root.mkdir(parents=True)
    coordinator_root.mkdir(parents=True)
    (case_root / "attempt.json").write_text(json.dumps({
        "attempt_id": attempt_root.name, "case_id": case_id,
        "target_receipt_sha256": target_digest,
    }), encoding="utf-8")
    for name, value in {
        "before.json": {"target": {"head": "head-before"}},
        "after.json": {"target": {"head": "head-after"}},
        "trace.jsonl": {"event": "done"},
        "result.json": {"execution_status": "completed"},
        "graded-result.json": {"status": "passed"},
    }.items():
        (case_root / name).write_text(
            json.dumps(value) if name.endswith(".json") else json.dumps(value) + "\n",
            encoding="utf-8",
        )
    sidecar = {
        "kind": "astrid.timeline-eval.coordinator-evidence.v1", "case_id": case_id,
        "target_receipt_sha256": target_digest,
        "readback": {"status": "pass", "before_observed": True, "after_observed": True,
                     "projection": "active_media_replacement.v1"},
        "safety": {"source_unchanged": True, "test_target_only": True},
        "boundary": {"status": "verified"}, "host_final_capture": {"status": "captured"},
    }
    (coordinator_root / "readback.json").write_text(json.dumps(sidecar), encoding="utf-8")
    assert runtime_action_evidence_ready(
        case={"id": case_id, "kind": "action"}, target_path=target_path, attempt_root=attempt_root,
    ) == (True, [])

    target["head_revision_id"] = "newer-unreceipted-head"
    target_path.write_text(json.dumps(target), encoding="utf-8")
    ready, reasons = runtime_action_evidence_ready(
        case={"id": case_id, "kind": "action"}, target_path=target_path, attempt_root=attempt_root,
    )
    assert ready is False
    assert any("stale" in reason for reason in reasons)


def test_local_coordinator_rejects_overlapping_roots_and_symlinks(tmp_path):
    source = tmp_path / "source"
    _project(source, "source-project")
    nested_target = source / "nested"
    _project(nested_target, "case-project")
    with pytest.raises(LocalCoordinatorError, match="disjoint"):
        capture_local_before(case_id="A01", source_root=source, target_root=nested_target)

    linked = tmp_path / "linked"
    linked.symlink_to(source, target_is_directory=True)
    with pytest.raises(LocalCoordinatorError, match="non-symlink"):
        capture_local_before(case_id="A01", source_root=source, target_root=linked)


def test_local_coordinator_supports_offline_fixture_and_entrypoint_roots(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    (fixture / "informational").mkdir()
    (fixture / "informational" / "fixture.json").write_text(
        json.dumps({"source": {"head": "pinned-head"}}), encoding="utf-8",
    )
    (fixture / "media.bin").write_bytes(b"pinned media")
    entrypoint = tmp_path / "case" / "entrypoint"
    entrypoint.mkdir(parents=True)
    (entrypoint / "entrypoint.json").write_text(
        json.dumps({"case_id": "L01", "read_only": True}), encoding="utf-8",
    )

    before = capture_local_entrypoint_before(
        case_id="L01", pinned_fixture_root=fixture, entrypoint_root=entrypoint,
    )
    evidence = capture_local_after(before)

    assert evidence["before"]["source"]["anchor_name"] == "informational/fixture.json"
    assert evidence["after"]["target"]["document"]["read_only"] is True
    assert evidence["safety"]["source_unchanged"] is True
    assert evidence["safety"]["read_only_target"] is True
    assert evidence["readback"]["status"] == "pass"
    assert evidence["readback"]["scope"] == "filesystem_tree_unchanged"
    assert evidence["readback"]["runtime_closure_observed"] is False
