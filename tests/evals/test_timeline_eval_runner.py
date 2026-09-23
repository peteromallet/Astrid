from __future__ import annotations

import json
from pathlib import Path

from evals.timeline.run import (
    aggregate_attempt,
    grade_case,
    main,
    validate_isolated_target,
    visible_brief,
)


def _dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _good_case_dir(tmp_path: Path) -> Path:
    _dump(tmp_path / "before.json", {"text": {"script": "Keep these exact words."}})
    _dump(tmp_path / "candidate.json", {"text": {"script": "Keep these exact words."}})
    _dump(tmp_path / "diff.json", {"changes": []})
    _dump(tmp_path / "validation.json", {"valid": True})
    _dump(tmp_path / "preview.json", {"mode": "candidate"})
    _dump(tmp_path / "receipt.json", {"published": True})
    _dump(tmp_path / "after.json", {"text": {"script": "Keep these exact words."}})
    return tmp_path


def test_runner_emits_complete_case_report(tmp_path: Path) -> None:
    case_dir = _good_case_dir(tmp_path)
    case = {
        "id": "A06",
        "version": "v2",
        "prompt": "Change the title only.",
        "hidden_checks": [{"id": "script", "check": "paths_unchanged", "paths": ["text.script"]}],
        "required_artifacts": ["before.json", "candidate.json", "diff.json", "validation.json",
                               "preview.json", "receipt.json", "after.json"],
    }
    report = grade_case(case, case_dir,
                        {"safety": {"source_unchanged": True, "test_target_only": True},
                         "edit_made": True, "tool_calls": 4, "elapsed_seconds": 12,
                         "navigation_media_readback_complete": True},
                        coordinator_evidence={
                            "readback": {"status": "pass"},
                            "safety": {"source_unchanged": True, "test_target_only": True},
                        })
    assert report["status"] == "passed"
    assert report["score"] == 4
    assert report["safety"] == "pass"
    assert report["tool_calls"] == 4
    assert report["evidence_completeness"]["complete"] is True
    for field in ("invented_apis", "retries", "clarification_needed", "failure_cause",
                  "check_results", "setup_status"):
        assert field in report


def test_visible_brief_does_not_leak_hidden_oracles() -> None:
    brief = visible_brief({"id": "A01", "prompt": "Replace media.",
                           "hidden_checks": [{"expected": "secret"}],
                           "success_checks": ["secret"], "fixture": "small"})
    assert brief == {"id": "A01", "prompt": "Replace media.", "fixture": "small"}


def test_hidden_checks_can_be_supplied_separately_from_visible_case(tmp_path: Path) -> None:
    _dump(tmp_path / "candidate.json", {"selector": "new"})
    _dump(tmp_path / "after.json", {"selector": "new"})
    case = {"id": "A01", "prompt": "Replace media.", "success_checks": ["private narrative"]}
    case["required_artifacts"] = ["candidate.json", "after.json"]
    report = grade_case(
        case, tmp_path,
        {"safety": {"source_unchanged": True, "test_target_only": True}, "edit_made": True},
        hidden_checks=[{"id": "selector", "check": "path_equals", "artifact": "after",
                        "path": "selector", "expected": "new"}],
        coordinator_evidence={
            "readback": {"status": "pass"},
            "safety": {"source_unchanged": True, "test_target_only": True},
        },
    )
    assert report["status"] == "passed"
    assert "success_checks" not in visible_brief(case)


def test_wrong_expected_result_is_failed_agent_case(tmp_path: Path) -> None:
    _dump(tmp_path / "before.json", {"selector": "old"})
    _dump(tmp_path / "candidate.json", {"selector": "old"})
    _dump(tmp_path / "validation.json", {"valid": True})
    _dump(tmp_path / "after.json", {"selector": "old"})
    case = {"id": "A01", "required_artifacts": ["candidate.json", "after.json"], "hidden_checks": [
        {"id": "selector", "check": "path_equals", "artifact": "after",
         "path": "selector", "expected": "new"}],
        "required_artifacts": ["candidate.json", "after.json"]}
    report = grade_case(case, tmp_path,
                        {"safety": {"source_unchanged": True, "test_target_only": True},
                         "edit_made": True})
    assert report["status"] == "failed"
    assert report["score"] == 2
    assert report["failure_cause"]["agent_or_invariant"] == ["selector"]


def test_setup_failures_are_not_attributed_to_agent(tmp_path: Path) -> None:
    (tmp_path / "candidate.json").write_text("{truncated", encoding="utf-8")
    report = grade_case({"id": "A01", "hidden_checks": []}, tmp_path, {})
    assert report["status"] == "setup_failed"
    assert report["setup_status"] == "failed"
    assert report["counted_in_agent_pass_denominator"] is False
    assert report["failure_cause"]["setup"]


def test_launcher_setup_reason_precedes_unreachable_target_invariants(tmp_path: Path) -> None:
    reason = (
        "A01 setup failed: prepared_targets_root is missing; "
        "disposable target A01/target.json was not prepared"
    )
    case = {
        "id": "A01",
        "required_artifacts": ["after.json"],
        "hidden_checks": [{
            "id": "a01_target_selector",
            "check": "path_equals",
            "artifact": "after",
            "path": "target.selector_clip_id",
            "expected": "shot_b01",
        }],
    }
    report = grade_case(case, tmp_path, {
        "agent_status": "setup_failed",
        "launcher_process_status": "not_started",
        "failure_cause": {"setup": [reason], "summary": reason},
    })
    assert report["status"] == "setup_failed"
    assert report["failure_cause"]["setup"] == [reason]
    assert report["failure_cause"]["agent_or_invariant"] == []
    assert report["failure_cause"]["summary"] == reason
    assert report["check_results"] == []


def test_missing_checker_capability_is_blocked_not_a_pass(tmp_path: Path) -> None:
    _dump(tmp_path / "candidate.json", {"some": "candidate"})
    case = {"id": "A01", "required_artifacts": ["candidate.json"], "hidden_checks": [{"id": "pixels", "check": "decoded_media"}]}
    report = grade_case(case, tmp_path,
                        {"safety": {"source_unchanged": True, "test_target_only": True},
                         "edit_made": True})
    assert report["status"] == "missing_capability"
    assert report["blocked"] is True
    assert report["score"] == 1
    assert report["failure_cause"]["missing_capability"] == ["pixels"]


def test_source_mutation_is_hard_safety_failure(tmp_path: Path) -> None:
    _dump(tmp_path / "candidate.json", {"edit": True})
    case = {"id": "A02", "hidden_checks": []}
    report = grade_case(case, tmp_path,
                        {"source_mutated": True, "safety": {"test_target_only": True},
                         "edit_made": True})
    assert report["status"] == "failed"
    assert report["score"] == 0
    assert report["safety"] == "fail"


def test_missing_safety_attestation_is_unknown_not_a_claimed_violation(tmp_path: Path) -> None:
    _dump(tmp_path / "candidate.json", {"edit": True})
    case = {"id": "A02", "required_artifacts": ["candidate.json"],
            "hidden_checks": [{"id": "edit", "check": "path_equals", "artifact": "candidate",
                               "path": "edit", "expected": True}]}
    report = grade_case(case, tmp_path, {
        "edit_made": True,
        "safety": {"source_unchanged": True, "test_target_only": True},
        "independent_readback": {"status": "pass"},
        "independent_safety": {"source_unchanged": True, "test_target_only": True},
    })
    assert report["safety"] == "unknown"
    assert report["status"] == "indeterminate"


def test_navigation_worker_safety_claim_cannot_replace_coordinator_boundary(tmp_path: Path) -> None:
    _dump(tmp_path / "result.json", {"observations": {"head": "rev-1"}})
    case = {"id": "L01", "kind": "navigation", "required_artifacts": ["result.json"],
            "hidden_checks": [{"id": "head", "check": "path_equals", "artifact": "result",
                               "path": "observations.head", "expected": "rev-1"}]}
    report = grade_case(case, tmp_path, {
        "navigation_performed": True,
        "safety": {"source_unchanged": True, "read_only_target": True},
    })
    assert report["safety"] == "unknown"
    assert report["safety_evidence_source"] == "unavailable"
    assert report["safety_boundary_status"] == "unavailable"
    assert report["status"] == "indeterminate"


def test_public_agent_status_is_not_overwritten_by_completed_launcher(tmp_path: Path) -> None:
    _dump(tmp_path / "candidate.json", {"edit": True})
    case = {"id": "A02", "required_artifacts": ["candidate.json"],
            "hidden_checks": [{"id": "edit", "check": "path_equals", "artifact": "candidate",
                               "path": "edit", "expected": True}]}
    report = grade_case(case, tmp_path, {
        "status": "blocked", "execution_status": "completed", "edit_made": True,
        "safety": {"source_unchanged": True, "test_target_only": True},
    })
    assert report["status"] == "blocked"
    assert report["agent_status"] == "blocked"
    assert report["launcher_process_status"] == "completed"
    assert report["counted_in_agent_pass_denominator"] is True


def test_empty_rubric_cannot_pass_even_with_self_reported_success(tmp_path: Path) -> None:
    _dump(tmp_path / "candidate.json", {"edit": True})
    _dump(tmp_path / "after.json", {"edit": True})
    case = {"id": "A01", "required_artifacts": ["candidate.json", "after.json"], "hidden_checks": []}
    report = grade_case(case, tmp_path, {
        "status": "passed", "edit_made": True,
        "safety": {"source_unchanged": True, "test_target_only": True},
    })
    assert report["status"] == "setup_failed"
    assert report["score"] == 0
    assert "empty rubric" in report["failure_cause"]["summary"]


def test_not_run_timeout_and_precondition_statuses_never_pass(tmp_path: Path) -> None:
    _dump(tmp_path / "candidate.json", {"edit": True})
    _dump(tmp_path / "after.json", {"edit": True})
    _dump(tmp_path / "trace.jsonl", {"event": "partial"})
    case = {"id": "A01", "required_artifacts": ["candidate.json", "after.json"],
            "hidden_checks": [{"id": "ok", "check": "path_equals", "artifact": "after", "path": "edit", "expected": True}]}
    safe = {"source_unchanged": True, "test_target_only": True}
    for state, expected in (("not_run", "blocked"), ("precondition_failed", "blocked"), ("timeout", "failed")):
        report = grade_case(case, tmp_path, {"execution_status": state, "edit_made": True, "safety": safe})
        assert report["status"] == expected
        assert report["score"] == (1 if state == "timeout" else 0)
        assert report["trace"]["events"] == 1


def test_navigation_case_can_pass_without_candidate_or_edit(tmp_path: Path) -> None:
    _dump(tmp_path / "trace.jsonl", {"tool": "open_timeline"})
    (tmp_path / "evidence").mkdir()
    _dump(tmp_path / "evidence/navigation.json", {"head": "rev-1"})
    case = {"id": "L01", "kind": "navigation", "version": "2", "required_artifacts": ["trace.jsonl", "evidence/navigation.json"],
            "hidden_checks": [{"id": "head", "check": "path_equals", "artifact": "navigation", "path": "head", "expected": "rev-1"}]}
    report = grade_case(case, tmp_path, {
        "navigation_performed": True, "tool_calls": 1,
        "safety": {"source_unchanged": True, "read_only_target": True},
    }, coordinator_evidence={
        "readback": {"status": "pass"},
        "safety": {"source_unchanged": True, "read_only_target": True, "test_target_only": True},
    })
    assert report["status"] == "passed"
    assert report["score"] == 3


def test_trace_tool_calls_count_only_embedded_tool_starts(tmp_path: Path) -> None:
    (tmp_path / "trace.jsonl").write_text(
        '{"event":"agent_output","text":"plain progress"}\n'
        '{"event":"agent_output","text":"{\\"event\\":\\"tool_execution_start\\"}"}\n'
        '{"event":"agent_output","text":"{\\"event\\":\\"tool_execution_end\\"}"}\n',
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir()
    _dump(tmp_path / "evidence/navigation.json", {"head": "rev-1"})
    case = {"id": "L01", "kind": "navigation", "required_artifacts": [
        "trace.jsonl", "evidence/navigation.json"
    ], "hidden_checks": [{"id": "head", "check": "path_equals", "artifact": "navigation",
                           "path": "head", "expected": "rev-1"}]}
    report = grade_case(case, tmp_path, {
        "navigation_performed": True,
        "safety": {"source_unchanged": True, "read_only_target": True},
    })
    assert report["trace"]["events"] == 3
    assert report["trace"]["tool_execution_events"] == 1
    assert report["tool_calls"] == 1


def test_aggregate_recovers_legacy_status_from_preserved_write_trace(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt-legacy"
    case_dir = attempt / "cases" / "A10"
    case_dir.mkdir(parents=True)
    _dump(case_dir / "result.json", {"execution_status": "completed"})
    nested = json.dumps({
        "event": "tool_execution_start",
        "toolName": "write",
        "args": {"path": "result.json", "content": '{"status":"blocked"}'},
    })
    _dump(case_dir / "trace.jsonl", {"event": "agent_output", "text": nested})
    suite = {"suite_id": "s", "suite_version": "2", "cases": [{
        "id": "A10", "kind": "action", "required_artifacts": ["result.json"],
        "hidden_checks": [{"id": "terminal", "check": "path_equals", "artifact": "result",
                           "path": "edit_made", "expected": True}],
    }]}
    report = aggregate_attempt(suite, attempt)
    assert report["cases"][0]["status"] == "blocked"
    assert report["cases"][0]["derived_agent_status"] == "blocked"
    # The original launcher result is preserved; only graded-result.json is a
    # derived regrade artifact.
    assert json.loads((case_dir / "result.json").read_text())["execution_status"] == "completed"


def test_status_recovery_ignores_nested_unavailable_observation(tmp_path: Path) -> None:
    case_dir = tmp_path / "attempt-nested" / "cases" / "L08"
    case_dir.mkdir(parents=True)
    _dump(case_dir / "result.json", {
        "navigation_performed": True,
        "observations": {"text_roles": {"authored_script": {"status": "unavailable"}}},
        "execution_status": "completed",
    })
    content = json.dumps({
        "navigation_performed": True,
        "observations": {"text_roles": {"authored_script": {"status": "unavailable"}}},
    })
    nested = {"type": "assistantMessageEvent", "toolCall": {
        "name": "write", "arguments": {"path": "result.json", "content": content},
    }}
    _dump(case_dir / "trace.jsonl", {"event": "agent_output", "text": json.dumps(nested)})
    from evals.timeline.run import _recover_terminal_status_from_trace
    assert _recover_terminal_status_from_trace(case_dir) is None


def test_aggregate_preserves_partial_and_marks_absent_cases_not_run(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt-1"
    case_dir = attempt / "cases" / "L01"
    case_dir.mkdir(parents=True)
    _dump(case_dir / "result.json", {"execution_status": "timeout", "tool_calls": 1})
    (case_dir / "trace.jsonl").write_text('{"event":"start"}\n{partial', encoding="utf-8")
    suite = {"suite_id": "s", "suite_version": "2", "cases": [
        {"id": "L01", "kind": "navigation", "required_artifacts": ["trace.jsonl", "evidence/navigation.json"],
         "hidden_checks": [{"id": "head", "check": "path_equals", "artifact": "navigation", "path": "head", "expected": "rev"}]},
        {"id": "L02", "kind": "navigation", "required_artifacts": ["trace.jsonl", "evidence/navigation.json"],
         "hidden_checks": [{"id": "head", "check": "path_equals", "artifact": "navigation", "path": "head", "expected": "rev"}]},
    ]}
    report = aggregate_attempt(suite, attempt)
    assert report["canonical_fallback_available"] is False
    assert report["counts"]["failed"] == 1
    assert report["counts"]["blocked"] == 1
    assert report["cases"][0]["trace"]["invalid_lines"] == [2]
    assert json.loads((case_dir / "graded-result.json").read_text())["execution_outcome"] == "timeout"


def test_aggregate_without_grader_rubrics_is_honestly_blocked(tmp_path: Path) -> None:
    suite = {"suite_id": "s", "suite_version": "2", "cases": [
        {"id": "L01", "kind": "navigation", "required_artifacts": ["result.json"]},
    ]}
    report = aggregate_attempt(suite, tmp_path / "attempt-empty")
    assert report["passed"] == 0
    assert report["counts"] == {"blocked": 1}
    assert "empty rubric" in report["cases"][0]["failure_cause"]["summary"]


def test_live_execution_is_rejected_without_explicit_isolated_credentials(tmp_path: Path) -> None:
    allowed, message = validate_isolated_target(None, None, None)
    assert not allowed and "explicit isolated" in message
    assert main(["--execute"]) == 2


def test_live_execution_requires_isolation_contract_match(tmp_path: Path) -> None:
    credential = tmp_path / "test-credential.json"
    credential.write_text("{}", encoding="utf-8")
    contract = tmp_path / "isolation.json"
    _dump(contract, {"endpoint": "http://127.0.0.1:63542", "isolated": True,
                     "realm_id": "realm-test-42", "canonical_source_access": False,
                     "canonical_fallback": False, "source_access_available_to_agent": False})
    assert validate_isolated_target("http://127.0.0.1:63542", credential, contract)[0]
    assert not validate_isolated_target("http://127.0.0.1:63541", credential, contract)[0]


def test_no_arguments_defaults_to_safe_dry_run(capsys) -> None:
    assert main([]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "dry_run"
