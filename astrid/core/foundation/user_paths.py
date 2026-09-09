"""Shared paths for per-user and per-workspace Astrid state."""

from __future__ import annotations

import os
from pathlib import Path

ASTRID_HOME_ENV = "ASTRID_HOME"
ASTRID_WORKSPACE_CONFIG_DIR_ENV = "ASTRID_WORKSPACE_CONFIG_DIR"
USER_CONFIG_FILENAME = "config.json"
WORKSPACE_CONFIG_DIRNAME = ".astrid"
WORKSPACE_CONFIG_FILENAME = "config.json"

_DEFAULT_ASTRID_HOME = Path("~/.astrid")


def astrid_home() -> Path:
    """Return the per-user Astrid state directory."""
    raw = os.environ.get(ASTRID_HOME_ENV)
    base = Path(raw) if raw else _DEFAULT_ASTRID_HOME
    return base.expanduser().resolve()


def user_config_path() -> Path:
    """Return the per-user preference file path."""
    return astrid_home() / USER_CONFIG_FILENAME


def workspace_config_path(cwd: str | Path | None = None) -> Path:
    """Return the workspace preference file path."""
    override = os.environ.get(ASTRID_WORKSPACE_CONFIG_DIR_ENV)
    if override and cwd is None:
        return Path(override).expanduser().resolve() / WORKSPACE_CONFIG_FILENAME
    base = Path(cwd) if cwd is not None else Path.cwd()
    return base / WORKSPACE_CONFIG_DIRNAME / WORKSPACE_CONFIG_FILENAME


__all__ = [
    "ASTRID_HOME_ENV",
    "ASTRID_WORKSPACE_CONFIG_DIR_ENV",
    "USER_CONFIG_FILENAME",
    "WORKSPACE_CONFIG_DIRNAME",
    "WORKSPACE_CONFIG_FILENAME",
    "astrid_home",
    "user_config_path",
    "workspace_config_path",
]
