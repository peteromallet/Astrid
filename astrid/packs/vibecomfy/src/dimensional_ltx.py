"""Typed dimensional LTX first/last-frame request compilation.

This module is deliberately a small, closed contract.  The route table below is
its complete supported surface: a request can select only one of these six
semantic rows and can never provide a workflow, plugin, or template path.
Runtime/CAS object ids are carried through unchanged; local paths and runtime
readiness details are outside this contract.
"""

from __future__ import annotations

import re

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, Mapping, TypeAlias

CAPABILITY_ID = "vibecomfy.dimensional_ltx"
SCHEMA_VERSION = 1

FIRST_LAST_TEMPLATE_ID = "video/ltx2_3_runexx_first_last_frame"
ICLORA_TEMPLATE_ID = "video/ltx2_3_first_last_frame_travel_iclora_control"

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 576
DEFAULT_FRAMES = 81
DEFAULT_FPS = 24

SemanticFamily: TypeAlias = Literal["ltx_first_last", "ltx_iclora"]
ControlIdentity: TypeAlias = Literal[
    "ltx_control_pose",
    "ltx_control_depth",
    "ltx_control_canny",
    "ltx_control_cameraman",
]

SUPPORTED_ROUTE_KEYS: tuple[str, ...] = (
    "travel_segment__model-ltx2__guidance-none__continuity-first_last__profile-default",
    "travel_segment__model-ltx2_distilled__guidance-none__continuity-first_last__profile-default",
    "travel_segment__model-ltx2_distilled__guidance-ltx_control_pose__continuity-first_last__profile-default",
    "travel_segment__model-ltx2_distilled__guidance-ltx_control_depth__continuity-first_last__profile-default",
    "travel_segment__model-ltx2_distilled__guidance-ltx_control_canny__continuity-first_last__profile-default",
    "travel_segment__model-ltx2_distilled__guidance-ltx_control_cameraman__continuity-first_last__profile-default",
)

NEGATIVE_ROUTE_KEYS: tuple[str, ...] = (
    "travel_segment__model-ltx2_distilled__guidance-ltx_control_video__continuity-first_last__profile-default",
    "travel_segment__model-wan22_vace__guidance-uni3c__continuity-first_last__profile-default",
)

ALL_ROUTE_KEYS: tuple[str, ...] = SUPPORTED_ROUTE_KEYS + NEGATIVE_ROUTE_KEYS

_REQUEST_KEYS = frozenset(
    {
        "route_key",
        "prompt",
        "negative_prompt",
        "seed",
        "width",
        "height",
        "frames",
        "fps",
        "start_image_object_id",
        "end_image_object_id",
        "guide_object_id",
    }
)

_AUTHORIZED_OBJECT_ID_SCHEMES = frozenset({"cas", "sha256"})
_URI_SCHEME_RE = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):")
_ENDPOINT_RE = re.compile(
    r"^(?:(?:localhost|(?:\d{1,3}\.){3}\d{1,3})|\[[0-9A-Fa-f:.]+\]|[0-9A-Fa-f:]+):\d+$",
    re.IGNORECASE,
)
_RELATIVE_FILENAME_RE = re.compile(r"^[^./\\]+\.[^./\\]+$")


@dataclass(frozen=True, slots=True)
class RouteSpec:
    """The immutable typed facts needed to compile one supported route."""

    route_key: str
    semantic_family: SemanticFamily
    model_id: Literal["ltx2", "ltx2_distilled"]
    template_id: str
    control_identity: ControlIdentity | None
    requires_guide: bool


# This is an allowlist of route facts, not a discoverable or mutable registry.
_SUPPORTED_ROUTES: Mapping[str, RouteSpec] = MappingProxyType(
    {
        SUPPORTED_ROUTE_KEYS[0]: RouteSpec(
            route_key=SUPPORTED_ROUTE_KEYS[0],
            semantic_family="ltx_first_last",
            model_id="ltx2",
            template_id=FIRST_LAST_TEMPLATE_ID,
            control_identity=None,
            requires_guide=False,
        ),
        SUPPORTED_ROUTE_KEYS[1]: RouteSpec(
            route_key=SUPPORTED_ROUTE_KEYS[1],
            semantic_family="ltx_first_last",
            model_id="ltx2_distilled",
            template_id=FIRST_LAST_TEMPLATE_ID,
            control_identity=None,
            requires_guide=False,
        ),
        SUPPORTED_ROUTE_KEYS[2]: RouteSpec(
            route_key=SUPPORTED_ROUTE_KEYS[2],
            semantic_family="ltx_iclora",
            model_id="ltx2_distilled",
            template_id=ICLORA_TEMPLATE_ID,
            control_identity="ltx_control_pose",
            requires_guide=True,
        ),
        SUPPORTED_ROUTE_KEYS[3]: RouteSpec(
            route_key=SUPPORTED_ROUTE_KEYS[3],
            semantic_family="ltx_iclora",
            model_id="ltx2_distilled",
            template_id=ICLORA_TEMPLATE_ID,
            control_identity="ltx_control_depth",
            requires_guide=True,
        ),
        SUPPORTED_ROUTE_KEYS[4]: RouteSpec(
            route_key=SUPPORTED_ROUTE_KEYS[4],
            semantic_family="ltx_iclora",
            model_id="ltx2_distilled",
            template_id=ICLORA_TEMPLATE_ID,
            control_identity="ltx_control_canny",
            requires_guide=True,
        ),
        SUPPORTED_ROUTE_KEYS[5]: RouteSpec(
            route_key=SUPPORTED_ROUTE_KEYS[5],
            semantic_family="ltx_iclora",
            model_id="ltx2_distilled",
            template_id=ICLORA_TEMPLATE_ID,
            control_identity="ltx_control_cameraman",
            requires_guide=True,
        ),
    }
)

_NEGATIVE_REASONS: Mapping[str, str] = MappingProxyType(
    {
        NEGATIVE_ROUTE_KEYS[0]: "ltx_raw_control_video is unsupported pending a typed raw-guide contract",
        NEGATIVE_ROUTE_KEYS[1]: "wan_uni3c has no complete typed template and input contract",
    }
)


@dataclass(frozen=True, slots=True)
class LtxRequest:
    """Typed producer input; object ids refer to already-authorized CAS objects."""

    route_key: str
    prompt: str
    start_image_object_id: str
    end_image_object_id: str
    negative_prompt: str = ""
    seed: int = 0
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    frames: int = DEFAULT_FRAMES
    fps: int = DEFAULT_FPS
    guide_object_id: str | None = None


@dataclass(frozen=True, slots=True)
class CasBinding:
    """A typed reference to one Runtime/CAS object, never a filesystem path."""

    kind: Literal["image", "video"]
    object_id: str

    def __getitem__(self, key: str) -> str:
        if key == "kind":
            return self.kind
        if key == "object_id":
            return self.object_id
        raise KeyError(key)

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "object_id": self.object_id}


@dataclass(frozen=True, slots=True)
class CompiledLtxTask:
    """Deterministic, admission-ready typed task payload."""

    route_key: str
    semantic_family: SemanticFamily
    model_id: Literal["ltx2", "ltx2_distilled"]
    template_id: str
    input_object_ids: tuple[str, ...]
    bindings: Mapping[str, CasBinding]
    control_identity: ControlIdentity | None
    prompt: str
    negative_prompt: str
    seed: int
    width: int
    height: int
    frames: int
    fps: int

    @property
    def capability_id(self) -> str:
        return CAPABILITY_ID

    def as_dict(self) -> dict[str, Any]:
        """Return the stable wire-shaped payload without local execution data."""
        return {
            "schema_version": SCHEMA_VERSION,
            "capability_id": CAPABILITY_ID,
            "route_key": self.route_key,
            "semantic_family": self.semantic_family,
            "model_id": self.model_id,
            "template_id": self.template_id,
            "input_object_ids": list(self.input_object_ids),
            "bindings": {name: binding.as_dict() for name, binding in self.bindings.items()},
            "control_identity": self.control_identity,
            "parameters": {
                "prompt": self.prompt,
                "negative_prompt": self.negative_prompt,
                "seed": self.seed,
                "width": self.width,
                "height": self.height,
                "frames": self.frames,
                "fps": self.fps,
            },
        }


@dataclass(frozen=True, slots=True)
class LtxRejection:
    """Typed deterministic reason for a request that cannot be admitted."""

    code: Literal[
        "invalid_request",
        "missing_required_cas_input",
        "unsupported_route",
        "unsupported_semantic_family",
    ]
    reason: str


@dataclass(frozen=True, slots=True)
class LtxCompilation:
    """Compiler result; rejected requests always have a null task and fallback."""

    task: CompiledLtxTask | None
    rejection: LtxRejection | None
    fallback_template_id: None = None

    @property
    def accepted(self) -> bool:
        return self.task is not None and self.rejection is None


def _reject(
    code: Literal[
        "invalid_request",
        "missing_required_cas_input",
        "unsupported_route",
        "unsupported_semantic_family",
    ],
    reason: str,
) -> LtxCompilation:
    return LtxCompilation(task=None, rejection=LtxRejection(code=code, reason=reason))


def _string(value: Any, *, field: str, non_empty: bool = True) -> str | LtxCompilation:
    if not isinstance(value, str) or (non_empty and not value.strip()):
        return _reject("invalid_request", f"{field} must be a non-empty string")
    return value


def _object_id(value: Any, *, field: str) -> str | LtxCompilation:
    if not isinstance(value, str) or not value.strip():
        return _reject("missing_required_cas_input", f"{field} must be an authorized CAS object id")

    candidate = value.strip()
    is_drive_path = len(candidate) >= 2 and candidate[0].isalpha() and candidate[1] == ":"
    scheme_match = _URI_SCHEME_RE.match(candidate)
    scheme = scheme_match.group("scheme").lower() if scheme_match else None
    is_path = (
        candidate.startswith(("/", "\\", "./", "../", "~/"))
        or "/" in candidate
        or "\\" in candidate
        or is_drive_path
        or bool(_RELATIVE_FILENAME_RE.fullmatch(candidate))
    )
    is_url_or_endpoint = (
        (scheme is not None and scheme not in _AUTHORIZED_OBJECT_ID_SCHEMES)
        or bool(_ENDPOINT_RE.fullmatch(candidate))
    )
    if is_path or is_url_or_endpoint:
        return _reject(
            "invalid_request",
            f"{field} must be a Runtime/CAS object id, not a path, URL, or endpoint",
        )
    return value


def _integer(value: Any, *, field: str, minimum: int) -> int | LtxCompilation:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return _reject("invalid_request", f"{field} must be an integer >= {minimum}")
    return value


def _coerce_request(request: object) -> LtxRequest | LtxCompilation:
    if isinstance(request, LtxRequest):
        values: Mapping[str, Any] = {
            "route_key": request.route_key,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
            "width": request.width,
            "height": request.height,
            "frames": request.frames,
            "fps": request.fps,
            "start_image_object_id": request.start_image_object_id,
            "end_image_object_id": request.end_image_object_id,
            "guide_object_id": request.guide_object_id,
        }
    elif isinstance(request, Mapping):
        keys = tuple(request)
        if any(not isinstance(key, str) for key in keys):
            return _reject("invalid_request", "request keys must be strings")
        unknown = sorted(set(keys) - _REQUEST_KEYS)
        if unknown:
            return _reject("invalid_request", "request does not accept keys: " + ", ".join(unknown))
        values = request
    else:
        return _reject("invalid_request", "request must be LtxRequest or a mapping")

    missing = [
        field
        for field in ("route_key", "prompt", "start_image_object_id", "end_image_object_id")
        if field not in values
    ]
    if missing:
        return _reject("invalid_request", "request is missing fields: " + ", ".join(missing))

    route_key = _string(values["route_key"], field="route_key")
    if isinstance(route_key, LtxCompilation):
        return route_key
    prompt = _string(values["prompt"], field="prompt")
    if isinstance(prompt, LtxCompilation):
        return prompt
    start_id = _object_id(values["start_image_object_id"], field="start_image_object_id")
    if isinstance(start_id, LtxCompilation):
        return start_id
    end_id = _object_id(values["end_image_object_id"], field="end_image_object_id")
    if isinstance(end_id, LtxCompilation):
        return end_id

    negative_prompt = _string(values.get("negative_prompt", ""), field="negative_prompt", non_empty=False)
    if isinstance(negative_prompt, LtxCompilation):
        return negative_prompt
    seed = _integer(values.get("seed", 0), field="seed", minimum=0)
    if isinstance(seed, LtxCompilation):
        return seed
    width = _integer(values.get("width", DEFAULT_WIDTH), field="width", minimum=1)
    if isinstance(width, LtxCompilation):
        return width
    height = _integer(values.get("height", DEFAULT_HEIGHT), field="height", minimum=1)
    if isinstance(height, LtxCompilation):
        return height
    frames = _integer(values.get("frames", DEFAULT_FRAMES), field="frames", minimum=1)
    if isinstance(frames, LtxCompilation):
        return frames
    fps = _integer(values.get("fps", DEFAULT_FPS), field="fps", minimum=1)
    if isinstance(fps, LtxCompilation):
        return fps

    guide_value = values.get("guide_object_id")
    if guide_value is not None:
        guide_id = _object_id(guide_value, field="guide_object_id")
        if isinstance(guide_id, LtxCompilation):
            return guide_id
    else:
        guide_id = None

    return LtxRequest(
        route_key=route_key,
        prompt=prompt,
        start_image_object_id=start_id,
        end_image_object_id=end_id,
        negative_prompt=negative_prompt,
        seed=seed,
        width=width,
        height=height,
        frames=frames,
        fps=fps,
        guide_object_id=guide_id,
    )


def compile_dimensional_ltx(request: object) -> LtxCompilation:
    """Compile one supported LTX route or fail closed before admission."""
    normalized = _coerce_request(request)
    if isinstance(normalized, LtxCompilation):
        return normalized

    spec = _SUPPORTED_ROUTES.get(normalized.route_key)
    if spec is None:
        if normalized.route_key in _NEGATIVE_REASONS:
            return _reject("unsupported_semantic_family", _NEGATIVE_REASONS[normalized.route_key])
        return _reject("unsupported_route", f"route is not in the LTX allowlist: {normalized.route_key}")

    if spec.requires_guide and normalized.guide_object_id is None:
        return _reject(
            "missing_required_cas_input",
            f"{spec.semantic_family} requires guide_object_id for {spec.control_identity}",
        )
    if not spec.requires_guide and normalized.guide_object_id is not None:
        return _reject(
            "invalid_request",
            f"{spec.semantic_family} does not accept guide_object_id",
        )

    bindings: dict[str, CasBinding] = {
        "start_image": CasBinding(kind="image", object_id=normalized.start_image_object_id),
        "end_image": CasBinding(kind="image", object_id=normalized.end_image_object_id),
    }
    input_object_ids = [normalized.start_image_object_id, normalized.end_image_object_id]
    if normalized.guide_object_id is not None:
        bindings["guide_video"] = CasBinding(kind="video", object_id=normalized.guide_object_id)
        input_object_ids.append(normalized.guide_object_id)

    return LtxCompilation(
        task=CompiledLtxTask(
            route_key=normalized.route_key,
            semantic_family=spec.semantic_family,
            model_id=spec.model_id,
            template_id=spec.template_id,
            input_object_ids=tuple(input_object_ids),
            bindings=MappingProxyType(bindings),
            control_identity=spec.control_identity,
            prompt=normalized.prompt,
            negative_prompt=normalized.negative_prompt,
            seed=normalized.seed,
            width=normalized.width,
            height=normalized.height,
            frames=normalized.frames,
            fps=normalized.fps,
        ),
        rejection=None,
    )


__all__ = [
    "ALL_ROUTE_KEYS",
    "CAPABILITY_ID",
    "CasBinding",
    "CompiledLtxTask",
    "FIRST_LAST_TEMPLATE_ID",
    "ICLORA_TEMPLATE_ID",
    "LtxCompilation",
    "LtxRejection",
    "LtxRequest",
    "NEGATIVE_ROUTE_KEYS",
    "SCHEMA_VERSION",
    "SUPPORTED_ROUTE_KEYS",
    "compile_dimensional_ltx",
]
