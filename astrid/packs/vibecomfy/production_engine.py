"""Pinned-interpreter bridge from typed Astrid workflows to VibeComfy."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import shutil
import signal
import sys
import tempfile
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_PROFILE_CONFIGS = {
    "pip_embedded": {
        "name": "pip_embedded",
        "dependency_lock": "vibecomfy-pip-comfyui-0.26.0",
        "session_kind": "embedded_session",
        "warm_policy": "never",
        "cancellation": "owned_process_group",
    },
    "checkout_server": {
        "name": "checkout_server",
        "dependency_lock": "vibecomfy-checkout-comfyui-0.26.0",
        "session_kind": "server_session",
        "warm_policy": "auto",
        "cancellation": "interrupt-clear-free-then-owned_process_group",
    },
}

_EMBEDDED_COMFY_CLIENT = Path("comfy/client/embedded_comfy_client.py")
_EMBEDDED_COMFY_FALLBACKS = (Path("/root/b06-t04/comfyui-embedded"),)


class ProductionEngineError(RuntimeError):
    """The pinned VibeComfy engine rejected or failed a typed workflow."""


@dataclass(frozen=True, slots=True)
class LoadedWorkflow:
    """Canonical loader result shared by host preflight and child execution."""

    resolved: Any
    model_id: str
    template_id: str
    workflow_identity: str
    workflow_revision: str
    workflow_content_digest: str


@dataclass(frozen=True, slots=True)
class ProductionRunResult:
    """Structured producer completion retained across the engine boundary."""

    outputs: tuple[Path, ...]
    managed_generation_result_path: Path | None = None
    managed_generation_result: dict[str, Any] | None = None
    producer_run_id: str | None = None
    attempt_id: str | None = None


_LAST_PRODUCTION_RESULT: ProductionRunResult | None = None


def _workflow_comfyui_version_requirement(resolved: Any) -> str | None:
    """Read the canonical workflow's typed ComfyUI version declaration."""
    bundle = _canonical_bundle_value(resolved)
    workflow = getattr(bundle, "workflow", None)
    requirements = getattr(workflow, "requirements", None)
    runtime = getattr(requirements, "runtime", None)
    declared = getattr(runtime, "comfy_version", None)
    if declared is None and isinstance(getattr(workflow, "metadata", None), Mapping):
        raw = workflow.metadata.get("requirements")
        if isinstance(raw, Mapping) and isinstance(raw.get("runtime"), Mapping):
            declared = raw["runtime"].get("comfy_version")
    if declared is None:
        return None
    if not isinstance(declared, str) or not declared.strip():
        raise ProductionEngineError(
            "workflow requirements.runtime.comfy_version must be a non-empty string"
        )
    return declared.strip()


def _profile_comfyui_version_requirement(hc03_profile: Any) -> str | None:
    """Read the release-bound ComfyUI contract from a worker profile."""
    if not isinstance(hc03_profile, Mapping):
        return None
    runtime = hc03_profile.get("runtime")
    if not isinstance(runtime, Mapping):
        return None
    declared = runtime.get("comfyui_version")
    if declared is None:
        return None
    if not isinstance(declared, str) or not declared.strip():
        raise ProductionEngineError(
            "worker readiness runtime.comfyui_version must be a non-empty string"
        )
    return declared.strip()


def _bootstrap_embedded_comfy_client(hc03_profile: Any = None) -> Path:
    """Select and import the embedded-client ComfyUI tree for pip execution."""
    candidate = hc03_profile.get("comfyui_candidate") if isinstance(hc03_profile, Mapping) else None
    launch = hc03_profile.get("launch") if isinstance(hc03_profile, Mapping) else None
    raw_root = candidate.get("root") if isinstance(candidate, Mapping) else None
    revision = candidate.get("revision") if isinstance(candidate, Mapping) else None
    content_digest = candidate.get("source_content_digest") if isinstance(candidate, Mapping) else None
    configured = launch.get("comfyui_path") if isinstance(launch, Mapping) else None
    if not all(isinstance(value, str) and value.strip() for value in (raw_root, revision, content_digest, configured)):
        raise ProductionEngineError(
            "pip_embedded requires an attested pinned ComfyUI tree and explicit verified COMFYUI_PATH"
        )
    if not re.fullmatch(r"(?:sha256:)?[0-9a-fA-F]{64}", content_digest):
        raise ProductionEngineError("pip_embedded readiness has an invalid ComfyUI source hash")
    root = Path(raw_root).expanduser()
    environment_root = os.environ.get("COMFYUI_PATH")
    if not root.is_absolute() or root.is_symlink() or not isinstance(environment_root, str) or not environment_root:
        raise ProductionEngineError("pip_embedded requires explicit verified COMFYUI_PATH")
    root = root.resolve()
    if Path(configured).expanduser().resolve() != root or Path(environment_root).expanduser().resolve() != root:
        raise ProductionEngineError("COMFYUI_PATH does not match the attested pinned ComfyUI tree")
    if not (root / _EMBEDDED_COMFY_CLIENT).is_file():
        raise ProductionEngineError("attested ComfyUI tree lacks comfy/client/embedded_comfy_client.py")
    try:
        actual_revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        archive = subprocess.run(
            ["git", "-C", str(root), "archive", "--format=tar", "HEAD"],
            check=True,
            capture_output=True,
            timeout=10,
        ).stdout
        clean = subprocess.run(
            ["git", "-C", str(root), "diff", "--quiet", "HEAD", "--"],
            check=False,
            capture_output=True,
            timeout=5,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProductionEngineError("attested ComfyUI tree revision could not be verified") from exc
    archive_digest = "sha256:" + hashlib.sha256(archive).hexdigest()
    if actual_revision != revision or archive_digest != "sha256:" + content_digest.removeprefix("sha256:") or not clean:
        raise ProductionEngineError("ComfyUI tree does not match its pinned readiness identity")

    root_string = str(root)
    sys.path[:] = [entry for entry in sys.path if entry != root_string]
    sys.path.insert(0, root_string)
    importlib.invalidate_caches()
    try:
        module = importlib.import_module("comfy.client.embedded_comfy_client")
        getattr(module, "Comfy")
    except Exception as exc:  # noqa: BLE001 - normalize the third-party import boundary.
        raise ProductionEngineError(
            f"pip_embedded cannot import comfy.client.embedded_comfy_client from {root}"
        ) from exc

    module_path = Path(getattr(module, "__file__", "")).resolve()
    expected_path = (root / _EMBEDDED_COMFY_CLIENT).resolve()
    if module_path != expected_path:
        raise ProductionEngineError(
            "pip_embedded imported comfy.client.embedded_comfy_client from "
            f"{module_path}, expected {expected_path}"
        )
    return root


def _replace_references(value: Any, references: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        return references.get(value, value)
    if isinstance(value, list):
        return [_replace_references(item, references) for item in value]
    if isinstance(value, dict):
        object_id = value.get("object_id")
        if (
            isinstance(object_id, str)
            and object_id in references
            and set(value).issubset({"kind", "object_id"})
        ):
            return references[object_id]
        return {
            key: _replace_references(item, references)
            for key, item in value.items()
        }
    return value


def _load_workflow(workflow: Mapping[str, Any], references: Mapping[str, str], scratch: Path):
    template_id = workflow.get("template_id")
    bindings = workflow.get("bindings")
    if isinstance(template_id, str) and isinstance(bindings, Mapping):
        import vibecomfy
        from vibecomfy.registry.ready import repo_ready_template_discovery, workflow_from_ready

        if vibecomfy.__file__ is None:
            raise ProductionEngineError("installed vibecomfy package has no filesystem root")
        ready_root = Path(vibecomfy.__file__).resolve().parent.parent / "ready_templates"
        discovery = repo_ready_template_discovery(root=ready_root if ready_root.exists() else None)
        resolved = workflow_from_ready(template_id, _discovery=discovery)
        for name, value in bindings.items():
            try:
                resolved.set_input(name, _replace_references(value, references))
            except ValueError as exc:
                # A typed producer must not silently lose a control or source
                # binding merely because the selected ready template does not
                # expose it.  Ignoring that case can run a template against a
                # default local file, violating CAS custody and UI semantics.
                raise ProductionEngineError(
                    f"ready template {template_id!r} does not expose typed input {name!r}"
                ) from exc
        return resolved

    raise ProductionEngineError(
        "production engine accepts only canonical ready-template workflows"
    )


def _canonical_bundle_value(resolved: Any) -> Any:
    """Bind a loader result to VibeComfy's canonical bundle authority."""
    try:
        from vibecomfy.workflow import VibeWorkflow
        from vibecomfy.workflow_bundle import WorkflowBundle, load_bundle
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise ProductionEngineError(
            "VibeComfy canonical workflow bundle support is unavailable"
        ) from exc
    if isinstance(resolved, WorkflowBundle):
        bundle = resolved
    elif isinstance(resolved, VibeWorkflow):
        bundle = load_bundle(resolved)
    else:
        raise ProductionEngineError(
            "production engine requires a canonical VibeComfy loader result"
        )
    bundle.require_canonical_authority("production engine execution")
    return bundle


def _workflow_content_digest(source: Path) -> str:
    """Bind execution identity to the exact admitted input member bytes."""
    members = [source]
    if source.suffix.lower() == ".py":
        members.extend((source.with_suffix(".vibe.json"), source.with_name("source.json")))
    digest = hashlib.sha256()
    for member in members:
        try:
            payload = member.read_bytes()
        except OSError as exc:
            raise ProductionEngineError(
                f"canonical workflow member could not be read: {member}"
            ) from exc
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return "sha256:" + digest.hexdigest()


def _ui_workflow_identity(workflow: Mapping[str, Any], source_bytes: bytes) -> str:
    """Use declared UI identity when present, otherwise its exact content hash."""
    candidates = [
        workflow.get("workflow_identity"),
        workflow.get("workflow_id"),
        workflow.get("id"),
    ]
    nested_source = workflow.get("source")
    if isinstance(nested_source, Mapping):
        candidates.extend(
            (
                nested_source.get("id"),
                nested_source.get("workflow_identity"),
                nested_source.get("workflow_id"),
            )
        )
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return hashlib.sha256(source_bytes).hexdigest()


def _canonicalize_ui_workflow(
    source: Path,
    raw_workflow: Mapping[str, Any],
    scratch: Path,
) -> Any:
    """Convert UI JSON through VibeComfy's canonical import service."""
    try:
        source_bytes = source.read_bytes()
        from vibecomfy.porting.import_service import import_workflow_bytes

        artifacts = import_workflow_bytes(
            source_bytes,
            workflow_id=_ui_workflow_identity(raw_workflow, source_bytes),
        )
    except ImportError as exc:
        raise ProductionEngineError(
            "VibeComfy canonical UI workflow conversion is unavailable"
        ) from exc
    except OSError as exc:
        raise ProductionEngineError(f"workflow could not be read: {source}") from exc
    except Exception as exc:
        raise ProductionEngineError(
            f"VibeComfy canonical UI workflow conversion failed: {exc}"
        ) from exc

    python_bytes = getattr(artifacts, "python_bytes", None)
    companion_bytes = getattr(artifacts, "companion_bytes", None)
    returned_source = getattr(artifacts, "source_bytes", None)
    if (
        not isinstance(python_bytes, bytes)
        or not python_bytes
        or not isinstance(companion_bytes, bytes)
        or not companion_bytes
        or returned_source != source_bytes
    ):
        raise ProductionEngineError(
            "VibeComfy canonical UI workflow conversion returned invalid members"
        )
    staging = Path(tempfile.mkdtemp(prefix="canonical-ui-", dir=scratch))
    python_path = staging / "workflow.py"
    python_path.write_bytes(python_bytes)
    python_path.with_suffix(".vibe.json").write_bytes(companion_bytes)
    python_path.with_name("source.json").write_bytes(source_bytes)
    try:
        from vibecomfy.security.provenance import Provenance
        from vibecomfy.workflow_bundle import load_bundle

        return load_bundle(python_path, trust=Provenance.USER_CONFIRMED)
    except Exception as exc:
        raise ProductionEngineError(
            f"VibeComfy canonical UI workflow bundle could not be loaded: {exc}"
        ) from exc


def load_workflow_path(
    workflow_path: str | Path,
    scratch: str | Path,
    *,
    model_id: str = "vibecomfy",
    template_id: str = "vibecomfy.run",
) -> LoadedWorkflow:
    """Load one canonical workflow and return its effective execution profile."""
    source = Path(workflow_path).expanduser().resolve(strict=True)
    scratch_path = Path(scratch).expanduser().resolve()
    scratch_path.mkdir(parents=True, exist_ok=True)
    try:
        source_bytes = source.read_bytes()
        raw_workflow = None if source.suffix.lower() == ".py" else json.loads(
            source_bytes.decode("utf-8")
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionEngineError(f"workflow could not be read: {source}") from exc
    if source.suffix.lower() == ".py":
        try:
            from vibecomfy.security.provenance import Provenance
            from vibecomfy.workflow_bundle import load_bundle

            resolved = load_bundle(source, trust=Provenance.USER_CONFIRMED)
        except Exception as exc:
            raise ProductionEngineError(
                f"canonical workflow bundle could not be loaded: {exc}"
            ) from exc
    else:
        if not isinstance(raw_workflow, Mapping):
            raise ProductionEngineError("workflow must be a JSON object")
        if isinstance(raw_workflow.get("template_id"), str) and isinstance(
            raw_workflow.get("bindings"), Mapping
        ):
            resolved = _load_workflow(raw_workflow, {}, scratch_path)
        else:
            resolved = _canonicalize_ui_workflow(
                source,
                raw_workflow,
                scratch_path,
            )
    bundle = _canonical_bundle_value(resolved)
    metadata = getattr(bundle.workflow, "metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    effective_template_id = str(
        metadata.get("ready_template") or bundle.workflow_identity or template_id
    )
    effective_model_id = str(metadata.get("model_id") or model_id)
    if not effective_template_id.strip():
        raise ProductionEngineError("canonical workflow has no execution identity")
    workflow_identity = str(bundle.workflow_identity)
    workflow_revision = str(bundle.revision_id)
    if not workflow_identity.strip() or not workflow_revision.strip():
        raise ProductionEngineError("canonical workflow bundle identity is incomplete")
    return LoadedWorkflow(
        resolved=bundle,
        model_id=effective_model_id,
        template_id=effective_template_id,
        workflow_identity=workflow_identity,
        workflow_revision=workflow_revision,
        workflow_content_digest=_workflow_content_digest(source),
    )


def execution_identity_digest(
    model_id: str,
    template_id: str,
    *,
    model_digest: str | None = None,
    workflow_identity: str | None = None,
    workflow_revision: str | None = None,
    workflow_content_digest: str | None = None,
) -> str:
    """Return the shared host/child identity for one canonical execution."""
    return hashlib.sha256(
        json.dumps(
            {
                "model_id": model_id,
                "template_id": template_id,
                "model_digest": model_digest,
                "workflow_identity": workflow_identity,
                "workflow_revision": workflow_revision,
                "workflow_content_digest": workflow_content_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def loaded_workflow_execution_identity(
    loaded: LoadedWorkflow,
    hc03_profile: Any = None,
) -> str:
    """Derive the exact host/child identity from one canonical loader result."""
    model_digest = None
    if isinstance(hc03_profile, Mapping):
        facts = hc03_profile.get("verified_facts")
        exact = facts.get("exact") if isinstance(facts, Mapping) else None
        model_digest = exact.get("model_digest") if isinstance(exact, Mapping) else None
    return execution_identity_digest(
        loaded.model_id,
        loaded.template_id,
        model_digest=model_digest,
        workflow_identity=loaded.workflow_identity,
        workflow_revision=loaded.workflow_revision,
        workflow_content_digest=loaded.workflow_content_digest,
    )


def loaded_workflow_session_requirements(loaded: LoadedWorkflow) -> dict[str, Any]:
    """Extract resident-engine requirements from the admitted canonical bundle.

    This deliberately excludes prompts, seeds, and workflow graph identity.
    It includes model/auxiliary asset declarations and loader/runtime settings
    that can change what remains resident in the engine.
    """
    workflow = getattr(loaded.resolved, "workflow", None)
    metadata = getattr(workflow, "metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    requirements = getattr(workflow, "requirements", None)
    if requirements is not None:
        to_dict = getattr(requirements, "to_dict", None)
        if callable(to_dict):
            requirements = to_dict()
        elif isinstance(requirements, Mapping):
            requirements = dict(requirements)
        else:
            requirements = repr(requirements)
    else:
        requirements = metadata.get("requirements", {})
    resident_keys = (
        "model_assets",
        "comfy_configuration",
        "loader",
        "loader_settings",
        "model_set",
        "auxiliary_models",
    )
    resident_metadata = {
        key: metadata[key]
        for key in resident_keys
        if key in metadata
    }
    return {
        "model_id": loaded.model_id,
        "requirements": requirements,
        "resident_metadata": resident_metadata,
    }


def session_identity_digest(
    model_id: str,
    *,
    model_digest: str | None = None,
    required_identity: Mapping[str, object] | None = None,
) -> str:
    """Return the stable engine/session identity for resident model state.

    Workflow/template and invocation fields intentionally do not participate
    here.  They remain part of ``loaded_workflow_execution_identity`` so the
    child still verifies the exact invocation, while the host can retain one
    compatible VibeComfy session across workflow changes.
    """
    if not isinstance(model_id, str) or not model_id.strip():
        raise ProductionEngineError("session model_id must be a non-empty string")
    if model_digest is not None and (
        not isinstance(model_digest, str) or not model_digest.strip()
    ):
        raise ProductionEngineError("session model_digest must be a non-empty string")
    identity = None
    if required_identity is not None:
        if not isinstance(required_identity, Mapping):
            raise ProductionEngineError("session required_identity must be an object")
        identity = {}
        for key, value in required_identity.items():
            if not isinstance(key, str) or not key.strip():
                raise ProductionEngineError("session required_identity has an invalid key")
            if value == "":
                raise ProductionEngineError(
                    f"session required_identity field {key!r} is incomplete"
                )
            try:
                json.dumps(value, sort_keys=True, separators=(",", ":"))
            except (TypeError, ValueError) as exc:
                raise ProductionEngineError(
                    f"session required_identity field {key!r} is not canonical JSON"
                ) from exc
            identity[key] = value
    return hashlib.sha256(
        json.dumps(
            {
                "schema": "astrid.vibecomfy.session-identity.v1",
                "model_id": model_id.strip(),
                "model_digest": model_digest,
                "required_identity": identity,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def _profile_id(value: Any) -> str:
    if not isinstance(value, Mapping):
        raise ProductionEngineError("production engine request lacks an execution profile")
    profile_id = value.get("name")
    if not isinstance(profile_id, str) or profile_id not in _PROFILE_CONFIGS:
        raise ProductionEngineError("production engine request has an unsupported execution profile")
    if dict(value) != _PROFILE_CONFIGS[profile_id]:
        raise ProductionEngineError("production engine profile identity does not match local semantics")
    return profile_id


def _canonical_bundle(
    resolved: Any,
    *,
    run_inputs: Mapping[str, Any] | None = None,
) -> tuple[Any, Any]:
    """Return the approved projection and canonical bundle for one run.

    Runtime inputs belong in the detached approval record.  They must never be
    written into ``bundle.workflow`` after the bundle revision has been
    established: doing so makes the revision fence reject an otherwise valid
    invocation.
    """
    bundle = _canonical_bundle_value(resolved)
    if run_inputs is None:
        return bundle.compile(), bundle
    if not isinstance(run_inputs, Mapping):
        raise ProductionEngineError("workflow run inputs must be an object")
    return bundle.compile(run_inputs=dict(run_inputs)), bundle


def _validate_workflow_input_bindings(
    resolved: Any,
    bindings: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Validate task-owned public inputs without changing the sealed bundle."""
    if bindings is None:
        return None
    if not isinstance(bindings, Mapping):
        raise ProductionEngineError("workflow input bindings must be an object")
    bundle = _canonical_bundle_value(resolved)
    workflow = getattr(bundle, "workflow", None)
    public_inputs = getattr(workflow, "inputs", None)
    if not isinstance(public_inputs, Mapping):
        raise ProductionEngineError("canonical workflow has no public input map")
    validated: dict[str, Any] = {}
    for name, value in bindings.items():
        if not isinstance(name, str) or not name.strip():
            raise ProductionEngineError("workflow run input names must be non-empty strings")
        if name not in public_inputs:
            raise ProductionEngineError(
                f"workflow run input {name!r} is not a declared public input"
            )
        input_type = str(getattr(public_inputs[name], "type", "") or "").upper()
        media = str(getattr(public_inputs[name], "media_semantics", "") or "").lower()
        if media in {"image", "video", "audio", "mask"}:
            if not isinstance(value, str) or not value.strip() or Path(value).name != value:
                raise ProductionEngineError(
                    f"workflow media input {name!r} must be a non-empty basename"
                )
        elif input_type in {"INT", "INTEGER"}:
            if type(value) is not int:
                raise ProductionEngineError(f"workflow input {name!r} must be an integer")
        elif input_type in {"FLOAT", "NUMBER"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ProductionEngineError(f"workflow input {name!r} must be numeric")
        elif input_type in {"BOOLEAN", "BOOL"}:
            if type(value) is not bool:
                raise ProductionEngineError(f"workflow input {name!r} must be a boolean")
        elif not isinstance(value, (str, int, float, bool)) or isinstance(value, bool) and input_type not in {"BOOLEAN", "BOOL"}:
            raise ProductionEngineError(
                f"workflow input {name!r} must be a JSON scalar"
            )
        validated[name] = value
    return validated


def _embedded_session_config(
    bundle: Any,
    destination: Path,
    comfy_root: Path,
    *,
    task_identity: str,
    attempt_identity: str | None = None,
) -> Any:
    """Build a pinned SessionConfig for the embedded profile.

    The Comfy-specific values remain in VibeComfy's ``extra`` mapping; the
    runtime-root and cwd fields are typed SessionConfig fields.  This keeps
    model/configuration identity explicit and prevents the child from
    inheriting a task worker's ambient cwd or global model registry.
    """
    from vibecomfy.runtime.session import SessionConfig

    metadata = getattr(bundle.workflow, "metadata", {})
    configured = metadata.get("comfy_configuration", {})
    if not isinstance(configured, Mapping):
        raise ProductionEngineError("workflow comfy_configuration must be an object")
    host_owned_keys = {
        "base_directory",
        "extra_model_paths_config",
        "runtime_root",
        "cwd",
        "port",
        "server_url",
        "endpoint",
        "output_directory",
        "input_directory",
        "temp_directory",
        "server_log_path",
        "models_root",
        "model_root",
        "warm_policy",
        "download",
        "download_models",
        "ensure_models",
        "install_nodes",
        "custom_nodes",
        "custom_nodes_path",
        "quiet_schema_degradation",
        "schema_warn_only",
        "strict_drift",
    }
    overridden = sorted(set(configured).intersection(host_owned_keys))
    if overridden:
        raise ProductionEngineError(
            "workflow comfy_configuration attempts to override host-owned keys: "
            + ", ".join(overridden)
        )
    values = dict(configured)
    values.update(
        {
            "base_directory": str(comfy_root.resolve()),
            "extra_model_paths_config": [
                str((comfy_root / "extra_model_paths.yaml").resolve())
            ],
            "disable_known_models": True,
            "runtime_root": str((destination / ".vibecomfy-runtime").resolve()),
            "cwd": str(comfy_root.resolve()),
            "input_directory": str((destination / "engine-input").resolve()),
            "port": None,
            "warm_policy": "never",
            "quiet_schema_degradation": False,
            "strict_drift": True,
        }
    )
    config = SessionConfig.from_dict(values)
    config.extra["output_directory"] = str(
        (destination / "engine-output").resolve()
    )
    config.extra["task_id"] = task_identity
    if attempt_identity is not None:
        config.extra["attempt_id"] = attempt_identity
    return config


def _verify_embedded_workflow_attestation(bundle: Any, profile: Any) -> None:
    """Match canonical workflow pins to the host's observed runtime facts."""
    from vibecomfy.runtime.dependencies import (
        compare_runtime,
        runtime_requirements_from_workflow,
    )

    workflow = bundle.workflow
    metadata = getattr(workflow, "metadata", {})
    metadata = metadata if isinstance(metadata, Mapping) else {}
    declared = runtime_requirements_from_workflow(workflow)
    requirements = declared.to_dict() if declared is not None else {}
    packs = metadata.get("custom_node_packs", {})
    if not isinstance(packs, Mapping):
        raise ProductionEngineError("workflow custom_node_packs must be an object")
    custom_nodes = list(requirements.get("custom_nodes", ()))
    for name, row in packs.items():
        if not isinstance(row, Mapping):
            raise ProductionEngineError(f"workflow custom-node pack {name!r} is invalid")
        exact = {key: row[key] for key in ("commit", "class_schema_sha256", "schema_hash") if row.get(key)}
        if exact:
            custom_nodes.append({"name": name, **exact})
    if custom_nodes:
        requirements["custom_nodes"] = custom_nodes
    assets = metadata.get("model_assets", ())
    if not isinstance(assets, (list, tuple)):
        raise ProductionEngineError("workflow model_assets must be an array")
    models = list(requirements.get("models", ()))
    workflow_models = getattr(getattr(workflow, "requirements", None), "models", ())
    models.extend(row for row in workflow_models if isinstance(row, Mapping))
    models.extend(row for row in assets if isinstance(row, Mapping) and row.get("sha256"))
    if models:
        requirements["models"] = models
    if not requirements:
        return

    target = profile.get("runtime_attestation") if isinstance(profile, Mapping) else None
    if not isinstance(target, Mapping):
        raise ProductionEngineError("embedded workflow requires runtime dependency attestation")
    candidate = profile.get("comfyui_candidate")
    revision = candidate.get("revision") if isinstance(candidate, Mapping) else None
    if revision and target.get("comfy_commit") != revision:
        raise ProductionEngineError("runtime attestation Comfy commit disagrees with verified Comfy tree")
    report = compare_runtime(requirements, target=target)
    failures = [
        str(check["path"])
        for check in report["checks"]
        if check["status"] != "matching"
    ]
    observed_nodes = target.get("custom_nodes")
    for row in custom_nodes:
        name = row.get("name") or row.get("slug")
        observed = observed_nodes.get(name) if isinstance(observed_nodes, Mapping) else None
        for key in ("class_schema_sha256", "schema_hash"):
            if row.get(key) and (not isinstance(observed, Mapping) or observed.get(key) != row[key]):
                failures.append(f"custom_nodes.{name}.{key}")
    if failures:
        raise ProductionEngineError(
            "embedded workflow runtime attestation is missing or mismatched: "
            + ", ".join(sorted(set(failures)))
        )


@contextmanager
def _checkout_cancellation(control: Any):
    cancelled = False
    previous: dict[signal.Signals, Any] = {}

    def cancel(signum: int, _frame: Any) -> None:
        nonlocal cancelled
        cancelled = True
        control.cancel()
        raise SystemExit(128 + signum)

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.getsignal(signum)
        signal.signal(signum, cancel)
    try:
        yield lambda: cancelled
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _result_from_runtime_result(
    result: Any,
    outputs: tuple[Path, ...],
) -> ProductionRunResult:
    raw_path = getattr(result, "managed_generation_result_path", None)
    result_path = Path(raw_path).expanduser().resolve() if raw_path else None
    payload: dict[str, Any] | None = None
    if result_path is not None:
        if not result_path.is_file():
            raise ProductionEngineError(
                f"VibeComfy declared a managed-generation result that is missing: {result_path}"
            )
        try:
            decoded = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProductionEngineError(
                f"VibeComfy managed-generation result is unreadable: {result_path}"
            ) from exc
        if not isinstance(decoded, dict):
            raise ProductionEngineError("VibeComfy managed-generation result must be an object")
        payload = decoded
    return ProductionRunResult(
        outputs=outputs,
        managed_generation_result_path=result_path,
        managed_generation_result=payload,
        producer_run_id=(str(payload["producer_run_id"]) if payload and payload.get("producer_run_id") else None),
        attempt_id=(str(payload["attempt_id"]) if payload and payload.get("attempt_id") else None),
    )


def _run_profile_result(
    resolved: Any,
    profile_id: str,
    hc03_profile: Any,
    *,
    model_id: str,
    template_id: str,
    task_identity: str,
    destination: Path,
    attempt_identity: str | None = None,
    run_inputs: Mapping[str, Any] | None = None,
) -> ProductionRunResult:
    if profile_id == "pip_embedded":
        comfy_root = _bootstrap_embedded_comfy_client(hc03_profile)
        from vibecomfy.runtime.run import run_embedded_sync

        if run_inputs is None:
            # Keep the lightweight test doubles and older internal callers on
            # the zero-argument seam; real task inputs take the approval path
            # below and are recorded in the detached projection.
            record, bundle = _canonical_bundle(resolved)
        else:
            record, bundle = _canonical_bundle(resolved, run_inputs=run_inputs)
        _verify_embedded_workflow_attestation(bundle, hc03_profile)
        previous_warm = os.environ.get("VIBECOMFY_WARM")
        previous_warn_only = os.environ.get("VIBECOMFY_SCHEMA_WARN_ONLY")
        previous_configuration = os.environ.get("VIBECOMFY_COMFY_CONFIGURATION")
        previous_comfyui_path = os.environ.get("COMFYUI_PATH")
        previous_attention = os.environ.get("VIBECOMFY_ATTENTION_PROFILE")
        previous_reigh_attention = os.environ.get("REIGH_VIBECOMFY_ATTENTION_PROFILE")
        os.environ["VIBECOMFY_WARM"] = "never"
        os.environ["VIBECOMFY_SCHEMA_WARN_ONLY"] = "0"
        # VibeComfy's environment layer otherwise has precedence over the
        # typed SessionConfig.  Pin the environment layer to the empty
        # object and the already-selected Comfy tree for this invocation.
        os.environ["VIBECOMFY_COMFY_CONFIGURATION"] = "{}"
        os.environ["COMFYUI_PATH"] = str(comfy_root.resolve())
        os.environ.pop("VIBECOMFY_ATTENTION_PROFILE", None)
        os.environ.pop("REIGH_VIBECOMFY_ATTENTION_PROFILE", None)
        try:
            result = run_embedded_sync(
                record,
                bundle,
                config=_embedded_session_config(
                    bundle,
                    destination,
                    comfy_root,
                    task_identity=task_identity,
                    attempt_identity=attempt_identity,
                ),
            )
        finally:
            if previous_warm is None:
                os.environ.pop("VIBECOMFY_WARM", None)
            else:
                os.environ["VIBECOMFY_WARM"] = previous_warm
            if previous_warn_only is None:
                os.environ.pop("VIBECOMFY_SCHEMA_WARN_ONLY", None)
            else:
                os.environ["VIBECOMFY_SCHEMA_WARN_ONLY"] = previous_warn_only
            if previous_configuration is None:
                os.environ.pop("VIBECOMFY_COMFY_CONFIGURATION", None)
            else:
                os.environ["VIBECOMFY_COMFY_CONFIGURATION"] = previous_configuration
            if previous_comfyui_path is None:
                os.environ.pop("COMFYUI_PATH", None)
            else:
                os.environ["COMFYUI_PATH"] = previous_comfyui_path
            if previous_attention is None:
                os.environ.pop("VIBECOMFY_ATTENTION_PROFILE", None)
            else:
                os.environ["VIBECOMFY_ATTENTION_PROFILE"] = previous_attention
            if previous_reigh_attention is None:
                os.environ.pop("REIGH_VIBECOMFY_ATTENTION_PROFILE", None)
            else:
                os.environ["REIGH_VIBECOMFY_ATTENTION_PROFILE"] = previous_reigh_attention
        raw_outputs = getattr(result, "outputs", None)
        if not isinstance(raw_outputs, (list, tuple)) or not raw_outputs:
            raise ProductionEngineError("VibeComfy produced no output artifacts")
        outputs: list[Path] = []
        for raw in raw_outputs:
            outputs.append(Path(raw).resolve(strict=True))
        return _result_from_runtime_result(result, tuple(outputs))
    if profile_id == "t9_cpu_stub":
        raise ProductionEngineError(
            "T9 deterministic substitute was not active at the model boundary; refusing real model execution"
        )

    if not isinstance(hc03_profile, Mapping):
        raise ProductionEngineError("checkout_server lacks its verified HC-03 profile")
    from astrid.core.generation.backends.vibecomfy import CheckoutServerAdapter

    workflow_comfyui_version = _workflow_comfyui_version_requirement(resolved)
    profile_comfyui_version = _profile_comfyui_version_requirement(hc03_profile)
    if (
        workflow_comfyui_version is not None
        and profile_comfyui_version is not None
        and workflow_comfyui_version != profile_comfyui_version
    ):
        raise ProductionEngineError(
            "workflow and worker profile ComfyUI version contracts disagree: "
            f"workflow={workflow_comfyui_version!r} profile={profile_comfyui_version!r}"
        )
    adapter = CheckoutServerAdapter.from_host_session(
        hc03_profile=hc03_profile,
        model_id=model_id,
        template_id=template_id,
        invocation_identity=task_identity,
        expected_comfyui_version=workflow_comfyui_version or profile_comfyui_version,
    )
    with _checkout_cancellation(adapter) as was_cancelled:
        try:
            outputs = tuple(
                adapter.run_compiled_workflow(
                    resolved,
                    destination,
                    task_identity=task_identity,
                    attempt_identity=attempt_identity,
                    run_inputs=run_inputs,
                )
            )
            return _result_from_runtime_result(
                getattr(adapter, "_last_run_result", None), outputs
            )
        except BaseException:
            if not was_cancelled():
                adapter.release(reason="failed")
            raise


def _run_profile(
    resolved: Any,
    profile_id: str,
    hc03_profile: Any,
    *,
    model_id: str,
    template_id: str,
    task_identity: str,
    destination: Path,
    attempt_identity: str | None = None,
    run_inputs: Mapping[str, Any] | None = None,
) -> tuple[Path, ...]:
    """Compatibility projection for callers that only need output paths."""
    global _LAST_PRODUCTION_RESULT
    _LAST_PRODUCTION_RESULT = _run_profile_result(
        resolved,
        profile_id,
        hc03_profile,
        model_id=model_id,
        template_id=template_id,
        task_identity=task_identity,
        destination=destination,
        attempt_identity=attempt_identity,
        run_inputs=run_inputs,
    )
    return _LAST_PRODUCTION_RESULT.outputs


def run_workflow_path(
    workflow_path: str | Path,
    destination: str | Path,
    *,
    task_identity: str,
    profile_id: str = "pip_embedded",
    model_id: str = "vibecomfy",
    template_id: str = "vibecomfy.run",
    hc03_profile: Any = None,
    expected_execution_identity: str | None = None,
    attempt_identity: str | None = None,
    workflow_input_bindings: Mapping[str, Any] | None = None,
) -> tuple[Path, ...]:
    """Run a file workflow through the reviewed production-engine path.

    The registered ``vibecomfy.run`` executor uses this adapter instead of
    importing VibeComfy's low-level runner directly.  Checkout-server callers
    must supply the host-issued HC-03 profile; the default embedded profile is
    intentionally the only implicit profile.
    """
    if not isinstance(task_identity, str) or not task_identity.strip():
        raise ProductionEngineError("production engine task_identity is required")
    destination_path = Path(destination).expanduser().resolve()
    destination_path.mkdir(parents=True, exist_ok=True)
    loaded = load_workflow_path(
        workflow_path,
        destination_path,
        model_id=model_id,
        template_id=template_id,
    )
    if expected_execution_identity is not None:
        actual_identity = loaded_workflow_execution_identity(loaded, hc03_profile)
        if actual_identity != expected_execution_identity:
            raise ProductionEngineError("workflow execution identity changed before launch")
    run_inputs = _validate_workflow_input_bindings(
        loaded.resolved, workflow_input_bindings
    )
    global _LAST_PRODUCTION_RESULT
    _LAST_PRODUCTION_RESULT = None
    profile_kwargs: dict[str, Any] = {}
    if attempt_identity is not None:
        profile_kwargs["attempt_identity"] = attempt_identity
    outputs = _run_profile(
        loaded.resolved,
        profile_id,
        hc03_profile,
        model_id=loaded.model_id,
        template_id=loaded.template_id,
        task_identity=task_identity,
        destination=destination_path,
        **profile_kwargs,
        run_inputs=run_inputs,
    )
    return outputs


def run_workflow_result_path(
    workflow_path: str | Path,
    destination: str | Path,
    *,
    task_identity: str,
    profile_id: str = "pip_embedded",
    model_id: str = "vibecomfy",
    template_id: str = "vibecomfy.run",
    hc03_profile: Any = None,
    expected_execution_identity: str | None = None,
    attempt_identity: str | None = None,
    workflow_input_bindings: Mapping[str, Any] | None = None,
) -> ProductionRunResult:
    """Run a workflow while retaining the producer result envelope.

    This projects the existing path API so callers and test doubles that still
    replace ``run_workflow_path`` continue to work.
    """
    global _LAST_PRODUCTION_RESULT
    _LAST_PRODUCTION_RESULT = None
    kwargs: dict[str, Any] = {
        "task_identity": task_identity,
        "profile_id": profile_id,
        "hc03_profile": hc03_profile,
        "expected_execution_identity": expected_execution_identity,
    }
    if model_id != "vibecomfy":
        kwargs["model_id"] = model_id
    if template_id != "vibecomfy.run":
        kwargs["template_id"] = template_id
    if attempt_identity is not None:
        kwargs["attempt_identity"] = attempt_identity
    if workflow_input_bindings is not None:
        kwargs["workflow_input_bindings"] = workflow_input_bindings
    outputs = run_workflow_path(
        workflow_path,
        destination,
        **kwargs,
    )
    if _LAST_PRODUCTION_RESULT is not None:
        return _LAST_PRODUCTION_RESULT
    return ProductionRunResult(outputs=tuple(Path(path) for path in outputs))


def execute(request_path: str | Path, out: str | Path, result_path: str | Path) -> None:
    request = json.loads(Path(request_path).read_text(encoding="utf-8"))
    if request.get("schema_version") != "astrid.vibecomfy.production-engine.v3":
        raise ProductionEngineError("unknown production engine request schema")
    workflow = request.get("workflow")
    references = request.get("references")
    profile_id = _profile_id(request.get("profile"))
    capability_id = request.get("capability_id")
    model_id = request.get("model_id")
    template_id = request.get("template_id")
    task_identity = request.get("task_identity")
    if not isinstance(workflow, Mapping) or not isinstance(references, Mapping):
        raise ProductionEngineError("production engine request lacks workflow/references")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in (capability_id, model_id, template_id, task_identity)
    ):
        raise ProductionEngineError("production engine request lacks typed execution identity")
    destination = Path(out).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    resolved = _load_workflow(workflow, references, destination)

    raw_outputs = _run_profile(
        resolved,
        profile_id,
        request.get("hc03_profile"),
        model_id=model_id,
        template_id=template_id,
        task_identity=task_identity,
        destination=destination,
        run_inputs=request.get("run_inputs"),
    )
    outputs: list[str] = []
    for index, raw in enumerate(raw_outputs):
        candidate = Path(raw)
        if profile_id == "checkout_server" and candidate.is_symlink():
            raise ProductionEngineError(
                "checkout_server output is not a private staged artifact"
            )
        source = candidate.resolve(strict=True)
        if profile_id == "checkout_server":
            try:
                source.relative_to(destination)
            except ValueError as exc:
                raise ProductionEngineError(
                    "checkout_server output escaped canonical adapter custody"
                ) from exc
            if not source.is_file() or source.stat().st_nlink != 1:
                raise ProductionEngineError(
                    "checkout_server output is not a private staged artifact"
                )
            target = source
        else:
            suffix = source.suffix or ".bin"
            target = destination / f"engine-output-{index:04d}{suffix}"
            if source != target:
                shutil.copyfile(source, target)
        outputs.append(str(target))
    Path(result_path).write_text(
        json.dumps({"outputs": outputs}, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--result", required=True)
    args = parser.parse_args(argv)
    execute(args.request, args.out, args.result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
