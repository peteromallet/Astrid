"""Explicit Astrid launcher boundary for the neutral runtime."""

from __future__ import annotations

import json
import hashlib
import hmac
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Iterator, Mapping

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
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.next_action = next_action
        self.code = code
        self.details = dict(details or {})


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


def _bounded_details(value: Any, *, limit: int = 16_384) -> dict[str, Any]:
    """Keep launcher-provided diagnostic details typed and bounded.

    The neutral launcher owns the underlying cause.  Preserve its small,
    machine-readable diagnostic fields instead of stringifying the whole
    response, while refusing an accidentally huge error payload.
    """
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    for key, item in list(value.items())[:32]:
        if not isinstance(key, str):
            continue
        if isinstance(item, str):
            result[key] = item[:1_000]
        elif isinstance(item, (bool, int, float)) or item is None:
            result[key] = item
        elif isinstance(item, Mapping):
            result[key] = _bounded_details(item, limit=limit)
        elif isinstance(item, (list, tuple)):
            result[key] = list(item)[:32]
    try:
        encoded = json.dumps(result, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return {"details_truncated": True}
    if len(encoded.encode("utf-8")) > limit:
        return {"details_truncated": True}
    return result


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


def _acquisition_lock_path(data_root: Path) -> Path:
    """Return the stable cross-process lock path for one canonical root."""
    return data_root.expanduser().resolve(strict=False) / "runtime" / "acquisition.lock"


def _nested_handoff_from_environment() -> Mapping[str, Any] | None:
    """Load only a complete host-issued handoff whose issuer is an ancestor."""
    from astrid.sdk.host_bootstrap import (
        NESTED_HANDOFF_HASH_ENV,
        NESTED_HANDOFF_PATH_ENV,
    )

    raw_path = os.environ.get(NESTED_HANDOFF_PATH_ENV)
    raw_hash = os.environ.get(NESTED_HANDOFF_HASH_ENV)
    if raw_path is None and raw_hash is None:
        if os.environ.get("ASTRID_INTERNAL_INVOCATION") == "1":
            raise AutoBootstrapError(
                "internal runtime acquisition requires a validated host handoff",
                code="nested_handoff_missing",
            )
        return None
    if not raw_path or not raw_hash:
        raise AutoBootstrapError("nested runtime handoff is partial", code="nested_handoff_invalid")
    path = Path(raw_path)
    try:
        metadata = path.lstat()
        if (not path.is_absolute() or path.is_symlink() or not path.is_file()
                or metadata.st_mode & 0o777 != 0o600):
            raise OSError("handoff must be an absolute owner-only regular file")
        payload = path.read_bytes()
        observed = "sha256:" + hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(observed, raw_hash):
            raise OSError("handoff bytes do not match their host-issued hash")
        value = json.loads(payload.decode("utf-8"))
        if not isinstance(value, Mapping):
            raise OSError("handoff payload must be an object")
        required = (
            "schema_version", "attempt_id", "support_root", "endpoint", "executor_id",
            "runtime_instance_id", "runtime_epoch", "schema_digest", "issuer_pid",
            "issuer_birth_id", "ready_file", "source_checkout", "source_checkout_digest",
            "source_inventory_identity", "boot_manifest_path", "boot_manifest_hash",
            "readiness_profile_path", "readiness_profile_hash",
            "vibecomfy_execution_attestation", "effective_capacity", "python_executable",
        )
        if value.get("schema_version") != 1 or any(key not in value for key in required):
            raise OSError("handoff schema or required identity is incomplete")
        for field in ("support_root", "ready_file", "source_checkout", "boot_manifest_path", "python_executable"):
            item = value.get(field)
            if not isinstance(item, str) or not Path(item).is_absolute():
                raise OSError(f"handoff {field} must be an absolute path")
        if value.get("readiness_profile_path") is not None and (
            not isinstance(value.get("readiness_profile_path"), str)
            or not Path(str(value["readiness_profile_path"])).is_absolute()
        ):
            raise OSError("handoff readiness profile path must be absolute or null")
        issuer = value.get("issuer_pid")
        birth = value.get("issuer_birth_id")
        if isinstance(issuer, bool) or not isinstance(issuer, int) or issuer <= 1 or not isinstance(birth, str) or not birth:
            raise OSError("handoff issuer identity is invalid")
        from astrid.core.execution.process_group import _process_snapshot

        census = _process_snapshot()
        current = os.getpid()
        seen: set[int] = set()
        ancestor = False
        while current in census and current not in seen:
            seen.add(current)
            info = census[current]
            if info.pid == issuer and hmac.compare_digest(info.birth, birth):
                ancestor = True
                break
            current = info.ppid
        if not ancestor:
            raise OSError("handoff issuer is not a live process ancestor")
        return dict(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise AutoBootstrapError("nested runtime handoff is invalid or stale", code="nested_handoff_invalid") from exc


@contextmanager
def _acquisition_file_lock(
    data_root: Path, *, timeout: float | None = None
) -> Iterator[None]:
    """Serialize launcher acquisition across independent Astrid processes.

    The in-process lock above only protects threads sharing one interpreter.
    A stable flock sibling is needed because LC-06 launches separate CLI
    processes concurrently.  The lock is advisory, auto-released on process
    death, and scoped to the canonical support root.  Waiting is bounded by
    the same admission budget as the launcher so a stuck peer cannot leave a
    caller hanging forever.
    """
    try:
        import fcntl
    except ImportError as exc:  # pragma: no cover - Astrid runs on POSIX
        raise AutoBootstrapError(
            f"neutral runtime acquisition lock is unavailable; {RECONFIGURE_ACTION}",
            code="runtime_acquisition_lock_unavailable",
        ) from exc

    lock_path = _acquisition_lock_path(data_root)
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+")
        os.fchmod(handle.fileno(), 0o600)
    except OSError as exc:
        raise AutoBootstrapError(
            f"neutral runtime acquisition lock is unavailable; {RECONFIGURE_ACTION}",
            code="runtime_acquisition_lock_unavailable",
        ) from exc

    wait_timeout = _launcher_timeout() if timeout is None else float(timeout)
    if wait_timeout <= 0 or not math.isfinite(wait_timeout):
        handle.close()
        raise AutoBootstrapError(
            "runtime acquisition lock timeout must be finite and positive",
            code="runtime_acquisition_lock_unavailable",
        )
    deadline = time.monotonic() + wait_timeout
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AutoBootstrapError(
                        f"neutral runtime acquisition lock timed out; {RECONFIGURE_ACTION}",
                        code="runtime_acquisition_lock_timeout",
                    )
                time.sleep(min(0.05, remaining))
            except OSError as exc:
                raise AutoBootstrapError(
                    f"neutral runtime acquisition lock is unavailable; {RECONFIGURE_ACTION}",
                    code="runtime_acquisition_lock_unavailable",
                ) from exc
        yield
    finally:
        if acquired:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def _lifecycle_result(
    value: Mapping[str, Any],
    *,
    action: str,
    started: float,
    allowed_statuses: frozenset[str],
) -> Mapping[str, Any]:
    """Validate a launcher result while preserving its lifecycle cause."""
    if value.get("ok") is False:
        raw_error = value.get("error")
        if isinstance(raw_error, Mapping):
            raw_details = _bounded_details(raw_error.get("details"))
            cause_code = raw_error.get("code")
            cause_message = raw_error.get("message")
            if isinstance(cause_code, str) and cause_code:
                raw_details.setdefault("cause_code", cause_code)
            if isinstance(cause_message, str) and cause_message:
                raw_details.setdefault("cause_message", cause_message[:1_000])
            for key in ("next_action", "recovery_action", "state"):
                if key in raw_error and key not in raw_details:
                    raw_details[key] = raw_error[key]
            reason = str(cause_message or cause_code or "launcher rejected the request")
        else:
            raw_details = {}
            reason = str(raw_error or "launcher rejected the request")
        raise AutoBootstrapError(
            f"neutral runtime {action} was not ready: {reason}; {RECONFIGURE_ACTION}",
            code="runtime_" + action + "_rejected",
            details=raw_details,
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


def _live_runtime_identity(connection: Mapping[str, Any]) -> dict[str, Any]:
    """Read canonical runtime identity from health for a selected connection."""
    from astrid.sdk.workspace_client import (
        PROTOCOL,
        SCHEMA_DIGEST,
        WorkspaceClient,
        _read_credential,
    )

    endpoint = connection.get("endpoint")
    credential_file = connection.get("worker_credential_file")
    if not isinstance(endpoint, str) or not isinstance(credential_file, str) or not credential_file:
        raise AutoBootstrapError(
            "neutral runtime connection has no explicit worker health credential",
            code="runtime_identity_unavailable",
        )
    try:
        from astrid.sdk.workspace_client import _safe_local_path, validate_runtime_endpoint

        endpoint = validate_runtime_endpoint(endpoint)
        credential_path = _safe_local_path(credential_file, field="credential")
        if credential_path.is_symlink() or not credential_path.is_file():
            raise ValueError("credential file is not a regular file")
        token = _read_credential(credential_path)
        health = WorkspaceClient(endpoint, token).health()
    except Exception as exc:
        raise AutoBootstrapError(
            "selected runtime health identity could not be verified",
            code="runtime_identity_unavailable",
        ) from exc
    if isinstance(health, Mapping):
        fields = health
    else:
        fields = {
            name: getattr(health, name, None)
            for name in (
                "status", "protocol", "schema_digest", "runtime_epoch",
                "runtime_instance_id", "runtime_session_id",
            )
        }
    epoch = fields.get("runtime_epoch")
    instance_id = fields.get("runtime_instance_id")
    schema_digest = fields.get("schema_digest")
    if (
        fields.get("status") != "ok"
        or fields.get("protocol") != PROTOCOL
        or schema_digest != SCHEMA_DIGEST
        or isinstance(epoch, bool)
        or not isinstance(epoch, int)
        or epoch < 1
        or not isinstance(instance_id, str)
        or not instance_id.strip()
        or not isinstance(fields.get("runtime_session_id"), str)
        or not fields["runtime_session_id"].strip()
    ):
        raise AutoBootstrapError(
            "selected runtime health identity is incomplete or incompatible",
            code="runtime_identity_invalid",
        )
    observed = {
        "runtime_instance_id": instance_id,
        "runtime_epoch": epoch,
        "schema_digest": schema_digest,
    }
    for field, actual in observed.items():
        asserted = connection.get(field)
        if asserted is not None and asserted != actual:
            raise AutoBootstrapError(
                f"launcher connection {field} disagrees with live runtime health",
                code="runtime_identity_mismatch",
            )
    return observed


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
    nested_handoff = _nested_handoff_from_environment()
    manifest = None if nested_handoff is not None else _manifest_from_environment()
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
    if nested_handoff is not None and data_root is not None:
        expected_support = (Path(data_root) / "runtime").resolve(strict=False)
        raw_support = nested_handoff.get("support_root")
        issued_support = Path(raw_support).resolve(strict=False) if isinstance(raw_support, str) else None
        if issued_support is None or not Path(raw_support).is_absolute() or issued_support != expected_support:
            raise AutoBootstrapError(
                "nested runtime handoff belongs to a different support root",
                code="nested_handoff_mismatch",
            )
    if nested_handoff is not None:
        connect_command = [*launcher, "connect", "--profile", PROFILE]
        if manifest is not None:
            connect_command.extend(("--source-manifest", str(manifest)))
        if data_root is not None:
            connect_command.extend(("--data-root", str(data_root)))
        connect_command.append("--json")
        value = _invoke_launcher(
            connect_command,
            action="connection",
            allowed_statuses=frozenset({"reconnected"}),
        )
        value = {**value, **_live_runtime_identity(value)}
        from astrid.sdk.host_bootstrap import attach_pack_host

        try:
            attached = attach_pack_host(nested_handoff, value)
        except Exception as exc:
            raise AutoBootstrapError(
                f"nested runtime attachment was rejected: {exc}",
                code=str(getattr(exc, "code", "nested_attach_rejected")),
                details={"terminal": True},
            ) from exc
        result = dict(value)
        result.update(attached)
        return result
    base = [*launcher, "up", "--profile", PROFILE]
    if manifest is not None:
        base.extend(("--source-manifest", str(manifest)))
    if data_root is not None:
        base.extend(("--data-root", str(data_root)))
    with _ACQUISITION_LOCK, _acquisition_file_lock(Path(data_root)):
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
            from astrid.sdk.host_bootstrap import _readiness_profile_binding

            handoff = dict(value)
            operator_path_present = "ASTRID_HOST_READINESS_PROFILE_PATH" in os.environ
            operator_hash_present = "ASTRID_HOST_READINESS_PROFILE_HASH" in os.environ
            if operator_path_present != operator_hash_present:
                raise PackHostBootstrapError(
                    "operator readiness profile path and hash must be supplied together"
                )

            # Validate any launcher-provided selection before considering the
            # explicit operator selection. Never combine a partial binding.
            mapping_path, mapping_hash, _ = _readiness_profile_binding(handoff)
            if operator_path_present:
                operator_selection = {
                    "readiness_profile_path": os.environ[
                        "ASTRID_HOST_READINESS_PROFILE_PATH"
                    ],
                    "readiness_profile_hash": os.environ[
                        "ASTRID_HOST_READINESS_PROFILE_HASH"
                    ],
                }
                operator_path, operator_hash, _ = _readiness_profile_binding(
                    operator_selection
                )
                if mapping_path is not None and (
                    mapping_path != operator_path or mapping_hash != operator_hash
                ):
                    raise PackHostBootstrapError(
                        "operator readiness profile conflicts with launcher selection"
                    )
                handoff.update(
                    readiness_profile_path=operator_path,
                    readiness_profile_hash=operator_hash,
                )
            elif mapping_path is not None:
                handoff.update(
                    readiness_profile_path=mapping_path,
                    readiness_profile_hash=mapping_hash,
                )

            # Validate the exact copy that crosses the host boundary. The host
            # repeats validation before reuse/retirement and derives attestation.
            _readiness_profile_binding(handoff)
            result.update(ensure_pack_host(handoff, reconfigure_action=RECONFIGURE_ACTION))
        except PackHostBootstrapError as exc:
            raise AutoBootstrapError(str(exc)) from exc
    return result


__all__ = ["AutoBootstrapError", "ensure_runtime"]
