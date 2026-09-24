"""Local disposable project preparation for timeline-eval cases.

This is deliberately a filesystem seam, not another Runtime implementation.  A
seed project is copied into a case-owned directory, the caller (or an existing
Runtime client) supplies the destination project identity, and only the
project-local identity/path fields are changed.  The seed is never opened for
writing.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


RECEIPT_KIND = "astrid.timeline-eval.local-disposable-project.v1"
RECEIPT_NAME = "disposable-project-receipt.json"


class LocalProjectAdapterError(ValueError):
    """The seed or case-local project cannot satisfy the adapter contract."""


def _safe_path(path: str | Path, label: str) -> Path:
    value = Path(path).expanduser().absolute()
    # Resolve normal system aliases such as macOS's /tmp -> /private/tmp,
    # while rejecting a symlink supplied as the project root itself.
    if value.is_symlink():
        raise LocalProjectAdapterError(f"{label} must not be a symlink: {value}")
    return value.resolve(strict=False)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalProjectAdapterError(f"cannot read {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise LocalProjectAdapterError(f"{label} must be a JSON object")
    return value


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalProjectAdapterError(f"cannot read {label}: {exc}") from exc


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _case_slug(seed_slug: str, case_id: str) -> str:
    suffix = re.sub(r"[^a-z0-9-]+", "-", case_id.strip().lower()).strip("-")
    if not suffix:
        raise LocalProjectAdapterError("case_id must contain at least one alphanumeric character")
    return f"{seed_slug}-{suffix}"


def _rewrite_strings(
    value: Any,
    *,
    seed_root: str,
    case_root: str,
    seed_slug: str,
    case_slug: str,
    seed_project_id: str,
    case_project_id: str,
    key: str | None = None,
) -> Any:
    """Rewrite only paths that unambiguously point into this project."""
    if isinstance(value, str):
        if key in {"project_id", "projectId"} and value == seed_project_id:
            return case_project_id
        if key in {"project_slug", "projectSlug"} and value == seed_slug:
            return case_slug
        if value == seed_root or value.startswith(seed_root + "/"):
            return case_root + value[len(seed_root):]
        project_prefix = f"projects/{seed_slug}/"
        if value == f"projects/{seed_slug}":
            return f"projects/{case_slug}"
        if value.startswith(project_prefix):
            return f"projects/{case_slug}/" + value[len(project_prefix):]
        return value
    if isinstance(value, list):
        return [_rewrite_strings(item, seed_root=seed_root, case_root=case_root, seed_slug=seed_slug, case_slug=case_slug, seed_project_id=seed_project_id, case_project_id=case_project_id, key=key) for item in value]
    if isinstance(value, dict):
        return {child_key: _rewrite_strings(item, seed_root=seed_root, case_root=case_root, seed_slug=seed_slug, case_slug=case_slug, seed_project_id=seed_project_id, case_project_id=case_project_id, key=child_key) for child_key, item in value.items()}
    return value


def _runtime_project_id(
    *,
    seed: Mapping[str, Any],
    case_slug: str,
    case_id: str,
    runtime_project_id: str | None,
    runtime: Any | None,
    project_creator: Callable[..., Any] | None,
) -> str:
    seed_id = seed["project_id"]
    if runtime_project_id is not None:
        value = str(runtime_project_id).strip()
    elif project_creator is not None:
        result = project_creator(case_slug, case_id=case_id, seed_project=seed)
        value = result.get("project_id", result.get("id")) if isinstance(result, Mapping) else str(result)
    elif runtime is not None and hasattr(runtime, "create_project"):
        creator = runtime.create_project
        try:
            result = creator(
                "Timeline Eval Case",
                slug=case_slug,
                metadata={"purpose": "timeline-eval-local-disposable", "case_id": case_id},
                idempotency_key=f"timeline-eval-local:{case_id}:{case_slug}",
            )
        except TypeError:
            # RealmStore/service-style Runtime APIs use slug, name, metadata.
            result = creator(
                case_slug,
                "Timeline Eval Case",
                {"purpose": "timeline-eval-local-disposable", "case_id": case_id},
                idempotency_key=f"timeline-eval-local:{case_id}:{case_slug}",
            )
        value = result.get("project_id", result.get("id")) if isinstance(result, Mapping) else str(result)
    else:
        # Local preparation remains runnable without a daemon.  When a Runtime
        # client is available, callers should pass it so its server-assigned ID
        # is used instead.
        value = str(uuid.uuid4())
    if not value:
        raise LocalProjectAdapterError("Runtime project creation returned no project ID")
    if value == seed_id:
        raise LocalProjectAdapterError("disposable Runtime project ID must differ from the seed project ID")
    return value


@dataclass(frozen=True)
class LocalDisposableProject:
    case_id: str
    seed_project_id: str
    seed_project_slug: str
    project_id: str
    project_slug: str
    case_dir: Path
    project_json: Path
    receipt_path: Path
    receipt: Mapping[str, Any]


def prepare_local_project(
    seed_dir: str | Path,
    case_dir: str | Path,
    *,
    case_id: str,
    runtime_project_id: str | None = None,
    runtime: Any | None = None,
    project_creator: Callable[..., Any] | None = None,
) -> LocalDisposableProject:
    """Copy one pinned seed project into a fresh case-owned directory.

    ``runtime_project_id`` is useful for local tests and an existing Runtime
    client's ``create_project`` can be supplied for server-assigned identity.
    No network, daemon, container, or alternate store is created here.
    """
    seed_root = _safe_path(seed_dir, "seed project")
    case_root = _safe_path(case_dir, "case project")
    if not seed_root.is_dir():
        raise LocalProjectAdapterError("seed project directory does not exist")
    seed_json = seed_root / "project.json"
    if not seed_json.is_file():
        raise LocalProjectAdapterError("seed project is missing project.json")
    seed = _load_object(seed_json, "seed project.json")
    seed_id = seed.get("project_id")
    seed_slug = seed.get("slug")
    if not isinstance(seed_id, str) or not seed_id or not isinstance(seed_slug, str) or not seed_slug:
        raise LocalProjectAdapterError("seed project.json requires non-empty project_id and slug")
    for path in seed_root.rglob("*"):
        if path.is_symlink():
            raise LocalProjectAdapterError(f"seed project contains a symlink: {path}")
    if case_root.exists():
        receipt = case_root / RECEIPT_NAME
        if receipt.is_file():
            existing = _load_object(receipt, "existing disposable project receipt")
            if existing.get("case_id") == case_id and existing.get("seed", {}).get("project_id") == seed_id:
                target = existing.get("target", {})
                return LocalDisposableProject(case_id, seed_id, seed_slug, str(target["project_id"]), str(target["slug"]), case_root, case_root / "project.json", receipt, existing)
        if any(case_root.iterdir()):
            raise LocalProjectAdapterError("case directory already exists and is not a matching prepared project")
    else:
        case_root.mkdir(parents=True)

    case_slug = _case_slug(seed_slug, case_id)
    project_id = _runtime_project_id(seed=seed, case_slug=case_slug, case_id=case_id, runtime_project_id=runtime_project_id, runtime=runtime, project_creator=project_creator)
    canonical_hash_before = _sha256(seed_json)
    shutil.copytree(seed_root, case_root, dirs_exist_ok=True)
    copied_json = case_root / "project.json"
    for path in case_root.rglob("*.json"):
        if path.name == RECEIPT_NAME:
            continue
        data = _load_json(path, f"copied JSON {path}")
        rewritten = _rewrite_strings(data, seed_root=str(seed_root), case_root=str(case_root), seed_slug=seed_slug, case_slug=case_slug, seed_project_id=seed_id, case_project_id=project_id)
        if path == copied_json:
            rewritten["project_id"] = project_id
            rewritten["slug"] = case_slug
        path.write_text(json.dumps(rewritten, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if _sha256(seed_json) != canonical_hash_before:
        raise LocalProjectAdapterError("canonical seed project changed while preparing disposable copy")

    receipt_data: dict[str, Any] = {
        "kind": RECEIPT_KIND,
        "case_id": case_id,
        "seed": {"project_id": seed_id, "slug": seed_slug, "project_json_sha256": canonical_hash_before},
        "target": {"project_id": project_id, "slug": case_slug, "case_dir": str(case_root), "project_json": str(copied_json)},
        "mutable_path_checks": {"project_id_rewritten": True, "slug_rewritten": True, "case_dir_owned": True, "canonical_seed_unchanged": True},
    }
    receipt_path = case_root / RECEIPT_NAME
    receipt_path.write_text(json.dumps(receipt_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return LocalDisposableProject(case_id, seed_id, seed_slug, project_id, case_slug, case_root, copied_json, receipt_path, receipt_data)


clone_disposable_project = prepare_local_project
prepare_disposable_project = prepare_local_project


class LocalDisposableProjectAdapter:
    """Small object-form wrapper for callers that already use adapters."""

    prepare = staticmethod(prepare_local_project)
