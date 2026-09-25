from __future__ import annotations

import json
from pathlib import Path

from evals.timeline.local_inspection import inspect_attempt, inspect_case


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _case(tmp_path: Path, *, after_digest: str = "sha256:new") -> tuple[Path, Path]:
    attempt = tmp_path / "attempt"
    case_dir = attempt / "cases" / "A01"
    _write(case_dir / "canonical-before.json", {"active_media_digest": "sha256:old"})
    _write(case_dir / "canonical-after.json", {"active_media_digest": after_digest})
    _write(case_dir / "result.json", {"status": "done", "answer": "replaced media"})
    _write(case_dir / "checks.json", [{
        "id": "target-media", "check": "path_equals", "artifact": "after",
        "path": "active_media_digest", "expected": "sha256:new",
    }])
    _write(case_dir / "readback.json", {
        "status": "pass", "before_observed": True, "after_observed": True,
        "projection": "active_media_replacement.v1",
    })
    return attempt, case_dir


def test_independent_saved_readback_and_checker_distinguish_good_from_bad(tmp_path: Path) -> None:
    attempt, case_dir = _case(tmp_path)
    good = inspect_case("A01", case_dir, attempt, write=False)
    assert good["status"] == "pass"
    assert good["checks"][0]["status"] == "pass"

    # The worker says it is done, but the independently captured state is bad.
    _write(case_dir / "canonical-after.json", {"active_media_digest": "sha256:wrong"})
    bad = inspect_case("A01", case_dir, attempt, write=False)
    assert bad["status"] == "fail"
    assert bad["checks"][0]["status"] == "fail"


def test_missing_checker_or_readback_is_unreviewed_not_a_launch_gate(tmp_path: Path) -> None:
    attempt, case_dir = _case(tmp_path)
    (case_dir / "checks.json").unlink()
    (case_dir / "readback.json").unlink()
    record = inspect_case("A01", case_dir, attempt, write=False)
    assert record["status"] == "unreviewed"
    assert any("checker is not recorded" in reason for reason in record["reasons"])
    assert any("readback is not recorded" in reason for reason in record["reasons"])


def test_manual_independent_review_can_finish_an_unreviewed_case(tmp_path: Path) -> None:
    attempt, case_dir = _case(tmp_path)
    (case_dir / "readback.json").unlink()
    _write(case_dir / "manual-review.json", {
        "status": "pass", "reviewer": "independent reviewer",
        "rationale": "The saved rendered frame and target snapshot agree.",
        "evidence": ["evidence/title-frame.png", "canonical-after.json"],
    })
    record = inspect_case("A01", case_dir, attempt, write=False)
    assert record["status"] == "pass"
    assert record["disposition_source"] == "independent_manual_review"
    assert record["readback_status"] is None


def test_local_loop_manual_review_shape_is_read_without_requiring_missing_checks(tmp_path: Path) -> None:
    attempt, case_dir = _case(tmp_path)
    (case_dir / "checks.json").unlink()
    _write(case_dir / "manual-review.json", {
        "manual_review": "pass", "task_outcome": "completed",
        "evidence_sufficiency": "sufficient", "safety": "supported",
        "notes": ["reviewed canonical-after.json"],
    })
    record = inspect_case("A01", case_dir, attempt, write=False)
    assert record["status"] == "unreviewed"
    assert record["manual_review"]["status"] == "pass"
    assert any("checker is not recorded" in reason for reason in record["reasons"])


def test_attempt_reinspection_writes_case_and_aggregate_inspection_without_launch(tmp_path: Path) -> None:
    attempt, case_dir = _case(tmp_path)
    suite_path = tmp_path / "suite.json"
    _write(suite_path, {"suite_id": "mini", "cases": [{"id": "A01"}, {"id": "A02"}]})
    output = inspect_attempt(attempt, suite_path=suite_path)
    assert output["totals"] == {"fail": 0, "pass": 1, "unreviewed": 1}
    assert (attempt / "inspection.json").is_file()
    assert (case_dir / "inspection.json").is_file()
    assert output["cases"][1]["status"] == "unreviewed"
