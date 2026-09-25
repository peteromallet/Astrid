"""Compile honest H3 audiovisual requests into sealed VibeComfy bindings."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from astrid.packs.vibecomfy.asset_manifest import (
    AssetManifestError,
    build_asset_manifest,
)

from .request import H3Request, normalize_request
from .timing import ContinuationTimingError, plan_continuation


class CompilationError(ValueError):
    """A prepared request cannot be represented by the selected H3 graph."""


_PROFILE_ID = "h3_av.native.v1"
_LANPAINT_WORKFLOW = Path("workflows/lanpaint_h3_av_generalized")
_NATIVE_WORKFLOW = Path("workflows/native_h3_continuation")
_REFERENCE_WORKFLOW = Path("workflows/native_h3_continuation_refs")
_DEFAULTS = {
    "model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "steps": 8,
    "seed": 123456789,
    "sampler": "res_multistep",
    "guidance": 0.95,
}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _resolved_request(preparation: Mapping[str, Any]) -> H3Request:
    if preparation.get("kind") != "h3_av_preparation":
        raise CompilationError("preparation.kind must be h3_av_preparation")
    if preparation.get("status") != "prepared" or preparation.get("runtime_submission") != "eligible":
        raise CompilationError("preparation is not eligible for runtime submission")
    raw = preparation.get("request")
    if not isinstance(raw, Mapping):
        raise CompilationError("preparation is missing its normalized request")
    request = normalize_request(raw)
    if request.digest != preparation.get("request_digest"):
        raise CompilationError("preparation request digest does not match its request")
    return request


def _asset_paths(preparation: Mapping[str, Any]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    records = preparation.get("assets")
    if not isinstance(records, list):
        raise CompilationError("preparation.assets must be an array")
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or not isinstance(record.get("asset"), str):
            raise CompilationError(f"preparation.assets[{index}] is malformed")
        asset_id = str(record["asset"])
        if record.get("status") != "resolved" or not isinstance(record.get("path"), str):
            raise CompilationError(f"asset {asset_id!r} is unresolved")
        path = Path(record["path"]).expanduser().resolve()
        if path.is_symlink() or not path.is_file():
            raise CompilationError(f"asset {asset_id!r} is not a regular file")
        if record.get("sha256") != _sha256(path) or record.get("size") != path.stat().st_size:
            raise CompilationError(f"asset {asset_id!r} changed after preparation")
        previous = result.get(asset_id)
        if previous is not None and previous != path:
            raise CompilationError(f"asset {asset_id!r} resolves to multiple files")
        result[asset_id] = path
    return result


def _asset_member(binding: str, path: Path, digest: str) -> str:
    suffix = path.suffix.lower()
    safe = "".join(character if character.isalnum() or character in "._-" else "-" for character in path.stem).strip(".-")
    safe = safe or binding.replace("/", "-") or "asset"
    return f"assets/{digest[:16]}-{safe}{suffix}"


def _write_asset_bundle(
    path: Path,
    bindings: Mapping[str, Path],
    *,
    workflow_inputs: Mapping[str, Any] | None = None,
    lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        manifest = build_asset_manifest(
            bindings,
            workflow_inputs=workflow_inputs,
            lineage=lineage,
        )
    except AssetManifestError as exc:
        raise CompilationError(str(exc)) from exc
    payloads: list[tuple[str, bytes]] = []
    seen_members: set[str] = set()
    for record in manifest["assets"]:
        member = str(record["member"])
        source = Path(bindings[str(record["binding"])])
        if member not in seen_members:
            payloads.append((member, source.read_bytes()))
            seen_members.add(member)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for member, data in [("manifest.json", _canonical_bytes(manifest)), *payloads]:
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, data)
    return manifest


def _copy_workflow_bundle(resource_root: Path, destination: Path) -> dict[str, Path]:
    members = {name: resource_root / name for name in ("workflow.py", "workflow.vibe.json", "source.json")}
    for name, member in members.items():
        if not member.is_file():
            raise CompilationError(f"selected packaged workflow is missing {name}")
    destination.mkdir(parents=True, exist_ok=True)
    frozen: dict[str, Path] = {}
    for name, source in members.items():
        target = destination / name
        shutil.copy2(source, target)
        if _sha256(target) != _sha256(source):
            raise CompilationError(f"copied workflow member {name} failed integrity validation")
        frozen[name] = target
    return frozen


def _member_by_binding(manifest: Mapping[str, Any]) -> dict[str, str]:
    records = manifest.get("assets")
    if not isinstance(records, list):
        raise CompilationError("managed asset manifest is malformed")
    return {str(record["binding"]): PurePosixPath(str(record["member"])).name for record in records}


def _asset_bindings(request: H3Request, assets: Mapping[str, Path], *, include_masks: bool = False) -> tuple[dict[str, Path], dict[str, str]]:
    value = request.value
    bindings: dict[str, Path] = {}
    asset_binding: dict[str, str] = {}

    def add(asset_id: str, preferred: str) -> str:
        if asset_id not in assets:
            raise CompilationError(f"asset {asset_id!r} is missing from preparation")
        if asset_id in asset_binding:
            return asset_binding[asset_id]
        binding = preferred
        suffix = 1
        while binding in bindings:
            suffix += 1
            binding = f"{preferred}_{suffix}"
        bindings[binding] = assets[asset_id]
        asset_binding[asset_id] = binding
        return binding

    source = value.get("source")
    if isinstance(source, Mapping):
        add(str(source["asset"]), "source_video")
    for index, reference in enumerate(value["references"]):
        add(str(reference["asset"]), f"reference_{index}")
    if include_masks:
        for index, change in enumerate(value["changes"]["video"]):
            area = change.get("area", {})
            mask_id = change.get("mask_asset") or area.get("mask_asset")
            if mask_id:
                add(str(mask_id), f"video_mask_{index}")
        for index, change in enumerate(value["changes"]["audio"]):
            if change.get("mask_asset"):
                add(str(change["mask_asset"]), f"audio_mask_{index}")
    return bindings, asset_binding


def _request_dialogue_prompt(request: H3Request) -> str:
    prompt = request.value["content"]["prompt"]
    dialogue = [
        change for change in request.value["changes"]["audio"]
        if change.get("action") == "generate" and change.get("dialogue")
    ]
    if not dialogue:
        return prompt
    lines = [prompt, "", "Exact dialogue timing:"]
    lines.extend(f"{item['during'][0]:g}-{item['during'][1]:g}s: {item['dialogue']}" for item in dialogue)
    return "\n".join(lines)


def _frame_index(seconds: float, path: str) -> int:
    frame = round(seconds * 24)
    if abs(frame / 24 - seconds) > 1e-6:
        raise CompilationError(f"{path} must be aligned to the selected graph's 24 fps frame grid")
    return frame


def _lanpaint_masks(request: H3Request, *, asset_binding: Mapping[str, str], internal_full_frame: str, internal_preserve: str) -> tuple[str, str, dict[str, Any]]:
    value = request.value
    events: dict[int, str] = {0: internal_preserve}
    generated_video: list[list[float]] = []
    active_end = -1.0
    for index, change in enumerate(sorted(value["changes"]["video"], key=lambda item: item["during"])):
        if change["action"] != "generate":
            continue
        start, end = map(float, change["during"])
        if start < active_end:
            raise CompilationError("LanPaint compilation requires non-overlapping generated video intervals")
        area = change["area"]
        mask_id = change.get("mask_asset") or area.get("mask_asset")
        if area.get("full_frame"):
            binding = internal_full_frame if mask_id is None else asset_binding.get(str(mask_id))
        else:
            if mask_id is None:
                raise CompilationError(f"changes.video[{index}] regional edits require an explicit mask asset")
            binding = asset_binding.get(str(mask_id))
        if binding is None:
            raise CompilationError(f"video mask asset {mask_id!r} is missing from the managed asset bundle")
        start_frame = _frame_index(start, f"changes.video[{index}].during[0]")
        end_frame = _frame_index(end, f"changes.video[{index}].during[1]")
        if start_frame in events and events[start_frame] != internal_preserve:
            raise CompilationError("video mask keyframes collide on the 24 fps frame grid")
        events[start_frame] = binding
        if end_frame in events and events[end_frame] not in {internal_preserve, binding}:
            raise CompilationError("video mask keyframes collide on the 24 fps frame grid")
        events[end_frame] = internal_preserve
        active_end = end
        generated_video.append([start, end])

    audio_intervals: list[dict[str, float]] = []
    for index, change in enumerate(value["changes"]["audio"]):
        if change.get("mask_asset"):
            raise CompilationError(f"changes.audio[{index}].mask_asset is not an input of the LanPaint AV graph")
        if change.get("stem", "mix") != "mix":
            raise CompilationError(f"changes.audio[{index}].stem requires a real stem/separation graph")
        if change["action"] == "generate":
            start, end = map(float, change["during"])
            audio_intervals.append({"start": start, "end": end})
    keyframes = json.dumps({str(frame): events[frame] for frame in sorted(events)}, separators=(",", ":"))
    intervals = json.dumps(audio_intervals, separators=(",", ":"))
    return keyframes, intervals, {"video": generated_video, "audio": [[x["start"], x["end"]] for x in audio_intervals]}


def _require_lanpaint(request: H3Request) -> None:
    value = request.value
    if value["operation"] != "edit":
        raise CompilationError("the LanPaint graph is selected only for source-backed operation=edit")
    source = value.get("source")
    duration = value.get("output", {}).get("duration")
    if not isinstance(source, Mapping) or "range" not in source:
        raise CompilationError("LanPaint source-backed edits require source.range")
    if duration is None or source["range"][0] != 0 or float(source["range"][1]) != float(duration):
        raise CompilationError("LanPaint requires source.range=[0, output.duration]; arbitrary source windows are unsupported")
    if value["references"]:
        raise CompilationError("the LanPaint AV graph has no reference-image input")
    for name in ("sampler", "guidance"):
        if name in value["overrides"] and value["overrides"][name] != _DEFAULTS[name]:
            raise CompilationError(f"overrides.{name} is not a public input of the LanPaint graph")


def _require_native(request: H3Request) -> tuple[float, float]:
    value = request.value
    if value["operation"] != "continue":
        raise CompilationError("native Seitanism graphs support operation=continue only")
    source = value.get("source")
    if not isinstance(source, Mapping) or "range" not in source:
        raise CompilationError("native continuation requires source.range")
    source_start, source_end = map(float, source["range"])
    duration = value.get("output", {}).get("duration")
    if source_start != 0 or duration is None or float(duration) <= source_end:
        raise CompilationError("native continuation requires source.range starting at 0 and output.duration greater than its end")
    suffix = [source_end, float(duration)]
    video = value["changes"]["video"]
    audio = value["changes"]["audio"]
    if len(video) != 1 or video[0].get("during") != suffix or video[0].get("area") != {"full_frame": True} or video[0].get("action") != "generate" or video[0].get("mask_asset"):
        raise CompilationError("native continuation requires one full-frame generated video suffix")
    if len(audio) != 1 or audio[0].get("during") != suffix or audio[0].get("action") != "generate":
        raise CompilationError("native continuation requires one generated audio suffix matching the video suffix")
    if audio[0].get("mask_asset") or audio[0].get("stem", "mix") != "mix":
        raise CompilationError("native continuation has no independent audio mask or stem binding")
    for reference in value["references"]:
        if reference["purpose"] == "audio":
            raise CompilationError("native reference slots are image references; audio references are unsupported")
    for name in ("sampler", "guidance"):
        if name in value["overrides"] and value["overrides"][name] != _DEFAULTS[name]:
            raise CompilationError(f"overrides.{name} is not a public input of the native graph")
    return source_end, float(duration)


def _compile_manifest(
    *,
    request: H3Request,
    destination: Path,
    resource_root: Path,
    workflow_inputs: dict[str, Any],
    asset_bindings: Mapping[str, Path],
    capabilities: Mapping[str, Any],
    limitations: list[str],
    asset_lineage: Mapping[str, Any] | None = None,
    continuation_timing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    public_generation = capabilities.get("public_generation")
    if not isinstance(public_generation, Mapping):
        raise CompilationError("selected H3 graph is missing its sealed public generation contract")
    selectors = public_generation.get("selectors")
    if not isinstance(selectors, list) or not selectors:
        raise CompilationError("sealed H3 generation contract must declare at least one public selector")
    frozen = _copy_workflow_bundle(resource_root, destination / "workflow-bundle")
    managed_path = destination / "managed-assets.zip"
    asset_manifest = _write_asset_bundle(
        managed_path,
        asset_bindings,
        workflow_inputs=workflow_inputs,
        lineage=asset_lineage,
    )
    graph_identity = {name: {"path": str(frozen[name]), "sha256": _sha256(frozen[name])} for name in sorted(frozen)}
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3_av_compilation",
        "status": "compiled",
        "profile": _PROFILE_ID,
        "request_digest": request.digest,
        "workflow": graph_identity,
        "workflow_inputs": workflow_inputs,
        "managed_assets": {"path": str(managed_path), "sha256": _sha256(managed_path), "manifest": asset_manifest},
        "capabilities": dict(capabilities),
        "limitations": limitations,
    }
    if continuation_timing is not None:
        manifest["continuation_timing"] = dict(continuation_timing)
    digest_payload = {
        **{key: value for key, value in manifest.items() if key not in {"workflow", "managed_assets", "compilation_digest"}},
        "workflow": {name: {"sha256": value["sha256"]} for name, value in graph_identity.items()},
        "managed_assets": {"sha256": manifest["managed_assets"]["sha256"], "manifest": asset_manifest},
    }
    manifest["compilation_digest"] = hashlib.sha256(_canonical_bytes(digest_payload)).hexdigest()
    manifest_path = destination / "compilation.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _compile_native(request: H3Request, assets: Mapping[str, Path], destination: Path) -> dict[str, Any]:
    source_end, output_duration = _require_native(request)
    try:
        timing = plan_continuation(
            source_end=source_end,
            output_duration=output_duration,
        )
    except ContinuationTimingError as exc:
        raise CompilationError(str(exc)) from exc
    bindings, asset_binding = _asset_bindings(request, assets)
    reference_count = len(request.value["references"])
    if reference_count > 2:
        raise CompilationError("the selected Seitanism graph has two image-reference slots; more references cannot be bound")
    resource_root = _NATIVE_WORKFLOW if reference_count == 0 else _REFERENCE_WORKFLOW
    managed = dict(bindings)
    if "source_video" not in managed:
        raise CompilationError("source video is missing from the managed asset bundle")
    destination.mkdir(parents=True, exist_ok=True)
    asset_manifest = _write_asset_bundle(destination / "managed-assets.zip", managed)
    members = _member_by_binding(asset_manifest)
    workflow_inputs: dict[str, Any] = {
        "model": request.value["overrides"].get("model", _DEFAULTS["model"]),
        "seed": request.value["overrides"].get("seed", _DEFAULTS["seed"]),
        "steps": request.value["overrides"].get("steps", _DEFAULTS["steps"]),
        "prompt": _request_dialogue_prompt(request),
        # The graph duration controls raw H3 latent length. Its first 39
        # frames are preserved AV context, so the requested suffix alone can
        # produce a fully preserved no-op. Ask for enough raw capacity and
        # trim the H3 block-rounding tail during composition.
        "duration": timing.workflow_duration,
        "source_start": 0.0,
        "source_frames": timing.source_frames,
        "source_video": members["source_video"],
    }
    if reference_count:
        first = members[asset_binding[request.value["references"][0]["asset"]]]
        second = members[asset_binding[request.value["references"][1]["asset"]]] if reference_count == 2 else first
        workflow_inputs.update({"reference_0": first, "reference_1": second})
    return _compile_manifest(
        request=request,
        destination=destination,
        resource_root=_pack_root() / resource_root,
        workflow_inputs=workflow_inputs,
        asset_bindings=managed,
        capabilities={"operation": "continue", "prompt": "bound", "references": reference_count, "reference_capacity": 2, "video_mask": "full-frame generated suffix only", "audio_mask": "generated suffix only", "source_range": "bound to 24fps loader frame cap", "output_duration": "exact after deterministic tail trim", "output_contract": "muxed_av_full_timeline", "public_generation": {"modality": "video", "selectors": [{"selector": "main-0", "ordinal": 0, "variant_key": "original", "required": True}], "internal_outputs": []}, "overrides": ["model", "seed", "steps"]},
        limitations=["continuation is full-frame only; spatial continuation masks are not present in the Seitanism graph", "reference slots are image guidance only and support at most two references", "sampler and guidance remain graph constants", "H3 raw lengths are quantized to 5 + 17k frames; excess generated tail frames are removed during composition"],
        continuation_timing=timing.to_dict(),
    )


def _compile_lanpaint(request: H3Request, assets: Mapping[str, Path], destination: Path) -> dict[str, Any]:
    _require_lanpaint(request)
    bindings, asset_binding = _asset_bindings(request, assets, include_masks=True)
    resource_root = _pack_root() / _LANPAINT_WORKFLOW
    full_mask = resource_root / "mask_full_frame.png"
    preserve_mask = resource_root / "mask_preserve.png"
    if not full_mask.is_file() or not preserve_mask.is_file():
        raise CompilationError("packaged LanPaint mask resources are missing")
    bindings["mask_full_frame"] = full_mask
    bindings["mask_preserve"] = preserve_mask
    keyframes, audio_intervals, schedule = _lanpaint_masks(request, asset_binding=asset_binding, internal_full_frame="mask_full_frame", internal_preserve="mask_preserve")
    asset_manifest = _write_asset_bundle(destination / "managed-assets.zip", bindings)
    members = _member_by_binding(asset_manifest)
    source_id = request.value["source"]["asset"]
    workflow_inputs = {
        "model": request.value["overrides"].get("model", "minimax_h3_fl2va_pruned_fp8_scaled.safetensors"),
        "steps": request.value["overrides"].get("steps", 20),
        "seed": request.value["overrides"].get("seed", 0),
        "prompt": _request_dialogue_prompt(request),
        "duration": float(request.value["output"]["duration"]),
        "source_video": members["source_video"],
        "mask_keyframes": json.dumps({str(k): members.get(v, v) for k, v in json.loads(keyframes).items()}, separators=(",", ":")),
        "audio_intervals": audio_intervals,
    }
    result = _compile_manifest(
        request=request,
        destination=destination,
        resource_root=resource_root,
        workflow_inputs=workflow_inputs,
        asset_bindings=bindings,
        capabilities={"operation": "edit", "prompt": "bound", "source_range": request.value["source"]["range"], "output_duration": float(request.value["output"]["duration"]), "video_mask": "LanPaint frame keyframes", "audio_mask": "independent sample intervals", "references": 0, "output_contract": "separate_av_full_timeline", "public_generation": {"modality": "video", "selectors": [{"selector": "main-0", "ordinal": 0, "variant_key": "original", "required": True}], "internal_outputs": ["audio"]}, "overrides": ["model", "seed", "steps"]},
        limitations=["regional masks must be supplied image masks; rectangle, polygon, and semantic regions are not rasterized", "source-backed edits use source.range=[0, output.duration] because LanPaint has no arbitrary source-window input", "audio stems and audio mask assets require a separator graph"],
    )
    result["mask_schedule"] = schedule
    return result


def compile_preparation(preparation: Mapping[str, Any], *, out_dir: str | Path) -> dict[str, Any]:
    """Compile one prepared request into immutable runtime bindings and assets."""
    request = _resolved_request(preparation)
    assets = _asset_paths(preparation)
    destination = Path(out_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    if request.value["operation"] == "generate":
        return _compile_generation(request, assets, destination)
    if request.value["operation"] == "edit":
        return _compile_lanpaint(request, assets, destination)
    if request.value["operation"] == "continue":
        return _compile_native(request, assets, destination)
    raise CompilationError(f"unsupported H3 operation: {request.value['operation']!r}")


def _compile_generation(request: H3Request, assets: Mapping[str, Path], destination: Path) -> dict[str, Any]:
    from PIL import Image
    from vibecomfy.security.provenance import Provenance
    from vibecomfy.workflow_bundle import emit_bundle
    from .generation import IMAGE_REFERENCE_CAPACITY, build_generation_workflow, generation_timing

    references = request.value["references"]
    # Keep slots ordered even for repeated assets; the archive deduplicates bytes.
    bindings = {f"reference_{index}": assets[item["asset"]] for index, item in enumerate(references)}
    for binding, path in bindings.items():
        try:
            with Image.open(path) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise CompilationError(f"{binding} must be a still image")
                image.verify()
        except (OSError, ValueError) as exc:
            raise CompilationError(f"{binding} must be a decodable still image") from exc
    manifest = _write_asset_bundle(destination / "managed-assets.zip", bindings)
    members = _member_by_binding(manifest)
    settings = {**_DEFAULTS, **request.value["overrides"]}
    timing = generation_timing(request.value["output"]["duration"])
    prompt = request.value["content"]["prompt"]
    graph = build_generation_workflow(references=list(members.values()), prompt=prompt,
                                      frames=timing["raw_frames"], **settings)
    if len(graph.outputs) != 1 or graph.outputs[0].expected_cardinality != "one":
        raise CompilationError("generation adapter must expose exactly one output")
    resource = destination / "generation-bundle"
    emit_bundle(graph, resource / "workflow.py", provenance=Provenance.AGENT_AUTHORED)
    (resource / "source.json").write_text(json.dumps({
        "kind": "authored_h3_reference_adapter", "node": "MiniMaxH3ReferenceToVideo",
        "comfy_commit": "ee71d5c4993f29086b27fde1629a945ae48425bf",
    }, sort_keys=True) + "\n")
    return _compile_manifest(
        request=request, destination=destination, resource_root=resource,
        workflow_inputs={**settings, "prompt": prompt, **members}, asset_bindings=bindings,
        capabilities={
            "operation": "generate", "reference_capacity": IMAGE_REFERENCE_CAPACITY,
            "references": len(references), "reference_order": [item["asset"] for item in references],
            "reference_binding": "ordered image conditioning; Picture 1..N",
            "generation_timing": timing, "output_contract": "muxed_av_full_timeline",
            "public_generation": {"modality": "video", "selectors": [
                {"selector": "main-0", "ordinal": 0, "variant_key": "original", "required": True}],
                "internal_outputs": []},
            "validation": "CPU structural; live GPU acceptance pending",
        },
        limitations=["image references only; no timed keyframes or source-free masks", "single pass, up to 362 frames at 24 fps"],
    )


__all__ = ["CompilationError", "compile_preparation"]
