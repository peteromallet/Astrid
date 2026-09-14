"""Run an environment-based tool with one Astrid-resolved credential."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from astrid.core.contracts.errors import AstridError
from astrid.core.util.credentials_scope import _PROVIDER_ENV, CredentialsScope


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="astrid-with-credential",
        description=(
            "Resolve one credential through Astrid and pass it only to a child process. "
            "The credential is never placed in arguments or written to disk."
        ),
    )
    parser.add_argument("--provider", choices=sorted(_PROVIDER_ENV), required=True)
    parser.add_argument(
        "--reference",
        help="Use a profile-specific environment-variable reference.",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        _parser().error("provide a child command after --")

    try:
        credential = CredentialsScope.resolve_local(
            args.provider,
            env_var=args.reference,
        )
    except AstridError as exc:
        print(f"astrid-with-credential: {exc.cause}", file=sys.stderr)
        if exc.recovery_command:
            print(f"Next: {exc.recovery_command}", file=sys.stderr)
        return 1

    print(
        "astrid-with-credential: "
        f"using {credential.source} for {credential.provider} ({credential.reference})",
        file=sys.stderr,
    )
    child_env = os.environ.copy()
    child_env[credential.reference] = credential.value
    try:
        return int(subprocess.run(command, env=child_env, check=False).returncode)
    except OSError as exc:
        print(f"astrid-with-credential: could not start {command[0]!r}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
