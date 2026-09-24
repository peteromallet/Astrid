import json
from pathlib import Path

from evals.timeline.fixture_manifest import (
    _fixture_requirement_reasons,
    build_readiness,
    validate_case,
)


def _dump(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_fixture_case_readiness_checks_targets_media_units_and_lifecycle(tmp_path):
    ready = {
        "id": "L01",
        "targets": {"occurrence_id": "occ-1", "head": "rev-1"},
        "media_handles": [{"id": "img-1", "digest": "sha256:abc"}],
        "units": {"time": "milliseconds", "frame_rate": "source_manifest"},
        "lifecycle": {"state": "read_only", "reset": "fresh_fixture"},
    }
    partial = {
        "id": "L02",
        "targets": {"occurrence_id": "{UNRESOLVED}"},
        "media_handles": [],
        "media_requirement": "none",
        "units": {"time": "not_applicable"},
        "lifecycle": {"state": "read_only"},
    }

    result_ready = validate_case(ready, "navigation", tmp_path / "info.json")
    result_partial = validate_case(partial, "navigation", tmp_path / "info.json")

    assert result_ready.readiness == "ready"
    assert result_partial.readiness == "blocked"
    assert any("target identities" in reason for reason in result_partial.reasons)


def test_build_readiness_reports_actual_fixture_states_per_case(tmp_path):
    suite_path = tmp_path / "suite.json"
    fixture_root = tmp_path / "fixtures"
    _dump(suite_path, {"cases": [
        {"id": "L01", "kind": "navigation"},
        {"id": "L02", "kind": "navigation"},
        {"id": "A01", "kind": "action"},
    ]})
    _dump(fixture_root / "informational" / "fixture.json", {"cases": [
        {
            "id": "L01", "targets": {"occurrence_id": "occ-1"},
            "media_handles": [{"id": "img-1", "digest": "sha256:abc"}],
            "units": {"time": "milliseconds"}, "lifecycle": {"state": "read_only"},
        }
    ]})
    _dump(fixture_root / "action" / "manifest.json", {"cases": [
        {
            "id": "A01", "targets": {"occurrence_id": "occ-1"},
            "media": [{"id": "new-img", "digest": "sha256:def"}],
            "units": {"time": "frames", "fps": "30/1"},
            "lifecycle": {"state": "fresh_derived_timeline", "reset": "new_timeline"},
        }
    ]})

    rows = {row.case_id: row for row in build_readiness(suite_path, fixture_root)}

    assert rows["L01"].readiness == "blocked"
    assert rows["L02"].readiness == "blocked"
    assert rows["A01"].readiness == "blocked"
    assert rows["L02"].reasons == ["case entry is missing from fixture manifest"]
    assert all(not row.operational_ready for row in rows.values())


def test_real_fixture_matrix_checks_sidecar_bytes_and_separates_operational_readiness():
    rows = {row.case_id: row for row in build_readiness()}

    assert rows["A01"].readiness == "fixture_ready"
    assert rows["A09"].readiness == "fixture_ready"
    assert rows["A10"].readiness == "fixture_ready"
    assert rows["L04"].readiness == "blocked"
    assert rows["L05"].readiness == "blocked"
    assert rows["L06"].readiness == "fixture_ready"
    assert rows["L07"].readiness == "fixture_ready"
    assert rows["L09"].readiness == "blocked"
    assert rows["L10"].readiness == "fixture_ready"
    assert any("historical video alternative" in reason for reason in rows["L05"].reasons)
    assert not any(row.operational_ready for row in rows.values())


def test_declared_fixture_requirements_follow_actual_fields_not_case_ids(tmp_path):
    manifest = {"targets": {"shot": {"alternatives": []}}}
    requirement = {
        "id": "probe-any-name",
        "fixture_requirements": [{
            "scope": "targets",
            "path": "shot.alternatives",
            "predicate": "explicit",
            "reason": "retained alternatives are unavailable",
        }],
    }
    assert _fixture_requirement_reasons(requirement, manifest, tmp_path / "fixture.json") == [
        "retained alternatives are unavailable",
    ]
    manifest["targets"]["shot"]["alternatives"] = [{"media_id": "sha256:retained"}]
    assert _fixture_requirement_reasons(requirement, manifest, tmp_path / "fixture.json") == []


def test_attempt_evidence_marks_only_fixture_ready_case_operational(tmp_path):
    attempt_root = tmp_path / "attempt-fresh-20260923-01"
    for case_id in ("A01", "L04"):
        case_dir = attempt_root / "cases" / case_id
        case_dir.mkdir(parents=True)
        identity = {
            "attempt_id": attempt_root.name,
            "case_id": case_id,
        }
        _dump(case_dir / "attempt.json", {
            **identity,
            "kind": "astrid.timeline-eval.case-attempt.v1",
            "fresh_context": True,
            "session_id": f"luna-{case_id}-session",
            "started_at": "2026-09-23T13:00:00Z",
        })
        (case_dir / "trace.jsonl").write_text('{"event":"opened_fixture"}\n', encoding="utf-8")
        _dump(case_dir / "result.json", {**identity, "execution_status": "completed"})
        _dump(case_dir / "graded-result.json", {**identity, "status": "failed", "setup_status": "ready"})

    rows = {row.case_id: row for row in build_readiness(attempt_root=attempt_root)}

    assert rows["A01"].readiness == "fixture_ready"
    assert rows["A01"].operational_ready is True
    assert rows["A01"].operational_reasons == []
    assert rows["L04"].readiness == "blocked"
    assert rows["L04"].operational_ready is False
    assert "fixture prerequisites are blocked" in rows["L04"].operational_reasons[0]


def test_blocked_and_setup_failed_attempts_remain_non_operational(tmp_path):
    attempt_root = tmp_path / "attempt-fresh-20260923-02"
    case_dir = attempt_root / "cases" / "A02"
    case_dir.mkdir(parents=True)
    identity = {"attempt_id": attempt_root.name, "case_id": "A02"}
    _dump(case_dir / "attempt.json", {
        **identity,
        "kind": "astrid.timeline-eval.case-attempt.v1",
        "fresh_context": True,
        "session_id": "luna-A02-session",
        "started_at": "2026-09-23T13:00:00Z",
    })
    (case_dir / "trace.jsonl").write_text('{"event":"preflight"}\n', encoding="utf-8")
    _dump(case_dir / "result.json", {**identity, "execution_status": "blocked"})
    _dump(case_dir / "graded-result.json", {**identity, "status": "setup_failed", "setup_status": "failed"})

    row = {item.case_id: item for item in build_readiness(attempt_root=attempt_root)}["A02"]

    assert row.readiness == "fixture_ready"
    assert row.operational_ready is False
    assert any("agent execution ended in blocked" in reason for reason in row.operational_reasons)
    assert any("grading ended in setup_failed" in reason for reason in row.operational_reasons)
