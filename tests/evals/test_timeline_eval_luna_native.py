from __future__ import annotations

import json
import os
from pathlib import Path

from evals.timeline.luna_native import DEFAULT_MODEL, run_attempt


REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE = REPO_ROOT / "Astrid/evals/timeline/suite.json"
FIXTURES = REPO_ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"
BRIEFS = REPO_ROOT / "Astrid/evals/timeline/cases/agent_briefs.json"


def _fake_omp(tmp_path: Path) -> tuple[Path, Path]:
    calls = tmp_path / "omp-calls.jsonl"
    script = tmp_path / "fake-omp.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "case = Path.cwd().name\n"
        "assert not (Path.cwd() / 'checks.json').exists(), 'hidden checks leaked before launch'\n"
        "with Path(os.environ['LUNA_CALL_LOG']).open('a', encoding='utf-8') as h:\n"
        "    h.write(json.dumps({'case': case, 'argv': sys.argv[1:]}) + '\\n')\n"
        "print(json.dumps({'event': 'fake-agent-complete', 'case': case}))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script, calls


def test_native_launcher_invokes_each_fixture_ready_case_once_in_fresh_contexts(tmp_path, monkeypatch):
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    aggregate = run_attempt(
        SUITE,
        tmp_path / "attempt-1",
        fixture_root=FIXTURES,
        briefs_path=BRIEFS,
        omp_bin=str(fake),
        execute=True,
    )

    rows = {row["id"]: row for row in aggregate["cases"]}
    call_rows = [json.loads(line) for line in calls.read_text(encoding="utf-8").splitlines()]
    assert len(call_rows) == 14
    assert {row["case"] for row in call_rows} == {
        case_id for case_id, row in rows.items() if case_id not in {"L04", "L05", "L06", "L07", "L09", "L10"}
    }
    assert all("--no-session" in row["argv"] for row in call_rows)
    assert all(row["argv"][row["argv"].index("--model") + 1] == DEFAULT_MODEL for row in call_rows)
    assert all("--print" in row["argv"] for row in call_rows)
    assert aggregate["case_count"] == 20
    assert len(list((tmp_path / "attempt-1" / "cases").iterdir())) == 20
    for case_id, report in rows.items():
        case_dir = tmp_path / "attempt-1" / "cases" / case_id
        assert (case_dir / "attempt.json").is_file()
        assert (case_dir / "trace.jsonl").is_file()
        assert (case_dir / "result.json").is_file()
        assert (case_dir / "checks.json").is_file()
        if case_id in {"L04", "L05", "L06", "L07", "L09", "L10"}:
            assert json.loads((case_dir / "result.json").read_text())["execution_status"] == "fixture_blocked"
        else:
            attempt = json.loads((case_dir / "attempt.json").read_text())
            assert attempt["fresh_context"] is True
            assert json.loads((case_dir / "result.json").read_text())["execution_status"] == "completed"


def test_hidden_checks_are_materialized_only_after_agent_process_exits(tmp_path, monkeypatch):
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    run_attempt(
        SUITE,
        tmp_path / "attempt-2",
        fixture_root=FIXTURES,
        briefs_path=BRIEFS,
        omp_bin=str(fake),
        execute=True,
        launchable_ids={"A03"},
    )
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1
    checks = json.loads((tmp_path / "attempt-2/cases/A03/checks.json").read_text())
    assert checks and any(check["check"] == "order" for check in checks)
    public = json.loads((tmp_path / "attempt-2/cases/A03/brief.json").read_text())
    assert not any(key in public for key in ("invariants", "success_checks", "required_artifacts", "hidden_checks"))


def test_dry_run_never_invokes_omp_or_creates_case_records(tmp_path, monkeypatch):
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    result = run_attempt(
        SUITE,
        tmp_path / "attempt-dry",
        fixture_root=FIXTURES,
        briefs_path=BRIEFS,
        omp_bin=str(fake),
        execute=False,
    )
    assert result["execution"] == "dry_run"
    assert not calls.exists()
    assert (tmp_path / "attempt-dry/cases").is_dir()
    assert not any((tmp_path / "attempt-dry/cases").iterdir())
