"""Reinspect saved timeline-evaluation evidence without launching a worker.

The worker result is deliberately not a grading input.  Semantic checks use
the coordinator's before/after JSON and optional hidden checks; a separate
independent readback record must also confirm that both observations were
captured.  Missing or incomplete inspection machinery is reported as
``unreviewed`` so it does not become a launch prerequisite.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .checks import DecodedMediaVerifier, run_checks
from .fixture_manifest import DEFAULT_SUITE
from .run import SetupError, load_json


INSPECTION_KIND = "astrid.timeline-eval.local-inspection.v1"
REVIEW_STATUSES = frozenset({"pass", "fail", "unreviewed"})


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _load_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if path.is_symlink() or not path.is_file():
        return None, "missing or unsafe"
    try:
        value = load_json(path)
    except (SetupError, OSError) as exc:
        return None, str(exc)
    if not isinstance(value, Mapping):
        return None, "must contain a JSON object"
    return dict(value), None


def _case_readback(case_dir: Path, case_id: str, attempt_root: Path) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    candidates = (
        case_dir / "readback.json",
        attempt_root / "coordinator" / "cases" / case_id / "readback.json",
    )
    for path in candidates:
        if path.is_symlink():
            return None, path, "readback path is unsafe"
        if not path.is_file():
            continue
        value, error = _load_object(path)
        if error:
            return None, path, f"readback is unreadable: {error}"
        # Accept either the direct readback result or the existing coordinator
        # sidecar envelope; neither form accepts a worker-authored claim.
        nested = value.get("readback")
        return (dict(nested) if isinstance(nested, Mapping) else value), path, None
    return None, None, "independent readback is not recorded"


def _artifact(case_dir: Path, primary: str, alternate: str) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    for name in (primary, alternate):
        path = case_dir / name
        if path.is_symlink():
            return None, path, f"{name} is unsafe"
        if not path.exists():
            continue
        value, error = _load_object(path)
        if error:
            return None, path, f"{name} is unreadable: {error}"
        # Preserve the established ``target.*`` paths while also allowing
        # direct semantic projections used by the local loop.  This is a view
        # over coordinator artifacts only; it does not add worker claims.
        target = value.get("target")
        if isinstance(target, Mapping):
            value.update(target)
        else:
            value["target"] = dict(value)
        return value, path, None
    return None, None, f"{primary} / {alternate} is not recorded"


def _manual_review(case_dir: Path) -> tuple[dict[str, Any] | None, Path | None, str | None]:
    path = case_dir / "manual-review.json"
    if not path.exists():
        return None, None, None
    value, error = _load_object(path)
    if error:
        return None, path, f"manual review is unreadable: {error}"
    status = value.get("status")
    # The local runner's established shape records the disposition alongside
    # task outcome, evidence sufficiency, safety, and notes. Normalize its
    # disposition for this inspector while retaining every supplied field.
    if status is None and value.get("manual_review") in {"pass", "fail"}:
        value["status"] = value["manual_review"]
        status = value["status"]
    reviewer = value.get("reviewer")
    rationale = value.get("rationale")
    evidence = value.get("evidence", value.get("evidence_paths"))
    if status not in {"pass", "fail"}:
        return None, path, "manual review status must be pass or fail"
    if not isinstance(reviewer, str) or not reviewer.strip():
        if "manual_review" in value:
            return value, path, None
        return None, path, "manual review must name an independent reviewer"
    if not isinstance(rationale, str) or not rationale.strip():
        return None, path, "manual review must include a rationale"
    if not isinstance(evidence, list) or not evidence or any(not isinstance(item, str) or not item for item in evidence):
        return None, path, "manual review must reference concrete evidence paths"
    return value, path, None


def inspect_case(
    case_id: str,
    case_dir: Path,
    attempt_root: Path,
    *,
    verifier: DecodedMediaVerifier | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Independently inspect one saved case and return its review record."""
    case_dir = case_dir.expanduser().absolute()
    attempt_root = attempt_root.expanduser().absolute()
    paths: dict[str, str | None] = {}
    reasons: list[str] = []
    before, before_path, before_error = _artifact(case_dir, "canonical-before.json", "before.json")
    after, after_path, after_error = _artifact(case_dir, "canonical-after.json", "after.json")
    paths["before"] = before_path.relative_to(attempt_root).as_posix() if before_path else None
    paths["after"] = after_path.relative_to(attempt_root).as_posix() if after_path else None
    if before_error:
        reasons.append(before_error)
    if after_error:
        reasons.append(after_error)

    checks_path = case_dir / "checks.json"
    checks: Any = None
    if checks_path.is_symlink():
        reasons.append("checks.json is unsafe")
    elif checks_path.is_file():
        try:
            checks = load_json(checks_path)
        except (SetupError, OSError) as exc:
            reasons.append(f"checks.json is unreadable: {exc}")
    else:
        reasons.append("independent checker is not recorded")
    paths["checks"] = checks_path.relative_to(attempt_root).as_posix() if checks_path.is_file() else None

    readback, readback_path, readback_error = _case_readback(case_dir, case_id, attempt_root)
    paths["readback"] = readback_path.relative_to(attempt_root).as_posix() if readback_path else None
    if readback_error:
        reasons.append(readback_error)

    check_results: list[dict[str, Any]] = []
    if isinstance(checks, list) and checks and before is not None and after is not None:
        artifacts: dict[str, Any] = {"before": before, "after": after}
        result, result_path, result_error = _artifact(case_dir, "coordinator-result.json", "result.json")
        if result is not None:
            artifacts["result"] = result
            paths["worker_result"] = result_path.relative_to(attempt_root).as_posix() if result_path else None
        else:
            # A result-dependent checker cannot be completed without an input;
            # generic check execution records this as a failed check, which is
            # converted below to unreviewed when the dependency is absent.
            paths["worker_result"] = None
        try:
            check_results = [
                {
                    "id": row.check_id,
                    "status": "unreviewed" if row.status == "missing_capability" else row.status,
                    "message": row.message,
                    "evidence": list(row.evidence),
                }
                for row in run_checks(checks, artifacts, verifier)
            ]
        except Exception as exc:  # checkers are untrusted plugins/adapters
            reasons.append(f"checker failed: {type(exc).__name__}: {exc}")
    elif checks is not None and (not isinstance(checks, list) or not checks):
        reasons.append("checks.json must contain a non-empty checker list")

    readback_status = None
    if readback is not None:
        readback_status = readback.get("status")
        if (readback.get("before_observed") is not True or readback.get("after_observed") is not True
                or readback_status not in {"pass", "fail"}):
            reasons.append("independent before/after readback is incomplete")

    manual, manual_path, manual_error = _manual_review(case_dir)
    paths["manual_review"] = manual_path.relative_to(attempt_root).as_posix() if manual_path else None
    if manual_error:
        reasons.append(manual_error)

    check_statuses = [row["status"] for row in check_results]
    if manual is not None and checks is not None:
        status = str(manual["status"])
        disposition_source = "independent_manual_review"
    elif (before is None or after is None or not check_results or readback is None
          or any(reason for reason in reasons)
          or "unreviewed" in check_statuses):
        status = "unreviewed"
        disposition_source = "automated_inspection"
    elif readback_status == "fail" or "fail" in check_statuses:
        status = "fail"
        disposition_source = "automated_inspection"
    elif all(value == "pass" for value in check_statuses) and readback_status == "pass":
        status = "pass"
        disposition_source = "automated_inspection"
    else:
        status = "unreviewed"
        disposition_source = "automated_inspection"

    record = {
        "kind": INSPECTION_KIND,
        "case_id": case_id,
        "status": status,
        "disposition_source": disposition_source,
        "readback_status": readback_status,
        "checks": check_results,
        "manual_review": manual,
        "artifact_paths": paths,
        "reasons": list(dict.fromkeys(reasons)),
    }
    if write:
        _write_json(case_dir / "inspection.json", record)
    return record


def inspect_attempt(
    attempt_root: Path,
    *,
    suite_path: Path = DEFAULT_SUITE,
    verifier: DecodedMediaVerifier | None = None,
) -> dict[str, Any]:
    """Reinspect all suite cases in an existing attempt without any launch."""
    root = attempt_root.expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError("attempt root must be an existing non-symlink directory")
    suite = load_json(suite_path)
    cases = suite.get("cases") if isinstance(suite, Mapping) else None
    if not isinstance(cases, list):
        raise ValueError("suite does not contain cases")
    rows = []
    for case in cases:
        if not isinstance(case, Mapping) or not isinstance(case.get("id"), str):
            continue
        case_id = str(case["id"])
        case_dir = root / "cases" / case_id
        if case_dir.is_symlink():
            rows.append({
                "kind": INSPECTION_KIND, "case_id": case_id,
                "status": "unreviewed", "disposition_source": "automated_inspection",
                "readback_status": None, "checks": [], "manual_review": None,
                "artifact_paths": {}, "reasons": ["case directory is unsafe"],
            })
            continue
        if not case_dir.is_dir():
            case_dir.mkdir(parents=True, exist_ok=True)
        rows.append(inspect_case(case_id, case_dir, root, verifier=verifier))
    totals = {status: sum(row["status"] == status for row in rows) for status in sorted(REVIEW_STATUSES)}
    output = {
        "kind": INSPECTION_KIND,
        "attempt_root": str(root),
        "suite_id": suite.get("suite_id") if isinstance(suite, Mapping) else None,
        "case_count": len(rows),
        "totals": totals,
        "cases": rows,
    }
    _write_json(root / "inspection.json", output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt_root", type=Path)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    args = parser.parse_args(argv)
    result = inspect_attempt(args.attempt_root, suite_path=args.suite)
    print(json.dumps({"status": "ok", "attempt_root": result["attempt_root"], "case_count": result["case_count"], "totals": result["totals"]}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["INSPECTION_KIND", "inspect_attempt", "inspect_case", "main"]
