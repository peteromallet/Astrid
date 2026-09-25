"""Evidence-backed expected observations for selected navigation probes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class NavigationOracleError(ValueError):
    """A pinned navigation oracle input is absent, unsafe, or inconsistent."""


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise NavigationOracleError(f"expected JSON object: {path}")
    return value


def build_l07_legacy_canonical_oracle(
    *, fixture_root: Path, repo_root: Path,
) -> dict[str, Any]:
    """Independently compare the real legacy snapshot with pinned canonical rows.

    The expected observations are derived from the raw source artifact and
    pinned baseline, not copied from the fixture's comparison sidecar.
    """
    fixture_root = fixture_root.resolve()
    repo_root = repo_root.resolve()
    manifest_path = fixture_root / "informational" / "fixture.json"
    manifest = _read_object(manifest_path)
    cases = manifest.get("cases", [])
    case = next((row for row in cases if isinstance(row, Mapping) and row.get("id") == "L07"), None)
    if not isinstance(case, Mapping):
        raise NavigationOracleError("L07 informational fixture case is missing")
    requirement = next((row for row in case.get("fixture_requirements", [])
                        if isinstance(row, Mapping) and row.get("path") == "legacy_clip_type_shot_fixture"), None)
    if not isinstance(requirement, Mapping):
        raise NavigationOracleError("L07 legacy sidecar requirement is missing")
    sidecar_path = fixture_root / "informational" / "L07-legacy-compare.json"
    sidecar_bytes = sidecar_path.read_bytes()
    if "sha256:" + hashlib.sha256(sidecar_bytes).hexdigest() != requirement.get("sha256"):
        raise NavigationOracleError("L07 legacy comparison sidecar digest does not match pinned requirement")
    sidecar = json.loads(sidecar_bytes.decode("utf-8"))
    if not isinstance(sidecar, Mapping) or sidecar.get("kind") != "astrid.timeline-eval.legacy-canonical-compare.v1":
        raise NavigationOracleError("L07 legacy comparison sidecar kind is unsupported")

    legacy_meta = sidecar.get("legacy_source", {})
    legacy_relative = legacy_meta.get("artifact") if isinstance(legacy_meta, Mapping) else None
    if not isinstance(legacy_relative, str):
        raise NavigationOracleError("L07 legacy source artifact path is missing")
    legacy_path = (repo_root / legacy_relative).resolve()
    try:
        legacy_path.relative_to(repo_root)
    except ValueError as exc:
        raise NavigationOracleError("L07 legacy artifact escapes repository root") from exc
    legacy_bytes = legacy_path.read_bytes()
    legacy_digest = "sha256:" + hashlib.sha256(legacy_bytes).hexdigest()
    if legacy_digest != legacy_meta.get("artifact_sha256"):
        raise NavigationOracleError("L07 legacy source artifact digest does not match sidecar")
    legacy_root = json.loads(legacy_bytes.decode("utf-8"))
    selection = legacy_meta.get("selection")
    try:
        config_name, _, collection = str(selection).partition(".config.")
        raw_clips = legacy_root[config_name]["config"]["clips"]
    except (KeyError, TypeError) as exc:
        raise NavigationOracleError("L07 legacy source selection is absent from artifact") from exc
    if collection != "clips" or not isinstance(raw_clips, list):
        raise NavigationOracleError("L07 legacy source selection is not a clip collection")
    wanted = sidecar.get("legacy_clips")
    if not isinstance(wanted, list) or not wanted:
        raise NavigationOracleError("L07 sidecar declares no legacy clips to compare")
    actual_by_id = {row.get("id"): row for row in raw_clips if isinstance(row, Mapping)}

    source = manifest.get("source", {})
    baseline_rel = source.get("baseline") if isinstance(source, Mapping) else None
    if not isinstance(baseline_rel, str):
        raise NavigationOracleError("L07 pinned baseline path is missing")
    baseline_path = (manifest_path.parent / baseline_rel).resolve()
    try:
        baseline_path.relative_to(fixture_root.parent.resolve())
    except ValueError as exc:
        raise NavigationOracleError("L07 pinned baseline escapes eval fixture root") from exc
    baseline = _read_object(baseline_path)
    closure = baseline.get("closure", {})
    parent = closure.get("parent_revision", {}) if isinstance(closure, Mapping) else {}
    payload = parent.get("payload", {}) if isinstance(parent, Mapping) else {}
    occurrences = payload.get("occurrences", []) if isinstance(payload, Mapping) else []
    canonical_by_id = {row.get("occurrence_id"): row for row in occurrences if isinstance(row, Mapping)}

    rows: list[dict[str, Any]] = []
    for declared in wanted:
        if not isinstance(declared, Mapping):
            raise NavigationOracleError("L07 declared legacy clip is malformed")
        occurrence_id = declared.get("id")
        actual = actual_by_id.get(occurrence_id)
        if not isinstance(actual, Mapping):
            raise NavigationOracleError(f"L07 legacy clip is absent from source artifact: {occurrence_id}")
        fields = ("id", "clipType", "at", "hold", "track", "params")
        if {field: actual.get(field) for field in fields} != {field: declared.get(field) for field in fields}:
            raise NavigationOracleError(f"L07 sidecar legacy clip differs from source artifact: {occurrence_id}")
        canonical = canonical_by_id.get(occurrence_id)
        if not isinstance(canonical, Mapping):
            raise NavigationOracleError(f"L07 canonical occurrence is absent from pinned baseline: {occurrence_id}")
        legacy_start_ms = round(float(actual["at"]) * 1000)
        legacy_hold_ms = round(float(actual["hold"]) * 1000)
        start_ms = canonical.get("placement", {}).get("start_ms")
        duration_ms = canonical.get("duration_ms")
        rows.append({
            "occurrence_id": occurrence_id,
            "legacy": {field: actual.get(field) for field in fields},
            "canonical": {
                "shot_id": canonical.get("shot_id"),
                "shot_revision_id": canonical.get("shot_revision_id"),
                "placement_start_ms": start_ms,
                "duration_ms": duration_ms,
                "embedded_legacy_source": canonical.get("provenance", {}).get("legacy_source"),
            },
            "comparison": {
                "shot_identity_matches": actual.get("params", {}).get("shot_id") == canonical.get("shot_id"),
                "legacy_start_ms_rounded": legacy_start_ms,
                "start_delta_ms": legacy_start_ms - start_ms if isinstance(start_ms, int) else None,
                "legacy_hold_ms_rounded": legacy_hold_ms,
                "duration_delta_ms": legacy_hold_ms - duration_ms if isinstance(duration_ms, int) else None,
                "legacy_is_canonical_authority": False,
            },
        })
    return {
        "kind": "astrid.timeline-eval.l07-comparison-oracle.v1",
        "case_id": "L07",
        "status": "verified_from_source_bytes",
        "read_only": True,
        "legacy_artifact_sha256": legacy_digest,
        "pinned_source_head": baseline.get("source", {}).get("head"),
        "pinned_closure_digest": baseline.get("closure_digest"),
        "rows": rows,
        "scope_note": "Legacy clip values are compared with the separately pinned canonical closure; numeric deltas are reported, not normalized into equivalence.",
    }
