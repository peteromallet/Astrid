"""Astrid-owned binding boundary for the pinned H3 graph.

The graph described here is a transport manifest, not a replacement for a
Seitanism node implementation.  It records the inputs and the complete
post-node lineages that the runtime binding must construct.  Keeping this
boundary in Astrid makes the exact delivery-domain masks available to
composition while only the conservative H3 sampling envelopes cross into the
latent graph.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .kernel import (
    H3KernelContractError,
    classify_anchors,
    require_supported_anchors,
    validate_final_sampler_state,
)
from .masks import PreparedAVMaskError, load_prepared_av_mask
from .request import H3Request, read_prepared_request

PINNED_SEITANISM_URL = "https://github.com/peteromallet/ComfyUI-H3-Motion-Context-MultiRef.git"
PINNED_SEITANISM_COMMIT = "361624fb406b63eb6694442eac6c895fc1533a70"
PINNED_SEITANISM_REQUIREMENT = f"git+{PINNED_SEITANISM_URL}@{PINNED_SEITANISM_COMMIT}"
PINNED_COMFY_COMMIT = "ee71d5c4993f29086b27fde1629a945ae48425bf"
H3_REFERENCE_CAPACITIES = {
    "ref_images.ref_image_": 9,
    "ref_videos.ref_video_": 3,
    "ref_video_audios.ref_video_audio_": 3,
    "ref_audios.ref_audio_": 3,
}
GRAPH_SCHEMA_VERSION = 1
PREPARED_MASK_REFERENCE_KIND = "h3_prepared_av_mask_reference"


class GraphBindingError(ValueError):
    """The prepared input cannot be bound to the declared H3 graph."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GraphBindingError(f"{path} must be an object")
    return value


def _artifact(preparation: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return T2's prepared-input object without creating a second format."""

    for key in ("prepared_input", "prepared_av_mask", "prepared"):
        candidate = preparation.get(key)
        if isinstance(candidate, Mapping):
            return candidate
    if preparation.get("kind") in {"h3_av_prepared_input", "h3_av_prepared_av_mask"}:
        return preparation
    raise GraphBindingError(
        "T4 requires T2's prepared-input artifact under prepared_input (or prepared_av_mask)"
    )


def _shape(record: Mapping[str, Any], path: str) -> list[int]:
    raw = record.get("shape")
    if isinstance(raw, Mapping):
        names = ("frames", "height", "width") if path.startswith("video") else ("channels", "samples")
        result = [raw.get(name) for name in names]
    elif isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        result = list(raw)
    else:
        raise GraphBindingError(f"{path}.shape is required")
    if any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in result):
        raise GraphBindingError(f"{path}.shape must contain positive integer dimensions")
    return [int(item) for item in result]


def _payload_reference(record: Mapping[str, Any], path: str) -> Any:
    for key in ("payload", "values", "artifact", "path", "asset", "data"):
        if key in record:
            value = record[key]
            if value is None:
                raise GraphBindingError(f"{path}.{key} cannot be null")
            return value
    raise GraphBindingError(f"{path} is missing its lossless payload reference")


def _prepared_delivery_reference(
    artifact: Mapping[str, Any],
    stream: str,
    delivery: Mapping[str, Any],
    *,
    prepared_artifact_digest: str,
    shape: list[int],
    polarity: str,
) -> dict[str, Any]:
    """Replace only canonical PreparedAVMask delivery bytes with a managed ref."""

    payload = delivery.get("payload")
    if not isinstance(payload, Mapping):
        raise GraphBindingError(f"{stream}.delivery.payload must be a prepared payload manifest")
    if payload.get("encoding") != "bitpack-msb-v1":
        raise GraphBindingError(f"{stream}.delivery.payload uses an unsupported encoding")
    payload_shape = payload.get("shape")
    if payload_shape != shape:
        raise GraphBindingError(f"{stream}.delivery.payload shape does not match its stream shape")
    payload_length = payload.get("length")
    if type(payload_length) is not int or payload_length <= 0:
        raise GraphBindingError(f"{stream}.delivery.payload length is invalid")
    payload_sha256 = payload.get("sha256")
    if not isinstance(payload_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", payload_sha256):
        raise GraphBindingError(f"{stream}.delivery.payload sha256 is invalid")
    if not isinstance(payload.get("data"), str) or not payload["data"]:
        raise GraphBindingError(f"{stream}.delivery.payload data is missing")
    if not isinstance(prepared_artifact_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", prepared_artifact_digest):
        raise GraphBindingError("prepared AV mask artifact digest is invalid")
    if artifact.get("kind") != "h3_prepared_av_mask":
        raise GraphBindingError("managed delivery references require canonical PreparedAVMask input")
    return {
        "kind": PREPARED_MASK_REFERENCE_KIND,
        "managed_output": "prepared_artifact",
        "artifact_digest": prepared_artifact_digest,
        "member": f"{stream}.payload",
        "stream": stream,
        "payload_sha256": payload_sha256,
        "encoding": payload["encoding"],
        "shape": list(shape),
        "length": payload_length,
        "polarity": polarity,
    }


def _validate_prepared_delivery_reference(
    reference: Mapping[str, Any],
    prepared_manifest: Mapping[str, Any],
    stream: str,
) -> None:
    """Validate a compact delivery reference against a loaded managed artifact."""

    if reference.get("kind") != PREPARED_MASK_REFERENCE_KIND:
        raise GraphBindingError(f"{stream}.delivery.payload is not a PreparedAVMask reference")
    if reference.get("managed_output") != "prepared_artifact":
        raise GraphBindingError(f"{stream}.delivery.payload points outside prepared_artifact")
    if reference.get("stream") != stream or reference.get("member") != f"{stream}.payload":
        raise GraphBindingError(f"{stream}.delivery.payload member identity changed")
    artifact_digest = prepared_manifest.get("artifact_digest")
    if reference.get("artifact_digest") != artifact_digest:
        raise GraphBindingError(f"{stream}.delivery.payload artifact identity changed")
    payload = prepared_manifest.get(stream, {}).get("payload") if isinstance(prepared_manifest.get(stream), Mapping) else None
    if not isinstance(payload, Mapping):
        raise GraphBindingError(f"prepared artifact is missing {stream}.payload")
    expected = {
        "payload_sha256": payload.get("sha256"),
        "encoding": payload.get("encoding"),
        "shape": payload.get("shape"),
        "length": payload.get("length"),
        "polarity": (
            prepared_manifest.get(stream, {}).get("polarity")
            if isinstance(prepared_manifest.get(stream), Mapping)
            else None
        ),
    }
    for key, value in expected.items():
        if reference.get(key) != value:
            raise GraphBindingError(f"{stream}.delivery.payload {key} does not match managed artifact")


def validate_prepared_mask_references(
    binding: Mapping[str, Any],
    prepared_manifest: Mapping[str, Any],
) -> None:
    """Validate both canonical delivery references and retained sampling data."""

    if prepared_manifest.get("kind") != "h3_prepared_av_mask":
        raise GraphBindingError("managed prepared artifact is not canonical PreparedAVMask")
    inputs = _mapping(binding.get("inputs"), "inputs")
    masks = _mapping(inputs.get("masks"), "inputs.masks")
    for stream in ("video", "audio"):
        row = _mapping(masks.get(stream), f"inputs.masks.{stream}")
        delivery = _mapping(row.get("delivery"), f"inputs.masks.{stream}.delivery")
        reference = _mapping(delivery.get("payload"), f"inputs.masks.{stream}.delivery.payload")
        _validate_prepared_delivery_reference(reference, prepared_manifest, stream)

        artifact_stream = _mapping(prepared_manifest.get(stream), f"prepared.{stream}")
        shape_value = artifact_stream.get("shape")
        if not isinstance(shape_value, Mapping):
            raise GraphBindingError(f"prepared {stream}.shape is missing")
        shape_names = ("frames", "height", "width") if stream == "video" else ("channels", "samples")
        artifact_shape = [shape_value.get(name) for name in shape_names]
        if delivery.get("shape") != artifact_shape:
            raise GraphBindingError(f"{stream}.delivery shape does not match managed artifact")
        if delivery.get("polarity") != artifact_stream.get("polarity"):
            raise GraphBindingError(f"{stream}.delivery polarity does not match managed artifact")
        if "clock" in delivery and delivery.get("clock") != artifact_stream.get("clock"):
            raise GraphBindingError(f"{stream}.delivery clock does not match managed artifact")
        if "coverage" in delivery and delivery.get("coverage") != artifact_stream.get("coverage"):
            raise GraphBindingError(f"{stream}.delivery coverage does not match managed artifact")


def _stream_record(
    artifact: Mapping[str, Any],
    stream: str,
    *,
    aliases: tuple[str, ...],
    prepared_artifact_digest: str | None = None,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    raw = None
    for key in aliases:
        if isinstance(artifact.get(key), Mapping):
            raw = artifact[key]
            break
    if raw is None:
        raise GraphBindingError(f"prepared input is missing {stream} AV mask stream")
    record = _mapping(raw, stream)

    # T4's original adapter fixtures used an already split delivery/sampling
    # shape.  T2's real PreparedAVMask deliberately stores only exact delivery
    # payloads (plus the audio envelope); video latent materialization remains
    # the explicit h3_masks boundary.  Accept both without creating a second
    # producer artifact.
    delivery = record.get("delivery")
    if delivery is None:
        delivery = record.get("exact")
    if delivery is None and "payload" in record:
        delivery = record
    if delivery is None and "values" in record:
        delivery = record
    delivery = _mapping(delivery, f"{stream}.delivery")
    expected_delivery_shape = _shape(delivery, f"{stream}.delivery")

    sampling = None
    for key in ("sampling", "sampling_envelope", "model", "model_mask"):
        if isinstance(record.get(key), Mapping):
            sampling = record[key]
            break
    if sampling is None and stream == "video" and "payload" in record:
        dimensions = artifact.get("target_model_dimensions")
        if not isinstance(dimensions, Mapping):
            raise GraphBindingError("video mask stream is missing target_model_dimensions")
        if any(type(dimensions.get(key)) is not int or int(dimensions[key]) < 1 for key in ("frames", "height", "width")):
            raise GraphBindingError("video target_model_dimensions must contain positive frames, height, and width")
        sampling = {
            "shape": {key: int(dimensions[key]) for key in ("frames", "height", "width")},
            "payload": {
                "kind": "prepared_av_mask_derivation",
                "source_artifact_digest": prepared_artifact_digest,
                "materializer": "PreparedAVMask.h3_masks.video_cell_mask",
            },
        }
    if sampling is None:
        raise GraphBindingError(f"{stream} mask stream is missing its conservative sampling artifact")
    sampling = _mapping(sampling, f"{stream}.sampling")
    sampling_shape = _shape(sampling, f"{stream}.sampling")

    polarity = delivery.get("polarity", record.get("polarity", "black_preserve_white_edit"))
    if polarity != "black_preserve_white_edit":
        raise GraphBindingError(f"{stream} mask polarity must be black_preserve_white_edit")
    delivery_payload = _payload_reference(delivery, f"{stream}.delivery")
    if prepared_artifact_digest is not None and artifact.get("kind") == "h3_prepared_av_mask":
        delivery_payload = _prepared_delivery_reference(
            artifact,
            stream,
            delivery,
            prepared_artifact_digest=prepared_artifact_digest,
            shape=expected_delivery_shape,
            polarity=polarity,
        )
    delivery_record: dict[str, Any] = {
        "shape": expected_delivery_shape,
        "payload": delivery_payload,
        "polarity": polarity,
    }
    for key in ("clock", "coverage"):
        if key in record:
            delivery_record[key] = record[key]
    return (
        {
            "delivery": delivery_record,
            "sampling": {
                "shape": sampling_shape,
                "payload": _payload_reference(sampling, f"{stream}.sampling"),
                "polarity": polarity,
            },
        },
        record,
    )


def _request_from_preparation(preparation: Mapping[str, Any], artifact: Mapping[str, Any]) -> H3Request:
    raw = preparation.get("request", artifact.get("request"))
    if not isinstance(raw, Mapping):
        raise GraphBindingError("prepared-input artifact is missing its normalized request")
    expected = preparation.get("request_digest", artifact.get("request_digest"))
    try:
        request = read_prepared_request(raw, expected, require_normalized_v2=True)
    except Exception as exc:  # normalize_request has several contract-specific exception classes.
        raise GraphBindingError(f"prepared request is invalid: {exc}") from exc
    if request.value.get("version") != 2:
        raise GraphBindingError("T4 graph binding requires the normalized v2 request")
    return request


def _reference_bindings(request: H3Request) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, item in enumerate(request.value["media"]):
        if item.get("role") != "reference":
            continue
        modality = item.get("modality")
        if modality not in {"image", "video", "audio"}:
            raise GraphBindingError(f"reference {item.get('occurrence_id', index)!r} has no supported modality")
        result.append(
            {
                "index": len(result),
                "id": item.get("id", item["occurrence_id"]),
                "asset": item["asset"],
                "modality": modality,
                "audio": item.get("audio", True) if modality == "video" else modality == "audio",
                "model_tag": item.get("model_tag"),
                "range": item.get("range"),
                "resolved_range": item.get("resolved_range"),
            }
        )
    return result


def _reference_port_plan(
    references: Sequence[Mapping[str, Any]],
    asset_members: Mapping[str, str] | None,
    *,
    reserved_audio: int = 0,
) -> list[dict[str, Any]]:
    """Resolve ordered occurrences to the pinned node's dynamic port families."""

    counts = {"image": 0, "video": 0, "audio": reserved_audio}
    prefixes = {
        "image": "ref_images.ref_image_",
        "video": "ref_videos.ref_video_",
        "audio": "ref_audios.ref_audio_",
    }
    plan: list[dict[str, Any]] = []
    loader_by_semantics: dict[tuple[str, ...], str] = {}
    if reserved_audio > H3_REFERENCE_CAPACITIES[prefixes["audio"]]:
        raise GraphBindingError(
            "pinned MiniMaxH3ReferenceToVideo supports at most 3 combined timeline/reference audio inputs"
        )
    for occurrence_index, reference in enumerate(references):
        modality = str(reference["modality"])
        slot = counts[modality]
        prefix = prefixes[modality]
        capacity = H3_REFERENCE_CAPACITIES[prefix]
        if slot >= capacity:
            if modality == "audio":
                raise GraphBindingError(
                    f"pinned MiniMaxH3ReferenceToVideo supports at most {capacity} combined timeline/reference audio inputs"
                )
            label = {"image": "image", "video": "video", "audio": "standalone audio"}[modality]
            raise GraphBindingError(
                f"pinned MiniMaxH3ReferenceToVideo supports at most {capacity} {label} references"
            )
        counts[modality] += 1
        member = _asset_member(str(reference["asset"]), asset_members)
        semantics = (
            str(reference["asset"]), modality,
            _canonical(reference.get("resolved_range")).decode("utf-8"),
        )
        if modality == "audio":
            semantics = (*semantics, str(reference["id"]))
        loader = loader_by_semantics.setdefault(
            semantics, f"c3-reference-{modality}-{occurrence_index}"
        )
        row = {
            "occurrence_index": occurrence_index,
            "id": str(reference["id"]),
            "role": "reference",
            "occurrence_id": str(reference["id"]),
            "asset": str(reference["asset"]),
            "asset_member": member,
            "modality": modality,
            "model_tag": reference.get("model_tag"),
            "range": reference.get("range"),
            "resolved_range": reference.get("resolved_range"),
            "loader": loader,
            "loader_output": "0",
            "conditioner": "110",
            "conditioner_input": f"{prefix}{slot}",
        }
        if modality == "video" and reference.get("audio", True):
            row["paired_audio_output"] = "2"
            row["paired_audio_input"] = f"ref_video_audios.ref_video_audio_{slot}"
        plan.append(row)
    return plan


def _declare_native_reference_schema(workflow: Any) -> None:
    """Attach the complete pinned autogrow schema to the authored node instance."""

    node = workflow.nodes["110"]
    declared = list(node.native_input_names)
    for prefix, capacity in H3_REFERENCE_CAPACITIES.items():
        for slot in range(capacity):
            name = f"{prefix}{slot}"
            if name not in declared:
                declared.append(name)
                node.native_input_types.append("IMAGE" if prefix.startswith("ref_images") or prefix.startswith("ref_videos") else "AUDIO")
                node.native_input_optional.append(True)
    node.native_input_names = declared


def _native_geometry(
    request: H3Request,
    video_masks: Mapping[str, Any],
    audio_masks: Mapping[str, Any],
) -> dict[str, Any]:
    """Describe H3's native AV grid separately from exact delivery clocks."""

    delivery_video = list(video_masks["delivery"]["shape"])
    delivery_audio = list(audio_masks["delivery"]["shape"])
    if len(delivery_video) != 3 or len(delivery_audio) != 2:
        raise GraphBindingError("prepared delivery masks do not describe video and audio clocks")
    frames, height, width = delivery_video
    channels, samples = delivery_audio
    expected_frames = round(float(request.value["duration"]) * 24)
    expected_samples = round(float(request.value["duration"]) * 48000)
    if frames != expected_frames or samples != expected_samples:
        raise GraphBindingError(
            "prepared delivery clocks do not match the normalized 24fps/48kHz request duration"
        )
    native_frames = max(5, frames)
    while native_frames % 17 != 5:
        native_frames += 1
    video_latent_t = 2 if native_frames <= 5 else ((native_frames - 5) // 17) * 5 + 2
    audio_latent_t = round(native_frames * 40 / 24)
    return {
        "source": None if not _timeline_items(request) else {"kind": "prepared_timeline"},
        "delivery": {
            "video": {"frames": frames, "height": height, "width": width, "fps": 24},
            "audio": {"channels": channels, "samples_per_channel": samples, "sample_rate": 48000},
        },
        "native": {
            "video_frames": native_frames,
            "audio_ticks": audio_latent_t,
            "audio_tick_rate": 40,
            "tail_padding": {"video_frames": native_frames - frames, "audio_ticks": audio_latent_t - round(samples * 40 / 48000)},
        },
        "latent": {
            "video": [1, 24, video_latent_t, height // 16, width // 16],
            "audio": [1, 32, 2, audio_latent_t],
        },
        "delivery_trim": {
            "leading_video_frames": 0,
            "leading_audio_samples": 0,
            "keep_video_frames": [0, frames],
            "keep_audio_samples": [0, samples],
            "tail_policy": "exact_delivery_crop_after_declared_resampling",
        },
    }


def _timeline_items(request: H3Request) -> list[Mapping[str, Any]]:
    return [item for item in request.value["media"] if item.get("role") == "timeline"]


def require_supported_source_timeline(request: H3Request) -> None:
    """Keep only true unedited prefixes on the continuation branch."""

    for item in _timeline_items(request):
        if item.get("modality") != "video":
            continue
        if not isinstance(item.get("resolved_range"), list) or not isinstance(item.get("resolved_at"), Mapping):
            raise GraphBindingError("video timeline is missing resolved range or placement")


def _anchors(artifact: Mapping[str, Any], request: H3Request) -> list[dict[str, Any]]:
    image_timeline_ids = {
        str(item.get("id", item["occurrence_id"]))
        for item in _timeline_items(request)
        if item.get("modality") == "image"
    }
    supplied = artifact.get("anchors")
    if supplied is not None:
        if not isinstance(supplied, Sequence) or isinstance(supplied, (str, bytes)):
            raise GraphBindingError("prepared anchors must be an array")
        return [
            anchor
            for index, item in enumerate(supplied)
            if str((anchor := dict(_mapping(item, f"anchors[{index}]"))).get("id")) in image_timeline_ids
        ]
    result: list[dict[str, Any]] = []
    for item in _timeline_items(request):
        if item.get("modality") != "image":
            continue
        result.append(
            {
                "id": item.get("id", item["occurrence_id"]),
                "frame": int(item["resolved_at"]["value"]),
                "mode": "hard" if item.get("hard") else "soft",
            }
        )
    return result


def _anchor_state(artifact: Mapping[str, Any], request: H3Request) -> list[dict[str, Any]]:
    anchors = _anchors(artifact, request)
    if not anchors:
        return []
    target_dimensions = artifact.get("target_model_dimensions")
    latent_steps = artifact.get("latent_steps", artifact.get("target", {}).get("latent_steps"))
    if latent_steps is None and isinstance(target_dimensions, Mapping):
        latent_steps = target_dimensions.get("frames")
    latent_steps = latent_steps or 7
    protected = artifact.get("protected_cells", artifact.get("target", {}).get("protected_cells", []))
    fallback = artifact.get("unsupported_hard", "reject")
    # T2 has already classified anchors against its target model dimensions.
    # Reuse that producer result when present; raw T4 fixtures still take the
    # public T3 classifier path below.
    if all(isinstance(item, Mapping) and isinstance(item.get("classification"), str) for item in anchors):
        try:
            require_supported_anchors(anchors)
        except H3KernelContractError as exc:
            raise GraphBindingError(str(exc)) from exc
        return anchors
    try:
        classified = classify_anchors(
            anchors,
            latent_steps=int(latent_steps),
            protected_cells=protected,
            unsupported_hard=str(fallback),
        )
        try:
            require_supported_anchors(classified)
        except H3KernelContractError as exc:
            rejected = [
                f"{item.get('id')} ({','.join(str(reason) for reason in item.get('reasons', []))})"
                for item in classified
                if item.get("classification") == "rejected"
            ]
            detail = "; ".join(rejected)
            raise H3KernelContractError(f"{exc}; {detail}" if detail else str(exc)) from exc
    except (H3KernelContractError, TypeError, ValueError) as exc:
        raise GraphBindingError(str(exc)) from exc
    return classified


def _guide_bindings(request: H3Request, references: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    known = {str(item["id"]): item for item in references}
    audio_only = any(item.get("modality") == "audio" for item in _timeline_items(request)) and not any(
        item.get("modality") == "video" for item in _timeline_items(request)
    )
    guides: list[dict[str, Any]] = []
    for item in _timeline_items(request):
        for edit_index, edit in enumerate(item.get("edit", [])):
            for guide in edit.get("guides", []):
                if guide not in known:
                    raise GraphBindingError(f"guide {guide!r} is not a bound reference")
                if audio_only and edit["stream"] == "audio" and known[guide].get("modality") == "audio":
                    # These references are directly wired to the native audio
                    # conditioner; MotionContext additionally requires video frames.
                    continue
                guides.append(
                    {
                        "reference": guide,
                        "stream": edit["stream"],
                        "timeline": item.get("id", item["occurrence_id"]),
                        "edit_index": edit_index,
                        "placement_frame": item["resolved_at"]["value"],
                        "edit_range": edit["resolved"]["range"],
                    }
                )
    return guides


def _branch(request: H3Request) -> str:
    timeline = _timeline_items(request)
    if not timeline:
        return "source_free"
    if any(item.get("modality") == "audio" for item in timeline) and not any(
        item.get("modality") == "video" for item in timeline
    ):
        return "audio_only"
    has_source = any(item.get("modality") in {"video", "audio"} for item in timeline)
    if not has_source:
        return "source_free"
    video = [item for item in timeline if item.get("modality") == "video"]
    continuation = (
        len(video) == 1
        and all(item.get("modality") in {"video", "image"} for item in timeline)
        and not video[0].get("edit")
        and video[0]["resolved_at"]["value"] == 0
        and video[0]["resolved_range"][0] == 0
    )
    return "extension_context" if continuation else "source_backed_v2v"


def _lineage_item(node: str, output: str, kind: str, input_source: str | None) -> dict[str, str | None]:
    return {"node": node, "input_source": input_source, "output": output, "kind": kind}


def _asset_member(asset_id: str, asset_members: Mapping[str, str] | None) -> str:
    """Resolve one logical asset through the compile-owned managed manifest."""

    if asset_members is not None and asset_id in asset_members:
        return str(asset_members[asset_id])
    return asset_id


def _add_node(workflow: Any, class_type: str, node_id: str, **inputs: Any) -> Any:
    """Add an existing Comfy/H3 primitive with a stable authored identity."""

    from vibecomfy.security.provenance import Provenance

    return workflow.add_node(
        class_type,
        node_id,
        uid=f"c3-{node_id}",
        _provenance=Provenance.USER_CONFIRMED,
        **inputs,
    )


def _disconnect_target(workflow: Any, target: str) -> None:
    while workflow.disconnect(target):
        pass


def _load_h3_workflow() -> Any:
    """Load the pinned packaged graph as the source graph for this binding."""

    try:
        from vibecomfy.scratchpad_loader import load_scratchpad
        from vibecomfy.security.provenance import Provenance
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise GraphBindingError("VibeComfy is required to materialize the H3 executable graph") from exc
    source = Path(__file__).resolve().parents[1] / "workflows" / "native_h3_continuation_refs" / "workflow.py"
    try:
        return load_scratchpad(source, provenance_override=Provenance.USER_CONFIRMED).copy()
    except Exception as exc:  # the loader reports the exact canonical-source defect
        raise GraphBindingError(f"could not load the packaged H3 VibeWorkflow: {exc}") from exc


def _request_prompt(request: H3Request) -> str:
    prompt = str(request.value["prompt"])
    dialogue: list[str] = []
    for item in _timeline_items(request):
        for edit in item.get("edit", []):
            if edit.get("stream") == "audio" and edit.get("text"):
                dialogue.append(str(edit["text"]))
    if not dialogue:
        return prompt
    return "{}\n\nExact dialogue:\n{}".format(prompt, "\n".join(dialogue))


def _register_media_loader(
    workflow: Any,
    binding: str,
    node_id: str,
    field: str,
    member: str,
    semantics: str,
) -> None:
    """Expose a managed archive binding on its real loader socket."""

    try:
        workflow.register_input(
            binding,
            node_id,
            field,
            value=member,
            default=Path(member).name,
            media_semantics=semantics,
        )
    except (TypeError, ValueError) as exc:
        raise GraphBindingError(
            f"managed {semantics} binding {binding!r} cannot target {node_id}.{field}: {exc}"
        ) from exc


def _video_loader_inputs(
    member: str, *, rate: int = 24, window: Sequence[int] | None = None, format_name: str = "AnimateDiff"
) -> dict[str, Any]:
    """Pinned VHS_LoadVideoFFmpeg required inputs (packaged workflow node 99)."""
    start, end = window if window is not None else (0, 0)
    return {
        "video": member, "force_rate": rate, "custom_width": 0,
        "custom_height": 0, "frame_load_cap": end - start if window is not None else 0,
        "start_time": start / 24, "format": format_name,
    }


def _audio_loader_inputs(member: str, *, window: Sequence[int] | None = None) -> dict[str, Any]:
    """Pinned VHS_LoadAudio uses audio_file, seek_seconds and duration."""
    start, end = window if window is not None else (0, 0)
    return {
        "audio_file": member,
        "seek_seconds": start / 48000,
        "duration": (end - start) / 48000 if window is not None else 0,
    }


def _reference_loader(
    workflow: Any,
    reference: Mapping[str, Any],
    member: str,
    index: int,
    *,
    binding: str,
    register: bool = True,
) -> tuple[str, str, str | None]:
    """Create one real loader for a reference and return its image/audio ports."""

    modality = str(reference["modality"])
    if modality == "image":
        node_id = f"c3-reference-image-{index}"
        _add_node(workflow, "LoadImage", node_id, image=member)
        if register:
            _register_media_loader(workflow, binding, node_id, "image", member, "image")
        return node_id, "0", None
    if modality == "video":
        node_id = f"c3-reference-video-{index}"
        window = reference.get("resolved_range")
        _add_node(workflow, "VHS_LoadVideoFFmpeg", node_id, **_video_loader_inputs(member, window=window))
        if register:
            _register_media_loader(workflow, binding, node_id, "video", member, "video")
        return node_id, "0", "2"
    node_id = f"c3-reference-audio-{index}"
    _add_node(workflow, "VHS_LoadAudio", node_id, **_audio_loader_inputs(member))
    if register:
        _register_media_loader(workflow, binding, node_id, "audio_file", member, "audio")
    return node_id, "0", "0"


def _timeline_loader(
    workflow: Any,
    item: Mapping[str, Any],
    member: str,
    index: int,
    *,
    binding: str,
    register: bool = True,
) -> tuple[str, str, str | None]:
    modality = str(item.get("modality"))
    if modality == "image":
        node_id = f"c3-timeline-image-{index}"
        _add_node(workflow, "LoadImage", node_id, image=member)
        if register:
            _register_media_loader(workflow, binding, node_id, "image", member, "image")
        return node_id, "0", None
    if modality == "video":
        node_id = f"c3-timeline-video-{index}"
        _add_node(workflow, "VHS_LoadVideoFFmpeg", node_id, **_video_loader_inputs(member, window=item.get("resolved_range")))
        if register:
            _register_media_loader(workflow, binding, node_id, "video", member, "video")
        return node_id, "0", "2"
    node_id = f"c3-timeline-audio-{index}"
    _add_node(workflow, "VHS_LoadAudio", node_id, **_audio_loader_inputs(member, window=item.get("resolved_range")))
    if register:
        _register_media_loader(workflow, binding, node_id, "audio_file", member, "audio")
    return node_id, "0", "0"


def _serialize_graph(workflow: Any) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    """Serialize and reload through the public VibeComfy IR boundary."""

    try:
        from vibecomfy.workflow import VibeWorkflow

        envelope = workflow.to_envelope()
        # The packaged H3 workflow predates the current typed requirement
        # wire format. Normalize only those two representations; nodes and
        # edges remain untouched and are reloaded by the public decoder.
        requirements = envelope.get("requirements", {})
        models = requirements.get("models", [])
        requirements["models"] = [item.get("name") if isinstance(item, Mapping) else item for item in models]
        runtime = requirements.get("runtime", {})
        if isinstance(runtime.get("packages"), (list, tuple)):
            runtime["packages"] = dict(runtime["packages"])
        reloaded = VibeWorkflow.from_envelope(json.loads(json.dumps(envelope)))
        compiled = reloaded.compile("api")
    except Exception as exc:
        raise GraphBindingError(f"serialized H3 VibeWorkflow did not reload/compile: {exc}") from exc
    return envelope, reloaded, compiled


def _materialize_executable_graph(
    request: H3Request,
    artifact: Mapping[str, Any],
    *,
    asset_members: Mapping[str, str] | None,
    mask_members: Mapping[str, str] | None,
    references: Sequence[Mapping[str, Any]],
    reference_plan: Sequence[Mapping[str, Any]],
    guides: Sequence[Mapping[str, Any]],
    anchors: Sequence[Mapping[str, Any]],
    audio_only: bool,
    geometry: Mapping[str, Any],
    baseline_member: str | None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Bind the request to one real H3 graph path and return its IR evidence."""

    workflow = _load_h3_workflow()
    branch = _branch(request)
    source_items = _timeline_items(request)
    source = next((item for item in source_items if item.get("modality") == "video"), None)
    source_member = (baseline_member if branch == "source_backed_v2v" else _asset_member(str(source["asset"]), asset_members)) if source is not None else None

    # Remove the packaged multi-extension fan-out and rebuild one public path.
    for target in ("946.extension_2", "946.extension_3", "946.extension_4", "946.extension_5", "946.extension_6"):
        _disconnect_target(workflow, target)
    _declare_native_reference_schema(workflow)
    for prefix, capacity in H3_REFERENCE_CAPACITIES.items():
        for slot in range(capacity):
            _disconnect_target(workflow, f"110.{prefix}{slot}")
    for node_id in ("1020", "1021", "1022"):
        workflow.remove_node(node_id)
    _disconnect_target(workflow, "121.conditioning")
    _disconnect_target(workflow, "124.latent_image")

    if source_member is not None:
        workflow.set_input("source_video", source_member)
        source_window = source.get("resolved_range") if branch == "extension_context" else None
        workflow.set_input("source_start", source_window[0] / 24 if source_window else 0)
        workflow.set_input("source_frames", source_window[1] - source_window[0] if source_window else 0)
        workflow.set_input("duration", max(5, float(request.value.get("duration") or 5)))
    workflow.set_input("prompt", _request_prompt(request))
    settings = request.value.get("settings", {})
    workflow.set_input("model", settings.get("model", workflow.inputs["model"].value))
    workflow.set_input("seed", int(settings.get("seed", workflow.inputs["seed"].value)))
    workflow.set_input("steps", int(settings.get("steps", workflow.inputs["steps"].value)))
    workflow.nodes["937"].inputs["sampler_name"] = str(settings.get("sampler", workflow.nodes["937"].inputs.get("sampler_name", "res_multistep")))
    workflow.nodes["935"].inputs["strength_model"] = float(settings["guidance_scale"])

    if branch in {"source_free", "audio_only", "source_backed_v2v"}:
        for target in ("110.width", "110.height", "110.length"):
            _disconnect_target(workflow, target)
        native = geometry["native"]
        delivery = geometry["delivery"]["video"]
        workflow.nodes["110"].inputs.update(
            {
                "width": int(delivery["width"]),
                "height": int(delivery["height"]),
                "length": int(native["video_frames"]),
            }
        )

    loaders: dict[str, tuple[str, str, str | None]] = {}
    registered_bindings: set[str] = set()
    binding_modalities: dict[str, str] = {}
    reference_loader_cache: dict[tuple[str, ...], tuple[str, str, str | None]] = {}
    for index, (reference, port) in enumerate(zip(references, reference_plan, strict=True)):
        binding = str(reference["asset"])
        modality = str(reference["modality"])
        if binding in binding_modalities and binding_modalities[binding] != modality:
            raise GraphBindingError(f"asset binding {binding!r} is reused with incompatible media semantics")
        binding_modalities[binding] = modality
        cache_key = (binding, modality, _canonical(reference.get("resolved_range")).decode("utf-8"))
        if modality == "audio":
            cache_key = (*cache_key, str(reference["id"]))
        loader = reference_loader_cache.get(cache_key)
        if loader is None:
            loader = _reference_loader(
                workflow, reference, str(port["asset_member"]), index,
                binding=binding, register=binding not in registered_bindings,
            )
            reference_loader_cache[cache_key] = loader
        registered_bindings.add(binding)
        loaders[str(reference["id"])] = loader
        modality = reference["modality"]
        primary_output = loader[2] or "0" if modality == "audio" else loader[1]
        workflow.connect(f"{loader[0]}.{primary_output}", f"110.{port['conditioner_input']}")
        if port.get("paired_audio_input") is not None:
            if loader[2] is None:
                raise GraphBindingError(f"reference video {reference['id']!r} is missing its paired audio output")
            workflow.connect(f"{loader[0]}.{loader[2]}", f"110.{port['paired_audio_input']}")

    conditioning_source = "110.0"
    soft = [item for item in anchors if item.get("classification") == "soft_conditioned"]
    hard = [item for item in anchors if item.get("classification") == "hard_conditioned" and (branch != "source_backed_v2v" or any(t.get("modality") == "image" and str(t.get("id", t.get("occurrence_id"))) == str(item["id"]) for t in source_items))]
    timeline_loaders: dict[str, tuple[str, str, str | None]] = {}
    for index, item in enumerate(source_items):
        binding = str(item["asset"])
        modality = str(item["modality"])
        if binding in binding_modalities and binding_modalities[binding] != modality:
            raise GraphBindingError(f"asset binding {binding!r} is reused with incompatible media semantics")
        binding_modalities[binding] = modality
        member = _asset_member(binding, asset_members)
        loader = _timeline_loader(
            workflow, item, member, index, binding=binding,
            register=binding not in registered_bindings,
        )
        registered_bindings.add(binding)
        timeline_loaders[str(item.get("id", item["occurrence_id"]))] = loader
    audio_timeline = [item for item in source_items if item.get("modality") == "audio"]
    if any(item["resolved_at"]["value"] != 0 for item in audio_timeline):
        raise GraphBindingError("timeline audio placement after frame 0 cannot be represented by the native reference conditioner")
    for index, item in enumerate(audio_timeline):
        loader = timeline_loaders[str(item.get("id", item["occurrence_id"]))]
        workflow.connect(f"{loader[0]}.{loader[1]}", f"110.ref_audios.ref_audio_{index}")
    if branch == "source_backed_v2v":
        if baseline_member is None:
            baseline_member = "prepared-source-baseline.mkv"
        workflow.set_input("source_video", baseline_member)
        _add_node(
            workflow, "H3V2VGranularFractionalDenoise", "c3-full-source-v2v",
            source_fps=24.0, mode="global", global_strength=0.0,
            inside_strength=1.0, outside_strength=0.0, audio_strength=0.0,
            source_fit="start", crop="disabled", mask_temporal_reduce="max", invert_mask=False,
        )
        workflow.connect("110.1", "c3-full-source-v2v.latent")
        workflow.connect("5.0", "c3-full-source-v2v.model")
        workflow.connect("3.0", "c3-full-source-v2v.vae")
        workflow.connect("1046.0", "c3-full-source-v2v.audio_vae")
        workflow.connect("99.0", "c3-full-source-v2v.source_frames")
        workflow.connect("99.2", "c3-full-source-v2v.source_audio")
        _disconnect_target(workflow, "121.model")
        workflow.connect("c3-full-source-v2v.1", "121.model")
        soft = [item for item in soft if any(t.get("modality") == "image" and str(t.get("id", t.get("occurrence_id"))) == str(item["id"]) for t in source_items)]
    if soft:
        state = {"count": len(soft), "positions": [int(item["frame"]) + 1 for item in soft]}
        _add_node(
            workflow,
            "MiniMaxH3CustomKeyframes",
            "c3-soft-anchors",
            keyframe_state=json.dumps(state, separators=(",", ":")),
            indexing="1-based",
            crop="disabled",
        )
        workflow.connect(conditioning_source, "c3-soft-anchors.conditioning")
        workflow.connect("3.0", "c3-soft-anchors.vae")
        workflow.connect("110.1", "c3-soft-anchors.latent")
        for index, anchor in enumerate(soft, start=1):
            try:
                loader = timeline_loaders[str(anchor["id"])]
            except KeyError as exc:
                raise GraphBindingError(
                    f"anchor {anchor['id']!r} has no timeline asset loader"
                ) from exc
            workflow.connect(f"{loader[0]}.{loader[1]}", f"c3-soft-anchors.keyframe_image_{index}")
        conditioning_source = "c3-soft-anchors.0"

    # CustomKeyframes replaces the complete keyframe state; append-capable
    # MotionContext must therefore come afterwards or its guides are erased.
    for guide_index, guide in enumerate(guides):
        reference = next(item for item in references if str(item["id"]) == str(guide["reference"]))
        loader = loaders[str(reference["id"])]
        guide_id = f"c3-motion-guide-{guide_index}"
        edit_start, edit_end = guide["edit_range"]
        if guide["stream"] == "audio":
            if edit_start % 2000 or edit_end % 2000:
                raise GraphBindingError("audio motion guide interval must align to 24fps frames")
            edit_start, edit_end = edit_start // 2000, edit_end // 2000
        edit_start += guide["placement_frame"]
        edit_end += guide["placement_frame"]
        if edit_end > geometry["delivery"]["video"]["frames"]:
            raise GraphBindingError("motion guide edit interval is outside the output")
        context_length = min(39, edit_end - edit_start)
        if context_length < 1:
            raise GraphBindingError("motion guide has an empty target context")
        _add_node(
            workflow,
            "MiniMaxH3MotionContext",
            guide_id,
            context_length=context_length,
            encode_mode="video",
            anchor_mode="head",
            crop="disabled",
            audio_context_length=context_length,
            audio_mode="timeline",
            target_start=edit_start,
        )
        workflow.connect(conditioning_source, f"{guide_id}.conditioning")
        workflow.connect("3.0", f"{guide_id}.vae")
        workflow.connect("110.1", f"{guide_id}.latent")
        if reference["modality"] == "audio":
            if source is None:
                raise GraphBindingError("audio motion guides require a video timeline context")
            workflow.connect("99.0", f"{guide_id}.context_frames")
            workflow.connect(f"{loader[0]}.{loader[2] or '0'}", f"{guide_id}.context_audio")
            workflow.connect("4.0", f"{guide_id}.audio_vae")
        else:
            workflow.connect(f"{loader[0]}.{loader[1]}", f"{guide_id}.context_frames")
            if loader[2] is not None and reference.get("audio", True):
                workflow.connect(f"{loader[0]}.{loader[2]}", f"{guide_id}.context_audio")
                workflow.connect("4.0", f"{guide_id}.audio_vae")
        conditioning_source = f"{guide_id}.0"
    workflow.connect(conditioning_source, "121.conditioning")

    mask_members = dict(mask_members or {})
    _add_node(
        workflow,
        "VHS_LoadVideoFFmpeg",
        "c3-video-mask-loader",
        **_video_loader_inputs(mask_members.get("video", "prepared_video_mask.mkv"), format_name="None"),
    )
    _register_media_loader(
        workflow,
        "prepared_video_mask",
        "c3-video-mask-loader",
        "video",
        mask_members.get("video", "prepared_video_mask.mkv"),
        "video",
    )
    _add_node(
        workflow,
        "VHS_LoadVideoFFmpeg",
        "c3-audio-mask-loader",
        **_video_loader_inputs(mask_members.get("audio", "prepared_audio_mask.mkv"), rate=40, format_name="None"),
    )
    _register_media_loader(
        workflow,
        "prepared_audio_mask",
        "c3-audio-mask-loader",
        "video",
        mask_members.get("audio", "prepared_audio_mask.mkv"),
        "video",
    )
    _add_node(workflow, "MiniMaxH3SetAVNoiseMask", "c3-av-mask")
    mask_latent = "c3-full-source-v2v.0" if branch == "source_backed_v2v" else ("110.1" if branch in {"source_free", "audio_only"} else "103.0")
    workflow.connect(mask_latent, "c3-av-mask.latent")
    for stream in ("video", "audio"):
        loader = f"c3-{stream}-mask-loader"
        image_mask = f"c3-{stream}-image-to-mask"
        threshold = f"c3-{stream}-threshold-mask"
        # VHS output 1 is inverted alpha (zero for grayscale FFV1); its IMAGE
        # output 0 repeats the encoded gray value in RGB. Red is that gray
        # channel, and thresholding restores exact binary permission endpoints.
        _add_node(workflow, "ImageToMask", image_mask, channel="red")
        _add_node(workflow, "ThresholdMask", threshold, value=0.5)
        workflow.connect(f"{loader}.0", f"{image_mask}.image")
        workflow.connect(f"{image_mask}.0", f"{threshold}.mask")
        workflow.connect(f"{threshold}.0", f"c3-av-mask.{stream}_mask")
    latent_source = "c3-av-mask.0"
    if hard:
        state = {"count": len(hard), "positions": [int(item["frame"]) + 1 for item in hard]}
        _add_node(
            workflow,
            "MiniMaxH3CustomKeyframesMasked",
            "c3-hard-anchors",
            keyframe_state=json.dumps(state, separators=(",", ":")),
            indexing="1-based",
            crop="disabled",
        )
        workflow.connect(latent_source, "c3-hard-anchors.latent")
        workflow.connect("3.0", "c3-hard-anchors.vae")
        for index, anchor in enumerate(hard, start=1):
            try:
                loader = timeline_loaders[str(anchor["id"])]
            except KeyError as exc:
                raise GraphBindingError(
                    f"anchor {anchor['id']!r} has no timeline asset loader"
                ) from exc
            workflow.connect(f"{loader[0]}.{loader[1]}", f"c3-hard-anchors.keyframe_image_{index}")
        latent_source = "c3-hard-anchors.0"
    workflow.connect(latent_source, "124.latent_image")

    # The graph has one public output and one final sampler/guider ancestry.
    if branch in {"source_free", "audio_only", "source_backed_v2v"}:
        workflow.nodes["992"].inputs.update(
            {
                "filename_prefix": "video/h3_source_backed_av" if branch == "source_backed_v2v" else "video/h3_source_free_av",
                "save_output": True,
                "save_metadata": False,
                "trim_to_audio": False,
            }
        )
        keep: set[str] = {"992"}
        output_node = "992"
    else:
        keep = {"946", "1043"}
        output_node = "946"
    pending = list(keep)
    while pending:
        target = pending.pop()
        for edge in workflow.edges:
            if edge.to_node == target and edge.from_node not in keep:
                keep.add(edge.from_node)
                pending.append(edge.from_node)
    for node_id in list(workflow.nodes):
        if node_id not in keep:
            workflow.remove_node(node_id)
    workflow.inputs.pop("reference_0", None)
    workflow.inputs.pop("reference_1", None)
    workflow.finalize_metadata()
    from vibecomfy.workflow import VibeOutput

    workflow.outputs = [
        VibeOutput(
            node_id=output_node,
            output_type=workflow.nodes[output_node].class_type,
            name="av" if branch in {"source_free", "audio_only", "source_backed_v2v"} else "continuation",
            artifact_kind="video",
            mime_type="video/mp4",
            filename_prefix=(
                ("video/h3_source_backed_av" if branch == "source_backed_v2v" else "video/h3_source_free_av")
                if branch in {"source_free", "audio_only", "source_backed_v2v"}
                else "video/masked_av_extension"
            ),
            expected_cardinality="one",
        )
    ]
    envelope, reloaded, compiled = _serialize_graph(workflow)
    return reloaded, envelope, compiled


def validate_h3_graph_binding(value: Mapping[str, Any]) -> dict[str, Any]:
    """Revalidate serialized request-to-edge completeness and semantic identity."""

    if value.get("kind") != "h3_av_graph_binding" or value.get("schema_version") != GRAPH_SCHEMA_VERSION:
        raise GraphBindingError("unsupported H3 graph binding manifest")
    inputs = _mapping(value.get("inputs"), "inputs")
    references = inputs.get("references")
    plan = inputs.get("reference_edges")
    timeline_plan = inputs.get("timeline_loaders", [])
    audio_baselines = inputs.get("audio_baselines", [])
    executable = _mapping(value.get("executable_graph"), "executable_graph")
    edges = executable.get("edges")
    nodes = executable.get("nodes")
    compiled = executable.get("compiled_api")
    outputs = executable.get("outputs")
    if not isinstance(references, list) or not isinstance(plan, list):
        raise GraphBindingError("H3 graph binding reference manifests must be arrays")
    if not isinstance(timeline_plan, list):
        raise GraphBindingError("H3 graph binding timeline loader witnesses must be an array")
    if len(references) != len(plan):
        raise GraphBindingError("H3 graph binding omitted a normalized reference occurrence")
    if not isinstance(edges, list) or not isinstance(nodes, list) or not isinstance(compiled, Mapping):
        raise GraphBindingError("H3 executable graph evidence is malformed")
    expected: set[tuple[str, str, str, str]] = set()
    node_by_id = {str(node.get("id")): node for node in nodes if isinstance(node, Mapping)}
    settings = _mapping(inputs.get("settings"), "inputs.settings")
    guidance = settings.get("guidance_scale")
    lora = node_by_id.get("935")
    lora_inputs = lora.get("inputs") if isinstance(lora, Mapping) else None
    compiled_lora = compiled.get("935")
    compiled_lora_inputs = compiled_lora.get("inputs") if isinstance(compiled_lora, Mapping) else None
    if not isinstance(lora_inputs, Mapping) or not isinstance(compiled_lora_inputs, Mapping) or lora_inputs.get("strength_model") != guidance or compiled_lora_inputs.get("strength_model") != guidance:
        raise GraphBindingError("guidance_scale is not bound to the H3 LoRA strength control")
    for index, (reference, row) in enumerate(zip(references, plan, strict=True)):
        if not isinstance(reference, Mapping) or not isinstance(row, Mapping):
            raise GraphBindingError(f"reference binding {index} is malformed")
        for field in ("id", "asset", "modality", "model_tag", "range", "resolved_range"):
            if row.get(field) != reference.get(field):
                raise GraphBindingError(f"reference binding {index} changed {field}")
        if row.get("role") != "reference" or row.get("occurrence_id") != reference.get("id"):
            raise GraphBindingError(f"reference binding {index} changed occurrence identity")
        loader = str(row.get("loader"))
        port = str(row.get("conditioner_input"))
        output = str(row.get("loader_output"))
        expected.add((loader, output, "110", port))
        if row.get("paired_audio_input") is not None:
            expected.add((loader, str(row.get("paired_audio_output")), "110", str(row.get("paired_audio_input"))))
        loader_node = node_by_id.get(loader)
        if not isinstance(loader_node, Mapping):
            raise GraphBindingError(f"reference binding {index} loader is missing")
        loader_inputs = loader_node.get("inputs")
        if not isinstance(loader_inputs, Mapping):
            raise GraphBindingError(f"reference binding {index} loader inputs are missing")
        asset_field = {"image": "image", "video": "video", "audio": "audio_file"}[str(reference["modality"])]
        if loader_inputs.get(asset_field) != row.get("asset_member"):
            raise GraphBindingError(f"reference binding {index} asset identity changed")
        if reference["modality"] == "video":
            window = reference.get("resolved_range")
            start, end = (window if window is not None else (0, 0))
            if loader_inputs.get("start_time") != start / 24 or loader_inputs.get("frame_load_cap") != (end - start if window is not None else 0):
                raise GraphBindingError(f"reference binding {index} video window changed")
            if any(loader_inputs.get(key) != value for key, value in _video_loader_inputs(str(row["asset_member"]), window=window).items()):
                raise GraphBindingError(f"reference binding {index} native video loader schema changed")
        elif reference["modality"] == "audio" and any(
            loader_inputs.get(key) != value for key, value in _audio_loader_inputs(str(row["asset_member"])).items()
        ):
            raise GraphBindingError(f"reference binding {index} native audio loader schema changed")
    if not isinstance(audio_baselines, list):
        raise GraphBindingError("timeline audio baseline bindings must be an array")
    for index, row in enumerate(timeline_plan):
        if not isinstance(row, Mapping) or row.get("role") != "timeline" or row.get("occurrence_id") != row.get("id"):
            raise GraphBindingError(f"timeline loader witness {index} has invalid occurrence identity")
        modality = row.get("modality")
        expected_class = {"image": "LoadImage", "video": "VHS_LoadVideoFFmpeg", "audio": "VHS_LoadAudio"}.get(modality) if isinstance(modality, str) else None
        loader = str(row.get("loader"))
        node = node_by_id.get(loader)
        compiled_node = compiled.get(loader)
        if expected_class is None or not isinstance(node, Mapping) or node.get("class_type") != expected_class:
            raise GraphBindingError(f"timeline loader witness {index} has no matching node")
        if modality == "audio" and not isinstance(compiled_node, Mapping):
            raise GraphBindingError(f"timeline loader witness {index} is absent from the compiled conditioner")
        node_inputs = node.get("inputs")
        compiled_inputs = compiled_node.get("inputs") if isinstance(compiled_node, Mapping) else None
        if not isinstance(node_inputs, Mapping) or (compiled_node is not None and not isinstance(compiled_inputs, Mapping)):
            raise GraphBindingError(f"timeline loader witness {index} has malformed native inputs")
        member = str(row.get("asset_member"))
        window = row.get("resolved_range")
        expected_inputs = (
            {"image": member} if modality == "image" else
            _video_loader_inputs(member, window=window) if modality == "video" else
            _audio_loader_inputs(member, window=window)
        )
        for key, expected_value in expected_inputs.items():
            if node_inputs.get(key) != expected_value or (compiled_inputs is not None and compiled_inputs.get(key) != expected_value):
                raise GraphBindingError(f"timeline loader witness {index} changed native input {key}")
    for stream, rate in (("video", 24), ("audio", 40)):
        loader = f"c3-{stream}-mask-loader"
        node = node_by_id.get(loader)
        compiled_node = compiled.get(loader)
        if not isinstance(node, Mapping) or node.get("class_type") != "VHS_LoadVideoFFmpeg" or not isinstance(compiled_node, Mapping):
            raise GraphBindingError(f"{stream} mask loader is missing")
        node_inputs = node.get("inputs")
        compiled_inputs = compiled_node.get("inputs")
        if not isinstance(node_inputs, Mapping) or not isinstance(compiled_inputs, Mapping):
            raise GraphBindingError(f"{stream} mask loader inputs are malformed")
        expected_inputs = _video_loader_inputs(str(node_inputs.get("video")), rate=rate, format_name="None")
        if any(node_inputs.get(key) != expected_value or compiled_inputs.get(key) != expected_value for key, expected_value in expected_inputs.items()):
            raise GraphBindingError(f"{stream} mask loader native schema changed")
    for index, row in enumerate(audio_baselines):
        if not isinstance(row, Mapping):
            raise GraphBindingError(f"timeline audio baseline binding {index} is malformed")
        if row.get("role") != "timeline" or row.get("occurrence_id") != row.get("id"):
            raise GraphBindingError(f"timeline audio baseline {index} occurrence identity changed")
        loader = str(row.get("loader"))
        port = str(row.get("conditioner_input"))
        output = str(row.get("loader_output"))
        expected.add((loader, output, "110", port))
        loader_node = node_by_id.get(loader)
        if not isinstance(loader_node, Mapping) or loader_node.get("class_type") != "VHS_LoadAudio":
            raise GraphBindingError(f"timeline audio baseline {index} loader is missing")
        loader_inputs = loader_node.get("inputs")
        if not isinstance(loader_inputs, Mapping) or loader_inputs.get("audio_file") != row.get("asset_member"):
            raise GraphBindingError(f"timeline audio baseline {index} managed asset identity changed")
        if any(loader_inputs.get(key) != value for key, value in _audio_loader_inputs(str(row["asset_member"]), window=row.get("resolved_range")).items()):
            raise GraphBindingError(f"timeline audio baseline {index} source window changed")
    actual = {
        (str(edge.get("from_node")), str(edge.get("from_output")), str(edge.get("to_node")), str(edge.get("to_input")))
        for edge in edges
        if isinstance(edge, Mapping)
        and str(edge.get("to_node")) == "110"
        and any(str(edge.get("to_input", "")).startswith(prefix) for prefix in H3_REFERENCE_CAPACITIES)
    }
    if actual != expected:
        raise GraphBindingError("serialized H3 graph reference edges do not match the normalized request")
    compiled_inputs = compiled.get("110", {}).get("inputs", {}) if isinstance(compiled.get("110"), Mapping) else {}
    for loader, _, _, port in expected:
        link = compiled_inputs.get(port) if isinstance(compiled_inputs, Mapping) else None
        if not isinstance(link, list) or len(link) != 2 or str(link[0]) != loader:
            raise GraphBindingError(f"compiled H3 graph reference input 110.{port} is missing or changed")
    if not isinstance(outputs, list) or len(outputs) != 1 or outputs[0].get("expected_cardinality") != "one":
        raise GraphBindingError("serialized H3 graph must declare one AV output")
    supplied_identity = value.get("bundle_identity")
    if supplied_identity is not None:
        identity_value = {
            key: item
            for key, item in value.items()
            if key not in {"bundle_identity", "graph_path", "graph_sha256"}
        }
        if supplied_identity != _digest(identity_value):
            raise GraphBindingError("H3 graph binding semantic identity does not match its contents")
    return dict(value)


def build_h3_graph_binding(
    preparation: Mapping[str, Any],
    *,
    asset_members: Mapping[str, str] | None = None,
    mask_members: Mapping[str, str] | None = None,
    baseline_member: str | None = None,
) -> dict[str, Any]:
    """Validate T2's artifact and emit one executable H3 VibeWorkflow binding."""

    artifact = _artifact(preparation)
    if artifact.get("status") not in {None, "prepared", "ready"}:
        raise GraphBindingError("prepared input is not ready for graph binding")
    request = _request_from_preparation(preparation, artifact)
    require_supported_source_timeline(request)
    branch = _branch(request)
    timeline_items = _timeline_items(request)
    source_digest = artifact.get("source_baseline_digest", artifact.get("baseline_digest"))
    if branch != "source_free" and (not isinstance(source_digest, str) or not source_digest):
        raise GraphBindingError("prepared input is missing source_baseline_digest")
    if branch == "source_free" and not timeline_items and source_digest is not None:
        raise GraphBindingError("source-free prepared input must have a null source baseline digest")
    baseline_identity = artifact.get("mapping", {}).get("baseline_identity") if isinstance(artifact.get("mapping"), Mapping) else None
    if branch == "source_free" and not timeline_items and baseline_identity is not None:
        if not isinstance(baseline_identity, Mapping) or baseline_identity.get("kind") != "none" or baseline_identity.get("digest") is not None:
            raise GraphBindingError("source-free prepared input must preserve baseline_identity none/null")
    prepared_artifact_digest: str | None = None
    if artifact.get("kind") == "h3_prepared_av_mask":
        try:
            prepared = load_prepared_av_mask(artifact)
        except PreparedAVMaskError as exc:
            raise GraphBindingError(str(exc)) from exc
        prepared_artifact_digest = prepared.artifact_digest
        declared_digest = preparation.get("artifact_digest")
        if declared_digest is not None and declared_digest != prepared_artifact_digest:
            raise GraphBindingError("prepared AV mask artifact digest does not match its preparation wrapper")

    video_masks, video_record = _stream_record(
        artifact,
        "video",
        aliases=("video", "video_mask"),
        prepared_artifact_digest=prepared_artifact_digest,
    )
    audio_masks, audio_record = _stream_record(
        artifact,
        "audio",
        aliases=("audio", "audio_mask"),
        prepared_artifact_digest=prepared_artifact_digest,
    )
    references = _reference_bindings(request)
    timeline_loader_bindings = [
        {
            "id": str(item.get("id", item["occurrence_id"])),
            "role": "timeline",
            "occurrence_id": str(item["occurrence_id"]),
            "asset": str(item["asset"]),
            "asset_member": _asset_member(str(item["asset"]), asset_members),
            "modality": str(item["modality"]),
            "resolved_range": item.get("resolved_range"),
            "resolved_at": item.get("resolved_at"),
            "loader": f"c3-timeline-{item['modality']}-{index}",
        }
        for index, item in enumerate(timeline_items)
    ]
    audio_timeline = [item for item in timeline_items if item.get("modality") == "audio"]
    reference_plan = _reference_port_plan(references, asset_members, reserved_audio=len(audio_timeline))
    audio_baseline_bindings = []
    for timeline_index, item in enumerate(timeline_items):
        if item.get("modality") != "audio":
            continue
        audio_index = sum(1 for prior in timeline_items[:timeline_index] if prior.get("modality") == "audio")
        asset_id = str(item["asset"])
        audio_baseline_bindings.append({
            "id": str(item.get("id", item["occurrence_id"])),
            "role": "timeline",
            "occurrence_id": str(item["occurrence_id"]),
            "asset": asset_id,
            "asset_member": _asset_member(asset_id, asset_members),
            "resolved_range": item.get("resolved_range"),
            "resolved_at": item.get("resolved_at"),
            "loader": f"c3-timeline-audio-{timeline_index}",
            "loader_output": "0",
            "conditioner_input": f"ref_audios.ref_audio_{audio_index}",
        })
    geometry = _native_geometry(request, video_masks, audio_masks)
    anchors = _anchor_state(artifact, request)
    guides = _guide_bindings(request, references)
    audio_only = bool(_timeline_items(request)) and not any(
        edit.get("stream") == "video" and edit.get("action") == "generate"
        for item in _timeline_items(request)
        for edit in item.get("edit", [])
    )

    reloaded, envelope, compiled = _materialize_executable_graph(
        request,
        artifact,
        asset_members=asset_members,
        mask_members=mask_members,
        references=references,
        reference_plan=reference_plan,
        guides=guides,
        anchors=anchors,
        audio_only=audio_only,
        geometry=geometry,
        baseline_member=baseline_member,
    )
    timeline_loader_bindings = [row for row in timeline_loader_bindings if row["loader"] in reloaded.nodes]
    actual_nodes = [
        {"id": str(node_id), "class_type": node.class_type, "inputs": dict(node.inputs)}
        for node_id, node in reloaded.nodes.items()
    ]
    actual_edges = [
        {"from_node": edge.from_node, "from_output": edge.from_output, "to_node": edge.to_node, "to_input": edge.to_input}
        for edge in reloaded.edges
    ]
    expected_reference_edges = {
        (str(row["loader"]), str(row["loader_output"]), "110", str(row["conditioner_input"]))
        for row in reference_plan
    }
    expected_reference_edges.update(
        (str(row["loader"]), str(row["paired_audio_output"]), "110", str(row["paired_audio_input"]))
        for row in reference_plan
        if row.get("paired_audio_input") is not None
    )
    expected_reference_edges.update(
        (str(row["loader"]), str(row["loader_output"]), "110", str(row["conditioner_input"]))
        for row in audio_baseline_bindings
    )
    actual_reference_edges = {
        (edge["from_node"], edge["from_output"], edge["to_node"], edge["to_input"])
        for edge in actual_edges
        if edge["to_node"] == "110" and any(edge["to_input"].startswith(prefix) for prefix in H3_REFERENCE_CAPACITIES)
    }
    if actual_reference_edges != expected_reference_edges:
        raise GraphBindingError("serialized H3 graph reference edges do not match the normalized request")
    compiled_conditioner = compiled.get("110", {}).get("inputs", {})
    if compiled_conditioner.get("prompt") != _request_prompt(request):
        raise GraphBindingError("compiled H3 graph prompt does not match the normalized request")
    for _, _, _, port in expected_reference_edges:
        if port not in compiled_conditioner:
            raise GraphBindingError(f"compiled H3 graph omitted dynamic reference input 110.{port}")
    output_descriptors = [
        {
            "node_id": output.node_id,
            "output_type": output.output_type,
            "name": output.name,
            "artifact_kind": output.artifact_kind,
            "mime_type": output.mime_type,
            "filename_prefix": output.filename_prefix,
            "expected_cardinality": output.expected_cardinality,
        }
        for output in reloaded.outputs
    ]
    expected_sink = "992" if branch in {"source_free", "audio_only", "source_backed_v2v"} else "946"
    if len(output_descriptors) != 1 or output_descriptors[0]["node_id"] != expected_sink:
        raise GraphBindingError("serialized H3 graph must declare exactly one real AV sink")
    if output_descriptors[0]["expected_cardinality"] != "one":
        raise GraphBindingError("serialized H3 AV sink must declare cardinality one")

    hard = [item for item in anchors if item["classification"] == "hard_conditioned" and (branch != "source_backed_v2v" or any(t.get("modality") == "image" and str(t.get("id", t.get("occurrence_id"))) == str(item["id"]) for t in timeline_items))]
    if branch in {"source_free", "audio_only"}:
        latent = [
            _lineage_item("110", "110.1", "empty_av_latent", None),
            _lineage_item("c3-av-mask", "c3-av-mask.0", "nested_av_mask", "110.1"),
        ]
    elif branch == "source_backed_v2v":
        latent = [
            _lineage_item("110", "110.1", "empty_av_latent", None),
            _lineage_item("c3-full-source-v2v", "c3-full-source-v2v.0", "source_av_context", "110.1"),
            _lineage_item("c3-av-mask", "c3-av-mask.0", "nested_av_mask", "c3-full-source-v2v.0"),
        ]
    else:
        latent = [
            _lineage_item("103", "103.0", "source_av_context", None),
            _lineage_item("c3-av-mask", "c3-av-mask.0", "nested_av_mask", "103.0"),
        ]
    if hard:
        latent.append(_lineage_item("c3-hard-anchors", "c3-hard-anchors.0", "hard_anchor", "c3-av-mask.0"))
    conditioning = [
        _lineage_item(
            "110",
            "110.0",
            "reference_conditioning" if references else "prompt_conditioning",
            None,
        )
    ]
    active_soft = [item for item in anchors if item.get("classification") == "soft_conditioned" and (branch != "source_backed_v2v" or any(t.get("modality") == "image" and str(t.get("id", t.get("occurrence_id"))) == str(item["id"]) for t in timeline_items))]
    if active_soft:
        conditioning.append(_lineage_item("c3-soft-anchors", "c3-soft-anchors.0", "soft_keyframe", conditioning[-1]["output"] if conditioning else "110.0"))
    conditioning.extend(_lineage_item(f"c3-motion-guide-{index}", f"c3-motion-guide-{index}.0", "motion_context", conditioning[-1]["output"] if conditioning else "110.0") for index, _ in enumerate(guides))
    final_conditioning = conditioning[-1]["output"] if conditioning else "110.0"
    guider_output = "121.0"
    sampler_state = {
        "sampler": "SamplerCustomAdvanced",
        "nodes": actual_nodes,
        "latent_lineage": latent,
        "conditioning_lineage": conditioning,
        "guider": {"node": "121", "conditioning_source": final_conditioning, "output": guider_output},
        "sampler_sockets": {
            "noise": "120.0",
            "guider": guider_output,
            "sampler": "937.0",
            "sigmas": "976.0",
            "latent_image": latent[-1]["output"],
        },
    }
    required_latent = {"nested_av_mask"}
    if branch in {"source_free", "audio_only"}:
        required_latent.add("empty_av_latent")
    else:
        required_latent.add("source_av_context")
    if hard:
        required_latent.add("hard_anchor")
    required_conditioning: set[str] = set()
    if guides:
        required_conditioning.add("motion_context")
    if references:
        required_conditioning.add("reference_conditioning")
    if active_soft:
        required_conditioning.add("soft_keyframe")
    try:
        validation = validate_final_sampler_state(
            sampler_state,
            required_latent_kinds=required_latent,
            required_conditioning_kinds=required_conditioning,
        )
    except H3KernelContractError as exc:
        raise GraphBindingError(str(exc)) from exc

    binding = {
        "schema_version": GRAPH_SCHEMA_VERSION,
        "kind": "h3_av_graph_binding",
        "profile": "h3_av.native.v2",
        "branch": branch,
        "request_digest": request.digest,
        "source_baseline_digest": source_digest,
        "prepared_artifact_digest": prepared_artifact_digest,
        "native_geometry": geometry,
        "pinned_native_schema": {
            "comfy_commit": PINNED_COMFY_COMMIT,
            "node": "MiniMaxH3ReferenceToVideo",
            "dynamic_capacities": dict(H3_REFERENCE_CAPACITIES),
        },
        "pinned_seitanism": {
            "url": PINNED_SEITANISM_URL,
            "commit": PINNED_SEITANISM_COMMIT,
            "requirement": PINNED_SEITANISM_REQUIREMENT,
        },
        "inputs": {
            "references": references,
            "reference_edges": reference_plan,
            "timeline_loaders": timeline_loader_bindings,
            "audio_baselines": audio_baseline_bindings,
            "guides": guides,
            "settings": dict(request.value.get("settings", {})),
            "masks": {
                "video": video_masks,
                "audio": audio_masks,
                "video_policy": (
                    "all_generate_native_padding"
                    if branch in {"source_free", "audio_only"}
                    else ("preserve_existing" if audio_only else "prepared_sampling")
                ),
                "audio_policy": "all_generate_native_padding" if branch == "source_free" else "prepared_sampling",
                "exact_delivery_outside_latent": True,
            },
            "reference_audio_policy": [
                {"id": item["id"], "modality": item["modality"], "audio": item["audio"]} for item in references
            ],
        },
        "anchors": anchors,
        "sampler_state": sampler_state,
        "executable_graph": {
            "format": "vibe_envelope",
            "envelope": envelope,
            "compiled_api": compiled,
            "nodes": actual_nodes,
            "edges": actual_edges,
            "outputs": output_descriptors,
            "final_sampler": {"node": "124", "guider": "121", "output": expected_sink},
        },
        "shared_components": {
            "loaders": "shared_h3_av_media_loaders",
            "settings": dict(request.value.get("settings", {})),
            "sampler": {
                "class_type": "SamplerCustomAdvanced",
                "socket_lineage": dict(sampler_state["sampler_sockets"]),
            },
            "finishing": {
                "output_contract": "one_public_muxed_av",
                "composition_boundary": "astrid_exact_delivery_restoration",
            },
        },
        "final_sampler_validation": validation,
        "delivery_domains": {"video": video_record.get("shape"), "audio": audio_record.get("shape")},
    }
    if artifact.get("kind") == "h3_prepared_av_mask":
        validate_prepared_mask_references(binding, artifact)
    binding["bundle_identity"] = _digest({key: value for key, value in binding.items() if key != "bundle_identity"})
    validate_h3_graph_binding(binding)
    return binding


__all__ = [
    "GRAPH_SCHEMA_VERSION",
    "GraphBindingError",
    "H3_REFERENCE_CAPACITIES",
    "PINNED_COMFY_COMMIT",
    "PINNED_SEITANISM_COMMIT",
    "PINNED_SEITANISM_REQUIREMENT",
    "PINNED_SEITANISM_URL",
    "build_h3_graph_binding",
    "validate_h3_graph_binding",
]
