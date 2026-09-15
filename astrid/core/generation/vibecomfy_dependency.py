"""Selection and validation of Astrid's supported VibeComfy dependency."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping
from pathlib import Path

VIBECOMFY_CHECKOUT_ENV = "ASTRID_VIBECOMFY_CHECKOUT"
VIBECOMFY_ENGINE_REVISION = "a6a0cdb493c2f8bea4115740b96ec4c118af7ad1"
VIBECOMFY_FORK_URL = "https://github.com/AstridAnon/VibeComfy.git"


class VibeComfyDependencyError(ValueError):
    """The configured VibeComfy source cannot satisfy the supported pin."""


def configured_vibecomfy_checkout(environ: Mapping[str, str] | None = None) -> Path | None:
    """Return the explicitly configured, exact VibeComfy source checkout.

    A checkout is opt-in and must be an absolute Git worktree at the exact
    reviewed revision. This keeps an ambient ``PYTHONPATH`` or an arbitrary
    installed package from silently replacing the supported dependency.
    """

    env = os.environ if environ is None else environ
    raw = str(env.get(VIBECOMFY_CHECKOUT_ENV, "")).strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise VibeComfyDependencyError(
            f"{VIBECOMFY_CHECKOUT_ENV} must be an absolute VibeComfy checkout"
        )
    checkout = candidate.resolve()
    if not checkout.is_dir() or not (checkout / "vibecomfy" / "__init__.py").is_file():
        raise VibeComfyDependencyError(
            f"{VIBECOMFY_CHECKOUT_ENV} must name a VibeComfy source checkout"
        )
    try:
        result = subprocess.run(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VibeComfyDependencyError(
            f"{VIBECOMFY_CHECKOUT_ENV} could not be identity-checked"
        ) from exc
    revision = result.stdout.strip() if result.returncode == 0 else ""
    if revision != VIBECOMFY_ENGINE_REVISION:
        raise VibeComfyDependencyError(
            f"{VIBECOMFY_CHECKOUT_ENV} must resolve to VibeComfy revision "
            f"{VIBECOMFY_ENGINE_REVISION}"
        )
    try:
        clean = subprocess.run(
            ["git", "-C", str(checkout), "status", "--porcelain", "--untracked-files=all"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise VibeComfyDependencyError(
            f"{VIBECOMFY_CHECKOUT_ENV} could not verify clean source content"
        ) from exc
    if clean.returncode != 0 or clean.stdout.strip():
        raise VibeComfyDependencyError(
            f"{VIBECOMFY_CHECKOUT_ENV} must be a clean VibeComfy checkout"
        )
    return checkout


def dependency_pythonpath(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Return approved dependency roots for both host and executor children."""

    env = os.environ if environ is None else environ
    values: list[str] = []
    checkout = configured_vibecomfy_checkout(env)
    if checkout is not None:
        values.append(str(checkout))
    for raw in str(env.get("PYTHONPATH", "")).split(os.pathsep):
        if not raw:
            continue
        path = Path(raw)
        if path.name in {"site-packages", "dist-packages"}:
            values.append(str(path))
    return tuple(dict.fromkeys(values))


__all__ = [
    "VIBECOMFY_CHECKOUT_ENV",
    "VIBECOMFY_ENGINE_REVISION",
    "VIBECOMFY_FORK_URL",
    "VibeComfyDependencyError",
    "configured_vibecomfy_checkout",
    "dependency_pythonpath",
]
