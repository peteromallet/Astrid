"""Validate the informational/action fixture manifests and render readiness.

This is deliberately a small contract checker, not another eval runner. It
checks whether each case has concrete fixture inputs before an agent run.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SUITE = REPO_ROOT / "Astrid/evals/timeline/suite.json"
DEFAULT_FIXTURE_ROOT = (
    REPO_ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"
)
DEFAULT_REPORT_ROOT = DEFAULT_FIXTURE_ROOT
PLACEHOLDER = re.compile(r"(?:\{[^}]+\}|TODO|TBD|UNRESOLVED|PLACEHOLDER)", re.I)


@dataclass
class CaseReadiness:
    case_id: str
    kind: str
    readiness: str
    reasons: list[str] = field(default_factory=list)
    manifest: str | None = None


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _is_explicit(value: Any) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return False
    if isinstance(value, str):
        return not PLACEHOLDER.search(value)
    if isinstance(value, dict):
        # Object records commonly include empty optional fields. Treat an
        # object as explicit when it contains at least one concrete value and
        # none of its populated string values are unresolved placeholders.
        populated = [item for item in value.values() if item not in (None, "", [], {})]
        return bool(populated) and all(
            not (isinstance(item, str) and PLACEHOLDER.search(item))
            and (not isinstance(item, (dict, list)) or _is_explicit(item))
            for item in populated
        )
    if isinstance(value, list):
        return bool(value) and all(_is_explicit(item) for item in value)
    return True


def _has_explicit_units(case: dict[str, Any]) -> bool:
    return _is_explicit(case.get("units")) or _is_explicit(
        (case.get("timing") or {}).get("unit")
    )


def _targets_are_explicit(case: dict[str, Any], target_catalog: dict[str, Any]) -> bool:
    targets = case.get("targets")
    if not _is_explicit(targets):
        return False
    if isinstance(targets, list):
        for target in targets:
            if isinstance(target, str) and target in target_catalog:
                resolved = target_catalog[target]
                if not _is_explicit(resolved):
                    return False
                if not any(
                    key in resolved
                    for key in ("occurrence_id", "shot_id", "shot_revision_id", "internal_timeline_revision_id", "revision_id", "element_id", "id")
                ):
                    return False
            elif isinstance(target, str):
                # A symbolic alias is useful only when its identity is
                # resolved by the manifest-level target table.
                return False
    return True


def _media_is_explicit(case: dict[str, Any], kind: str, target_catalog: dict[str, Any]) -> bool:
    # Information cases may explicitly state that media is not needed; action
    # cases need an explicit list, even when the list is empty.
    key = "media_handles" if kind == "navigation" else "media"
    if key not in case:
        return False
    media = case[key]
    if media == []:
        return kind == "navigation" or case.get("media_requirement") == "none"
    if not _is_explicit(media):
        return False
    if kind == "navigation":
        for handle in media:
            if isinstance(handle, str) and ".media_handle" in handle:
                alias = handle.split(".media_handles", 1)[0]
                alias = handle.split(".media_handle", 1)[0]
                target = target_catalog.get(alias)
                if not isinstance(target, dict):
                    return False
                if ".media_handles" in handle:
                    target_media = target.get("media_handles")
                    if not isinstance(target_media, list) or not target_media:
                        return False
                    if "[" in handle and not any(
                        isinstance(item, dict)
                        and item.get("role") == handle.partition("[")[2].rstrip("]")
                        and _is_explicit(item)
                        for item in target_media
                    ):
                        return False
                elif not _is_explicit(target.get("media_handle")):
                    return False
            elif isinstance(handle, str) and handle not in target_catalog and not handle.startswith("media/"):
                return False
    return True


def validate_case(
    case: dict[str, Any],
    kind: str,
    manifest_path: Path,
    target_catalog: dict[str, Any] | None = None,
) -> CaseReadiness:
    case_id = str(case.get("id", "<missing-id>"))
    reasons: list[str] = []
    target_catalog = target_catalog or {}
    if not _targets_are_explicit(case, target_catalog):
        reasons.append("target identities are missing or unresolved")
    if not _media_is_explicit(case, kind, target_catalog):
        reasons.append("media handles/requirements are missing or unresolved")
    if not _has_explicit_units(case):
        reasons.append("units are missing or implicit")
    if not _is_explicit(case.get("lifecycle")):
        reasons.append("lifecycle/reset state is missing or unresolved")
    if case.get("blockers"):
        reasons.extend(str(item) for item in case["blockers"] if str(item))

    declared = str(case.get("status", "")).lower()
    if declared in {"blocked", "not_ready", "missing"}:
        reasons.append(f"fixture declares status={declared}")
    elif declared in {"partial", "partially_ready"} and not reasons:
        reasons.append("fixture declares partial readiness")

    if reasons:
        readiness = "blocked" if any(
            token in " ".join(reasons).lower()
            for token in ("missing", "unresolved", "not supplied", "unavailable", "absent")
        ) else "partial"
    else:
        readiness = "ready"
    return CaseReadiness(case_id, kind, readiness, reasons, str(manifest_path))


def build_readiness(
    suite_path: Path = DEFAULT_SUITE,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> list[CaseReadiness]:
    suite = _read_json(suite_path)
    by_id = {str(case["id"]): case for case in suite.get("cases", [])}
    manifests = {
        "navigation": fixture_root / "informational" / "fixture.json",
        "action": fixture_root / "action" / "manifest.json",
    }
    result: dict[str, CaseReadiness] = {}
    for kind, path in manifests.items():
        expected = [case_id for case_id, case in by_id.items() if case.get("kind") == kind]
        if not path.exists():
            for case_id in expected:
                result[case_id] = CaseReadiness(
                    case_id, kind, "blocked", ["fixture manifest has not been written"], str(path)
                )
            continue
        manifest = _read_json(path)
        rows = manifest.get("cases")
        if not isinstance(rows, list):
            raise ValueError(f"{path}: cases must be an array")
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            case_id = str(row.get("id", "<missing-id>"))
            if case_id in seen:
                result[case_id] = CaseReadiness(
                    case_id, kind, "blocked", ["duplicate case entry in fixture manifest"], str(path)
                )
                continue
            seen.add(case_id)
            target_catalog = manifest.get("targets", {})
            if not isinstance(target_catalog, dict):
                target_catalog = {}
            result[case_id] = validate_case(row, kind, path, target_catalog)
        for case_id in expected:
            if case_id not in seen:
                result[case_id] = CaseReadiness(
                    case_id, kind, "blocked", ["case entry is missing from fixture manifest"], str(path)
                )
        for case_id in seen - set(expected):
            result[case_id] = CaseReadiness(
                case_id, kind, "blocked", ["case ID is not in the versioned 20-case suite"], str(path)
            )
    return [result[key] for key in by_id if key in result]


def write_reports(rows: list[CaseReadiness], report_root: Path = DEFAULT_REPORT_ROOT) -> tuple[Path, Path]:
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / "readiness.json"
    markdown_path = report_root / "readiness.md"
    payload = {
        "kind": "astrid.timeline-eval.fixture-readiness.v1",
        "suite": "astrid-timeline-navigation-and-actions",
        "counts": {status: sum(row.readiness == status for row in rows) for status in ("ready", "partial", "blocked")},
        "cases": [row.__dict__ for row in rows],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Timeline evaluation fixture readiness",
        "",
        "Generated by `Astrid/evals/timeline/fixture_manifest.py`. Readiness is based on concrete manifest fields, not case IDs.",
        "",
        "| Case | Kind | Readiness | Missing or blocking details |",
        "|---|---|---|---|",
    ]
    for row in rows:
        details = "; ".join(row.reasons).replace("|", "\\|") or "All required fixture fields are explicit."
        lines.append(f"| {row.case_id} | {row.kind} | {row.readiness} | {details} |")
    lines.extend(["", f"Counts: {payload['counts']}.", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    args = parser.parse_args()
    rows = build_readiness(args.suite, args.fixture_root)
    json_path, markdown_path = write_reports(rows, args.report_root)
    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    print(" ".join(f"{status}={sum(row.readiness == status for row in rows)}" for status in ("ready", "partial", "blocked")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
