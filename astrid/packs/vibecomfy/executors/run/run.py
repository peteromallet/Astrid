"""Run an authored VibeComfy workflow and settle its artifact inventory."""


from __future__ import annotations

from astrid.core.pack.entrypoint import guard_canonical_entrypoint

guard_canonical_entrypoint('vibecomfy.run')
import argparse
import hashlib
import json
import mimetypes
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from astrid.core._shared.result_manifest import (  # noqa: E402
    build_manifest,
    write_manifest,
)
from astrid.core.cli_choices import add_choice_arg  # noqa: E402
from astrid.core.contracts.managed_generation_result import (  # noqa: E402
    ManagedGenerationResultError,
    read_managed_generation_result,
)
from astrid.packs.vibecomfy.executors._bundle_inputs import (  # noqa: E402
    staged_workflow_path,
)
from astrid.packs.vibecomfy.asset_manifest import (  # noqa: E402
    AssetManifestError,
    ResolvedAssetManifest,
    read_archive,
)
from astrid.packs.h3_av.src.output_contract import (  # noqa: E402
    OutputContractError,
    validate_output_contract,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VibeComfy workflow commands.")
    add_choice_arg(parser, "command", values=("run", "validate"))
    parser.add_argument("workflow", nargs="?", default="")
    parser.add_argument("--python", default="")
    parser.add_argument("--companion", default="")
    parser.add_argument("--source", default="")
    parser.add_argument(
        "--source-video",
        default="",
        help="Optional managed source video to copy into the Comfy input directory.",
    )
    parser.add_argument("--source-video-node", default="99")
    parser.add_argument("--source-video-widget", default="video")
    parser.add_argument(
        "--managed-assets",
        default="",
        help="Optional deterministic managed-assets ZIP containing manifest.json.",
    )
    parser.add_argument(
        "--workflow-inputs",
        default="{}",
        help="JSON object of scalar public workflow inputs; managed assets supply media basenames.",
    )
    parser.add_argument("--output-contract", default="{}")
    parser.add_argument(
        "--out",
        type=Path,
        help="Host-assigned output spool (required for run; optional for validate).",
    )
    parser.add_argument(
        "--task-identity",
        required=False,
        help="Host-issued task identity used by the production engine adapter.",
    )
    parser.add_argument(
        "--attempt-identity",
        default="-",
        help="Host-issued attempt identity used for stale-result fencing.",
    )
    parser.add_argument(
        "--execution-identity",
        default="-",
        help="Host-issued canonical workflow execution identity.",
    )
    parser.add_argument(
        "--readiness-profile-path",
        default="-",
        help="Worker-issued readiness profile path; '-' selects embedded execution.",
    )
    parser.add_argument(
        "--readiness-profile-hash",
        default="-",
        help="SHA-256 hash paired with the Worker readiness profile.",
    )
    return parser


def _source_video_input_directory(
    readiness_profile: dict[str, Any] | None,
    output_root: Path,
) -> Path:
    """Resolve the worker-owned Comfy input directory for source media."""
    if isinstance(readiness_profile, dict) and isinstance(
        readiness_profile.get("vibecomfy_session"), dict
    ):
        session = readiness_profile["vibecomfy_session"]
        raw_session_dir = session.get("session_dir")
        if not isinstance(raw_session_dir, str) or not raw_session_dir.strip():
            raise ValueError("checkout_server readiness profile lacks session_dir")
        session_dir = Path(raw_session_dir).expanduser()
        config_path = session_dir / "config.json"
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("checkout_server session config is unreadable") from exc
        raw_input_directory = config.get("input_directory") if isinstance(config, dict) else None
        if not isinstance(raw_input_directory, str) or not raw_input_directory.strip():
            raise ValueError("checkout_server session config lacks input_directory")
        input_directory = Path(raw_input_directory).expanduser()
    else:
        input_directory = output_root.expanduser().resolve() / "engine-input"
    if not input_directory.is_absolute():
        raise ValueError("Comfy input_directory must be absolute")
    if input_directory.is_symlink():
        raise ValueError("Comfy input_directory must not be a symlink")
    input_directory.mkdir(parents=True, exist_ok=True)
    if not input_directory.is_dir():
        raise ValueError("Comfy input_directory is not a directory")
    return input_directory


def _stage_source_video(
    source_video: str,
    *,
    readiness_profile: dict[str, Any] | None,
    output_root: Path,
) -> str:
    """Copy one managed source video into Comfy input custody."""
    source = Path(source_video).expanduser()
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"source video is not a regular file: {source}")
    source = source.resolve(strict=True)
    input_directory = _source_video_input_directory(readiness_profile, output_root)
    destination = input_directory / source.name
    if destination.exists() and destination.is_symlink():
        raise ValueError(f"source video destination is a symlink: {destination}")
    if destination.exists() and destination.read_bytes() != source.read_bytes():
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
        destination = input_directory / f"{source.stem}-{digest}{source.suffix}"
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination.name


def _workflow_inputs(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("workflow inputs must be valid JSON") from exc
    if not isinstance(decoded, dict) or any(not isinstance(name, str) or not name for name in decoded):
        raise ValueError("workflow inputs must be a JSON object with non-empty string keys")
    return decoded


def _parse_output_contract(value: str) -> dict[str, Any] | None:
    if not value or value == "{}":
        return None
    try:
        decoded = json.loads(value)
        return validate_output_contract(decoded)
    except (json.JSONDecodeError, OutputContractError) as exc:
        raise ValueError(f"compiled output contract is invalid: {exc}") from exc


def _stage_managed_asset_manifest(
    archive_path: str,
    *,
    readiness_profile: dict[str, Any] | None,
    output_root: Path,
) -> ResolvedAssetManifest:
    """Verify and stage one canonical managed-asset/input manifest."""

    input_directory = _source_video_input_directory(readiness_profile, output_root)
    try:
        resolved = read_archive(archive_path)
    except AssetManifestError as exc:
        raise ValueError(str(exc)) from exc
    for record in resolved.manifest["assets"]:
        member = str(record["member"])
        data = resolved.members[member]
        destination = input_directory / Path(member).name
        if destination.exists() and (
            destination.is_symlink() or destination.read_bytes() != data
        ):
            raise ValueError(f"managed asset destination collision: {destination.name}")
        if not destination.exists():
            destination.write_bytes(data)
    return resolved


def _stage_managed_assets(
    archive_path: str,
    *,
    readiness_profile: dict[str, Any] | None,
    output_root: Path,
) -> dict[str, str]:
    """Compatibility wrapper returning only resolved workflow bindings."""

    resolved = _stage_managed_asset_manifest(
        archive_path,
        readiness_profile=readiness_profile,
        output_root=output_root,
    )
    staged = {
        str(record["binding"]): Path(str(record["member"])).name
        for record in resolved.manifest["assets"]
    }
    lineage = resolved.manifest.get("lineage", {})
    if "h3_av_executable_bindings" not in lineage:
        if {"prepared_video_mask", "prepared_audio_mask"} <= set(staged):
            raise ValueError("managed H3 archive is missing executable workflow bindings")
        # Older and non-H3 archives retain their original binding contract.
        return staged
    executable = lineage["h3_av_executable_bindings"]
    if not isinstance(executable, dict) or not executable or any(
        not isinstance(socket, str) or not socket or not isinstance(binding, str)
        or binding not in staged for socket, binding in executable.items()
    ):
        raise ValueError("managed H3 executable bindings are malformed")
    selected = {socket: staged[binding] for socket, binding in executable.items()}
    if resolved.manifest.get("workflow_inputs") != selected:
        raise ValueError("managed H3 executable bindings disagree with workflow inputs")
    return selected


def _materialize_managed_generation_result(
    output_root: Path,
    production_result: Any,
    *,
    task_identity: str,
    attempt_identity: str | None = None,
    workflow_path: Path,
) -> dict[str, Any]:
    """Rebase one producer envelope into the host-owned output spool."""
    output_root = output_root.expanduser().resolve()
    envelope_path = Path(production_result.managed_generation_result_path).expanduser()
    if not envelope_path.is_file():
        raise ValueError(f"managed-generation result is missing: {envelope_path}")
    producer_root = envelope_path.resolve().parent
    try:
        result = read_managed_generation_result(
            envelope_path,
            staging_root=producer_root,
            expected_task_id=task_identity,
            expected_attempt_id=attempt_identity,
        )
    except ManagedGenerationResultError as exc:
        raise ValueError(f"managed-generation result failed validation: {exc}") from exc
    if any(
        result.outcomes[phase].status != expected
        for phase, expected in (
            ("execution", "succeeded"),
            ("retrieval", "succeeded"),
            ("verification", "succeeded"),
            ("publication", "not_started"),
        )
    ):
        raise ValueError("managed-generation result is not publishable")

    # Keep the neutral envelope in its own namespace, while placing the
    # host-owned output files under the existing one-level ``outputs``
    # namespace accepted by Runtime's upload contract.
    managed_root = output_root
    managed_storage_root = output_root / "managed-generation"
    outputs_root = output_root / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    rebased_payload = result.to_dict()
    rebased_outputs: list[dict[str, Any]] = []
    for output in result.outputs:
        source = (producer_root / output.path).resolve(strict=True)
        try:
            source.relative_to(producer_root)
        except ValueError as exc:
            raise ValueError(f"managed output escapes producer custody: {output.path}") from exc
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"managed output is not a regular file: {output.path}")
        destination = outputs_root / f"{output.ordinal:04d}-{output.output_port}{source.suffix}"
        if destination.exists():
            raise ValueError(f"managed output destination collides: {destination.name}")
        shutil.copy2(source, destination)
        rebased = output.to_dict()
        rebased["path"] = destination.relative_to(managed_root).as_posix()
        rebased_outputs.append(rebased)
    rebased_payload["outputs"] = rebased_outputs
    staged_envelope = managed_storage_root / "managed-generation-result.json"
    staged_envelope.parent.mkdir(parents=True, exist_ok=True)
    staged_envelope.write_text(
        json.dumps(rebased_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    try:
        staged = read_managed_generation_result(
            staged_envelope,
            staging_root=managed_root,
            expected_task_id=task_identity,
            expected_attempt_id=(attempt_identity or result.attempt_id),
        )
    except ManagedGenerationResultError as exc:
        raise ValueError(f"rebased managed-generation result failed validation: {exc}") from exc

    envelope_ref = staged_envelope.relative_to(output_root).as_posix()
    durable_envelope = outputs_root / "managed-generation-result.json"
    shutil.copy2(staged_envelope, durable_envelope)
    outputs = []
    for output in staged.outputs:
        outputs.append(
            {
                # The host capability has one declared result port. The
                # producer port remains authoritative in the preserved neutral
                # envelope and the per-output producer metadata.
                "path": (managed_root / output.path).relative_to(output_root).as_posix(),
                "name": "vibecomfy_run",
                "output_port": "vibecomfy_run",
                "ordinal": output.ordinal,
                "role": "result",
                "is_primary": output.ordinal == 0,
                "content_hash": f"sha256:{output.sha256}",
                "bytes": output.bytes,
                "media_type": output.media_type,
                "producer": {
                    "output_port": output.output_port,
                    "producer_output_id": output.producer_output_id,
                    "media_type": output.media_type,
                    "producer_run_id": staged.producer_run_id,
                },
                "provenance": {
                    "managed_generation_result": envelope_ref,
                    "evidence_namespaces": ["producer", "transport"],
                },
            }
        )
    envelope_digest = hashlib.sha256(durable_envelope.read_bytes()).hexdigest()
    envelope_ordinal = max((output.ordinal for output in staged.outputs), default=-1) + 1
    outputs.append(
        {
            "path": durable_envelope.relative_to(output_root).as_posix(),
            "name": "result_manifest",
            "output_port": "result_manifest",
            "ordinal": envelope_ordinal,
            "role": "auxiliary",
            "is_primary": False,
            "media_type": "application/json",
            "content_hash": f"sha256:{envelope_digest}",
            "bytes": durable_envelope.stat().st_size,
            "provenance": {
                "managed_generation_result": envelope_ref,
                "evidence_namespaces": ["producer", "transport"],
            },
        }
    )
    return write_manifest(
        output_root / "manifest.json",
        build_manifest(
            kind="vibecomfy.run.managed",
            inputs={"workflow": str(workflow_path), **dict(staged.inputs)},
            outputs=outputs,
            created=staged.created,
            schema_version=2,
            warnings=list(staged.warnings),
            managed_generation_result=rebased_payload,
            managed_generation_result_path=envelope_ref,
        ),
    )


def _run_and_settle(
    workflow_path: Path,
    output_root: Path,
    *,
    task_identity: str | None,
    execution_identity: str = "-",
    attempt_identity: str = "-",
    readiness_profile_path: str = "-",
    readiness_profile_hash: str = "-",
    source_video: str = "",
    source_video_node: str = "99",
    source_video_widget: str = "video",
    managed_assets: str = "",
    workflow_inputs: str = "{}",
    output_contract: str = "{}",
) -> dict[str, Any]:
    """Run *workflow_path*, copy every engine result, and write its receipt."""
    if not isinstance(task_identity, str) or not task_identity.strip():
        raise ValueError("host-issued task identity is required")
    compiled_output_contract = _parse_output_contract(output_contract)
    from astrid.packs.vibecomfy import production_engine

    readiness_profile = None
    if (readiness_profile_path == "-") != (readiness_profile_hash == "-"):
        raise ValueError("readiness profile path and hash must be supplied together")
    if readiness_profile_path != "-":
        try:
            profile_bytes = Path(readiness_profile_path).read_bytes()
            actual_hash = "sha256:" + hashlib.sha256(profile_bytes).hexdigest()
            if readiness_profile_hash != actual_hash:
                raise ValueError("Worker readiness profile hash does not match")
            readiness_profile = json.loads(profile_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Worker readiness profile could not be read") from exc
        if not isinstance(readiness_profile, dict):
            raise ValueError("Worker readiness profile must be an object")
    if readiness_profile is None:
        raise ValueError("VibeComfy execution requires a verified readiness profile")
    from astrid.core.execution.t9_model_substitute import (
        T9SubstituteError,
        approved_source as _approved_t9_substitute_source,
    )
    substitute = _approved_t9_substitute_source(readiness_profile)
    if substitute is not None:
        profile_id = "t9_cpu_stub"
    elif isinstance(readiness_profile.get("vibecomfy_session"), dict):
        profile_id = "checkout_server"
    else:
        comfy = readiness_profile.get("comfyui_candidate")
        launch = readiness_profile.get("launch")
        root = comfy.get("root") if isinstance(comfy, dict) else None
        configured = launch.get("comfyui_path") if isinstance(launch, dict) else None
        if not isinstance(root, str) or not isinstance(configured, str) or Path(root).expanduser().resolve() != Path(configured).expanduser().resolve():
            raise ValueError("pip_embedded requires an attested pinned ComfyUI tree and explicit COMFYUI_PATH")
        profile_id = "pip_embedded"
    workflow_input_bindings: dict[str, Any] = _workflow_inputs(workflow_inputs)
    if managed_assets:
        staged_bindings = _stage_managed_assets(
            managed_assets,
            readiness_profile=readiness_profile,
            output_root=output_root,
        )
        conflicts = sorted(
            name
            for name, staged_value in staged_bindings.items()
            if name in workflow_input_bindings
            and workflow_input_bindings[name] != staged_value
        )
        if conflicts:
            raise ValueError("managed assets conflict with workflow inputs: " + ", ".join(conflicts))
        workflow_input_bindings.update(staged_bindings)
    if source_video:
        source_video_name = _stage_source_video(
            source_video,
            readiness_profile=readiness_profile,
            output_root=output_root,
        )
        # Bind through the workflow's declared public input contract.  The
        # node/field is owned by the workflow; repeating it in the executor
        # arguments caused the old path to mutate a sealed bundle after its
        # revision had been established.
        if "source_video" in workflow_input_bindings:
            raise ValueError("source_video was supplied by more than one input path")
        workflow_input_bindings["source_video"] = source_video_name
    if "source_video" in workflow_input_bindings:
        from astrid.packs.vibecomfy.invocation_preflight import preflight_invocation

        staged_input = _source_video_input_directory(
            readiness_profile,
            output_root,
        ) / str(workflow_input_bindings["source_video"])
        # This is intentionally before model/session setup.  The SDK performs
        # the same CPU-only check before admission; repeating it against the
        # actual staged basename catches collisions, renames, and target-side
        # byte changes before H3 warms the GPU or Comfy receives a prompt.
        preflight_invocation(
            workflow_path,
            run_inputs=workflow_input_bindings,
            source_video_path=staged_input,
            expected_source_node=source_video_node,
            expected_source_field=source_video_widget,
            phase="worker-staged",
        )
    production_kwargs: dict[str, Any] = {
        "task_identity": task_identity,
        "expected_execution_identity": (
            None if execution_identity == "-" else execution_identity
        ),
        "profile_id": profile_id,
        "hc03_profile": readiness_profile,
    }
    if workflow_input_bindings:
        production_kwargs["workflow_input_bindings"] = workflow_input_bindings
    if attempt_identity != "-":
        production_kwargs["attempt_identity"] = attempt_identity
    if profile_id == "t9_cpu_stub":
        try:
            from astrid.core.execution.t9_model_substitute import require_active_marker

            require_active_marker()
        except T9SubstituteError as exc:
            raise ValueError(f"T9 CPU substitute activation failed closed: {exc}") from exc
    production_result = production_engine.run_workflow_result_path(
        workflow_path,
        output_root,
        **production_kwargs,
    )

    if production_result.managed_generation_result_path is not None:
        if compiled_output_contract is not None:
            declared_count = len(compiled_output_contract["graph_outputs"])
            actual_count = len(production_result.outputs)
            if actual_count != declared_count:
                raise ValueError(
                    "managed generation output cardinality differs from compiled contract: "
                    f"expected {declared_count}, found {actual_count}"
                )
        return _materialize_managed_generation_result(
            output_root,
            production_result,
            task_identity=task_identity,
            attempt_identity=(None if attempt_identity == "-" else attempt_identity),
            workflow_path=workflow_path,
        )

    inventory = production_result.outputs

    sources: list[Path] = []
    output_root = output_root.expanduser().resolve()
    for ordinal, raw_path in enumerate(inventory):
        if not isinstance(raw_path, (str, Path)) or not str(raw_path):
            raise ValueError(
                f"VibeComfy artifact inventory entry {ordinal} is not a path"
            )
        raw_source = Path(raw_path).expanduser()
        if raw_source.is_symlink():
            raise ValueError(
                f"VibeComfy artifact inventory entry {ordinal} is a symlink"
            )
        source = raw_source.resolve()
        if not source.is_file() or not source.is_relative_to(output_root):
            raise FileNotFoundError(
                f"VibeComfy artifact inventory entry {ordinal} escaped output custody: {source}"
            )
        if source.stat().st_nlink != 1:
            raise ValueError(
                f"VibeComfy artifact inventory entry {ordinal} is not privately owned"
            )
        sources.append(source)

    if not sources:
        raise ValueError("VibeComfy workflow completed with an empty artifact inventory")

    classified: list[tuple[Path, Mapping[str, Any]]] = []
    if compiled_output_contract is not None:
        expected = {str(row["modality"]): row for row in compiled_output_contract["graph_outputs"]}
        by_modality: dict[str, list[Path]] = {name: [] for name in expected}
        for source in sources:
            media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            modality = "video" if media_type.startswith("video/") else "audio" if media_type.startswith("audio/") else None
            if modality not in by_modality:
                raise ValueError(f"artifact {source.name!r} is outside the compiled output contract")
            by_modality[modality].append(source)
        for declaration in compiled_output_contract["graph_outputs"]:
            modality = str(declaration["modality"])
            matched = by_modality[modality]
            if len(matched) != 1:
                raise ValueError(
                    f"compiled output {modality!r} expected exactly one artifact; found {len(matched)}"
                )
            classified.append((matched.pop(), declaration))
        if any(by_modality.values()):
            raise ValueError("artifact inventory contains outputs not accounted for by compiled contract")
    else:
        classified = [
            (source, {"ordinal": ordinal, "role": "primary" if ordinal == 0 else "internal", "modality": "video"})
            for ordinal, source in enumerate(sources)
        ]

    artifacts_root = output_root / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    for source, declaration in classified:
        ordinal = int(declaration["ordinal"])
        destination = artifacts_root / f"{ordinal:04d}-{source.name}"
        if source != destination.resolve():
            shutil.copy2(source, destination)
        outputs.append(
            {
                "path": destination.relative_to(output_root).as_posix(),
                "name": "vibecomfy_run",
                "ordinal": ordinal,
                "role": "result" if declaration.get("role") == "primary" else "auxiliary",
                "is_primary": declaration.get("role") == "primary",
                "media_type": mimetypes.guess_type(source.name)[0]
                or "application/octet-stream",
            }
        )

    manifest = build_manifest(
        kind="vibecomfy.run",
        inputs={
            "workflow": str(workflow_path),
            **({"source_video": str(Path(source_video).expanduser().resolve())} if source_video else {}),
            **({"managed_assets": str(Path(managed_assets).expanduser().resolve())} if managed_assets else {}),
            **({"workflow_input_bindings": workflow_input_bindings} if workflow_input_bindings else {}),
        },
        outputs=outputs,
        created=datetime.now(timezone.utc).isoformat(),
        schema_version=2,
        warnings=[],
        engine_run_id=None,
        engine_prompt_id=None,
    )
    return write_manifest(output_root / "manifest.json", manifest)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scratch = (
            args.out.expanduser().resolve().parent
            if args.out is not None
            else Path.cwd()
        )
        with staged_workflow_path(
            workflow=args.workflow,
            python=args.python,
            companion=args.companion,
            source=args.source,
            scratch=scratch,
        ) as (workflow_path, _authority):
            if args.command == "validate":
                return subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "vibecomfy.cli",
                        "validate",
                        str(workflow_path),
                    ]
                ).returncode
            if args.out is None:
                print("vibecomfy.run: --out is required for run", file=sys.stderr)
                return 2
            _run_and_settle(
                workflow_path,
                args.out,
                task_identity=args.task_identity,
                execution_identity=args.execution_identity,
                readiness_profile_path=args.readiness_profile_path,
                readiness_profile_hash=args.readiness_profile_hash,
                attempt_identity=args.attempt_identity,
                source_video=args.source_video,
                source_video_node=args.source_video_node,
                source_video_widget=args.source_video_widget,
                managed_assets=args.managed_assets,
                workflow_inputs=args.workflow_inputs,
                output_contract=args.output_contract,
            )
    except Exception as exc:
        print(f"vibecomfy.run: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
