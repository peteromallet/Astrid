"""Typed, finite compiler for the supported Wan 2.2 dimensional routes.

This module is deliberately a small boundary: callers provide a semantic
request and ordered Runtime CAS object ids; the compiler selects one of two
allowlisted ready templates and emits only typed bindings.  It never resolves
paths, discovers plugins, or falls back to another route.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, Sequence, cast


class DimensionalVaceError(ValueError):
    """A dimensional request cannot be admitted by the finite contract."""


class UnsupportedDimensionalRoute(DimensionalVaceError):
    """The requested semantic combination is not one of the frozen routes."""


SemanticFamily = Literal[
    "wan_i2v_first_last",
    "wan_vace_travel",
    "wan_vace_individual",
    "wan_vace_join_bridge",
]
Operation = Literal["travel_segment", "individual_travel_segment", "join_clips_segment"]
Model = Literal["wan22_i2v", "wan22_vace"]
Guidance = Literal["none", "vace", "vace_flow", "vace_canny", "vace_depth", "vace_raw"]
Continuity = Literal["first_last", "video_source", "join_bridge"]
Profile = Literal["default"]

I2V_TEMPLATE_ID = "video/wanvideo_wrapper_22_14b_i2v_kijai"
VACE_TEMPLATE_ID = "video/wanvideo_wrapper_22_14b_vace_cocktail"
ALLOWLISTED_TEMPLATE_IDS = frozenset({I2V_TEMPLATE_ID, VACE_TEMPLATE_ID})

_DEFAULT_NEGATIVE_PROMPT = "fading, breaking, shot cuts, jumpcuts, blurry, noise, distorted"
_SHA256_OBJECT_ID_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_CAS_OBJECT_ID_RE = re.compile(r"^cas-[A-Za-z0-9][A-Za-z0-9_-]*$")
_REQUEST_FIELDS = frozenset(
    {
        "family",
        "operation",
        "model",
        "guidance",
        "continuity",
        "profile",
        "input_object_ids",
        "prompt",
        "negative_prompt",
        "width",
        "height",
        "frames",
        "fps",
        "steps",
        "seed",
    }
)


@dataclass(frozen=True, slots=True)
class DimensionalRequest:
    """The complete portable input contract for one dimensional generation."""

    family: SemanticFamily
    operation: Operation
    model: Model
    guidance: Guidance
    continuity: Continuity
    profile: Profile
    input_object_ids: tuple[str, ...]
    prompt: str
    negative_prompt: str = _DEFAULT_NEGATIVE_PROMPT
    width: int = 832
    height: int = 480
    frames: int = 81
    fps: int = 16
    steps: int = 6
    seed: int = -1


@dataclass(frozen=True, slots=True)
class ResultSemantics:
    """Explicit output meaning consumed by the later producer handoff."""

    output_kind: Literal["travel_segment", "individual_segment", "join_bridge"]
    continuity: Continuity
    publication: Literal["runtime_cas"] = "runtime_cas"
    settlement: Literal["published_video"] = "published_video"

    def as_dict(self) -> dict[str, str]:
        return {
            "output_kind": self.output_kind,
            "continuity": self.continuity,
            "publication": self.publication,
            "settlement": self.settlement,
        }


@dataclass(frozen=True, slots=True)
class CompiledDimensionalRequest:
    """A ready-template identity plus deterministic, typed bindings."""

    semantic_family: SemanticFamily
    template_id: str
    bindings: Mapping[str, object]
    input_object_ids: tuple[str, ...]
    result_semantics: ResultSemantics
    portable_identity: str

    def as_dict(self) -> dict[str, object]:
        """Return the JSON-safe handoff without machine-local values."""
        return {
            "semantic_family": self.semantic_family,
            "template_id": self.template_id,
            "bindings": dict(self.bindings),
            "input_object_ids": list(self.input_object_ids),
            "result_semantics": self.result_semantics.as_dict(),
            "portable_identity": self.portable_identity,
        }


@dataclass(frozen=True, slots=True)
class RouteFixture:
    """One frozen route matrix entry; not a dynamic route registry."""

    route_key: str
    family: SemanticFamily
    operation: Operation
    model: Model
    guidance: Guidance
    continuity: Continuity
    profile: Profile = "default"

    @property
    def template_id(self) -> str:
        return I2V_TEMPLATE_ID if self.family == "wan_i2v_first_last" else VACE_TEMPLATE_ID


# This is the exact 16-row frozen matrix.  Keep it finite and explicit.
ROUTE_FIXTURES: tuple[RouteFixture, ...] = (
    RouteFixture(
        "travel_segment__model-wan22_i2v__guidance-none__continuity-first_last__profile-default",
        "wan_i2v_first_last", "travel_segment", "wan22_i2v", "none", "first_last",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_flow__continuity-first_last__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_flow", "first_last",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_flow__continuity-video_source__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_flow", "video_source",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_canny__continuity-first_last__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_canny", "first_last",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_canny__continuity-video_source__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_canny", "video_source",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_depth__continuity-first_last__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_depth", "first_last",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_depth__continuity-video_source__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_depth", "video_source",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_raw__continuity-first_last__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_raw", "first_last",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace_raw__continuity-video_source__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace_raw", "video_source",
    ),
    RouteFixture(
        "travel_segment__model-wan22_vace__guidance-vace__continuity-video_source__profile-default",
        "wan_vace_travel", "travel_segment", "wan22_vace", "vace", "video_source",
    ),
    RouteFixture(
        "individual_travel_segment__model-wan22_vace__guidance-vace__continuity-first_last__profile-default",
        "wan_vace_individual", "individual_travel_segment", "wan22_vace", "vace", "first_last",
    ),
    RouteFixture(
        "individual_travel_segment__model-wan22_vace__guidance-vace_flow__continuity-first_last__profile-default",
        "wan_vace_individual", "individual_travel_segment", "wan22_vace", "vace_flow", "first_last",
    ),
    RouteFixture(
        "individual_travel_segment__model-wan22_vace__guidance-vace_canny__continuity-first_last__profile-default",
        "wan_vace_individual", "individual_travel_segment", "wan22_vace", "vace_canny", "first_last",
    ),
    RouteFixture(
        "individual_travel_segment__model-wan22_vace__guidance-vace_depth__continuity-first_last__profile-default",
        "wan_vace_individual", "individual_travel_segment", "wan22_vace", "vace_depth", "first_last",
    ),
    RouteFixture(
        "individual_travel_segment__model-wan22_vace__guidance-vace_raw__continuity-first_last__profile-default",
        "wan_vace_individual", "individual_travel_segment", "wan22_vace", "vace_raw", "first_last",
    ),
    RouteFixture(
        "join_clips_segment__model-wan22_vace__guidance-vace__continuity-join_bridge__profile-default",
        "wan_vace_join_bridge", "join_clips_segment", "wan22_vace", "vace", "join_bridge",
    ),
)

SUPPORTED_ROUTE_KEYS = frozenset(row.route_key for row in ROUTE_FIXTURES)


def _route_key(request: DimensionalRequest) -> str:
    return (
        f"{request.operation}__model-{request.model}__guidance-{request.guidance}"
        f"__continuity-{request.continuity}__profile-{request.profile}"
    )


def _route_for(request: DimensionalRequest) -> RouteFixture:
    key = _route_key(request)
    for row in ROUTE_FIXTURES:
        if row.route_key == key:
            if (
                row.family != request.family
                or row.operation != request.operation
                or row.model != request.model
                or row.guidance != request.guidance
                or row.continuity != request.continuity
                or row.profile != request.profile
            ):
                raise UnsupportedDimensionalRoute(f"inconsistent semantic family for route {key!r}")
            return row
    raise UnsupportedDimensionalRoute(f"unsupported dimensional route {key!r}")


def _non_empty_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DimensionalVaceError(f"{field} must be a non-empty string")
    return value.strip()


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DimensionalVaceError(f"{field} must be a positive integer")
    return value


def _normalise_ids(value: object) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise DimensionalVaceError("input_object_ids must be an ordered sequence of CAS object ids")
    ids: list[str] = []
    for index, object_id in enumerate(value):
        if not isinstance(object_id, str) or not object_id.strip():
            raise DimensionalVaceError(f"input_object_ids[{index}] must be a non-empty string")
        normalized = object_id.strip()
        if _SHA256_OBJECT_ID_RE.fullmatch(normalized) is None and _CAS_OBJECT_ID_RE.fullmatch(normalized) is None:
            raise DimensionalVaceError(
                f"input_object_ids[{index}] must be a Runtime/CAS identity, not a machine-local path, URL, or endpoint"
            )
        ids.append(normalized)
    return tuple(ids)


def _coerce_request(request: object) -> DimensionalRequest:
    if isinstance(request, DimensionalRequest):
        values: Mapping[str, object] = {
            "family": request.family,
            "operation": request.operation,
            "model": request.model,
            "guidance": request.guidance,
            "continuity": request.continuity,
            "profile": request.profile,
            "input_object_ids": request.input_object_ids,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "width": request.width,
            "height": request.height,
            "frames": request.frames,
            "fps": request.fps,
            "steps": request.steps,
            "seed": request.seed,
        }
    elif isinstance(request, Mapping):
        unknown = set(request) - _REQUEST_FIELDS
        if unknown:
            raise DimensionalVaceError(f"unknown request field(s): {', '.join(sorted(map(str, unknown)))}")
        values = request
    else:
        raise DimensionalVaceError("request must be DimensionalRequest or a mapping")

    required = ("family", "operation", "model", "guidance", "continuity", "profile", "input_object_ids", "prompt")
    missing = [field for field in required if field not in values]
    if missing:
        raise DimensionalVaceError(f"missing required field(s): {', '.join(missing)}")

    family = _non_empty_text(values["family"], "family")
    operation = _non_empty_text(values["operation"], "operation")
    model = _non_empty_text(values["model"], "model")
    guidance = _non_empty_text(values["guidance"], "guidance")
    continuity = _non_empty_text(values["continuity"], "continuity")
    profile = _non_empty_text(values["profile"], "profile")
    prompt = _non_empty_text(values["prompt"], "prompt")
    negative_prompt = _non_empty_text(values.get("negative_prompt", _DEFAULT_NEGATIVE_PROMPT), "negative_prompt")
    width = _positive_int(values.get("width", 832), "width")
    height = _positive_int(values.get("height", 480), "height")
    frames = _positive_int(values.get("frames", 81), "frames")
    fps = _positive_int(values.get("fps", 16), "fps")
    steps = _positive_int(values.get("steps", 6), "steps")
    seed = values.get("seed", -1)
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise DimensionalVaceError("seed must be an integer")
    if width % 8 or height % 8:
        raise DimensionalVaceError("width and height must be divisible by 8")
    if (frames - 1) % 4:
        raise DimensionalVaceError("frames must be 4n+1 for Wan 2.2")

    return DimensionalRequest(
        family=cast(SemanticFamily, family),
        operation=cast(Operation, operation),
        model=cast(Model, model),
        guidance=cast(Guidance, guidance),
        continuity=cast(Continuity, continuity),
        profile=cast(Profile, profile),
        input_object_ids=_normalise_ids(values["input_object_ids"]),
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        frames=frames,
        fps=fps,
        steps=steps,
        seed=seed,
    )


def _input_roles(request: DimensionalRequest, row: RouteFixture) -> tuple[str, ...]:
    count = len(request.input_object_ids)
    if row.continuity == "join_bridge":
        expected = ("left_clip", "right_clip")
    elif row.continuity == "first_last":
        expected = ("first_image", "last_image", "guidance_video") if row.model == "wan22_vace" else ("first_image", "last_image")
    else:
        expected = ("first_image", "last_image", "video_source")
    if count != len(expected):
        raise DimensionalVaceError(
            f"{row.route_key!r} requires {len(expected)} ordered CAS inputs ({', '.join(expected)}); got {count}"
        )
    return expected


def compile_dimensional_request(
    request: DimensionalRequest | Mapping[str, object],
) -> CompiledDimensionalRequest:
    """Compile exactly one supported request; unsupported combinations fail closed."""
    normalized = _coerce_request(request)
    row = _route_for(normalized)
    roles = _input_roles(normalized, row)
    result_kind: Literal["travel_segment", "individual_segment", "join_bridge"]
    if row.family == "wan_vace_individual":
        result_kind = "individual_segment"
    elif row.family == "wan_vace_join_bridge":
        result_kind = "join_bridge"
    else:
        result_kind = "travel_segment"
    result = ResultSemantics(output_kind=result_kind, continuity=row.continuity)
    input_bindings = {
        role: object_id for role, object_id in zip(roles, normalized.input_object_ids)
    }
    bindings: dict[str, object] = {
        "model": normalized.model,
        "guidance": normalized.guidance,
        "continuity": normalized.continuity,
        "profile": normalized.profile,
        "prompt": normalized.prompt,
        "negative_prompt": normalized.negative_prompt,
        "width": normalized.width,
        "height": normalized.height,
        "frames": normalized.frames,
        "fps": normalized.fps,
        "steps": normalized.steps,
        "seed": normalized.seed,
        **input_bindings,
    }
    portable = {
        "semantic_family": row.family,
        "template_id": row.template_id,
        "bindings": bindings,
        "input_object_ids": list(normalized.input_object_ids),
        "result_semantics": result.as_dict(),
    }
    encoded = json.dumps(portable, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return CompiledDimensionalRequest(
        semantic_family=row.family,
        template_id=row.template_id,
        bindings=MappingProxyType(bindings),
        input_object_ids=normalized.input_object_ids,
        result_semantics=result,
        portable_identity="sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    )


__all__ = [
    "ALLOWLISTED_TEMPLATE_IDS",
    "CompiledDimensionalRequest",
    "DimensionalRequest",
    "DimensionalVaceError",
    "I2V_TEMPLATE_ID",
    "ResultSemantics",
    "ROUTE_FIXTURES",
    "SUPPORTED_ROUTE_KEYS",
    "UnsupportedDimensionalRoute",
    "VACE_TEMPLATE_ID",
    "compile_dimensional_request",
]
