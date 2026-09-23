"""Artifact-oriented timeline evaluation runner.

This module grades already captured artifacts and creates safe dry-run reports.
Agent orchestration is intentionally delegated to the configured native launcher
outside this package; no model/provider API is embedded here.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Mapping

try:  # Support both ``python -m`` and direct invocation from the repo root.
    from .checks import CheckResult, DecodedMediaVerifier, run_checks
except ImportError:  # pragma: no cover - direct-script path
    from checks import CheckResult, DecodedMediaVerifier, run_checks

try:
    from .result_adapter import ResultContractError, adapt_worker_result
except ImportError:  # pragma: no cover - direct-script path
    from result_adapter import ResultContractError, adapt_worker_result


ARTIFACT_FILES = {
    "before": "before.json",
    "candidate": "candidate.json",
    "diff": "diff.json",
    "validation": "validation.json",
    "preview": "preview.json",
    "receipt": "receipt.json",
    "after": "after.json",
}
HIDDEN_KEYS = {
    "hidden_checks", "verification", "expected", "success_checks", "invariants",
    "verification_checks", "oracle_checks", "expected_outcome",
}

_PUBLIC_AGENT_STATUSES = {
    "passed", "failed", "blocked", "partial", "indeterminate",
    "missing_capability", "setup_failed", "setup_failure", "precondition_failed",
    "unavailable", "fixture_blocked", "timeout", "timed_out", "not_run",
}
_LAUNCHER_STATUSES = {
    "not_started", "running", "completed", "failed", "timeout",
    "timed_out", "unavailable", "setup_failed",
}


class SetupError(ValueError):
    """Fixture or artifact setup is unusable; do not blame the evaluated agent."""


def visible_brief(case: Mapping[str, Any]) -> dict[str, Any]:
    """Return agent-visible case content without verifier expectations."""
    return {key: value for key, value in case.items() if key not in HIDDEN_KEYS}


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise SetupError(f"required JSON file missing: {path}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SetupError(f"invalid JSON file {path}: {exc}") from exc


def load_artifacts(case_dir: Path) -> tuple[dict[str, Any], list[str], list[str]]:
    artifacts: dict[str, Any] = {}
    present: list[str] = []
    malformed: list[str] = []
    for key, filename in ARTIFACT_FILES.items():
        path = case_dir / filename
        if not path.exists():
            continue
        try:
            artifacts[key] = load_json(path)
            present.append(filename)
        except SetupError:
            malformed.append(filename)
    return artifacts, present, malformed


def _validate_check_list(checks: Any) -> list[Mapping[str, Any]]:
    if not isinstance(checks, list):
        raise SetupError("hidden checker list must be a JSON array")
    if not checks:
        raise SetupError("at least one hidden semantic check is required; an empty rubric cannot pass")
    if any(not isinstance(check, Mapping) for check in checks):
        raise SetupError("each hidden check must be a JSON object")
    required = {
        "path_equals": {"artifact", "path", "expected"},
        "records_include": {"artifact", "path", "expected"},
        "paths_unchanged": {"paths"},
        "order": {"artifact", "path"},
        "identity_disjoint": {"before_artifact", "after_artifact", "original_ids_path", "duplicate_ids_path"},
        "panel_coverage": {"artifact", "path"},
        "decoded_media": set(),
        # Explicitly records a grader gap as unavailable. It is not a
        # successful semantic check and can never award a pass.
        "semantic_oracle_unavailable": set(),
    }
    for index, check in enumerate(checks):
        check_type = str(check.get("check", ""))
        if not check.get("id"):
            raise SetupError(f"hidden check {index} has no stable id")
        if check_type not in required:
            raise SetupError(f"hidden check {check['id']!r} uses unsupported checker {check_type!r}")
        missing_fields = sorted(key for key in required[check_type] if key not in check)
        if missing_fields:
            raise SetupError(f"hidden check {check['id']!r} is missing fields: {', '.join(missing_fields)}")
        if check_type == "paths_unchanged" and not isinstance(check.get("paths"), list):
            raise SetupError(f"hidden check {check['id']!r} paths must be an array")
        if check_type == "records_include":
            if not isinstance(check.get("expected"), list) or not check.get("expected"):
                raise SetupError(f"hidden check {check['id']!r} expected must be a non-empty array")
            if any(not isinstance(row, Mapping) for row in check["expected"]):
                raise SetupError(f"hidden check {check['id']!r} expected records must be objects")
            if str(check.get("mode", "all")).lower() not in {"all", "any"}:
                raise SetupError(f"hidden check {check['id']!r} mode must be 'all' or 'any'")
    return checks


def _check_dicts(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    checks = case.get("hidden_checks", case.get("verification_checks", case.get("oracle_checks")))
    if checks is None:
        checks = case.get("verification", {}).get("checks", [])
    return _validate_check_list(checks)


def _required_filenames(case: Mapping[str, Any]) -> list[str]:
    names = []
    for value in case.get("required_artifacts", ()):
        name = str(value)
        if name in ARTIFACT_FILES:
            name = ARTIFACT_FILES[name]
        names.append(name)
    return names


def _agent_public_status(agent: Mapping[str, Any]) -> str | None:
    """Read the worker's outcome without confusing it with launcher lifecycle.

    New results store this in ``agent_status``. Historical records may use
    ``status`` or ``execution_status``; prefer the explicit public ``status``
    when an old launcher also wrote ``execution_status=completed``.
    """
    for key in ("agent_status", "status", "agent_execution_status", "agent_reported_execution_status"):
        value = str(agent.get(key, "")).strip().lower()
        if value in _PUBLIC_AGENT_STATUSES:
            return value
    value = str(agent.get("execution_status", "")).strip().lower()
    return value if value in _PUBLIC_AGENT_STATUSES else None


def _launcher_process_status(agent: Mapping[str, Any]) -> str:
    """Return OMP/process state independently of the worker's public outcome."""
    for key in ("launcher_process_status", "execution_status"):
        value = str(agent.get(key, "")).strip().lower()
        if value in _LAUNCHER_STATUSES:
            return value
    return "unknown"


def _available_paths(case_dir: Path) -> set[str]:
    """List files and directories with case-relative POSIX paths."""
    found = set()
    if not case_dir.exists():
        return found
    for path in case_dir.rglob("*"):
        found.add(path.relative_to(case_dir).as_posix())
    return found


def _load_check_artifacts(case: Mapping[str, Any], case_dir: Path,
                          checks: list[Mapping[str, Any]],
                          artifacts: dict[str, Any]) -> None:
    required = _required_filenames(case)
    for check in checks:
        names = [check.get("artifact")]
        if check.get("check") == "paths_unchanged":
            names.extend(["before", "after"])
        elif check.get("check") == "identity_disjoint":
            names.extend([check.get("before_artifact", "before"), check.get("after_artifact", "after")])
        for raw_name in names:
            if not raw_name:
                continue
            name = str(raw_name)
            if name in artifacts:
                continue
            candidates = [case_dir / name, case_dir / f"{name}.json", case_dir / "evidence" / f"{name}.json"]
            candidates.extend(case_dir / item for item in required if Path(item).stem == name)
            for path in candidates:
                if path.is_file():
                    try:
                        artifacts[name] = load_json(path)
                    except SetupError:
                        continue
                    break


def _trace_summary(case_dir: Path) -> dict[str, Any]:
    path = case_dir / "trace.jsonl"
    if not path.exists():
        return {"present": False, "events": 0, "tool_calls": 0,
                "tool_execution_events": 0, "invalid_lines": [], "complete": False}
    events = 0
    tool_calls = 0
    invalid_lines = []
    tool_start_events = {
        "tool_execution_start", "tool_call", "tool_use", "tool_started",
    }

    def count_tool_event(row: Mapping[str, Any]) -> bool:
        event_name = str(row.get("event", row.get("type", row.get("name", "")))).lower()
        if event_name in tool_start_events:
            return True
        # Native OMP wraps the model's JSONL in an ``agent_output`` trace
        # record.  Count only an embedded tool-start event, never every output
        # line (which can number in the thousands for a long conversation).
        if event_name != "agent_output":
            return False
        text = row.get("text")
        if not isinstance(text, str):
            return False
        try:
            nested = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return False
        if not isinstance(nested, Mapping):
            return False
        nested_name = str(nested.get("event", nested.get("type", nested.get("name", "")))).lower()
        return nested_name in tool_start_events

    try:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if not isinstance(row, Mapping):
                        raise ValueError("trace event must be an object")
                    events += 1
                    if count_tool_event(row):
                        tool_calls += 1
                except (json.JSONDecodeError, ValueError):
                    invalid_lines.append(line_number)
    except (OSError, UnicodeDecodeError):
        invalid_lines.append("unreadable")
    return {"present": True, "events": events, "tool_calls": tool_calls,
            "tool_execution_events": tool_calls, "invalid_lines": invalid_lines,
            "complete": not invalid_lines}


def _recover_terminal_status_from_trace(case_dir: Path) -> str | None:
    """Recover an explicit agent result status from preserved OMP output.

    Older native attempts wrote ``status`` rather than ``execution_status`` and
    the launcher subsequently replaced the file with its process status.  The
    trace still contains the tool-call payload that wrote the original record;
    recover only a recognized terminal value for a derived regrade, leaving the
    original ``result.json`` untouched.
    """
    path = case_dir / "trace.jsonl"
    if not path.is_file():
        return None
    terminal = {
        "passed", "failed", "blocked", "missing_capability", "setup_failed",
        "precondition_failed", "unavailable", "fixture_blocked", "timeout",
        "timed_out", "not_run",
    }
    def _status_from_result_write(value: Any) -> str | None:
        """Read only top-level terminal fields from a result.json write.

        Do not regex-search the whole payload: result records legitimately
        contain nested status values (for example an unavailable text role in
        L08), which are observations rather than the worker's terminal state.
        """
        if isinstance(value, Mapping):
            tool_name = value.get("toolName") or value.get("name")
            arguments = value.get("arguments", value.get("args"))
            if tool_name == "write" and isinstance(arguments, Mapping):
                path_value = arguments.get("path")
                content = arguments.get("content")
                if str(path_value) == "result.json" and isinstance(content, str):
                    try:
                        result_value = json.loads(content)
                    except (TypeError, json.JSONDecodeError):
                        result_value = None
                    if isinstance(result_value, Mapping):
                        for key in ("agent_status", "status", "agent_execution_status", "execution_status"):
                            candidate = str(result_value.get(key, "")).strip().lower()
                            if candidate in terminal:
                                return candidate
            for child in value.values():
                recovered = _status_from_result_write(child)
                if recovered:
                    return recovered
        elif isinstance(value, list):
            for child in value:
                recovered = _status_from_result_write(child)
                if recovered:
                    return recovered
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if not isinstance(row, Mapping) or row.get("event") != "agent_output":
                    continue
                text = row.get("text")
                if not isinstance(text, str) or "result.json" not in text:
                    continue
                try:
                    outer = json.loads(text)
                except (TypeError, json.JSONDecodeError):
                    continue
                recovered = _status_from_result_write(outer)
                if recovered:
                    return recovered
    except (OSError, UnicodeDecodeError):
        return None
    return None


def grade_case(case: Mapping[str, Any], case_dir: Path,
               agent_result: Mapping[str, Any] | None = None,
               verifier: DecodedMediaVerifier | None = None,
               hidden_checks: list[Mapping[str, Any]] | None = None,
               coordinator_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Grade captured evidence and return the stable case-report schema."""
    started = time.monotonic()
    if agent_result is None and (case_dir / "result.json").is_file():
        loaded_result = load_json(case_dir / "result.json")
        agent = dict(loaded_result) if isinstance(loaded_result, Mapping) else {}
    else:
        agent = dict(agent_result or {})
    case_kind = str(case.get("kind", "action"))
    if case_kind not in {"action", "navigation"}:
        return {
            "id": case.get("id", "unknown"), "version": case.get("version"),
            "status": "setup_failed", "blocked": True, "score": 0,
            "score_scale": "0-4", "safety": "fail",
            "failure_cause": {"setup": [f"unsupported case kind: {case_kind}"], "summary": "unsupported case kind"},
            "setup_status": "failed", "agent_status": "not_run",
        }
    artifacts, _present, malformed = load_artifacts(case_dir)
    required = _required_filenames(case)
    available = _available_paths(case_dir)
    missing = [name for name in required if name not in available]
    setup_failures = [f"malformed artifact: {name}" for name in malformed]
    reported_status = _agent_public_status(agent)
    upstream_setup_reasons: list[str] = []
    if reported_status in {"setup_failed", "setup_failure", "fixture_blocked"}:
        # Coordinator/native-launcher setup failures are terminal before
        # semantic checks. Preserve their concrete reason instead of running
        # private invariants against artifacts which could not be created.
        failure_cause = agent.get("failure_cause", {})
        if isinstance(failure_cause, Mapping):
            raw_setup = failure_cause.get("setup", ())
            if isinstance(raw_setup, list):
                target = setup_failures if reported_status in {"setup_failed", "setup_failure"} else upstream_setup_reasons
                target.extend(
                    str(reason) for reason in raw_setup if isinstance(reason, str) and reason
                )
            summary = failure_cause.get("summary")
            target = setup_failures if reported_status in {"setup_failed", "setup_failure"} else upstream_setup_reasons
            if isinstance(summary, str) and summary and summary not in target:
                target.append(summary)
        if reported_status in {"setup_failed", "setup_failure"} and not setup_failures:
            setup_failures.append("native launcher reported setup failure without a reason")
        if reported_status == "fixture_blocked" and not upstream_setup_reasons:
            upstream_setup_reasons.append("fixture was blocked before worker launch")
    if not isinstance(case.get("required_artifacts", []), list) or not case.get("required_artifacts"):
        setup_failures.append("case contract must declare at least one required artifact")
    result_contract_failures: list[str] = []
    try:
        adapted_result = adapt_worker_result(case, agent)
    except ResultContractError as exc:
        adapted_result = None
        result_contract_failures.append(str(exc))
    check_results: list[CheckResult] = []
    try:
        checks = _validate_check_list(hidden_checks) if hidden_checks is not None else _check_dicts(case)
    except SetupError as exc:
        checks = []
        setup_failures.append(str(exc))
    # A coordinator-declared fixture block means the worker never had a valid
    # semantic surface. Preserve the missing-artifact evidence, but do not run
    # hidden semantic checks against an unmaterialized derivative.
    blocked_before_worker = bool(upstream_setup_reasons)
    if not setup_failures and not blocked_before_worker:
        _load_check_artifacts(case, case_dir, checks, artifacts)
    if not setup_failures and not blocked_before_worker:
        check_results = run_checks(checks, artifacts, verifier)

    missing_capability = [r.check_id for r in check_results if r.status == "missing_capability"]
    failed_checks = [r.check_id for r in check_results if r.status == "fail"]
    invalid_check_results = [r.check_id for r in check_results if r.status not in {"pass", "fail", "missing_capability"}]
    source_mutated = bool(agent.get("source_mutated", False))
    forbidden_publish = bool(agent.get("forbidden_publication", False))
    # Positive safety proof is coordinator-owned only. The worker can write
    # result.json and every artifact below case_dir, so neither its `safety`
    # claims nor its `independent_*` fields establish provenance. The native
    # coordinator stores this evidence in attempt_root/coordinator/ after the
    # worker exits and passes it separately to this grader.
    coordinator = dict(coordinator_evidence or {})
    coordinator_readback = coordinator.get("readback", {})
    if not isinstance(coordinator_readback, Mapping):
        coordinator_readback = {}
    independent_safety = coordinator.get("safety", {})
    if not isinstance(independent_safety, Mapping):
        independent_safety = {}
    agent_safety = agent.get("safety", {})
    if not isinstance(agent_safety, Mapping):
        agent_safety = {}
    source_unchanged = independent_safety.get("source_unchanged")
    target_only = independent_safety.get("test_target_only")
    read_only_target = independent_safety.get("read_only_target")
    target_scope_safe = (
        target_only is True if case_kind == "action"
        else read_only_target is True or target_only is True
    )
    explicit_agent_violation = (
        agent_safety.get("source_unchanged") is False
        or agent_safety.get("test_target_only") is False
        or agent_safety.get("read_only_target") is False
    )
    explicit_violation = (
        source_mutated or forbidden_publish or source_unchanged is False
        or explicit_agent_violation
    )
    explicit_scope_violation = (
        target_only is False
        if case_kind == "action"
        else read_only_target is False
        and target_only is not True
    )
    if explicit_violation or explicit_scope_violation:
        safety = "fail"
    elif source_unchanged is True and target_scope_safe:
        safety = "pass"
    else:
        # Missing self-report is not independent proof of a violation. Keep it
        # separate so an incomplete agent record cannot be narrated as a source
        # mutation, while still preventing a full pass without safety proof.
        safety = "unknown"

    evidence_completeness = {
        "required": required,
        "present": sorted(name for name in required if name in available),
        "missing": missing,
        "malformed": malformed,
        "complete": not missing and not malformed,
    }
    # Score is based on evidence, never on agent self-report. Safety violations
    # and setup failures are hard zeros; unavailable tools are blocked instead.
    launcher_status = _launcher_process_status(agent)
    status = "pending"
    if source_mutated or forbidden_publish:
        status = "failed"
    elif setup_failures:
        status = "setup_failed"
    elif reported_status == "fixture_blocked" or agent.get("setup_status") == "fixture_blocked":
        status = "blocked"
    elif reported_status == "not_run":
        status = "blocked"
    elif reported_status in {"blocked", "precondition_failed", "unavailable"}:
        status = "blocked"
    elif reported_status in {"setup_failed", "setup_failure"}:
        status = "setup_failed"
    elif reported_status == "partial":
        status = "partial"
    elif reported_status == "failed":
        status = "failed"
    elif missing_capability:
        status = "missing_capability"
    elif result_contract_failures:
        status = "failed"
    elif missing or failed_checks or invalid_check_results:
        status = "failed"
    elif safety == "fail":
        status = "failed"
    elif safety == "unknown":
        status = "indeterminate"
    elif reported_status in {"timeout", "timed_out"} or launcher_status in {"timeout", "timed_out"}:
        status = "failed"
    if case_kind == "action":
        # Parent-composition replacement is an immediate, immutable Runtime
        # publication route; it has no legacy detached ``candidate`` artifact.
        # Its useful-result proof is the explicit edit flag plus an independent
        # post-save readback.  Keep the older candidate requirement for the
        # remaining action cases.
        parent_route = agent.get("route") == "timelines replace-parent-media"
        parent_readback = (
            coordinator_readback.get("status") == "pass"
            and "after" in artifacts
        )
        useful_result = (
            agent.get("edit_made") is True and parent_readback
            if parent_route
            else ("candidate" in artifacts and agent.get("edit_made") is True)
        )
    else:
        useful_result = (
            agent.get("navigation_performed") is True
            and bool(agent.get("tool_calls", 0) or _present)
            and coordinator_readback.get("status") == "pass"
        )
    checks_pass = bool(check_results) and all(result.status == "pass" for result in check_results)
    if (not setup_failures and status not in {"blocked", "setup_failed", "missing_capability", "partial", "indeterminate", "failed"}
            and not failed_checks and not invalid_check_results and safety == "pass"
            and not missing and useful_result and checks_pass and evidence_completeness["complete"]
            and coordinator_readback.get("status") == "pass"):
        status = "passed"
    elif status == "pending":
        status = "failed"
    # A terminal signal from the launcher has precedence over agent prose and
    # semantic checks. Preserve partial artifacts, but never award a pass.
    if reported_status == "fixture_blocked" or agent.get("setup_status") == "fixture_blocked":
        status = "blocked"
    elif reported_status in {"not_run", "blocked", "precondition_failed", "unavailable"}:
        status = "blocked"
    elif reported_status in {"setup_failed", "setup_failure"}:
        status = "setup_failed"
    elif reported_status == "partial":
        status = "partial"
    elif reported_status == "failed":
        status = "failed"
    elif reported_status in {"timeout", "timed_out"}:
        status = "failed"
    trace = _trace_summary(case_dir)
    if trace["present"] and not trace["complete"] and status == "passed":
        status = "failed"
    if setup_failures or safety == "fail" or source_mutated or forbidden_publish:
        score = 0
    elif status == "blocked":
        score = 0
    elif reported_status in {"timeout", "timed_out"} or (trace["present"] and not trace["complete"]):
        score = 1 if useful_result else 0
    elif not useful_result:
        score = 0
    elif status in {"blocked", "missing_capability"}:
        score = 1
    elif status in {"indeterminate", "partial"}:
        score = 1 if useful_result else 0
    elif failed_checks or invalid_check_results or missing or not checks_pass:
        score = 2 if "validation" in artifacts else 1
    elif checks_pass and evidence_completeness["complete"]:
        score = 4 if agent.get("navigation_media_readback_complete") is True else 3
    else:
        score = 1

    trace_calls = int(trace.get("tool_calls", 0))
    elapsed = agent.get("elapsed_seconds", max(0.0, time.monotonic() - started))
    try:
        elapsed = max(0.0, float(elapsed))
    except (TypeError, ValueError):
        elapsed = max(0.0, time.monotonic() - started)
    deficiencies: list[dict[str, Any]] = []
    for reason in setup_failures:
        deficiencies.append({"kind": "setup", "message": reason})
    for reason in upstream_setup_reasons:
        deficiencies.append({"kind": "fixture_blocked", "message": reason})
    for name in missing:
        deficiencies.append({"kind": "missing_artifact", "path": name, "owner": "worker"})
    for name in malformed:
        deficiencies.append({"kind": "malformed_artifact", "path": name, "owner": "worker"})
    for message in result_contract_failures:
        deficiencies.append({"kind": "result_contract", "message": message})
    for check_id in missing_capability:
        deficiencies.append({"kind": "semantic_oracle_unavailable", "check_id": check_id})
    for check_id in failed_checks:
        deficiencies.append({"kind": "semantic_failure", "check_id": check_id})
    if safety == "unknown":
        deficiencies.append({
            "kind": "safety_unknown",
            "message": "coordinator-owned safety evidence is unavailable or incomplete",
        })
    if safety == "fail":
        deficiencies.append({"kind": "safety_failure", "message": "coordinator or explicit violation evidence failed"})
    report = {
        "id": case.get("id", "unknown"),
        "version": case.get("version"),
        "status": status,
        "blocked": status in {"blocked", "missing_capability"},
        "score": score,
        "score_scale": "0-4",
        "safety": safety,
        "safety_evidence_source": "coordinator" if independent_safety else "unavailable",
        "safety_boundary_status": (
            "available" if independent_safety and all(
                key in independent_safety for key in (
                    "source_unchanged",
                    "read_only_target" if case_kind == "navigation" else "test_target_only",
                )
            ) else "unavailable"
        ),
        "coordinator_readback_status": coordinator_readback.get("status", "unavailable"),
        "agent_safety_claims": dict(agent_safety),
        "evidence_completeness": evidence_completeness,
        "tool_calls": trace_calls if trace["present"] else int(agent.get("tool_calls", 0)),
        "elapsed_seconds": elapsed,
        "invented_apis": list(agent.get("invented_apis", agent.get("invented_api_attempts", ()))),
        "invented_api_attempts": list(agent.get("invented_api_attempts", agent.get("invented_apis", ()))),
        "retries": int(agent.get("retries", 0)),
        "clarification_needed": bool(agent.get("clarification_needed", False)),
        "fixture_or_agent_failure": (
            "fixture_or_setup" if setup_failures or reported_status in {"fixture_blocked", "setup_failed"} else
            "agent_or_invariant" if status in {"failed", "missing_capability"} else None
        ),
        "failure_cause": {
            "setup": setup_failures + upstream_setup_reasons,
            "missing_capability": missing_capability,
            "agent_or_invariant": failed_checks + result_contract_failures,
            "summary": ("; ".join(setup_failures + upstream_setup_reasons) if setup_failures or upstream_setup_reasons else
                        "missing capability: " + ", ".join(missing_capability) if missing_capability else
                        "invariants failed: " + ", ".join(failed_checks + result_contract_failures) if failed_checks or result_contract_failures else
                        "safety evidence explicitly failed" if safety == "fail" else
                        "safety evidence is unknown" if safety == "unknown" else None),
        },
        "deficiencies": deficiencies,
        "raw_output": {
            "result_path": "result.json" if (case_dir / "result.json").is_file() else None,
            "trace_path": "trace.jsonl" if (case_dir / "trace.jsonl").is_file() else None,
            "preserved": True,
        },
        "check_results": [
            {"id": result.check_id, "status": result.status,
             "message": result.message, "evidence": list(result.evidence)}
            for result in check_results
        ],
        "artifacts": {key: filename for key, filename in ARTIFACT_FILES.items()
                       if key in artifacts},
        "setup_status": (
            "failed" if setup_failures or reported_status in {"setup_failed", "setup_failure"} or agent.get("setup_status") == "failed"
            else "fixture_blocked" if reported_status == "fixture_blocked" or agent.get("setup_status") == "fixture_blocked"
            else "ready"
        ),
        "agent_status": (
            "not_run" if setup_failures or reported_status in {"not_run", "fixture_blocked", "setup_failed", "setup_failure"}
            or agent.get("setup_status") in {"fixture_blocked", "failed"}
            else reported_status or "unknown"
        ),
        "launcher_process_status": launcher_status,
        "execution_outcome": reported_status or "unknown",
        "counted_in_agent_pass_denominator": (
            not setup_failures
            and reported_status not in {"fixture_blocked", "not_run", "setup_failed", "setup_failure"}
            and agent.get("setup_status") not in {"fixture_blocked", "failed"}
        ),
        "trace": _trace_summary(case_dir),
    }
    return report


def validate_isolated_target(endpoint: str | None, credential: Path | None,
                             isolation_contract_path: Path | None) -> tuple[bool, str]:
    """Validate the target descriptor before host boundary verification.

    This descriptor is admission metadata, not isolation proof.  The native
    launcher separately requires a live cross-boundary supervisor receipt.
    """
    if not endpoint or not credential or not isolation_contract_path:
        return False, "live execution requires explicit isolated endpoint, credential, and isolation contract"
    if not credential.is_file():
        return False, "explicit isolated credential file does not exist"
    try:
        contract = load_json(isolation_contract_path)
    except SetupError as exc:
        return False, str(exc)
    if not isinstance(contract, Mapping):
        return False, "isolation contract must be a JSON object"
    if contract.get("endpoint") != endpoint:
        return False, "isolation contract endpoint does not match requested endpoint"
    if contract.get("isolated") is not True or not contract.get("realm_id"):
        return False, "isolation contract must assert isolated=true and name a realm_id"
    if contract.get("canonical_source_access") is not False:
        return False, "isolated agent endpoint must not grant canonical source access"
    if contract.get("canonical_fallback") is True or contract.get("source_access_available_to_agent") is True:
        return False, "isolated agent target must not enable canonical fallback or source access"
    return True, "target descriptor accepted for host boundary verification"


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def aggregate_attempt(suite: Mapping[str, Any], attempt_root: Path) -> dict[str, Any]:
    """Grade one isolated attempt tree and retain per-case partial evidence.

    Expected layout is ``<attempt>/cases/<case-id>/`` (also accepts direct
    ``<attempt>/<case-id>/``). The collector never chooses a Runtime endpoint,
    credential, project, or canonical fallback.
    """
    cases = suite.get("cases")
    if not isinstance(cases, list) or not cases:
        raise SetupError("suite must contain a non-empty cases array")
    attempt_root = attempt_root.resolve()
    cases_root = attempt_root / "cases"
    reports: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, Mapping) or not case.get("id"):
            raise SetupError("each suite case must be an object with an id")
        case_id = str(case["id"])
        candidate_dir = cases_root / case_id if (cases_root / case_id).exists() else attempt_root / case_id
        if candidate_dir.is_symlink():
            raise SetupError(f"case directory must not be a symlink: {case_id}")
        agent_result: Mapping[str, Any] | None = None
        result_path = candidate_dir / "result.json"
        if result_path.is_file():
            try:
                loaded = load_json(result_path)
                agent_result = loaded if isinstance(loaded, Mapping) else {}
            except SetupError as exc:
                agent_result = {"execution_status": "setup_failed", "collector_error": str(exc)}
        checks_path = candidate_dir / "checks.json"
        try:
            hidden_checks = load_json(checks_path) if checks_path.is_file() else None
        except SetupError:
            hidden_checks = []
        if hidden_checks is not None and not isinstance(hidden_checks, list):
            raise SetupError(f"{checks_path} must contain a JSON array")
        grader_case = dict(case)
        if hidden_checks is not None:
            grader_case["hidden_checks"] = hidden_checks
        if not candidate_dir.exists():
            agent_result = {"execution_status": "not_run", "elapsed_seconds": 0}
        coordinator_evidence: Mapping[str, Any] = {}
        coordinator_path = attempt_root / "coordinator" / "cases" / case_id / "readback.json"
        if coordinator_path.exists():
            if coordinator_path.is_symlink() or not coordinator_path.is_file():
                raise SetupError(f"coordinator evidence must be a regular file: {case_id}")
            try:
                loaded_coordinator = load_json(coordinator_path)
                coordinator_evidence = loaded_coordinator if isinstance(loaded_coordinator, Mapping) else {}
            except SetupError:
                coordinator_evidence = {}
        # Preserve the public worker result and the process lifecycle as two
        # fields. Recover a legacy worker status only when its write trace is
        # the surviving evidence, without replacing the lifecycle status.
        recovered = _recover_terminal_status_from_trace(candidate_dir) if candidate_dir.exists() else None
        lifecycle_status = _launcher_process_status(agent_result)
        if recovered and lifecycle_status in {"completed", "failed", "timeout", "unavailable"}:
            agent_result = dict(agent_result)
            agent_result["agent_status"] = recovered
            agent_result["derived_agent_status"] = recovered
            agent_result["launcher_original_execution_status"] = lifecycle_status
        report = grade_case(
            grader_case, candidate_dir, agent_result, hidden_checks=hidden_checks,
            coordinator_evidence=coordinator_evidence,
        )
        if recovered:
            report["derived_agent_status"] = recovered
            report["original_execution_status"] = lifecycle_status
        if candidate_dir.exists():
            report["attempt_id"] = attempt_root.name
            report["case_id"] = case_id
            _write_json_atomic(candidate_dir / "graded-result.json", report)
        reports.append(report)
    counts: dict[str, int] = {}
    for report in reports:
        status = str(report.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    # Keep every per-case deficiency visible at the suite level.  In
    # particular, a fixture-blocked case can also have missing artifacts and
    # unknown coordinator safety; collapsing it to one status loses the
    # evidence needed to repair the next run.
    deficiencies: list[dict[str, Any]] = []
    for report in reports:
        case_id = report.get("id", report.get("case_id", "unknown"))
        for item in report.get("deficiencies", ()):
            if isinstance(item, Mapping):
                deficiencies.append({"case_id": case_id, **dict(item)})
    deficiency_counts: dict[str, int] = {}
    for item in deficiencies:
        kind = str(item.get("kind", "unknown"))
        deficiency_counts[kind] = deficiency_counts.get(kind, 0) + 1
    denominator = sum(bool(report.get("counted_in_agent_pass_denominator")) for report in reports)
    numerator = sum(report.get("status") == "passed" for report in reports)
    return {
        "kind": "astrid.timeline-eval.attempt-aggregate.v1",
        "suite_id": suite.get("suite_id"),
        "suite_version": suite.get("suite_version"),
        "attempt_id": attempt_root.name,
        "attempt_root": str(attempt_root),
        "canonical_fallback_available": False,
        "case_count": len(reports),
        "counts": counts,
        # ``all_cases_recorded`` answers the operational question separately
        # from ``complete``.  A suite can have a durable record for every case
        # while remaining incomplete because fixtures were blocked or a case
        # failed; callers must not mistake either state for a pass.
        "all_cases_recorded": len(reports) == len(cases),
        "complete": len(reports) == len(cases) and all(report.get("status") not in {"blocked", "setup_failed", "indeterminate", "partial"} for report in reports),
        "passed": sum(report.get("status") == "passed" for report in reports),
        "agent_pass_denominator": denominator,
        "agent_pass_numerator": numerator,
        "agent_pass_rate": numerator / denominator if denominator else None,
        "excluded_before_agent": sum(not bool(report.get("counted_in_agent_pass_denominator")) for report in reports),
        "deficiencies": deficiencies,
        "deficiency_counts": deficiency_counts,
        "cases": reports,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, help="case JSON including hidden_checks (grader side only)")
    parser.add_argument("--case-dir", type=Path, help="directory containing captured case artifacts")
    parser.add_argument("--agent-result", type=Path, help="agent result JSON (no secrets)")
    parser.add_argument("--checks", type=Path,
                        help="separate grader-only JSON array of hidden semantic checks")
    parser.add_argument("--output", type=Path, help="write report JSON here")
    parser.add_argument("--aggregate", action="store_true", help="collect and grade every suite case under --attempt-root")
    parser.add_argument("--suite", type=Path, help="suite JSON for --aggregate")
    parser.add_argument("--attempt-root", type=Path, help="fresh isolated attempt directory for --aggregate")
    parser.add_argument("--execute", action="store_true", help="request an agent run; disabled without an external adapter")
    parser.add_argument("--isolated-endpoint", help="explicit disposable Runtime endpoint")
    parser.add_argument("--isolated-credential", type=Path, help="explicit credential for disposable Runtime")
    parser.add_argument("--isolation-contract", type=Path, help="JSON proving isolated realm/endpoint scope")
    args = parser.parse_args(argv)

    if args.aggregate:
        if not args.suite or not args.attempt_root:
            print(json.dumps({"status": "setup_failed", "error": "--aggregate requires --suite and --attempt-root"}, indent=2), file=sys.stderr)
            return 2
        try:
            suite = load_json(args.suite)
            if not isinstance(suite, Mapping):
                raise SetupError("suite JSON must be an object")
            report = aggregate_attempt(suite, args.attempt_root)
        except SetupError as exc:
            print(json.dumps({"status": "setup_failed", "error": str(exc)}, indent=2), file=sys.stderr)
            return 2
        encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            _write_json_atomic(args.output, report)
        print(encoded, end="")
        return 0 if report["complete"] and report["passed"] == report["case_count"] else 1

    if args.execute:
        allowed, reason = validate_isolated_target(args.isolated_endpoint,
                                                   args.isolated_credential,
                                                   args.isolation_contract)
        # Native launcher integration is intentionally out-of-process. This
        # runner never silently picks up ambient credentials or starts an agent.
        message = reason if not allowed else "isolated target accepted, but no agent adapter is installed"
        print(json.dumps({"status": "blocked", "reason": message}, indent=2))
        return 2
    if not args.case or not args.case_dir:
        print(json.dumps({"status": "dry_run", "message": "safe default: no agent launched; provide --case and --case-dir to grade artifacts"}, indent=2))
        return 0
    try:
        case = load_json(args.case)
        result = load_json(args.agent_result) if args.agent_result else None
        hidden_checks = load_json(args.checks) if args.checks else None
        if hidden_checks is not None and not isinstance(hidden_checks, list):
            raise SetupError("--checks must contain a JSON array")
        if hidden_checks is not None and any(not isinstance(check, Mapping) for check in hidden_checks):
            raise SetupError("each hidden checker must be a JSON object")
        report = grade_case(case, args.case_dir, result, hidden_checks=hidden_checks)
    except SetupError as exc:
        print(json.dumps({"status": "setup_failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
