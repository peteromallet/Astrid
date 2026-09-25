"""Fail-closed T9 CPU inference substitute admission and activation."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Mapping


SOURCE_ENV = "ASTRID_T9_MODEL_SUBSTITUTE_SOURCE"
HASH_ENV = "ASTRID_T9_MODEL_SUBSTITUTE_SHA256"
MARKER_ENV = "ASTRID_T9_MODEL_SUBSTITUTE_MARKER"


class T9SubstituteError(RuntimeError):
    pass


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def approved_source(profile: Mapping[str, Any]) -> tuple[Path, str] | None:
    """Validate an explicitly approved, fixture-local model-boundary source."""
    value = profile.get("t9_model_substitute")
    if value is None:
        return None
    if not isinstance(value, Mapping) or value.get("approved") is not True:
        raise T9SubstituteError("T9 model substitute is not approved by readiness")
    if value.get("mode") != "deterministic_cpu_model_boundary_v1":
        raise T9SubstituteError("T9 model substitute mode is unsupported")
    raw_path, expected = value.get("source_path"), value.get("source_sha256")
    if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
        raise T9SubstituteError("T9 model substitute source_path must be absolute")
    path = Path(raw_path)
    if path.is_symlink() or not path.is_file():
        raise T9SubstituteError("T9 model substitute source must be a regular non-symlink file")
    if not isinstance(expected, str) or expected != _digest(path):
        raise T9SubstituteError("T9 model substitute source hash does not match readiness")
    return path.resolve(), expected


def verify_child_contract(environment: Mapping[str, str] | None = None) -> tuple[Path, str, Path]:
    env = os.environ if environment is None else environment
    raw_path, expected, raw_marker = env.get(SOURCE_ENV), env.get(HASH_ENV), env.get(MARKER_ENV)
    if not raw_path or not expected or not raw_marker:
        raise T9SubstituteError("T9 model substitute approval and activation marker are required")
    path, marker = Path(raw_path), Path(raw_marker)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise T9SubstituteError("T9 model substitute source is unavailable")
    if _digest(path) != expected:
        raise T9SubstituteError("T9 model substitute source hash changed")
    if not marker.is_absolute() or marker.is_symlink():
        raise T9SubstituteError("T9 model substitute activation marker path is invalid")
    return path.resolve(), expected, marker


def activate_from_environment() -> None:
    """Load the attested boundary hook and record activation for this child."""
    try:
        source, expected, marker = verify_child_contract()
        spec = importlib.util.spec_from_file_location("astrid_t9_approved_model_substitute", source)
        if spec is None or spec.loader is None:
            raise T9SubstituteError("T9 model substitute cannot be loaded")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if getattr(module, "ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE", False) is not True:
            raise T9SubstituteError("T9 model substitute did not activate its model boundary")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({"pid": os.getpid(), "source": str(source), "sha256": expected}, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        # Importing sitecustomize must never convert a failed T9 hook into real
        # model execution. The engine boundary independently checks the marker.
        os.environ["ASTRID_T9_MODEL_SUBSTITUTE_ACTIVATION_ERROR"] = type(exc).__name__


def require_active_marker(environment: Mapping[str, str] | None = None) -> None:
    source, expected, marker = verify_child_contract(environment)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise T9SubstituteError("T9 model substitute child activation marker is missing") from exc
    if not isinstance(payload, Mapping) or payload.get("source") != str(source) or payload.get("sha256") != expected:
        raise T9SubstituteError("T9 model substitute child activation marker does not match approval")
