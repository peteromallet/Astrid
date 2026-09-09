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

from astrid.core._shared.result_manifest import build_manifest, write_manifest
from astrid.core.cli_choices import add_choice_arg


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VibeComfy workflow commands.")
    add_choice_arg(parser, "command", values=("run", "validate"))
    parser.add_argument("workflow", type=Path)
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


def _run_and_settle(
    workflow_path: Path,
    output_root: Path,
    *,
    task_identity: str | None,
    execution_identity: str = "-",
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
    inventory = production_engine.run_workflow_path(
        workflow_path,
        output_root,
        task_identity=task_identity,
        expected_execution_identity=(
            None if execution_identity == "-" else execution_identity
        ),
        profile_id=profile_id,
        hc03_profile=readiness_profile,
    )

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
    if args.command == "validate":
        return subprocess.run(
            [sys.executable, "-m", "vibecomfy.cli", "validate", str(args.workflow)]
        ).returncode
    if args.out is None:
        print("vibecomfy.run: --out is required for run", file=sys.stderr)
        return 2
    try:
        _run_and_settle(
            args.workflow,
            args.out,
            task_identity=args.task_identity,
            execution_identity=args.execution_identity,
            readiness_profile_path=args.readiness_profile_path,
            readiness_profile_hash=args.readiness_profile_hash,
        )
    except Exception as exc:
        print(f"vibecomfy.run: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
