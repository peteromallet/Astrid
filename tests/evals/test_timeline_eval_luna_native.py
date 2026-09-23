from __future__ import annotations

import json
import os
import copy
import subprocess
import time
from pathlib import Path

import pytest

from evals.timeline import luna_native
from evals.timeline.checks import run_checks
from evals.timeline.luna_native import DEFAULT_MODEL, run_attempt
from evals.timeline.worker_boundary import (
    BoundaryRequirements,
    ProtectedPath,
    WorkerLaunchObservation,
)


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
    fixture_ready_ids = {
        case_id for case_id, row in rows.items()
        if row["setup_status"] == "ready"
    }
    assert len(call_rows) == len(fixture_ready_ids)
    assert {row["case"] for row in call_rows} == {
        case_id for case_id in fixture_ready_ids
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
        if case_id not in fixture_ready_ids:
            result = json.loads((case_dir / "result.json").read_text())
            assert result["agent_status"] == "fixture_blocked"
            assert result["execution_status"] == "not_started"
            assert report["counted_in_agent_pass_denominator"] is False
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


def test_a03_order_oracle_moves_closing_immediately_before_middle_and_rejects_wrong_orders():
    case = next(row for row in json.loads(SUITE.read_text())["cases"] if row["id"] == "A03")
    checks = luna_native._hidden_checks(case, fixture_root=FIXTURES)
    order = next(check for check in checks if check["id"] == "a03_order")
    expected = [
        "shot-ee383f695b10431c", "shot-63979db219fd7599",
        "shot-closing-v6-sign", "shot-49829dff799aa392",
    ]
    assert order["expected_ids"] == expected
    correct_after = {"occurrences": [{"occurrence_id": value} for value in expected]}
    old_wrong_oracle = dict(order, expected_ids=[expected[2], expected[0], expected[3], expected[1]])
    assert run_checks([order], {"after": correct_after})[0].status == "pass"
    assert run_checks([old_wrong_oracle], {"after": correct_after})[0].status == "fail"
    wrong_after = {"occurrences": [{"occurrence_id": value} for value in [expected[0], expected[2], expected[1], expected[3]]]}
    assert run_checks([order], {"after": wrong_after})[0].status == "fail"


def test_l02_identity_oracle_matches_one_publicly_requested_expansion_and_allows_extras():
    case = next(row for row in json.loads(SUITE.read_text())["cases"] if row["id"] == "L02")
    checks = luna_native._hidden_checks(case, fixture_root=FIXTURES)
    identity = next(check for check in checks if check["id"] == "l02_expanded_identities")
    assert identity["check"] == "records_include"
    assert identity["mode"] == "any"
    expected = identity["expected"][0]
    actual = dict(expected, nested_clips=[], parent_duration_ms=7067,
                  media_handles=[{"role": "selected_image", "media_id": expected["selected_image_media_id"]}])
    assert run_checks([identity], {"result": {"observations": {"expanded_occurrences": [actual]}}})[0].status == "pass"


def test_skill_reference_resolves_versioned_checked_in_path():
    reference = luna_native._skill_reference()
    path = Path(reference["path"])
    assert path.as_posix().endswith("/astrid/packs/rendering/skill/SKILL.md")
    assert path.is_file()
    assert reference["version"] == "astrid-timeline-2026.09.24.1"
    assert len(reference["sha256"]) == 64


def test_prompt_does_not_claim_a_universal_edit_route():
    prompt = luna_native._prompt(
        {"id": "A02"}, skill_reference={"path": "/skill", "version": "v1", "sha256": "hash"},
        public_target={"capabilities": {"edit": {"status": "unavailable", "reason": "not seeded"}}},
    )
    assert "No case-specific edit capability is declared available" in prompt
    assert "use the public timelines replace-parent-media route" not in prompt


def test_action_without_case_specific_route_is_blocked_before_model_launch(tmp_path, monkeypatch):
    suite = json.loads(SUITE.read_text())
    suite["cases"] = [next(row for row in suite["cases"] if row["id"] == "A02")]
    suite_path = tmp_path / "a02-only-suite.json"
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    target_root = tmp_path / "targets"
    target_root.mkdir()
    credential, contract, _unused_targets = _isolation_inputs(tmp_path)
    monkeypatch.setattr("evals.timeline.run.validate_isolated_target", lambda *_args: (True, "ok"))
    fake, calls = _fake_omp(tmp_path)
    aggregate = run_attempt(
        suite_path, tmp_path / "attempt-a02-blocked", fixture_root=FIXTURES,
        briefs_path=BRIEFS, omp_bin=str(fake), execute=True,
        isolated_endpoint="http://127.0.0.1:9001", isolated_credential=credential,
        isolation_contract=contract, prepared_targets_root=target_root,
    )
    result = json.loads((tmp_path / "attempt-a02-blocked/cases/A02/result.json").read_text())
    assert not calls.exists()
    assert result["agent_status"] == "fixture_blocked"
    assert "case-specific" in result["failure_cause"]["summary"]
    assert aggregate["cases"][0]["status"] == "blocked"
    assert aggregate["cases"][0]["counted_in_agent_pass_denominator"] is False


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
        "  'status': 'blocked',\n"
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
    assert result["agent_status"] == "blocked"
    assert result["execution_status"] == "completed"
    assert result["launcher_process_status"] == "completed"
    assert row["status"] == "blocked"


def _isolation_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    credential = tmp_path / "credential.json"
    credential.write_text("{}", encoding="utf-8")
    contract = tmp_path / "isolation.json"
    contract.write_text("{}", encoding="utf-8")
    return credential, contract, tmp_path / "targets"


def _boundary_requirements(
    tmp_path: Path, case_id: str = "A01", attempt_name: str = "attempt-live",
) -> BoundaryRequirements:
    skill = luna_native._skill_reference()
    return BoundaryRequirements(
        case_id=case_id,
        worker_id="test-worker",
        model_boundary_id="test-model-boundary",
        host_selected_case_path=str(tmp_path / attempt_name / "cases" / case_id),
        selected_case_path=f"/worker/cases/{case_id}",
        disposable_credential_path="/worker/authority/credential.json",
        skill_path="/worker/public-skill/SKILL.md",
        skill_sha256=skill["sha256"],
        public_package_digest="sha256:test-public-package",
        disposable_endpoint="http://127.0.0.1:9001",
        disposable_realm_id="test-realm",
        disposable_runtime_receipt_id="test-runtime-receipt",
        canonical_endpoint="https://canonical.invalid",
        coordinator_paths=(ProtectedPath("coordinator", "/host/coordinator", "/private/coordinator"),),
        source_paths=(ProtectedPath("source", "/host/source", "/private/source"),),
        sibling_paths=(ProtectedPath("sibling", "/host/sibling", "/private/sibling"),),
        agent_case_paths=(ProtectedPath("agent-case", "/host/prior", "/private/prior"),),
        denied_endpoints=("https://other.invalid",),
    )


def _install_fake_boundary(
    monkeypatch, tmp_path: Path, case_id: str = "A01", attempt_name: str = "attempt-live",
) -> tuple[BoundaryRequirements, object]:
    requirements = _boundary_requirements(tmp_path, case_id, attempt_name)

    class Receipt:
        worker_id = requirements.worker_id
        boundary_id = requirements.model_boundary_id
        runtime_receipt_id = "test-container-receipt"
        challenge = "test-boundary-challenge"
        selected_case_path = requirements.selected_case_path

        def as_dict(self):
            return {
                "status": "pass",
                "boundary_id": requirements.model_boundary_id,
                "runtime_receipt_id": self.runtime_receipt_id,
                "challenge": self.challenge,
            }

    class Supervisor:
        def launch_worker(self, request):
            started = time.monotonic()
            try:
                completed = subprocess.run(
                    request.argv,
                    cwd=requirements.host_selected_case_path,
                    env=dict(request.environment),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=request.timeout_seconds,
                    check=False,
                )
                status = "completed" if completed.returncode == 0 else "failed"
                returncode = completed.returncode
                stdout, stderr = completed.stdout, completed.stderr
            except subprocess.TimeoutExpired as exc:
                status, returncode = "timeout", None
                stdout, stderr = exc.stdout or "", exc.stderr or ""
            return WorkerLaunchObservation(
                worker_id=request.worker_id,
                boundary_id=request.boundary_id,
                runtime_receipt_id=request.runtime_receipt_id,
                challenge=request.challenge,
                status=status,
                returncode=returncode,
                elapsed_seconds=time.monotonic() - started,
                stdout=stdout,
                stderr=stderr,
            )

    monkeypatch.setattr(luna_native, "prove_worker_boundary", lambda _supervisor, _requirements: Receipt())
    return requirements, Supervisor()


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
            "readback_projection": "active_media_replacement.v1",
            "voice_clip_id": "vo_b01",
            "frame_overlay_clip_id": "frame_v1",
        },
        "capabilities": {"edit": {"status": "available", "route": "timelines replace-parent-media"}},
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
                "registry": copy.deepcopy(registry),
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
        self.head = str(closure["head_revision_id"])
        self.closures = {self.head: closure}

    def read_current_closure(self, project_id, timeline_id, *, head=None):
        return self.closures[head or self.head]

    def current_head(self, project_id, timeline_id):
        return self.head

    def list_project_timeline_heads(self, project_id):
        return {"timeline-test": self.head}


def _run_live_a01(tmp_path: Path, monkeypatch, *, target: dict[str, object] | None, adapter, invoke=None) -> tuple[dict, Path]:
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    credential, contract, targets = _isolation_inputs(tmp_path)
    targets.mkdir()
    if target is not None:
        (targets / "A01").mkdir()
        (targets / "A01" / "target.json").write_text(json.dumps(target), encoding="utf-8")
    monkeypatch.setattr("evals.timeline.run.validate_isolated_target", lambda *_args: (True, "ok"))
    monkeypatch.setattr(luna_native, "_connect_readback_adapter", lambda **_kwargs: adapter)
    if invoke is not None:
        monkeypatch.setattr(luna_native, "_invoke", invoke)
    boundary_requirements, boundary_supervisor = _install_fake_boundary(monkeypatch, tmp_path)
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
        boundary_supervisor=boundary_supervisor,
        boundary_requirements={"A01": boundary_requirements},
    )
    return aggregate, calls


def test_prepared_target_is_copied_and_preflight_allows_one_launch(tmp_path, monkeypatch):
    aggregate, calls = _run_live_a01(tmp_path, monkeypatch, target=_target(), adapter=_ReadbackAdapter(_closure()))
    assert len(calls.read_text(encoding="utf-8").splitlines()) == 1
    case_dir = tmp_path / "attempt-live/cases/A01"
    assert json.loads((case_dir / "target.json").read_text(encoding="utf-8"))["project_id"] == "project-test"
    public_brief = json.loads((case_dir / "brief.json").read_text(encoding="utf-8"))
    assert public_brief["fixture_entry_point"]["root"] == "/worker/cases/A01"
    assert public_brief["skill_reference"]["path"] == "/worker/public-skill/SKILL.md"
    assert str(case_dir) not in json.dumps(public_brief)
    assert (case_dir / "before.json").is_file()
    result = json.loads((case_dir / "result.json").read_text(encoding="utf-8"))
    assert not (case_dir / "after.json").exists()
    assert "independent_readback" not in result
    evidence = json.loads((tmp_path / "attempt-live/coordinator/cases/A01/readback.json").read_text(encoding="utf-8"))
    assert evidence["readback"]["status"] == "unavailable"
    assert evidence["safety"] == {"source_unchanged": None, "test_target_only": None}
    assert "publication_response" not in result
    assert aggregate["case_count"] == 20


def test_exact_publication_response_and_dependency_manifest_feed_contract(tmp_path, monkeypatch):
    adapter = _ReadbackAdapter(_closure())
    expected_digest = "sha256:03810afd80e1d43aef0a33dffafac508fcc7ad616deffb9f5d712c35a89f99b7"
    after = copy.deepcopy(adapter.closures["head-before"])
    after["head_revision_id"] = "head-after"
    after["parent_revision"]["revision_id"] = "head-after"
    after["parent_revision"]["payload"]["occurrences"][0]["shot_revision_id"] = "shot-rev-after"
    after["shot_revisions"][0]["revision_id"] = "shot-rev-after"
    after["shot_revisions"][0]["internal_timeline_revision_id"] = "internal-after"
    after["internal_timeline_revisions"][0]["revision_id"] = "internal-after"
    after_internal = after["internal_timeline_revisions"][0]["payload"]
    after_internal["clips"][0]["asset"] = "new-charcoal"
    after_internal["registry"]["assets"]["new-charcoal"] = {"media_id": expected_digest}
    publication_response = {
        "ok": True,
        "data": {
            "publication": {
                "new_head": "head-after",
                "old_head": "head-before",
                "dependency_manifest": {
                    "shots": [{"shot_id": "shot-target", "revision_id": "shot-rev-after"}],
                    "internal_timelines": [{"revision_id": "internal-after"}],
                },
            },
        },
        "error": None,
        "receipt": None,
        "idempotency_key": "eval-publication-1",
    }

    def invoke(**kwargs):
        assert kwargs["model_boundary_id"] == "test-model-boundary"
        adapter.closures["head-after"] = after
        adapter.head = "head-after"
        luna_native._write_json(kwargs["case_dir"] / "result.json", {
            "agent_status": "passed",
            "route": "timelines replace-parent-media",
            "edit_made": True,
            "saved_to_test_timeline": True,
            "publication_response": publication_response,
        })
        return "completed", 0, 0.01, [], ""

    aggregate, _calls = _run_live_a01(
        tmp_path, monkeypatch, target=_target(), adapter=adapter, invoke=invoke,
    )
    result = json.loads((tmp_path / "attempt-live/cases/A01/result.json").read_text())
    assert "independent_readback" not in result
    evidence = json.loads((tmp_path / "attempt-live/coordinator/cases/A01/readback.json").read_text())
    readback = evidence["readback"]
    assert readback["committed_revisions"]["returned_parent"] == "head-after"
    assert readback["committed_revisions"]["returned_shots"] == [["shot-target", "shot-rev-after"]]
    assert readback["media_digest_evidence"]["matched"] is True
    assert readback["safety"] == {"source_unchanged": None, "test_target_only": True}
    assert json.loads((tmp_path / "attempt-live/cases/A01/after.json").read_text())["target"]["active_media_digest"] == expected_digest
    # No source-reader proof means the coordinator may not call the operation
    # fully safe or award an agent pass.
    assert next(row for row in aggregate["cases"] if row["id"] == "A01")["status"] != "passed"


def test_missing_prepared_target_fails_closed_without_launch(tmp_path, monkeypatch):
    aggregate, calls = _run_live_a01(tmp_path, monkeypatch, target=None, adapter=_ReadbackAdapter(_closure()))
    assert not calls.exists() or not calls.read_text(encoding="utf-8").strip()
    result = json.loads((tmp_path / "attempt-live/cases/A01/result.json").read_text(encoding="utf-8"))
    assert result["agent_status"] == "setup_failed"
    assert "prepared public target" in result["failure_cause"]["summary"]
    assert next(row for row in aggregate["cases"] if row["id"] == "A01")["status"] == "setup_failed"


def test_a01_missing_prepared_targets_root_has_explicit_setup_reason(tmp_path, monkeypatch):
    suite = json.loads(SUITE.read_text())
    suite["cases"] = [next(row for row in suite["cases"] if row["id"] == "A01")]
    suite_path = tmp_path / "a01-only-suite.json"
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    credential, contract, _targets = _isolation_inputs(tmp_path)
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    monkeypatch.setattr("evals.timeline.run.validate_isolated_target", lambda *_args: (True, "ok"))
    aggregate = run_attempt(
        suite_path, tmp_path / "attempt-no-target-root", fixture_root=FIXTURES,
        briefs_path=BRIEFS, omp_bin=str(fake), execute=True,
        isolated_endpoint="http://127.0.0.1:9001", isolated_credential=credential,
        isolation_contract=contract,
    )
    result = json.loads((tmp_path / "attempt-no-target-root/cases/A01/result.json").read_text())
    assert not calls.exists() or not calls.read_text(encoding="utf-8").strip()
    assert result["agent_status"] == "setup_failed"
    assert "prepared_targets_root" in result["failure_cause"]["summary"]
    assert "disposable target" in result["failure_cause"]["summary"]
    assert aggregate["cases"][0]["status"] == "setup_failed"


def test_missing_boundary_supervisor_fails_closed_before_model_launch(tmp_path, monkeypatch):
    fake, calls = _fake_omp(tmp_path)
    monkeypatch.setenv("LUNA_CALL_LOG", str(calls))
    credential, contract, targets = _isolation_inputs(tmp_path)
    targets.mkdir()
    (targets / "A01").mkdir()
    (targets / "A01" / "target.json").write_text(json.dumps(_target()), encoding="utf-8")
    monkeypatch.setattr("evals.timeline.run.validate_isolated_target", lambda *_args: (True, "ok"))
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
    assert result["agent_status"] == "setup_failed"
    assert "no typed host boundary requirements" in result["failure_cause"]["summary"]


def test_navigation_uses_exact_closure_projection_without_a01_roles(tmp_path, monkeypatch):
    suite = json.loads(SUITE.read_text())
    suite["cases"] = [next(row for row in suite["cases"] if row["id"] == "L01")]
    suite_path = tmp_path / "l01-only-suite.json"
    suite_path.write_text(json.dumps(suite), encoding="utf-8")
    credential, contract, targets = _isolation_inputs(tmp_path)
    targets.mkdir()
    (targets / "L01").mkdir()
    target = {
        "endpoint": "http://127.0.0.1:9001",
        "project_id": "project-test",
        "timeline_id": "timeline-test",
        "head_revision_id": "head-before",
        "target_locator": {"readback_projection": "exact_closure_navigation.v1"},
    }
    (targets / "L01" / "target.json").write_text(json.dumps(target), encoding="utf-8")
    target_reader = _ReadbackAdapter(_closure())
    source_reader = _ReadbackAdapter(_closure())
    monkeypatch.setattr("evals.timeline.run.validate_isolated_target", lambda *_args: (True, "ok"))
    monkeypatch.setattr(luna_native, "_connect_readback_adapter", lambda **_kwargs: target_reader)
    boundary_requirements, boundary_supervisor = _install_fake_boundary(
        monkeypatch, tmp_path, "L01", attempt_name="attempt-nav",
    )
    sequence = []

    def prove(_supervisor, requirements):
        sequence.append(("boundary", requirements.model_boundary_id))

        class Receipt:
            boundary_id = requirements.model_boundary_id

            def as_dict(self):
                return {"status": "pass", "boundary_id": requirements.model_boundary_id}

        return Receipt()

    def invoke(**kwargs):
        sequence.append(("invoke", kwargs["model_boundary_id"]))
        luna_native._write_json(kwargs["case_dir"] / "result.json", {
            "navigation_performed": True,
            "tool_calls": 1,
            "observations": {"head_revision_id": "head-before", "selected_image_media_id": "sha256:unused"},
        })
        return "completed", 0, 0.01, [], ""

    monkeypatch.setattr(luna_native, "prove_worker_boundary", prove)
    monkeypatch.setattr(luna_native, "_invoke", invoke)
    run_attempt(
        suite_path, tmp_path / "attempt-nav", fixture_root=FIXTURES, briefs_path=BRIEFS,
        execute=True, launchable_ids={"L01"}, isolated_endpoint="http://127.0.0.1:9001",
        isolated_credential=credential, isolation_contract=contract,
        prepared_targets_root=targets, source_reader=source_reader,
        boundary_supervisor=boundary_supervisor, boundary_requirements={"L01": boundary_requirements},
    )
    assert sequence == [
        ("boundary", "test-model-boundary"),
        ("invoke", "test-model-boundary"),
    ]
    evidence = json.loads((tmp_path / "attempt-nav/coordinator/cases/L01/readback.json").read_text())
    assert evidence["readback"]["status"] == "pass"
    assert evidence["safety"] == {
        "source_unchanged": True, "read_only_target": True, "test_target_only": True,
    }
