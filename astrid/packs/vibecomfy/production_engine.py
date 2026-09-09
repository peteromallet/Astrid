"""Pinned-interpreter bridge from typed Astrid workflows to VibeComfy."""

from __future__ import annotations

import argparse
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
                if "no registered public input" not in str(exc):
                    raise
        return resolved

    from vibecomfy.cli_loader import load_workflow_any

    raw_path = scratch / "compiled-workflow.json"
    raw_path.write_text(
        json.dumps(_replace_references(dict(workflow), references), sort_keys=True),
        encoding="utf-8",
    )
    return load_workflow_any(str(raw_path))


def _profile_id(value: Any) -> str:
    if not isinstance(value, Mapping):
        raise ProductionEngineError("production engine request lacks an execution profile")
    profile_id = value.get("name")
    if not isinstance(profile_id, str) or profile_id not in _PROFILE_CONFIGS:
        raise ProductionEngineError("production engine request has an unsupported execution profile")
    if dict(value) != _PROFILE_CONFIGS[profile_id]:
        raise ProductionEngineError("production engine profile identity does not match local semantics")
    return profile_id


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
        _bootstrap_embedded_comfy_client()
        from vibecomfy.runtime.run import run_embedded_sync

        result = run_embedded_sync(resolved)
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
