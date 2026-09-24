from __future__ import annotations

import json
from pathlib import Path

from evals.timeline.fixture_preparation import (
    build_preparation_table,
    prepare_public_case,
    write_preparation_table,
)


ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "Astrid/evals/timeline/suite.json"
FIXTURES = ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"


def test_preparation_table_has_all_cases_and_preserves_real_blockers(tmp_path: Path) -> None:
    rows = build_preparation_table(SUITE, FIXTURES)
    assert len(rows) == 20
    by_id = {row.case_id: row for row in rows}
    assert by_id["A01"].kind == "action"
    assert by_id["L05"].status == "blocked-essential-input"
    assert any("historical video alternative" in blocker for blocker in by_id["L05"].blockers)
    assert by_id["L10"].kind == "navigation"
    assert any("afplay" in tool for tool in by_id["L10"].available_tools)
    table = write_preparation_table(rows, tmp_path / "preparation.md")
    text = table.read_text(encoding="utf-8")
    assert text.count("| A") + text.count("| L") >= 20
    assert "answer" not in text.lower()


def test_prepare_public_action_case_fails_closed_without_target(tmp_path: Path) -> None:
    result = prepare_public_case(
        {"id": "A02", "kind": "action"}, fixture_root=FIXTURES,
        destination=tmp_path / "A02",
    )
    assert result["status"] == "blocked-essential-input"
    assert not (tmp_path / "A02" / "target.json").exists()


def test_prepare_public_navigation_case_materializes_selected_entrypoint(tmp_path: Path) -> None:
    result = prepare_public_case(
        {"id": "L01", "kind": "navigation"}, fixture_root=FIXTURES,
        destination=tmp_path / "L01",
    )
    assert result["status"] == "prepared"
    entrypoint = json.loads((tmp_path / "L01/entrypoint/entrypoint.json").read_text())
    assert entrypoint["read_only"] is True
    assert entrypoint["case_id"] == "L01"
