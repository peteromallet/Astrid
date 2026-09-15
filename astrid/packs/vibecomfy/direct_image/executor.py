"""Typed direct image executor for the two explicit VibeComfy profiles.

The executor only owns pack semantics.  Runtime claim, attempt fencing, output
upload, and settlement remain GenericPackHost responsibilities.  An injected
engine object must expose ``run(workflow, task_identity=..., out_dir=...)``;
production adapters bind that method to the already-owned Vibe profile.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .compiler import (
    CANONICAL_CAPABILITIES,
    CompiledImageRequest,
    ImageCompileError,
    compile_image_request,
)


class ImageExecutionError(RuntimeError):
    """A typed image execution failed closed before output publication."""


class ImageEngine(Protocol):
    def run(self, workflow: Any, *, task_identity: str | None, out_dir: Path) -> Any:
        """Run a compiled workflow using an already-bound Vibe profile."""


@dataclass(frozen=True, slots=True)
class ImageResult:
    capability_id: str
    model_id: str
    mode: str
    profile: str
    execution_digest: str
    template_digest: str
    outputs: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "direct-image.result.v1",
            "capability_id": self.capability_id,
            "model_id": self.model_id,
            "mode": self.mode,
            "profile": self.profile,
            "execution_digest": self.execution_digest,
            "template_digest": self.template_digest,
            "outputs": list(self.outputs),
        }


def _template_module(compiled: CompiledImageRequest) -> Any:
    expected = CANONICAL_CAPABILITIES[compiled.capability_id].template_module
    if compiled.template_module != expected:
        raise ImageExecutionError("compiled template identity does not match capability")
    try:
        return importlib.import_module(expected)
    except (ImportError, ModuleNotFoundError) as exc:
        raise ImageExecutionError(f"typed template is unavailable: {expected}") from exc


def _attest_template(module: Any, template_id: str) -> str:
    source_file = getattr(module, "__file__", None)
    if not isinstance(source_file, str) or not source_file:
        raise ImageExecutionError("typed template has no source file")
    path = Path(source_file).resolve(strict=True)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as exc:
        raise ImageExecutionError("typed template source is not readable Python") from exc
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
        raise ImageExecutionError("production typed templates must be pure Python")
    if not callable(getattr(module, "build", None)):
        raise ImageExecutionError(f"typed template {template_id!r} has no build()")
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _bindings(compiled: CompiledImageRequest) -> dict[str, Any]:
    values = dict(compiled.params)
    values.update({"model_id": compiled.model_id, "mode": compiled.mode})
    return values


def _engine_outputs(value: Any) -> list[Path]:
    if isinstance(value, dict):
        raw = value.get("outputs")
    else:
        raw = getattr(value, "outputs", None)
    if not isinstance(raw, (list, tuple)):
        raise ImageExecutionError("Vibe engine returned no declared outputs")
    result: list[Path] = []
    for item in raw:
        if not isinstance(item, (str, Path)):
            raise ImageExecutionError("Vibe engine returned an invalid output path")
        result.append(Path(item))
    return result


class DirectImageExecutor:
    """Compile and execute one explicitly selected direct image capability."""

    def compile(
        self,
        capability_id: str,
        params: dict[str, Any],
        *,
        profile: str,
        task_identity: str | None = None,
    ) -> CompiledImageRequest:
        try:
            return compile_image_request(
                capability_id,
                params,
                profile=profile,
                task_identity=task_identity,
            )
        except ImageCompileError as exc:
            raise ImageExecutionError(str(exc)) from exc

    def execute(
        self,
        capability_id: str,
        params: dict[str, Any],
        *,
        profile: str,
        engine: ImageEngine,
        out_dir: str | Path,
        task_identity: str | None = None,
    ) -> ImageResult:
        compiled = self.compile(capability_id, params, profile=profile, task_identity=task_identity)
        destination = Path(out_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        module = _template_module(compiled)
        template_digest = _attest_template(module, compiled.template_id)
        try:
            workflow = module.build(template_id=compiled.template_id, bindings=_bindings(compiled))
        except (TypeError, ValueError) as exc:
            raise ImageExecutionError(f"typed template binding failed: {exc}") from exc
        try:
            engine_result = engine.run(workflow, task_identity=compiled.task_identity, out_dir=destination)
        except Exception as exc:
            raise ImageExecutionError("Vibe profile execution failed") from exc
        outputs: list[str] = []
        for candidate in _engine_outputs(engine_result):
            try:
                resolved = candidate.expanduser().resolve(strict=True)
                resolved.relative_to(destination)
            except (OSError, ValueError) as exc:
                raise ImageExecutionError("engine output escapes the attempt output root") from exc
            if resolved.is_symlink() or not resolved.is_file():
                raise ImageExecutionError("engine output must be a regular file")
            outputs.append(resolved.relative_to(destination).as_posix())
        if not outputs:
            raise ImageExecutionError("Vibe profile produced no image output")
        return ImageResult(
            capability_id=compiled.capability_id,
            model_id=compiled.model_id,
            mode=compiled.mode,
            profile=compiled.profile.name,
            execution_digest=compiled.execution_digest,
            template_digest=template_digest,
            outputs=tuple(sorted(outputs)),
        )


__all__ = ["DirectImageExecutor", "ImageEngine", "ImageExecutionError", "ImageResult"]
