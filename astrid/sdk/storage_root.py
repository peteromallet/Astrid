"""Resolve Astrid's installation-owned neutral-runtime data root.

The runtime remains the authority for the database and object store.  This
module only chooses the support-root argument passed to ``banodoco-local``;
it never opens or creates runtime state.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping


DATA_ROOT_ENV = "BANODOCO_LOCAL_DATA_ROOT"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "astrid-runtime.json"


def _safe_absolute(value: str | Path, *, base: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Astrid runtime data root contains a symlink component: {path}")
    return path


def resolve_runtime_data_root() -> Path:
    """Return the configured absolute support root.

    An environment override wins. Otherwise the checked-in install config
    anchors the default ``.astrid-data`` beside the Astrid source checkout.
    Wheel installs use ``~/.astrid-data``. Both locations are stable across
    cwd changes and separate invocations.
    """

    configured = os.environ.get(DATA_ROOT_ENV, "").strip()
    if configured:
        if not Path(configured).expanduser().is_absolute():
            raise ValueError(f"{DATA_ROOT_ENV} must be an absolute path")
        return _safe_absolute(configured, base=Path(__file__).resolve().parents[2])
    if not CONFIG_PATH.is_file() or CONFIG_PATH.is_symlink():
        # A wheel does not ship the source checkout's top-level config. Keep
        # its default persistent and cwd-independent rather than silently
        # falling back to the neutral launcher's old external support tree.
        return _safe_absolute(Path.home() / ".astrid-data", base=Path.home())
    try:
        value: Any = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Astrid runtime data-root config is invalid: {CONFIG_PATH}") from exc
    if not isinstance(value, Mapping) or value.get("version") != 1:
        raise ValueError(f"Astrid runtime data-root config is invalid: {CONFIG_PATH}")
    raw = value.get("data_root", ".astrid-data")
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Astrid runtime data-root config has no data_root: {CONFIG_PATH}")
    return _safe_absolute(raw, base=CONFIG_PATH.parent.parent)


def ensure_no_unmigrated_runtime(data_root: Path) -> None:
    """Refuse a blank default when an older selected realm still exists.

    This guard only reads the old neutral catalog. It prevents an upgrade from
    silently creating a second empty realm before an operator has reviewed a
    backup/restore relocation plan. Explicit ``BANODOCO_LOCAL_DATA_ROOT``
    overrides remain available for deliberate recovery or test composition.
    """

    if os.environ.get(DATA_ROOT_ENV, "").strip():
        return
    target_catalog = data_root / "runtime" / "catalog.json"
    if target_catalog.is_file():
        return
    legacy = Path.home() / "Library" / "Application Support" / "Banodoco" / "runtime" / "catalog.json"
    if not legacy.is_file() or legacy.is_symlink():
        return
    try:
        value = json.loads(legacy.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return
    if isinstance(value, Mapping) and value.get("selected_realm_id"):
        raise ValueError(
            "an existing neutral runtime realm is configured at "
            f"{legacy.parent}; review a relocation plan before using {data_root}"
        )


__all__ = ["CONFIG_PATH", "DATA_ROOT_ENV", "ensure_no_unmigrated_runtime", "resolve_runtime_data_root"]
