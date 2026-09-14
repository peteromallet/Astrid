"""API key resolution from Astrid's shared local environment file.

Local resolution has one deterministic policy: explicit value, shared
``astrid.env``, process environment, then an explicitly named fallback file.
Broad cwd/repository/workspace env-file scavenging remains disabled.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values

from astrid.core.contracts.errors import AstridError
from astrid.core.env_vars import ASTRID_ENV_FILE, ASTRID_HOME

EnvSearchProfile = Literal["default"]

_RECOVERY_HINTS: dict[str, str] = {
    "GIPHY_API_KEY": "Get a GIPHY API key at https://developers.giphy.com/dashboard/.",
}


# ---------------------------------------------------------------------------
# Env-file parsing and discovery
# ---------------------------------------------------------------------------


def read_env_value(env_path: Path | str, key: str) -> str:
    """Read one value using the same dotenv parser as RunPod/VibeComfy."""

    env_path = Path(env_path).expanduser()
    if not env_path.is_file():
        return ""
    # Values in the shared file are literal credentials; do not expand ${...}.
    values = dotenv_values(env_path, encoding="utf-8", interpolate=False)
    value = values.get(key)
    return value.strip() if isinstance(value, str) else ""


def astrid_env_file_path(environ: Mapping[str, str] | None = None) -> Path:
    """Return the shared per-user Astrid environment-file path.

    ``ASTRID_ENV_FILE`` can point at a mounted file in containers or another
    operating environment. Otherwise the file lives in Astrid's state home,
    defaulting to ``~/.astrid/astrid.env``.
    """

    env = os.environ if environ is None else environ
    astrid_home = env.get(ASTRID_HOME, "").strip()
    root = (Path(astrid_home).expanduser() if astrid_home else Path.home() / ".astrid").resolve()
    override = env.get(ASTRID_ENV_FILE, "").strip()
    if override:
        override_path = Path(override).expanduser()
        return override_path if override_path.is_absolute() else root / override_path
    return root / "astrid.env"


def load_local_api_key_with_source(
    name: str,
    *,
    explicit: str | None = None,
    env_file: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[str, str]:
    """Resolve a local credential from Astrid's shared file first.

    Precedence is explicit value, shared ``astrid.env``, process environment,
    then an optional caller-named env file. The shared file therefore wins
    over stale project-local dotenv copies while environment-only operation
    remains available where no shared file exists.
    """

    if explicit is not None and str(explicit).strip():
        return str(explicit).strip(), "explicit"

    env = os.environ if environ is None else environ
    shared_file = astrid_env_file_path(env)
    if value := read_env_value(shared_file, name).strip():
        return value, "astrid_env_file"

    if value := env.get(name, "").strip():
        return value, "environment"

    if env_file is not None and env_file.expanduser().resolve() != shared_file.expanduser().resolve():
        if value := read_env_value(env_file, name).strip():
            return value, "env_file"

    recovery = (
        f"run `astrid-credential set {name}` to store it in the shared astrid.env file, "
        "or provide it through the process environment"
    )
    if hint := _RECOVERY_HINTS.get(name):
        recovery = f"{recovery}. {hint}"
    raise AstridError(
        f"{name} not found. Tried: explicit option, shared astrid.env, environment, optional env file.",
        recovery_command=recovery,
    )


def candidate_env_files(
    env_file: Path | None = None,
    *,
    profile: EnvSearchProfile = "default",
) -> list[Path]:
    """Return at most the one explicitly named env file.

    Broad cwd/repository/workspace/home env-file scavenging was removed in m4:
    an env file is consulted **only** when the caller names it explicitly. The
    ``profile`` is a no-op label and never changes the path set.
    """
    if env_file is None:
        return []
    resolved = env_file.expanduser().resolve()
    return [resolved]


# ---------------------------------------------------------------------------
# Canonical resolver
# ---------------------------------------------------------------------------


def load_api_key(
    name: str,
    env_file: Path | None = None,
    *,
    explicit: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    """Resolve *name* through Astrid's canonical credential policy.

    Args:
        name: The environment variable name (e.g. ``"FAL_KEY"``).
        env_file: An explicitly named .env file, consulted as the final
            compatibility fallback.
        explicit: A caller-supplied explicit value (highest priority tier).
        environ: The process environment mapping to read. Defaults to
            ``os.environ``.

    Returns:
        The resolved key string.

    Raises:
        AstridError: If no tier yields a value. The message names the tiers
            tried and never contains a secret value, file contents, or paths.
    """
    return load_local_api_key_with_source(
        name,
        env_file=env_file,
        explicit=explicit,
        environ=environ,
    )[0]


def scrub_secret(value: str, text: str) -> str:
    """Mask every occurrence of *value* in *text* with ``"***"``.

    Args:
        value: The secret string to mask.
        text: The text that may contain the secret.

    Returns:
        *text* with all occurrences of *value* replaced by ``"***"``.
    """
    if not value:
        return text
    return text.replace(value, "***")
