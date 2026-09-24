"""Small local sequential loop for manual timeline-evaluation evidence.

This module is deliberately not a launcher, grader, or AgentBox adapter.  By
default it writes a no-model plan for all twenty cases.  An operator may later
provide an explicit per-case command; the loop preserves that command's raw
transcript/result and records execution separately from a human review.  It
never assigns a score or turns an absent safety witness into a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .admission_rehearsal import _target_preparation_state
from .fixture_manifest import DEFAULT_FIXTURE_ROOT, DEFAULT_SUITE, build_readiness
from .run import load_json


LOOP_KIND = "astrid.timeline-eval.local-manual-loop.v1"
EXECUTION_STATUSES = frozenset({
    "not_launched", "completed", "timed_out", "interrupted", "launcher_failed",
})
TASK_OUTCOMES = frozenset({"completed", "partial", "failed", "not_assessed"})
EVIDENCE_STATUSES = frozenset({"sufficient", "insufficient", "unavailable", "not_collected"})
SAFETY_STATUSES = frozenset({"supported", "violation", "unknown"})
MANUAL_REVIEW_STATUSES = frozenset({"pass", "fail", "undetermined"})


@dataclass(frozen=True)
class ManualCaseRecord:
    case_id: str
    kind: str
    execution: str
    task_outcome: str
    manual_review: str
    evidence_sufficiency: str
    safety: str
    case_root: str
    target_receipt: str | None
    canonical_before: str | None
    canonical_after: str | None
    transcript: str | None
    result: str | None
    returncode: int | None
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.execution not in EXECUTION_STATUSES:
            raise ValueError(f"invalid execution status: {self.execution}")
        if self.task_outcome not in TASK_OUTCOMES:
            raise ValueError(f"invalid task outcome: {self.task_outcome}")
        if self.manual_review not in MANUAL_REVIEW_STATUSES:
            raise ValueError(f"invalid manual review: {self.manual_review}")
        if self.evidence_sufficiency not in EVIDENCE_STATUSES:
            raise ValueError(f"invalid evidence status: {self.evidence_sufficiency}")
        if self.safety not in SAFETY_STATUSES:
            raise ValueError(f"invalid safety status: {self.safety}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _regular_file(path: Path | None) -> Path | None:
    if path is None or path.is_symlink() or not path.is_file():
        return None
    return path


def _relative(path: Path | None, root: Path) -> str | None:
    path = _regular_file(path)
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _copy_target_receipt(target_root: Path | None, case_id: str, case_root: Path) -> Path | None:
    if target_root is None:
        return None
    source = target_root / case_id / "target.json"
    if source.is_symlink() or not source.is_file():
        return None
    state, receipt = _target_preparation_state(target_root, case_id)
    if state != "receipt" or not isinstance(receipt, Mapping):
        return None
    destination = case_root / "target-receipt.json"
    destination.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return destination


def _review(case_root: Path) -> tuple[str, str, str, str, tuple[str, ...]]:
    path = _regular_file(case_root / "manual-review.json")
    if path is None:
        return "not_assessed", "undetermined", "not_collected", "unknown", ("manual review is not recorded",)
    try:
        value = load_json(path)
    except Exception as exc:  # noqa: BLE001 - malformed review is a review gap
        return "not_assessed", "undetermined", "unavailable", "unknown", (f"manual review is unreadable: {exc}",)
    if not isinstance(value, Mapping):
        return "not_assessed", "undetermined", "unavailable", "unknown", ("manual review is not an object",)
    outcome = str(value.get("task_outcome", "not_assessed"))
    manual = str(value.get("manual_review", "undetermined"))
    evidence = str(value.get("evidence_sufficiency", "not_collected"))
    safety = str(value.get("safety", "unknown"))
    if outcome not in TASK_OUTCOMES or manual not in MANUAL_REVIEW_STATUSES or evidence not in EVIDENCE_STATUSES or safety not in SAFETY_STATUSES:
        return "not_assessed", "undetermined", "unavailable", "unknown", ("manual review uses an unsupported status",)
    return outcome, manual, evidence, safety, tuple(str(item) for item in value.get("notes", ()) if item)


def _case_is_launchable(case: Mapping[str, Any], readiness: Mapping[str, Any], target_root: Path | None) -> tuple[bool, str]:
    if readiness.get("readiness") != "fixture_ready":
        return False, "fixture readiness is not fixture_ready"
    if case.get("kind") != "action":
        return True, "navigation entrypoint is fixture-ready"
    if target_root is None:
        return False, "action target root was not supplied"
    state, target = _target_preparation_state(target_root, str(case.get("id", "")))
    edit = target.get("capabilities", {}).get("edit", {}) if isinstance(target, Mapping) else {}
    if state != "receipt":
        return False, f"action target receipt state is {state}"
    if not isinstance(edit, Mapping) or edit.get("status") != "available":
        return False, "target receipt has no available edit route"
    return True, "target and edit route are available"


def run_local_loop(
    suite_path: Path = DEFAULT_SUITE,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    *,
    attempt_root: Path,
    target_root: Path | None = None,
    execute: bool = False,
    case_command: str | None = None,
    timeout_seconds: int = 3600,
    case_ids: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Create a sequential, review-oriented twenty-case run.

    ``execute=False`` is the safe default and launches nothing.  With
    ``execute=True`` an operator must supply an explicit command template; it
    receives ``{case_id}``, ``{case_root}``, ``{attempt_root}``, and
    ``{target_receipt}`` substitutions.  A command's exit status is lifecycle
    evidence only, not a task score.
    """
    if execute and not case_command:
        raise ValueError("--execute requires an explicit case command template")
    suite = load_json(suite_path)
    cases = suite.get("cases") if isinstance(suite, Mapping) else None
    if not isinstance(cases, list):
        raise ValueError("suite does not contain cases")
    selected = set(case_ids) if case_ids is not None else None
    readiness = {row.case_id: row for row in build_readiness(suite_path, fixture_root)}
    root = attempt_root.expanduser().absolute()
    if root.exists() and root.is_symlink():
        raise ValueError("attempt root must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    records: list[ManualCaseRecord] = []
    for raw in cases:
        if not isinstance(raw, Mapping) or not raw.get("id"):
            raise ValueError("suite case is missing an id")
        case_id = str(raw["id"])
        if selected is not None and case_id not in selected:
            continue
        case_root = root / "cases" / case_id
        case_root.mkdir(parents=True, exist_ok=True)
        target_copy = _copy_target_receipt(target_root, case_id, case_root)
        can_launch, launch_reason = _case_is_launchable(raw, readiness.get(case_id, {}).__dict__, target_root)
        notes: list[str] = [launch_reason]
        returncode: int | None = None
        if not execute or not can_launch:
            execution = "not_launched"
            notes.append("no model launched; raw case root preserved")
        else:
            command = case_command.format(
                case_id=case_id, case_root=str(case_root), attempt_root=str(root),
                target_receipt=str(target_copy) if target_copy else "",
            )
            (case_root / "command.json").write_text(json.dumps({"argv": shlex.split(command), "command": command}, indent=2) + "\n", encoding="utf-8")
            try:
                completed = subprocess.run(
                    shlex.split(command), cwd=str(root), timeout=timeout_seconds,
                    capture_output=True, text=True, check=False,
                )
                returncode = completed.returncode
                (case_root / "transcript.txt").write_text(completed.stdout + completed.stderr, encoding="utf-8")
                execution = "completed" if completed.returncode == 0 else "launcher_failed"
                notes.append("launcher lifecycle recorded; task outcome requires manual review")
            except subprocess.TimeoutExpired as exc:
                execution = "timed_out"
                (case_root / "transcript.txt").write_text((exc.stdout or "") + (exc.stderr or ""), encoding="utf-8")
                notes.append("timeout artifacts preserved; no automatic retry")
            except KeyboardInterrupt:
                execution = "interrupted"
                notes.append("interrupted; case root preserved")
        outcome, manual, evidence, safety, review_notes = _review(case_root)
        notes.extend(review_notes)
        records.append(ManualCaseRecord(
            case_id=case_id, kind=str(raw.get("kind", "unknown")), execution=execution,
            task_outcome=outcome, manual_review=manual, evidence_sufficiency=evidence, safety=safety,
            case_root=str(case_root), target_receipt=_relative(target_copy, root),
            canonical_before=_relative(case_root / "canonical-before.json", root),
            canonical_after=_relative(case_root / "canonical-after.json", root),
            transcript=_relative(case_root / "transcript.txt", root),
            result=_relative(case_root / "result.json", root), returncode=returncode,
            notes=tuple(dict.fromkeys(notes)),
        ))
    matrix = {
        "kind": LOOP_KIND, "suite_id": suite.get("suite_id"),
        "suite_version": suite.get("suite_version"),
        # This generic seam does not know whether an explicit command launches
        # a model; only the host runner may assert that separately.
        "model_launched": False, "execution_requested": execute,
        "automatic_scoring": False, "case_count": len(records),
        "records": [record.as_dict() for record in records],
        "controls": {
            "sequential": True, "retry": "none", "failed_roots_preserved": True,
            "manual_review_required": True, "unknown_safety_is_not_pass": True,
            "agentbox_prerequisite": False,
        },
    }
    _write_json(root / "local-loop.json", matrix)
    return matrix


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path)
    parser.add_argument("--case", dest="case_ids", action="append")
    parser.add_argument("--execute", action="store_true", help="run the explicit command template")
    parser.add_argument("--case-command", help="argv template; supports {case_id}, {case_root}, {attempt_root}, {target_receipt}")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args(argv)
    result = run_local_loop(
        args.suite, args.fixture_root, attempt_root=args.attempt_root,
        target_root=args.target_root, execute=args.execute,
        case_command=args.case_command, timeout_seconds=args.timeout_seconds,
        case_ids=args.case_ids,
    )
    print(json.dumps({"status": "ok", "attempt_root": str(args.attempt_root), "case_count": result["case_count"], "model_launched": result["model_launched"], "execution_requested": result["execution_requested"]}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["LOOP_KIND", "ManualCaseRecord", "run_local_loop"]
