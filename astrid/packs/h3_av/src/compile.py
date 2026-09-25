"""Compile honest H3 audiovisual requests into sealed VibeComfy bindings."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from astrid.packs.vibecomfy.asset_manifest import (
    AssetManifestError,
    build_asset_manifest,
)

from .graph import GraphBindingError, _branch, build_h3_graph_binding, require_supported_source_timeline, validate_h3_graph_binding
from .masks import PreparedAVMaskError, load_prepared_av_mask
from .output_contract import build_output_contract, validate_output_contract
from .request import H3Request, read_prepared_request


class CompilationError(ValueError):
    """A prepared request cannot be represented by the selected H3 graph."""


_PROFILE_ID = "h3_av.native.v1"
_LEGACY_WORKFLOW_RELATIVE = Path("workflows/seitanism_h3_av_extension_repaired")
_LANPAINT_WORKFLOW = Path("workflows/lanpaint_h3_av_generalized")
_NATIVE_WORKFLOW = Path("workflows/native_h3_continuation")
_REFERENCE_WORKFLOW = Path("workflows/native_h3_continuation_refs")
_DEFAULT_PROMPT = (
    'End state: Morpheus remains in the same close/medium shot, seated in the red chair in the dark room, '
    'wearing the black coat, with the same camera position, lighting, identity, and acoustic perspective. '
    'In the generated continuation, he begins by saying the exact line: "This is your last chance." He then '
    'continues with the exact line: "You can poo or pee on my face." Preserve the supplied audiovisual prefix, '
    "including Morpheus's original voice, cadence, room tone, and timing, then carry that voice and acoustic "
    'perspective into both requested lines. Keep his expression calm and deliberate, looking forward with one '
    'hand resting in a restrained natural gesture. No camera change, reset, new character, subtitles, or visible text.'
)
_DEFAULTS = {
    "model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
    "steps": 8,
    "seed": 123456789,
    "sampler": "res_multistep",
    "guidance": 0.95,
}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


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
    if raw.get("operation") == "generate":
        raise CompilationError(
            "source-free operation=generate is not admitted: this pack has no "
            "verified source-free H3 graph"
        )
    try:
        return read_prepared_request(
            raw,
            preparation.get("request_digest"),
            require_normalized_v2=True,
        )
    except (TypeError, ValueError) as exc:
        raise CompilationError(f"preparation request is invalid: {exc}") from exc


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


def _is_legacy_request(request: H3Request) -> bool:
    value = request.value
    return (
        value["operation"] == "continue"
        and value.get("source", {}).get("range") == [0.0, 4.0]
        and value.get("output", {}).get("duration") == 8.0
        and value["references"] == []
        and value["changes"]["video"] == [{"during": [4.0, 8.0], "area": {"full_frame": True}, "action": "generate"}]
        and value["changes"]["audio"] == [{"during": [4.0, 8.0], "action": "generate"}]
    )


def _legacy_require(request: H3Request) -> None:
    _require_native(request)
    if request.value["references"]:
        raise CompilationError("the legacy repaired Existing Video path has no reference binding")
    if request.value["content"]["prompt"] != _DEFAULT_PROMPT:
        raise CompilationError("the legacy repaired bundle embeds a fixed prompt")


def _compile_manifest(*, request: H3Request, destination: Path, resource_root: Path, workflow_inputs: dict[str, Any], asset_bindings: Mapping[str, Path], capabilities: Mapping[str, Any], limitations: list[str], graph_outputs: list[Mapping[str, Any]], asset_lineage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    frozen = _copy_workflow_bundle(resource_root, destination / "workflow-bundle")
    managed_path = destination / "managed-assets.zip"
    asset_manifest = _write_asset_bundle(
        managed_path,
        asset_bindings,
        workflow_inputs=workflow_inputs,
        lineage=asset_lineage,
    )
    output_contract = build_output_contract(graph_outputs)
    graph_identity = {name: {"path": str(frozen[name]), "sha256": _sha256(frozen[name])} for name in sorted(frozen)}
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "kind": "h3_av_compilation",
        "status": "compiled",
        "profile": _PROFILE_ID,
        "request_digest": request.digest,
        "workflow": graph_identity,
        "workflow_inputs": workflow_inputs,
        "output_contract": output_contract,
        "managed_assets": {"path": str(managed_path), "sha256": _sha256(managed_path), "manifest": asset_manifest},
        "capabilities": dict(capabilities),
        "limitations": limitations,
    }
    digest_payload = {
        **{key: value for key, value in manifest.items() if key not in {"workflow", "managed_assets", "compilation_digest"}},
        "workflow": {name: {"sha256": value["sha256"]} for name, value in graph_identity.items()},
        "managed_assets": {"sha256": manifest["managed_assets"]["sha256"], "manifest": asset_manifest},
        "output_contract": output_contract,
    }
    manifest["compilation_digest"] = hashlib.sha256(_canonical_bytes(digest_payload)).hexdigest()
    validate_output_contract(manifest["output_contract"])
    manifest_path = destination / "compilation.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def _compile_legacy(request: H3Request, assets: Mapping[str, Path], destination: Path) -> dict[str, Any]:
    _legacy_require(request)
    source_id = request.value["source"]["asset"]
    if source_id not in assets:
        raise CompilationError(f"source asset {source_id!r} is missing from preparation")
    source_member = PurePosixPath(_asset_member("source_video", assets[source_id], _sha256(assets[source_id]))).name
    return _compile_manifest(
        request=request,
        destination=destination,
        resource_root=_repo_root() / _LEGACY_WORKFLOW_RELATIVE,
        workflow_inputs={"model": request.value["overrides"].get("model", _DEFAULTS["model"]), "seed": request.value["overrides"].get("seed", _DEFAULTS["seed"]), "source_video": source_member, "steps": request.value["overrides"].get("steps", _DEFAULTS["steps"])},
        asset_bindings={"source_video": assets[source_id]},
        graph_outputs=[{"name": "continuation", "modality": "video", "expected_cardinality": "one"}],
        capabilities={"operation": "continue", "prompt": "fixed-canonical", "references": 0, "video_mask": "full-frame generated suffix only", "audio_mask": "generated suffix only", "overrides": ["model", "seed", "steps"]},
        limitations=["legacy compatibility route; generalized bindings use the packaged native workflow", "references, regional masks, audio masks, sampler, and guidance are not represented by this legacy graph"],
    )


def _compile_native(request: H3Request, assets: Mapping[str, Path], destination: Path) -> dict[str, Any]:
    source_end, output_duration = _require_native(request)
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
        "duration": output_duration - source_end,
        "source_start": 0.0,
        "source_frames": _frame_index(source_end, "source.range[1]"),
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
        graph_outputs=[{"name": "continuation", "modality": "video", "expected_cardinality": "one"}],
        capabilities={"operation": "continue", "prompt": "bound", "references": reference_count, "reference_capacity": 2, "video_mask": "full-frame generated suffix only", "audio_mask": "generated suffix only", "source_range": "bound to 24fps loader frame cap", "output_duration": "bound as generated suffix duration", "overrides": ["model", "seed", "steps"]},
        limitations=["continuation is full-frame only; spatial continuation masks are not present in the Seitanism graph", "reference slots are image guidance only and support at most two references", "sampler and guidance remain graph constants"],
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
        graph_outputs=[
            {"name": "video", "modality": "video", "expected_cardinality": "one"},
            {"name": "audio", "modality": "audio", "expected_cardinality": "one"},
        ],
        capabilities={"operation": "edit", "prompt": "bound", "source_range": request.value["source"]["range"], "output_duration": float(request.value["output"]["duration"]), "video_mask": "LanPaint frame keyframes", "audio_mask": "independent sample intervals", "references": 0, "overrides": ["model", "seed", "steps"]},
        limitations=["regional masks must be supplied image masks; rectangle, polygon, and semantic regions are not rasterized", "source-backed edits use source.range=[0, output.duration] because LanPaint has no arbitrary source-window input", "audio stems and audio mask assets require a separator graph"],
    )
    result["mask_schedule"] = schedule
    return result


def _is_prepared_v2(preparation: Mapping[str, Any]) -> bool:
    """Recognize T2's prepared-input handoff without changing its schema."""

    raw = preparation.get("request")
    if isinstance(raw, Mapping) and raw.get("version") == 2:
        return True
    for key in ("prepared_input", "prepared_av_mask", "prepared"):
        artifact = preparation.get(key)
        if isinstance(artifact, Mapping):
            raw = artifact.get("request")
            if isinstance(raw, Mapping) and raw.get("version") == 2:
                return True
    return preparation.get("kind") in {"h3_av_prepared_input", "h3_av_prepared_av_mask"}


def _prepared_asset_paths(preparation: Mapping[str, Any]) -> dict[str, Path]:
    """Stage only resolved T2 assets; managed identifiers remain logical inputs."""

    records = preparation.get("assets", [])
    if not isinstance(records, list):
        raise CompilationError("prepared input assets must be an array")
    result: dict[str, Path] = {}
    for index, record in enumerate(records):
        if not isinstance(record, Mapping) or not isinstance(record.get("asset"), str):
            raise CompilationError(f"prepared input assets[{index}] is malformed")
        if record.get("status") != "resolved":
            continue
        path_value = record.get("path")
        if not isinstance(path_value, str):
            raise CompilationError(f"prepared input asset {record['asset']!r} has no path")
        path = Path(path_value).expanduser().resolve()
        if path.is_symlink() or not path.is_file():
            raise CompilationError(f"prepared input asset {record['asset']!r} is not a regular file")
        if record.get("sha256") != _sha256(path) or record.get("size") != path.stat().st_size:
            raise CompilationError(f"prepared input asset {record['asset']!r} changed after preparation")
        result[str(record["asset"])] = path
    return result


def _prepared_artifact_manifest(preparation: Mapping[str, Any]) -> dict[str, Any] | None:
    """Reload T2's real artifact and return its canonical manifest."""

    candidate = preparation.get("prepared_av_mask")
    if not isinstance(candidate, Mapping):
        for key in ("prepared_input", "prepared"):
            nested = preparation.get(key)
            if isinstance(nested, Mapping) and nested.get("kind") == "h3_prepared_av_mask":
                candidate = nested
                break
    if not isinstance(candidate, Mapping) or candidate.get("kind") != "h3_prepared_av_mask":
        return None
    try:
        return load_prepared_av_mask(candidate).to_manifest()
    except PreparedAVMaskError as exc:
        raise CompilationError(str(exc)) from exc


def _write_mask_video(path: Path, frames: Any, *, rate: int) -> Path:
    """Encode a binary MASK stream as one lossless, managed video input."""

    rows = list(frames)
    if not rows:
        raise CompilationError("prepared H3 mask stream is empty")
    height = len(rows[0])
    width = len(rows[0][0])
    if height < 1 or width < 1 or any(len(frame) != height for frame in rows):
        raise CompilationError("prepared H3 mask stream has invalid geometry")
    raw = bytearray()
    for frame in rows:
        if any(len(row) != width for row in frame for _ in (0,)):
            raise CompilationError("prepared H3 mask stream is not rectangular")
        raw.extend(255 if int(value) else 0 for row in frame for value in row)
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{width}x{height}",
        "-r", str(rate), "-i", "pipe:0", "-an", "-c:v", "ffv1", "-pix_fmt", "gray",
        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-map_metadata", "-1",
        "-metadata", "creation_time=0", str(path),
    ]
    try:
        subprocess.run(command, input=bytes(raw), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CompilationError(f"could not materialize prepared H3 mask video: {exc}") from exc
    return path


def _compile_prepared_v2(preparation: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    """Compile one T2 artifact into the shared Astrid H3 graph boundary."""
    try:
        raw = preparation.get("request")
        expected_digest = preparation.get("request_digest")
        if not isinstance(raw, Mapping):
            for key in ("prepared_input", "prepared_av_mask", "prepared"):
                candidate = preparation.get(key)
                if isinstance(candidate, Mapping) and isinstance(candidate.get("request"), Mapping):
                    raw = candidate["request"]
                    expected_digest = expected_digest or candidate.get("request_digest")
                    break
        if isinstance(raw, Mapping):
            request = read_prepared_request(
                raw,
                expected_digest,
                require_normalized_v2=True,
            )
            require_supported_source_timeline(request)
    except (GraphBindingError, TypeError, ValueError) as exc:
        raise CompilationError(str(exc)) from exc
    destination.mkdir(parents=True, exist_ok=True)
    assets = _prepared_asset_paths(preparation)
    prepared_manifest = _prepared_artifact_manifest(preparation)
    if prepared_manifest is None:
        raise CompilationError("prepared-input artifact is missing")
    prepared_path: Path | None = None
    mask_paths: dict[str, Path] = {}
    if prepared_manifest is not None:
        prepared_path = destination / "prepared-av-mask.json"
        prepared_path.write_text(json.dumps(prepared_manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        from .masks import load_prepared_av_mask

        prepared = load_prepared_av_mask(prepared_path)
        import numpy as np
        from .kernel import temporal_cells

        frames, height, width = prepared.video_shape
        native_frames = max(5, frames)
        while native_frames % 17 != 5:
            native_frames += 1
        latent_steps = 2 if native_frames <= 5 else ((native_frames - 5) // 17) * 5 + 2
        latent_height, latent_width = height // 16, width // 16
        if min(latent_height, latent_width) < 1 or height % 16 or width % 16:
            raise CompilationError("H3 video mask geometry must be divisible by 16")
        flat = np.unpackbits(np.frombuffer(prepared.video_payload, dtype=np.uint8), bitorder="big")
        delivery = flat[:frames * height * width].reshape((frames, height, width))
        cells = np.zeros((latent_steps, latent_height, latent_width), dtype=np.uint8)
        for cell in temporal_cells(latent_steps):
            start, end = cell["start"], min(cell["end"], frames)
            if start >= end:
                continue
            spatial = delivery[start:end].max(axis=0)
            for row in range(latent_height):
                y0, y1 = row * height // latent_height, (row + 1) * height // latent_height
                for column in range(latent_width):
                    x0, x1 = column * width // latent_width, (column + 1) * width // latent_width
                    cells[cell["cell"], row, column] = spatial[y0:y1, x0:x1].max()
        mask_paths["prepared_video_mask"] = _write_mask_video(
            destination / "prepared-video-mask.mkv", cells.tolist(), rate=24,
        )
        native_audio_ticks = round(native_frames * 40 / 24)
        audio_ticks = list(prepared.audio_sampling_envelope())
        if len(audio_ticks) > native_audio_ticks:
            raise CompilationError("prepared audio mask exceeds native H3 audio grid")
        audio_ticks.extend([0] * (native_audio_ticks - len(audio_ticks)))
        mask_paths["prepared_audio_mask"] = _write_mask_video(
            destination / "prepared-audio-mask.mkv",
            tuple(((value,),) for value in audio_ticks),
            rate=40,
        )
    assets.update(mask_paths)
    baseline_binding = None
    if _branch(request) == "source_backed_v2v":
        from .baseline import BaselineError, encode_native_baseline, render_timeline_baseline

        native_frames = max(5, prepared.video_shape[0])
        while native_frames % 17 != 5:
            native_frames += 1
        try:
            with tempfile.TemporaryDirectory(prefix="h3-delivery-baseline-") as temp:
                video_raw, audio_raw = render_timeline_baseline(
                    preparation, prepared, Path(temp), native_frames=native_frames,
                )
                baseline_binding = "prepared_source_baseline"
                assets[baseline_binding] = encode_native_baseline(
                    video_raw, audio_raw, destination / "prepared-source-baseline.mkv",
                    frames=native_frames, width=prepared.video_shape[2], height=prepared.video_shape[1],
                )
        except BaselineError as exc:
            raise CompilationError(str(exc)) from exc
    # These are compilation provenance, not public graph inputs.  Keep their
    # witnesses in graph_binding/prepared_artifact metadata below.
    workflow_inputs: dict[str, Any] = {}
    asset_manifest = _write_asset_bundle(
        destination / "managed-assets.zip",
        assets,
        workflow_inputs=workflow_inputs,
        lineage={"prepared_input": preparation.get("request_digest")},
    )
    members = _member_by_binding(asset_manifest)
    asset_members = {asset_id: members[asset_id] for asset_id in _prepared_asset_paths(preparation) if asset_id in members}
    mask_members = {
        "video": members["prepared_video_mask"],
        "audio": members["prepared_audio_mask"],
    } if mask_paths else None
    try:
        graph_binding = build_h3_graph_binding(
            preparation,
            asset_members=asset_members,
            mask_members=mask_members,
            baseline_member=members.get(baseline_binding) if baseline_binding else None,
        )
    except GraphBindingError as exc:
        raise CompilationError(str(exc)) from exc
    graph_path = destination / "graph.vibe.json"
    graph_envelope = graph_binding["executable_graph"]["envelope"]
    graph_path.write_text(json.dumps(graph_envelope, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    binding_path = destination / "graph_binding.json"
    graph_binding["graph_path"] = str(graph_path)
    graph_binding["graph_sha256"] = _sha256(graph_path)
    try:
        validate_h3_graph_binding(graph_binding)
    except GraphBindingError as exc:
        raise CompilationError(str(exc)) from exc
    binding_path.write_text(json.dumps(graph_binding, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    graph_outputs = graph_binding["executable_graph"].get("outputs", [])
    if len(graph_outputs) != 1:
        raise CompilationError("the executable H3 graph must declare exactly one muxed AV output")
    output = graph_outputs[0]
    if output.get("artifact_kind") != "video" or output.get("mime_type") != "video/mp4":
        raise CompilationError("the executable H3 graph output is not the declared muxed MP4 artifact")
    output_contract = build_output_contract(
        [
            {
                "name": str(output.get("name") or "av"),
                "modality": "video",
                "expected_cardinality": "one",
                "sink_node": str(output["node_id"]),
                "mime_type": str(output["mime_type"]),
                "contains_audio": True,
            }
        ]
    )
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "kind": "h3_av_compilation",
        "status": "compiled",
        "profile": "h3_av.native.v2",
        "request_digest": graph_binding["request_digest"],
        "workflow_inputs": workflow_inputs,
        "graph_binding": {
            "path": str(binding_path),
            "relative_path": binding_path.name,
            "sha256": _sha256(binding_path),
            "bundle_identity": graph_binding["bundle_identity"],
        },
        "graph": {
            "path": str(graph_path),
            "relative_path": graph_path.name,
            "sha256": _sha256(graph_path),
        },
        "managed_assets": {
            "path": str(destination / "managed-assets.zip"),
            "relative_path": "managed-assets.zip",
            "sha256": _sha256(destination / "managed-assets.zip"),
            "manifest": asset_manifest,
        },
        "output_contract": output_contract,
        "capabilities": {
            "operation": "transform",
            "branch": graph_binding["branch"],
            "references": len(graph_binding["inputs"]["references"]),
            "reference_modalities": sorted({row["modality"] for row in graph_binding["inputs"]["references"]}),
            "mask_streams": ["video", "audio"],
            "exact_delivery_outside_latent": True,
        },
        "limitations": [
            "H3 audio sampling is a conservative joint envelope; exact channel/sample permissions remain for Astrid composition",
            "this CPU boundary proves serialized VibeWorkflow lineage and socket identity, not decoded equality, model quality, or GPU compatibility",
            "the packaged workflow requirement metadata is normalized at the VibeComfy envelope door because its legacy model/runtime representation is not accepted by the current public decoder",
        ],
    }
    if prepared_path is not None:
        manifest["prepared_artifact"] = {
            "path": str(prepared_path),
            "relative_path": prepared_path.name,
            "sha256": _sha256(prepared_path),
            "artifact_digest": prepared_manifest["artifact_digest"],
        }
    digest_payload = {
        key: value
        for key, value in manifest.items()
        if key not in {
            "graph",
            "graph_binding",
            "managed_assets",
            "prepared_artifact",
            "compilation_digest",
        }
    }
    digest_payload["graph_binding"] = {"bundle_identity": graph_binding["bundle_identity"]}
    digest_payload["managed_assets"] = {"sha256": manifest["managed_assets"]["sha256"], "manifest": asset_manifest}
    if prepared_path is not None:
        digest_payload["prepared_artifact"] = {
            "sha256": manifest["prepared_artifact"]["sha256"],
            "artifact_digest": manifest["prepared_artifact"]["artifact_digest"],
        }
    manifest["compilation_digest"] = hashlib.sha256(_canonical_bytes(digest_payload)).hexdigest()
    validate_output_contract(output_contract)
    manifest_path = destination / "compilation.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def compile_preparation(
    preparation: Mapping[str, Any],
    *,
    out_dir: str | Path,
    input_bundle: str | Path | None = None,
) -> dict[str, Any]:
    """Compile one prepared request into immutable runtime bindings and assets."""
    destination = Path(out_dir).expanduser().resolve()
    if input_bundle is not None:
        from .input_bundle import resolve_preparation_assets

        preparation = resolve_preparation_assets(
            preparation,
            input_bundle,
            destination / "input-assets",
        )
    if _is_prepared_v2(preparation):
        return _compile_prepared_v2(preparation, destination)
    request = _resolved_request(preparation)
    assets = _asset_paths(preparation)
    destination.mkdir(parents=True, exist_ok=True)
    if _is_legacy_request(request):
        return _compile_legacy(request, assets, destination)
    if request.value["operation"] == "edit":
        return _compile_lanpaint(request, assets, destination)
    if request.value["operation"] == "continue":
        return _compile_native(request, assets, destination)
    raise CompilationError(
        "source-free operation=generate is not admitted: this pack has no "
        "verified source-free H3 graph"
    )


__all__ = ["CompilationError", "compile_preparation"]
