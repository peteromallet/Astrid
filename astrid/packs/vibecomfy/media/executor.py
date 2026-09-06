"""Direct Vibe media executor boundary.

The generic host/runtime remains the lifecycle authority.  This executor only
checks the compiled identity and hands one immutable workflow to the selected
profile's already-admitted runner.  It never selects a fallback profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .compiler import (
    CharacterAnimationRequest,
    CompiledVibeMedia,
    MediaCompileError,
    VideoEnhanceRequest,
    WanI2VRequest,
    WanT2IRequest,
    compile_character_animation,
    compile_video_enhance,
    compile_wan_2_2_i2v,
    compile_wan_2_2_t2i,
)


class MediaExecutionError(RuntimeError):
    """Raised when profile identity or direct execution evidence is invalid."""


class DirectWorkflowRunner(Protocol):
    def __call__(
        self,
        workflow: Mapping[str, Any],
        *,
        capability_id: str,
        model_identity: str,
        profile_id: str,
        task_identity: str,
    ) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class MediaExecutionResult:
    capability_id: str
    model_identity: str
    profile_id: str
    task_identity: str
    output_transport: str
    outputs: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "model_identity": self.model_identity,
            "profile_id": self.profile_id,
            "task_identity": self.task_identity,
            "output_transport": self.output_transport,
            "outputs": dict(self.outputs),
        }


class DirectVibeMediaExecutor:
    """Execute one typed media request through one explicit Vibe profile."""

    def __init__(self, profile_id: str, runner: DirectWorkflowRunner) -> None:
        from .compiler import profile_semantics

        self.profile = profile_semantics(profile_id)
        self._runner = runner

    def _execute(
        self,
        compiled: CompiledVibeMedia,
        *,
        runtime_context: Mapping[str, Any],
    ) -> MediaExecutionResult:
        try:
            compiled.verify_integrity()
        except MediaCompileError as exc:
            raise MediaExecutionError(str(exc)) from exc
        if compiled.profile.profile_id != self.profile.profile_id:
            raise MediaExecutionError(
                f"compiled profile {compiled.profile.profile_id!r} does not match executor profile {self.profile.profile_id!r}"
            )
        if not isinstance(runtime_context, Mapping):
            raise MediaExecutionError("runtime_context must be a mapping")
        missing = [
            field
            for field in self.profile.required_runtime_fields
            if field not in runtime_context or runtime_context[field] in (None, "")
        ]
        if missing:
            raise MediaExecutionError(
                f"{self.profile.profile_id} runtime identity is incomplete: {', '.join(missing)}"
            )
        task_identity = runtime_context["task_identity"]
        if not isinstance(task_identity, str) or not task_identity.strip():
            raise MediaExecutionError("task_identity must be a non-empty string")
        try:
            outputs = self._runner(
                compiled.workflow,
                capability_id=compiled.capability_id,
                model_identity=compiled.model_identity,
                profile_id=self.profile.profile_id,
                task_identity=task_identity,
            )
        except Exception as exc:
            raise MediaExecutionError(
                f"{compiled.capability_id} direct execution failed"
            ) from exc
        if not isinstance(outputs, Mapping):
            raise MediaExecutionError("direct media runner returned a non-object result")
        return MediaExecutionResult(
            capability_id=compiled.capability_id,
            model_identity=compiled.model_identity,
            profile_id=self.profile.profile_id,
            task_identity=task_identity,
            output_transport=self.profile.output_transport,
            outputs=outputs,
        )

    def execute_wan_2_2_t2i(
        self, request: WanT2IRequest, *, task_identity: str, runtime_context: Mapping[str, Any]
    ) -> MediaExecutionResult:
        return self._execute(
            compile_wan_2_2_t2i(request, profile=self.profile.profile_id),
            runtime_context={**runtime_context, "task_identity": task_identity},
        )

    def execute_wan_2_2_i2v(
        self, request: WanI2VRequest, *, task_identity: str, runtime_context: Mapping[str, Any]
    ) -> MediaExecutionResult:
        return self._execute(
            compile_wan_2_2_i2v(request, profile=self.profile.profile_id),
            runtime_context={**runtime_context, "task_identity": task_identity},
        )

    def execute_video_enhance(
        self, request: VideoEnhanceRequest, *, task_identity: str, runtime_context: Mapping[str, Any]
    ) -> MediaExecutionResult:
        return self._execute(
            compile_video_enhance(request, profile=self.profile.profile_id),
            runtime_context={**runtime_context, "task_identity": task_identity},
        )

    def execute_character_animation(
        self,
        request: CharacterAnimationRequest,
        *,
        task_identity: str,
        runtime_context: Mapping[str, Any],
    ) -> MediaExecutionResult:
        return self._execute(
            compile_character_animation(request, profile=self.profile.profile_id),
            runtime_context={**runtime_context, "task_identity": task_identity},
        )


__all__ = [
    "DirectVibeMediaExecutor",
    "DirectWorkflowRunner",
    "MediaExecutionError",
    "MediaExecutionResult",
]
