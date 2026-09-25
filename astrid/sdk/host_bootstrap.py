"""Process boundary for Astrid's one generic pack executor host.

The neutral runtime owns data and credentials.  This module only starts the
generic executor, waits for its registration/preflight readiness record, and
keeps a small support-directory marker so an Astrid relaunch reuses one host.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import signal
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping

from astrid.core.execution.process_group import _process_snapshot
from astrid.core.execution.host_lane_policy import (
    CANONICAL_PACK_HOST_MAX_CONCURRENCY,
    canonical_pack_host_capacity,
)
from astrid.core.generation.vibecomfy_dependency import (
    VibeComfyDependencyError,
    dependency_pythonpath,
)

PACK_HOST_ACTOR = "astrid-pack-host"
PACK_HOST_SCOPES = (
    "handshake",
    "worker:register",
    "worker:execute",
    "tasks:read",
    "objects:read",
    "objects:write",
)
PACK_HOST_PYTHON_ENV = "ASTRID_PACK_HOST_PYTHON"
# The canonical host has one coordination lane and one serial executor lane.
# Runtime's max_concurrency remains the admission ceiling; the named resource
# reservations published by GenericPackHost keep the lanes independent.
PACK_HOST_MAX_CONCURRENCY = CANONICAL_PACK_HOST_MAX_CONCURRENCY
NESTED_HANDOFF_PATH_ENV = "ASTRID_NESTED_RUNTIME_HANDOFF_PATH"
NESTED_HANDOFF_HASH_ENV = "ASTRID_NESTED_RUNTIME_HANDOFF_HASH"


def _canonical_capacity_matches(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    expected = canonical_pack_host_capacity()
    if any(value.get(key) != expected_value for key, expected_value in expected.items()):
        return False
    resource_keys = value.get("registered_resource_keys")
    return (
        isinstance(resource_keys, (list, tuple))
        and all(isinstance(key, str) for key in resource_keys)
        and {"astrid-orchestration", "cpu"}.issubset(resource_keys)
    )


def _capacity_readiness_matches(value: Mapping[str, Any] | None) -> bool:
    if not isinstance(value, Mapping):
        return False
    capacity = value.get("effective_capacity")
    registration = value.get("registration")
    return (
        _canonical_capacity_matches(capacity)
        and isinstance(registration, Mapping)
        and registration.get("effective_capacity") == capacity
    )


def _readiness_profile_ack_matches(
    value: Mapping[str, Any] | None,
    *,
    profile_path: str | None,
    profile_hash: str | None,
    attestation: Mapping[str, Any] | None,
) -> bool:
    """Require the child marker to acknowledge the selected semantic binding."""
    if not isinstance(value, Mapping):
        return False
    if (
        value.get("readiness_profile_path") != profile_path
        or value.get("readiness_profile_hash") != profile_hash
        or value.get("vibecomfy_execution_attestation") != attestation
    ):
        return False
    if profile_path is None:
        return True
    ready_capabilities = value.get("ready_capabilities")
    return isinstance(ready_capabilities, (list, tuple)) and "vibecomfy.run" in ready_capabilities


class PackHostBootstrapError(RuntimeError):
    """A bounded, secret-free failure while starting the generic host."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "pack_host_bootstrap_failed",
        request_id: str = "",
        terminal: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.terminal = terminal

def _pack_host_python_executable() -> str:
    """Return the selected pack-host interpreter without resolving venv links."""
    configured = os.environ.get(PACK_HOST_PYTHON_ENV, "").strip()
    if not configured:
        return os.path.abspath(sys.executable)

    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        raise PackHostBootstrapError(
            f"{PACK_HOST_PYTHON_ENV} must be an absolute path to an executable file"
        )
    try:
        executable = candidate.is_file() and os.access(candidate, os.X_OK)
    except (OSError, ValueError):
        executable = False
    if not executable:
        raise PackHostBootstrapError(
            f"{PACK_HOST_PYTHON_ENV} must be an absolute path to an executable file"
        )
    return os.path.abspath(str(candidate))

def _host_pid_alive(pid: Any) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    # A terminated process can remain as a zombie until its original parent
    # reaps it.  It is not a live host and must not block a fresh launch.  The
    # Linux /proc probe is not available on macOS, which is the primary local
    # deployment, so keep a portable ``ps`` fallback as well.  Without this,
    # a host killed alongside an interrupted CLI remains recorded forever and
    # every next launch attempts to terminate the zombie until it times out.
    try:
        stat = Path(f"/proc/{value}/stat").read_text(encoding="ascii")
        state = stat.rsplit(")", 1)[-1].lstrip().split(None, 1)[0]
        if state == "Z":
            return False
    except (OSError, UnicodeDecodeError, IndexError):
        try:
            # ``subprocess.run`` is deliberately avoided here: the bootstrap
            # tests (and some embedded launchers) replace ``Popen`` while
            # modelling host startup.  The PID is already parsed as an int,
            # so this small, read-only ps probe has no shell-input surface.
            with os.popen(f"/bin/ps -p {value} -o state=", "r") as probe:
                state_text = probe.read()
            state = state_text.strip().split(None, 1)[0] if state_text.strip() else ""
            if state.upper().startswith("Z"):
                return False
        except (OSError, ValueError, IndexError):
            pass
    return True


def _host_command(pid: Any) -> str:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return ""
    try:
        return Path(f"/proc/{value}/cmdline").read_bytes().decode("utf-8", "ignore").replace("\x00", " ")
    except (OSError, ValueError):
        try:
            probe = subprocess.run(
                ["ps", "-p", str(value), "-o", "command="],
                capture_output=True, text=True, check=False, timeout=1.0,
            )
            return probe.stdout.strip()
        except (OSError, subprocess.SubprocessError, ValueError):
            return ""


def _our_host(pid: Any) -> bool:
    return _host_pid_alive(pid) and "astrid.core.execution.generic_host" in _host_command(pid)


def _host_birth_identity(pid: Any) -> str:
    """Return the OS birth token for *pid*, or an empty value if unavailable."""
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    try:
        info = _process_snapshot().get(value)
    except Exception:
        info = None
    return str(info.birth) if info is not None else ""


def _host_identity_matches(state: Mapping[str, Any]) -> bool:
    """Verify PID, birth, process group, and every launch binding."""
    pid = state.get("pid")
    if not _host_pid_alive(pid):
        return False
    expected_birth = str(state.get("process_birth_id") or "")
    if not expected_birth or _host_birth_identity(pid) != expected_birth:
        return False
    if not _our_host(pid):
        return False
    try:
        if os.getpgid(int(pid)) != int(pid):
            return False
    except (OSError, TypeError, ValueError):
        return False
    command = _host_command(pid)
    required = [
        "astrid.core.execution.generic_host",
        str(state.get("ready_file") or ""),
        str(state.get("source_checkout") or ""),
        str(state.get("credential_file") or ""),
        str(state.get("support_root") or ""),
        str(state.get("endpoint") or ""),
        str(state.get("boot_manifest_path") or ""),
        str(state.get("boot_manifest_hash") or ""),
    ]
    readiness_path = state.get("readiness_profile_path")
    readiness_hash = state.get("readiness_profile_hash")
    if readiness_path or readiness_hash:
        if not readiness_path or not readiness_hash:
            return False
        required.extend((str(readiness_path), str(readiness_hash)))
    return all(value and value in command for value in required)


def _readiness_profile_binding(
    value: Mapping[str, Any],
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    """Validate the selected readiness profile before host reuse/retirement."""
    raw_path = value.get("readiness_profile_path")
    expected_hash = value.get("readiness_profile_hash")
    if (raw_path is None) != (expected_hash is None):
        raise PackHostBootstrapError(
            "readiness profile path and hash must be supplied together"
        )
    if raw_path is None:
        return None, None, None
    if not isinstance(raw_path, str) or not raw_path:
        raise PackHostBootstrapError("readiness profile path is invalid")
    path = Path(raw_path).expanduser()
    try:
        metadata = path.lstat()
        if not path.is_absolute() or not stat.S_ISREG(metadata.st_mode):
            raise OSError("readiness profile must be an absolute regular file")
        contents = path.read_bytes()
        actual_hash = "sha256:" + hashlib.sha256(contents).hexdigest()
        if not isinstance(expected_hash, str) or expected_hash != actual_hash:
            raise OSError("readiness profile hash does not match its bytes")
        profile = json.loads(contents.decode("utf-8"))
        if not isinstance(profile, Mapping):
            raise OSError("readiness profile must contain an object")
        from astrid.core.execution.generic_host import (
            _vibecomfy_execution_attestation,
        )

        attestation = _vibecomfy_execution_attestation(profile)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PackHostBootstrapError(f"readiness profile is invalid: {exc}") from exc
    except Exception as exc:
        raise PackHostBootstrapError(
            f"readiness profile attestation is invalid: {exc}"
        ) from exc
    return str(path), actual_hash, attestation


def _read_object(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def attach_pack_host(handoff: Mapping[str, Any], runtime: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read-only validation of the exact host incarnation issuing a nested attach."""
    required = (
        "support_root", "endpoint", "executor_id", "runtime_instance_id", "runtime_epoch",
        "schema_digest", "issuer_pid", "issuer_birth_id", "ready_file",
        "source_checkout", "source_checkout_digest", "source_inventory_identity",
        "boot_manifest_path", "boot_manifest_hash", "readiness_profile_path",
        "readiness_profile_hash", "vibecomfy_execution_attestation", "effective_capacity",
        "python_executable",
    )
    if handoff.get("schema_version") != 1 or any(key not in handoff for key in required):
        raise PackHostBootstrapError("nested runtime handoff is incomplete", code="nested_handoff_invalid", terminal=True)
    expected_instance = handoff.get("runtime_instance_id")
    expected_epoch = handoff.get("runtime_epoch")
    expected_schema = handoff.get("schema_digest")
    if (
        not isinstance(handoff.get("endpoint"), str)
        or not handoff["endpoint"].strip()
        or not isinstance(expected_instance, str)
        or not expected_instance.strip()
        or isinstance(expected_epoch, bool)
        or not isinstance(expected_epoch, int)
        or expected_epoch < 1
        or not isinstance(expected_schema, str)
        or not expected_schema.strip()
    ):
        raise PackHostBootstrapError(
            "nested runtime handoff identity is incomplete",
            code="nested_handoff_invalid",
            terminal=True,
        )
    support = Path(str(handoff["support_root"]))
    ready_path = Path(str(handoff["ready_file"]))
    state_path = support / "generic-host.json"
    try:
        if (not support.is_absolute() or support.is_symlink() or not support.is_dir()
                or ready_path.is_symlink() or state_path.is_symlink()
                or not stat.S_ISREG(ready_path.lstat().st_mode)
                or not stat.S_ISREG(state_path.lstat().st_mode)):
            raise OSError("host acknowledgement paths are unsafe")
    except OSError as exc:
        raise PackHostBootstrapError("nested runtime host acknowledgement is unsafe", code="nested_handoff_invalid", terminal=True) from exc
    state, ready = _read_object(state_path), _read_object(ready_path)
    if state is None or ready is None:
        raise PackHostBootstrapError("nested runtime handoff host acknowledgement is missing", code="nested_handoff_stale", terminal=True)
    issuer_pid = handoff.get("issuer_pid")
    issuer_birth = str(handoff.get("issuer_birth_id") or "")
    if (str(state.get("pid")) != str(issuer_pid)
            or str(state.get("process_birth_id") or "") != issuer_birth
            or not _host_identity_matches(state)
            or str(ready.get("pid")) != str(issuer_pid)
            or str(ready.get("process_birth_id") or "") != issuer_birth):
        raise PackHostBootstrapError("nested runtime handoff belongs to a different or dead host", code="nested_handoff_foreign", terminal=True)
    for key in required:
        if key in {"issuer_pid", "issuer_birth_id", "effective_capacity"}:
            continue
        state_key = "readiness_profile_path" if key == "readiness_profile_path" else key
        if state.get(state_key) != handoff.get(key) or ready.get(state_key) != handoff.get(key):
            raise PackHostBootstrapError(f"nested runtime handoff binding changed: {key}", code="nested_handoff_mismatch", terminal=True)
    if (ready.get("status") != "ready"
            or ready.get("effective_capacity") != handoff.get("effective_capacity")
            or state.get("effective_capacity") != handoff.get("effective_capacity")
            or not _capacity_readiness_matches(ready)
            or not _readiness_profile_ack_matches(
                ready,
                profile_path=handoff.get("readiness_profile_path"),
                profile_hash=handoff.get("readiness_profile_hash"),
                attestation=handoff.get("vibecomfy_execution_attestation"),
            )):
        raise PackHostBootstrapError("nested runtime handoff readiness or capacity acknowledgement changed", code="nested_handoff_mismatch", terminal=True)
    if handoff.get("readiness_profile_path") is None:
        ready_capabilities = ready.get("ready_capabilities")
        if not isinstance(ready_capabilities, (list, tuple)) or "vibecomfy.run" in ready_capabilities:
            raise PackHostBootstrapError("profile-free nested host advertises VibeComfy without readiness", code="nested_handoff_mismatch", terminal=True)
    for key in ("endpoint", "runtime_instance_id", "runtime_epoch", "schema_digest"):
        observed = runtime.get(key)
        if key == "runtime_epoch":
            valid = not isinstance(observed, bool) and isinstance(observed, int) and observed >= 1
        else:
            valid = isinstance(observed, str) and bool(observed.strip())
        if not valid:
            raise PackHostBootstrapError(
                f"nested runtime attachment identity is missing: {key}",
                code="nested_runtime_mismatch",
                terminal=True,
            )
        if observed != handoff.get(key):
            raise PackHostBootstrapError(f"nested runtime attachment identity changed: {key}", code="nested_runtime_mismatch", terminal=True)
    profile_path = handoff.get("readiness_profile_path")
    profile_hash = handoff.get("readiness_profile_hash")
    if (profile_path is None) != (profile_hash is None):
        raise PackHostBootstrapError("nested runtime handoff has a partial readiness selection", code="nested_handoff_invalid", terminal=True)
    if profile_path is not None:
        checked_path, checked_hash, attestation = _readiness_profile_binding({
            "readiness_profile_path": profile_path,
            "readiness_profile_hash": profile_hash,
        })
        if checked_path != profile_path or not hmac.compare_digest(str(checked_hash), str(profile_hash)) or attestation != handoff.get("vibecomfy_execution_attestation"):
            raise PackHostBootstrapError("nested runtime readiness attestation changed", code="nested_handoff_mismatch", terminal=True)
    elif handoff.get("vibecomfy_execution_attestation") is not None:
        raise PackHostBootstrapError("profile-free nested host has an unexpected attestation", code="nested_handoff_mismatch", terminal=True)
    try:
        from astrid.core.execution.generic_host import source_checkout_digest
        from astrid.core.pack.source_setup import active_source_inventory
        if os.path.abspath(sys.executable) != handoff["python_executable"]:
            raise ValueError("nested SDK interpreter does not match the host interpreter")
        source_path = Path(str(handoff["source_checkout"]))
        if (not source_path.is_absolute() or source_path.is_symlink() or not source_path.is_dir()
                or source_checkout_digest(source_path) != handoff["source_checkout_digest"]):
            raise ValueError("source checkout identity changed")
        inventory = active_source_inventory()
        observed_inventory = inventory.identity if inventory.sources else ""
        if observed_inventory != handoff["source_inventory_identity"]:
            raise ValueError("source inventory identity changed")
        boot_path = Path(str(handoff["boot_manifest_path"]))
        boot_meta = boot_path.lstat()
        if not boot_path.is_absolute() or not stat.S_ISREG(boot_meta.st_mode):
            raise ValueError("boot manifest is not a regular file")
        from astrid.core._shared.boot_manifest import (
            load_boot_manifest_hash,
            normalize_sha256_digest,
        )

        boot_hash = load_boot_manifest_hash(boot_path, support_root=support)
        if not hmac.compare_digest(
            normalize_sha256_digest(boot_hash, label="loaded boot manifest hash"),
            normalize_sha256_digest(
                handoff["boot_manifest_hash"], label="nested boot manifest hash"
            ),
        ):
            raise ValueError("boot manifest identity changed")
    except Exception as exc:
        raise PackHostBootstrapError("nested runtime source or boot identity changed", code="nested_handoff_mismatch", terminal=True) from exc
    return {
        "host_status": "ready",
        "host_pid": int(issuer_pid),
        "host_executor_id": PACK_HOST_ACTOR,
        "host_ready_file": str(ready_path),
        "host_ready_capabilities": list(ready.get("ready_capabilities", [])),
        "host_runtime_instance_id": handoff["runtime_instance_id"],
        "host_runtime_epoch": handoff["runtime_epoch"],
        "effective_capacity": dict(handoff["effective_capacity"]),
    }


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_text(json.dumps(dict(value), sort_keys=True), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _dependency_pythonpath() -> tuple[str, ...]:
    """Keep only approved dependency roots across the host boundary."""
    try:
        return dependency_pythonpath()
    except VibeComfyDependencyError as exc:
        raise PackHostBootstrapError(str(exc)) from exc


def _provision_render_runtime_env(
    source_path: Path, child_env: dict[str, str]
) -> None:
    """Bind a trusted local source profile to its concrete render toolchain.

    Packaged deployments may supply all three absolute settings themselves.
    For a source checkout, the launcher turns its installed Remotion bundle,
    schema package, and resolved Node executable into the same explicit
    settings before strict host preflight runs.
    """
    from astrid.core.env_vars import (
        ASTRID_NODE_EXECUTABLE,
        ASTRID_REMOTION_PROJECT_DIR,
        ASTRID_TIMELINE_SCHEMA_PYTHONPATH,
    )

    project_dir = (source_path / "remotion").resolve()
    if (
        ASTRID_REMOTION_PROJECT_DIR not in child_env
        and (project_dir / "package.json").is_file()
        and (project_dir / "node_modules").is_dir()
    ):
        child_env[ASTRID_REMOTION_PROJECT_DIR] = str(project_dir)

    schema_root = (
        project_dir
        / "node_modules"
        / "@banodoco"
        / "timeline-schema"
        / "python"
    )
    if (
        ASTRID_TIMELINE_SCHEMA_PYTHONPATH not in child_env
        and (schema_root / "banodoco_timeline_schema" / "__init__.py").is_file()
    ):
        child_env[ASTRID_TIMELINE_SCHEMA_PYTHONPATH] = str(schema_root.resolve())

    if ASTRID_NODE_EXECUTABLE not in child_env:
        node = shutil.which("node", path=child_env.get("PATH"))
        if node:
            child_env[ASTRID_NODE_EXECUTABLE] = str(Path(node).resolve())


def _descendant_snapshot(pid: int) -> dict[int, tuple[str, int]]:
    """Capture descendant birth/PGID pairs before stopping a host."""
    try:
        snapshot = _process_snapshot()
    except Exception:
        return {}
    descendants: dict[int, tuple[str, int]] = {}
    frontier = [pid]
    while frontier:
        parent = frontier.pop()
        for info in snapshot.values():
            if info.ppid == parent and info.pid not in descendants:
                descendants[info.pid] = (str(info.birth), int(info.pgid))
                frontier.append(info.pid)
    return descendants


def _terminate_descendants(members: Mapping[int, tuple[str, int]]) -> None:
    """Clean groups/children captured from the verified host, with birth checks."""
    if not members:
        return
    groups: dict[int, str] = {
        pgid: birth
        for pid, (birth, pgid) in members.items()
        if pid == pgid
    }
    for sig, seconds in ((signal.SIGTERM, 1.0), (signal.SIGKILL, 1.0)):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            snapshot = _process_snapshot()
            live = [
                (pid, birth)
                for pid, (birth, _pgid) in members.items()
                if (info := snapshot.get(pid)) is not None and info.birth == birth
            ]
            if not live:
                return
            # A child launched by GenericPackHost is a fresh session leader.
            # Kill its whole group only while that leader's birth token still
            # matches; otherwise fall back to exact individual members so a
            # reused PGID can never receive the signal.
            for pgid, birth in groups.items():
                leader = snapshot.get(pgid)
                if leader is not None and leader.birth == birth and leader.pgid == pgid:
                    try:
                        os.killpg(pgid, sig)
                    except OSError:
                        pass
            # Signal individual birth-verified processes whose group leader is
            # already gone, including late descendants observed by the group
            # signal above on the next census.
            for pid, _birth in live:
                info = snapshot.get(pid)
                if info is not None and info.pgid in groups:
                    leader = snapshot.get(info.pgid)
                    if leader is not None and leader.birth == groups[info.pgid]:
                        continue
                try:
                    os.kill(pid, sig)
                except OSError:
                    pass
            time.sleep(0.03)


def _terminate_old_host(state: Mapping[str, Any]) -> None:
    """TERM, bounded wait, then KILL one exact prior host and its children."""
    pid_value = state.get("pid")
    try:
        pid = int(pid_value)
    except (TypeError, ValueError):
        return
    if not _host_pid_alive(pid):
        return
    if not _host_identity_matches(state):
        raise PackHostBootstrapError(
            "existing generic Astrid host cannot be verified safely; remove its stale marker and retry"
        )
    members = _descendant_snapshot(pid)

    def signal_verified(sig: int) -> None:
        if not _host_pid_alive(pid):
            return
        if not _host_identity_matches(state):
            return
        try:
            if os.getpgid(pid) == pid and hasattr(os, "killpg"):
                os.killpg(pid, sig)
            else:
                os.kill(pid, sig)
        except OSError:
            pass

    signal_verified(signal.SIGTERM)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and _host_pid_alive(pid):
        time.sleep(0.05)
    if _host_pid_alive(pid):
        signal_verified(signal.SIGKILL)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and _host_pid_alive(pid):
            time.sleep(0.05)
    _terminate_descendants(members)
    if _host_pid_alive(pid):
        raise PackHostBootstrapError("prior generic Astrid host did not terminate")


def ensure_pack_host(value: Mapping[str, Any], *, reconfigure_action: str) -> Mapping[str, Any]:
    """Ensure the runtime-issued pack host is registered and preflight-ready."""
    worker_file = value.get("worker_credential_file")
    source_checkout = value.get("source_checkout")
    if not worker_file or not source_checkout:
        # Tiny fake launcher boundaries intentionally model only the runtime
        # handoff.  Real neutral-runtime results contain both fields.
        return {}
    from astrid.sdk.workspace_client import _safe_local_path

    try:
        worker_path = _safe_local_path(str(worker_file), field="worker credential")
        source_path = _safe_local_path(str(source_checkout), field="source checkout")
    except Exception as exc:
        raise PackHostBootstrapError(f"generic Astrid pack host handoff is unsafe; {reconfigure_action}") from exc
    if (not worker_path.is_file() or worker_path.is_symlink()
            or not source_path.is_dir() or source_path.is_symlink()
            or worker_path.stat().st_mode & 0o777 != 0o600):
        raise PackHostBootstrapError(f"generic Astrid pack host handoff is unavailable; {reconfigure_action}")
    host_python = _pack_host_python_executable()
    try:
        from astrid.core.pack.source_setup import active_source_inventory

        managed_inventory = active_source_inventory()
    except Exception as exc:
        raise PackHostBootstrapError(
            f"managed source inventory could not be verified; {reconfigure_action}"
        ) from exc
    inventory_identity = managed_inventory.identity if managed_inventory.sources else ""
    pack_root = source_path / "astrid" / "packs"
    if not pack_root.is_dir() or pack_root.is_symlink():
        raise PackHostBootstrapError(f"Astrid source checkout has no pack root; {reconfigure_action}")
    scopes = tuple(str(scope) for scope in (value.get("worker_scopes") or ()))
    if str(value.get("worker_actor")) != PACK_HOST_ACTOR or scopes != PACK_HOST_SCOPES:
        raise PackHostBootstrapError(f"runtime worker credential is not the least-privilege pack-host contract; {reconfigure_action}")
    readiness_profile_path, readiness_profile_hash, readiness_attestation = (
        _readiness_profile_binding(value)
    )

    # Bind the process to the exact source and runtime instance it registered
    # against.  The health read is intentionally performed with the worker
    # credential, never the owner credential or an ambient environment token.
    from astrid.core.execution.generic_host import RuntimeProtocolClient, source_checkout_digest

    try:
        source_digest = source_checkout_digest(source_path)
    except (OSError, ValueError) as exc:
        raise PackHostBootstrapError(
            f"generic Astrid pack source tree is not a safe checkout; {reconfigure_action}"
        ) from exc
    try:
        worker_token = worker_path.read_text(encoding="utf-8").strip()
        if not worker_token:
            raise ValueError("worker credential is empty")
        runtime_client = RuntimeProtocolClient(str(value["endpoint"]).rstrip("/"), worker_token)
        health = runtime_client.health()
    except Exception as exc:
        raise PackHostBootstrapError(
            f"generic Astrid pack host could not verify runtime identity; {reconfigure_action}"
        ) from exc
    finally:
        worker_token = ""
    health_value = dict(health) if isinstance(health, Mapping) else {
        "status": getattr(health, "status", None),
        "protocol": getattr(health, "protocol", None),
        "runtime_epoch": getattr(health, "runtime_epoch", None),
        "schema_digest": getattr(health, "schema_digest", None),
        "runtime_instance_id": getattr(health, "runtime_instance_id", None),
        "runtime_session_id": getattr(health, "runtime_session_id", None),
        "coordinator_epoch": getattr(health, "coordinator_epoch", None),
    }
    if str(health_value.get("status", "")) != "ok":
        raise PackHostBootstrapError(
            f"generic Astrid pack host runtime is not healthy; {reconfigure_action}",
            code="runtime_not_ready",
            terminal=True,
        )
    runtime_epoch = health_value.get("runtime_epoch")
    runtime_instance_id = health_value.get("runtime_instance_id")
    schema_digest = health_value.get("schema_digest")
    from astrid.sdk.workspace_client import PROTOCOL, SCHEMA_DIGEST

    if (
        health_value.get("protocol") != PROTOCOL
        or schema_digest != SCHEMA_DIGEST
        or isinstance(runtime_epoch, bool)
        or not isinstance(runtime_epoch, int)
        or runtime_epoch < 1
        or not isinstance(runtime_instance_id, str)
        or not runtime_instance_id.strip()
        or not isinstance(health_value.get("runtime_session_id"), str)
        or not health_value["runtime_session_id"].strip()
    ):
        raise PackHostBootstrapError(
            f"generic Astrid pack host runtime identity is incomplete; {reconfigure_action}"
        )
    for field, actual in (
        ("runtime_instance_id", runtime_instance_id),
        ("runtime_epoch", runtime_epoch),
        ("schema_digest", schema_digest),
    ):
        asserted = value.get(field)
        if asserted is not None and asserted != actual:
            raise PackHostBootstrapError(
                f"launcher {field} disagrees with live runtime health; {reconfigure_action}",
                code="runtime_identity_mismatch",
                terminal=True,
            )

    runtime_support = worker_path.parent.parent
    host_root = runtime_support / "astrid-host"
    boot_manifest_path = host_root / "boot-manifest.json"
    from astrid.core.gateway.dispatch import compose_profile_handoff
    try:
        boot_handoff = compose_profile_handoff(
            boot_manifest_path, support_root=runtime_support
        )
    except Exception as exc:
        raise PackHostBootstrapError(
            f"generic Astrid pack boot manifest could not be composed; {reconfigure_action}"
        ) from exc
    boot_manifest_hash = str(boot_handoff["sha256"])
    state_path = runtime_support / "generic-host.json"
    ready_path = runtime_support / "generic-host.ready.json"
    lock_path = runtime_support / "generic-host.lock"
    endpoint = str(value["endpoint"]).rstrip("/")
    try:
        lock_handle = lock_path.open("a+")
        os.fchmod(lock_handle.fileno(), 0o600)
    except OSError as exc:
        raise PackHostBootstrapError(f"generic Astrid pack host lock is unavailable; {reconfigure_action}") from exc
    try:
        try:
            import fcntl
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError) as exc:
            raise PackHostBootstrapError(f"generic Astrid pack host lock is unavailable; {reconfigure_action}") from exc
        current = _read_object(state_path)
        ready = _read_object(ready_path)
        expected = {
            # Preserve the venv executable path: resolving its symlink would
            # collapse different dependency environments to the base Python.
            "python_executable": host_python,
            "endpoint": endpoint,
            "executor_id": PACK_HOST_ACTOR,
            "ready_file": str(ready_path),
            "credential_file": str(worker_path),
            "support_root": str(runtime_support),
            "source_checkout": str(source_path),
            "source_checkout_digest": source_digest,
            "source_inventory_identity": inventory_identity,
            "runtime_instance_id": str(runtime_instance_id),
            "runtime_epoch": runtime_epoch,
            "schema_digest": schema_digest,
            "boot_manifest_path": str(boot_manifest_path),
            "boot_manifest_hash": boot_manifest_hash,
            "readiness_profile_path": readiness_profile_path,
            "readiness_profile_hash": readiness_profile_hash,
            "vibecomfy_execution_attestation": readiness_attestation,
        }
        if (current and ready
                and all(current.get(key) == expected_value for key, expected_value in expected.items())
                and _host_identity_matches(current)
                and str(ready.get("status")) == "ready"
                and all(ready.get(key) == expected_value for key, expected_value in expected.items())
                and _readiness_profile_ack_matches(
                    ready,
                    profile_path=readiness_profile_path,
                    profile_hash=readiness_profile_hash,
                    attestation=readiness_attestation,
                )
                and _canonical_capacity_matches(current.get("effective_capacity"))
                and _capacity_readiness_matches(ready)
                and current.get("effective_capacity") == ready.get("effective_capacity")
                and str(ready.get("pid")) == str(current.get("pid"))
                and str(ready.get("process_birth_id")) == str(current.get("process_birth_id"))):
            return {
                "host_status": "ready",
                "host_pid": int(current["pid"]),
                "host_executor_id": PACK_HOST_ACTOR,
                "host_ready_file": str(ready_path),
                "host_ready_capabilities": list(ready.get("ready_capabilities", [])),
                "host_runtime_instance_id": str(runtime_instance_id),
                "host_runtime_epoch": runtime_epoch,
                "host_source_checkout_digest": source_digest,
                "host_source_inventory_identity": inventory_identity,
                "host_boot_manifest_path": str(boot_manifest_path),
                "host_boot_manifest_hash": boot_manifest_hash,
                "host_readiness_profile_path": readiness_profile_path,
                "host_readiness_profile_hash": readiness_profile_hash,
                "effective_capacity": dict(ready["effective_capacity"]),
            }
        if current:
            # Reconfiguration is not cancellation. In particular, a status
            # command from another interpreter or after a documentation edit
            # must not terminate a render already owned by this host.
            if _host_identity_matches(current) and _descendant_snapshot(int(current["pid"])):
                raise PackHostBootstrapError(
                    "generic Astrid pack host is busy with active child processes; "
                    "reconfiguration is deferred until its work finishes"
                )
            _terminate_old_host(current)
        ready_path.unlink(missing_ok=True)
        log_path = runtime_support / "generic-host.log"
        matrix = source_path / "config" / "astrid-beta-capabilities.json"
        argv = [
            host_python,
            "-m", "astrid.core.execution.generic_host", "run",
            "--pack-root", str(pack_root),
            "--runtime-endpoint", endpoint,
            "--credential-file", str(worker_path),
            "--executor-id", PACK_HOST_ACTOR,
            "--max-concurrency", str(PACK_HOST_MAX_CONCURRENCY),
            "--ready-file", str(ready_path),
            "--support-root", str(runtime_support),
            "--source-checkout", str(source_path),
            "--source-checkout-digest", source_digest,
            "--runtime-instance-id", str(runtime_instance_id),
            "--register",
            "--source-inventory-identity", inventory_identity,
            "--boot-manifest-path", str(boot_manifest_path),
            "--boot-manifest-hash", boot_manifest_hash,
        ]
        if readiness_profile_path is not None:
            argv.extend((
                "--readiness-profile-path", readiness_profile_path,
                "--readiness-profile-hash", readiness_profile_hash or "",
            ))
        for managed_root in managed_inventory.roots:
            argv.extend(("--pack-root", str(managed_root)))
        if matrix.is_file():
            argv.extend(("--capability-matrix", str(matrix)))
        child_env = dict(os.environ)
        # The argv pair is the sole readiness authority for this child. Clear
        # inherited profile and derived candidate values before it parses argv.
        for name in (
            "ASTRID_HOST_READINESS_PROFILE_PATH",
            "ASTRID_HOST_READINESS_PROFILE_HASH",
            "ASTRID_VIBECOMFY_ATTESTED_REVISION",
            "ASTRID_VIBECOMFY_ATTESTED_CONTENT_DIGEST",
            "ASTRID_VIBECOMFY_MODELS_ROOT",
            "ASTRID_VIBECOMFY_CANDIDATE_KIND",
            "ASTRID_VIBECOMFY_CANDIDATE_REVISION",
            "ASTRID_VIBECOMFY_CANDIDATE_CONTENT_DIGEST",
        ):
            child_env.pop(name, None)
        # The selected source profile is the complete pack-discovery fence;
        # ambient pack roots/PYTHONPATH entries must not silently add another
        # checkout to this host.
        child_env.pop("ASTRID_PACKS_PATH", None)
        child_env["PYTHONPATH"] = os.pathsep.join(
            (str(source_path), *_dependency_pythonpath())
        )
        _provision_render_runtime_env(source_path, child_env)
        try:
            log = log_path.open("ab")
            process = subprocess.Popen(
                argv,
                cwd=str(source_path),
                env=child_env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                close_fds=True,
            )
        except OSError as exc:
            raise PackHostBootstrapError(f"generic Astrid pack host could not be started; {reconfigure_action}") from exc
        finally:
            try:
                log.close()
            except UnboundLocalError:
                pass
        process_state = {
            **expected,
            "version": 2,
            "pid": process.pid,
            "process_birth_id": _host_birth_identity(process.pid),
        }
        if not process_state["process_birth_id"]:
            _terminate_old_host(process_state)
            raise PackHostBootstrapError(f"generic Astrid pack host identity could not be captured; {reconfigure_action}")
        deadline = time.monotonic() + 20.0
        ready = None
        terminal_failure = None
        while time.monotonic() < deadline:
            ready = _read_object(ready_path)
            if ready and str(ready.get("status")) == "ready":
                break
            if (
                ready
                and str(ready.get("status")) == "failed"
                and ready.get("terminal") is True
                and str(ready.get("pid")) == str(process.pid)
                and str(ready.get("process_birth_id"))
                == str(process_state["process_birth_id"])
            ):
                terminal_failure = ready
                break
            if process.poll() is not None:
                break
            time.sleep(0.05)
        if terminal_failure is not None:
            _terminate_old_host(process_state)
            error = terminal_failure.get("error")
            diagnostic = error if isinstance(error, Mapping) else {}
            code = str(diagnostic.get("code") or "host_registration_failed")[:128]
            request_id = str(diagnostic.get("request_id") or "")[:128]
            message = str(
                diagnostic.get("message") or "generic Astrid pack host registration failed"
            )[:512]
            suffix = f" [request_id={request_id}]" if request_id else ""
            raise PackHostBootstrapError(
                message + suffix,
                code=code,
                request_id=request_id,
                terminal=True,
            )
        if (not ready or ready.get("status") != "ready"
                or str(ready.get("pid")) != str(process.pid)
                or str(ready.get("process_birth_id")) != str(process_state["process_birth_id"])
                or not all(ready.get(key) == expected_value for key, expected_value in expected.items())
                or not _readiness_profile_ack_matches(
                    ready,
                    profile_path=readiness_profile_path,
                    profile_hash=readiness_profile_hash,
                    attestation=readiness_attestation,
                )
                or not _capacity_readiness_matches(ready)
                or process.poll() is not None):
            _terminate_old_host(process_state)
            raise PackHostBootstrapError(f"generic Astrid pack host did not become ready; inspect {log_path}")
        effective_capacity = dict(ready["effective_capacity"])
        _write_object(
            state_path,
            {**process_state, "effective_capacity": effective_capacity},
        )
        return {
            "host_status": "ready",
            "host_pid": process.pid,
            "host_executor_id": PACK_HOST_ACTOR,
            "host_ready_file": str(ready_path),
            "host_ready_capabilities": list(ready.get("ready_capabilities", [])),
            "host_runtime_instance_id": str(runtime_instance_id),
            "host_runtime_epoch": runtime_epoch,
            "host_source_checkout_digest": source_digest,
            "host_source_inventory_identity": inventory_identity,
            "host_boot_manifest_path": str(boot_manifest_path),
            "host_boot_manifest_hash": boot_manifest_hash,
            "host_readiness_profile_path": readiness_profile_path,
            "host_readiness_profile_hash": readiness_profile_hash,
            "effective_capacity": effective_capacity,
        }
    finally:
        try:
            import fcntl
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        lock_handle.close()


__all__ = [
    "PACK_HOST_ACTOR",
    "PACK_HOST_SCOPES",
    "PACK_HOST_MAX_CONCURRENCY",
    "PackHostBootstrapError",
    "ensure_pack_host",
]
