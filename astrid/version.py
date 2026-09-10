"""Astrid's distribution version.

The project metadata in ``pyproject.toml`` is the canonical source.  Installed
packages use their distribution metadata; a source checkout falls back to the
local metadata file so the launcher remains usable before installation.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib


def _source_version() -> str:
    metadata_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with metadata_path.open("rb") as stream:
        metadata = tomllib.load(stream)
    project = metadata.get("project", {})
    value = project.get("version")
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"Astrid project metadata has no valid version: {metadata_path}")
    return value.strip()


try:
    __version__ = version("astrid")
except PackageNotFoundError:
    __version__ = _source_version()


ASTRID_VERSION = __version__

__all__ = ["ASTRID_VERSION", "__version__"]
