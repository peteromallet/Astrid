"""One coordinator-owned, parameterized preparation/readiness seam.

This module only materializes inputs that already exist in the pinned fixture
or in an explicit coordinator target root.  It never fabricates media,
targets, expected answers, or a ``ready`` status from a static suite row.
"""

from __future__ import annotations

import json
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .fixture import FixtureError, materialize_public_navigation_entrypoint
from .fixture_contracts import action_target_contract, validate_action_target_receipt
from .fixture_manifest import CaseReadiness, build_readiness


PREPARATION_KIND = "astrid.timeline-eval.fixture-preparation.v1"
ACTION_PREPARATION_KIND = "astrid.timeline-eval.action-target-preparation.v1"

# These are the only extra, case-specific files currently pinned in the public
# action fixture.  A sidecar is useful input evidence, but it is not a target
# receipt and never makes an action case executable by itself.
_ACTION_SIDECARS: dict[str, tuple[str, ...]] = {
    "A05": ("action/A05-vo-endpoints.json",),
    "A06": ("action/A06-text-roles.json",),
    "A09": ("action/A09-images.json",),
    "A10": ("action/A10-brightness-collection.json",),
}


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


def _action_inputs(case_id: str, fixture_root: Path) -> str:
    """Return pinned paths, keeping absent prerequisites visible."""
    paths = ["action/manifest.json"]
    paths.extend(_ACTION_SIDECARS.get(case_id, ()))
    existing = [path for path in paths if (fixture_root / path).is_file()]
    missing = [path for path in paths if path not in existing]
    description = "; ".join(existing) if existing else "action/manifest.json (missing)"
    if missing:
        description += "; missing: " + ", ".join(missing)
    return description


def _row(
    case: Mapping[str, Any], readiness: CaseReadiness,
    prepared_targets_root: Path | None, fixture_root: Path,
) -> PreparationRow:
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
        input_name = _action_inputs(case_id, fixture_root)
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
            contract = action_target_contract(case)
            blockers.append(
                contract.reason
                or "no coordinator-prepared target receipt with an available edit route"
            )
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
    return [_row(suite[case_id], readiness[case_id], prepared_targets_root, fixture_root)
            for case_id in suite if case_id in readiness]


def _target_source(source_root: Path, case_id: str) -> Path:
    """Resolve the two supported coordinator receipt layouts."""
    # A coordinator evidence directory for one case commonly contains the
    # receipt directly.  Keep this form explicit so callers cannot accidentally
    # walk arbitrary descendants looking for a convenient JSON file.
    direct_root = source_root / "target.json"
    if direct_root.is_file() or direct_root.is_symlink():
        return direct_root
    direct = source_root / case_id / "target.json"
    if direct.is_file() or direct.is_symlink():
        return direct
    nested = source_root / "cases" / case_id / "target.json"
    return nested


def _json_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def materialize_action_target_receipts(
    *, source_root: Path, destination_root: Path,
    case_ids: tuple[str, ...] = tuple(f"A{index:02d}" for index in range(1, 11)),
) -> dict[str, dict[str, Any]]:
    """Copy only real coordinator receipts into a disposable prepared root.

    ``source_root`` must contain receipts produced by an actual disposable
    Runtime preparation (either ``A01/target.json`` or ``cases/A01/target.json``).
    This seam deliberately does not synthesize an action target from a static
    manifest or media sidecar.  A missing route/receipt remains blocked.
    """
    source_root = source_root.expanduser().absolute()
    destination_root = destination_root.expanduser().absolute()
    if source_root.is_symlink() or not source_root.is_dir():
        raise FixtureError(f"action receipt source root is missing or unsafe: {source_root}")
    if destination_root.exists() and destination_root.is_symlink():
        raise FixtureError(f"action receipt destination root is unsafe: {destination_root}")
    destination_root.mkdir(parents=True, exist_ok=True)

    rows: dict[str, dict[str, Any]] = {}
    for case_id in case_ids:
        source = _target_source(source_root, case_id)
        row: dict[str, Any] = {
            "kind": ACTION_PREPARATION_KIND,
            "case_id": case_id,
            "status": "blocked-essential-input",
            "source": str(source),
            "destination": str(destination_root / case_id / "target.json"),
        }
        if source.is_symlink() or not source.is_file():
            row["reason"] = "no coordinator-produced disposable target receipt"
            rows[case_id] = row
            continue
        try:
            raw = source.read_bytes()
            value = json.loads(raw.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            row["reason"] = f"target receipt is unreadable: {exc}"
            rows[case_id] = row
            continue
        if not isinstance(value, Mapping):
            row["reason"] = "target receipt is not a JSON object"
            rows[case_id] = row
            continue
        errors = validate_action_target_receipt(value, action_target_contract({"id": case_id}))
        if errors:
            row["reason"] = "; ".join(errors)
            rows[case_id] = row
            continue
        owned = value.get("owned_media_ids")
        if not isinstance(owned, list) or not owned or any(not isinstance(item, str) or not item for item in owned):
            row["reason"] = "target receipt does not prove destination-owned media"
            rows[case_id] = row
            continue
        target_dir = destination_root / case_id
        if target_dir.exists() and target_dir.is_symlink():
            row["reason"] = "target destination directory is a symlink"
            rows[case_id] = row
            continue
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / "target.json"
        rendered = json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
        if destination.exists() and destination.read_text(encoding="utf-8") != rendered:
            raise FixtureError(f"refusing to overwrite a different prepared receipt: {destination}")
        destination.write_text(rendered, encoding="utf-8")
        row.update({
            "status": "prepared",
            "sha256": _json_sha256(rendered.encode("utf-8")),
            "owned_media_count": len(owned),
            "project_id": value.get("project_id"),
            "timeline_id": value.get("timeline_id"),
            "edit_route": value.get("capabilities", {}).get("edit", {}).get("route"),
        })
        rows[case_id] = row

    manifest = {
        "kind": ACTION_PREPARATION_KIND,
        "owner": "coordinator",
        "source_root": str(source_root),
        "destination_root": str(destination_root),
        "cases": rows,
    }
    (destination_root / "preparation.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return rows


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
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"kind": PREPARATION_KIND, "case_id": case_id,
                "status": "blocked-essential-input",
                "reason": f"prepared public target is unreadable: {exc}"}
    if not isinstance(value, Mapping):
        raise FixtureError(f"prepared public target must be an object: {source}")
    errors = validate_action_target_receipt(value, action_target_contract(case))
    if errors:
        return {"kind": PREPARATION_KIND, "case_id": case_id,
                "status": "blocked-essential-input", "reason": "; ".join(errors)}
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


__all__ = ["ACTION_PREPARATION_KIND", "PREPARATION_KIND", "PreparationRow",
           "build_preparation_table", "materialize_action_target_receipts",
           "prepare_public_case", "write_preparation_table"]
