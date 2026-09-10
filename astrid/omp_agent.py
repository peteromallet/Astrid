"""Launch the named Astrid agent through oh-my-pi (OMP).

The installed ``astrid`` command is the conversational surface.  The product
gateway remains available as ``astrid-tools`` and through ``python -m astrid``.
Keeping this wrapper small and stdlib-only means ``astrid --help`` remains
usable even when the optional Astrid runtime dependencies are not installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .core.auth import AUTH_COMMANDS, contributor_auth_system_notice, run_auth
from .version import ASTRID_VERSION

DEFAULT_AGENT = "astrid"

# ``astrid`` is the single user-facing command.  The conversational agent is
# the default route, while these names retain the product gateway's compact
# toolkit surface.  Keep this list explicit: an unknown first word is useful
# natural-language input and must continue to become a one-shot prompt.
_TOOLKIT_FAMILIES = frozenset(
    {"projects", "timelines", "media", "tasks", "runs", "doctor", "backup"}
)
_AUTH_ALIASES = frozenset(AUTH_COMMANDS)

_LAUNCHER_CANDIDATES: tuple[Path, ...] = (Path.home() / ".bun" / "bin" / "agent",)
_PATH_FALLBACK_BLOCKLIST: tuple[str, ...] = (".grok",)
_BRANDED_OMP = (
    Path.home() / "Documents" / "oh-my-pi" / "packages" / "coding-agent" / "dist" / "omp"
)

_HELP_FLAGS = frozenset({"-h", "--help"})
_VERSION_FLAGS = frozenset({"-v", "--version"})
_VALUE_FLAGS = frozenset(
    {
        "-r",
        "--resume",
        "--session-dir",
        "--profile",
        "--system-prompt",
        "--append-system-prompt",
    }
)
_ONBOARD_HELP_MARKER = "detect-first provider onboarding"

# This is retained as an explicit environment override for installations that
# want a small extra prompt.  The named `astrid` agent already supplies its
# profile through `agent --system-prompt`; appending this by default would
# duplicate the profile and create competing replacement/append paths.
ASTRID_SYSTEM_PROMPT = """\
You are Astrid, the creative-production agent for the Astrid media toolkit.

As your first action in each new session, perform one bounded update preflight.
Use each checkout's configured upstream and only a fast-forward pull when the
worktree is clean; never stash, reset, merge, rebase, or overwrite user work.
After an Astrid update run `python3 -m astrid.skills sync`. After a custom OMP
update use its established branded-build path:
`cd ~/Documents/oh-my-pi/packages/coding-agent && bun run build`; never replace
it with stock OMP self-update. Network/update failures must not block the user's
request. Linked skills can be refreshed with `/reload-plugins`; rebuilt OMP and
system-prompt changes take effect on the next `astrid` launch, so mention when a
restart is needed.

Read the discovered `astrid` skill first (`skill://astrid`) and follow its
linked pack route. Use discovered `astrid-references`, `hivemind`, and
`vibecomfy` skills when their capabilities match the request. Treat the
Astrid runtime as the authority for project and media state; do not edit its
database or invent filesystem side channels. For the product CLI use
`astrid-tools` (or `python3 -m astrid`); prefer JSON output for inspection and
report artifacts, exit status, and the next useful action clearly.

Hivemind contributor access is optional. Public Hivemind search and ordinary
Astrid work remain available without login. Contribution and ingestion actions
require Discord contributor authentication: if the user asks to contribute
while not logged in, say so and offer `astrid login`; do not block unrelated
work.
"""


_USAGE = """\
usage: astrid [flags] [message...]

Run Astrid. Bare = interactive OMP agent; a message = one-shot agent prompt.
Toolkit families dispatch to the Astrid product gateway. Use ``astrid agent``
when you want to make the agent route explicit.

  astrid                         interactive Astrid agent
  astrid agent [flags] [message] interactive/one-shot Astrid agent
  astrid <toolkit> ...           product toolkit gateway
  astrid login                   log in for Hivemind contributions
  astrid status                  show Hivemind contributor login status
  astrid logout                  remove the local Hivemind login
  astrid revoke                  revoke the Hivemind contributor login
  astrid help                    product toolkit help

  --agent NAME     talk to a different installed agent (default: astrid)
  --onboard        run OMP provider setup, then exit
  -v, --version    show the Astrid product version
  -c               continue the most recent conversation
  --resume ID      resume a specific session
  -h, --help       show this help

Launcher: ASTRID_AGENT_LAUNCHER env var, else ~/.bun/bin/agent.
OMP binary: OMP_BIN env var, else the branded Astrid-compatible build, then PATH.
"""


def _print_version(stream=None) -> None:
    """Print Astrid's product version without booting the OMP runtime."""
    stream = sys.stdout if stream is None else stream
    print(f"astrid/{ASTRID_VERSION}", file=stream)


def _print_unified_help(stream=None) -> None:
    """Print the top-level command contract without starting OMP or a runtime."""
    stream = sys.stdout if stream is None else stream
    print(_USAGE, end="", file=stream)
    print("Toolkit families: " + " ".join(sorted(_TOOLKIT_FAMILIES)), file=stream)
    print(
        "\nExamples:\n"
        "  astrid projects list --json\n"
        "  astrid timelines list --project PROJECT\n"
        "  astrid agent --resume SESSION\n"
        "  astrid \"draft a cinematic shot list\"\n",
        file=stream,
    )


def _dispatch_toolkit(rest: list[str]) -> int:
    """Delegate a recognized product family to the canonical gateway."""
    # Delayed import keeps the interactive launcher usable in a minimal OMP
    # installation and makes ``astrid --help`` independent of runtime deps.
    from astrid.core.gateway import main as gateway_main

    return int(gateway_main(rest))


def _find_launcher(env=None) -> Path | None:
    """Find OMP's named-agent launcher, avoiding unrelated vendor binaries."""
    target = os.environ if env is None else env
    for variable in ("ASTRID_AGENT_LAUNCHER", "OMP_AGENT_LAUNCHER"):
        override = target.get(variable)
        if override:
            candidate = Path(override).expanduser()
            return candidate if candidate.is_file() else None
    for candidate in _LAUNCHER_CANDIDATES:
        if candidate.is_file():
            return candidate
    on_path = shutil.which("agent")
    if on_path and not any(marker in on_path for marker in _PATH_FALLBACK_BLOCKLIST):
        return Path(on_path)
    return None


def _resolve_omp_bin(env=None) -> str | None:
    """Resolve the OMP binary; an explicit ``OMP_BIN`` always wins."""
    target = os.environ if env is None else env
    override = target.get("OMP_BIN")
    if override:
        return override
    if target.get("ASTRID_STOCK_OMP") != "1" and _BRANDED_OMP.is_file():
        return str(_BRANDED_OMP)
    return shutil.which("omp")


def _select_omp_bin(env=None) -> None:
    """Expose the selected OMP binary to the ``agent`` launcher."""
    target = os.environ if env is None else env
    resolved = _resolve_omp_bin(target)
    if resolved and target.get("ASTRID_STOCK_OMP") != "1":
        target.setdefault("OMP_BIN", resolved)


def _omp_supports_onboard(omp_bin: str) -> bool:
    """Return whether this OMP build has the native onboarding command."""
    try:
        proc = subprocess.run(
            [omp_bin, "onboard", "--help"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and _ONBOARD_HELP_MARKER.encode() in proc.stdout + proc.stderr


def _split_flags(rest: list[str]) -> tuple[list[str], list[str]]:
    """Partition leading OMP flags from the message words."""
    flags: list[str] = []
    index = 0
    while index < len(rest) and rest[index].startswith("-"):
        token = rest[index]
        flags.append(token)
        index += 1
        if token in _VALUE_FLAGS and index < len(rest):
            flags.append(rest[index])
            index += 1
    return flags, rest[index:]


def _identity_label(agent: str) -> str:
    return "Astrid Creative Resident" if agent == DEFAULT_AGENT else f"agent · {agent}"


def _one_shot_header(agent: str) -> str:
    return f"astrid · {_identity_label(agent)}"


def _print_one_shot_header(agent: str, stream=None) -> None:
    """Brand a one-shot run without polluting piped stdout."""
    stream = sys.stderr if stream is None else stream
    if not stream.isatty():
        return
    header = _one_shot_header(agent)
    print(f"\x1b]0;{header}\x07", end="", file=stream, flush=True)
    print(f"\x1b[1m{header}\x1b[0m", file=stream, flush=True)


def _prompt_args(flags: list[str], *, agent: str = DEFAULT_AGENT, env=None) -> list[str]:
    """Return only an explicit Astrid prompt override.

    ``agent run astrid`` already passes the named profile as ``--system-prompt``.
    The built-in prompt is therefore opt-in through an environment override,
    never an additional default append.  Alternate OMP agents must not inherit
    Astrid's persona.
    """
    if "--system-prompt" in flags:
        return []
    if agent != DEFAULT_AGENT:
        return []
    target = os.environ if env is None else env
    prompt = target.get("ASTRID_SYSTEM_PROMPT")
    prompt_file = target.get("ASTRID_SYSTEM_PROMPT_FILE")
    if prompt_file:
        try:
            prompt = Path(prompt_file).expanduser().read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            # A bad optional override must not prevent the OMP session from
            # starting; fall back to the explicit text override if present.
            prompt = target.get("ASTRID_SYSTEM_PROMPT")
    auth_notice = contributor_auth_system_notice()
    prompt = f"{prompt}\n\n{auth_notice}" if prompt else auth_notice
    return ["--append-system-prompt", prompt]


def main(argv: list[str] | None = None) -> int:
    rest = list(sys.argv[1:] if argv is None else argv)

    # The console script is now the unified Astrid surface.  ``--help`` is
    # intentionally launcher help (not OMP help), while ``help`` remains the
    # gateway's full product-family help.  Explicit ``agent`` is an alias for
    # the default conversational route and consumes no prompt text itself.
    if rest and rest[0] in _HELP_FLAGS:
        _print_unified_help()
        return 0
    if rest and rest[0] == "help":
        return _dispatch_toolkit(rest)
    if rest and rest[0] == "auth":
        return run_auth(rest[1:])
    if rest and rest[0] in _AUTH_ALIASES:
        return run_auth(rest)
    if rest and rest[0] in _TOOLKIT_FAMILIES:
        return _dispatch_toolkit(rest)
    if rest and rest[0] == "agent":
        rest.pop(0)

    agent = DEFAULT_AGENT
    while "--agent" in rest:
        index = rest.index("--agent")
        rest.pop(index)
        if index >= len(rest):
            print('astrid: --agent requires a value (e.g. astrid --agent scout "hi")', file=sys.stderr)
            return 1
        agent = rest.pop(index)

    # The wrapper owns Astrid's product contract.  Do not expose OMP's
    # compatibility/runtime version here (or spend a provider request).
    if len(rest) == 1 and rest[0] in _VERSION_FLAGS:
        _print_version()
        return 0

    # The command name selects the user-visible OMP identity.  Assignment is
    # intentional: a shell that previously launched Arnold must not leak its
    # identity into a new Astrid process (including the onboarding surface).
    os.environ["OMP_AGENT_IDENTITY"] = agent
    os.environ["ASTRID_AGENT_IDENTITY"] = agent
    # Keep the OMP runtime's compatibility version separate from the version
    # shown in Astrid's interactive banner.  Assignment also prevents a
    # previously launched branded profile from leaking into this process.
    os.environ["OMP_DISPLAY_VERSION"] = ASTRID_VERSION

    if "--onboard" in rest:
        rest.remove("--onboard")
        if rest:
            print("astrid: --onboard takes no other arguments", file=sys.stderr)
            return 1
        omp_bin = _resolve_omp_bin()
        if omp_bin is None or not _omp_supports_onboard(omp_bin):
            print("astrid: this OMP build does not support native onboarding", file=sys.stderr)
            return 1
        os.execvp(omp_bin, [omp_bin, "onboard"])
        return 1  # pragma: no cover - execvp replaces the process

    flags, message = _split_flags(rest)
    if not message and _HELP_FLAGS.intersection(flags):
        print(_USAGE, end="")
        return 0
    if any(token.startswith("-") for token in message):
        print("astrid: flags must precede the message, e.g. astrid -c \"follow-up\"", file=sys.stderr)
        return 1

    launcher = _find_launcher()
    if launcher is None:
        print(
            "astrid: could not locate the omp agent launcher. Install oh-my-pi "
            "(~/.bun/bin/agent) or set ASTRID_AGENT_LAUNCHER to its 'agent' script.",
            file=sys.stderr,
        )
        return 1

    _select_omp_bin()
    exec_argv = [str(launcher), "run", agent, *flags]
    if not any(flag in flags for flag in ("--system-prompt", "--append-system-prompt")):
        exec_argv += _prompt_args(flags, agent=agent)
    if message:
        exec_argv += ["--print", *message]
        _print_one_shot_header(agent)
    os.execvp(str(launcher), exec_argv)
    return 1  # pragma: no cover - execvp replaces the process


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
