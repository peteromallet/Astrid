from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from evals.timeline.local_loop import run_local_loop


ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "Astrid/evals/timeline/suite.json"
FIXTURES = ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"


def _target_root(tmp_path: Path, case_id: str = "A01") -> Path:
    root = tmp_path / "targets" / case_id
    root.mkdir(parents=True)
    (root / "target.json").write_text(json.dumps({
        "kind": "astrid.timeline-eval.public-target.v1",
        "case_id": case_id,
        "capabilities": {"edit": {"status": "available", "route": "test-route"}},
        "project_id": "disposable-project", "timeline_id": "disposable-timeline",
        "head_revision_id": "head-before",
    }), encoding="utf-8")
    return root.parent


def test_local_loop_dry_run_writes_twenty_manual_review_rows_without_scoring(tmp_path: Path) -> None:
    result = run_local_loop(SUITE, FIXTURES, attempt_root=tmp_path / "attempt")
    assert result["case_count"] == 20
    assert result["model_launched"] is False
    assert result["execution_requested"] is False
    assert result["automatic_scoring"] is False
    assert result["controls"]["failed_roots_preserved"] is True
    assert all(row["execution"] == "not_launched" for row in result["records"])
    assert all(row["task_outcome"] == "not_assessed" for row in result["records"])
    assert all(row["safety"] == "unknown" for row in result["records"])
    assert (tmp_path / "attempt/local-loop.json").is_file()


def test_local_loop_preserves_failed_case_root_and_separates_manual_review(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"
    case_root = attempt / "cases" / "A01"
    case_root.mkdir(parents=True)
    (case_root / "manual-review.json").write_text(json.dumps({
        "manual_review": "fail",
        "task_outcome": "failed", "evidence_sufficiency": "insufficient",
        "safety": "unknown", "notes": ["human review required"],
    }), encoding="utf-8")
    command = shlex.join([sys.executable, "-c", "import sys; sys.exit(3)"])
    result = run_local_loop(
        SUITE, FIXTURES, attempt_root=attempt, target_root=_target_root(tmp_path),
        execute=True, case_command=command, case_ids=["A01"], timeout_seconds=10,
    )
    row = result["records"][0]
    assert row["execution"] == "launcher_failed"
    assert row["returncode"] == 3
    assert row["task_outcome"] == "failed"
    assert row["manual_review"] == "fail"
    assert row["evidence_sufficiency"] == "insufficient"
    assert row["safety"] == "unknown"
    assert row["target_receipt"] == "cases/A01/target-receipt.json"
    assert (attempt / "cases/A01/transcript.txt").is_file()
    assert (attempt / "cases/A01/manual-review.json").is_file()
    assert "score" not in row


def test_local_loop_requires_explicit_command_for_execution(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="explicit case command"):
        run_local_loop(SUITE, FIXTURES, attempt_root=tmp_path / "attempt", execute=True)
