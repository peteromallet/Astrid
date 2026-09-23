"""Validate the informational/action fixture manifests and render readiness.

This is deliberately a small contract checker, not another eval runner. It
checks whether each case has concrete fixture inputs before an agent run.
"""

from __future__ import annotations

import argparse
import hashlib
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
    operational_ready: bool = False
    operational_reasons: list[str] = field(default_factory=list)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _canonical_digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _file_digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def _resolve_file(manifest_path: Path, relative: Any, eval_root: Path) -> Path | None:
    if not isinstance(relative, str) or not relative:
        return None
    path = (manifest_path.parent / relative).resolve()
    try:
        path.relative_to(eval_root.resolve())
    except ValueError:
        return None
    return path


def _verify_baseline(
    baseline_path: Path | None,
    *,
    expected: dict[str, Any],
    eval_root: Path,
) -> tuple[dict[str, Any] | None, list[str], set[str]]:
    reasons: list[str] = []
    verified_media: set[str] = set()
    if baseline_path is None or not baseline_path.is_file():
        return None, ["pinned baseline file is missing or outside the eval evidence root"], verified_media
    try:
        baseline = _read_json(baseline_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, [f"pinned baseline is unreadable: {exc}"], verified_media
    required = {"schema_version", "source", "closure", "closure_digest", "semantic_digest", "source_hashes", "media", "frame_rate"}
    missing = sorted(required - set(baseline))
    if missing:
        reasons.append("baseline schema missing fields: " + ", ".join(missing))
    source = baseline.get("source", {})
    for manifest_key, baseline_key in (
        ("source_project_id", "project_id"),
        ("source_timeline_id", "timeline_id"),
        ("source_parent_revision_id", "head"),
        ("source_closure_digest", "closure_digest"),
        ("source_semantic_digest", "semantic_digest"),
    ):
        value = expected.get(manifest_key)
        if value is not None and value != (baseline.get("closure_digest") if baseline_key == "closure_digest" else baseline.get("semantic_digest") if baseline_key == "semantic_digest" else source.get(baseline_key)):
            reasons.append(f"baseline {baseline_key} does not match fixture manifest")
    closure = baseline.get("closure")
    if not isinstance(closure, dict):
        reasons.append("baseline closure is not an object")
        closure = {}
    else:
        digest = _canonical_digest(closure)
        if digest != baseline.get("closure_digest"):
            reasons.append("baseline closure digest does not match closure bytes")
        parent = closure.get("parent_revision", {})
        source_head = source.get("head")
        if not isinstance(parent, dict) or parent.get("revision_id") != source_head:
            reasons.append("pinned parent revision ID does not match baseline source head")
        semantic = {
            "parent": parent.get("payload") if isinstance(parent, dict) else None,
            "shots": [row.get("payload") for row in closure.get("shot_revisions", []) if isinstance(row, dict)],
            "internal_timelines": [row.get("payload") for row in closure.get("internal_timeline_revisions", []) if isinstance(row, dict)],
        }
        if _canonical_digest(semantic) != baseline.get("semantic_digest"):
            reasons.append("baseline semantic digest does not match pinned closure payloads")
        hashes = baseline.get("source_hashes", {})
        expected_rows = [("parent", parent)]
        expected_rows += [("shot", row) for row in closure.get("shot_revisions", []) if isinstance(row, dict)]
        expected_rows += [("internal", row) for row in closure.get("internal_timeline_revisions", []) if isinstance(row, dict)]
        for prefix, row in expected_rows:
            revision_id = row.get("revision_id") if isinstance(row, dict) else None
            key = f"{prefix}:{revision_id}"
            if not revision_id or hashes.get(key) != _canonical_digest(row):
                reasons.append(f"source record hash is missing or invalid: {key}")

    media_root_value = expected.get("media_root")
    media_root = _resolve_file(baseline_path.parent / "placeholder", media_root_value, eval_root) if media_root_value else baseline_path.parent
    # Resolve media_root relative to the manifest, when the caller has supplied
    # it. Otherwise the baseline's containing directory is the defined root.
    if isinstance(media_root_value, str):
        source_manifest_path = expected.get("_manifest_path")
        if isinstance(source_manifest_path, Path):
            media_root = _resolve_file(source_manifest_path, media_root_value, eval_root)
    if media_root is None:
        reasons.append("media root is missing or escapes eval evidence root")
    for row in baseline.get("media", []) if isinstance(baseline.get("media"), list) else []:
        if not isinstance(row, dict):
            reasons.append("baseline media record is malformed")
            continue
        digest = str(row.get("digest", ""))
        handle = row.get("source_handle")
        path = (media_root / Path(str(handle))) if media_root and isinstance(handle, str) else None
        if not digest.startswith("sha256:") or path is None or not path.is_file():
            reasons.append(f"media bytes missing for {digest or '<missing digest>'}")
            continue
        if _file_digest(path) != digest:
            reasons.append(f"media byte digest mismatch for {digest}")
            continue
        verified_media.add(digest)
    return baseline, reasons, verified_media


def _extract_known_ids(baseline: dict[str, Any] | None) -> dict[str, set[str]]:
    result = {key: set() for key in ("occurrence", "shot", "shot_revision", "internal_revision", "clip", "timeline", "media")}
    if not baseline:
        return result
    closure = baseline.get("closure", {})
    parent = closure.get("parent_revision", {}) if isinstance(closure, dict) else {}
    payload = parent.get("payload", {}) if isinstance(parent, dict) else {}
    result["timeline"].add(str(parent.get("timeline_id", "")))
    result["timeline"].add(str(baseline.get("source", {}).get("timeline_id", "")))
    for row in payload.get("occurrences", []) if isinstance(payload.get("occurrences"), list) else []:
        if isinstance(row, dict):
            result["occurrence"].add(str(row.get("occurrence_id", "")))
            result["shot"].add(str(row.get("shot_id", "")))
            result["shot_revision"].add(str(row.get("shot_revision_id", "")))
    for row in closure.get("shot_revisions", []) if isinstance(closure.get("shot_revisions"), list) else []:
        if isinstance(row, dict):
            result["shot"].add(str(row.get("shot_id", "")))
            result["shot_revision"].add(str(row.get("revision_id", "")))
            result["internal_revision"].add(str(row.get("internal_timeline_revision_id", "")))
    internal_by_id = {}
    for row in closure.get("internal_timeline_revisions", []) if isinstance(closure.get("internal_timeline_revisions"), list) else []:
        if isinstance(row, dict):
            result["internal_revision"].add(str(row.get("revision_id", "")))
            internal_by_id[str(row.get("revision_id", ""))] = row
    def add_clips(value: Any) -> None:
        if isinstance(value, dict):
            clip_id = value.get("id") or value.get("clip_id")
            if clip_id:
                result["clip"].add(str(clip_id))
            for child in value.values():
                add_clips(child)
        elif isinstance(value, list):
            for child in value:
                add_clips(child)
    add_clips(payload)
    for row in closure.get("shot_revisions", []) if isinstance(closure.get("shot_revisions"), list) else []:
        if isinstance(row, dict):
            add_clips(row.get("payload", {}))
    for row in internal_by_id.values():
        add_clips(row.get("payload", {}))
    result["media"] = {str(row.get("digest")) for row in baseline.get("media", []) if isinstance(row, dict)}
    result["parent_revision"] = {str(parent.get("revision_id", ""))}  # type: ignore[assignment]
    return {key: values - {"", "None"} for key, values in result.items()}


def _verify_media_entry(path: Path, expected_sha: Any) -> str | None:
    if not path.is_file():
        return "missing bytes"
    digest = str(expected_sha or "")
    if digest.startswith("sha256:"):
        digest = digest.removeprefix("sha256:")
    if len(digest) != 64 or _file_digest(path) != "sha256:" + digest:
        return "byte digest mismatch"
    return None


def _verify_asset_collection(action_root: Path, name: str, count: int, base_media: set[str]) -> list[str]:
    reasons: list[str] = []
    manifest_path = action_root / name
    if not manifest_path.is_file():
        return [f"required sidecar is missing: {name}"]
    try:
        collection = _read_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [f"invalid sidecar {name}: {exc}"]
    images = collection.get("images")
    if not isinstance(images, list) or len(images) != count:
        return [f"{name} must contain exactly {count} image records"]
    seen: set[str] = set()
    sort_keys = []
    for index, row in enumerate(images):
        if not isinstance(row, dict):
            reasons.append(f"{name} image record {index} is malformed")
            continue
        path = _resolve_file(manifest_path, row.get("path"), action_root.parent.parent.parent)
        if path is None:
            reasons.append(f"{name} image path escapes the fixture tree at index {index}")
            continue
        problem = _verify_media_entry(path, row.get("sha256"))
        if problem:
            reasons.append(f"{name} image {index}: {problem}")
        digest = str(row.get("sha256", "")).removeprefix("sha256:")
        media_id = str(row.get("media_id", ""))
        if media_id != "sha256:" + digest:
            reasons.append(f"{name} image {index} media_id does not match sha256")
        if media_id in seen:
            reasons.append(f"{name} contains duplicate media_id {media_id}")
        seen.add(media_id)
        if name == "A10-brightness-collection.json":
            value = row.get("brightness_mean_srgb_luma")
            if not isinstance(value, (int, float)):
                reasons.append(f"{name} image {index} has no numeric brightness score")
            else:
                sort_keys.append((float(value), media_id))
        source_id = row.get("source_media_id") or row.get("derived_from")
        if source_id is not None and source_id not in base_media:
            reasons.append(f"{name} image {index} source media is not in the pinned closure")
    if len(seen) != count:
        reasons.append(f"{name} does not contain {count} distinct media IDs")
    if sort_keys and sort_keys != sorted(sort_keys):
        reasons.append("A10 brightness collection is not sorted by brightness then media_id")
    return reasons


def _manifest_context(path: Path, kind: str, eval_root: Path) -> tuple[dict[str, Any] | None, set[str], list[str]]:
    """Validate schema and exact pinned closure/media bytes shared by a group."""
    problems: list[str] = []
    try:
        manifest = _read_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, set(), [f"fixture manifest is unreadable: {exc}"]
    if kind == "navigation":
        if manifest.get("kind") != "astrid.timeline-eval.informational-fixture.v1":
            problems.append("informational fixture schema kind is missing or unsupported")
        source = manifest.get("source", {})
        baseline_path = _resolve_file(path, source.get("baseline"), eval_root)
        expected = {
            "source_project_id": source.get("project_id"),
            "source_timeline_id": source.get("timeline_id"),
            "source_parent_revision_id": source.get("head"),
            "source_closure_digest": source.get("closure_digest"),
            "source_semantic_digest": source.get("semantic_digest"),
            "media_root": source.get("media_root"),
            "_manifest_path": path,
        }
    else:
        if manifest.get("schema_version") != "astrid.timeline.action-fixtures.v1":
            problems.append("action fixture schema_version is missing or unsupported")
        if manifest.get("suite_id") != "astrid-timeline-navigation-and-actions":
            problems.append("action fixture suite_id does not match the versioned suite")
        base = manifest.get("base", {})
        baseline_path = _resolve_file(path, base.get("baseline_path"), eval_root)
        expected = {
            "source_project_id": base.get("source_project_id"),
            "source_timeline_id": base.get("source_timeline_id"),
            "source_parent_revision_id": base.get("source_parent_revision_id"),
            "source_closure_digest": base.get("source_closure_digest"),
            "source_semantic_digest": base.get("source_semantic_digest"),
            "_manifest_path": path,
        }
    baseline, baseline_problems, verified_media = _verify_baseline(
        baseline_path, expected=expected, eval_root=eval_root
    )
    problems.extend(baseline_problems)
    if baseline is not None:
        if kind == "action":
            base = manifest.get("base", {})
            if base.get("frame_rate") != baseline.get("frame_rate"):
                problems.append("action fixture frame_rate does not match baseline")
            action_root = path.parent
            problems.extend(_verify_asset_collection(action_root, "A09-images.json", 4, verified_media))
            problems.extend(_verify_asset_collection(action_root, "A10-brightness-collection.json", 200, verified_media))
            for sidecar in ("A05-vo-endpoints.json", "A06-text-roles.json", "audio-fixtures.json"):
                sidecar_path = action_root / sidecar
                if not sidecar_path.is_file():
                    problems.append(f"required action sidecar is missing: {sidecar}")
                    continue
                try:
                    side = _read_json(sidecar_path)
                except (OSError, ValueError, json.JSONDecodeError) as exc:
                    problems.append(f"invalid sidecar {sidecar}: {exc}")
                    continue
                if sidecar == "A05-vo-endpoints.json":
                    occurrences = side.get("occurrences", [])
                    parent_occurrences = baseline.get("closure", {}).get("parent_revision", {}).get("payload", {}).get("occurrences", [])
                    if len(occurrences) != len(parent_occurrences) or side.get("source_parent_revision_id") != baseline.get("source", {}).get("head"):
                        problems.append("A05 endpoint table does not cover the pinned parent occurrences/head")
                elif sidecar == "A06-text-roles.json":
                    roles = {entry.get("role") for entry in side.get("bindings", []) if isinstance(entry, dict)}
                    if not {"visible_title", "authored_script", "transcript", "voiceover"} <= roles:
                        problems.append("A06 text-role sidecar does not separate title/script/transcript/voice roles")
                elif sidecar == "audio-fixtures.json":
                    for entry in side.get("assets", []):
                        asset_path = _resolve_file(sidecar_path, entry.get("path"), eval_root)
                        if asset_path is None or _verify_media_entry(asset_path, entry.get("sha256")):
                            problems.append("audio fixture bytes are missing or fail their declared digest")
        else:
            targets = manifest.get("targets", {})
            ids = _extract_known_ids(baseline)
            problems.extend(_validate_target_catalog(targets, ids, verified_media))
    return manifest, verified_media, problems


def _validate_target_catalog(targets: Any, ids: dict[str, set[str]], media: set[str]) -> list[str]:
    if not isinstance(targets, dict):
        return ["target catalog is not an object"]
    reasons: list[str] = []
    key_groups = {
        "occurrence_id": "occurrence", "shot_id": "shot", "shot_revision_id": "shot_revision",
        "internal_timeline_revision_id": "internal_revision", "revision_id": "parent_revision",
        "timeline_id": "timeline", "clip_id": "clip", "element_id": "clip",
    }
    def walk(alias: str, value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in key_groups and isinstance(child, str) and child not in ids.get(key_groups[key], set()):
                    reasons.append(f"target {alias}.{key} does not resolve in pinned closure")
                if key in {"media_id", "digest", "source_object_id"} and isinstance(child, str) and child.startswith("sha256:") and child not in media:
                    reasons.append(f"target {alias}.{key} has no verified media bytes")
                walk(alias, child)
        elif isinstance(value, list):
            for child in value:
                walk(alias, child)
    for alias, record in targets.items():
        walk(str(alias), record)
    return reasons


def _validate_action_case(case: dict[str, Any], ids: dict[str, set[str]], media: set[str], action_root: Path) -> list[str]:
    reasons: list[str] = []
    if str(case.get("status", "")).lower() != "ready":
        reasons.append(f"case manifest status is {case.get('status', 'missing')!r}")
    if case.get("blockers"):
        reasons.extend(str(item) for item in case["blockers"] if str(item))
    targets = case.get("targets", {})
    if not isinstance(targets, dict):
        reasons.append("case targets must be an object")
        targets = {}
    for key, value in targets.items():
        if key.endswith("_occurrence") and isinstance(value, str) and value not in ids["occurrence"]:
            reasons.append(f"target {key} does not resolve to a pinned occurrence")
        elif key.endswith("_shot_id") and isinstance(value, str) and value not in ids["shot"]:
            reasons.append(f"target {key} does not resolve to a pinned shot")
        elif key.endswith("_clip_id") and isinstance(value, str) and value not in ids["clip"]:
            reasons.append(f"target {key} does not resolve to a pinned clip")
        elif key == "four_occurrences_in_order" and isinstance(value, list):
            if len(value) != 4 or any(item not in ids["occurrence"] for item in value):
                reasons.append("four_occurrences_in_order must name four pinned occurrences")
        elif key == "move_with_occurrence" and isinstance(value, list):
            # This is a set of semantic labels, not concrete clip/role targets.
            reasons.append("moved image/VO/caption group lacks concrete clip IDs")
    case_media = case.get("media", {})
    if isinstance(case_media, dict):
        for key, value in case_media.items():
            if key.endswith("digest") and isinstance(value, str) and value.startswith("sha256:") and value not in media:
                reasons.append(f"media digest for {key} is not present in verified pinned bytes")
            if key.endswith("_path") or key.endswith("_directory") or key == "collection_path":
                if isinstance(value, str):
                    resource = (action_root / value).resolve()
                    try:
                        resource.relative_to(action_root.resolve())
                    except ValueError:
                        reasons.append(f"media path for {key} escapes the action fixture root")
                    else:
                        if not resource.exists():
                            reasons.append(f"media path for {key} is missing: {value}")
    if case.get("id") == "A02" and not (action_root / "media/music-bed.wav").is_file():
        reasons.append("A02 continuous fixture music bytes are missing")
    if case.get("id") == "A03" and not any("concrete clip IDs" in item for item in reasons):
        pass
    if case.get("id") == "A04" and not case_media.get("alternate_image_digest"):
        reasons.append("A04 alternate image digest is missing")
    if case.get("id") == "A05" and not (action_root / "A05-vo-endpoints.json").is_file():
        reasons.append("A05 frame-aligned voice endpoint table is missing")
    if case.get("id") == "A06" and not (action_root / "A06-text-roles.json").is_file():
        reasons.append("A06 separate title/script/transcript/voice fixture is missing")
    if case.get("id") == "A07" and not (action_root / "audio-fixtures.json").is_file():
        reasons.append("A07 decoded audio fixture is missing")
    if case.get("id") == "A09":
        collection = action_root / "A09-images.json"
        if not collection.is_file():
            reasons.append("A09 four-image collection bytes are missing")
    if case.get("id") == "A10":
        collection = action_root / "A10-brightness-collection.json"
        if not collection.is_file():
            reasons.append("A10 200-image brightness collection bytes are missing")
    return reasons


def _case_operational_evidence(case_id: str, attempt_root: Path | None) -> tuple[bool, list[str]]:
    if attempt_root is None:
        return False, ["no attempt root was supplied"]
    candidates = [attempt_root / "cases" / case_id, attempt_root / case_id]
    case_dir = next((path for path in candidates if path.exists()), candidates[0])
    if case_dir.is_symlink():
        return False, ["case evidence directory is a symlink"]
    required = ("attempt.json", "trace.jsonl", "result.json", "graded-result.json")
    missing = [name for name in required if not (case_dir / name).is_file()]
    if missing:
        return False, ["attempt evidence missing: " + ", ".join(missing)]
    reasons: list[str] = []
    try:
        attempt = _read_json(case_dir / "attempt.json")
        result = _read_json(case_dir / "result.json")
        graded = _read_json(case_dir / "graded-result.json")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return False, [f"attempt evidence JSON is invalid: {exc}"]
    if attempt.get("kind") != "astrid.timeline-eval.case-attempt.v1":
        reasons.append("attempt manifest schema is missing or unsupported")
    if attempt.get("attempt_id") != attempt_root.name:
        reasons.append("attempt manifest ID does not match the supplied attempt root")
    if attempt.get("case_id") != case_id:
        reasons.append("attempt manifest case ID does not match fixture case")
    if attempt.get("fresh_context") is not True:
        reasons.append("attempt does not certify a fresh agent context")
    if not attempt.get("session_id") or not attempt.get("started_at"):
        reasons.append("attempt manifest lacks a session ID or start time")
    for label, payload in (("agent result", result), ("graded result", graded)):
        if payload.get("attempt_id") != attempt_root.name or payload.get("case_id", payload.get("id")) != case_id:
            reasons.append(f"{label} is not bound to this attempt and case")
    try:
        with (case_dir / "trace.jsonl").open(encoding="utf-8") as handle:
            trace_rows = [json.loads(line) for line in handle if line.strip()]
        if not trace_rows or any(not isinstance(row, dict) for row in trace_rows):
            reasons.append("trace has no valid event objects")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        reasons.append("trace is unreadable or contains an incomplete JSON line")
    result_status = str(result.get("execution_status", result.get("status", ""))).lower()
    if result_status in {"not_run", "blocked", "fixture_blocked", "precondition_failed", "unavailable", "setup_failed", "setup_failure"}:
        reasons.append(f"agent execution ended in {result_status}")
    elif result_status not in {"passed", "failed", "completed", "timeout", "timed_out", "partial", "missing_capability"}:
        reasons.append("agent result has no recognized terminal execution status")
    grade_status = str(graded.get("status", "")).lower()
    setup_status = str(graded.get("setup_status", "")).lower()
    if grade_status in {"blocked", "setup_failed", "not_run", "precondition_failed", "unavailable"}:
        reasons.append(f"grading ended in {grade_status}")
    elif grade_status not in {"passed", "failed", "missing_capability"}:
        reasons.append("graded result has no recognized terminal status")
    if setup_status != "ready":
        reasons.append(f"grader setup status is {setup_status or 'missing'}")
    return not reasons, reasons


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


def _lookup_dotted(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        current = current.get(part) if isinstance(current, dict) else None
    return current


def _fixture_requirement_reasons(
    case: dict[str, Any], manifest: dict[str, Any], manifest_path: Path,
    eval_root: Path | None = None,
) -> list[str]:
    """Check case-declared prerequisites against the pinned fixture contents.

    Requirements live with the fixture case instead of a runner-side case-ID
    table, so adding an artifact or adapter can directly change readiness.
    Supported predicates stay deliberately small: explicit values, exact
    equality, or a regular file constrained to the fixture evidence root.
    """
    requirements = case.get("fixture_requirements", [])
    if not isinstance(requirements, list):
        return ["fixture_requirements must be an array"]
    reasons: list[str] = []
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict):
            reasons.append(f"fixture requirement {index} is malformed")
            continue
        scope = requirement.get("scope", "manifest")
        path = requirement.get("path")
        predicate = requirement.get("predicate", "explicit")
        label = str(requirement.get("reason") or f"required fixture prerequisite {scope}.{path} is unavailable")
        if not isinstance(path, str) or not path:
            reasons.append(f"fixture requirement {index} has no dotted path")
            continue
        root = manifest if scope == "manifest" else manifest.get("targets") if scope == "targets" else None
        if root is None:
            reasons.append(f"fixture requirement {index} has unsupported scope {scope!r}")
            continue
        value = _lookup_dotted(root, path)
        available = False
        if predicate == "explicit":
            available = _is_explicit(value)
        elif predicate == "equals":
            available = value == requirement.get("expected")
        elif predicate == "file":
            if isinstance(value, str) and value:
                candidate = _resolve_file(
                    manifest_path, value, eval_root or manifest_path.parent,
                )
                if candidate and candidate.is_file() and not candidate.is_symlink():
                    expected_digest = requirement.get("sha256")
                    available = expected_digest is None or _file_digest(candidate) == expected_digest
        else:
            reasons.append(f"fixture requirement {index} has unsupported predicate {predicate!r}")
            continue
        if not available:
            reasons.append(label)
    return reasons


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
            if isinstance(target, str) and target:
                resolved: Any = target_catalog
                for segment in target.split("."):
                    resolved = resolved.get(segment) if isinstance(resolved, dict) else None
                if resolved is None:
                    return False
                if not _is_explicit(resolved):
                    return False
                if not any(
                    key in resolved
                    for key in ("occurrence_id", "shot_id", "shot_revision_id", "internal_timeline_revision_id", "revision_id", "element_id", "segment_id", "text_id", "output_id", "id", "status")
                ):
                    nested = json.dumps(resolved, ensure_ascii=False)
                    if not any(token in nested for token in ('"segment_id"', '"output_id"', '"text_id"')):
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
    attempt_root: Path | None = None,
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
        eval_root = fixture_root.parent.parent
        manifest, verified_media, group_problems = _manifest_context(path, kind, eval_root)
        if manifest is None:
            manifest = {}
        rows = manifest.get("cases")
        if not isinstance(rows, list):
            raise ValueError(f"{path}: cases must be an array")
        baseline_path_value = (
            manifest.get("source", {}).get("baseline") if kind == "navigation"
            else manifest.get("base", {}).get("baseline_path")
        )
        baseline_path = _resolve_file(path, baseline_path_value, eval_root)
        baseline = _read_json(baseline_path) if baseline_path and baseline_path.is_file() else None
        known_ids = _extract_known_ids(baseline)
        action_root = path.parent
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
            readiness = validate_case(row, kind, path, target_catalog)
            specific_reasons = []
            specific_reasons.extend(_fixture_requirement_reasons(row, manifest, path, eval_root))
            for problem in group_problems:
                if kind == "action" and any(problem.startswith(prefix) for prefix in ("A05", "A06", "A09", "A10")):
                    if problem.startswith(case_id):
                        specific_reasons.append(problem)
                    elif problem.startswith("A05") and case_id in {"A02", "A05", "A07"}:
                        specific_reasons.append(problem)
                else:
                    specific_reasons.append(problem)
            if kind == "action":
                specific_reasons.extend(_validate_action_case(row, known_ids, verified_media, action_root))
            else:
                aliases = row.get("targets", [])
                if isinstance(aliases, list):
                    for alias in aliases:
                        if not isinstance(alias, str) or _lookup_dotted(target_catalog, alias) is None:
                            specific_reasons.append(f"target alias {alias!r} has no pinned target record")
            readiness.reasons.extend(specific_reasons)
            if readiness.reasons:
                readiness.readiness = "blocked"
            else:
                readiness.readiness = "fixture_ready"
            evidence_ready, evidence_reasons = _case_operational_evidence(case_id, attempt_root)
            readiness.operational_ready = readiness.readiness == "fixture_ready" and evidence_ready
            if readiness.readiness == "blocked":
                readiness.operational_reasons = ["fixture prerequisites are blocked; attempt evidence cannot clear them"]
            elif not readiness.operational_ready:
                readiness.operational_reasons = evidence_reasons
            result[case_id] = readiness
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
        "counts": {
            "fixture_ready": sum(row.readiness == "fixture_ready" for row in rows),
            "blocked": sum(row.readiness == "blocked" for row in rows),
            "operational_ready": sum(row.operational_ready for row in rows),
        },
        "cases": [row.__dict__ for row in rows],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Timeline evaluation fixture readiness",
        "",
        "Generated by `Astrid/evals/timeline/fixture_manifest.py`. Readiness is based on concrete manifest fields, not case IDs.",
        "",
        "| Case | Kind | Fixture inputs | Operational run | Missing or blocking details |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        details = "; ".join(row.reasons + row.operational_reasons).replace("|", "\\|") or "All required fixture fields are explicit."
        op = "ready" if row.operational_ready else "not ready"
        lines.append(f"| {row.case_id} | {row.kind} | {row.readiness} | {op} | {details} |")
    lines.extend(["", f"Counts: {payload['counts']}.", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--report-root", type=Path, default=DEFAULT_REPORT_ROOT)
    parser.add_argument("--attempt-root", "--operational-root", dest="attempt_root", type=Path,
                        help="fresh attempt root containing per-case attempt/trace/result/graded-result evidence")
    parser.add_argument("--require-ready", nargs="*", default=None, metavar="CASE_ID",
                        help="exit nonzero unless each selected case's fixture inputs validate")
    parser.add_argument("--require-operational", nargs="*", default=None, metavar="CASE_ID",
                        help="exit nonzero unless selected cases have executable/run evidence")
    args = parser.parse_args()
    rows = build_readiness(args.suite, args.fixture_root, args.attempt_root)
    json_path, markdown_path = write_reports(rows, args.report_root)
    print(f"wrote {json_path}")
    print(f"wrote {markdown_path}")
    counts = {
        "fixture_ready": sum(row.readiness == "fixture_ready" for row in rows),
        "blocked": sum(row.readiness == "blocked" for row in rows),
        "operational_ready": sum(row.operational_ready for row in rows),
    }
    print(" ".join(f"{status}={value}" for status, value in counts.items()))
    indexed = {row.case_id: row for row in rows}
    for case_id in args.require_ready or []:
        if case_id not in indexed or indexed[case_id].readiness != "fixture_ready":
            print(f"required fixture case is blocked or unknown: {case_id}")
            return 2
    for case_id in args.require_operational or []:
        if case_id not in indexed or not indexed[case_id].operational_ready:
            print(f"required operational case is not executable: {case_id}")
            return 2
    if args.require_ready is not None or args.require_operational is not None:
        return 0
    return 2 if counts["blocked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
