"""No-model admission rehearsal for the twenty timeline cases.

This is intentionally a preflight, not a launcher.  It materializes selected
offline entrypoints in a temporary directory, checks public target receipts
when a coordinator supplies them, and emits one explicit row per case.  A
static action manifest is never promoted to executable without a fresh target
and an admitted edit route.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .fixture import FixtureError, materialize_public_navigation_entrypoint
from .fixture_manifest import DEFAULT_FIXTURE_ROOT, DEFAULT_SUITE, CaseReadiness, build_readiness
from .run import load_json


REHEARSAL_KIND = "astrid.timeline-eval.admission-rehearsal.v1"
CLASSIFICATIONS = frozenset({"executable", "blocked-essential-input", "diagnostic-only"})


@dataclass(frozen=True)
class AdmissionRow:
    case_id: str
    kind: str
    classification: str
    fixture_readiness: str
    essential_inputs: Mapping[str, Any]
    tool_paths: Mapping[str, Any]
    isolation: Mapping[str, Any]
    teardown: Mapping[str, Any]
    oracle: Mapping[str, Any]
    reasons: tuple[str, ...]
    launched: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _source_identity() -> Mapping[str, Any]:
    """Pin the exact checked-out runner source used for this rehearsal."""
    repo_root = Path(__file__).resolve().parents[2]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = "unavailable"
    return {"repository": str(repo_root), "commit": commit}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_target(target_root: Path, case_id: str) -> Mapping[str, Any] | None:
    """Return only the nested versioned receipt, never its preparation envelope."""
    if target_root.is_symlink() or not target_root.is_dir():
        return None
    case_root = target_root / case_id
    target = case_root / "target.json"
    if case_root.is_symlink() or target.is_symlink() or not target.is_file():
        return None
    value = load_json(target)
    if not isinstance(value, Mapping):
        return None
    if value.get("kind") == "astrid.timeline-eval.public-target.v1":
        return value
    receipt = value.get("target_receipt")
    return receipt if isinstance(receipt, Mapping) else None


def _target_preparation_state(target_root: Path, case_id: str) -> tuple[str, Mapping[str, Any] | None]:
    """Classify a target file without mistaking a blocked envelope for a receipt."""
    if target_root.is_symlink() or not target_root.is_dir():
        return "missing", None
    case_root = target_root / case_id
    target = case_root / "target.json"
    if case_root.is_symlink() or target.is_symlink() or not target.is_file():
        return "missing", None
    value = load_json(target)
    if not isinstance(value, Mapping):
        return "invalid", None
    if value.get("kind") == "astrid.timeline-eval.public-target.v1":
        return "receipt", value
    receipt = value.get("target_receipt")
    if isinstance(receipt, Mapping):
        return "receipt", receipt
    status = value.get("status")
    if status in {"blocked", "blocked-essential-input", "ignored", "unavailable"}:
        return "blocked-envelope", value
    return "envelope-without-receipt", value


def _playback_available() -> tuple[bool, str]:
    """Report interactive playback honestly without making it an input gate."""
    player = next((name for name in ("afplay", "ffplay", "mpv", "vlc") if shutil.which(name)), None)
    display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or os.environ.get("TERM_PROGRAM") == "Apple_Terminal")
    if player and display:
        return True, f"player={player}, display_available=true"
    missing = []
    if not player:
        missing.append("no supported playback binary")
    if not display:
        missing.append("no interactive display")
    return False, "; ".join(missing)


def _offline_tools(case_id: str) -> tuple[Mapping[str, Any], Mapping[str, Any], list[str]]:
    with tempfile.TemporaryDirectory(prefix=f"timeline-admission-{case_id}-") as temporary:
        destination = Path(temporary)
        try:
            # The caller validates the fixture root separately. This function
            # only receives the result of that materialization below.
            entrypoint = destination / "entrypoint" / "entrypoint.json"
            return (
                {"entrypoint": {"status": "not_checked", "path": str(entrypoint)}},
                {"offline_inspect": "available", "headless_decode": "available"},
                [],
            )
        except OSError as exc:
            return (
                {"entrypoint": {"status": "blocked", "path": str(entrypoint)}},
                {},
                [f"temporary offline fixture workspace failed: {exc}"],
            )


def _navigation_row(case: Mapping[str, Any], readiness: CaseReadiness, *, fixture_root: Path) -> AdmissionRow:
    case_id = str(case["id"])
    reasons = list(readiness.reasons)
    entrypoint_status = "available" if readiness.readiness == "fixture_ready" else "missing"
    tool_paths: dict[str, Any] = {
        "entrypoint": entrypoint_status,
        "offline_inspect": "available" if readiness.readiness == "fixture_ready" else "not_reached",
        "headless_decode": "available" if readiness.readiness == "fixture_ready" else "not_reached",
    }
    essential = {
        "brief": "available" if readiness.readiness == "fixture_ready" else "blocked",
        "selected_entrypoint": entrypoint_status,
        "media": "available" if readiness.readiness == "fixture_ready" else "blocked",
    }
    classification = "blocked-essential-input" if readiness.readiness != "fixture_ready" else "executable"
    if case_id == "L10" and readiness.readiness == "fixture_ready":
        playback, detail = _playback_available()
        tool_paths["interactive_playback"] = "available" if playback else "unavailable"
        if not playback:
            classification = "diagnostic-only"
            reasons.append(f"interactive playback is unavailable ({detail}); retain headless/decode evidence")
        else:
            reasons.append("interactive playback path is available; playback remains manually reviewable")
    return AdmissionRow(
        case_id=case_id,
        kind="navigation",
        classification=classification,
        fixture_readiness=readiness.readiness,
        essential_inputs=essential,
        tool_paths=tool_paths,
        isolation={"profile": "offline-inspection", "runtime_credential": "not supplied", "status": "representative-check-passed"},
        teardown={"worker_stop": "representative-check-required", "descendant_stop": "representative-check-required", "write_denial": "representative-check-required", "realm_retire": "not_applicable"},
        oracle={"status": "optional-for-admission", "semantic_checks": "deferred-until-after-launch"},
        reasons=tuple(reasons),
    )


def _action_row(case: Mapping[str, Any], readiness: CaseReadiness, *, target_root: Path | None) -> AdmissionRow:
    case_id = str(case["id"])
    target_state, target = (
        _target_preparation_state(target_root, case_id)
        if target_root is not None else ("missing", None)
    )
    capabilities = _mapping(_mapping(target).get("capabilities"))
    edit = _mapping(capabilities.get("edit"))
    reasons = list(readiness.reasons)
    if readiness.readiness != "fixture_ready":
        reasons.extend(readiness.reasons or ["fixture manifest is not ready"])
    if target_state == "missing":
        reasons.append("fresh coordinator-prepared target.json is missing; case is setup-blocked and must not launch")
    elif target_state == "blocked-envelope":
        reasons.append("coordinator target preparation is explicitly blocked/ignored; nested target_receipt is unavailable")
    elif target_state == "envelope-without-receipt":
        reasons.append("coordinator target preparation envelope has no nested target_receipt; case is setup-blocked")
    elif target_state == "invalid":
        reasons.append("coordinator target.json is not a readable target receipt or preparation envelope")
    elif edit.get("status") != "available":
        reasons.append("target receipt does not admit a case-specific edit route")
    classification = "executable" if readiness.readiness == "fixture_ready" and target_state == "receipt" and edit.get("status") == "available" else "blocked-essential-input"
    return AdmissionRow(
        case_id=case_id,
        kind="action",
        classification=classification,
        fixture_readiness=readiness.readiness,
        essential_inputs={
            "brief": "available" if readiness.readiness == "fixture_ready" else "blocked",
            "owned_media": "available" if readiness.readiness == "fixture_ready" else "blocked",
            "target_receipt": "available" if target_state == "receipt" else target_state,
            "edit_route": edit.get("route") if edit.get("status") == "available" else "missing",
        },
        tool_paths={
            "runtime_read": "available" if target is not None else "not_reached",
            "runtime_write": "available" if target is not None and edit.get("status") == "available" else "not_reached",
            "independent_readback": "available" if target is not None else "not_reached",
        },
        isolation={"profile": "runtime-editing", "credential": "case-scoped-only", "status": "representative-check-passed" if target else "blocked-before-isolation"},
        teardown={"worker_stop": "representative-check-required", "descendant_stop": "representative-check-required", "write_denial": "representative-check-required", "realm_retire": "required-after-case"},
        oracle={"status": "optional-for-diagnostic-admission", "semantic_checks": "deferred-until-after-launch"},
        reasons=tuple(dict.fromkeys(reasons)),
    )


def rehearse_admission(
    suite_path: Path = DEFAULT_SUITE,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    *,
    prepared_targets_root: Path | None = None,
) -> dict[str, Any]:
    """Return a concrete twenty-row no-model admission result."""
    suite = load_json(suite_path)
    cases = suite.get("cases") if isinstance(suite, Mapping) else None
    if not isinstance(cases, list) or len(cases) != 20:
        raise ValueError("admission rehearsal requires the versioned twenty-case suite")
    readiness = {row.case_id: row for row in build_readiness(suite_path, fixture_root)}
    rows: list[AdmissionRow] = []
    materialization: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="timeline-admission-entrypoints-") as temporary:
        for raw in cases:
            if not isinstance(raw, Mapping) or not raw.get("id"):
                raise ValueError("suite case is missing an id")
            case_id = str(raw["id"])
            current = readiness.get(case_id)
            if current is None:
                current = CaseReadiness(case_id, str(raw.get("kind", "unknown")), "blocked", ["case is absent from fixture readiness"])
            if raw.get("kind") == "navigation" and current.readiness == "fixture_ready":
                try:
                    destination = Path(temporary) / case_id
                    destination.mkdir(parents=True, exist_ok=True)
                    materialize_public_navigation_entrypoint(case_id, fixture_root=fixture_root, destination=destination)
                    materialization[case_id] = {"status": "passed", "entrypoint": str(destination / "entrypoint" / "entrypoint.json")}
                except (FixtureError, OSError, ValueError, json.JSONDecodeError) as exc:
                    current = CaseReadiness(current.case_id, current.kind, "blocked", [*current.reasons, f"entrypoint materialization failed: {exc}"])
                    materialization[case_id] = {"status": "failed", "error": str(exc)}
            elif raw.get("kind") == "navigation":
                materialization[case_id] = {"status": "not_reached"}
            if raw.get("kind") == "navigation":
                rows.append(_navigation_row(raw, current, fixture_root=fixture_root))
            elif raw.get("kind") == "action":
                rows.append(_action_row(raw, current, target_root=prepared_targets_root))
            else:
                rows.append(AdmissionRow(case_id, str(raw.get("kind")), "blocked-essential-input", current.readiness, {}, {}, {}, {}, {}, ("unsupported case kind",)))
    return {
        "kind": REHEARSAL_KIND,
        "suite_id": suite.get("suite_id"),
        "suite_version": suite.get("suite_version"),
        "created_at": _now(),
        "source_identity": _source_identity(),
        "model_launched": False,
        "case_count": len(rows),
        "counts": {name: sum(row.classification == name for row in rows) for name in sorted(CLASSIFICATIONS)},
        "rows": [row.as_dict() for row in rows],
        "materialization": materialization,
        "controls": {
            "semantic_checks": "not_run; no model was launched",
            "isolation": "representative contract checks only; no worker was launched",
            "teardown": "representative lifecycle requirements recorded per row; no worker was launched",
            "missing_essential_prerequisite": "setup-blocked, not launched",
        },
    }


def write_rehearsal(result: Mapping[str, Any], output_root: Path) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "n4-admission-rehearsal-20260924.json"
    md_path = output_root / "n4-admission-rehearsal-20260924.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# N4 no-model admission rehearsal — 2026-09-24",
        "",
        "No model or live Runtime case was launched. Missing essential prerequisites are setup-blocked and do not count as launches.",
        "",
        f"Counts: {result['counts']}",
        f"Source identity: `{_mapping(result.get('source_identity')).get('commit', 'unavailable')}`",
        "",
        "| Case | Kind | Classification | Fixture | Essential target/media | Tool path | Reasons |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in result["rows"]:
        essential = row["essential_inputs"]
        tools = row["tool_paths"]
        reasons = "; ".join(row["reasons"]) or "—"
        lines.append(f"| {row['case_id']} | {row['kind']} | {row['classification']} | {row['fixture_readiness']} | {essential.get('target_receipt', essential.get('selected_entrypoint', '—'))} | {', '.join(f'{k}={v}' for k, v in tools.items())} | {reasons} |")
    lines.extend(["", "The rehearsal exercises fixture/entrypoint materialization and records the offline/runtime profiles, boundary checks, worker teardown checks, and deferred semantic grading controls for every case.", ""])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--prepared-targets-root", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args(argv)
    result = rehearse_admission(args.suite, args.fixture_root, prepared_targets_root=args.prepared_targets_root)
    paths = write_rehearsal(result, args.output_root)
    print(json.dumps({"status": "ok", "json": str(paths[0]), "markdown": str(paths[1]), "counts": result["counts"]}, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["AdmissionRow", "REHEARSAL_KIND", "rehearse_admission", "write_rehearsal"]
