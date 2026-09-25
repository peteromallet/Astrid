"""Durable execution reconciliation over Astrid's existing task APIs.

This is intentionally a thin state machine, not a scheduler or a second
database.  Runtime task/attempt records remain authoritative; the reconciler
only binds a frozen request to an observed target, fences uncertain work, and
verifies output custody before settlement.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from astrid.core.media import MediaProbeError, ffprobe_metadata_strict
from astrid.sdk.execution_request import (
    ExecutionRequestError,
    merge_execution_input_manifest,
    normalize_execution_request,
)

from .target_adapter import TargetAdapter, TargetAdapterError, TargetObservation


class ReconcilerError(RuntimeError):
    """Base reconciler error."""


class ExecutionUncertain(ReconcilerError):
    """The engine or delivery outcome cannot be safely replayed."""


class OutputCustodyError(ReconcilerError):
    """An output failed containment, hash, size, or decode verification."""


OutputVerifier = Callable[
    [Path, Mapping[str, Any], tuple[str, ...]], Mapping[str, Any] | None
]

_SUPPORTED_OUTPUT_REQUIREMENTS = frozenset(
    {"sha256", "decode", "audio", "video", "image"}
)


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    data = getattr(value, "data", None)
    if isinstance(data, Mapping):
        return dict(data)
    return {
        key: getattr(value, key)
        for key in (
            "task_id",
            "id",
            "run_id",
            "attempt_id",
            "lease_id",
            "fence",
            "runtime_epoch",
            "spec",
            "state",
            "status",
            "result",
            "idempotency_key",
            "capability_id",
            "execution_binding",
        )
        if hasattr(value, key)
    }


def _ok_data(value: Any) -> tuple[bool, dict[str, Any], str]:
    if hasattr(value, "ok") and hasattr(value, "data"):
        if not bool(value.ok):
            error = getattr(value, "error", None)
            return False, {}, str(getattr(error, "message", error or "runtime operation failed"))
        return True, _mapping(value.data), ""
    if isinstance(value, Mapping) and value.get("ok") is False:
        return False, {}, str(value.get("error") or "runtime operation failed")
    return True, _mapping(value), ""


def _default_output_verifier(
    path: Path,
    output: Mapping[str, Any],
    requirements: tuple[str, ...],
) -> Mapping[str, Any] | None:
    media_type = str(output.get("media_type") or output.get("mime_type") or "").lower()
    declared_kind = media_type.split("/", 1)[0] if "/" in media_type else ""
    media_requirements = set(requirements) & {"decode", "audio", "video", "image"}
    if declared_kind in {"audio", "video", "image"}:
        media_requirements.add(declared_kind)
    if not media_requirements:
        return None

    try:
        probe = ffprobe_metadata_strict(path)
    except MediaProbeError as exc:
        raise OutputCustodyError(f"output media decode failed: {exc}") from exc
    if not probe.has_video_stream and not probe.has_audio_stream:
        raise OutputCustodyError("output media decode produced no audio or video stream")
    if "audio" in media_requirements and not probe.has_audio_stream:
        raise OutputCustodyError("output does not contain the required audio stream")
    if "video" in media_requirements and not probe.has_video_stream:
        raise OutputCustodyError("output does not contain the required video stream")
    if "image" in media_requirements:
        image_formats = {"image2", "png_pipe", "jpeg_pipe", "gif", "webp_pipe"}
        formats = {
            item.strip().lower()
            for item in str(probe.format_name or "").split(",")
            if item.strip()
        }
        if not probe.has_video_stream or not formats.intersection(image_formats):
            raise OutputCustodyError("output is not a decodable image")

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise OutputCustodyError("output media decode failed: ffmpeg is not available on PATH")
    decode_streams: list[tuple[str, str]] = []
    if probe.has_video_stream and (
        "decode" in media_requirements
        or "video" in media_requirements
        or "image" in media_requirements
    ):
        decode_streams.append(("video", "0:v:0"))
    if probe.has_audio_stream and (
        "decode" in media_requirements or "audio" in media_requirements
    ):
        decode_streams.append(("audio", "0:a:0"))
    if not decode_streams:
        raise OutputCustodyError("output media decode selected no required stream")
    for stream_kind, selector in decode_streams:
        command = [
            ffmpeg,
            "-v",
            "error",
            "-nostdin",
            "-i",
            str(path),
            "-map",
            selector,
        ]
        if stream_kind == "video":
            command.extend(["-frames:v", "1"])
        else:
            command.extend(["-t", "0.25"])
        command.extend(["-f", "null", "-"])
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OutputCustodyError(
                f"output {stream_kind} decode failed: {exc}"
            ) from exc
        if completed.returncode != 0:
            diagnostic = str(completed.stderr or completed.stdout or "").strip()
            suffix = f": {diagnostic}" if diagnostic else ""
            raise OutputCustodyError(
                f"output {stream_kind} decode failed with exit {completed.returncode}{suffix}"
            )
    return {
        "decoder": "ffmpeg",
        "probe": "ffprobe",
        "format": probe.format_name,
        "has_video": probe.has_video_stream,
        "has_audio": probe.has_audio_stream,
        "decoded_streams": [kind for kind, _selector in decode_streams],
    }


def verify_output_custody(
    output_root: str | Path,
    outputs: list[Mapping[str, Any]],
    *,
    requirements: tuple[str, ...] = (),
    verifier: OutputVerifier | None = None,
) -> list[dict[str, Any]]:
    """Verify staged outputs before any Runtime settlement is attempted."""

    normalized_requirements = tuple(str(item).strip().lower() for item in requirements)
    unsupported = sorted(set(normalized_requirements) - _SUPPORTED_OUTPUT_REQUIREMENTS)
    if unsupported:
        raise OutputCustodyError(
            "unsupported output requirements: " + ", ".join(unsupported)
        )
    output_verifier = verifier or _default_output_verifier
    root = Path(output_root).expanduser().resolve()
    if not root.is_dir():
        raise OutputCustodyError("output custody root is not a directory")
    if not isinstance(outputs, list) or not outputs:
        raise OutputCustodyError("execution produced no declared outputs")
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(outputs):
        if not isinstance(raw, Mapping):
            raise OutputCustodyError(f"output {index} is not an object")
        raw_path = raw.get("path")
        if not isinstance(raw_path, str) or not raw_path or Path(raw_path).is_absolute() or ".." in Path(raw_path).parts:
            raise OutputCustodyError(f"output {index} has an unsafe path")
        path = (root / raw_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise OutputCustodyError(f"output {index} escapes custody root") from exc
        if not path.is_file() or path.is_symlink():
            raise OutputCustodyError(f"output {index} is not a regular file")
        data = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        declared = raw.get("content_hash") or raw.get("digest")
        if declared != digest:
            raise OutputCustodyError(f"output {index} hash mismatch")
        declared_size = raw.get("bytes", raw.get("size"))
        if declared_size is not None and declared_size != len(data):
            raise OutputCustodyError(f"output {index} size mismatch")
        if raw_path in seen:
            raise OutputCustodyError(f"output {index} repeats a filename")
        seen.add(raw_path)
        try:
            evidence = output_verifier(path, raw, normalized_requirements)
        except OutputCustodyError:
            raise
        except Exception as exc:  # noqa: BLE001 - injectable verification boundary
            raise OutputCustodyError(f"output {index} verification failed: {exc}") from exc
        if evidence is not None and not isinstance(evidence, Mapping):
            raise OutputCustodyError(
                f"output {index} verifier returned invalid evidence"
            )
        verified_output = {**dict(raw), "content_hash": digest, "bytes": len(data)}
        verified_output.pop("decoded", None)
        if evidence:
            verified_output["verification"] = dict(evidence)
        verified.append(verified_output)
    return verified


class ReconcilerRuntime(Protocol):
    def create(self, **kwargs: Any) -> Any: ...

    def claim(self, **kwargs: Any) -> Any: ...

    def settle(self, *args: Any, **kwargs: Any) -> Any: ...

    def fail(self, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class ReconcileResult:
    status: str
    phase: str
    task_id: str | None = None
    run_id: str | None = None
    attempt_id: str | None = None
    error: str | None = None
    receipts: tuple[Mapping[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "phase": self.phase,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "error": self.error,
            "receipts": [dict(item) for item in self.receipts],
        }


@dataclass
class ExecutionReconciler:
    runtime: ReconcilerRuntime
    target: TargetAdapter
    clock: Callable[[], float] = time.monotonic
    output_verifier: OutputVerifier | None = None
    _receipts: list[Mapping[str, Any]] = field(default_factory=list, init=False)

    def _receipt(self, phase: str, *, status: str, **extra: Any) -> None:
        self._receipts.append({"phase": phase, "status": status, **extra})

    def _result(
        self,
        status: str,
        phase: str,
        *,
        task_id: str | None = None,
        run_id: str | None = None,
        attempt_id: str | None = None,
        error: str | None = None,
    ) -> ReconcileResult:
        return ReconcileResult(
            status=status,
            phase=phase,
            task_id=task_id,
            run_id=run_id,
            attempt_id=attempt_id,
            error=error,
            receipts=tuple(self._receipts),
        )

    def _fail_claim(self, claim: Mapping[str, Any], message: str, *, retryable: bool) -> bool:
        try:
            raw = self.runtime.fail(
                str(claim["task_id"]),
                str(claim["lease_id"]),
                message,
                retryable=retryable,
                attempt_id=str(claim["attempt_id"]),
                fence=int(claim["fence"]),
                runtime_epoch=int(claim["runtime_epoch"]),
            )
            ok, _data, _error = _ok_data(raw)
            return ok
        except Exception:
            return False

    @staticmethod
    def _deadline_seconds(
        request: Mapping[str, Any], field: str
    ) -> int | None:
        limits = request.get("limits")
        value = limits.get(field) if isinstance(limits, Mapping) else None
        return int(value) if isinstance(value, int) and not isinstance(value, bool) else None

    def _expired(
        self, request: Mapping[str, Any], field: str, started_at: float
    ) -> bool:
        limit = self._deadline_seconds(request, field)
        return limit is not None and self.clock() - started_at >= limit

    def _read_task(
        self, task_id: str
    ) -> tuple[bool, dict[str, Any] | None, str | None]:
        """Read the durable task record through whichever Runtime facade exists."""

        reader = next(
            (
                getattr(self.runtime, name)
                for name in ("get_task", "show", "task", "get")
                if callable(getattr(self.runtime, name, None))
            ),
            None,
        )
        if reader is None:
            return False, None, None
        try:
            ok, task, error = _ok_data(reader(task_id))
        except Exception as exc:  # noqa: BLE001 - durable read boundary
            return True, None, str(exc)
        if not ok:
            return True, None, error
        if not task:
            return True, None, "runtime task lookup returned no task"
        return True, task, None

    def _validate_task_identity(
        self,
        task: Mapping[str, Any],
        *,
        task_id: str,
        capability: str,
        idempotency_key: str,
        contract_digest: str,
    ) -> str | None:
        durable_task_id = str(task.get("task_id") or task.get("id") or "")
        if durable_task_id and durable_task_id != task_id:
            return "durable task identity does not match admission"
        durable_key = task.get("idempotency_key")
        if durable_key is not None and str(durable_key) != idempotency_key:
            return "durable task idempotency key does not match admission"
        durable_capability = task.get("capability_id")
        if durable_capability is not None and str(durable_capability) != capability:
            return "durable task capability does not match admission"
        task_spec = task.get("spec")
        stored_request = (
            task_spec.get("execution_request")
            if isinstance(task_spec, Mapping)
            else None
        )
        if stored_request is not None:
            try:
                stored_normalized = normalize_execution_request(stored_request)
            except Exception as exc:  # noqa: BLE001 - corrupt durable authority
                return f"durable task execution request is invalid: {exc}"
            if stored_normalized is None or _digest(stored_normalized) != contract_digest:
                return "durable task execution request does not match admission"
        return None

    def _terminal_result(
        self,
        task: Mapping[str, Any],
        *,
        phase: str,
        task_id: str,
        run_id: str | None,
    ) -> ReconcileResult | None:
        state = str(task.get("state") or task.get("status") or "").strip().lower()
        attempt_id = str(task.get("attempt_id") or "") or None
        if state in {"succeeded", "complete", "completed"}:
            result = task.get("result")
            if not isinstance(result, Mapping):
                message = "terminal task has no recoverable result"
                self._receipt(phase, status="undetermined", error=message, durable=True)
                return self._result(
                    "undetermined",
                    phase,
                    task_id=task_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    error=message,
                )
            self._receipt(
                phase,
                status="complete",
                durable=True,
                task_state=state,
                result_digest=_digest(result),
            )
            return self._result(
                "complete",
                phase,
                task_id=task_id,
                run_id=run_id,
                attempt_id=attempt_id,
            )
        if state in {"failed", "cancelled", "canceled"}:
            message = f"durable task is terminal: {state}"
            self._receipt(phase, status="failed", durable=True, task_state=state)
            return self._result(
                "failed",
                phase,
                task_id=task_id,
                run_id=run_id,
                attempt_id=attempt_id,
                error=message,
            )
        return None

    def run(
        self,
        *,
        contract: Mapping[str, Any],
        project_id: str | None,
        capability: str,
        spec: Mapping[str, Any],
        executor_id: str,
        execute: Callable[[Mapping[str, Any], TargetObservation], Mapping[str, Any]],
        input_manifest: list[str] | None = None,
        idempotency_key: str,
    ) -> ReconcileResult:
        self._receipts.clear()
        queue_started_at = self.clock()
        try:
            normalized = normalize_execution_request(contract)
            if normalized is None:
                raise ExecutionRequestError("execution contract is required")
            manifest = merge_execution_input_manifest(normalized, input_manifest)
        except Exception as exc:  # noqa: BLE001 - named validation phase
            self._receipt("contract", status="failed", error=str(exc))
            return self._result("failed", "contract", error=str(exc))
        contract_digest = _digest(normalized)
        self._receipt("contract", status="verified", contract_digest=contract_digest, input_manifest=manifest)

        try:
            requested_target = normalized.get("target")
            if not isinstance(requested_target, Mapping):
                raise TargetAdapterError("execution request has no target identity")
            self.target.assert_request_target(requested_target)
            target_receipt = self.target.attach_or_start_owned()
            observation = target_receipt.observation
        except TargetAdapterError as exc:
            self._receipt("target_preflight", status="failed", error=str(exc))
            return self._result("retryable", "target_preflight", error=str(exc))
        if self._expired(normalized, "max_queue_seconds", queue_started_at):
            self._receipt("target_preflight", status="retryable", error="queue deadline exceeded")
            return self._result("retryable", "target_preflight", error="queue deadline exceeded")
        self._receipt("target_preflight", status="verified", **target_receipt.to_dict())

        try:
            admitted_raw = self.runtime.create(
                project_id=project_id,
                capability=capability,
                spec=dict(spec),
                input_manifest=manifest,
                idempotency_key=idempotency_key,
                execution_request=normalized,
            )
            admitted_ok, admitted, admitted_error = _ok_data(admitted_raw)
        except Exception as exc:  # noqa: BLE001 - runtime admission boundary
            admitted_ok, admitted, admitted_error = False, {}, str(exc)
        if not admitted_ok:
            self._receipt("admission", status="failed", error=admitted_error)
            return self._result("failed", "admission", error=admitted_error)
        task_id = str(admitted.get("task_id") or admitted.get("id") or "") or None
        run_id = str(admitted.get("run_id") or "") or None
        if task_id is None:
            self._receipt("admission", status="failed", error="runtime returned no task_id")
            return self._result("failed", "admission", error="runtime returned no task_id")
        self._receipt("admission", status="verified", task_id=task_id, run_id=run_id)
        lookup_available, durable_task, lookup_error = self._read_task(task_id)
        if lookup_available:
            if durable_task is None:
                message = f"durable task lookup failed: {lookup_error or 'unknown error'}"
                self._receipt("recovery", status="undetermined", error=message)
                return self._result(
                    "undetermined",
                    "recovery",
                    task_id=task_id,
                    run_id=run_id,
                    error=message,
                )
            identity_error = self._validate_task_identity(
                durable_task,
                task_id=task_id,
                capability=capability,
                idempotency_key=idempotency_key,
                contract_digest=contract_digest,
            )
            if identity_error is not None:
                self._receipt("recovery", status="undetermined", error=identity_error)
                return self._result(
                    "undetermined",
                    "recovery",
                    task_id=task_id,
                    run_id=run_id,
                    error=identity_error,
                )
            run_id = str(durable_task.get("run_id") or run_id or "") or None
            recovered = self._terminal_result(
                durable_task,
                phase="recovery",
                task_id=task_id,
                run_id=run_id,
            )
            if recovered is not None:
                return recovered
            durable_state = str(
                durable_task.get("state") or durable_task.get("status") or ""
            ).strip().lower()
            durable_attempt = durable_task.get("attempt_id")
            claimable_states = {"queued", "admitted", "pending", "created", "waiting"}
            if durable_attempt or durable_state not in claimable_states:
                message = (
                    "durable task is already in flight; refusing to replay execution"
                )
                self._receipt(
                    "recovery",
                    status="undetermined",
                    durable=True,
                    task_state=durable_state or "unknown",
                    attempt_id=str(durable_attempt) if durable_attempt else None,
                    error=message,
                )
                return self._result(
                    "undetermined",
                    "recovery",
                    task_id=task_id,
                    run_id=run_id,
                    attempt_id=str(durable_attempt) if durable_attempt else None,
                    error=message,
                )
            self._receipt(
                "recovery",
                status="pending",
                durable=True,
                task_state=str(
                    durable_task.get("state") or durable_task.get("status") or "unknown"
                ),
            )
        if self._expired(normalized, "max_queue_seconds", queue_started_at):
            self._receipt("admission", status="retryable", error="queue deadline exceeded")
            return self._result("retryable", "admission", task_id=task_id, run_id=run_id, error="queue deadline exceeded")

        try:
            claim_raw = self.runtime.claim(
                executor_id=executor_id,
                capability_ids=[capability],
                idempotency_key=f"claim-{idempotency_key}",
                runtime_epoch=observation.runtime_epoch,
                target=normalized["target"],
            )
            claim_ok, claim, claim_error = _ok_data(claim_raw)
        except Exception as exc:  # noqa: BLE001 - claim boundary
            claim_ok, claim, claim_error = False, {}, str(exc)
        if not claim_ok:
            self._receipt("claim", status="failed", error=claim_error)
            return self._result("retryable", "claim", task_id=task_id, run_id=run_id, error=claim_error)
        if not claim.get("attempt_id"):
            self._receipt("claim", status="waiting", task_id=task_id)
            return self._result("waiting", "claim", task_id=task_id, run_id=run_id)
        attempt_id = str(claim.get("attempt_id"))
        claimed_task_id = str(claim.get("task_id") or "")
        if claimed_task_id != task_id:
            message = (
                "claim task identity does not match the admitted task: "
                f"expected {task_id!r}, received {claimed_task_id or '<missing>'!r}"
            )
            self._receipt("claim", status="undetermined", error=message)
            return self._result(
                "undetermined",
                "claim",
                task_id=task_id,
                run_id=run_id,
                attempt_id=attempt_id,
                error=message,
            )
        claim_identity_error = self._validate_task_identity(
            claim,
            task_id=task_id,
            capability=capability,
            idempotency_key=idempotency_key,
            contract_digest=contract_digest,
        )
        if claim_identity_error is not None:
            self._receipt("claim", status="undetermined", error=claim_identity_error)
            return self._result(
                "undetermined",
                "claim",
                task_id=task_id,
                run_id=run_id,
                attempt_id=attempt_id,
                error=claim_identity_error,
            )
        required_claim = ("lease_id", "fence", "runtime_epoch")
        if any(field not in claim for field in required_claim):
            self._receipt("claim", status="failed", error="claim returned incomplete fence")
            return self._result("undetermined", "claim", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error="claim returned incomplete fence")
        claim_epoch = int(claim["runtime_epoch"])
        if claim_epoch != observation.runtime_epoch:
            self._receipt("claim", status="undetermined", error="target/runtime epoch changed before execution")
            self._fail_claim(claim, "target/runtime epoch changed before execution", retryable=False)
            return self._result("undetermined", "claim", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error="target/runtime epoch changed before execution")
        claim_started_at = self.clock()
        runtime_deadline_error = "runtime deadline exceeded"
        if self._expired(normalized, "max_runtime_seconds", claim_started_at):
            failed = self._fail_claim(claim, runtime_deadline_error, retryable=False)
            status = "failed" if failed else "undetermined"
            self._receipt("claim", status=status, error=runtime_deadline_error, failure_recorded=failed)
            return self._result(status, "claim", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error=runtime_deadline_error)
        self._receipt("claim", status="verified", attempt_id=attempt_id, runtime_epoch=claim_epoch, fence=int(claim["fence"]))

        runtime_limit = self._deadline_seconds(normalized, "max_runtime_seconds")
        execution_error: BaseException | None = None
        result: Mapping[str, Any] | None = None
        if runtime_limit is None:
            try:
                result = execute(claim, observation)
            except BaseException as exc:  # noqa: BLE001 - preserve callback outcome
                execution_error = exc
        else:
            callback_result: dict[str, Any] = {}

            def invoke_callback() -> None:
                try:
                    callback_result["value"] = execute(claim, observation)
                except BaseException as exc:  # noqa: BLE001 - cross-thread handoff
                    callback_result["error"] = exc

            worker = threading.Thread(
                target=invoke_callback,
                name=f"astrid-reconcile-{attempt_id}",
                daemon=True,
            )
            worker.start()
            worker.join(max(0.0, float(runtime_limit)))
            if worker.is_alive():
                message = "runtime deadline exceeded while executor remained active"
                failed = self._fail_claim(claim, message, retryable=False)
                status = "failed" if failed else "undetermined"
                self._receipt(
                    "execution",
                    status=status,
                    error=message,
                    failure_recorded=failed,
                    callback_still_running=True,
                )
                return self._result(
                    status,
                    "execution",
                    task_id=task_id,
                    run_id=run_id,
                    attempt_id=attempt_id,
                    error=message,
                )
            execution_error = callback_result.get("error")
            result = callback_result.get("value")
        try:
            if execution_error is not None:
                raise execution_error
            if not isinstance(result, Mapping):
                raise ReconcilerError("executor returned no result mapping")
        except ExecutionUncertain as exc:
            self._receipt("execution", status="undetermined", error=str(exc))
            return self._result("undetermined", "execution", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error=str(exc))
        except Exception as exc:  # noqa: BLE001 - post-claim fenced failure
            message = str(exc)
            failed = self._fail_claim(claim, message, retryable=True)
            status = "retryable" if failed else "undetermined"
            self._receipt("execution", status=status, error=message, failure_recorded=failed)
            return self._result(status, "execution", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error=message)
        if self._expired(normalized, "max_runtime_seconds", claim_started_at):
            failed = self._fail_claim(claim, runtime_deadline_error, retryable=False)
            status = "failed" if failed else "undetermined"
            self._receipt("execution", status=status, error=runtime_deadline_error, failure_recorded=failed)
            return self._result(status, "execution", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error=runtime_deadline_error)
        self._receipt("execution", status="observed", submission=result.get("submission"), result_digest=_digest(result))

        collection_started_at = self.clock()
        try:
            verified_outputs = verify_output_custody(
                observation.output_root,
                list(result.get("outputs") or []),
                requirements=tuple(
                    (normalized.get("checks") or {}).get("outputs", [])
                    if isinstance(normalized.get("checks"), Mapping)
                    else ()
                ),
                verifier=self.output_verifier,
            )
            current = self.target.revalidate(observation)  # type: ignore[attr-defined]
            if self._expired(normalized, "collection_seconds", collection_started_at):
                raise OutputCustodyError("collection deadline exceeded")
        except (OutputCustodyError, TargetAdapterError) as exc:
            message = str(exc)
            failed = self._fail_claim(claim, message, retryable=False)
            status = (
                "undetermined"
                if isinstance(exc, TargetAdapterError)
                else ("failed" if failed else "undetermined")
            )
            self._receipt("delivery", status=status, error=message, failure_recorded=failed)
            return self._result(status, "delivery", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error=message)
        self._receipt("delivery", status="verified", output_count=len(verified_outputs), incarnation=current.identity_key)

        if self._expired(normalized, "max_runtime_seconds", claim_started_at):
            failed = self._fail_claim(claim, runtime_deadline_error, retryable=False)
            status = "failed" if failed else "undetermined"
            self._receipt("delivery", status=status, error=runtime_deadline_error, failure_recorded=failed)
            return self._result(status, "delivery", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error=runtime_deadline_error)

        try:
            settled_raw = self.runtime.settle(
                attempt_id,
                lease_id=str(claim["lease_id"]),
                fence=int(claim["fence"]),
                outputs=verified_outputs,
                idempotency_key=f"settle-{attempt_id}-{int(claim['fence'])}",
                runtime_epoch=claim_epoch,
            )
            settled_ok, _settled, settled_error = _ok_data(settled_raw)
        except Exception as exc:  # noqa: BLE001 - uncertain delivery boundary
            settled_ok, settled_error = False, str(exc)
        if not settled_ok:
            lookup_available, durable_task, lookup_error = self._read_task(task_id)
            if lookup_available and durable_task is not None:
                identity_error = self._validate_task_identity(
                    durable_task,
                    task_id=task_id,
                    capability=capability,
                    idempotency_key=idempotency_key,
                    contract_digest=contract_digest,
                )
                if identity_error is None:
                    recovered = self._terminal_result(
                        durable_task,
                        phase="settlement_recovery",
                        task_id=task_id,
                        run_id=run_id,
                    )
                    if recovered is not None:
                        return recovered
                else:
                    lookup_error = identity_error
            self._receipt("settlement", status="undetermined", error=settled_error)
            error = settled_error
            if lookup_available and lookup_error:
                error = f"{settled_error}; durable recovery failed: {lookup_error}"
            return self._result("undetermined", "settlement", task_id=task_id, run_id=run_id, attempt_id=attempt_id, error=error)
        self._receipt("settlement", status="complete", output_count=len(verified_outputs))
        return self._result("complete", "settlement", task_id=task_id, run_id=run_id, attempt_id=attempt_id)


__all__ = [
    "ExecutionReconciler",
    "ExecutionUncertain",
    "OutputCustodyError",
    "ReconcileResult",
    "ReconcilerError",
    "ReconcilerRuntime",
    "verify_output_custody",
]
