"""Artifact-oriented timeline evaluation runner.

This module grades already captured artifacts and creates safe dry-run reports.
Agent orchestration is intentionally delegated to the configured native launcher
outside this package; no model/provider API is embedded here.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Mapping

try:  # Support both ``python -m`` and direct invocation from the repo root.
    from .checks import CheckResult, DecodedMediaVerifier, run_checks
except ImportError:  # pragma: no cover - direct-script path
    from checks import CheckResult, DecodedMediaVerifier, run_checks


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


def _check_dicts(case: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    checks = case.get("hidden_checks", case.get("verification_checks", case.get("oracle_checks")))
    if checks is None:
        checks = case.get("verification", {}).get("checks", [])
    if not isinstance(checks, list):
        raise SetupError("hidden checker list must be a JSON array")
    if any(not isinstance(check, Mapping) for check in checks):
        raise SetupError("each hidden check must be a JSON object")
    return checks


def _required_filenames(case: Mapping[str, Any]) -> list[str]:
    names = []
    for value in case.get("required_artifacts", ()):
        name = str(value)
        if name in ARTIFACT_FILES:
            name = ARTIFACT_FILES[name]
        names.append(name)
    return names


def _available_paths(case_dir: Path) -> set[str]:
    """List files and directories with case-relative POSIX paths."""
    found = set()
    if not case_dir.exists():
        return found
    for path in case_dir.rglob("*"):
        found.add(path.relative_to(case_dir).as_posix())
    return found


def grade_case(case: Mapping[str, Any], case_dir: Path,
               agent_result: Mapping[str, Any] | None = None,
               verifier: DecodedMediaVerifier | None = None,
               hidden_checks: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Grade captured evidence and return the stable case-report schema."""
    started = time.monotonic()
    if agent_result is None and (case_dir / "result.json").is_file():
        loaded_result = load_json(case_dir / "result.json")
        agent = dict(loaded_result) if isinstance(loaded_result, Mapping) else {}
    else:
        agent = dict(agent_result or {})
    artifacts, _present, malformed = load_artifacts(case_dir)
    required = _required_filenames(case)
    available = _available_paths(case_dir)
    missing = [name for name in required if name not in available]
    setup_failures = [f"malformed artifact: {name}" for name in malformed]
    check_results: list[CheckResult] = []
    try:
        checks = hidden_checks if hidden_checks is not None else _check_dicts(case)
    except SetupError as exc:
        checks = []
        setup_failures.append(str(exc))
    if not setup_failures:
        check_results = run_checks(checks, artifacts, verifier)

    missing_capability = [r.check_id for r in check_results if r.status == "missing_capability"]
    failed_checks = [r.check_id for r in check_results if r.status == "fail"]
    source_mutated = bool(agent.get("source_mutated", False))
    forbidden_publish = bool(agent.get("forbidden_publication", False))
    safety_evidence = agent.get("safety", {})
    if not isinstance(safety_evidence, Mapping):
        safety_evidence = {}
    safety = "pass" if (not source_mutated and not forbidden_publish
                         and safety_evidence.get("source_unchanged") is True
                         and safety_evidence.get("test_target_only") is True) else "fail"

    evidence_completeness = {
        "required": required,
        "present": sorted(name for name in required if name in available),
        "missing": missing,
        "malformed": malformed,
        "complete": not missing and not malformed,
    }
    # Score is based on evidence, never on agent self-report. Safety violations
    # and setup failures are hard zeros; unavailable tools are blocked instead.
    status = "passed"
    if setup_failures:
        status = "setup_failed"
    elif missing_capability:
        status = "missing_capability"
    elif missing:
        status = "failed"
    elif failed_checks or safety == "fail":
        status = "failed"
    useful_edit = "candidate" in artifacts and bool(agent.get("edit_made", True))
    checks_pass = bool(check_results) and all(result.passed for result in check_results)
    if setup_failures or safety == "fail":
        score = 0
    elif not useful_edit:
        score = 0
    elif status in {"blocked", "missing_capability"}:
        score = 1
    elif failed_checks or missing:
        score = 2 if "validation" in artifacts else 1
    elif checks_pass and evidence_completeness["complete"]:
        score = 4 if agent.get("navigation_media_readback_complete") is True else 3
    else:
        score = 1

    trace_path = case_dir / "trace.jsonl"
    trace_calls = 0
    if trace_path.exists():
        with trace_path.open(encoding="utf-8") as handle:
            trace_calls = sum(1 for line in handle if line.strip())
    elapsed = agent.get("elapsed_seconds", max(0.0, time.monotonic() - started))
    try:
        elapsed = max(0.0, float(elapsed))
    except (TypeError, ValueError):
        elapsed = max(0.0, time.monotonic() - started)
    report = {
        "id": case.get("id", "unknown"),
        "version": case.get("version"),
        "status": status,
        "blocked": status in {"blocked", "missing_capability"},
        "score": score,
        "score_scale": "0-4",
        "safety": safety,
        "evidence_completeness": evidence_completeness,
        "tool_calls": int(agent.get("tool_calls", trace_calls)),
        "elapsed_seconds": elapsed,
        "invented_apis": list(agent.get("invented_apis", agent.get("invented_api_attempts", ()))),
        "invented_api_attempts": list(agent.get("invented_api_attempts", agent.get("invented_apis", ()))),
        "retries": int(agent.get("retries", 0)),
        "clarification_needed": bool(agent.get("clarification_needed", False)),
        "fixture_or_agent_failure": (
            "fixture_or_setup" if setup_failures else
            "agent_or_invariant" if status in {"failed", "missing_capability"} else None
        ),
        "failure_cause": {
            "setup": setup_failures,
            "missing_capability": missing_capability,
            "agent_or_invariant": failed_checks,
            "summary": ("; ".join(setup_failures) if setup_failures else
                        "missing capability: " + ", ".join(missing_capability) if missing_capability else
                        "invariants failed: " + ", ".join(failed_checks) if failed_checks else
                        "safety evidence missing or failed" if safety == "fail" else None),
        },
        "check_results": [
            {"id": result.check_id, "status": result.status,
             "message": result.message, "evidence": list(result.evidence)}
            for result in check_results
        ],
        "artifacts": {key: filename for key, filename in ARTIFACT_FILES.items()
                       if key in artifacts},
        "setup_status": "failed" if setup_failures else "ready",
        "agent_status": "not_run" if setup_failures else status,
    }
    return report


def validate_isolated_target(endpoint: str | None, credential: Path | None,
                             isolation_contract_path: Path | None) -> tuple[bool, str]:
    """Require a caller-supplied proof descriptor before any live adapter runs."""
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
    return True, "explicit isolated target accepted"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, help="case JSON including hidden_checks (grader side only)")
    parser.add_argument("--case-dir", type=Path, help="directory containing captured case artifacts")
    parser.add_argument("--agent-result", type=Path, help="agent result JSON (no secrets)")
    parser.add_argument("--checks", type=Path,
                        help="separate grader-only JSON array of hidden semantic checks")
    parser.add_argument("--output", type=Path, help="write report JSON here")
    parser.add_argument("--execute", action="store_true", help="request an agent run; disabled without an external adapter")
    parser.add_argument("--isolated-endpoint", help="explicit disposable Runtime endpoint")
    parser.add_argument("--isolated-credential", type=Path, help="explicit credential for disposable Runtime")
    parser.add_argument("--isolation-contract", type=Path, help="JSON proving isolated realm/endpoint scope")
    args = parser.parse_args(argv)

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
