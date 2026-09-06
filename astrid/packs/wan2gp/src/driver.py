"""Native Wan2GP driver — private spool + persistent session owner.

Owns the ``shared.api.init() → WanGPSession.submit_task() → GenerationResult``
seam for the Astrid wan2gp pack.  The native path remains one-shot: a fresh
``WanGPSession`` is created per attempt, its ``output_dir`` is a private
attempt-scoped spool, outputs are verified to stay inside that spool, and the
session is closed (model release) at the end.  This module also contains a
fixture-only persistent runner for CPU lifecycle tests; it never imports or
starts the native engine.

This module deliberately avoids Worker/GW imports and does not depend on any
runtime database.  Importing/initializing the real Wan2GP engine requires the
explicitly identified pinned Wan2GP checkout on ``sys.path`` with ``cwd`` inside that checkout
(``Wan2GP/shared/api.py`` does ``_pushd(runtime.root)`` + ``import wgp``).
When the checkout or heavy dependencies are absent, the driver surfaces a
structured, disclosure-carrying failure rather than raising an opaque import
error.
"""

import hashlib
import json
import os
import platform
import shutil
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .compiler import (
    WanExecutionIdentity,
    compile_from_inputs,
    runner_fingerprint,
    warmth_identity,
)

# Pinned by M0 source custody: banodoco/Wan2GP @ 181bb71a, reigh-sprint-3
WAN2GP_PIN_SHA = "181bb71a21008032e4771e11663f33e4489c4512"
WAN2GP_PIN_REF = "refs/remotes/origin/reigh-sprint-3"


# This is deliberately the only error text table in the driver.  Values are
# local constants; no native or foreign exception is allowed to choose either
# a code or a message.
_ERROR_MESSAGES = {
    "identity_incomplete": "Wan execution identity is incomplete.",
    "identity_mismatch": "Wan execution identity does not match owned evidence.",
    "owned_identity_unavailable": "Owned Wan execution identity is unavailable.",
    "model_identity_mismatch": "Wan model identity does not match settings.",
    "model_template_mismatch": "Wan model template does not match settings.",
    "unsupported_route": "Owned Wan route is unavailable.",
    "unsupported_engine_seam": "Owned Wan engine seam is unavailable.",
    "root_unavailable": "Owned Wan route is unavailable.",
    "interpreter_mismatch": "Wan interpreter identity does not match owned evidence.",
    "interpreter_unavailable": "Wan interpreter evidence is unavailable.",
    "engine_unavailable": "Wan engine is unavailable.",
    "engine_unsupported": "Wan engine does not support the required operation.",
    "engine_init_failed": "Wan engine initialization failed.",
    "engine_failed": "Wan execution failed.",
    "cancelled": "Wan operation was cancelled.",
    "cancel_failed": "Wan cancellation failed.",
    "release_failed": "Wan release failed.",
    "release_unsupported": "Wan release is unavailable.",
    "cleanup_failed": "Wan cleanup failed.",
    "output_custody_failed": "Wan output custody failed.",
    "transport_failed": "Wan transport failed.",
    "timeout": "Wan operation timed out.",
    "session_poisoned": "Wan session requires a successful cold reset.",
    "session_busy": "Wan session is busy.",
    "engine_not_alive": "Wan engine is not alive.",
    "stale_generation": "Wan invocation is stale.",
    "lifecycle_incomplete": "Wan job completed without a result.",
    "unknown_failure": "Wan operation failed.",
}


def _safe_call(function: Callable[[], Any]) -> tuple[bool, Any]:
    """Run one untrusted operation without retaining its exception."""
    try:
        return True, function()
    except Exception:
        return False, None


def _safe_attr(value: Any, name: str) -> tuple[bool, Any]:
    return _safe_call(lambda: getattr(value, name))


def _safe_error(code: str) -> str:
    return _ERROR_MESSAGES.get(code, _ERROR_MESSAGES["unknown_failure"])


def _driver_error(code: str) -> str:
    selected = code if code in _ERROR_MESSAGES else "unknown_failure"
    return f"{selected}: {_safe_error(selected)}"


class RunCancelled(RuntimeError):
    """Cooperative cancellation requested before a fake lifecycle step."""

    code = "cancelled"

    def __init__(self, _reason: str = "cancelled") -> None:
        super().__init__("Wan operation was cancelled.")


class CancellationToken:
    """Small thread-safe cancellation seam shared by real and fake runners."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False
        self._reason: str | None = None

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @property
    def reason(self) -> str | None:
        with self._lock:
            return self._reason

    def cancel(self, reason: str = "cancelled") -> bool:
        """Request cancellation, returning ``True`` only on the first request."""
        with self._lock:
            if self._cancelled:
                return False
            self._cancelled = True
            self._reason = "cancelled"
            return True

    def raise_if_cancelled(self) -> None:
        reason = self.reason
        if reason is not None:
            raise RunCancelled(reason)


@dataclass(frozen=True)
class CancellationPolicy:
    """Deterministic fake-work cancellation policy.

    ``cancel_after_steps=0`` cancels before the first unit of fake work.
    ``None`` disables policy cancellation; an explicit token can still cancel.
    """

    cancel_after_steps: int | None = None

    def __post_init__(self) -> None:
        if self.cancel_after_steps is not None and self.cancel_after_steps < 0:
            raise ValueError("cancel_after_steps must be non-negative")

    def should_cancel(self, step: int) -> bool:
        return (
            self.cancel_after_steps is not None
            and step >= self.cancel_after_steps
        )

    def apply(self, token: CancellationToken, step: int) -> None:
        if self.should_cancel(step):
            token.cancel(f"cancelled by policy at step {step}")


@dataclass(frozen=True)
class RunnerSnapshot:
    runner_id: str
    status: str
    fingerprint: str | None
    warmth_identity: str | None
    event_seq: int
    total_runs: int
    successful_runs: int
    cancelled_runs: int
    failed_runs: int
    last_event: str | None
    last_error: str | None


class PersistentRunnerState:
    """Append-only, deterministic JSONL state for the fake persistent runner."""

    SCHEMA_VERSION = 1
    COLD = "cold"
    WARM = "warm"
    CLOSED = "closed"

    def __init__(self, path: str | os.PathLike[str], runner_id: str = "wan2gp-fake") -> None:
        self.path = Path(path).expanduser().resolve()
        self.runner_id = str(runner_id)
        if not self.runner_id:
            raise ValueError("runner_id is required")

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "PersistentRunnerState":
        """Reopen an existing journal, deriving its runner id from its header."""
        resolved = Path(path).expanduser().resolve()
        if not resolved.is_file():
            raise ValueError(f"runner state is empty: {resolved}")
        try:
            first = next(
                line for line in resolved.read_text(encoding="utf-8").splitlines() if line.strip()
            )
            header = json.loads(first)
            runner_id = header["runner_id"]
        except (OSError, StopIteration, KeyError, json.JSONDecodeError):
            raise ValueError(_safe_error("unknown_failure"))
        state = cls(resolved, runner_id=str(runner_id))
        if not state._events():
            raise ValueError(f"runner state is empty: {state.path}")
        return state

    def _events(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            for line_number, line in enumerate(lines, start=1):
                if not line.strip():
                    continue
                event = json.loads(line)
                if (
                    not isinstance(event, dict)
                    or event.get("schema_version") != self.SCHEMA_VERSION
                    or event.get("runner_id") != self.runner_id
                    or not isinstance(event.get("seq"), int)
                    or not isinstance(event.get("event"), str)
                ):
                    raise ValueError(f"invalid runner state record at line {line_number}")
                if event["seq"] != len(events) + 1:
                    raise ValueError(f"non-contiguous runner state at line {line_number}")
                events.append(event)
        except (OSError, json.JSONDecodeError):
            raise ValueError(_safe_error("unknown_failure"))
        return events

    def _append(self, event: str, **payload: Any) -> None:
        events = self._events()
        if events and events[0]["runner_id"] != self.runner_id:
            raise ValueError("runner state belongs to another runner")
        record = {
            "event": event,
            "runner_id": self.runner_id,
            "schema_version": self.SCHEMA_VERSION,
            "seq": len(events) + 1,
            **payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _ensure_created(self) -> None:
        if not self._events():
            self._append("runner_created")

    @property
    def snapshot(self) -> RunnerSnapshot:
        events = self._events()
        status = self.COLD
        fingerprint = None
        warmth = None
        total = successful = cancelled = failed = 0
        last_event = last_error = None
        for event in events:
            kind = event["event"]
            last_event = kind
            if kind in {"runner_started", "runner_reused", "runner_reconfigured"}:
                status = self.WARM
                fingerprint = event.get("fingerprint", fingerprint)
                warmth = event.get("warmth_identity", warmth)
            elif kind == "runner_closed":
                status = self.CLOSED
            elif kind == "run_started":
                total += 1
                fingerprint = event.get("fingerprint", fingerprint)
                warmth = event.get("warmth_identity", warmth)
            elif kind == "run_succeeded":
                successful += 1
            elif kind == "run_cancelled":
                cancelled += 1
                last_error = _safe_error("cancelled")
            elif kind == "run_failed":
                failed += 1
                last_error = _safe_error("engine_failed")
        return RunnerSnapshot(
            runner_id=self.runner_id,
            status=status,
            fingerprint=fingerprint,
            warmth_identity=warmth,
            event_seq=len(events),
            total_runs=total,
            successful_runs=successful,
            cancelled_runs=cancelled,
            failed_runs=failed,
            last_event=last_event,
            last_error=last_error,
        )

    def start(self, fingerprint: str, warmth_identity_value: str) -> RunnerSnapshot:
        self._ensure_created()
        current = self.snapshot
        payload = {
            "fingerprint": str(fingerprint),
            "warmth_identity": str(warmth_identity_value),
        }
        if current.status == self.WARM and current.fingerprint == fingerprint:
            self._append("runner_reused", **payload)
        else:
            self._append(
                "runner_reconfigured" if current.status == self.WARM else "runner_started",
                **payload,
            )
        return self.snapshot

    def begin_run(self, fingerprint: str, warmth_identity_value: str) -> None:
        if self.snapshot.status != self.WARM:
            raise RuntimeError("runner is not warm")
        self._append(
            "run_started",
            fingerprint=str(fingerprint),
            warmth_identity=str(warmth_identity_value),
        )

    def finish_run(self, status: str, *, reason: str | None = None) -> None:
        if status not in {"succeeded", "cancelled", "failed"}:
            raise ValueError("run status must be succeeded, cancelled, or failed")
        payload = {
            "reason": _safe_error("cancelled" if status == "cancelled" else "engine_failed")
        } if reason is not None else {}
        self._append(f"run_{status}", **payload)

    def close(self) -> RunnerSnapshot:
        self._ensure_created()
        if self.snapshot.status != self.CLOSED:
            self._append("runner_closed")
        return self.snapshot

    def liveness_probe(self) -> dict[str, Any]:
        snapshot = self.snapshot
        alive = self.path.is_file() and snapshot.status == self.WARM
        return {
            "alive": alive,
            "event_seq": snapshot.event_seq,
            "fingerprint": snapshot.fingerprint,
            "runner_id": snapshot.runner_id,
            "status": snapshot.status,
            "warmth_identity": snapshot.warmth_identity,
        }

    def is_alive(self) -> bool:
        return bool(self.liveness_probe()["alive"])


@dataclass(frozen=True)
class FakeRunResult:
    status: str
    generated_files: list[str]
    errors: list[str]
    fingerprint: str
    warmth_identity: str
    runner_alive: bool
    containment_ok: bool
    cancelled: bool
    state: RunnerSnapshot


class FakePersistentRunner:
    """Fixture-only persistent runner; never imports or starts Wan2GP."""

    RUNNER_KIND = "wan2gp-cpu-fake"

    def __init__(
        self,
        state_path: str | os.PathLike[str],
        *,
        output_root: str | os.PathLike[str] | None = None,
        runner_id: str = "wan2gp-fake",
        warmth_profile: str = "cpu-fake",
    ) -> None:
        self.state = PersistentRunnerState(state_path, runner_id)
        self.output_root = (
            Path(output_root).expanduser().resolve()
            if output_root is not None
            else self.state.path.parent / "outputs"
        )
        self.warmth_profile = str(warmth_profile)

    def liveness_probe(self) -> dict[str, Any]:
        return self.state.liveness_probe()

    def is_alive(self) -> bool:
        return self.state.is_alive()

    def run(
        self,
        settings: dict[str, Any],
        *,
        token: CancellationToken | None = None,
        policy: CancellationPolicy | None = None,
        work_steps: int = 1,
        output_name: str = "fake-output.json",
        escape_output: bool = False,
        fixture: dict[str, Any] | None = None,
    ) -> FakeRunResult:
        if work_steps < 0:
            raise ValueError("work_steps must be non-negative")
        token = token or CancellationToken()
        policy = policy or CancellationPolicy()
        fingerprint = runner_fingerprint(
            settings,
            runner_kind=self.RUNNER_KIND,
            engine_identity=f"wan2gp@{WAN2GP_PIN_SHA}",
        )
        warm_id = warmth_identity(
            settings,
            runner_kind=self.RUNNER_KIND,
            warmth_profile=self.warmth_profile,
            engine_identity=f"wan2gp@{WAN2GP_PIN_SHA}",
        )
        self.state.start(fingerprint, warm_id)
        self.state.begin_run(fingerprint, warm_id)
        try:
            for step in range(work_steps):
                policy.apply(token, step)
                token.raise_if_cancelled()
            policy.apply(token, work_steps)
            token.raise_if_cancelled()
            spool = self.output_root.expanduser().resolve()
            spool.mkdir(parents=True, exist_ok=True)
            candidate = (
                spool.parent / "escaped-fake-output.json"
                if escape_output
                else spool / output_name
            )
            if not _verify_within_spool(candidate, spool):
                error = _safe_error("output_custody_failed")
                self.state.finish_run("failed", reason=error)
                return FakeRunResult(
                    status="failed",
                    generated_files=[],
                    errors=[error],
                    fingerprint=fingerprint,
                    warmth_identity=warm_id,
                    runner_alive=self.state.is_alive(),
                    containment_ok=False,
                    cancelled=False,
                    state=self.state.snapshot,
                )
            payload = fixture if fixture is not None else {
                "fixture": "wan2gp-cpu-fake",
                "fingerprint": fingerprint,
                "settings": settings,
            }
            candidate.write_text(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            self.state.finish_run("succeeded")
            return FakeRunResult(
                status="succeeded",
                generated_files=[str(candidate)],
                errors=[],
                fingerprint=fingerprint,
                warmth_identity=warm_id,
                runner_alive=self.state.is_alive(),
                containment_ok=True,
                cancelled=False,
                state=self.state.snapshot,
            )
        except RunCancelled as exc:
            self.state.finish_run("cancelled", reason="cancelled")
            return FakeRunResult(
                status="cancelled",
                generated_files=[],
                errors=["Wan operation was cancelled."],
                fingerprint=fingerprint,
                warmth_identity=warm_id,
                runner_alive=self.state.is_alive(),
                containment_ok=True,
                cancelled=True,
                state=self.state.snapshot,
            )

    def close(self) -> RunnerSnapshot:
        return self.state.close()


class WanLifecycleError(RuntimeError):
    """Typed failure for the persistent Wan lifecycle boundary."""

    def __init__(
        self,
        code: str,
        _message: str | None = None,
        *,
        fence_required: bool = False,
    ) -> None:
        selected = code if isinstance(code, str) and code in _ERROR_MESSAGES else "unknown_failure"
        super().__init__(_safe_error(selected))
        self.code = selected
        self.fence_required = bool(fence_required)


@dataclass(frozen=True, slots=True)
class PersistentWanResult:
    """Stable terminal result returned by the persistent Wan driver."""

    status: str
    generated_files: tuple[str, ...]
    errors: tuple[str, ...]
    invocation_id: str
    session_generation: int
    warmth_identity: str
    identity_digest: str
    outputs: tuple[dict[str, Any], ...] = ()
    cancelled: bool = False
    poisoned: bool = False
    fence_pending: bool = False

    @property
    def success(self) -> bool:
        return self.status == "succeeded"

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "success": self.success,
            "generated_files": list(self.generated_files),
            "errors": list(self.errors),
            "invocation_id": self.invocation_id,
            "session_generation": self.session_generation,
            "warmth_identity": self.warmth_identity,
            "identity_digest": self.identity_digest,
            "outputs": [dict(item) for item in self.outputs],
            "cancelled": self.cancelled,
            "poisoned": self.poisoned,
            "fence_pending": self.fence_pending,
        }


class PersistentWanJob:
    """Joinable, cancellation-aware wrapper around one native session job."""

    def __init__(self, session: "PersistentWanSession", record: dict[str, Any]) -> None:
        self._session = session
        self._record = record

    def cancel(self) -> bool:
        return self._session._request_cancel(self._record)

    def result(self, timeout: float | None = None) -> PersistentWanResult:
        if not self._record["done"].wait(timeout):
            raise TimeoutError("persistent Wan session job timed out")
        result = self._record.get("result")
        if not isinstance(result, PersistentWanResult):
            raise WanLifecycleError("lifecycle_incomplete", "persistent Wan job completed without a result")
        return result

    join = result

    @property
    def done(self) -> bool:
        return self._record["done"].is_set()

    @property
    def thread(self) -> threading.Thread | None:
        return self._record.get("thread")


def _hash_regular_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_owned_identity_evidence(_settings: dict[str, Any]) -> dict[str, Any] | None:
    """Read independently owned native evidence.

    The current three-file seam has no Runtime/Worker-issued ownership
    evidence.  It therefore fails closed.  CPU tests replace this private
    reader with a harness-owned reader that observes real temporary files and
    bindings; no public argument can enable that fixture path.
    """
    return None


def _path_from_evidence(value: Any) -> Path | None:
    if not isinstance(value, (str, os.PathLike)):
        return None
    try:
        path = Path(value)
        if not path.is_absolute() or path.is_symlink():
            return None
        resolved = path.resolve(strict=False)
    except Exception:
        return None
    return resolved if str(resolved) == str(path) else None


def _regular_file_digest(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return _hash_regular_file(path)
    except Exception:
        return None


def _derive_owned_identity(
    settings: dict[str, Any], claimed: WanExecutionIdentity | None
) -> tuple[str, WanExecutionIdentity | None]:
    """Derive a complete identity from the private owned-evidence reader."""
    ok, evidence = _safe_call(lambda: _read_owned_identity_evidence(settings))
    if not ok or not isinstance(evidence, dict):
        return "owned_identity_unavailable", None

    root = _path_from_evidence(evidence.get("root"))
    interpreter = _path_from_evidence(evidence.get("interpreter"))
    model_file = _path_from_evidence(evidence.get("model_file"))
    template_file = _path_from_evidence(evidence.get("template_file"))
    engine_pin_file = _path_from_evidence(evidence.get("engine_pin_file"))
    if None in (root, interpreter, model_file, template_file, engine_pin_file):
        return "owned_identity_unavailable", None

    assert root is not None
    assert interpreter is not None
    assert model_file is not None
    assert template_file is not None
    assert engine_pin_file is not None

    try:
        api_file = root / "shared" / "api.py"
        if (
            not root.is_dir()
            or root.is_symlink()
            or api_file.is_symlink()
            or not api_file.is_file()
            or api_file.resolve(strict=False).relative_to(root) != Path("shared/api.py")
        ):
            return "owned_identity_unavailable", None
        if model_file.resolve(strict=False).relative_to(root) != model_file.relative_to(root):
            return "owned_identity_unavailable", None
        if template_file.resolve(strict=False).relative_to(root) != template_file.relative_to(root):
            return "owned_identity_unavailable", None
        if interpreter != Path(sys.executable).resolve(strict=False):
            return "identity_mismatch", None
    except (OSError, ValueError):
        return "owned_identity_unavailable", None

    model_digest = _regular_file_digest(model_file)
    pin_digest = _regular_file_digest(engine_pin_file)
    template_digest = _regular_file_digest(template_file)
    if model_digest is None or pin_digest is None or template_digest is None:
        return "owned_identity_unavailable", None
    ok, pin_text = _safe_call(lambda: engine_pin_file.read_text(encoding="utf-8"))
    if not ok or not isinstance(pin_text, str) or pin_text.strip() != WAN2GP_PIN_SHA:
        return "identity_mismatch", None
    ok, template_text = _safe_call(lambda: template_file.read_text(encoding="utf-8"))
    if not ok or not isinstance(template_text, str):
        return "owned_identity_unavailable", None
    expected_template = str(settings.get("model_type", "")).strip()
    expected_model = str(settings.get("model", "")).strip()
    if not expected_model or not expected_template:
        return "identity_incomplete", None
    if template_text.strip() != expected_template or model_file.name != expected_model:
        return "identity_mismatch", None
    active_interpreter_digest = _regular_file_digest(interpreter)
    if active_interpreter_digest is None:
        return "owned_identity_unavailable", None
    observed_version = platform.python_version()
    observed_facts = {
        "interpreter_version": observed_version,
        "interpreter_sha256": active_interpreter_digest,
        "model": expected_model,
        "model_template": expected_template,
        "model_bytes_digest": model_digest,
        "template_bytes_digest": template_digest,
        "engine_pin_digest": pin_digest,
    }
    if any(
        not isinstance(evidence.get(key), str) or evidence[key] != value
        for key, value in observed_facts.items()
    ):
        return "identity_mismatch", None

    # These values are emitted only by the private owner reader.  Requiring
    # explicit strings avoids filling missing owner facts with defaults.
    required = (
        "runtime_identity",
        "transport_identity",
        "process_identity",
        "route",
        "engine_seam",
    )
    if any(not isinstance(evidence.get(key), str) or not evidence[key].strip() for key in required):
        return "owned_identity_unavailable", None
    if evidence.get("engine_identity") != f"wan2gp@{WAN2GP_PIN_SHA}":
        return "identity_mismatch", None

    try:
        expected = WanExecutionIdentity.from_facts(
            interpreter=str(interpreter),
            interpreter_version=observed_version,
            interpreter_sha256=active_interpreter_digest,
            model=expected_model,
            model_template=expected_template,
            model_bytes_digest=model_digest,
            root=str(root),
            runtime_identity=evidence["runtime_identity"],
            transport_identity=evidence["transport_identity"],
            process_identity=evidence["process_identity"],
            engine_identity=evidence["engine_identity"],
            route=evidence["route"],
            engine_seam=evidence["engine_seam"],
        )
    except (TypeError, ValueError, OSError):
        return "owned_identity_unavailable", None
    if expected.route != "wan2gp.generate_video" or expected.engine_seam != "shared.api.init/WanGPSession.submit_task":
        return "identity_mismatch", None
    if claimed is not None and claimed.to_dict() != expected.to_dict():
        return "identity_mismatch", None
    return "ok", expected


def _native_wan_session_factory(
    identity: WanExecutionIdentity, output_dir: Path
) -> Any:
    """Load only the explicitly identified native Wan2GP checkout.

    No environment variable, PATH lookup, model download, route selector, or
    alternate engine import is consulted here.  The identity was validated
    before this function is called; these checks protect the side-effecting
    import/init boundary as well.
    """
    root = Path(identity.root)
    if identity.route != "wan2gp.generate_video":
        raise WanLifecycleError("unsupported_route")
    if identity.engine_seam != "shared.api.init/WanGPSession.submit_task":
        raise WanLifecycleError("unsupported_engine_seam")
    if not root.is_dir() or not (root / "shared" / "api.py").is_file():
        raise WanLifecycleError("root_unavailable")
    executable = Path(identity.interpreter)
    if executable.resolve(strict=False) != Path(sys.executable).resolve(strict=False):
        raise WanLifecycleError("interpreter_mismatch")
    if _regular_file_digest(executable) != identity.interpreter_sha256:
        raise WanLifecycleError("interpreter_mismatch")

    original_path = list(sys.path)
    original_cwd = Path.cwd()
    engine: Any | None = None
    engine_closed = False
    primary_code: str | None = None
    restoration_ok = True
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        ok, _ = _safe_call(lambda: os.chdir(root))
        if not ok:
            primary_code = "root_unavailable"
        else:
            import importlib

            ok, api = _safe_call(lambda: importlib.import_module("shared.api"))
            if not ok:
                primary_code = "engine_init_failed"
            else:
                ok, api_file = _safe_attr(api, "__file__")
                api_path = _path_from_evidence(api_file) if ok else None
                if api_path != (root / "shared" / "api.py").resolve(strict=False):
                    primary_code = "engine_init_failed"
                else:
                    ok, init_fn = _safe_attr(api, "init")
                    if not ok or not callable(init_fn):
                        primary_code = "engine_unavailable"
                    else:
                        ok, engine = _safe_call(
                            lambda: init_fn(
                                root=root,
                                output_dir=output_dir,
                                console_output=False,
                            )
                        )
                        if not ok:
                            primary_code = "engine_init_failed"
    except Exception:
        primary_code = "engine_init_failed"
    finally:
        sys.path[:] = original_path
        restoration_ok = _safe_call(lambda: os.chdir(original_cwd))[0]
        if not restoration_ok and engine is not None and not engine_closed:
            ok, close = _safe_attr(engine, "close")
            if ok and callable(close):
                _safe_call(lambda: close())
            engine_closed = True

    if not restoration_ok:
        if primary_code is None:
            primary_code = "cleanup_failed"
        raise WanLifecycleError(
            primary_code,
            fence_required=True,
        )
    if primary_code is not None:
        raise WanLifecycleError(primary_code)
    if engine is None:
        raise WanLifecycleError("engine_unavailable")
    return engine


class PersistentWanSession:
    """Serialized persistent owner of one native ``WanGPSession``.

    The session latches an exact :class:`WanExecutionIdentity` and warmth key
    before calling the native factory.  A task can reuse the engine only when
    the complete identity and settings-derived warmth key are equal.  Native
    or custody failures poison the owner; only a successful cold reset can
    clear that fence.
    """

    def __init__(
        self,
        *,
        output_root: str | os.PathLike[str],
        engine_factory: Callable[[WanExecutionIdentity, Path], Any] | None = None,
        warmth_profile: str = "default",
    ) -> None:
        root = Path(output_root).expanduser()
        if not root.is_absolute():
            raise ValueError("persistent Wan output_root must be explicit and absolute")
        if str(root) != str(root.resolve(strict=False)):
            raise ValueError("persistent Wan output_root must be canonical")
        if not isinstance(warmth_profile, str) or not warmth_profile.strip():
            raise ValueError("warmth_profile is required")
        self.output_root = root.resolve(strict=False)
        self._engine_factory = engine_factory or _native_wan_session_factory
        self.warmth_profile = warmth_profile.strip()
        self._lock = threading.RLock()
        self._engine: Any | None = None
        self._latched_identity: WanExecutionIdentity | None = None
        self._latched_warmth: str | None = None
        self._session_generation = 0
        self._preparing = False
        self._active: dict[str, Any] | None = None
        self._poisoned = False
        self._fence_pending = False
        self._cleanup_fence = False
        self._last_error: str | None = None
        self.last_lifecycle = "cold"
        self.last_warm_reused = False

    @property
    def warm(self) -> bool:
        with self._lock:
            return self._engine is not None and not self._poisoned and not self._fence_pending

    @property
    def poisoned(self) -> bool:
        with self._lock:
            return self._poisoned

    @property
    def fence_pending(self) -> bool:
        with self._lock:
            return self._fence_pending

    @property
    def session_generation(self) -> int:
        with self._lock:
            return self._session_generation

    @property
    def identity(self) -> WanExecutionIdentity | None:
        with self._lock:
            return self._latched_identity

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            active = self._active
            return {
                "lifecycle": "warm" if self.warm else "cold",
                "warm": self.warm,
                "poisoned": self._poisoned,
                "fence_pending": self._fence_pending,
                "session_generation": self._session_generation,
                "identity_digest": self._latched_identity.digest if self._latched_identity else None,
                "warmth_identity": self._latched_warmth,
                "active_invocation": active["invocation_id"] if active else None,
                "active_phase": active["phase"] if active else None,
                "last_error": self._last_error,
            }

    @staticmethod
    def _settings_identity(settings: dict[str, Any]) -> tuple[str, str]:
        compiled = compile_from_inputs(settings)
        model = str(compiled.get("model", "")).strip()
        template = str(compiled.get("model_type", "")).strip()
        if not model or not template:
            raise ValueError("Wan settings must contain model and model template")
        return model, template

    @staticmethod
    def _coerce_identity(identity: WanExecutionIdentity) -> WanExecutionIdentity:
        if not isinstance(identity, WanExecutionIdentity):
            raise WanLifecycleError("identity_incomplete")
        return identity

    def _validate_admission(
        self, settings: dict[str, Any], identity: WanExecutionIdentity
    ) -> tuple[dict[str, Any], str, WanExecutionIdentity]:
        if not isinstance(settings, dict):
            raise ValueError("Wan settings must be a dict")
        compiled = compile_from_inputs(settings)
        validate_settings(compiled)
        model, template = self._settings_identity(compiled)
        if model != identity.model:
            raise WanLifecycleError("model_identity_mismatch", "Wan model identity does not match settings")
        if template != identity.model_template:
            raise WanLifecycleError("model_template_mismatch", "Wan model template does not match settings")
        outcome, expected = _derive_owned_identity(compiled, identity)
        if outcome != "ok" or expected is None:
            raise WanLifecycleError(outcome)
        warmth = expected.warmth_key(compiled, self.warmth_profile)
        if identity.digest != expected.digest or identity.warmth_key(compiled, self.warmth_profile) != warmth:
            raise WanLifecycleError("identity_mismatch")
        return compiled, warmth, expected

    @staticmethod
    def _engine_alive(engine: Any) -> bool:
        ok, probe = _safe_attr(engine, "is_alive")
        if ok and callable(probe):
            ok, alive = _safe_call(lambda: bool(probe()))
            return bool(ok and alive)
        ok, closed = _safe_attr(engine, "closed")
        if ok and closed is True:
            return False
        return bool(ok)

    def _poison(self, reason: str, *, fence: bool = True) -> None:
        self._poisoned = True
        self._fence_pending = fence
        self._last_error = _safe_error(reason if reason in _ERROR_MESSAGES else "unknown_failure")
        self.last_lifecycle = "cold"
        self.last_warm_reused = False

    def _close_engine_locked(self) -> None:
        engine = self._engine
        if engine is None:
            return
        ok, close = _safe_attr(engine, "close")
        if not ok or not callable(close):
            raise WanLifecycleError("release_unsupported")
        if not _safe_call(lambda: close())[0]:
            raise WanLifecycleError("release_failed")

    def _prepare(
        self,
        settings: dict[str, Any],
        identity: WanExecutionIdentity,
        token: CancellationToken | None = None,
        active_record: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str, int, Path]:
        compiled, warmth, expected = self._validate_admission(settings, identity)
        release_failure_code: str | None = None
        with self._lock:
            if self._poisoned or self._fence_pending:
                raise WanLifecycleError("session_poisoned", "persistent Wan session requires cold reset")
            if self._active is not None and self._active is not active_record:
                raise WanLifecycleError("session_busy", "persistent Wan session is already executing")
            if self._preparing:
                raise WanLifecycleError("session_busy", "persistent Wan session is already preparing")
            if token is not None:
                token.raise_if_cancelled()
            same = (
                self._engine is not None
                and self._latched_identity == identity
                and self._latched_warmth == warmth
                and self._engine_alive(self._engine)
            )
            self.last_warm_reused = same
            if same:
                self.last_lifecycle = "warm"
                return compiled, warmth, self._session_generation, self.output_root / f"generation-{self._session_generation}"
            if self._engine is not None:
                try:
                    self._close_engine_locked()
                except Exception:
                    self._poison("release_failed")
                    release_failure_code = "release_failed"
                if release_failure_code is not None:
                    raise WanLifecycleError(release_failure_code)
                self._engine = None
                self._latched_identity = None
                self._latched_warmth = None
            if token is not None:
                token.raise_if_cancelled()
            self.output_root.mkdir(parents=True, exist_ok=True)
            self._session_generation += 1
            spool = self.output_root / f"generation-{self._session_generation}"
            spool.mkdir(parents=True, exist_ok=False)
            if active_record is not None:
                active_record["session_generation"] = self._session_generation
            self._preparing = True

        # Engine import/initialization may block.  Do not hold the lifecycle
        # lock across that side effect: cancel() must be able to fence the
        # reserved generation while preparation is in flight.
        engine: Any | None = None
        engine_closed = False
        cancellation_after_factory = False
        failure_code: str | None = None
        factory_fence = False
        try:
            engine = self._engine_factory(expected, spool)
        except WanLifecycleError as exc:
            failure_code = exc.code
            factory_fence = bool(getattr(exc, "fence_required", False))
        except Exception:
            failure_code = "engine_init_failed"
        if failure_code is not None:
            with self._lock:
                self._poison(failure_code)
                if factory_fence:
                    self._cleanup_fence = True
                self._preparing = False
            raise WanLifecycleError(failure_code)
        try:
            if engine is None:
                raise WanLifecycleError("engine_unavailable")
            if token is not None:
                token.raise_if_cancelled()
            # Re-read all independently owned evidence immediately before
            # latching the returned engine.  The factory cannot echo or
            # authorize an identity.
            _fresh_compiled, fresh_warmth, fresh_expected = self._validate_admission(
                settings, expected
            )
            if fresh_expected != expected or fresh_warmth != warmth:
                close = _safe_attr(engine, "close")
                if close[0] and callable(close[1]):
                    _safe_call(lambda: close[1]())
                engine_closed = True
                with self._lock:
                    self._poison("identity_mismatch")
                raise WanLifecycleError("identity_mismatch")
            with self._lock:
                cancelled = token is not None and token.cancelled
                stale = active_record is not None and self._active is not active_record
                if cancelled or stale:
                    ok, close = _safe_attr(engine, "close")
                    if ok and callable(close) and not _safe_call(lambda: close())[0]:
                        with self._lock:
                            self._poison("cleanup_failed")
                        raise WanLifecycleError("cleanup_failed")
                    engine_closed = True
                    raise RunCancelled("cancelled")
                self._engine = engine
                self._latched_identity = expected
                self._latched_warmth = fresh_warmth
                self.last_lifecycle = "cold"
                self.last_warm_reused = False
                return compiled, warmth, self._session_generation, spool
        except RunCancelled:
            if engine is not None and not engine_closed:
                ok, close = _safe_attr(engine, "close")
                if ok and callable(close) and not _safe_call(lambda: close())[0]:
                    with self._lock:
                        self._poison("cleanup_failed")
                    failure_code = "cleanup_failed"
            cancellation_after_factory = True
        except WanLifecycleError:
            raise
        except Exception:
            with self._lock:
                self._poison("engine_init_failed")
            failure_code = "engine_init_failed"
        finally:
            with self._lock:
                self._preparing = False
        if failure_code is not None:
            raise WanLifecycleError(failure_code)
        if cancellation_after_factory:
            raise RunCancelled("cancelled")

    def prepare(
        self, settings: dict[str, Any], *, identity: WanExecutionIdentity
    ) -> dict[str, Any]:
        """Validate and latch identity, initializing or exactly reusing warmth."""
        _compiled, warmth, generation, spool = self._prepare(
            settings, self._coerce_identity(identity)
        )
        return {
            "status": "warm" if self.last_warm_reused else "cold",
            "warm_reused": self.last_warm_reused,
            "session_generation": generation,
            "warmth_identity": warmth,
            "identity_digest": identity.digest,
            "spool": str(spool),
        }

    def submit_task(
        self,
        settings: dict[str, Any],
        *,
        identity: WanExecutionIdentity | None = None,
    ) -> PersistentWanJob:
        """Submit one typed task to the latched native Wan session."""
        if identity is not None:
            identity = self._coerce_identity(identity)
        selected_for_validation = identity or self._latched_identity
        if selected_for_validation is None:
            raise WanLifecycleError("identity_incomplete", "persistent Wan task requires complete identity facts")
        # Validate settings and exact route/model/template ownership before
        # reserving the active slot or touching the native engine.
        _compiled, warmth, expected = self._validate_admission(settings, selected_for_validation)
        with self._lock:
            if self._active is not None:
                raise WanLifecycleError("session_busy", "persistent Wan session is already executing")
            selected = expected
            record = {
                "invocation_id": uuid.uuid4().hex,
                "session_generation": self._session_generation,
                "identity": selected,
                "warmth_identity": warmth,
                "phase": "PREPARING",
                "settings": dict(settings),
                "token": CancellationToken(),
                "native_job": None,
                "result": None,
                "done": threading.Event(),
                "cancel_requested": False,
                "thread": None,
            }
            self._active = record
            thread = threading.Thread(
                target=self._run_record,
                args=(record, selected, True),
                name=f"wan2gp-session-{record['invocation_id'][:8]}",
                daemon=False,
            )
            record["thread"] = thread
            thread.start()
            return PersistentWanJob(self, record)

    def _result(
        self,
        record: dict[str, Any],
        *,
        status: str,
        errors: list[str] | tuple[str, ...] = (),
        files: list[str] | tuple[str, ...] = (),
        outputs: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
    ) -> PersistentWanResult:
        identity: WanExecutionIdentity = record["identity"]
        with self._lock:
            safe_errors = tuple(
                _safe_error(item) if isinstance(item, str) and item in _ERROR_MESSAGES else _safe_error("unknown_failure")
                for item in errors
            )
            return PersistentWanResult(
                status=status,
                generated_files=tuple(files),
                errors=safe_errors,
                invocation_id=record["invocation_id"],
                session_generation=record["session_generation"],
                warmth_identity=record.get("warmth_identity") or identity.warmth_key(
                    compile_from_inputs(record["settings"]), self.warmth_profile
                ),
                identity_digest=identity.digest,
                outputs=tuple(dict(item) for item in outputs),
                cancelled=status == "cancelled",
                poisoned=self._poisoned,
                fence_pending=self._fence_pending,
            )

    def _collect_outputs(
        self, files: list[Any], spool: Path, invocation_id: str
    ) -> tuple[list[str], list[dict[str, Any]]]:
        collected: list[str] = []
        descriptors: list[dict[str, Any]] = []
        seen: set[str] = set()
        publication_root = spool / "published" / invocation_id
        publication_root.mkdir(parents=True, exist_ok=False)
        for raw in files:
            if not isinstance(raw, (str, os.PathLike)):
                raise WanLifecycleError("output_custody_failed", "Wan output path is not path-like")
            path = Path(raw).expanduser()
            resolved = path.resolve(strict=False)
            try:
                relative = resolved.relative_to(spool.resolve(strict=False))
            except ValueError:
                raise WanLifecycleError("output_custody_failed")
            if (
                not relative.parts
                or str(relative) in seen
                or path.is_symlink()
                or not resolved.is_file()
                or resolved.is_symlink()
            ):
                raise WanLifecycleError("output_custody_failed", "Wan output is not a private regular file")
            seen.add(str(relative))
            before = resolved.stat()
            digest = _hash_regular_file(resolved)
            after = resolved.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise WanLifecycleError("output_custody_failed", "Wan output changed during collection")
            destination = publication_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                with resolved.open("rb") as source, temporary.open("xb") as target:
                    shutil.copyfileobj(source, target)
                    target.flush()
                    os.fsync(target.fileno())
                os.replace(temporary, destination)
                directory_fd = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                try:
                    temporary.unlink()
                except OSError:
                    pass
                raise WanLifecycleError("output_custody_failed")
            if _hash_regular_file(destination) != digest:
                raise WanLifecycleError("output_custody_failed", "Wan output changed during publication")
            collected.append(str(destination))
            descriptors.append(
                {
                    "relative_path": str(destination.relative_to(spool)),
                    "size_bytes": before.st_size,
                    "sha256": digest,
                }
            )
        return collected, descriptors

    def _run_record(
        self, record: dict[str, Any], identity: WanExecutionIdentity, needs_prepare: bool
    ) -> None:
        result: PersistentWanResult | None = None
        try:
            if needs_prepare:
                _settings, _warmth, generation, spool = self._prepare(
                    record["settings"], identity, record["token"], record
                )
                record["session_generation"] = generation
            _settings, fresh_warmth, fresh_identity = self._validate_admission(
                record["settings"], identity
            )
            with self._lock:
                if (
                    self._latched_identity != fresh_identity
                    or self._latched_warmth != fresh_warmth
                    or self._engine is None
                    or self._session_generation != record["session_generation"]
                ):
                    raise WanLifecycleError("identity_mismatch")
                if not self._engine_alive(self._engine):
                    self._poison("engine_not_alive")
                    raise WanLifecycleError("engine_not_alive")
                if self._active is not record or self._session_generation != record["session_generation"]:
                    raise WanLifecycleError("stale_generation")
                engine = self._engine
                record["phase"] = "EXECUTING"
            ok, submit = _safe_attr(engine, "submit_task")
            if not ok or not callable(submit):
                raise WanLifecycleError("engine_unsupported")
            ok, native_job = _safe_call(lambda: submit(compile_from_inputs(record["settings"])))
            if not ok or native_job is None:
                raise WanLifecycleError("engine_failed")
            with self._lock:
                record["native_job"] = native_job
                cancelled = record["cancel_requested"] or record["token"].cancelled
            cancel_failed = False
            if cancelled:
                ok, cancel = _safe_attr(native_job, "cancel")
                if ok and callable(cancel):
                    cancel_failed = not _safe_call(lambda: cancel())[0]
            ok, result_method = _safe_attr(native_job, "result")
            if ok and callable(result_method):
                ok, native_result = _safe_call(lambda: result_method())
                if not ok:
                    raise WanLifecycleError("engine_failed")
            else:
                native_result = native_job
            with self._lock:
                cancelled = record["cancel_requested"] or record["token"].cancelled
            ok, native_files = _safe_attr(native_result, "generated_files")
            if not ok:
                raise WanLifecycleError("engine_failed")
            ok, native_files = _safe_call(lambda: list(native_files or []))
            if not ok:
                raise WanLifecycleError("engine_failed")
            ok, native_success = _safe_attr(native_result, "success")
            if not ok:
                raise WanLifecycleError("engine_failed")
            ok, native_success = _safe_call(lambda: bool(native_success))
            if not ok:
                raise WanLifecycleError("engine_failed")
            _terminal_settings, terminal_warmth, terminal_identity = self._validate_admission(
                record["settings"], identity
            )
            with self._lock:
                if (
                    self._active is not record
                    or self._session_generation != record["session_generation"]
                    or self._latched_identity != terminal_identity
                    or self._latched_warmth != terminal_warmth
                ):
                    raise WanLifecycleError("identity_mismatch")
            if cancel_failed:
                with self._lock:
                    self._poison("cancel_failed")
                result = self._result(record, status="failed", errors=("cancel_failed",))
            elif cancelled:
                result = self._result(record, status="cancelled", errors=("cancelled",))
            elif not native_success:
                with self._lock:
                    self._poison("engine_failed")
                result = self._result(record, status="failed", errors=("engine_failed",))
            else:
                _final_settings, final_warmth, final_identity = self._validate_admission(
                    record["settings"], identity
                )
                with self._lock:
                    if (
                        self._active is not record
                        or self._session_generation != record["session_generation"]
                        or self._latched_identity != final_identity
                        or self._latched_warmth != final_warmth
                        or self._session_generation != record["session_generation"]
                    ):
                        raise WanLifecycleError("stale_generation")
                    files, outputs = self._collect_outputs(
                        native_files, spool, record["invocation_id"]
                    )
                if not files:
                    raise WanLifecycleError("output_custody_failed")
                result = self._result(record, status="succeeded", files=files, outputs=outputs)
        except RunCancelled:
            result = self._result(record, status="cancelled", errors=("cancelled",))
        except WanLifecycleError as exc:
            with self._lock:
                if exc.code not in {"identity_mismatch", "session_busy", "stale_generation"}:
                    self._poison(exc.code)
            result = self._result(
                record,
                status="cancelled" if record["cancel_requested"] and exc.code == "cancel_failed" else "failed",
                errors=(exc.code,),
            )
        except Exception:
            with self._lock:
                self._poison("unknown_failure")
            result = self._result(record, status="failed", errors=("unknown_failure",))
        finally:
            if result is None:
                result = self._result(record, status="failed", errors=("unknown_failure",))
            with self._lock:
                if self._active is record and self._session_generation == record["session_generation"]:
                    record["phase"] = "TERMINAL"
                    record["result"] = result
                    self._active = None
                else:
                    # A stale completion is observable by its caller but may
                    # never clear a newer session's fence, identity, or owner.
                    record["result"] = result
                record["native_job"] = None
                record["done"].set()

    def _request_cancel(self, record: dict[str, Any]) -> bool:
        with self._lock:
            if self._active is not record:
                return record["done"].is_set()
            record["cancel_requested"] = True
            record["phase"] = "CANCELLING"
            record["token"].cancel("cancelled")
            native_job = record.get("native_job")
        ok, cancel = _safe_attr(native_job, "cancel") if native_job is not None else (True, None)
        if ok and callable(cancel):
            if not _safe_call(lambda: cancel())[0]:
                with self._lock:
                    self._poison("cancel_failed")
        return True

    def cancel(self, *, timeout: float = 5.0) -> dict[str, Any]:
        with self._lock:
            record = self._active
        if record is None:
            return {"ok": True, "status": "cold" if not self.warm else "warm", "active": False}
        self._request_cancel(record)
        if not record["done"].wait(timeout):
            with self._lock:
                self._poison("timeout")
            return {
                "ok": False,
                "status": "cancellation_pending",
                "error": _safe_error("timeout"),
                "fence_pending": True,
            }
        result = record["result"]
        return {"ok": result.status == "cancelled", **result.to_dict(), "active": False}

    def release(self, *, timeout: float = 5.0) -> dict[str, Any]:
        cancelled = self.cancel(timeout=timeout)
        if cancelled.get("status") == "cancellation_pending":
            return cancelled
        with self._lock:
            if self._active is not None:
                return {"ok": False, "status": "release_pending", "fence_pending": True}
            if self._engine is None:
                self.last_lifecycle = "cold"
                self.last_warm_reused = False
                return {"ok": True, "status": "cold", "released": False}
            try:
                self._close_engine_locked()
            except WanLifecycleError:
                self._poison("release_failed")
                return {
                    "ok": False,
                    "status": "release_failed",
                    "error": _safe_error("release_failed"),
                    "fence_pending": True,
                }
            except Exception:
                self._poison("cleanup_failed")
                return {
                    "ok": False,
                    "status": "release_failed",
                    "error": _safe_error("cleanup_failed"),
                    "fence_pending": True,
                }
            self._engine = None
            self._latched_identity = None
            self._latched_warmth = None
            self.last_lifecycle = "cold"
            self.last_warm_reused = False
            return {
                "ok": True,
                "status": "cold",
                "released": True,
                "fence_pending": self._fence_pending,
            }

    def cold_reset(self, *, timeout: float = 5.0) -> dict[str, Any]:
        """Release the exact owner, then clear a poison/fence for cold reuse."""
        released = self.release(timeout=timeout)
        if not released.get("ok"):
            return {**released, "status": "cold_reset_failed"}
        with self._lock:
            if self._cleanup_fence:
                return {
                    "ok": False,
                    "status": "cold_reset_failed",
                    "error": _safe_error("cleanup_failed"),
                    "fence_pending": True,
                }
            self._poisoned = False
            self._fence_pending = False
            self._last_error = None
            self.last_lifecycle = "cold"
        return {"ok": True, "status": "cold", "recovered": True}

    recover = cold_reset

    def close(self, *, timeout: float = 5.0) -> dict[str, Any]:
        return self.release(timeout=timeout)


# Names used in handoffs and by pack authors.
WanGPSession = PersistentWanSession
WanGPSessionDriver = PersistentWanSession
PersistentWanDriver = PersistentWanSession


def persistent_run(
    settings: dict[str, Any],
    identity: WanExecutionIdentity,
    *,
    output_root: str | os.PathLike[str],
    engine_factory: Callable[[WanExecutionIdentity, Path], Any] | None = None,
) -> PersistentWanResult:
    """Run one typed task through a disposable persistent-session owner."""
    session = PersistentWanSession(output_root=output_root, engine_factory=engine_factory)
    try:
        return session.submit_task(settings, identity=identity).result()
    finally:
        session.release()


run_persistent = persistent_run


def fake_persistent_run(
    settings: dict[str, Any],
    state_path: str | os.PathLike[str],
    **kwargs: Any,
) -> FakeRunResult:
    """Run one deterministic fake attempt using a persisted runner journal."""
    return FakePersistentRunner(state_path).run(settings, **kwargs)


run_fake = fake_persistent_run


@dataclass(frozen=True)
class DriverSpec:
    wan2gp_root: Path
    attempt_root: Path
    output_dir: Path


@dataclass(frozen=True)
class DriverResult:
    success: bool
    generated_files: list[str]
    errors: list[str]
    total_tasks: int
    successful_tasks: int
    failed_tasks: int
    disclosed_engine: dict[str, Any]
    spool: Path


def _disclosed_engine(_wan2gp_root: Path | None = None) -> dict[str, Any]:
    return {
        "engine": "wan2gp",
        "route": "owned",
    }


def _verify_within_spool(path: Path, spool: Path) -> bool:
    try:
        resolved = path.resolve()
        spool_resolved = spool.resolve()
        return resolved == spool_resolved or resolved.is_relative_to(spool_resolved)
    except Exception:
        return False


def _verify_outputs_in_spool(files: list[str], spool: Path) -> list[str]:
    violations: list[str] = []
    for raw in files:
        candidate = Path(raw)
        if not _verify_within_spool(candidate, spool):
            violations.append(raw)
    return violations


def _terminal_mapping(
    generation_result: Any, spool: Path, errors: list[str]
) -> dict[str, Any]:
    """Map the native GenerationResult / failure into structured terminal evidence."""
    if generation_result is None:
        return {
            "status": "failed",
            "reason": _safe_error(errors[0] if errors else "unknown_failure"),
            "generated_files": [],
            "spool": spool,
            "disclosed_engine": _disclosed_engine(None),
        }
    ok, success = _safe_attr(generation_result, "success")
    if not ok:
        success = False
    ok, success = _safe_call(lambda: bool(success))
    if not ok:
        success = False
    ok, files = _safe_attr(generation_result, "generated_files")
    if not ok:
        files = []
        success = False
    ok, files = _safe_call(lambda: list(files or []))
    if not ok:
        files = []
        success = False
    violations = _verify_outputs_in_spool(files, spool)
    if violations:
        success = False
        errors = ["output_custody_failed"]
    code = errors[0] if errors else ("unknown_failure" if not success else "")
    ok, total = _safe_attr(generation_result, "total_tasks")
    total = total if ok else 0
    ok, successful = _safe_attr(generation_result, "successful_tasks")
    successful = successful if ok else 0
    ok, failed = _safe_attr(generation_result, "failed_tasks")
    failed = failed if ok else 0
    ok, total = _safe_call(lambda: int(total or 0))
    total = total if ok else 0
    ok, successful = _safe_call(lambda: int(successful or 0))
    successful = successful if ok else 0
    ok, failed = _safe_call(lambda: int(failed or 0))
    failed = failed if ok else 0
    return {
        "status": "succeeded" if success else "failed",
        "reason": _safe_error(code) if code else None,
        "generated_files": files if success else [],
        "total_tasks": total,
        "successful_tasks": successful,
        "failed_tasks": failed,
        "spool": spool,
        "disclosed_engine": _disclosed_engine(None),
    }


def resolve_wan2gp_root(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """Resolve only an explicitly supplied pinned Wan2GP checkout root."""
    if explicit is None:
        return None
    try:
        candidate = Path(explicit)
        if not candidate.is_absolute() or candidate.is_symlink():
            return None
        canonical = candidate.resolve(strict=False)
        api_file = canonical / "shared" / "api.py"
        if (
            not canonical.is_dir()
            or canonical.is_symlink()
            or api_file.is_symlink()
            or not api_file.is_file()
            or api_file.resolve(strict=False).relative_to(canonical) != Path("shared/api.py")
        ):
            return None
        return canonical
    except (OSError, ValueError, TypeError):
        return None

def _cancellation_reason(
    token: CancellationToken | None,
    cancelled: Callable[[], bool] | None,
) -> str | None:
    if token is not None:
        ok, requested = _safe_call(lambda: bool(token.cancelled))
        if ok and requested:
            return "cancelled"
    if cancelled is not None and _safe_call(lambda: bool(cancelled()))[1]:
        return "cancelled"
    return None


def _cancelled_driver_result(reason: str, spool: Path, disclosed: dict[str, Any]) -> DriverResult:
    return DriverResult(
        success=False,
        generated_files=[],
        errors=["cancelled: Wan operation was cancelled."],
        total_tasks=0,
        successful_tasks=0,
        failed_tasks=1,
        disclosed_engine=disclosed,
        spool=spool,
    )


def one_shot_run(
    *,
    settings: dict[str, Any],
    attempt_root: str | os.PathLike[str],
    wan2gp_root: str | os.PathLike[str] | None = None,
    timeout: float | None = None,
    cancel_token: CancellationToken | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> DriverResult:
    """Run one Wan2GP task in a private per-attempt spool (one-shot).

    Creates ``attempt_root/outputs`` as the private spool and passes it as
    ``output_dir`` to ``shared.api.init``.  The session is closed (model
    release) before return.  Outputs are verified to stay inside the spool.
    """
    try:
        attempt = Path(attempt_root).resolve()
    except Exception:
        attempt = Path(os.getcwd()) / "invalid-wan-attempt"
    spool = attempt / "outputs"
    disclosed = _disclosed_engine(None)
    if _cancellation_reason(cancel_token, cancelled) is not None:
        return _cancelled_driver_result("cancelled", spool, disclosed)
    root = resolve_wan2gp_root(wan2gp_root)
    if root is None:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=[_driver_error("root_unavailable")],
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=1,
            disclosed_engine=disclosed,
            spool=spool,
        )
    try:
        compiled = compile_from_inputs(settings)
        validate_settings(compiled)
    except Exception:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=[_driver_error("unknown_failure")],
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=1,
            disclosed_engine=disclosed,
            spool=spool,
        )

    # No complete owner evidence is available in production.  A test may
    # replace the private reader with independently created fixture evidence;
    # the resulting identity is still derived here, from actual observations.
    outcome, identity = _derive_owned_identity(compiled, None)  # type: ignore[arg-type]
    if outcome != "ok" or identity is None:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=[_driver_error(outcome)],
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=1,
            disclosed_engine=disclosed,
            spool=spool,
        )
    ok, _ = _safe_call(lambda: spool.mkdir(parents=True, exist_ok=True))
    if not ok:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=[_driver_error("output_custody_failed")],
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=1,
            disclosed_engine=disclosed,
            spool=spool,
        )

    original_path = list(sys.path)
    original_cwd = Path.cwd()
    session: Any | None = None
    primary_code = "unknown_failure"
    final_result: DriverResult | None = None
    cleanup_failed = False
    try:
        factory_error: str | None = None
        try:
            session = _native_wan_session_factory(identity, spool)
        except WanLifecycleError as exc:
            factory_error = exc.code
        except Exception:
            factory_error = "engine_init_failed"
        if factory_error is not None or session is None:
            primary_code = factory_error or "engine_init_failed"
            final_result = DriverResult(False, [], [_driver_error(primary_code)], 0, 0, 1, disclosed, spool)
        else:
            ok, submit = _safe_attr(session, "submit_task")
            if not ok or not callable(submit):
                primary_code = "engine_unsupported"
                final_result = DriverResult(False, [], [_driver_error(primary_code)], 0, 0, 1, disclosed, spool)
            else:
                ok, job = _safe_call(lambda: submit(compiled))
                if not ok or job is None:
                    primary_code = "transport_failed"
                    final_result = DriverResult(False, [], [_driver_error(primary_code)], 0, 0, 1, disclosed, spool)
                else:
                    reason = _cancellation_reason(cancel_token, cancelled)
                    if reason is not None:
                        ok, cancel_fn = _safe_attr(job, "cancel")
                        if ok and callable(cancel_fn) and not _safe_call(lambda: cancel_fn())[0]:
                            primary_code = "cancel_failed"
                        else:
                            raise RunCancelled("cancelled")
                    ok, result_method = _safe_attr(job, "result")
                    if ok and callable(result_method):
                        ok, native_result = _safe_call(lambda: result_method(timeout=timeout))
                        if not ok:
                            primary_code = "timeout" if timeout is not None else "engine_failed"
                            final_result = DriverResult(False, [], [_driver_error(primary_code)], 0, 0, 1, disclosed, spool)
                    else:
                        native_result = job
                    if final_result is None:
                        mapped = _terminal_mapping(
                            native_result,
                            spool,
                            [primary_code] if primary_code != "unknown_failure" else [],
                        )
                        if mapped["status"] == "failed":
                            mapped_code = primary_code if primary_code != "unknown_failure" else "engine_failed"
                            final_result = DriverResult(
                                success=False,
                                generated_files=[],
                                errors=[_driver_error(mapped_code)],
                                total_tasks=mapped.get("total_tasks", 0),
                                successful_tasks=mapped.get("successful_tasks", 0),
                                failed_tasks=max(1, mapped.get("failed_tasks", 0)),
                                disclosed_engine=disclosed,
                                spool=spool,
                            )
                        else:
                            final_result = DriverResult(
                                success=True,
                                generated_files=mapped["generated_files"],
                                errors=[],
                                total_tasks=mapped["total_tasks"],
                                successful_tasks=mapped["successful_tasks"],
                                failed_tasks=mapped["failed_tasks"],
                                disclosed_engine=disclosed,
                                spool=spool,
                            )
    except RunCancelled:
        primary_code = "cancelled"
        final_result = DriverResult(False, [], [_driver_error(primary_code)], 0, 0, 1, disclosed, spool)
    except Exception:
        final_result = DriverResult(False, [], [_driver_error(primary_code)], 0, 0, 1, disclosed, spool)
    finally:
        if session is not None:
            ok, close = _safe_attr(session, "close")
            if not ok or not callable(close) or not _safe_call(lambda: close())[0]:
                cleanup_failed = True
        sys.path[:] = original_path
        if not _safe_call(lambda: os.chdir(original_cwd))[0]:
            cleanup_failed = True
    if final_result is None:
        final_result = DriverResult(False, [], [_driver_error("unknown_failure")], 0, 0, 1, disclosed, spool)
    if cleanup_failed and final_result.success:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=[_driver_error("cleanup_failed")],
            total_tasks=final_result.total_tasks,
            successful_tasks=0,
            failed_tasks=max(1, final_result.failed_tasks),
            disclosed_engine=disclosed,
            spool=spool,
        )
    return final_result


def validate_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Validate (but do not execute) a compiled Wan2GP settings dict.

    Returns a sanitized copy with known portable keys preserved.  Raises
    ValueError with a disclosed message on missing/invalid inputs.
    """
    if not isinstance(settings, dict):
        raise ValueError("settings must be a dict")
    prompt = settings.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt is required and must be a non-empty string")
    model = settings.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError("model must be a non-empty string when provided")
    # Resolution sanity (if provided)
    res = settings.get("resolution")
    if res is not None:
        text = str(res).strip()
        if "x" not in text.lower():
            raise ValueError("resolution must be WxH, e.g. 1280x720")
        parts = text.lower().split("x")
        if len(parts) != 2 or not all(p.strip().isdigit() for p in parts):
            raise ValueError("resolution must be WxH with integer dimensions")
    # video_length sanity
    vl = settings.get("video_length")
    if vl is not None and int(vl) <= 0:
        raise ValueError("video_length must be a positive integer")
    return dict(settings)
