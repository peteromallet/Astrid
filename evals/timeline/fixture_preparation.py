"""One coordinator-owned, parameterized preparation/readiness seam.

This module only materializes inputs that already exist in the pinned fixture
or in an explicit coordinator target root.  It never fabricates media,
targets, expected answers, or a ``ready`` status from a static suite row.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .fixture import FixtureError, materialize_public_navigation_entrypoint
from .fixture_manifest import CaseReadiness, build_readiness


PREPARATION_KIND = "astrid.timeline-eval.fixture-preparation.v1"


@dataclass(frozen=True)
class PreparationRow:
    case_id: str
    kind: str
    status: str
    input: str
    target: str
    initial_condition: str
    available_tools: tuple[str, ...]
    blockers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "kind": self.kind,
            "status": self.status,
            "input": self.input,
            "target": self.target,
            "initial_condition": self.initial_condition,
            "available_tools": list(self.available_tools),
            "blockers": list(self.blockers),
        }


def _case_by_id(suite_path: Path) -> dict[str, Mapping[str, Any]]:
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    return {str(row["id"]): row for row in suite.get("cases", []) if isinstance(row, Mapping) and row.get("id")}


def _row(case: Mapping[str, Any], readiness: CaseReadiness, prepared_targets_root: Path | None) -> PreparationRow:
    case_id = str(case["id"])
    kind = str(case.get("kind", "unknown"))
    target_path: Path | None = None
    if kind == "navigation":
        aliases = ", ".join(str(value) for value in case.get("targets", ())) or "none"
        target = f"offline entrypoint targets: {aliases}"
        tools = ["selected-case entrypoint", "public SDK/CLI", "coordinator readback"]
        if case_id == "L10":
            tools.append(
                "afplay available" if shutil.which("afplay")
                else "afplay unavailable; headless decode only"
            )
        input_name = "informational/fixture.json plus selected pinned media"
    else:
        target_path = prepared_targets_root / case_id / "target.json" if prepared_targets_root else None
        target = str(target_path) if target_path else "coordinator target receipt (not supplied)"
        tools = ["public case-specific edit route", "coordinator before/after readback"]
        input_name = "action/manifest.json plus case-owned media sidecars"
    preconditions = case.get("preconditions", ())
    initial = "; ".join(str(value) for value in preconditions) if isinstance(preconditions, list) else str(preconditions)
    blockers = list(readiness.reasons)
    if kind == "action":
        target_ready = False
        if target_path is not None and target_path.is_file() and not target_path.is_symlink():
            try:
                target_value = json.loads(target_path.read_text(encoding="utf-8"))
                edit = target_value.get("capabilities", {}).get("edit", {}) if isinstance(target_value, Mapping) else {}
                target_ready = isinstance(edit, Mapping) and edit.get("status") == "available"
            except (OSError, ValueError, json.JSONDecodeError):
                target_ready = False
        if not target_ready:
            blockers.append("no coordinator-prepared target receipt with an available edit route")
    blockers_tuple = tuple(dict.fromkeys(blockers))
    status = "executable" if readiness.readiness == "fixture_ready" and not blockers_tuple else "blocked-essential-input"
    return PreparationRow(case_id, kind, status, input_name, target, initial, tuple(tools), blockers_tuple)


def build_preparation_table(
    suite_path: Path,
    fixture_root: Path,
    *,
    prepared_targets_root: Path | None = None,
) -> list[PreparationRow]:
    """Build the honest 20-row preparation table from current evidence."""
    suite = _case_by_id(suite_path)
    readiness = {row.case_id: row for row in build_readiness(suite_path, fixture_root)}
    return [_row(suite[case_id], readiness[case_id], prepared_targets_root)
            for case_id in suite if case_id in readiness]


def prepare_public_case(
    case: Mapping[str, Any], *, fixture_root: Path, destination: Path,
    prepared_targets_root: Path | None = None,
) -> dict[str, Any]:
    """Materialize one selected-case public envelope, never a synthetic target."""
    case_id = str(case.get("id", ""))
    if not case_id:
        raise FixtureError("selected case has no id")
    destination = destination.expanduser().absolute()
    if destination.exists() and (destination.is_symlink() or not destination.is_dir()):
        raise FixtureError(f"selected case destination is unsafe: {destination}")
    destination.mkdir(parents=True, exist_ok=True)
    if case.get("kind") == "navigation":
        entrypoint = materialize_public_navigation_entrypoint(
            case_id, fixture_root=fixture_root, destination=destination,
        )
        return {"kind": PREPARATION_KIND, "case_id": case_id, "status": "prepared",
                "entrypoint": entrypoint}
    if prepared_targets_root is None:
        return {"kind": PREPARATION_KIND, "case_id": case_id,
                "status": "blocked-essential-input",
                "reason": "prepared target root is missing; no real action target was fabricated"}
    root = prepared_targets_root.expanduser().absolute()
    source = root / case_id / "target.json"
    if root.is_symlink() or not root.is_dir() or source.is_symlink() or not source.is_file():
        return {"kind": PREPARATION_KIND, "case_id": case_id,
                "status": "blocked-essential-input",
                "reason": f"prepared public target is missing or unsafe: {source}"}
    value = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise FixtureError(f"prepared public target must be an object: {source}")
    (destination / "target.json").write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {"kind": PREPARATION_KIND, "case_id": case_id, "status": "prepared",
            "target": dict(value)}


def write_preparation_table(rows: list[PreparationRow], path: Path) -> Path:
    """Write a compact human/machine table without private answer material."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Timeline fixture preparation table", "",
        "| Case | Kind | Status | Input | Target | Initial condition | Available tools | Blockers |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        values = [row.case_id, row.kind, row.status, row.input, row.target,
                  row.initial_condition, ", ".join(row.available_tools), "; ".join(row.blockers) or "—"]
        lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in values) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


__all__ = ["PREPARATION_KIND", "PreparationRow", "build_preparation_table",
           "prepare_public_case", "write_preparation_table"]
