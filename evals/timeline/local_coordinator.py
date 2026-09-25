"""Filesystem-scoped before/after evidence for local disposable projects.

This coordinator does not implement Runtime reads or process isolation. It can
show that a pinned seed tree stayed unchanged and report the exact local target
tree observed after an operator-run case. Target-only write confinement stays
unknown because this adapter does not restrict what the worker can access.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping


LOCAL_EVIDENCE_KIND = "astrid.timeline-eval.local-coordinator-evidence.v1"


class LocalCoordinatorError(ValueError):
    """Local evidence inputs cannot be observed safely or consistently."""


def runtime_action_evidence_ready(
    *, case: Mapping[str, Any], target_path: str | Path, attempt_root: str | Path,
) -> tuple[bool, list[str]]:
    """Check case-scoped, current Runtime action evidence without trusting the agent.

    This is a completion/admission predicate, not a substitute for the live
    pre-launch boundary check. Filesystem-only coordinator evidence is always
    rejected. The target receipt hash must still match both the attempt and
    coordinator sidecar, and the sidecar must contain a passing independent
    Runtime readback plus post-teardown safety proof.
    """
    import hashlib

    from .fixture_contracts import action_target_contract, validate_action_target_receipt

    case_id = str(case.get("id", ""))
    reasons: list[str] = []
    target_file = Path(target_path)
    attempt = Path(attempt_root)
    case_dir = attempt / "cases" / case_id
    sidecar_path = attempt / "coordinator" / "cases" / case_id / "readback.json"
    unsafe_parent = next((path for path in (attempt, case_dir.parent, case_dir,
                                             sidecar_path.parent.parent, sidecar_path.parent)
                          if path.is_symlink()), None)
    if unsafe_parent is not None:
        return False, [f"case evidence path traverses a symlink: {unsafe_parent}"]
    for path, label in ((target_file, "target receipt"), (case_dir, "case artifacts"),
                        (sidecar_path, "coordinator readback")):
        if path.is_symlink():
            reasons.append(f"{label} path is a symlink")
    if reasons:
        return False, reasons
    try:
        target_document = json.loads(target_file.read_text(encoding="utf-8"))
        attempt_doc = json.loads((case_dir / "attempt.json").read_text(encoding="utf-8"))
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, [f"target/attempt/coordinator evidence unavailable: {exc}"]
    if not isinstance(target_document, Mapping):
        return False, ["target receipt must be an object"]
    target = target_document.get("target_receipt") if isinstance(target_document.get("target_receipt"), Mapping) else target_document
    contract = action_target_contract(case)
    reasons.extend(validate_action_target_receipt(target, contract))
    target_digest = hashlib.sha256(
        json.dumps(target, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if attempt_doc.get("attempt_id") != attempt.name or attempt_doc.get("case_id") != case_id:
        reasons.append("attempt manifest is not bound to this attempt and case")
    if attempt_doc.get("target_receipt_sha256") != target_digest:
        reasons.append("attempt target receipt digest is missing or stale")
    if sidecar.get("kind") != "astrid.timeline-eval.coordinator-evidence.v1":
        reasons.append("coordinator evidence is not a Runtime coordinator sidecar")
    if sidecar.get("case_id") != case_id:
        reasons.append("coordinator evidence is bound to another case")
    if sidecar.get("target_receipt_sha256") != target_digest:
        reasons.append("coordinator target receipt digest is missing or stale")
    readback = sidecar.get("readback") if isinstance(sidecar.get("readback"), Mapping) else {}
    if readback.get("status") != "pass" or readback.get("before_observed") is not True or readback.get("after_observed") is not True:
        reasons.append("coordinator Runtime before/after readback is not a passing complete observation")
    if not readback.get("projection"):
        reasons.append("coordinator readback has no case-specific semantic projection")
    safety = sidecar.get("safety") if isinstance(sidecar.get("safety"), Mapping) else {}
    for field in ("source_unchanged", "test_target_only"):
        if safety.get(field) is not True:
            reasons.append(f"coordinator safety evidence does not prove {field}=true")
    if not isinstance(sidecar.get("boundary"), Mapping):
        reasons.append("coordinator worker-boundary receipt is missing")
    if not isinstance(sidecar.get("host_final_capture"), Mapping):
        reasons.append("coordinator post-teardown Runtime capture is missing")
    for name in ("before.json", "after.json", "trace.jsonl", "result.json", "graded-result.json"):
        artifact = case_dir / name
        if artifact.is_symlink() or not artifact.is_file():
            reasons.append(f"case-scoped {name} artifact is missing or unsafe")
    return not reasons, list(dict.fromkeys(reasons))


@dataclass(frozen=True)
class LocalObservation:
    root: str
    anchor_name: str
    files: Mapping[str, str]
    tree_fingerprint: str
    document: Mapping[str, Any]


@dataclass(frozen=True)
class LocalBefore:
    case_id: str
    source: LocalObservation
    target: LocalObservation


def _root(path: str | Path, label: str) -> Path:
    value = Path(path).expanduser().absolute()
    if value.is_symlink() or not value.is_dir():
        raise LocalCoordinatorError(f"{label} must be an existing non-symlink directory")
    return value.resolve()


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _observe(path: Path, label: str, anchor_name: str) -> LocalObservation:
    files: dict[str, str] = {}
    for child in sorted(path.rglob("*")):
        if child.is_symlink():
            raise LocalCoordinatorError(f"{label} contains a symlink: {child.relative_to(path)}")
        if child.is_file():
            files[child.relative_to(path).as_posix()] = _digest(child.read_bytes())
    project_path = path / anchor_name
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalCoordinatorError(f"{label} {anchor_name} is unreadable: {exc}") from exc
    if not isinstance(project, Mapping):
        raise LocalCoordinatorError(f"{label} {anchor_name} must contain an object")
    tree_fingerprint = _digest(json.dumps(files, sort_keys=True, separators=(",", ":")).encode())
    return LocalObservation(str(path), anchor_name, files, tree_fingerprint, dict(project))


def capture_local_before(
    *, case_id: str, source_root: str | Path, target_root: str | Path,
) -> LocalBefore:
    """Capture full seed and target file fingerprints before local execution."""
    if not isinstance(case_id, str) or not case_id.strip():
        raise LocalCoordinatorError("case_id must be non-empty")
    source = _root(source_root, "source project")
    target = _root(target_root, "disposable target project")
    if source == target or source in target.parents or target in source.parents:
        raise LocalCoordinatorError("source and disposable target project roots must be disjoint")
    return LocalBefore(case_id.strip(), _observe(source, "source project", "project.json"), _observe(target, "disposable target project", "project.json"))


def capture_local_entrypoint_before(
    *, case_id: str, pinned_fixture_root: str | Path, entrypoint_root: str | Path,
) -> LocalBefore:
    """Observe the pinned offline fixture and copied case entrypoint.

    This is the L01 offline lane: ``fixture.json`` identifies the source-side
    export and ``entrypoint.json`` contains the selected read-only projection.
    It makes no Runtime head or closure claim.
    """
    if not isinstance(case_id, str) or not case_id.strip():
        raise LocalCoordinatorError("case_id must be non-empty")
    source = _root(pinned_fixture_root, "pinned fixture source")
    target = _root(entrypoint_root, "offline entrypoint")
    if source == target or source in target.parents or target in source.parents:
        raise LocalCoordinatorError("pinned fixture source and offline entrypoint roots must be disjoint")
    return LocalBefore(
        case_id.strip(),
        _observe(source, "pinned fixture source", "informational/fixture.json"),
        _observe(target, "offline entrypoint", "entrypoint.json"),
    )


def capture_local_after(before: LocalBefore) -> dict[str, Any]:
    """Read the exact local project trees again and produce bounded evidence.

    ``readback.status`` reports whether both observed trees stayed unchanged.
    Its explicit filesystem scope is not a Runtime closure readback or semantic
    task grade. ``test_target_only`` is unknown until a worker boundary can
    prove it.
    """
    source = _observe(Path(before.source.root), "source project", before.source.anchor_name)
    target = _observe(Path(before.target.root), "disposable target project", before.target.anchor_name)
    source_unchanged = source.files == before.source.files
    target_unchanged = target.files == before.target.files
    readback_status = "pass" if source_unchanged and target_unchanged else "fail"
    return {
        "kind": LOCAL_EVIDENCE_KIND,
        "case_id": before.case_id,
        "scope": "local-filesystem-observation-only",
        "before": {"source": asdict(before.source), "target": asdict(before.target)},
        "after": {"source": asdict(source), "target": asdict(target)},
        "readback": {
            "before_observed": True,
            "after_observed": True,
            "status": readback_status,
            "scope": "filesystem_tree_unchanged",
            "runtime_closure_observed": False,
            "semantic_task_grade": None,
        },
        "safety": {
            "source_unchanged": source_unchanged,
            "read_only_target": target_unchanged,
            "test_target_only": None,
        },
        "safety_scope": "the two observed roots only; no worker write boundary was enforced",
        "limitations": [
            "local project tree observation does not prove worker write confinement",
            "no Runtime head, immutable closure, or publication receipt was read",
        ],
    }


def local_evidence_unavailable(before: LocalBefore, reason: str) -> dict[str, Any]:
    """Represent failed post-run observation without filling in safety claims."""
    return {
        "kind": LOCAL_EVIDENCE_KIND,
        "case_id": before.case_id,
        "scope": "local-filesystem-observation-only",
        "before": {"source": asdict(before.source), "target": asdict(before.target)},
        "after": None,
        "readback": {
            "before_observed": True,
            "after_observed": False,
            "status": "unavailable",
            "scope": "filesystem_tree_unchanged",
            "runtime_closure_observed": False,
            "semantic_task_grade": None,
        },
        "safety": {
            "source_unchanged": None,
            "read_only_target": None,
            "test_target_only": None,
        },
        "safety_scope": "the two observed roots only; no worker write boundary was enforced",
        "limitations": [
            "local project tree observation does not prove worker write confinement",
            "no Runtime head, immutable closure, or publication receipt was read",
        ],
        "error": reason,
    }


def write_local_evidence(evidence_root: str | Path, evidence: Mapping[str, Any]) -> Path:
    """Persist local evidence using a distinct schema that Runtime admission rejects."""
    if evidence.get("kind") != LOCAL_EVIDENCE_KIND:
        raise LocalCoordinatorError("unsupported local coordinator evidence kind")
    case_id = evidence.get("case_id")
    if not isinstance(case_id, str) or not case_id.strip() or Path(case_id).name != case_id:
        raise LocalCoordinatorError("evidence case_id must be one path component")
    root = Path(evidence_root).expanduser().absolute()
    if root.is_symlink():
        raise LocalCoordinatorError("evidence root must not be a symlink")
    destination = root / "coordinator" / "cases" / case_id / "readback.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    current = root
    for part in destination.parent.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            raise LocalCoordinatorError("coordinator evidence path must not traverse a symlink")
    temporary = destination.with_name("." + destination.name + ".tmp")
    temporary.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination


__all__ = [
    "LOCAL_EVIDENCE_KIND", "LocalBefore", "LocalCoordinatorError", "LocalObservation",
    "capture_local_after", "capture_local_before", "capture_local_entrypoint_before",
    "local_evidence_unavailable", "write_local_evidence",
]
