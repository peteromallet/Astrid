from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from evals.timeline import luna_native
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
        fixture_only=True,
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
        fixture_only=True,
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


def test_native_launcher_requires_explicit_isolated_target_for_real_execution(tmp_path):
    fake, _calls = _fake_omp(tmp_path)
    with pytest.raises(Exception, match="explicit disposable Runtime isolation"):
        run_attempt(
            SUITE,
            tmp_path / "attempt-no-isolation",
            fixture_root=FIXTURES,
            briefs_path=BRIEFS,
            omp_bin=str(fake),
            execute=True,
        )


def test_explicit_agent_blocked_status_survives_successful_omp_exit(tmp_path):
    script = tmp_path / "blocked-omp.py"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "from pathlib import Path\n"
        "Path('result.json').write_text(json.dumps({\n"
        "  'execution_status': 'blocked',\n"
        "  'safety': {'source_unchanged': True, 'test_target_only': True},\n"
        "  'edit_made': False\n"
        "}))\n"
        "print(json.dumps({'event': 'agent-finished'}))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    aggregate = run_attempt(
        SUITE,
        tmp_path / "attempt-blocked",
        fixture_root=FIXTURES,
        briefs_path=BRIEFS,
        omp_bin=str(script),
        execute=True,
        fixture_only=True,
        launchable_ids={"A03"},
    )
    row = next(case for case in aggregate["cases"] if case["id"] == "A03")
    result = json.loads((tmp_path / "attempt-blocked/cases/A03/result.json").read_text())
    assert result["execution_status"] == "blocked"
    assert result["launcher_process_status"] == "completed"
    assert row["status"] == "blocked"


def _isolation_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    credential = tmp_path / "credential.json"
    credential.write_text("{}", encoding="utf-8")
    contract = tmp_path / "isolation.json"
    contract.write_text("{}", encoding="utf-8")
    return credential, contract, tmp_path / "targets"


def _target() -> dict[str, object]:
    return {
        "endpoint": "http://127.0.0.1:9001",
        "project_id": "project-test",
        "timeline_id": "timeline-test",
        "head_revision_id": "head-before",
        "target_locator": {
            "occurrence_id": "occ-target",
            "shot_id": "shot-target",
            "selector_clip_id": "shot_b01",
            "voice_clip_id": "vo_b01",
            "frame_overlay_clip_id": "frame_v1",
        },
    }


def _closure() -> dict[str, object]:
    registry = {
        "assets": {
            "charcoal": {"media_id": "sha256:new-image"},
            "voice": {"media_id": "sha256:voice"},
            "frame": {"media_id": "sha256:frame"},
        }
    }
    return {
        "head_revision_id": "head-before",
        "parent_revision": {
            "revision_id": "head-before",
            "payload": {
                "occurrences": [{
                    "occurrence_id": "occ-target", "shot_id": "shot-target",
                    "shot_revision_id": "shot-rev-before", "duration_ms": 7000,
                    "placement": {"start_ms": 0},
                }],
                "clips": [{"id": "frame_v1", "asset": "frame", "at": 0, "hold": 7}],
                "registry": registry,
            },
        },
        "shot_revisions": [{
            "shot_id": "shot-target", "revision_id": "shot-rev-before",
            "internal_timeline_revision_id": "internal-before",
        }],
        "internal_timeline_revisions": [{
            "revision_id": "internal-before",
            "payload": {"clips": [
                {"id": "shot_b01", "asset": "charcoal", "at": 0, "hold": 7, "track": "picture"},
                {"id": "vo_b01", "asset": "voice", "at": 0, "hold": 6.5, "track": "vo"},
            ], "registry": registry},
        }],
    }


class _ReadbackAdapter:
    def __init__(self, closure: dict[str, object]):
        self.closure = closure

    def read_current_closure(self, project_id, timeline_id, *, head=None):
        return self.closure


def _run_live_a01(tmp_path: Path, monkeypatch, *, target: dict[str, object] | None, adapter) -> tuple[dict, Path]:
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    credential, contract, targets = _isolation_inputs(tmp_path)
    targets.mkdir()
    if target is not None:
        (targets / "A01").mkdir()
        (targets / "A01" / "target.json").write_text(json.dumps(target), encoding="utf-8")
    monkeypatch.setattr("evals.timeline.run.validate_isolated_target", lambda *_args: (True, "ok"))
    monkeypatch.setattr(luna_native, "_connect_readback_adapter", lambda **_kwargs: adapter)
    aggregate = run_attempt(
        SUITE,
        tmp_path / "attempt-live",
        fixture_root=FIXTURES,
        briefs_path=BRIEFS,
        omp_bin=str(fake),
        execute=True,
        launchable_ids={"A01"},
        isolated_endpoint="http://127.0.0.1:9001",
        isolated_credential=credential,
        isolation_contract=contract,
        prepared_targets_root=targets,
    )
    return aggregate, calls


def test_prepared_target_is_copied_and_preflight_allows_one_launch(tmp_path, monkeypatch):
    aggregate, calls = _run_live_a01(tmp_path, monkeypatch, target=_target(), adapter=_ReadbackAdapter(_closure()))
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1
    case_dir = tmp_path / "attempt-live/cases/A01"
    assert json.loads((case_dir / "target.json").read_text(encoding="utf-8"))["project_id"] == "project-test"
    assert (case_dir / "before.json").is_file()
    assert (case_dir / "after.json").is_file()
    result = json.loads((case_dir / "result.json").read_text(encoding="utf-8"))
    assert result["independent_readback"]["status"] == "pass"
    assert aggregate["case_count"] == 20


def test_missing_prepared_target_fails_closed_without_launch(tmp_path, monkeypatch):
    aggregate, calls = _run_live_a01(tmp_path, monkeypatch, target=None, adapter=_ReadbackAdapter(_closure()))
    assert not calls.exists() or not calls.read_text(encoding="utf-8").strip()
    result = json.loads((tmp_path / "attempt-live/cases/A01/result.json").read_text(encoding="utf-8"))
    assert result["execution_status"] == "setup_failed"
    assert "prepared public target" in result["failure_cause"]["summary"]
    assert next(row for row in aggregate["cases"] if row["id"] == "A01")["status"] == "setup_failed"


def test_pre_readback_failure_fails_closed_without_launch(tmp_path, monkeypatch):
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    credential, contract, targets = _isolation_inputs(tmp_path)
    targets.mkdir()
    (targets / "A01").mkdir()
    (targets / "A01" / "target.json").write_text(json.dumps(_target()), encoding="utf-8")
    monkeypatch.setattr("evals.timeline.run.validate_isolated_target", lambda *_args: (True, "ok"))
    monkeypatch.setattr(luna_native, "_connect_readback_adapter", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("stale target")))
    run_attempt(
        SUITE,
        tmp_path / "attempt-preflight-fail",
        fixture_root=FIXTURES,
        briefs_path=BRIEFS,
        omp_bin=str(fake),
        execute=True,
        launchable_ids={"A01"},
        isolated_endpoint="http://127.0.0.1:9001",
        isolated_credential=credential,
        isolation_contract=contract,
        prepared_targets_root=targets,
    )
    assert not calls.exists() or not calls.read_text(encoding="utf-8").strip()
    result = json.loads((tmp_path / "attempt-preflight-fail/cases/A01/result.json").read_text(encoding="utf-8"))
    assert result["execution_status"] == "setup_failed"
    assert "refusing to launch OMP" in result["failure_cause"]["summary"]
