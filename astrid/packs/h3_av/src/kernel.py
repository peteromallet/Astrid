"""CPU-side H3 temporal, mask, anchor, and final-sampler contracts.

This module does not replace a Seitanism node.  It prepares conservative
inputs for the pinned nodes and keeps exact delivery permissions separate from
the coarser H3 sampling envelope.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

H3_FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
H3_VIDEO_FPS = 24
H3_AUDIO_HZ = 40


class H3KernelContractError(ValueError):
    """A delivery request cannot be represented by the declared H3 contract."""


def temporal_cells(latent_steps: int) -> list[dict[str, int]]:
    """Return the half-open delivery-frame support of every H3 video cell."""

    if isinstance(latent_steps, bool) or int(latent_steps) < 1:
        raise H3KernelContractError("latent_steps must be a positive integer")
    offset = 0
    result: list[dict[str, int]] = []
    for index in range(int(latent_steps)):
        span = H3_FRAME_PER_TOKEN[index % len(H3_FRAME_PER_TOKEN)]
        result.append({"cell": index, "start": offset, "end": offset + span, "span": span})
        offset += span
    return result


def frame_cell(frame: int, latent_steps: int) -> dict[str, int]:
    """Map one zero-based delivery frame to its containing H3 cell."""

    if isinstance(frame, bool) or int(frame) < 0:
        raise H3KernelContractError("frame must be a non-negative integer")
    for cell in temporal_cells(latent_steps):
        if cell["start"] <= int(frame) < cell["end"]:
            return cell
    coverage = temporal_cells(latent_steps)[-1]["end"]
    raise H3KernelContractError(f"frame {frame} is outside model coverage [0,{coverage})")


def conservative_video_cell_mask(
    delivery_mask: Any,
    *,
    latent_steps: int,
    latent_height: int,
    latent_width: int,
) -> Any:
    """Max-expand ``[F,H,W]`` delivery permissions onto H3 video cells.

    Every nonzero delivery pixel contributes to at least one latent spatial
    cell.  Every intersecting delivery frame contributes to its complete H3
    temporal cell.  The returned ``[T,h,w]`` tensor is a sampling envelope,
    never an exact-delivery mask.
    """

    import torch
    import torch.nn.functional as functional

    mask = torch.as_tensor(delivery_mask, dtype=torch.float32)
    if mask.ndim != 3 or int(mask.shape[0]) < 1:
        raise H3KernelContractError("delivery video mask must be [frames,height,width]")
    if not bool(torch.isfinite(mask).all()) or bool((mask < 0).any()) or bool((mask > 1).any()):
        raise H3KernelContractError("delivery video mask values must be finite and within [0,1]")
    if int(latent_height) < 1 or int(latent_width) < 1:
        raise H3KernelContractError("latent video dimensions must be positive")

    spatial = functional.adaptive_max_pool2d(
        mask.unsqueeze(1), (int(latent_height), int(latent_width))
    )[:, 0]
    rows = []
    frame_count = int(mask.shape[0])
    for cell in temporal_cells(latent_steps):
        start = cell["start"]
        end = min(cell["end"], frame_count)
        if start >= frame_count:
            rows.append(torch.zeros_like(spatial[0]))
        else:
            rows.append(spatial[start:end].amax(dim=0))
    return torch.stack(rows, dim=0)


def conservative_video_frame_mask(
    delivery_mask: Any,
    *,
    latent_steps: int,
    latent_height: int,
    latent_width: int,
) -> Any:
    """Return a model-frame mask accepted by fractional V2V's mask path.

    Spatial support is already reduced conservatively to latent resolution and
    each value is repeated across its complete irregular H3 temporal support.
    Consequently the pinned node's bilinear spatial resize is identity and its
    ``max`` temporal reduction reproduces :func:`conservative_video_cell_mask`.
    Native padding frames are explicit in this result and remain outside public
    delivery coordinates.
    """

    import torch

    cell_mask = conservative_video_cell_mask(
        delivery_mask,
        latent_steps=latent_steps,
        latent_height=latent_height,
        latent_width=latent_width,
    )
    frames = []
    for cell in temporal_cells(latent_steps):
        frames.extend(cell_mask[cell["cell"]] for _ in range(cell["span"]))
    return torch.stack(frames, dim=0)


def conservative_audio_tick_envelope(
    delivery_permissions: Any,
    *,
    sample_rate: int,
    audio_ticks: int,
) -> Any:
    """Union exact ``[channel,sample]`` permissions onto H3's 40 Hz clock.

    The returned ``[ticks,1,1]`` MASK is intended for the pinned AV mask node.
    It deliberately carries no channel identity: the pinned node averages the
    MASK and broadcasts the result across its two latent audio lanes.  Exact
    channel/sample permissions must remain available for final PCM restoration.
    """

    import torch

    permissions = torch.as_tensor(delivery_permissions)
    if permissions.ndim != 2 or int(permissions.shape[0]) < 1 or int(permissions.shape[1]) < 1:
        raise H3KernelContractError("delivery audio permissions must be [channels,samples]")
    if isinstance(sample_rate, bool) or int(sample_rate) < 1:
        raise H3KernelContractError("sample_rate must be a positive integer")
    if isinstance(audio_ticks, bool) or int(audio_ticks) < 1:
        raise H3KernelContractError("audio_ticks must be a positive integer")

    permissions = permissions.to(dtype=torch.bool)
    sample_count = int(permissions.shape[1])
    envelope = torch.zeros(int(audio_ticks), dtype=torch.float32, device=permissions.device)
    for tick in range(int(audio_ticks)):
        start = math.floor(tick * int(sample_rate) / H3_AUDIO_HZ)
        end = math.ceil((tick + 1) * int(sample_rate) / H3_AUDIO_HZ)
        start = min(max(start, 0), sample_count)
        end = min(max(end, start), sample_count)
        if end > start and bool(permissions[:, start:end].any()):
            envelope[tick] = 1.0
    return envelope.reshape(int(audio_ticks), 1, 1)


def intersect_sampling_permissions(*masks: Any) -> Any:
    """Combine same-shaped H3 masks with protection winning every conflict.

    H3 uses zero for preserve and one for generate, so intersection/minimum is
    the conservative composition for a prepared edit mask plus an existing
    context/extension mask.  The exact delivery masks remain separate.
    """

    import torch

    if not masks:
        raise H3KernelContractError("at least one sampling mask is required")
    tensors = [torch.as_tensor(mask, dtype=torch.float32) for mask in masks]
    shape = tuple(tensors[0].shape)
    if any(tuple(tensor.shape) != shape for tensor in tensors[1:]):
        raise H3KernelContractError("sampling masks must have identical shapes")
    for tensor in tensors:
        if not bool(torch.isfinite(tensor).all()) or bool((tensor < 0).any()) or bool((tensor > 1).any()):
            raise H3KernelContractError("sampling mask values must be finite and within [0,1]")
    result = tensors[0]
    for tensor in tensors[1:]:
        result = torch.minimum(result, tensor.to(device=result.device))
    return result


def classify_anchors(
    anchors: Sequence[Mapping[str, Any]],
    *,
    latent_steps: int,
    protected_cells: Iterable[int] = (),
    unsupported_hard: str = "reject",
) -> list[dict[str, Any]]:
    """Classify anchors without shifting them or claiming decoded exactness.

    Accepted classifications are ``hard_conditioned``, ``soft_conditioned``
    and ``restoration_only``.  ``hard`` is representable only on a one-frame
    phase-0 cell that is neither already protected nor shared with another hard
    request.  ``unsupported_hard='soft'`` is the only declared fallback path.
    Every accepted classification still requires exact final restoration.
    """

    if unsupported_hard not in {"reject", "soft", "restoration"}:
        raise H3KernelContractError("unsupported_hard must be 'reject', 'soft', or 'restoration'")
    protected = {int(value) for value in protected_cells}
    staged: list[dict[str, Any]] = []
    hard_by_cell: dict[int, list[str]] = defaultdict(list)
    seen_ids: set[str] = set()

    for index, raw in enumerate(anchors):
        anchor_id = str(raw.get("id", f"anchor-{index}"))
        if anchor_id in seen_ids:
            raise H3KernelContractError(f"duplicate anchor id {anchor_id!r}")
        seen_ids.add(anchor_id)
        frame = raw.get("frame")
        if isinstance(frame, bool) or not isinstance(frame, int):
            raise H3KernelContractError(f"anchor {anchor_id!r} frame must be an integer")
        requested = str(raw.get("mode", "soft"))
        if requested not in {"hard", "soft", "restoration"}:
            raise H3KernelContractError(f"anchor {anchor_id!r} has unsupported mode {requested!r}")
        cell = frame_cell(frame, latent_steps)
        record = {
            "id": anchor_id,
            "frame": frame,
            "requested_mode": requested,
            "latent_pin": raw.get("latent_pin") is True,
            "cell": cell["cell"],
            "cell_support": [cell["start"], cell["end"]],
            "exact_final_restoration": True,
        }
        staged.append(record)
        if requested == "hard":
            hard_by_cell[cell["cell"]].append(anchor_id)

    result: list[dict[str, Any]] = []
    for record in staged:
        requested = record["requested_mode"]
        reasons: list[str] = []
        if requested == "soft":
            classification = "soft_conditioned"
        elif requested == "restoration":
            classification = "restoration_only"
        else:
            if record["cell_support"][1] - record["cell_support"][0] != 1:
                reasons.append("cell_spans_multiple_delivery_frames")
            if len(hard_by_cell[record["cell"]]) > 1:
                reasons.append("hard_anchor_cell_collision")
            if record["cell"] in protected:
                reasons.append("cell_already_protected")
            if reasons and (unsupported_hard == "reject" or record.get("latent_pin") is True):
                classification = "rejected"
                record["exact_final_restoration"] = False
            elif reasons:
                classification = "restoration_only" if unsupported_hard == "restoration" else "soft_conditioned"
                reasons.append("exact_delivery_restoration_only" if classification == "restoration_only" else "declared_soft_fallback")
            else:
                classification = "hard_conditioned"
        record["classification"] = classification
        if reasons:
            record["reasons"] = reasons
        result.append(record)
    return result


def require_supported_anchors(classified: Sequence[Mapping[str, Any]]) -> None:
    """Fail compilation when any classified anchor was rejected."""

    rejected = [str(item.get("id")) for item in classified if item.get("classification") == "rejected"]
    if rejected:
        raise H3KernelContractError("unsupported hard anchors: " + ", ".join(rejected))


def validate_final_sampler_state(
    state: Mapping[str, Any],
    *,
    required_latent_kinds: Iterable[str] = (),
    required_conditioning_kinds: Iterable[str] = (),
) -> dict[str, Any]:
    """Validate final sampler sockets against complete post-node lineages.

    Each lineage item has ``node``, ``input_source``, ``output`` and ``kind``.
    The first item may use ``input_source=None``.  This catches a later node
    replacing an earlier mask/guide because the sampler and guider must consume
    the final outputs of the connected chains, not merely contain expected node
    types somewhere in the graph.
    """

    sockets = state.get("sampler_sockets")
    if not isinstance(sockets, Mapping):
        raise H3KernelContractError("final sampler state is missing sampler_sockets")
    required_sockets = {"noise", "guider", "sampler", "sigmas", "latent_image"}
    missing_sockets = sorted(required_sockets - set(sockets))
    if missing_sockets:
        raise H3KernelContractError("final sampler is missing sockets: " + ", ".join(missing_sockets))

    def check_chain(name: str) -> tuple[list[Mapping[str, Any]], set[str]]:
        raw_chain = state.get(name)
        if not isinstance(raw_chain, Sequence) or isinstance(raw_chain, (str, bytes)) or not raw_chain:
            raise H3KernelContractError(f"{name} must be a non-empty sequence")
        chain = list(raw_chain)
        kinds: set[str] = set()
        previous_output: Any = None
        for index, item in enumerate(chain):
            if not isinstance(item, Mapping):
                raise H3KernelContractError(f"{name}[{index}] must be an object")
            for field in ("node", "output", "kind"):
                if not isinstance(item.get(field), str) or not item[field]:
                    raise H3KernelContractError(f"{name}[{index}].{field} must be a non-empty string")
            if index and item.get("input_source") != previous_output:
                raise H3KernelContractError(
                    f"{name}[{index}] disconnects {previous_output!r} with input {item.get('input_source')!r}"
                )
            previous_output = item["output"]
            kinds.add(str(item["kind"]))
        return chain, kinds

    latent_chain, latent_kinds = check_chain("latent_lineage")
    conditioning_chain, conditioning_kinds = check_chain("conditioning_lineage")
    missing_latent = sorted(set(required_latent_kinds) - latent_kinds)
    missing_conditioning = sorted(set(required_conditioning_kinds) - conditioning_kinds)
    if missing_latent or missing_conditioning:
        raise H3KernelContractError(
            f"final sampler lineage is incomplete; latent={missing_latent}, conditioning={missing_conditioning}"
        )
    if sockets["latent_image"] != latent_chain[-1]["output"]:
        raise H3KernelContractError("sampler latent_image does not consume the final latent mutation")

    guider = state.get("guider")
    if not isinstance(guider, Mapping) or not isinstance(guider.get("output"), str):
        raise H3KernelContractError("final sampler state is missing guider provenance")
    if guider.get("conditioning_source") != conditioning_chain[-1]["output"]:
        raise H3KernelContractError("guider does not consume the final conditioning mutation")
    if sockets["guider"] != guider["output"]:
        raise H3KernelContractError("sampler guider socket does not consume the declared final guider")

    return {
        "status": "valid",
        "sampler": state.get("sampler"),
        "sockets": dict(sockets),
        "latent_kinds": sorted(latent_kinds),
        "conditioning_kinds": sorted(conditioning_kinds),
    }


__all__ = [
    "H3_AUDIO_HZ",
    "H3_FRAME_PER_TOKEN",
    "H3_VIDEO_FPS",
    "H3KernelContractError",
    "classify_anchors",
    "conservative_audio_tick_envelope",
    "conservative_video_cell_mask",
    "conservative_video_frame_mask",
    "frame_cell",
    "intersect_sampling_permissions",
    "require_supported_anchors",
    "temporal_cells",
    "validate_final_sampler_state",
]
