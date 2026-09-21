"""Run an authored VibeComfy workflow and settle its artifact inventory."""


from __future__ import annotations

from astrid.core.pack.entrypoint import guard_canonical_entrypoint

guard_canonical_entrypoint('vibecomfy.run')
import argparse
import hashlib
import json
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VibeComfy workflow commands.")
    add_choice_arg(parser, "command", values=("run", "validate"))
    parser.add_argument("workflow", nargs="?", default="")
    parser.add_argument("--python", default="")
    parser.add_argument("--companion", default="")
    parser.add_argument("--source", default="")
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
) -> dict[str, Any]:
    """Run *workflow_path*, copy every engine result, and write its receipt."""
    if not isinstance(task_identity, str) or not task_identity.strip():
        raise ValueError("host-issued task identity is required")
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
    profile_id = (
        "checkout_server"
        if isinstance(readiness_profile, dict)
        and isinstance(readiness_profile.get("vibecomfy_session"), dict)
        else "pip_embedded"
    )
    production_kwargs: dict[str, Any] = {
        "task_identity": task_identity,
        "expected_execution_identity": (
            None if execution_identity == "-" else execution_identity
        ),
        "profile_id": profile_id,
        "hc03_profile": readiness_profile,
    }
    if attempt_identity != "-":
        production_kwargs["attempt_identity"] = attempt_identity
    production_result = production_engine.run_workflow_result_path(
        workflow_path,
        output_root,
        **production_kwargs,
    )

    if production_result.managed_generation_result_path is not None:
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

    artifacts_root = output_root / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, Any]] = []
    for ordinal, source in enumerate(sources):
        destination = artifacts_root / f"{ordinal:04d}-{source.name}"
        if source != destination.resolve():
            shutil.copy2(source, destination)
        outputs.append(
            {
                "path": destination.relative_to(output_root).as_posix(),
                "name": "vibecomfy_run",
                "ordinal": ordinal,
                "role": "result",
                "is_primary": ordinal == 0,
            }
        )

    manifest = build_manifest(
        kind="vibecomfy.run",
        inputs={"workflow": str(workflow_path)},
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
            )
    except Exception as exc:
        print(f"vibecomfy.run: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
