"""SDK-connected H3 audiovisual transform orchestration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main
from astrid.sdk import AstridClient
from astrid.packs.h3_av.src.receipt import build_final_receipt, write_final_receipt
from astrid.packs.h3_av.src.input_bundle import build_input_bundle, materialize_input_bundle
from astrid.packs.h3_av.src.request import load_request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded H3 audiovisual transform.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--asset-map", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--project")
    parser.add_argument("--execution-request", type=Path)
    parser.add_argument(
        "--editorial-approved",
        action="store_true",
        help="record explicit editorial approval in the final receipt",
    )
    parser.add_argument(
        "--cleanup-receipt",
        type=Path,
        help="JSON receipt listing exact owned-resource cleanup postconditions",
    )
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
    descriptor = _descriptor(data, filename=filename)
    if descriptor["digest"] != "sha256:" + digest:
        raise RuntimeError(f"managed H3 input {filename!r} import returned a different digest")
    return descriptor


def _materialize_output(
    client: Any,
    result: Any,
    name: str,
    out_dir: Path,
    *,
    managed_only: bool = False,
    expected_filename: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    if not managed_only:
        local = _direct_output(result, name)
        if local is not None:
            return local, {"path": str(local), "sha256": hashlib.sha256(local.read_bytes()).hexdigest()}
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
    return destination, {**dict(row), "object_id": object_id, "digest": object_id, "path": str(destination), "sha256": object_id.removeprefix("sha256:")}


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


def _retrieve_muxed_generation(
    client: Any,
    result: Any,
    out_dir: Path,
) -> tuple[Path, dict[str, Any]]:
    """Retrieve the native graph's one full-timeline muxed AV result."""

    rows = _managed_rows(result, "vibecomfy_run")
    if len(rows) != 1:
        raise RuntimeError(
            "managed native H3 generation must return exactly one muxed AV output; "
            f"observed {len(rows)}"
        )
    row = rows[0]
    return _materialize_output(
        client,
        SimpleNamespace(
            capability_id=getattr(result, "capability_id", "vibecomfy.run"),
            outputs={"managed_outputs": [row]},
            raw_result={},
        ),
        "vibecomfy_run",
        out_dir,
        managed_only=True,
    )


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
    managed_assets = compilation.get("managed_assets")
    if not isinstance(workflow, Mapping) or not isinstance(managed_assets, Mapping):
        raise RuntimeError("H3 compilation is missing managed workflow or asset provenance")
    return {
        "schema_version": 1,
        "request_digest": request_digest,
        "schedule_digest": preparation.get("mask_schedule", {}).get("digest"),
        "assets": [dict(item) for item in assets] if isinstance(assets, list) else [],
        "graph": {
            "profile": compilation.get("profile"),
            "compilation_digest": compilation.get("compilation_digest"),
            "workflow": dict(workflow),
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


def _generation_intent(compilation: Mapping[str, Any]) -> dict[str, Any]:
    """Derive the child publication declaration from the sealed compilation."""

    capabilities = compilation.get("capabilities")
    public = capabilities.get("public_generation") if isinstance(capabilities, Mapping) else None
    if not isinstance(public, Mapping):
        raise RuntimeError("sealed H3 compilation is missing public_generation")
    selectors = public.get("selectors")
    modality = public.get("modality", "video")
    if not isinstance(selectors, list) or not selectors:
        raise RuntimeError("sealed H3 compilation declares no public generation selectors")
    if not all(isinstance(selector, Mapping) for selector in selectors):
        raise RuntimeError("sealed H3 generation selectors must be objects")
    return {
        "version": 1,
        "modality": modality,
        "partial_success_policy": "reject",
        "groups": [{"group_key": "main", "selectors": [dict(selector) for selector in selectors]}],
        "metadata": {"compiled_generation_contract": True},
    }


def run_transform(args: argparse.Namespace) -> dict[str, Any]:
    root = args.out.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    if args.dry_run:
        return {
            "status": "planned",
            "request": str(args.request.resolve()),
            "asset_map": str(args.asset_map.resolve()),
            "stages": ["h3_av.prepare", "h3_av.compile", "vibecomfy.validate", "vibecomfy.run", "h3_av.compose", "h3_av.verify"],
        }
    execution_request = _json_mapping(args.execution_request) if args.execution_request else None
    cleanup_receipt = _json_mapping(args.cleanup_receipt) if args.cleanup_receipt else None
    # The parent orchestrator is launched locally, while its child executor
    # tasks target the already-supervised Runtime/GenericPackHost. Starting a
    # second local pack host here would compete with that existing authority.
    with AstridClient.open_from_launcher(start_pack_host=False) as client:
        request = load_request(args.request)
        staging = root / "staged-inputs"
        staging.mkdir(parents=True, exist_ok=True)
        bundle_path = build_input_bundle(
            request, _json_mapping(args.asset_map), staging / "h3-inputs.zip"
        )
        request_path = staging / "request.json"
        request_path.write_text(json.dumps(request.value, sort_keys=True), encoding="utf-8")
        request_descriptor = _import_runtime_file(
            client, project=args.project, path=request_path, filename=request_path.name
        )
        bundle_descriptor = _import_runtime_file(
            client, project=args.project, path=bundle_path, filename=bundle_path.name
        )
        # Freeze the authoritative source from the same verified bytes as the
        # child inputs. Never open a prepare worker's absolute source path.
        frozen_assets, _ = materialize_input_bundle(request, bundle_path, staging / "assets")
        source_inputs = {}
        if request.value["source"] is not None:
            source_path = Path(frozen_assets[request.value["source"]["asset"]])
            source_inputs["source"] = _import_runtime_file(
                client, project=args.project, path=source_path, filename=source_path.name
            )
        prepared = _invoke(
            client, "h3_av.prepare",
            inputs={"request": request_descriptor, "input_bundle": bundle_descriptor},
            out=root / "01-prepare", project=args.project,
        )
        preparation_path, preparation_row = _materialize_output(client, prepared, "preparation", root / "01-prepare", managed_only=True)
        preparation = _json_mapping(preparation_path)
        compiled = _invoke(
            client, "h3_av.compile", inputs={
                "preparation": _descriptor(preparation_row, filename="preparation.json"),
                "input_bundle": bundle_descriptor,
            },
            out=root / "02-compile", project=args.project,
        )
        compilation_path, compilation_row = _materialize_output(client, compiled, "compilation", root / "02-compile", managed_only=True)
        managed_assets_path, managed_assets_row = _materialize_output(client, compiled, "managed_assets", root / "02-compile", managed_only=True)
        compilation = _json_mapping(compilation_path)
        expected_assets_digest = compilation.get("managed_assets", {}).get("sha256")
        actual_assets_digest = hashlib.sha256(managed_assets_path.read_bytes()).hexdigest()
        if expected_assets_digest != actual_assets_digest:
            raise RuntimeError("managed H3 assets failed compilation hash/provenance verification")
        provenance = _provenance(preparation, compilation)
        provenance_path = _write_provenance_preparation(root, preparation, provenance)
        bundle_inputs = _retrieve_compiled_workflow(client, compiled, compilation, root / "02-compile")
        # Canonical workflow Python is executable input.  Carry the explicit
        # consent scalar required by VibeComfy's audited validation gate;
        # execution-request targeting is not itself Python consent.
        _invoke(
            client,
            "vibecomfy.validate",
            inputs={**bundle_inputs, "python_execution_consent": "confirmed"},
            out=root / "03-validate",
            project=args.project,
        )
        generation_metadata = {"h3_av": provenance}
        generation_intent = _generation_intent(compilation)
        generation_intent["metadata"].update(generation_metadata)
        run = _invoke(
            client, "vibecomfy.run",
            inputs={
                **bundle_inputs,
                "managed_assets": _descriptor(managed_assets_row, filename="managed-assets.zip"),
                "workflow_inputs": json.dumps(compilation["workflow_inputs"], sort_keys=True, separators=(",", ":")),
                "generation_intent": generation_intent,
            },
            out=root / "04-run", project=args.project, execution_request=execution_request,
        )
        output_contract = compilation.get("capabilities", {}).get("output_contract")
        generated_audio_path: Path | None = None
        generated_bundle_path: Path | None = None
        if output_contract == "muxed_av_full_timeline":
            generated_path, muxed_row = _retrieve_muxed_generation(
                client, run, root / "04-run"
            )
            generated_outputs: dict[str, tuple[Path, Mapping[str, Any]]] = {
                "muxed_av": (generated_path, muxed_row)
            }
        elif output_contract == "separate_av_full_timeline":
            generated_outputs = _retrieve_generation_outputs(client, run, root / "04-run")
            generated_path = generated_outputs["video"][0]
            generated_audio_path = generated_outputs["audio"][0]
            generated_bundle_path = _write_generated_bundle(
                generated_outputs,
                root / "04-run" / "retrieved" / "lanpaint-generated-av.zip",
            )
        else:
            raise RuntimeError(f"unsupported H3 output contract: {output_contract!r}")
        runtime_provenance = {
            "run_id": getattr(run, "kernel_run_id", None),
            "task_id": getattr(run, "kernel_task_id", None),
            "attempt_id": getattr(run, "kernel_attempt_id", None),
            "generated_outputs": {
                role: row for role, (_path, row) in generated_outputs.items()
            },
            "output_contract": output_contract,
        }
        if generated_bundle_path is not None:
            runtime_provenance["generated_bundle"] = {
                "filename": generated_bundle_path.name,
                "sha256": hashlib.sha256(generated_bundle_path.read_bytes()).hexdigest(),
            }
        enriched = dict(preparation)
        enriched["provenance"] = {**provenance, "runtime": runtime_provenance}
        provenance_path.write_text(json.dumps(enriched, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        preparation_descriptor = _import_runtime_file(
            client, project=args.project, path=provenance_path, filename="provenance-preparation.json"
        )
        generated_input_path = generated_bundle_path or generated_path
        generated_descriptor = _import_runtime_file(
            client,
            project=args.project,
            path=generated_input_path,
            filename=generated_input_path.name,
        )
        composed = _invoke(
            client, "h3_av.compose",
            inputs={
                "preparation": preparation_descriptor,
                "generated": generated_descriptor,
                **source_inputs,
            },
            out=root / "05-compose", project=args.project,
        )
        composition_path, composition_row = _materialize_output(client, composed, "composition", root / "05-compose", managed_only=True)
        candidate_path, candidate_row = _materialize_output(client, composed, "candidate", root / "05-compose", managed_only=True)
        verified = _invoke(
            client, "h3_av.verify",
            inputs={
                "preparation": preparation_descriptor,
                "composition": _descriptor(composition_row, filename="composition-manifest.json"),
                "candidate": _descriptor(candidate_row, filename="candidate.media"),
                **source_inputs,
            },
            out=root / "06-verify", project=args.project,
        )
        verification_path, _ = _materialize_output(client, verified, "verification", root / "06-verify", managed_only=True)
        verification = _json_mapping(verification_path)
        task_evidence = {
            key: value
            for key, value in {
                "run_id": getattr(run, "kernel_run_id", None),
                "task_id": getattr(run, "kernel_task_id", None),
                "attempt_id": getattr(run, "kernel_attempt_id", None),
                "capability_id": getattr(run, "capability_id", None),
            }.items()
            if value is not None
        }
        receipt = build_final_receipt(
            request_digest=str(preparation["request_digest"]),
            task_succeeded=task_evidence,
            candidate_verified={
                "verification_path": str(verification_path),
                "verification": verification,
            },
            editorially_approved=(
                {"source": "--editorial-approved"}
                if args.editorial_approved
                else None
            ),
            cleanup=cleanup_receipt,
        )
        final_receipt_path = write_final_receipt(root / "07-final-receipt.json", receipt)
    return {
        "status": "verified",
        "preparation": str(preparation_path),
        "compilation": str(compilation_path),
        "generated": str(generated_path),
        "generated_audio": None if generated_audio_path is None else str(generated_audio_path),
        "composition": str(composition_path),
        "candidate": str(candidate_path),
        "verification": str(verification_path),
        "final_receipt": str(final_receipt_path),
        "final_receipt_status": receipt["overall_status"],
    }


def main(argv: list[str] | None = None) -> int:
    result = run_transform(build_parser().parse_args(argv))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.transform")
    raise SystemExit(run_pack_main("h3_av.transform", lambda: main()))
