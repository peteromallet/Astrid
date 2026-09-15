"""The explicit Astrid operator boundary for neutral-runtime upgrades.

This module resolves the installation-owned target and delegates the actual
database/storage transition to ``banodoco-local``.  Astrid only fences its
managed pack host before the handoff and verifies a normal relaunch after it.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from .autobootstrap import (
    AutoBootstrapError,
    _launcher_command,
    _result,
    ensure_runtime,
)
from .storage_root import resolve_runtime_data_root

PROFILE = "astrid"


class UpgradeError(RuntimeError):
    """A bounded operator-upgrade failure with no storage-side effects."""


def _absolute(value: str | Path, *, label: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise UpgradeError(f"{label} must be an absolute path")
    path = path.absolute()
    current = path
    while True:
        if current.is_symlink():
            raise UpgradeError(f"{label} must not contain a symlink: {path}")
        if current == current.parent:
            break
        current = current.parent
    return path


def _catalog(root: Path) -> Mapping[str, Any] | None:
    catalog = root / "runtime" / "catalog.json"
    if not catalog.is_file() or catalog.is_symlink():
        return None
    try:
        value = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpgradeError(f"runtime catalog is unreadable: {catalog}") from exc
    if not isinstance(value, Mapping):
        raise UpgradeError(f"runtime catalog must contain an object: {catalog}")
    return value


def _realm_id(root: Path, value: Mapping[str, Any]) -> str:
    selected = str(value.get("selected_realm_id") or "")
    realms = value.get("realms")
    if not selected or not isinstance(realms, list):
        raise UpgradeError(f"runtime source is not a selected one-realm catalog: {root}")
    matches = [item for item in realms if isinstance(item, Mapping) and str(item.get("realm_id") or "") == selected]
    if len(matches) != 1:
        raise UpgradeError(f"runtime source has ambiguous realm selection: {root}")
    return selected


def _legacy_source() -> Path | None:
    """Return the known old support root only when it has a valid selection."""
    root = (Path.home() / "Library" / "Application Support" / "Banodoco").absolute()
    value = _catalog(root)
    if value is None:
        return None
    _realm_id(root, value)
    return root


def resolve_upgrade_roots(
    *, source: str | Path | None = None, destination: str | Path | None = None
) -> tuple[Path, Path, str]:
    """Resolve ``(source, target, realm_id)`` without creating any state."""
    target = _absolute(destination, label="upgrade destination") if destination is not None else resolve_runtime_data_root()
    target = _absolute(target, label="upgrade destination")
    target_catalog = _catalog(target)

    if source is not None:
        source_root = _absolute(source, label="upgrade source")
    elif target_catalog is not None:
        # A completed migration is idempotent: ask the neutral launcher to
        # inspect the configured root instead of falling back to old storage.
        source_root = target
    else:
        source_root = _legacy_source() or target

    source_catalog = _catalog(source_root)
    if source_catalog is None:
        raise UpgradeError(
            "no existing runtime source was found; refusing to create an empty realm"
        )
    realm_id = _realm_id(source_root, source_catalog)
    return source_root, target, realm_id


@contextmanager
def _pack_host_lock(runtime_support: Path) -> Iterator[None]:
    lock_path = runtime_support / "generic-host.lock"
    try:
        handle = lock_path.open("a+")
    except OSError as exc:
        raise UpgradeError(f"generic Astrid pack host lock is unavailable: {lock_path}") from exc
    try:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise UpgradeError("generic Astrid pack host lifecycle is busy") from exc
        except (ImportError, OSError) as exc:
            raise UpgradeError("generic Astrid pack host lock is unavailable") from exc
        yield
    finally:
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        handle.close()


def stop_pack_host(data_root: str | Path) -> Mapping[str, Any]:
    """Stop one verified idle Astrid pack host under its lifecycle lock."""
    from . import host_bootstrap

    support = _absolute(data_root, label="runtime source") / "runtime"
    state_path = support / "generic-host.json"
    ready_path = support / "generic-host.ready.json"
    with _pack_host_lock(support):
        state = host_bootstrap._read_object(state_path)
        ready = host_bootstrap._read_object(ready_path)
        markers = tuple(marker for marker in (state, ready) if marker)
        candidate = state or ready
        if not candidate:
            return {"host_status": "absent"}
        live_markers = [marker for marker in markers if host_bootstrap._host_pid_alive(marker.get("pid"))]
        if len({str(marker.get("pid")) for marker in live_markers}) > 1:
            raise UpgradeError("generic Astrid pack host markers identify multiple live owners")
        pid = (live_markers[0] if live_markers else candidate).get("pid")
        if live_markers:
            if not state or not host_bootstrap._host_identity_matches(state):
                raise UpgradeError("existing generic Astrid pack host cannot be verified safely")
            if host_bootstrap._descendant_snapshot(int(pid)):
                raise UpgradeError("generic Astrid pack host has active child work; upgrade refused")
            try:
                host_bootstrap._terminate_old_host(state)
            except Exception as exc:
                raise UpgradeError(f"generic Astrid pack host could not be stopped: {exc}") from exc
        state_path.unlink(missing_ok=True)
        ready_path.unlink(missing_ok=True)
        return {"host_status": "stopped", "host_pid": int(pid) if str(pid).isdigit() else None}


def _launcher_upgrade(
    source: Path, target: Path, source_manifest: Path | None
) -> Mapping[str, Any]:
    command = [*_launcher_command(), "upgrade", "--profile", PROFILE, "--data-root", str(source)]
    if target != source:
        command.extend(("--destination", str(target)))
    if source_manifest is not None:
        command.extend(("--source-manifest", str(source_manifest)))
    command.append("--json")
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except Exception as exc:
        raise UpgradeError(f"neutral runtime upgrade could not be started: {exc}") from exc
    try:
        value = _result(completed.stdout.strip())
    except AutoBootstrapError as exc:
        raise UpgradeError(str(exc)) from exc
    if completed.returncode != 0 or value.get("ok") is False:
        detail = value.get("error") or "neutral runtime upgrade failed"
        raise UpgradeError(str(detail))
    return value


def upgrade(
    *, source: str | Path | None = None,
    destination: str | Path | None = None,
    source_manifest: str | Path | None = None,
) -> Mapping[str, Any]:
    """Perform one explicit neutral upgrade and verify the normal relaunch."""
    source_root, target, realm_id = resolve_upgrade_roots(source=source, destination=destination)
    manifest = None
    if source_manifest is not None:
        manifest = _absolute(source_manifest, label="source manifest")
        if not manifest.is_file():
            raise UpgradeError(f"source manifest is missing: {manifest}")
    stopped = stop_pack_host(source_root)
    try:
        result = _launcher_upgrade(source_root, target, manifest)
    except Exception as exc:
        # The neutral command owns database rollback.  Restore the normal
        # launcher/host handoff if it rejected the source before activation.
        try:
            source_still_exists = _catalog(source_root) is not None
        except UpgradeError:
            source_still_exists = False
        if source_still_exists:
            try:
                ensure_runtime(start_pack_host=True, data_root=source_root)
            except Exception as restore_exc:
                raise UpgradeError(f"{exc}; old host restart failed: {restore_exc}") from restore_exc
        raise
    activated_catalog = _catalog(target)
    if activated_catalog is None:
        raise UpgradeError(
            "neutral runtime upgrade returned success without an activated catalog; refusing blank-realm launch"
        )
    if _realm_id(target, activated_catalog) != realm_id:
        raise UpgradeError("neutral runtime upgrade activated a different selected realm")
    try:
        relaunched = ensure_runtime(start_pack_host=True, data_root=target)
    except Exception as exc:
        raise UpgradeError(f"upgrade activated but normal Astrid relaunch failed: {exc}") from exc
    return {
        "ok": True,
        "realm_id": realm_id,
        "source_root": str(source_root),
        "target_root": str(target),
        "host": dict(stopped),
        "upgrade": dict(result),
        "runtime": {
            key: value
            for key, value in relaunched.items()
            if key not in {"credential_file", "worker_credential_file"}
        },
    }


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(prog="astrid-upgrade", description="Upgrade the Astrid neutral runtime")
    command.add_argument("--data-root", type=Path, help="existing source support root")
    command.add_argument("--destination", type=Path, help="configured target support root")
    command.add_argument("--source-manifest", type=Path)
    command.add_argument("--json", action="store_true")
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        value = upgrade(source=args.data_root, destination=args.destination, source_manifest=args.source_manifest)
    except (UpgradeError, AutoBootstrapError, ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(dict(value), indent=2 if args.json else None, sort_keys=True))
    return 0


__all__ = ["UpgradeError", "main", "parser", "resolve_upgrade_roots", "stop_pack_host", "upgrade"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
