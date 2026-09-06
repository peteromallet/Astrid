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


class RunCancelled(RuntimeError):
    """Cooperative cancellation requested before a fake lifecycle step."""

    code = "cancelled"


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
            self._reason = str(reason) or "cancelled"
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
        except (OSError, StopIteration, KeyError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read runner state {resolved}: {exc}") from exc
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
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read runner state {self.path}: {exc}") from exc
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
                last_error = event.get("reason")
            elif kind == "run_failed":
                failed += 1
                last_error = event.get("reason")
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
        payload = {"reason": str(reason)} if reason is not None else {}
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
                error = f"output containment violated: {[str(candidate)]}"
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
            self.state.finish_run("cancelled", reason=str(exc))
            return FakeRunResult(
                status="cancelled",
                generated_files=[],
                errors=[str(exc)],
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

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = str(code)


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
        raise WanLifecycleError("unsupported_route", "persistent Wan route is not owned")
    if identity.engine_seam != "shared.api.init/WanGPSession.submit_task":
        raise WanLifecycleError("unsupported_engine_seam", "persistent Wan engine seam is unsupported")
    if not root.is_dir() or not (root / "shared" / "api.py").is_file():
        raise WanLifecycleError("root_unavailable", "identified Wan2GP root is unavailable")
    executable = Path(identity.interpreter)
    if executable.resolve(strict=False) != Path(sys.executable).resolve(strict=False):
        raise WanLifecycleError("interpreter_mismatch", "identified interpreter is not the active interpreter")
    try:
        if _hash_regular_file(executable) != identity.interpreter_sha256:
            raise WanLifecycleError("interpreter_mismatch", "identified interpreter bytes changed")
    except OSError as exc:
        raise WanLifecycleError("interpreter_unavailable", "identified interpreter cannot be verified") from exc

    original_path = list(sys.path)
    original_cwd = Path.cwd()
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        os.chdir(root)
        import importlib

        api = importlib.import_module("shared.api")
        init_fn = getattr(api, "init", None)
        if not callable(init_fn):
            raise WanLifecycleError("engine_unavailable", "Wan2GP shared.api.init is unavailable")
        return init_fn(root=root, output_dir=output_dir, console_output=False)
    except WanLifecycleError:
        raise
    except Exception as exc:
        raise WanLifecycleError("engine_init_failed", str(exc)) from exc
    finally:
        sys.path[:] = original_path
        os.chdir(original_cwd)


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
            raise TypeError("persistent Wan requires a complete WanExecutionIdentity")
        return identity

    def _validate_admission(
        self, settings: dict[str, Any], identity: WanExecutionIdentity
    ) -> tuple[dict[str, Any], str]:
        if not isinstance(settings, dict):
            raise ValueError("Wan settings must be a dict")
        compiled = compile_from_inputs(settings)
        validate_settings(compiled)
        model, template = self._settings_identity(compiled)
        if model != identity.model:
            raise WanLifecycleError("model_identity_mismatch", "Wan model identity does not match settings")
        if template != identity.model_template:
            raise WanLifecycleError("model_template_mismatch", "Wan model template does not match settings")
        if identity.route != "wan2gp.generate_video":
            raise WanLifecycleError("unsupported_route", "persistent Wan route is not owned")
        if identity.engine_seam != "shared.api.init/WanGPSession.submit_task":
            raise WanLifecycleError("unsupported_engine_seam", "persistent Wan engine seam is unsupported")
        return compiled, identity.warmth_key(compiled, self.warmth_profile)

    @staticmethod
    def _engine_alive(engine: Any) -> bool:
        probe = getattr(engine, "is_alive", None)
        if callable(probe):
            try:
                return bool(probe())
            except Exception:
                return False
        if getattr(engine, "closed", False) is True:
            return False
        return True

    def _poison(self, reason: str, *, fence: bool = True) -> None:
        self._poisoned = True
        self._fence_pending = fence
        self._last_error = str(reason)
        self.last_lifecycle = "cold"
        self.last_warm_reused = False

    def _close_engine_locked(self) -> None:
        engine = self._engine
        if engine is None:
            return
        close = getattr(engine, "close", None)
        if not callable(close):
            raise WanLifecycleError("release_unsupported", "Wan engine does not expose close/free")
        close()

    def _prepare(
        self,
        settings: dict[str, Any],
        identity: WanExecutionIdentity,
        token: CancellationToken | None = None,
        active_record: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str, int, Path]:
        compiled, warmth = self._validate_admission(settings, identity)
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
                except Exception as exc:
                    self._poison(str(exc))
                    raise WanLifecycleError("release_failed", str(exc)) from exc
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
        try:
            engine = self._engine_factory(identity, spool)
            if engine is None:
                raise WanLifecycleError("engine_unavailable", "Wan engine factory returned no session")
            if token is not None:
                token.raise_if_cancelled()
            with self._lock:
                cancelled = token is not None and token.cancelled
                stale = active_record is not None and self._active is not active_record
                if cancelled or stale:
                    close = getattr(engine, "close", None)
                    if callable(close):
                        close()
                    engine_closed = True
                    raise RunCancelled(token.reason if token is not None else "cancelled")
                self._engine = engine
                self._latched_identity = identity
                self._latched_warmth = warmth
                self.last_lifecycle = "cold"
                self.last_warm_reused = False
                return compiled, warmth, self._session_generation, spool
        except RunCancelled:
            if engine is not None and not engine_closed:
                close = getattr(engine, "close", None)
                if callable(close):
                    try:
                        close()
                    except Exception as exc:
                        with self._lock:
                            self._poison(str(exc))
            raise
        except Exception as exc:
            with self._lock:
                self._poison(str(exc))
            raise WanLifecycleError(getattr(exc, "code", "engine_init_failed"), str(exc)) from exc
        finally:
            with self._lock:
                self._preparing = False

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
        self._validate_admission(settings, selected_for_validation)
        with self._lock:
            if self._active is not None:
                raise WanLifecycleError("session_busy", "persistent Wan session is already executing")
            selected = identity or self._latched_identity
            if selected is None:
                raise WanLifecycleError("identity_incomplete", "persistent Wan task requires complete identity facts")
            record = {
                "invocation_id": uuid.uuid4().hex,
                "session_generation": self._session_generation,
                "identity": selected,
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
            return PersistentWanResult(
                status=status,
                generated_files=tuple(files),
                errors=tuple(str(item) for item in errors),
                invocation_id=record["invocation_id"],
                session_generation=record["session_generation"],
                warmth_identity=self._latched_warmth or identity.warmth_key(
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
            except ValueError as exc:
                raise WanLifecycleError("output_custody_failed", "Wan output escaped its owned spool") from exc
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
            except OSError as exc:
                try:
                    temporary.unlink()
                except OSError:
                    pass
                raise WanLifecycleError("output_custody_failed", "Wan output publication failed") from exc
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
        result: PersistentWanResult
        try:
            if needs_prepare:
                _settings, _warmth, generation, spool = self._prepare(
                    record["settings"], identity, record["token"], record
                )
                record["session_generation"] = generation
            else:
                with self._lock:
                    if self._latched_identity != identity or self._engine is None:
                        raise WanLifecycleError("identity_mismatch", "latched Wan session identity changed")
                    if not self._engine_alive(self._engine):
                        self._poison("latched Wan engine is no longer alive")
                        raise WanLifecycleError("engine_not_alive", "latched Wan engine is no longer alive")
                    spool = self.output_root / f"generation-{self._session_generation}"
            with self._lock:
                if self._active is not record or self._session_generation != record["session_generation"]:
                    raise WanLifecycleError("stale_generation", "stale Wan invocation cannot execute")
                engine = self._engine
                record["phase"] = "EXECUTING"
            submit = getattr(engine, "submit_task", None)
            if not callable(submit):
                raise WanLifecycleError("engine_unsupported", "Wan engine does not expose submit_task")
            native_job = submit(compile_from_inputs(record["settings"]))
            with self._lock:
                record["native_job"] = native_job
                cancelled = record["cancel_requested"] or record["token"].cancelled
            if cancelled:
                cancel = getattr(native_job, "cancel", None)
                if callable(cancel):
                    cancel()
            native_result = native_job.result() if hasattr(native_job, "result") else native_job
            with self._lock:
                cancelled = record["cancel_requested"] or record["token"].cancelled
            native_files = list(getattr(native_result, "generated_files", []) or [])
            native_success = bool(getattr(native_result, "success", False))
            native_errors = [str(item) for item in (getattr(native_result, "errors", []) or [])]
            if cancelled:
                result = self._result(record, status="cancelled", errors=native_errors or ["cancelled"])
            elif not native_success:
                reason = native_errors or ["Wan engine reported failure"]
                with self._lock:
                    self._poison("; ".join(reason))
                result = self._result(record, status="failed", errors=reason)
            else:
                with self._lock:
                    if self._active is not record or self._session_generation != record["session_generation"]:
                        raise WanLifecycleError("stale_generation", "stale Wan invocation cannot publish outputs")
                    files, outputs = self._collect_outputs(
                        native_files, spool, record["invocation_id"]
                    )
                if not files:
                    raise WanLifecycleError("output_custody_failed", "Wan engine produced no outputs")
                result = self._result(record, status="succeeded", files=files, outputs=outputs)
        except RunCancelled as exc:
            result = self._result(record, status="cancelled", errors=[str(exc)])
        except Exception as exc:
            code = getattr(exc, "code", "engine_failed")
            with self._lock:
                if code not in {"identity_mismatch", "session_busy", "unsupported_route", "unsupported_engine_seam"}:
                    self._poison(str(exc))
            result = self._result(record, status="cancelled" if record["cancel_requested"] else "failed", errors=[f"{code}: {exc}"])
        finally:
            with self._lock:
                if self._active is record and self._session_generation == record["session_generation"]:
                    record["phase"] = "TERMINAL"
                    record["result"] = result
                    self._active = None
                else:
                    # A stale completion is observable by its caller but may
                    # never clear a newer session's fence, identity, or owner.
                    record["result"] = result
                record["done"].set()

    def _request_cancel(self, record: dict[str, Any]) -> bool:
        with self._lock:
            if self._active is not record:
                return record["done"].is_set()
            record["cancel_requested"] = True
            record["phase"] = "CANCELLING"
            record["token"].cancel("cancelled")
            native_job = record.get("native_job")
        cancel = getattr(native_job, "cancel", None)
        if callable(cancel):
            try:
                cancel()
            except Exception as exc:
                with self._lock:
                    self._poison(str(exc))
        return True

    def cancel(self, *, timeout: float = 5.0) -> dict[str, Any]:
        with self._lock:
            record = self._active
        if record is None:
            return {"ok": True, "status": "cold" if not self.warm else "warm", "active": False}
        self._request_cancel(record)
        if not record["done"].wait(timeout):
            with self._lock:
                self._poison("cancellation did not reach a terminal state")
            return {"ok": False, "status": "cancellation_pending", "fence_pending": True}
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
            except Exception as exc:
                self._poison(str(exc))
                return {"ok": False, "status": "release_failed", "error": str(exc), "fence_pending": True}
            self._engine = None
            self._latched_identity = None
            self._latched_warmth = None
            self.last_lifecycle = "cold"
            self.last_warm_reused = False
            return {"ok": True, "status": "cold", "released": True, "fence_pending": False}

    def cold_reset(self, *, timeout: float = 5.0) -> dict[str, Any]:
        """Release the exact owner, then clear a poison/fence for cold reuse."""
        released = self.release(timeout=timeout)
        if not released.get("ok"):
            return {**released, "status": "cold_reset_failed"}
        with self._lock:
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


def _disclosed_engine(wan2gp_root: Path | None) -> dict[str, Any]:
    return {
        "engine": "wan2gp",
        "pin_sha": WAN2GP_PIN_SHA,
        "pin_ref": WAN2GP_PIN_REF,
        "wan2gp_root": str(wan2gp_root) if wan2gp_root is not None else None,
        "seam": "shared.api.init / WanGPSession.submit_task",
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
            "reason": "; ".join(errors) if errors else "unknown failure",
            "generated_files": [],
            "spool": str(spool),
            "disclosed_engine": _disclosed_engine(None),
        }
    success = bool(getattr(generation_result, "success", False))
    files = list(getattr(generation_result, "generated_files", []) or [])
    gen_errors = getattr(generation_result, "errors", []) or []
    error_texts = [str(e) for e in gen_errors] + errors
    violations = _verify_outputs_in_spool(files, spool)
    if violations:
        error_texts.append(f"output containment violated: {violations}")
        success = False
    return {
        "status": "succeeded" if success else "failed",
        "reason": "; ".join(error_texts) if error_texts else None,
        "generated_files": files if success else [],
        "total_tasks": int(getattr(generation_result, "total_tasks", 0) or 0),
        "successful_tasks": int(getattr(generation_result, "successful_tasks", 0) or 0),
        "failed_tasks": int(getattr(generation_result, "failed_tasks", 0) or 0),
        "spool": str(spool),
        "disclosed_engine": _disclosed_engine(None),
    }


def resolve_wan2gp_root(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """Resolve only an explicitly supplied pinned Wan2GP checkout root."""
    if explicit is None:
        return None
    candidate = Path(explicit).expanduser()
    if not candidate.is_absolute() or candidate.is_symlink():
        return None
    candidate = candidate.resolve(strict=False)
    if candidate.is_dir() and (candidate / "shared" / "api.py").is_file():
        return candidate
    return None

def _cancellation_reason(
    token: CancellationToken | None,
    cancelled: Callable[[], bool] | None,
) -> str | None:
    if token is not None and token.cancelled:
        return token.reason or "cancelled"
    if cancelled is not None and cancelled():
        return "cancelled"
    return None


def _cancelled_driver_result(reason: str, spool: Path, disclosed: dict[str, Any]) -> DriverResult:
    return DriverResult(
        success=False,
        generated_files=[],
        errors=[f"cancelled: {reason}"],
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
    attempt = Path(attempt_root).expanduser().resolve()
    spool = attempt / "outputs"
    spool.mkdir(parents=True, exist_ok=True)
    root = resolve_wan2gp_root(wan2gp_root)
    disclosed = _disclosed_engine(root)
    reason = _cancellation_reason(cancel_token, cancelled)
    if reason is not None:
        return _cancelled_driver_result(reason, spool, disclosed)


    if root is None:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=["Wan2GP checkout not found (expected Wan2GP/shared/api.py under WAN2GP_PATH or sibling checkout)"],
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=1,
            disclosed_engine=disclosed,
            spool=spool,
        )

    # Ensure the Wan2GP checkout is importable as a top-level package
    # ``shared`` (Wan2GP's own top-level package).  The native API expects
    # to be imported after ``ensure_wan2gp_on_path``-style path insertion
    # and a cwd inside the checkout.
    original_path = list(sys.path)
    original_cwd = Path.cwd()
    try:
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        # Also add parent so ``import Wan2GP.shared.api`` could work if needed
        parent = str(root.parent)
        if parent not in sys.path:
            sys.path.insert(0, parent)
        os.chdir(root)
        # Import the native API lazily (heavy; pulls torch-era deps on first use)
        import importlib

        api = importlib.import_module("shared.api")
        init_fn = getattr(api, "init", None)
        if not callable(init_fn):
            return DriverResult(
                success=False,
                generated_files=[],
                errors=["Wan2GP shared.api.init not found"],
                total_tasks=0,
                successful_tasks=0,
                failed_tasks=1,
                disclosed_engine=disclosed,
                spool=spool,
            )
        session = init_fn(root=root, output_dir=spool, console_output=False)
        try:
            job = session.submit_task(settings)
            reason = _cancellation_reason(cancel_token, cancelled)
            if reason is not None:
                cancel_fn = getattr(job, "cancel", None)
                if callable(cancel_fn):
                    try:
                        cancel_fn()
                    except Exception:
                        pass
                raise RunCancelled(reason)
            result = job.result(timeout=timeout)
            violations = _verify_outputs_in_spool(list(getattr(result, "generated_files", []) or []), spool)
            if violations:
                return DriverResult(
                    success=False,
                    generated_files=[],
                    errors=[f"output containment violated: {violations}"],
                    total_tasks=int(getattr(result, "total_tasks", 0) or 0),
                    successful_tasks=int(getattr(result, "successful_tasks", 0) or 0),
                    failed_tasks=max(1, int(getattr(result, "failed_tasks", 0) or 0)),
                    disclosed_engine=disclosed,
                    spool=spool,
                )
            disclosed["wan2gp_root"] = str(root)
            return DriverResult(
                success=bool(getattr(result, "success", False)),
                generated_files=list(getattr(result, "generated_files", []) or []),
                errors=[str(e) for e in (getattr(result, "errors", []) or [])],
                total_tasks=int(getattr(result, "total_tasks", 0) or 0),
                successful_tasks=int(getattr(result, "successful_tasks", 0) or 0),
                failed_tasks=int(getattr(result, "failed_tasks", 0) or 0),
                disclosed_engine=disclosed,
                spool=spool,
            )
        finally:
            try:
                session.close()
            except Exception:
                pass
    except RunCancelled as exc:
        return _cancelled_driver_result(str(exc), spool, disclosed)
    except TimeoutError as exc:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=[f"timeout: {exc}"],
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=1,
            disclosed_engine=disclosed,
            spool=spool,
        )
    except Exception as exc:
        return DriverResult(
            success=False,
            generated_files=[],
            errors=[str(exc)],
            total_tasks=0,
            successful_tasks=0,
            failed_tasks=1,
            disclosed_engine=disclosed,
            spool=spool,
        )
    finally:
        sys.path[:] = original_path
        try:
            os.chdir(original_cwd)
        except Exception:
            pass


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
