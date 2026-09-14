"""Runtime entrypoint for vibecomfy.*."""


from __future__ import annotations

from astrid.core.pack.entrypoint import guard_canonical_entrypoint

guard_canonical_entrypoint('vibecomfy.validate')
import argparse  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402

from astrid.core.cli_choices import add_choice_arg  # noqa: E402
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with staged_workflow_path(
        workflow=args.workflow,
        python=args.python,
        companion=args.companion,
        source=args.source,
    ) as (workflow_path, _authority):
        return subprocess.run(
            [sys.executable, "-m", "vibecomfy.cli", args.command, str(workflow_path)]
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
