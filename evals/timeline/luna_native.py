"""Run one native Luna timeline-evaluation attempt.

This is deliberately a thin adapter around the existing timeline fixture
readiness and :func:`evals.timeline.run.aggregate_attempt` collector.  It does
not seed Runtime or implement another grading harness.  A native execution
must be accompanied by an explicit disposable Runtime isolation contract;
without one the launcher fails closed.  Each fixture-ready case gets one OMP
one-shot invocation with ``--no-session``; fixture-blocked cases receive an
explicit blocked record instead.

The launcher writes only public case briefs before an agent starts.  Grader
checks are materialized after the process exits, so an evaluated agent cannot
read ``checks.json`` as part of its fresh context.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection, Mapping

from .fixture_manifest import DEFAULT_FIXTURE_ROOT, build_readiness
from .run import HIDDEN_KEYS, SetupError, aggregate_attempt, load_json, visible_brief


DEFAULT_SUITE = Path(__file__).with_name("suite.json")
DEFAULT_BRIEFS = Path(__file__).with_name("cases") / "agent_briefs.json"
DEFAULT_MODEL = "openai-codex/gpt-5.6-luna"
ATTEMPT_KIND = "astrid.timeline-eval.case-attempt.v1"
ATTEMPT_RESULT_KIND = "astrid.timeline-eval.native-attempt.v1"
CASE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


class NativeLauncherError(SetupError):
    """The attempt cannot be started without inventing fixture/runtime state."""


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_case_id(value: Any) -> str:
    case_id = str(value)
    if not CASE_ID.fullmatch(case_id) or case_id in {".", ".."}:
        raise NativeLauncherError(f"invalid suite case id: {case_id!r}")
    return case_id


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _public_brief(
    case: Mapping[str, Any],
    public_case: Mapping[str, Any] | None,
    *,
    fixture_root: Path,
    case_dir: Path,
) -> dict[str, Any]:
    """Build one agent-visible brief without verifier-only fields."""
    source = dict(public_case or visible_brief(case))
    # Be defensive when a caller supplies a hand-written brief.  The public
    # brief is a fresh object; no hidden check list or suite contract is copied.
    source = {key: value for key, value in source.items() if key not in HIDDEN_KEYS}
    source.setdefault("id", case.get("id"))
    source.setdefault("version", case.get("version"))
    source["fixture_entry_point"] = {
        # Do not disclose the shared fixture repository: it contains private
        # manifests, answer material (notably the A10 brightness ordering),
        # grader inputs and other cases.  A real disposable seed places only
        # the selected case's public entry point under this directory.
        "root": str(case_dir.resolve()),
        "case_id": str(case["id"]),
        "case_directory": str(case_dir.resolve()),
        "scope": "selected-case-only",
        "read_only": case.get("kind") == "navigation",
        "instruction": "Use only this supplied fixture entry point and public tools; do not read suite or grader files.",
    }
    return source


def _load_public_briefs(path: Path) -> dict[str, Mapping[str, Any]]:
    if not path.is_file():
        return {}
    value = load_json(path)
    rows = value.get("cases") if isinstance(value, Mapping) else None
    if not isinstance(rows, list):
        raise NativeLauncherError(f"public briefs must contain a cases array: {path}")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("id"):
            raise NativeLauncherError(f"public brief row is missing an id: {path}")
        result[_safe_case_id(row["id"])] = row
    return result


def _clean_child_environment() -> dict[str, str]:
    """Keep provider auth while excluding ambient Runtime/project credentials.

    A clean environment is only hygiene; it is not an isolation boundary.  A
    native attempt therefore also requires an explicit disposable Runtime
    contract (unless the caller is using the test-only fixture adapter).
    """
    blocked_fragments = (
        "ASTRID_RUNTIME", "ASTRID_CANONICAL", "RUNTIME_CREDENTIAL",
        "RUNTIME_TOKEN", "SUPABASE_SERVICE", "SUPABASE_SECRET",
    )
    return {
        key: value for key, value in os.environ.items()
        if not any(fragment in key.upper() for fragment in blocked_fragments)
    }


def _prompt(case: Mapping[str, Any]) -> str:
    return (
        "You are the evaluated Luna agent in one fresh, bounded context.\n"
        "Read only the selected public brief at brief.json and its supplied fixture entry point.\n"
        "Use normal public tools and documentation, and work only inside this disposable case directory.\n"
        "Do not inspect the versioned suite, grader files, prior attempts, or canonical Runtime.\n"
        "Perform the requested navigation or candidate edit if the fixture supports it. "
        "If a precondition or public capability is unavailable, stop and report that honestly.\n"
        "Record useful evidence under evidence/ and write a JSON result record to result.json "
        "when you can; do not claim an edit, render, playback, or publication you did not observe.\n\n"
        f"Selected case: {case.get('id')}\n"
        "The complete public brief is in brief.json."
    )


def _trace_lines(case_dir: Path, *, events: list[dict[str, Any]]) -> None:
    with (case_dir / "trace.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _invoke(
    *,
    omp_bin: str,
    model: str,
    case: Mapping[str, Any],
    case_dir: Path,
    isolated_endpoint: str | None = None,
    isolated_credential: Path | None = None,
    isolation_contract: Path | None = None,
    fixture_only: bool = False,
) -> tuple[str, int | None, float, list[dict[str, Any]], str]:
    """Invoke exactly one fresh OMP context and capture stdout/stderr as trace."""
    timeout_value = _mapping(case.get("timeout")).get("value", 600)
    try:
        timeout_seconds = max(1.0, float(timeout_value))
    except (TypeError, ValueError):
        timeout_seconds = 600.0
    command = [
        omp_bin,
        "--model", model,
        "--no-session",
        "--mode", "json",
        "--auto-approve",
        "--max-time", f"{int(timeout_seconds)}s",
        "--cwd", str(case_dir),
        "--print",
        _prompt(case),
    ]
    started = time.monotonic()
    events: list[dict[str, Any]] = [{
        "event": "launcher_start",
        "at": _now(),
        "case_id": str(case["id"]),
        "fresh_context": True,
        "model": model,
        "invocation": command,
    }]
    try:
        child_env = _clean_child_environment()
        if isolated_endpoint:
            child_env.update({
                "ASTRID_TIMELINE_EVAL_ENDPOINT": isolated_endpoint,
                "ASTRID_TIMELINE_EVAL_CREDENTIAL": str(isolated_credential),
                "ASTRID_TIMELINE_EVAL_ISOLATION_CONTRACT": str(isolation_contract),
                "ASTRID_TIMELINE_EVAL_SOURCE_ACCESS": "false",
            })
        if fixture_only:
            child_env["ASTRID_TIMELINE_EVAL_FIXTURE_ONLY"] = "1"
        process = subprocess.Popen(
            command,
            cwd=case_dir,
            env=child_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        elapsed = max(0.0, time.monotonic() - started)
        events.append({"event": "launcher_error", "at": _now(), "error": f"{type(exc).__name__}: {exc}"})
        events.append({"event": "launcher_exit", "at": _now(), "status": "unavailable", "returncode": None})
        return "unavailable", None, elapsed, events, ""
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        status = "completed" if process.returncode == 0 else "failed"
    except subprocess.TimeoutExpired:
        process.kill()
        stdout, stderr = process.communicate()
        status = "timeout"
    elapsed = max(0.0, time.monotonic() - started)
    for stream, text in (("stdout", stdout), ("stderr", stderr)):
        for line_number, line in enumerate((text or "").splitlines(), 1):
            events.append({
                "event": "agent_output",
                "stream": stream,
                "line": line_number,
                "text": line,
            })
    events.append({
        "event": "launcher_exit",
        "at": _now(),
        "status": status,
        "returncode": process.returncode,
        "elapsed_seconds": elapsed,
    })
    output = stdout or ""
    if stderr:
        output += ("\n" if output else "") + stderr
    return status, process.returncode, elapsed, events, output


def _merge_result(
    case_dir: Path,
    *,
    case: Mapping[str, Any],
    attempt_id: str,
    session_id: str,
    status: str,
    returncode: int | None,
    elapsed: float,
    output: str,
    model: str,
) -> dict[str, Any]:
    agent_result: dict[str, Any] = {}
    result_path = case_dir / "result.json"
    if result_path.is_file():
        try:
            loaded = load_json(result_path)
            if isinstance(loaded, Mapping):
                agent_result = dict(loaded)
        except SetupError as exc:
            agent_result["agent_result_error"] = str(exc)
    # A one-shot agent may return its terminal record in stdout instead of
    # writing the optional file.  Recover only an explicit JSON object with a
    # result-shaped field; never treat free-form prose as an evaluation result.
    if not agent_result and output:
        for line in reversed(output.splitlines()):
            candidate = line.strip()
            if not candidate.startswith("{") or not candidate.endswith("}"):
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping) and any(
                key in parsed for key in ("execution_status", "navigation_performed", "edit_made", "safety")
            ):
                agent_result = dict(parsed)
                break
    result = dict(agent_result)
    # Keep the agent's terminal declaration distinct from the subprocess
    # lifecycle.  In particular, an agent can honestly report ``blocked``
    # after discovering that a requested public capability is unavailable
    # even though OMP itself exited successfully.
    reported_status = str(result.get("execution_status", result.get("status", ""))).lower()
    terminal_statuses = {
        "passed", "failed", "blocked", "missing_capability", "setup_failed",
        "precondition_failed", "unavailable", "fixture_blocked", "timeout",
        "timed_out", "not_run",
    }
    if reported_status in terminal_statuses:
        result["agent_execution_status"] = reported_status
    else:
        result["agent_execution_status"] = None
    result.update({
        "kind": "astrid.timeline-eval.agent-result.v1",
        "attempt_id": attempt_id,
        "case_id": str(case["id"]),
        "session_id": session_id,
        "fresh_context": True,
        "launcher_process_status": status,
        "execution_status": reported_status if reported_status in terminal_statuses else status,
        "returncode": returncode,
        "elapsed_seconds": elapsed,
        "launcher": {
            "kind": "omp",
            "model": model,
            "output_captured": bool(output),
            "one_shot": True,
            "no_session": True,
        },
    })
    if output:
        (case_dir / "agent-output.txt").write_text(output, encoding="utf-8")
    _write_json(result_path, result)
    return result


def _hidden_checks(case: Mapping[str, Any], *, fixture_root: Path) -> list[dict[str, Any]]:
    """Return only checkers already implemented by ``checks.py``.

    Most narrative checks need decoded media, audio, or a case-specific oracle
    that is not currently available.  They intentionally remain ungraded
    rather than being approximated here.
    """
    case_id = str(case.get("id"))
    action_manifest = fixture_root / "action" / "manifest.json"
    manifest: Mapping[str, Any] = {}
    if action_manifest.is_file():
        try:
            manifest = load_json(action_manifest)
        except SetupError:
            return []
    rows = manifest.get("cases", []) if isinstance(manifest, Mapping) else []
    fixture_case = next((row for row in rows if isinstance(row, Mapping) and row.get("id") == case_id), {})
    targets = _mapping(fixture_case).get("targets", {})
    # Every case needs at least one independent, machine-runnable terminal
    # assertion.  This generic result check is deliberately small: it grades
    # whether the fresh agent actually reported the requested operation, while
    # the case-specific checks below add stronger semantic invariants where the
    # fixture already provides an oracle.
    generic = {
        "id": f"{case_id.lower()}_terminal_operation",
        "check": "path_equals",
        "artifact": "result",
        "path": "navigation_performed" if case.get("kind") == "navigation" else "edit_made",
        "expected": True,
    }
    if case_id == "A03":
        original = list(targets.get("four_occurrences_in_order", ()))
        if len(original) == 4:
            closing = targets.get("closing_occurrence")
            middle = targets.get("middle_occurrence")
            expected = [closing, original[0], middle, original[1]] if closing and middle else []
            if expected:
                return [{
                    **generic,
                }, {
                    "id": "a03_order",
                    "check": "order",
                    "artifact": "after",
                    "path": "occurrences",
                    "id_path": "occurrence_id",
                    "expected_ids": expected,
                }]
    if case_id == "A04":
        return [generic, {
            "id": "a04_identity_disjoint",
            "check": "identity_disjoint",
            "before_artifact": "before",
            "after_artifact": "after",
            "original_ids_path": "identity_ids",
            "duplicate_ids_path": "duplicate.identity_ids",
        }]
    if case_id == "A09":
        return [generic, {
            "id": "a09_panel_coverage",
            "check": "panel_coverage",
            "artifact": "after",
            "path": "panels",
            "required": ["top-left", "top-right", "bottom-right", "bottom-left"],
            "width": 1,
            "height": 1,
            "label_path": "quadrant",
            "rect_path": "rect",
        }]
    if case_id == "A10":
        collection_path = fixture_root / "action" / "A10-brightness-collection.json"
        if collection_path.is_file():
            try:
                collection = load_json(collection_path)
                images = collection.get("images", []) if isinstance(collection, Mapping) else []
                expected = [row.get("media_id") for row in images if isinstance(row, Mapping) and row.get("media_id")]
                if len(expected) == 200:
                    return [generic, {
                        "id": "a10_brightness_order",
                        "check": "order",
                        "artifact": "after",
                        "path": "montage.clips",
                        "id_path": "media_id",
                        "expected_ids": expected,
                    }]
            except SetupError:
                pass
    return [generic]


def _fixture_blocked_result(
    case: Mapping[str, Any], *, attempt_id: str, reason: str, case_dir: Path
) -> dict[str, Any]:
    session_id = f"{attempt_id}-{case['id']}-not-launched"
    result = {
        "kind": "astrid.timeline-eval.agent-result.v1",
        "attempt_id": attempt_id,
        "case_id": str(case["id"]),
        "session_id": session_id,
        "fresh_context": False,
        "execution_status": "fixture_blocked",
        "elapsed_seconds": 0.0,
        "tool_calls": 0,
        "retries": 0,
        "clarification_needed": False,
        "fixture_or_agent_failure": "fixture",
        "failure_cause": {"setup": [reason], "summary": reason},
        "safety": {"source_unchanged": True, "test_target_only": True, "read_only_target": True},
    }
    _write_json(case_dir / "result.json", result)
    _trace_lines(case_dir, events=[{
        "event": "fixture_blocked",
        "at": _now(),
        "case_id": str(case["id"]),
        "reason": reason,
    }])
    return result


def run_attempt(
    suite_path: Path = DEFAULT_SUITE,
    attempt_root: Path | None = None,
    *,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    briefs_path: Path = DEFAULT_BRIEFS,
    omp_bin: str = "omp",
    model: str = DEFAULT_MODEL,
    execute: bool = True,
    launchable_ids: Collection[str] | None = None,
    isolated_endpoint: str | None = None,
    isolated_credential: Path | None = None,
    isolation_contract: Path | None = None,
    fixture_only: bool = False,
) -> dict[str, Any]:
    """Run and aggregate one immutable 20-case attempt.

    ``launchable_ids`` is an explicit test seam for fake adapters; normal
    callers leave it unset and use the fixture manifest's readiness result.
    Regardless of readiness, every suite case receives exactly one case
    directory and one terminal record.
    """
    suite = load_json(suite_path)
    if not isinstance(suite, Mapping) or not isinstance(suite.get("cases"), list) or not suite["cases"]:
        raise NativeLauncherError("suite must contain a non-empty cases array")
    if attempt_root is None:
        raise NativeLauncherError("an explicit fresh attempt root is required")
    if execute and not fixture_only:
        from .run import validate_isolated_target
        allowed, message = validate_isolated_target(
            isolated_endpoint, isolated_credential, isolation_contract
        )
        if not allowed:
            raise NativeLauncherError(
                "refusing native agent execution without an explicit disposable "
                f"Runtime isolation contract: {message}"
            )
    attempt_root = attempt_root.expanduser().absolute()
    if attempt_root.exists():
        if attempt_root.is_symlink() or not attempt_root.is_dir() or any(attempt_root.iterdir()):
            raise NativeLauncherError(f"attempt root must be new and non-symlink: {attempt_root}")
    attempt_root.mkdir(parents=True, exist_ok=True)
    cases_root = attempt_root / "cases"
    cases_root.mkdir()
    attempt_id = attempt_root.name
    public_briefs = _load_public_briefs(briefs_path)
    readiness = {row.case_id: row for row in build_readiness(suite_path, fixture_root)}
    forced = set(launchable_ids) if launchable_ids is not None else None
    top_level = {
        "kind": ATTEMPT_RESULT_KIND,
        "attempt_id": attempt_id,
        "suite_id": suite.get("suite_id"),
        "suite_version": suite.get("suite_version"),
        "model": model,
        "fresh_context_per_case": True,
        "case_count": len(suite["cases"]),
        "started_at": _now(),
        "canonical_fallback_available": False,
        "execution": "native_omp" if execute else "dry_run",
        "isolation": {
            "fixture_only": fixture_only,
            "endpoint": isolated_endpoint,
            "credential": str(isolated_credential) if isolated_credential else None,
            "contract": str(isolation_contract) if isolation_contract else None,
        },
    }
    _write_json(attempt_root / "attempt.json", top_level)
    if not execute:
        plan = []
        for case in suite["cases"]:
            case_id = _safe_case_id(_mapping(case).get("id"))
            row = readiness.get(case_id)
            plan.append({"case_id": case_id, "fixture_ready": bool(row and row.readiness == "fixture_ready")})
        top_level["plan"] = plan
        _write_json(attempt_root / "attempt.json", top_level)
        return top_level

    for raw_case in suite["cases"]:
        if not isinstance(raw_case, Mapping) or not raw_case.get("id"):
            raise NativeLauncherError("every suite case must be an object with an id")
        case = dict(raw_case)
        case_id = _safe_case_id(case["id"])
        case_dir = cases_root / case_id
        case_dir.mkdir()
        _write_json(case_dir / "brief.json", _public_brief(
            case, public_briefs.get(case_id), fixture_root=fixture_root, case_dir=case_dir
        ))
        row = readiness.get(case_id)
        is_ready = bool(row and row.readiness == "fixture_ready")
        if forced is not None:
            is_ready = case_id in forced
        if not is_ready:
            reason = "; ".join(row.reasons) if row and row.reasons else "fixture readiness was not established"
            session_id = f"{attempt_id}-{case_id}-not-launched"
            _write_json(case_dir / "attempt.json", {
                "kind": ATTEMPT_KIND,
                "attempt_id": attempt_id,
                "case_id": case_id,
                "fresh_context": False,
                "session_id": session_id,
                "started_at": _now(),
                "model": model,
                "execution": "fixture_blocked",
            })
            _fixture_blocked_result(case, attempt_id=attempt_id, reason=reason, case_dir=case_dir)
            _write_json(case_dir / "checks.json", _hidden_checks(case, fixture_root=fixture_root))
            continue
        session_id = f"{attempt_id}-{case_id}-{uuid.uuid4().hex[:12]}"
        started_at = _now()
        _write_json(case_dir / "attempt.json", {
            "kind": ATTEMPT_KIND,
            "attempt_id": attempt_id,
            "case_id": case_id,
            "fresh_context": True,
            "session_id": session_id,
            "started_at": started_at,
            "model": model,
            "execution": "native_omp",
        })
        status, returncode, elapsed, events, output = _invoke(
            omp_bin=omp_bin,
            model=model,
            case=case,
            case_dir=case_dir,
            isolated_endpoint=isolated_endpoint,
            isolated_credential=isolated_credential,
            isolation_contract=isolation_contract,
            fixture_only=fixture_only,
        )
        _trace_lines(case_dir, events=events)
        _merge_result(
            case_dir,
            case=case,
            attempt_id=attempt_id,
            session_id=session_id,
            status=status,
            returncode=returncode,
            elapsed=elapsed,
            output=output,
            model=model,
        )
        # Hidden checks are deliberately installed only after the agent exits.
        _write_json(case_dir / "checks.json", _hidden_checks(case, fixture_root=fixture_root))

    aggregate = aggregate_attempt(suite, attempt_root)
    _write_json(attempt_root / "aggregate.json", aggregate)
    top_level["finished_at"] = _now()
    top_level["aggregate"] = "aggregate.json"
    _write_json(attempt_root / "attempt.json", top_level)
    return aggregate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--briefs", type=Path, default=DEFAULT_BRIEFS)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--omp-bin", default="omp", help="OMP executable (default: omp)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--isolated-endpoint", help="explicit disposable Runtime endpoint")
    parser.add_argument("--isolated-credential", type=Path,
                        help="credential file for the disposable Runtime")
    parser.add_argument("--isolation-contract", type=Path,
                        help="JSON proof of the disposable Runtime boundary")
    parser.add_argument("--fixture-only", action="store_true",
                        help="test-only fake adapter mode; never use for a native model run")
    parser.add_argument("--dry-run", action="store_true", help="print a plan without launching any agent")
    args = parser.parse_args(argv)
    try:
        result = run_attempt(
            args.suite,
            args.attempt_root,
            fixture_root=args.fixture_root,
            briefs_path=args.briefs,
            omp_bin=args.omp_bin,
            model=args.model,
            execute=not args.dry_run,
            isolated_endpoint=args.isolated_endpoint,
            isolated_credential=args.isolated_credential,
            isolation_contract=args.isolation_contract,
            fixture_only=args.fixture_only,
        )
    except (NativeLauncherError, OSError, ValueError) as exc:
        print(json.dumps({"status": "setup_failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.dry_run:
        return 0
    return 0 if result.get("complete") and result.get("passed") == result.get("case_count") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
