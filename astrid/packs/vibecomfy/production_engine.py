"""Pinned-interpreter bridge from typed Astrid workflows to VibeComfy."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import shutil
import signal
import sys
from collections.abc import Mapping
from contextlib import contextmanager
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


def _bootstrap_embedded_comfy_client() -> Path:
    """Select and import the embedded-client ComfyUI tree for pip execution."""
    candidates: list[str | Path] = []
    configured = os.environ.get("COMFYUI_PATH")
    if configured:
        candidates.append(configured)
    candidates.extend(_EMBEDDED_COMFY_FALLBACKS)

    root: Path | None = None
    for raw in candidates:
        candidate = Path(raw).expanduser().resolve()
        if (candidate / _EMBEDDED_COMFY_CLIENT).is_file():
            root = candidate
            break
    if root is None:
        raise ProductionEngineError(
            "pip_embedded requires a ComfyUI tree containing "
            "comfy/client/embedded_comfy_client.py; set COMFYUI_PATH or install "
            "the embedded checkout at /root/b06-t04/comfyui-embedded"
        )

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


def load_workflow_path(
    workflow_path: str | Path,
    scratch: str | Path,
    *,
    model_id: str = "vibecomfy",
    template_id: str = "vibecomfy.run",
) -> tuple[Any, str, str]:
    """Load one canonical workflow and return its effective execution identity."""
    source = Path(workflow_path).expanduser().resolve(strict=True)
    try:
        raw_workflow = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionEngineError(f"workflow could not be read: {source}") from exc
    if not isinstance(raw_workflow, Mapping):
        raise ProductionEngineError("workflow must be a JSON object")
    resolved = _load_workflow(raw_workflow, {}, Path(scratch).resolve())
    metadata = getattr(resolved, "metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    effective_template_id = str(metadata.get("ready_template") or template_id)
    effective_model_id = str(metadata.get("model_id") or model_id)
    if not effective_template_id.strip():
        raise ProductionEngineError("canonical workflow has no ready-template identity")
    return resolved, effective_model_id, effective_template_id


def execution_identity_digest(
    model_id: str,
    template_id: str,
    *,
    model_digest: str | None = None,
) -> str:
    """Return the shared host/child identity for one canonical execution."""
    return hashlib.sha256(
        json.dumps(
            {
                "model_id": model_id,
                "template_id": template_id,
                "model_digest": model_digest,
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


def _canonical_bundle(resolved: Any) -> tuple[Any, Any]:
    """Return the only workflow form admitted by the selected Vibe runtime."""
    try:
        from vibecomfy.workflow import VibeWorkflow
        from vibecomfy.workflow_bundle import load_bundle
    except ImportError as exc:  # pragma: no cover - dependency boundary
        raise ProductionEngineError(
            "VibeComfy canonical workflow bundle support is unavailable"
        ) from exc
    if not isinstance(resolved, VibeWorkflow):
        raise ProductionEngineError(
            "production engine requires a VibeWorkflow from the canonical loader"
        )
    bundle = load_bundle(resolved)
    bundle.require_canonical_authority("production engine execution")
    return bundle.compile(), bundle


def _embedded_session_config(bundle: Any, destination: Path, comfy_root: Path) -> Any:
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
            "port": None,
            "warm_policy": "never",
            "quiet_schema_degradation": False,
        }
    )
    config = SessionConfig.from_dict(values)
    config.extra["output_directory"] = str(
        (destination / "engine-output").resolve()
    )
    return config


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


def _run_profile(
    resolved: Any,
    profile_id: str,
    hc03_profile: Any,
    *,
    model_id: str,
    template_id: str,
    task_identity: str,
    destination: Path,
) -> tuple[Path, ...]:
    if profile_id == "pip_embedded":
        comfy_root = _bootstrap_embedded_comfy_client()
        from vibecomfy.runtime.run import run_embedded_sync

        record, bundle = _canonical_bundle(resolved)
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
                config=_embedded_session_config(bundle, destination, comfy_root),
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
        return tuple(outputs)

    if not isinstance(hc03_profile, Mapping):
        raise ProductionEngineError("checkout_server lacks its verified HC-03 profile")
    from astrid.core.generation.backends.vibecomfy import CheckoutServerAdapter

    adapter = CheckoutServerAdapter.from_host_session(
        hc03_profile=hc03_profile,
        model_id=model_id,
        template_id=template_id,
        invocation_identity=task_identity,
    )
    with _checkout_cancellation(adapter) as was_cancelled:
        try:
            return tuple(adapter.run_compiled_workflow(resolved, destination))
        except BaseException:
            if not was_cancelled():
                adapter.release(reason="failed")
            raise


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
    resolved, effective_model_id, effective_template_id = load_workflow_path(
        workflow_path,
        destination_path,
        model_id=model_id,
        template_id=template_id,
    )
    if expected_execution_identity is not None:
        model_digest = None
        if isinstance(hc03_profile, Mapping):
            facts = hc03_profile.get("verified_facts")
            exact = facts.get("exact") if isinstance(facts, Mapping) else None
            model_digest = exact.get("model_digest") if isinstance(exact, Mapping) else None
        actual_identity = execution_identity_digest(
            effective_model_id,
            effective_template_id,
            model_digest=model_digest,
        )
        if actual_identity != expected_execution_identity:
            raise ProductionEngineError("workflow execution identity changed before launch")
    return _run_profile(
        resolved,
        profile_id,
        hc03_profile,
        model_id=effective_model_id,
        template_id=effective_template_id,
        task_identity=task_identity,
        destination=destination_path,
    )


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
