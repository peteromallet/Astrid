"""Explicit Astrid launcher boundary for the neutral runtime."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Mapping

PROFILE = "astrid"
RECONFIGURE_ACTION = "run `banodoco-local up --profile astrid`"
INSTALL_RUNTIME_ACTION = (
    "python3 -m pip install 'banodoco-workspace-runtime @ "
    "git+https://github.com/banodoco/banodoco-workspace-runtime.git@"
    "bc74a4b2179de83ace55c35fa6371f10e1e58610'"
)


class AutoBootstrapError(RuntimeError):
    """A bounded, secret-free failure while invoking neutral bootstrap."""

    def __init__(
        self,
        message: str,
        *,
        next_action: str = RECONFIGURE_ACTION,
        code: str = "runtime_lifecycle_error",
    ) -> None:
        super().__init__(message)
        self.next_action = next_action
        self.code = code


# The neutral launcher remains the cross-process authority.  This lock only
# collapses callers in one Astrid process so a warm-up burst does not spawn a
# fleet of identical launcher commands before the first one publishes
# discovery.  Different processes still converge through banodoco-local's
# support mutex and owner lock.
_ACQUISITION_LOCK = threading.RLock()


def _configured(name: str) -> str:
    return os.environ.get(name, "").strip()


def _manifest_from_environment() -> Path | None:
    value = _configured("BANODOCO_LOCAL_SOURCE_MANIFEST")
    if not value:
        # The neutral launcher owns the persisted source profile under its
        # fixed support directory.  An ordinary Astrid relaunch must be able
        # to delegate to that profile without requiring the first-launch
        # environment variable to remain in the shell.  Do not read or
        # reconstruct the profile here: that would duplicate neutral
        # authority and bypass its source-trust validation.
        return None
    from astrid.sdk.workspace_client import _safe_local_path

    try:
        path = _safe_local_path(value, field="source manifest")
    except Exception as exc:
        raise AutoBootstrapError(
            f"configured Astrid source manifest is unsafe; {RECONFIGURE_ACTION}"
        ) from exc
    if not path.is_file():
        raise AutoBootstrapError(
            f"configured Astrid source manifest is missing; {RECONFIGURE_ACTION}"
        )
    return path


def _result(stdout: str) -> Mapping[str, Any]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AutoBootstrapError(
            f"neutral runtime bootstrap returned invalid JSON; {RECONFIGURE_ACTION}"
        ) from exc
    if not isinstance(value, Mapping):
        raise AutoBootstrapError(
            f"neutral runtime bootstrap returned an invalid result; {RECONFIGURE_ACTION}"
        )
    return value


def _launcher_command() -> list[str]:
    """Resolve the neutral launcher without relying solely on shell ``PATH``."""
    configured = _configured("BANODOCO_LOCAL_LAUNCHER")
    if configured:
        return [configured]
    executable = shutil.which("banodoco-local")
    if executable:
        return [executable]
    if find_spec("banodoco_local") is not None:
        return [sys.executable, "-m", "banodoco_local"]
    raise AutoBootstrapError(
        "the Banodoco workspace runtime is not installed",
        next_action=INSTALL_RUNTIME_ACTION,
    )


def _launcher_timeout() -> float:
    """Allow the runtime's admission budget plus launcher/process overhead."""
    raw = _configured("BANODOCO_RUNTIME_ADMISSION_TIMEOUT_SECONDS") or "120"
    try:
        admission = float(raw)
    except ValueError as exc:
        raise AutoBootstrapError("runtime admission timeout must be finite and positive") from exc
    if not math.isfinite(admission) or admission <= 0:
        raise AutoBootstrapError("runtime admission timeout must be finite and positive")
    return max(15.0, admission + 15.0)


def _discovery_present(data_root: Path) -> bool:
    """Return whether a safe, regular discovery advertisement exists.

    This is only a routing hint: the launcher validates PID, birth identity,
    owner lock, realm, and health.  Astrid never treats the file as authority.
    """
    try:
        from astrid.sdk.workspace_client import _safe_local_path

        path = _safe_local_path(data_root / "runtime" / "discovery.json", field="runtime discovery")
    except Exception:
        return False
    return path.is_file() and not path.is_symlink()


def _lifecycle_result(
    value: Mapping[str, Any],
    *,
    action: str,
    started: float,
    allowed_statuses: frozenset[str],
) -> Mapping[str, Any]:
    """Validate a launcher result while preserving its lifecycle cause."""
    if value.get("ok") is False:
        reason = str(value.get("error") or "launcher rejected the request")
        raise AutoBootstrapError(
            f"neutral runtime {action} was not ready: {reason}; {RECONFIGURE_ACTION}",
            code="runtime_" + action + "_rejected",
        )
    status = str(value.get("status", ""))
    if status not in allowed_statuses:
        raise AutoBootstrapError(
            f"neutral runtime {action} returned no ready status ({status or 'missing'}); {RECONFIGURE_ACTION}",
            code="runtime_invalid_result",
        )
    for field in ("realm_id", "endpoint", "actor_id"):
        item = value.get(field)
        if not isinstance(item, str) or not item.strip():
            raise AutoBootstrapError(
                f"neutral runtime {action} returned no {field}; {RECONFIGURE_ACTION}",
                code="runtime_invalid_result",
            )
    from astrid.sdk.workspace_client import validate_runtime_endpoint

    try:
        validate_runtime_endpoint(value["endpoint"])
    except Exception as exc:
        raise AutoBootstrapError(
            f"neutral runtime {action} returned an unsafe endpoint; {RECONFIGURE_ACTION}",
            code="runtime_unsafe_endpoint",
        ) from exc
    result = {
        "status": status,
        "realm_id": value["realm_id"].strip(),
        "endpoint": value["endpoint"].strip(),
        "actor_id": value["actor_id"].strip(),
        "runtime_instance_id": value.get("runtime_instance_id"),
        "coordinator_epoch": value.get("coordinator_epoch"),
        "credential_file": value.get("credential_file", ""),
        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
    }
    # Keep the non-secret fields that the existing generic pack-host contract
    # consumes.  The launcher owns source selection; dropping source_checkout
    # here makes a real worker handoff look incomplete and silently skips host
    # startup.  Runtime identity fields are likewise carried through when the
    # launcher provides them so host reuse can remain bound to this runtime.
    for field in (
        "worker_credential_file",
        "worker_actor",
        "worker_scopes",
        "source_checkout",
        "runtime_epoch",
        "schema_digest",
    ):
        if field in value:
            result[field] = value[field]
    credential_file = result["credential_file"]
    if credential_file:
        if not isinstance(credential_file, str):
            raise AutoBootstrapError(
                f"neutral runtime {action} returned an invalid credential path; {RECONFIGURE_ACTION}",
                code="runtime_invalid_result",
            )
        try:
            from astrid.sdk.workspace_client import _safe_local_path

            credential_path = _safe_local_path(credential_file, field="credential")
        except Exception as exc:
            raise AutoBootstrapError(
                f"neutral runtime {action} returned an unsafe credential path; {RECONFIGURE_ACTION}",
                code="runtime_unsafe_credential",
            ) from exc
        if not credential_path.is_file() or credential_path.is_symlink():
            raise AutoBootstrapError(
                f"neutral runtime {action} returned a missing credential file; {RECONFIGURE_ACTION}",
                code="runtime_missing_credential",
            )
    return result


def _invoke_launcher(
    command: list[str],
    *,
    action: str,
    allowed_statuses: frozenset[str],
) -> Mapping[str, Any]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=_launcher_timeout(),
        )
    except subprocess.TimeoutExpired as exc:
        raise AutoBootstrapError(
            f"neutral runtime {action} timed out; {RECONFIGURE_ACTION}",
            code="runtime_startup_interrupted",
        ) from exc
    except OSError as exc:
        raise AutoBootstrapError(
            f"neutral runtime {action} could not be started; {RECONFIGURE_ACTION}",
            code="runtime_launcher_unavailable",
        ) from exc
    value = _result(completed.stdout.strip())
    if completed.returncode != 0 and value.get("ok") is not False:
        raise AutoBootstrapError(
            f"neutral runtime {action} exited with status {completed.returncode}; {RECONFIGURE_ACTION}",
            code="runtime_launcher_failed",
        )
    return _lifecycle_result(
        value,
        action=action,
        started=started,
        allowed_statuses=allowed_statuses,
    )


def _bootstrap_with_recovery(command: list[str]) -> Mapping[str, Any]:
    """Retry one interrupted admission through the same launcher authority."""
    try:
        return _invoke_launcher(
            command,
            action="bootstrap",
            allowed_statuses=frozenset({"started", "reconnected", "restarted"}),
        )
    except AutoBootstrapError as exc:
        if exc.code != "runtime_startup_interrupted":
            raise
        # The CLI process can be interrupted after it has handed ownership to
        # the daemon but before it emits JSON. A single bounded retry lets the
        # launcher inspect and repair that partial handoff; it cannot create a
        # second owner because the launcher owns the support mutex/lock.
        return _invoke_launcher(
            command,
            action="bootstrap_recovery",
            allowed_statuses=frozenset({"started", "reconnected", "restarted"}),
        )


def _connection_failure_is_recoverable(exc: AutoBootstrapError) -> bool:
    """Allow ``up`` only for stale advertisement state, not every rejection."""
    if exc.code != "runtime_connection_rejected":
        return False
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "no runtime discovery",
            "no healthy selected runtime",
            "discovery is stale",
            "discovery is incomplete",
            "discovery does not match",
            "owner is unhealthy",
            "owned by another process",
        )
    )


def ensure_runtime(*, start_pack_host: bool = True, data_root: str | Path | None = None) -> Mapping[str, Any]:
    """Invoke the installed launcher once and return its bounded result.

    Runtime reads may connect while an existing pack-host child is busy.  The
    neutral runtime remains the authority for those reads; only execution
    needs the generic pack host to be registered and preflight-ready.
    """
    manifest = _manifest_from_environment()
    explicit_data_root = data_root is not None
    try:
        from astrid.sdk.storage_root import ensure_no_unmigrated_runtime, resolve_runtime_data_root

        data_root = (
            Path(data_root).expanduser().absolute()
            if explicit_data_root
            else resolve_runtime_data_root()
        )
        if data_root is not None and not explicit_data_root:
            ensure_no_unmigrated_runtime(data_root)
    except ValueError as exc:
        next_action = (
            "run `astrid-upgrade`"
            if "astrid-upgrade" in str(exc)
            else RECONFIGURE_ACTION
        )
        raise AutoBootstrapError(
            f"Astrid runtime data-root is not ready: {exc}; {next_action}",
            next_action=next_action,
        ) from exc
    launcher = _launcher_command()
    base = [*launcher, "up", "--profile", PROFILE]
    if manifest is not None:
        base.extend(("--source-manifest", str(manifest)))
    if data_root is not None:
        base.extend(("--data-root", str(data_root)))
    with _ACQUISITION_LOCK:
        value: Mapping[str, Any] | None = None
        if data_root is not None and _discovery_present(Path(data_root)):
            connect_command = [*launcher, "connect", "--profile", PROFILE]
            if manifest is not None:
                connect_command.extend(("--source-manifest", str(manifest)))
            connect_command.extend(("--data-root", str(data_root), "--json"))
            try:
                value = _invoke_launcher(
                    connect_command,
                    action="connection",
                    allowed_statuses=frozenset({"reconnected"}),
                )
            except AutoBootstrapError as exc:
                # Only stale/missing/unhealthy discovery is eligible for the
                # authoritative up recovery. Security, protocol, and launcher
                # failures remain typed failures and are never masked.
                if not _connection_failure_is_recoverable(exc):
                    raise
        if value is None:
            up_command = [*base, "--json"]
            value = _bootstrap_with_recovery(up_command)

    worker_handoff: dict[str, Any] = {}
    credential_file = value.get("credential_file", "")
    if value.get("worker_credential_file"):
        worker_file = value.get("worker_credential_file")
        if not isinstance(worker_file, str):
            raise AutoBootstrapError(f"neutral runtime bootstrap returned an invalid worker credential path; {RECONFIGURE_ACTION}")
        try:
            from astrid.sdk.workspace_client import _safe_local_path

            worker_path = _safe_local_path(worker_file, field="worker credential")
        except Exception as exc:
            raise AutoBootstrapError(f"neutral runtime bootstrap returned an unsafe worker credential path; {RECONFIGURE_ACTION}") from exc
        if not worker_path.is_file() or worker_path.is_symlink():
            raise AutoBootstrapError(f"neutral runtime bootstrap returned a missing worker credential file; {RECONFIGURE_ACTION}")
        worker_handoff = {
            "worker_credential_file": str(worker_path),
            "worker_actor": value.get("worker_actor"),
            "worker_scopes": value.get("worker_scopes", ()),
        }
    result = dict(value)
    # The launcher returns only a path to the owner-only credential file;
    # never put the credential value in the subprocess result or logs.
    result.update(worker_handoff)
    if worker_handoff and start_pack_host:
        from astrid.sdk.host_bootstrap import PackHostBootstrapError, ensure_pack_host

        try:
            result.update(ensure_pack_host(value, reconfigure_action=RECONFIGURE_ACTION))
        except PackHostBootstrapError as exc:
            raise AutoBootstrapError(str(exc)) from exc
    return result


__all__ = ["AutoBootstrapError", "ensure_runtime"]
