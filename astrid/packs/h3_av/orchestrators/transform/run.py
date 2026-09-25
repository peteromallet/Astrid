"""SDK-connected H3 audiovisual transform orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main
from astrid.sdk import AstridClient
from astrid.packs.h3_av.src.input_bundle import bundle_digest, materialize_input_bundle
from astrid.packs.h3_av.src.output_contract import (
    generation_intent_from_contract,
    validate_output_contract,
)
from astrid.packs.h3_av.src.masks import PreparedAVMaskError, load_prepared_av_mask
from astrid.packs.h3_av.src.graph import (
    GraphBindingError,
    validate_h3_graph_binding,
    validate_prepared_mask_references,
)
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.h3_av.src.receipt import write_retrieval_receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded H3 audiovisual transform.")
    parser.add_argument("--request", type=Path, required=True)
    # --asset-map remains a short-lived compatibility alias for callers that
    # already pass a managed ZIP; it is not a JSON-path transport anymore.
    parser.add_argument("--input-bundle", "--asset-map", dest="input_bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--project")
    parser.add_argument("--execution-request", default="")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _json_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    return value


def _direct_output(result: Any, name: str) -> Path | None:
    outputs = getattr(result, "outputs", {})
    value = outputs.get(name) if isinstance(outputs, Mapping) else None
    candidates: list[Any] = [value]
    if isinstance(outputs, Mapping):
        candidates.extend(outputs.get(key, []) for key in ("artifacts", "managed_outputs"))
    raw = getattr(result, "raw_result", {})
    if isinstance(raw, Mapping):
        raw_outputs = raw.get("outputs")
        if isinstance(raw_outputs, Mapping):
            candidates.append(raw_outputs.get(name))
            candidates.append(raw_outputs.get("artifacts"))
        candidates.append(raw.get("managed_outputs"))
    flattened: list[Any] = []
    for candidate in candidates:
        if isinstance(candidate, list):
            flattened.extend(candidate)
        elif candidate is not None:
            flattened.append(candidate)
    for candidate in flattened:
        if isinstance(candidate, str):
            path = Path(candidate).expanduser()
            if path.is_file():
                return path.resolve()
        if isinstance(candidate, Mapping):
            candidate_name = candidate.get("name") or candidate.get("output_port")
            if candidate_name not in (None, name):
                continue
            raw_path = candidate.get("path") or candidate.get("local_path") or candidate.get("file")
            if isinstance(raw_path, str) and Path(raw_path).expanduser().is_file():
                return Path(raw_path).expanduser().resolve()
    return None


def _managed_rows(result: Any, name: str) -> list[Mapping[str, Any]]:
    outputs = getattr(result, "outputs", {})
    raw = getattr(result, "raw_result", {})
    values: list[Any] = []
    containers: list[Mapping[str, Any]] = []
    for container in (outputs, raw):
        if not isinstance(container, Mapping):
            continue
        containers.append(container)
        nested_outputs = container.get("outputs")
        if isinstance(nested_outputs, Mapping):
            containers.append(nested_outputs)
    for container in containers:
        for key in ("managed_outputs", "artifacts"):
            value = container.get(key)
            if isinstance(value, list):
                values.extend(value)
            elif isinstance(value, Mapping):
                values.extend(value.values())
    rows: list[Mapping[str, Any]] = []
    for value in values:
        if not isinstance(value, Mapping):
            continue
        row_name = value.get("name") or value.get("output_port")
        producer = value.get("producer")
        producer_port = producer.get("output_port") if isinstance(producer, Mapping) else None
        if row_name == name or (
            name == "vibecomfy_run"
            and row_name in {"vibecomfy_run", "generated_videos", "video", "audio"}
        ) or (
            name == "vibecomfy_run"
            and producer_port in {"video", "audio", "generated_video", "generated_audio"}
        ) or (
            name == "vibecomfy_run"
            and _output_role(value) in {"video", "audio"}
        ):
            rows.append(value)
    unique: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        producer = row.get("producer")
        producer_id = (
            producer.get("producer_output_id")
            if isinstance(producer, Mapping)
            else row.get("producer_output_id")
        )
        identity = producer_id or row.get("object_id") or row.get("digest") or row.get("content_hash")
        key = (str(identity), str(_output_role(row) or row.get("name") or row.get("output_port") or ""))
        if key not in seen:
            seen.add(key)
            unique.append(row)
    return unique


def _output_role(row: Mapping[str, Any]) -> str | None:
    """Return the producer-declared audiovisual role for one settled row."""

    producer = row.get("producer")
    producer_port = producer.get("output_port") if isinstance(producer, Mapping) else None
    port = producer_port or row.get("output_port") or row.get("role")
    if isinstance(port, str):
        if port in {"video", "generated_video", "generated_videos", "SaveVideo"}:
            return "video"
        if port in {"audio", "generated_audio", "generated_audios", "SaveAudio"}:
            return "audio"
    media_type = row.get("media_type")
    if not isinstance(media_type, str) and isinstance(producer, Mapping):
        media_type = producer.get("media_type")
    if isinstance(media_type, str):
        if media_type.startswith("video/"):
            return "video"
        if media_type.startswith("audio/"):
            return "audio"
    return None


def _digest(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get("object_id") or value.get("digest") or value.get("content_hash")
    if not isinstance(raw, str):
        return None
    normalized = raw.removeprefix("sha256:")
    return "sha256:" + normalized if re.fullmatch(r"[0-9a-f]{64}", normalized) else None


def _descriptor(row: Mapping[str, Any], *, filename: str) -> dict[str, Any]:
    object_id = _digest(row)
    if object_id is None:
        raise RuntimeError(f"managed artifact {filename!r} has no canonical object digest")
    return {
        "object_id": object_id,
        "digest": object_id,
        "filename": Path(filename).name,
        "required": True,
    }


def _import_runtime_file(client: Any, *, project: str | None, path: Path, filename: str) -> dict[str, Any]:
    """Upload an immutable local input through the connected Runtime client."""

    importer = getattr(getattr(client, "media", None), "import_file", None)
    if not callable(importer):
        raise RuntimeError("connected Runtime client cannot import a managed input")
    if not isinstance(project, str) or not project:
        current = getattr(getattr(client, "projects", None), "current", None)
        observed = current() if callable(current) else None
        data = getattr(observed, "data", observed)
        if isinstance(data, Mapping):
            project = str(data.get("project_id") or data.get("id") or "") or None
    if not project:
        raise RuntimeError("H3 transform requires a selected project to stage managed inputs")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    result = importer(
        project=project,
        path=path,
        idempotency_key=f"h3-av-input-{digest}",
    )
    if not getattr(result, "ok", False):
        raise RuntimeError(f"could not import managed H3 input {filename!r}: {getattr(result, 'error', result)}")
    data = getattr(result, "data", None)
    if not isinstance(data, Mapping):
        raise RuntimeError(f"managed H3 input {filename!r} returned no object descriptor")
    return _descriptor(data, filename=filename)


def _materialize_output(
    client: Any,
    result: Any,
    name: str,
    out_dir: Path,
    *,
    managed_only: bool = False,
    expected_filename: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    rows = _managed_rows(result, name)
    if not rows:
        raise RuntimeError(f"child {getattr(result, 'capability_id', '?')} did not return settled output {name!r}")
    # A primary result is authoritative; do not accidentally retrieve a JSON
    # receipt or an auxiliary output with the same task.
    row = next((item for item in rows if item.get("is_primary") or item.get("role") == "result"), rows[0])
    object_id = _digest(row)
    if object_id is None:
        raise RuntimeError(f"managed output {name!r} has no canonical object digest")
    data = client.media.read_bytes(object_id)
    if not isinstance(data, bytes):
        raise RuntimeError(f"managed output {name!r} did not return bytes")
    actual = "sha256:" + hashlib.sha256(data).hexdigest()
    if actual != object_id:
        raise RuntimeError(f"managed output {name!r} failed digest verification")
    declared_size = row.get("size")
    if declared_size is not None and declared_size != len(data):
        raise RuntimeError(f"managed output {name!r} failed size verification")
    filename = row.get("filename") or row.get("name") or name
    filename = Path(str(filename)).name
    if not filename or filename in {".", ".."}:
        filename = name
    if expected_filename is not None and filename != expected_filename:
        raise RuntimeError(
            f"managed output {name!r} returned filename {filename!r}; expected {expected_filename!r}"
        )
    destination = out_dir / "retrieved" / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    receipt_path = write_retrieval_receipt(
        output_path=destination,
        data=data,
        managed_row={**dict(row), "object_id": object_id},
        task_result=result,
    )
    return destination, {
        **dict(row),
        "object_id": object_id,
        "digest": object_id,
        "path": str(destination),
        "sha256": object_id.removeprefix("sha256:"),
        "receipt_path": str(receipt_path),
    }


def _materialize_final_output(
    client: Any,
    result: Any,
    out_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Read back the one Runtime-selected finalizer association."""

    def raw_identity(value: Any, key: str) -> str | None:
        if isinstance(value, Mapping):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
            for nested in value.values():
                found = raw_identity(nested, key)
                if found:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = raw_identity(nested, key)
                if found:
                    return found
        return None


    path, row = _materialize_output(
        client,
        result,
        "verified_candidate",
        out_dir,
        expected_filename="verified-candidate.mkv",
    )
    if row.get("output_port", row.get("name")) != "verified_candidate":
        raise RuntimeError("final readback selected a non-finalizer output port")
    if row.get("ordinal") != 0 or row.get("group_key") != "main" or row.get("variant_key") != "original":
        raise RuntimeError("final readback did not select (main, original, ordinal 0)")
    selector = row.get("selector")
    if selector != {"group_key": "main", "variant_key": "original"}:
        raise RuntimeError("final readback returned the wrong selector")
    association_id = row.get("association_id") or raw_identity(getattr(result, "raw_result", None), "association_id")
    generation_id = row.get("generation_id") or raw_identity(getattr(result, "raw_result", None), "generation_id")
    if not association_id:
        raise RuntimeError("final readback is missing the managed association identity")
    if not generation_id:
        raise RuntimeError("final readback is missing the generation identity")
    variant_id = row.get("variant_id")
    if not variant_id:
        variant = row.get("variant")
        if isinstance(variant, Mapping):
            variant_id = variant.get("variant_id")
    if not variant_id:
        variant_id = (row.get("provenance") or {}).get("variant_id") if isinstance(row.get("provenance"), Mapping) else None
    if not variant_id:
        variant_id = raw_identity(getattr(result, "raw_result", None), "variant_id")
    if not variant_id:
        raise RuntimeError("final readback is missing the variant identity")
    return path, {
        **row,
        "association_id": association_id,
        "generation_id": generation_id,
        "variant_id": variant_id,
    }


def _retrieve_v2_workflow(
    client: Any,
    compiled: Any,
    compilation: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    """Retrieve and verify the v2 graph/index outputs through managed objects."""

    def declared_ref(name: str) -> Mapping[str, Any]:
        value = compilation.get(name)
        if not isinstance(value, Mapping):
            raise RuntimeError(f"v2 compilation is missing its compact {name} reference")
        digest = value.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise RuntimeError(f"v2 compilation has no valid hash for {name}")
        return value

    def read_declared(name: str, output_port: str, filename: str) -> tuple[Path, Mapping[str, Any], dict[str, Any]]:
        reference = declared_ref(name)
        path, row = _materialize_output(
            client,
            compiled,
            output_port,
            out_dir,
            managed_only=True,
            expected_filename=filename,
        )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != reference["sha256"]:
            raise RuntimeError(f"managed {name} failed compact-index hash verification")
        return path, row, dict(reference)

    binding_path, binding_row, binding_ref = read_declared(
        "graph_binding", "graph_binding", "graph_binding.json"
    )
    graph_path, graph_row, graph_ref = read_declared(
        "graph", "graph", "graph.vibe.json"
    )
    prepared_path, _prepared_row, prepared_ref = read_declared(
        "prepared_artifact", "prepared_artifact", "prepared-av-mask.json"
    )
    binding = _json_mapping(binding_path)
    graph = _json_mapping(graph_path)
    prepared_manifest = _json_mapping(prepared_path)
    try:
        prepared = load_prepared_av_mask(prepared_path)
    except PreparedAVMaskError as exc:
        raise RuntimeError(f"managed prepared artifact failed closed: {exc}") from exc
    try:
        validate_prepared_mask_references(binding, prepared_manifest)
        validate_h3_graph_binding(binding)
    except GraphBindingError as exc:
        raise RuntimeError(f"managed graph binding failed closed: {exc}") from exc
    if binding.get("bundle_identity") != binding_ref.get("bundle_identity"):
        raise RuntimeError("managed graph binding identity disagrees with compact compilation index")
    if binding.get("graph_sha256") != graph_ref["sha256"]:
        raise RuntimeError("managed graph binding points at a different executable graph")
    if prepared_ref.get("artifact_digest") != prepared.artifact_digest:
        raise RuntimeError("managed prepared artifact digest disagrees with compact compilation index")
    if binding.get("prepared_artifact_digest") != prepared.artifact_digest:
        raise RuntimeError("managed graph binding has a different prepared artifact digest")
    if graph.get("nodes") is None or graph.get("edges") is None:
        raise RuntimeError("managed executable graph is incomplete")

    # Keep a local verified copy for downstream provenance/debug inspection,
    # but pass the already-settled managed graph descriptor onward. This
    # avoids re-importing a producer output through a second public mutation.
    path = out_dir / "graph.vibe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(graph_path.read_bytes())
    return _descriptor(graph_row, filename="graph.vibe.json")


def _retrieve_generation_outputs(
    client: Any,
    result: Any,
    out_dir: Path,
) -> dict[str, tuple[Path, dict[str, Any]]]:
    """Retrieve LanPaint's required producer outputs without flattening roles."""

    rows = _managed_rows(result, "vibecomfy_run")
    by_role: dict[str, list[Mapping[str, Any]]] = {"video": [], "audio": []}
    for row in rows:
        role = _output_role(row)
        if role is not None:
            by_role[role].append(row)
    missing = [role for role in ("video", "audio") if not by_role[role]]
    if missing:
        raise RuntimeError(
            "managed LanPaint generation is missing required output role(s): "
            + ", ".join(missing)
        )
    duplicate = [role for role in ("video", "audio") if len(by_role[role]) != 1]
    if duplicate:
        raise RuntimeError(
            "managed LanPaint generation has ambiguous output role(s): "
            + ", ".join(duplicate)
        )
    return {
        role: (
            _materialize_output(
                client,
                SimpleNamespace(  # type: ignore[name-defined]
                    capability_id=getattr(result, "capability_id", "vibecomfy.run"),
                    outputs={"managed_outputs": [row]},
                    raw_result={},
                ),
                "vibecomfy_run",
                out_dir,
                managed_only=True,
            )
        )
        for role, row_list in by_role.items()
        for row in row_list
    }


def _write_generated_bundle(
    outputs: Mapping[str, tuple[Path, Mapping[str, Any]]],
    destination: Path,
) -> Path:
    """Create a deterministic, role-bearing bundle for compose/verify."""

    if set(outputs) != {"video", "audio"}:
        raise RuntimeError("LanPaint generated bundle requires exactly video and audio outputs")
    records: list[dict[str, Any]] = []
    payloads: list[tuple[str, bytes]] = []
    for role in ("video", "audio"):
        path, row = outputs[role]
        if not path.is_file():
            raise RuntimeError(f"retrieved LanPaint {role} output is missing: {path}")
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        declared = row.get("sha256")
        if declared != digest:
            raise RuntimeError(f"retrieved LanPaint {role} output failed digest verification")
        member = f"outputs/{role}-{path.name}"
        records.append(
            {
                "role": role,
                "member": member,
                "filename": path.name,
                "sha256": digest,
                "size": len(data),
                "object_id": row.get("object_id"),
                "producer_output_id": row.get("producer_output_id"),
                "output_port": row.get("producer", {}).get("output_port", role)
                if isinstance(row.get("producer"), Mapping)
                else row.get("output_port", role),
            }
        )
        payloads.append((member, data))
    manifest = {"schema_version": 1, "kind": "h3_av_generated_av", "outputs": records}
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w") as archive:
        for member, data in [("manifest.json", json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")), *payloads]:
            info = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o100600 << 16
            archive.writestr(info, data)
    return destination


def _retrieve_compiled_workflow(
    client: Any,
    compiled: Any,
    compilation: Mapping[str, Any],
    out_dir: Path,
) -> dict[str, Any]:
    """Retrieve and attest the exact canonical bundle selected by compilation."""

    workflow = compilation.get("workflow")
    if not isinstance(workflow, Mapping):
        raise RuntimeError("compilation.json is missing its selected workflow manifest")
    inputs: dict[str, Any] = {}
    for port, filename in (
        ("python", "workflow.py"),
        ("companion", "workflow.vibe.json"),
        ("source", "source.json"),
    ):
        identity = workflow.get(filename)
        expected = identity.get("sha256") if isinstance(identity, Mapping) else None
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise RuntimeError(f"compilation.json has no valid hash for workflow member {filename!r}")
        path, row = _materialize_output(
            client,
            compiled,
            port,
            out_dir,
            managed_only=True,
            expected_filename=filename,
        )
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(
                f"managed workflow member {filename!r} failed compilation hash/provenance verification"
            )
        inputs[port] = _descriptor(row, filename=filename)
    return inputs


def _provenance(preparation: Mapping[str, Any], compilation: Mapping[str, Any]) -> dict[str, Any]:
    request_digest = preparation.get("request_digest")
    if request_digest != compilation.get("request_digest"):
        raise RuntimeError("H3 request provenance does not match the selected compilation")
    assets = preparation.get("assets")
    workflow = compilation.get("workflow")
    graph_binding = compilation.get("graph_binding")
    managed_assets = compilation.get("managed_assets")
    if not isinstance(managed_assets, Mapping) or (not isinstance(workflow, Mapping) and not isinstance(graph_binding, Mapping)):
        raise RuntimeError("H3 compilation is missing managed workflow/graph or asset provenance")
    return {
        "schema_version": 1,
        "request_digest": request_digest,
        "schedule_digest": preparation.get("mask_schedule", {}).get("digest"),
        "assets": [dict(item) for item in assets] if isinstance(assets, list) else [],
        "graph": {
            "profile": compilation.get("profile"),
            "compilation_digest": compilation.get("compilation_digest"),
            "workflow": dict(workflow) if isinstance(workflow, Mapping) else None,
            "graph_binding": dict(graph_binding) if isinstance(graph_binding, Mapping) else None,
            "managed_assets": dict(managed_assets),
        },
    }


def _write_provenance_preparation(root: Path, preparation: Mapping[str, Any], provenance: Mapping[str, Any]) -> Path:
    enriched = dict(preparation)
    enriched["provenance"] = dict(provenance)
    path = root / "provenance-preparation.json"
    path.write_text(json.dumps(enriched, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _invoke(client: Any, capability_id: str, *, inputs: Mapping[str, Any], out: Path, project: str | None, execution_request: Mapping[str, Any] | None = None) -> Any:
    result = client.invoke_result(
        capability_id,
        kind="executor",
        inputs=inputs,
        out=out,
        project=project,
        execution_request=execution_request,
        wait=True,
    )
    if not result.ok:
        raise RuntimeError(f"{capability_id} failed: {result.error}")
    return result


def run_transform(args: argparse.Namespace) -> dict[str, Any]:
    root = args.out.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    input_bundle = getattr(args, "input_bundle", None) or getattr(args, "asset_map", None)
    if not isinstance(input_bundle, Path):
        input_bundle = Path(input_bundle) if input_bundle else None
    if input_bundle is None:
        raise RuntimeError("h3_av.transform requires a managed --input-bundle")
    if args.dry_run:
        return {
            "status": "planned",
            "request": str(args.request.resolve()),
            "input_bundle": str(input_bundle.resolve()),
            "stages": ["h3_av.prepare", "h3_av.compile", "vibecomfy.validate", "vibecomfy.run", "h3_av.compose", "h3_av.verify"],
        }
    execution_request_path = Path(args.execution_request) if args.execution_request else None
    execution_request = _json_mapping(execution_request_path) if execution_request_path else None
    request_value = _json_mapping(args.request)
    request_model = normalize_request(request_value)
    # The public file port retains its historical CLI name, but only a
    # prebuilt managed bundle is admissible here. Local asset-map paths cannot
    # be transported into an already running orchestrator safely.
    if not zipfile.is_zipfile(input_bundle):
        raise RuntimeError("h3_av.transform --input-bundle requires a prebuilt managed input bundle; JSON asset-map paths are unsupported")
    original_digest = bundle_digest(input_bundle)
    input_bundle_path = root / "00-input" / "h3-input-bundle.zip"
    input_bundle_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_bundle, input_bundle_path)
    if bundle_digest(input_bundle_path) != original_digest:
        raise RuntimeError("managed input bundle changed while entering h3_av.transform")
    staged_assets, _ = materialize_input_bundle(
        request_model, input_bundle_path, root / "00-input" / "staged-assets"
    )
    with AstridClient.open_from_launcher() as client:
        request_descriptor = _import_runtime_file(
            client, project=args.project, path=args.request, filename="request.json"
        )
        input_bundle_descriptor = _import_runtime_file(
            client, project=args.project, path=input_bundle_path, filename="h3-input-bundle.zip"
        )
        prepared = _invoke(
            client, "h3_av.prepare",
            inputs={"request": request_descriptor, "input_bundle": input_bundle_descriptor},
            out=root / "01-prepare", project=args.project,
        )
        preparation_path, preparation_row = _materialize_output(client, prepared, "preparation", root / "01-prepare")
        preparation = _json_mapping(preparation_path)
        compiled = _invoke(
            client, "h3_av.compile", inputs={
                "preparation": _descriptor(preparation_row, filename="preparation.json"),
                "input_bundle": input_bundle_descriptor,
            },
            out=root / "02-compile", project=args.project,
        )
        compilation_path, compilation_row = _materialize_output(client, compiled, "compilation", root / "02-compile")
        managed_assets_path, managed_assets_row = _materialize_output(client, compiled, "managed_assets", root / "02-compile")
        compilation = _json_mapping(compilation_path)
        output_contract = validate_output_contract(compilation.get("output_contract"))
        expected_assets_digest = compilation.get("managed_assets", {}).get("sha256")
        actual_assets_digest = hashlib.sha256(managed_assets_path.read_bytes()).hexdigest()
        if expected_assets_digest != actual_assets_digest:
            raise RuntimeError("managed H3 assets failed compilation hash/provenance verification")
        provenance = _provenance(preparation, compilation)
        provenance_path = _write_provenance_preparation(root, preparation, provenance)
        if compilation.get("schema_version") == 2:
            workflow_descriptor = _retrieve_v2_workflow(client, compiled, compilation, root / "02-compile")
            bundle_inputs = {"workflow": workflow_descriptor}
        else:
            bundle_inputs = _retrieve_compiled_workflow(client, compiled, compilation, root / "02-compile")
        _invoke(client, "vibecomfy.validate", inputs=bundle_inputs, out=root / "03-validate", project=args.project)
        run_inputs = {
            **bundle_inputs,
            "managed_assets": _descriptor(managed_assets_row, filename="managed-assets.zip"),
            "workflow_inputs": json.dumps(compilation.get("workflow_inputs", {}), sort_keys=True, separators=(",", ":")),
            "output_contract": json.dumps(output_contract, sort_keys=True, separators=(",", ":")),
        }
        run = _invoke(
            client, "vibecomfy.run",
            inputs=run_inputs,
            out=root / "04-run", project=args.project, execution_request=execution_request,
        )
        if compilation.get("schema_version") == 2:
            generated_path, generated_row = _materialize_output(client, run, "vibecomfy_run", root / "04-run")
            generated_bundle_path = generated_path
            generated_outputs = {"video": (generated_path, generated_row)}
        else:
            generated_outputs = _retrieve_generation_outputs(client, run, root / "04-run")
            generated_bundle_path = _write_generated_bundle(
                generated_outputs,
                root / "04-run" / "retrieved" / "lanpaint-generated-av.zip",
            )
        request = preparation["request"]
        source_path: Path | None = None
        source_descriptor: dict[str, Any] | None = None
        source_spec = request.get("source")
        if isinstance(source_spec, Mapping):
            source_asset = source_spec["asset"]
            source_record = next(item for item in preparation["assets"] if item["asset"] == source_asset)
            source_path = Path(staged_assets[source_asset]).resolve()
            if "sha256" in source_record and hashlib.sha256(source_path.read_bytes()).hexdigest() != source_record["sha256"]:
                raise RuntimeError("authoritative source changed after preparation")
        runtime_provenance = {
            "run_id": getattr(run, "kernel_run_id", None),
            "task_id": getattr(run, "kernel_task_id", None),
            "attempt_id": getattr(run, "kernel_attempt_id", None),
            "generated_outputs": {
                role: row for role, (_path, row) in generated_outputs.items()
            },
            "generated_bundle": {
                "filename": generated_bundle_path.name,
                "sha256": hashlib.sha256(generated_bundle_path.read_bytes()).hexdigest(),
            },
        }
        enriched = dict(preparation)
        enriched["provenance"] = {**provenance, "runtime": runtime_provenance}
        provenance_path.write_text(json.dumps(enriched, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        preparation_descriptor = _import_runtime_file(
            client, project=args.project, path=provenance_path, filename="provenance-preparation.json"
        )
        if source_path is not None:
            source_descriptor = _import_runtime_file(
                client, project=args.project, path=source_path, filename=source_path.name
            )
        generated_descriptor = _import_runtime_file(
            client,
            project=args.project,
            path=generated_bundle_path,
            filename=generated_bundle_path.name,
        )
        composed = _invoke(
            client, "h3_av.compose",
            inputs={
                "preparation": preparation_descriptor,
                "generated": generated_descriptor,
                "input_bundle": input_bundle_descriptor,
                **({"source": source_descriptor} if source_descriptor is not None else {}),
            },
            out=root / "05-compose", project=args.project,
        )
        composition_path, composition_row = _materialize_output(client, composed, "composition", root / "05-compose")
        candidate_path, candidate_row = _materialize_output(
            client, composed, "candidate", root / "05-compose", expected_filename="h3-av-master.mkv"
        )
        generation_intent = generation_intent_from_contract(
            output_contract,
            metadata={
                "source_capability": "h3_av.transform",
                "request_digest": preparation.get("request_digest"),
                "compilation_digest": compilation.get("compilation_digest"),
            },
        )
        verified = _invoke(
            client, "h3_av.verify",
            inputs={
                "preparation": preparation_descriptor,
                "composition": _descriptor(composition_row, filename="composition-manifest.json"),
                "candidate": _descriptor(candidate_row, filename="h3-av-master.mkv"),
                "input_bundle": input_bundle_descriptor,
                **({"source": source_descriptor} if source_descriptor is not None else {}),
                "generation_intent": generation_intent,
            },
            out=root / "06-verify", project=args.project,
        )
        verification_path, _ = _materialize_output(client, verified, "verification", root / "06-verify")
        final_path, final_row = _materialize_final_output(client, verified, root / "06-verify")
        composition_candidate = _digest(candidate_row)
        verification_digest = _digest(final_row)
        if composition_candidate != verification_digest:
            raise RuntimeError("compose candidate and verified final digests differ")
        if candidate_row.get("size") != final_row.get("size"):
            raise RuntimeError("compose candidate and verified final sizes differ")
    return {
        "status": "published",
        "preparation": str(preparation_path),
        "compilation": str(compilation_path),
        "generated": str(generated_outputs["video"][0]),
        **({"generated_audio": str(generated_outputs["audio"][0])} if "audio" in generated_outputs else {}),
        "composition": str(composition_path),
        "verification": str(verification_path),
        "final": str(final_path),
        "task_id": getattr(verified, "kernel_task_id", None),
        "attempt_id": getattr(verified, "kernel_attempt_id", None),
        "association_id": final_row.get("association_id"),
        "generation_id": final_row.get("generation_id"),
        "variant_id": final_row.get("variant_id"),
        "object_id": final_row.get("object_id") or final_row.get("digest"),
        "selector": {"group_key": "main", "variant_key": "original", "ordinal": 0},
        "retrieval_receipt": final_row.get("receipt_path"),
    }


def main(argv: list[str] | None = None) -> int:
    result = run_transform(build_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.transform")
    raise SystemExit(run_pack_main("h3_av.transform", lambda: main()))
