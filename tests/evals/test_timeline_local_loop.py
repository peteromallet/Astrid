from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import evals.timeline.local_loop as local_loop
from evals.timeline.local_loop import ProcessResult, run_local_loop

ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "Astrid/evals/timeline/suite.json"


def _fake_preparer(case_id, *, case_root, **kwargs):
    case_root.mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        fixture_receipt={"case_id": case_id},
        baseline_observer=lambda: {"case_id": case_id}, close=lambda: None,
    )


def test_local_loop_dry_run_writes_twenty_manual_review_rows_without_scoring(tmp_path: Path) -> None:
    result = run_local_loop(SUITE, attempt_root=tmp_path / "attempt")
    assert result["case_count"] == 20
    assert result["model_launched"] is False
    assert result["execution_requested"] is False
    assert result["automatic_scoring"] is False
    assert result["controls"]["failed_roots_preserved"] is True
    assert all(row["execution"] == "not_launched" for row in result["records"])
    assert all(row["task_outcome"] == "not_assessed" for row in result["records"])
    assert all(row["safety"] == "unknown" for row in result["records"])
    assert (tmp_path / "attempt/local-loop.json").is_file()
    assert (tmp_path / "attempt/cases/A01/work/project").is_dir()
    brief = tmp_path / "attempt/cases/A01/work/brief.md"
    assert brief.is_file()
    assert "result.json" in brief.read_text(encoding="utf-8")


def test_local_loop_continues_after_process_failure_and_records_result_reporting_defect(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_loop, "render_case_brief", lambda case_id, *, prepared, doc_path: f"prepared {case_id}\n")
    attempt = tmp_path / "attempt"
    launches: list[tuple[list[str], Path]] = []

    def fake_launcher(argv, cwd, timeout, trace_path, log_path):
        launches.append((list(argv), cwd))
        log_path.write_text("fake agent", encoding="utf-8")
        trace_path.write_text('{"event":"done"}\n', encoding="utf-8")
        if len(launches) == 1:
            return ProcessResult(3)
        if len(launches) == 2:
            # The loop record is durable before the next process is launched.
            partial = json.loads((attempt / "local-loop.json").read_text())
            assert partial["case_count"] == 1
            assert partial["records"][0]["case_id"] == "A01"
            (cwd / "result.json").write_text('{bad json', encoding="utf-8")
        else:
            (cwd / "result.json").write_text(json.dumps({
                "status": "completed", "answer": "Finished", "evidence": [],
            }), encoding="utf-8")
        return ProcessResult(0)

    result = run_local_loop(
        SUITE, attempt_root=attempt, execute=True,
        process_launcher=fake_launcher, case_ids=["A01", "A02", "A03"], timeout_seconds=10,
        case_preparer=_fake_preparer,
    )
    assert [row["execution"] for row in result["records"]] == ["launcher_failed", "completed", "completed"]
    assert result["launch_count"] == 3 and result["model_launched"] is True
    assert result["records"][0]["returncode"] == 3
    assert "OMP exited with status 3" in result["records"][0]["notes"]
    assert "reporting defect: result.json is malformed" in result["records"][1]["notes"][0]
    assert result["records"][1]["task_outcome"] == "not_assessed"
    assert result["records"][1]["manual_review"] == "undetermined"
    assert (attempt / "cases/A02/trace.jsonl").is_file()
    assert (attempt / "cases/A02/before.json").is_file()
    assert (attempt / "cases/A02/after.json").is_file()
    assert launches[0][1] == attempt / "cases/A01/work"
    assert launches[1][1] == attempt / "cases/A02/work"
    assert launches[2][1] == attempt / "cases/A03/work"
    assert "--no-session" in launches[0][0]
    assert launches[0][0][launches[0][0].index("--model") + 1] == "openai-codex/gpt-5.6-luna"
    assert (attempt / "cases/A01/agent.log").is_file()
    assert (attempt / "cases/A02/work/brief.md").is_file()


def test_local_loop_continues_after_case_timeout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_loop, "render_case_brief", lambda case_id, *, prepared, doc_path: f"prepared {case_id}\n")
    def fake_launcher(argv, cwd, timeout, trace_path, log_path):
        trace_path.write_text("", encoding="utf-8")
        log_path.write_text("", encoding="utf-8")
        if cwd.name == "work" and cwd.parent.name == "A01":
            return ProcessResult(None, timed_out=True)
        (cwd / "result.json").write_text(json.dumps({
            "status": "completed", "answer": "Finished", "evidence": [],
        }), encoding="utf-8")
        return ProcessResult(0)

    result = run_local_loop(
        SUITE, attempt_root=tmp_path / "attempt", execute=True,
        process_launcher=fake_launcher, case_ids=["A01", "A02"], case_preparer=_fake_preparer,
    )
    assert [row["execution"] for row in result["records"]] == ["timed_out", "completed"]
    timeout = json.loads((tmp_path / "attempt/cases/A01/timeout.json").read_text())
    assert timeout["automatic_retry"] is False
    assert timeout["partial_trace_preserved"] is True
    assert timeout["partial_stderr_preserved"] is True


def test_local_loop_accepts_worker_result_and_preserves_manual_review(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_loop, "render_case_brief", lambda case_id, *, prepared, doc_path: f"prepared {case_id}\n")
    attempt = tmp_path / "attempt"
    case_root = attempt / "cases" / "A01"
    case_root.mkdir(parents=True)
    (case_root / "manual-review.json").write_text(json.dumps({
        "manual_review": "fail", "task_outcome": "failed",
        "evidence_sufficiency": "insufficient", "safety": "unknown",
        "notes": ["human review required"],
    }), encoding="utf-8")

    def fake_launcher(argv, cwd, timeout, trace_path, log_path):
        (cwd / "result.json").write_text(json.dumps({
            "status": "failed", "answer": "Attempted but did not complete.", "evidence": [],
        }), encoding="utf-8")
        trace_path.write_text('{"event":"done"}\n', encoding="utf-8")
        log_path.write_text("", encoding="utf-8")
        return ProcessResult(0)

    result = run_local_loop(
        SUITE, attempt_root=attempt, execute=True,
        process_launcher=fake_launcher, case_ids=["A01"], timeout_seconds=10,
        case_preparer=_fake_preparer,
    )
    row = result["records"][0]
    assert row["execution"] == "completed"
    assert row["returncode"] == 0
    assert row["task_outcome"] == "failed"
    assert row["manual_review"] == "fail"
    assert row["evidence_sufficiency"] == "insufficient"
    assert row["safety"] == "unknown"
    assert row["result"] == "cases/A01/work/result.json"
    assert (case_root / "manual-review.json").is_file()
    assert "score" not in row


def test_local_loop_dry_run_does_not_launch_an_external_command(tmp_path: Path) -> None:
    result = run_local_loop(
        SUITE, attempt_root=tmp_path / "attempt", execute=False,
        case_ids=["A01"],
    )
    assert result["records"][0]["execution"] == "not_launched"


def test_execute_prepares_captures_and_closes_before_returning(tmp_path: Path, monkeypatch) -> None:
    attempt = tmp_path / "attempt"
    lifecycle: list[str] = []
    prepared = SimpleNamespace(
        fixture_receipt={"kind": "test-fixture"},
        baseline_observer=lambda: (lifecycle.append("capture"), {"sequence": lifecycle.count("capture")})[1],
        close=lambda: lifecycle.append("close"),
    )
    monkeypatch.setattr(local_loop, "render_case_brief", lambda case_id, *, prepared, doc_path: f"prepared {case_id}\n")

    def prepare(case_id, **kwargs):
        lifecycle.append("prepare")
        assert kwargs["fixture_root"] == tmp_path / "fixtures"
        assert kwargs["canonical_endpoint"] == "http://127.0.0.1:9"
        return prepared

    def launcher(argv, cwd, timeout, trace_path, log_path):
        lifecycle.append("launch")
        assert lifecycle == ["prepare", "capture", "launch"]
        (cwd / "result.json").write_text(json.dumps({
            "status": "completed", "answer": "Finished", "evidence": [],
        }), encoding="utf-8")
        trace_path.write_text("", encoding="utf-8")
        log_path.write_text("", encoding="utf-8")
        return ProcessResult(0)

    result = run_local_loop(
        SUITE, attempt_root=attempt, execute=True, case_ids=["L01"],
        fixture_root=tmp_path / "fixtures", canonical_endpoint="http://127.0.0.1:9",
        canonical_realm_id="canonical", canonical_root=tmp_path / "canonical",
        case_preparer=prepare, process_launcher=launcher,
    )
    assert result["records"][0]["execution"] == "completed"
    assert lifecycle == ["prepare", "capture", "launch", "capture", "close"]
    case_root = attempt / "cases/L01"
    assert json.loads((case_root / "before.json").read_text()) == {"sequence": 1}
    assert json.loads((case_root / "after.json").read_text()) == {"sequence": 2}
    assert json.loads((case_root / "fixture-receipt.json").read_text()) == {"kind": "test-fixture"}


def test_real_launcher_receives_only_the_prepared_runtime_environment_for_every_case(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_loop, "render_case_brief", lambda case_id, *, prepared, doc_path: f"prepared {case_id}\n")
    monkeypatch.setenv("ASTRID_TIMELINE_EVAL_ENDPOINT", "http://ambient.invalid")
    monkeypatch.setenv("ASTRID_TIMELINE_EVAL_CREDENTIAL", "/ambient/credential")
    monkeypatch.setenv("ASTRID_TIMELINE_EVAL_EXTRA", "ambient")
    monkeypatch.setenv("ASTRID_RUNTIME_ENDPOINT", "http://ambient-runtime.invalid")
    observed: dict[str, dict[str, str]] = {}

    class FakeProcess:
        pid = 999999999

        def __init__(self, argv, *, cwd, env, **kwargs):
            observed[Path(cwd).parent.name] = env
            self.cwd = Path(cwd)
            self.returncode = None

        def wait(self, timeout):
            (self.cwd / "result.json").write_text(json.dumps({
                "status": "completed", "answer": "done", "evidence": [],
            }), encoding="utf-8")
            self.returncode = 0
            return 0

    monkeypatch.setattr(local_loop.subprocess, "Popen", FakeProcess)

    def prepare(case_id, *, case_root, **kwargs):
        case_root.mkdir(parents=True)
        is_action = case_id == "A01"
        return SimpleNamespace(
            kind="action" if is_action else "navigation",
            endpoint="http://127.0.0.1:45678" if is_action else "http://127.0.0.1:45679",
            credential_file=tmp_path / ("prepared-credential" if is_action else "prepared-navigation-credential"),
            fixture_receipt={"case_id": case_id},
            baseline_observer=lambda: {"case_id": case_id}, close=lambda: None,
        )

    result = run_local_loop(
        SUITE, attempt_root=tmp_path / "attempt", execute=True,
        case_ids=["A01", "L01"], case_preparer=prepare,
    )
    assert [row["execution"] for row in result["records"]] == ["completed", "completed"]
    action_env = observed["A01"]
    assert action_env["ASTRID_TIMELINE_EVAL_ENDPOINT"] == "http://127.0.0.1:45678"
    assert action_env["ASTRID_TIMELINE_EVAL_CREDENTIAL"] == str(tmp_path / "prepared-credential")
    assert "ASTRID_TIMELINE_EVAL_EXTRA" not in action_env
    assert "ASTRID_RUNTIME_ENDPOINT" not in action_env
    navigation_env = observed["L01"]
    assert navigation_env["ASTRID_TIMELINE_EVAL_ENDPOINT"] == "http://127.0.0.1:45679"
    assert navigation_env["ASTRID_TIMELINE_EVAL_CREDENTIAL"] == str(tmp_path / "prepared-navigation-credential")
    assert "ASTRID_TIMELINE_EVAL_EXTRA" not in navigation_env
    assert action_env["PYTHONPATH"].split(":", 1)[0] == str(ROOT / "Astrid")
    assert action_env["PYTHONDONTWRITEBYTECODE"] == "1"


@pytest.mark.skipif(sys.platform != "darwin", reason="local worker boundary uses macOS sandbox-exec")
def test_real_case_boundary_denies_sibling_coordinator_and_evaluator_reads_but_captures_evidence(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"
    work = attempt / "cases/A01/work"
    sibling = attempt / "cases/A02/work/result.json"
    coordinator = attempt / "cases/A01/before.json"
    own_input = work / "project/input.json"
    for path, content in (
        (sibling, '{"secret":"sibling"}'),
        (coordinator, '{"secret":"coordinator"}'),
        (own_input, '{"public":"case"}'),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    evaluator = Path(local_loop.__file__).resolve()
    script = (
        "import json\n"
        "from pathlib import Path\n"
        f"paths = {{'own': Path({str(own_input)!r}), 'sibling': Path({str(sibling)!r}), "
        f"'coordinator': Path({str(coordinator)!r}), 'evaluator': Path({str(evaluator)!r})}}\n"
        "observed = {}\n"
        "for name, path in paths.items():\n"
        "    try:\n"
        "        path.read_bytes()\n"
        "    except (OSError, PermissionError):\n"
        "        observed[name] = 'denied'\n"
        "    else:\n"
        "        observed[name] = 'read'\n"
        "Path('result.json').write_text(json.dumps({'status':'captured','answer':observed,'evidence':[observed]}))\n"
        "print(json.dumps(observed))\n"
    )
    argv, receipt = local_loop._case_worker_boundary(
        [sys.executable, "-c", script], work=work, attempt_root=attempt,
    )
    trace = attempt / "cases/A01/trace.jsonl"
    log = attempt / "cases/A01/agent.log"
    result = local_loop._launch_omp(argv, work, 10, trace, log)

    assert result.returncode == 0
    observed = json.loads(trace.read_text(encoding="utf-8"))
    assert observed == {
        "own": "read",
        "sibling": "denied",
        "coordinator": "denied",
        "evaluator": "denied",
    }
    assert local_loop._result_problem(work / "result.json") is None
    assert receipt["status"] == "enforced"
    assert receipt["selected_case_path"] == str(work.resolve())


@pytest.mark.skipif(sys.platform != "darwin", reason="local worker boundary uses macOS sandbox-exec")
def test_real_case_boundary_denies_private_otto_trees_but_keeps_case_and_public_docs(tmp_path: Path) -> None:
    source_root = Path(local_loop.__file__).resolve().parents[2]
    checkout_private_root = source_root / ".otto"
    workspace_private_root = source_root.parent / ".otto"
    attempt = tmp_path / "attempt"
    work = attempt / "cases/A06/work"
    work.mkdir(parents=True)
    public_doc = source_root / "docs/timeline-editing-guide.md"

    with (
        tempfile.TemporaryDirectory(prefix="worker-boundary-", dir=checkout_private_root) as private_dir,
        tempfile.TemporaryDirectory(prefix="worker-boundary-", dir=workspace_private_root) as workspace_dir,
    ):
        private_evaluator = Path(private_dir) / "sibling-worktree/evals/private-evaluator.py"
        private_evaluator.parent.mkdir(parents=True)
        private_evaluator.write_text("secret = True\n", encoding="utf-8")
        private_write = private_evaluator.with_name("worker-wrote.py")
        workspace_private = Path(workspace_dir) / "private-evaluator.py"
        workspace_private.write_text("secret = True\n", encoding="utf-8")
        workspace_write = workspace_private.with_name("worker-wrote.py")
        script = (
            "import json\n"
            "from pathlib import Path\n"
            f"private = Path({str(private_evaluator)!r})\n"
            f"private_write = Path({str(private_write)!r})\n"
            f"workspace_private = Path({str(workspace_private)!r})\n"
            f"workspace_write = Path({str(workspace_write)!r})\n"
            f"public = Path({str(public_doc)!r})\n"
            "observed = {}\n"
            "for name, path in [('private_read', private), ('workspace_read', workspace_private), ('public_doc', public)]:\n"
            "    try: path.read_bytes()\n"
            "    except OSError: observed[name] = 'denied'\n"
            "    else: observed[name] = 'read'\n"
            "for name, path in [('private_write', private_write), ('workspace_write', workspace_write)]:\n"
            "    try: path.write_text('not allowed')\n"
            "    except OSError: observed[name] = 'denied'\n"
            "    else: observed[name] = 'wrote'\n"
            "Path('result.json').write_text(json.dumps(observed))\n"
            "print(json.dumps(observed))\n"
        )
        argv, receipt = local_loop._case_worker_boundary(
            [sys.executable, "-c", script], work=work, attempt_root=attempt,
        )
        trace = attempt / "cases/A06/trace.jsonl"
        log = attempt / "cases/A06/agent.log"
        result = local_loop._launch_omp(argv, work, 10, trace, log)

        assert result.returncode == 0
        assert json.loads(trace.read_text(encoding="utf-8")) == {
            "private_read": "denied",
            "private_write": "denied",
            "workspace_read": "denied",
            "workspace_write": "denied",
            "public_doc": "read",
        }
        assert json.loads((work / "result.json").read_text(encoding="utf-8"))["private_read"] == "denied"
        assert str(checkout_private_root.resolve()) in receipt["protected_read_paths"]
        assert str(checkout_private_root.resolve()) in receipt["protected_write_paths"]
        assert str(workspace_private_root.resolve()) in receipt["protected_read_paths"]
        assert str(workspace_private_root.resolve()) in receipt["protected_write_paths"]


def test_worker_boundary_denies_exact_runtime_and_canonical_paths_but_allows_credential(monkeypatch, tmp_path: Path) -> None:
    """Probe the concrete paths passed to the local runner's Seatbelt profile."""
    monkeypatch.setattr(local_loop.sys, "platform", "darwin")
    monkeypatch.setattr(local_loop.shutil, "which", lambda name: "/usr/bin/sandbox-exec" if name == "sandbox-exec" else None)
    work = tmp_path / "attempt/cases/A02/work"
    runtime = tmp_path / "attempt/cases/A02/runtime"
    canonical = tmp_path / "canonical-realm"
    credential = runtime / "support/credentials/worker.json"
    argv, receipt = local_loop._case_worker_boundary(
        [sys.executable, "-c", "pass"],
        work=work,
        attempt_root=tmp_path / "attempt",
        protected_paths=(runtime, runtime / "realm", runtime / "support"),
        public_read_paths=(credential,),
        canonical_root=canonical,
    )
    profile = argv[2]
    assert f'(deny file-read* (subpath "{runtime.resolve()}"))' in profile
    assert f'(deny file-read* (subpath "{(runtime / "support/credentials").resolve()}"))' in profile
    assert f'(allow file-read* (literal "{credential.resolve()}"))' in profile
    assert f'(deny file-read* (subpath "{canonical.resolve()}"))' in profile
    assert receipt["status"] == "enforced"
    assert str(runtime.resolve()) in receipt["runtime_storage_denied"]
    assert receipt["canonical_root_denied"] == str(canonical.resolve())


def test_preparation_failure_records_setup_error_and_continues_without_launch(tmp_path: Path, monkeypatch) -> None:
    attempts: list[str] = []
    monkeypatch.setattr(local_loop, "render_case_brief", lambda case_id, *, prepared, doc_path: f"prepared {case_id}\n")

    def prepare(case_id, **kwargs):
        if case_id == "A01":
            raise RuntimeError("Runtime protocol unavailable")
        return SimpleNamespace(
            fixture_receipt={"case_id": case_id},
            baseline_observer=lambda: {"case_id": case_id}, close=lambda: None,
        )

    def launcher(argv, cwd, timeout, trace_path, log_path):
        attempts.append(cwd.parent.name)
        (cwd / "result.json").write_text(json.dumps({
            "status": "completed", "answer": "Finished", "evidence": [],
        }), encoding="utf-8")
        trace_path.write_text("", encoding="utf-8")
        log_path.write_text("", encoding="utf-8")
        return ProcessResult(0)

    result = run_local_loop(
        SUITE, attempt_root=tmp_path / "attempt", execute=True,
        case_ids=["A01", "A02"], case_preparer=prepare, process_launcher=launcher,
    )
    assert result["records"][0]["execution"] == "not_launched"
    assert result["records"][0]["setup_error"] == "RuntimeError: Runtime protocol unavailable"
    assert result["records"][1]["execution"] == "completed"
    assert attempts == ["A02"]
