"""Run an authored VibeComfy workflow and settle its artifact inventory."""


from __future__ import annotations

from astrid.core.pack.entrypoint import guard_canonical_entrypoint

guard_canonical_entrypoint('vibecomfy.run')
import argparse
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
    return parser


def _run_and_settle(workflow_path: Path, output_root: Path) -> dict[str, Any]:
    """Run *workflow_path*, copy every engine result, and write its receipt."""
    from vibecomfy import load_workflow_any
    from vibecomfy.runtime.run import run_sync

    workflow = load_workflow_any(str(workflow_path))
    result = run_sync(workflow)
    inventory = getattr(result, "outputs", None)
    if not isinstance(inventory, (list, tuple)):
        raise ValueError("VibeComfy engine returned an invalid artifact inventory")

    sources: list[Path] = []
    for ordinal, raw_path in enumerate(inventory):
        if not isinstance(raw_path, (str, Path)) or not str(raw_path):
            raise ValueError(
                f"VibeComfy artifact inventory entry {ordinal} is not a path"
            )
        source = Path(raw_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(
                f"VibeComfy artifact inventory entry {ordinal} is missing: {source}"
            )
        sources.append(source)

    if not sources:
        raise ValueError("VibeComfy workflow completed with an empty artifact inventory")

    output_root = output_root.expanduser().resolve()
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
        engine_run_id=getattr(result, "run_id", None),
        engine_prompt_id=getattr(result, "prompt_id", None),
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
        _run_and_settle(args.workflow, args.out)
    except Exception as exc:
        print(f"vibecomfy.run: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
