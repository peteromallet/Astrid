"""Bounded, redacted projection of the frozen Plan A C2 diagnostic contract."""

from __future__ import annotations

import inspect
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping

C2_SCHEMA_VERSION = 2
C2_CONTRACT_REVISION = "C2"
C2_CONTRACT_DIGEST = "sha256:ca251dfbcadc6fbc68a5404495f2f0fd42128c821ce47a3560d2952399278d37"
C2_DEADLINE_MS = 5000
C2_LIMITS = {"maxEvents": 200, "maxLogBytes": 65536, "maxBundleBytes": 1048576}
_CAPTURE_KEYS = {"events": "maxEvents", "logBytes": "maxLogBytes", "bundleBytes": "maxBundleBytes"}
_SENSITIVE_KEYS = re.compile(
    r"(?:credential|token|secret|password|prompt|environment|env|media|signed.?url|authorization|path|root)$",
    re.IGNORECASE,
)
_PRIVATE_STRING = re.compile(r"(?:/(?:private|Users|home|tmp|var)/|(?:^|[\s(])~[/\\]|(?:file|https?)://|(?:token|secret|password)=|Bearer\s)", re.IGNORECASE)

FACT_NAMES = (
    "workspace", "runtime", "computeWorker", "selectedCapability", "authorization",
    "taskState", "contact", "progress", "terminalResult", "providerExecution",
    "providerBilling", "optionalContributionAuth", "hostedSessionAndGrants",
)
PROBLEM_CODES = {
    "workspace_missing", "workspace_ambiguous", "workspace_identity_mismatch",
    "workspace_configured_runtime_not_ready", "runtime_unavailable", "runtime_identity_mismatch",
    "permission_limited", "active_work_requires_authorization", "capability_unavailable",
    "authorization_required", "provider_state_unknown", "observation_stale",
    "observation_timeout", "hosted_session_required", "contributor_link_unavailable",
}
FAILURE_BOUNDARIES = {
    "workspace-selection", "runtime-process-identity", "runtime-contact", "runtime-permission",
    "runtime-schema", "compute-readiness", "execution-authorization", "task-admission",
    "attempt-execution", "provider-observation", "diagnostic-observation",
}
# C2 action effects are frozen here from the contract's ``allowedEffects``.
# Command effects below are the exact ordered values from the authoritative
# C1 ``commands`` source named by C2; do not add locally invented effects.
C2_ALLOWED_EFFECTS = frozenset({
    "observe", "configure-install", "start-stop-local-service", "interrupt-work",
    "may-spend-money", "write-relocate-change-data", "share-diagnostics",
})
COMMAND_EFFECTS = {
    "setup-preview": ["observe"], "setup-check": ["observe"],
    "setup-apply": ["configure-install", "write-relocate-change-data", "start-stop-local-service"],
    "runtime-up": ["start-stop-local-service", "configure-install", "write-relocate-change-data"],
    "runtime-status": ["observe"], "doctor": ["observe"], "workspace-status": ["observe"],
    "auth-status": ["observe"], "auth-login": ["configure-install", "write-relocate-change-data"],
    "auth-logout": ["write-relocate-change-data"], "auth-revoke": ["write-relocate-change-data"],
}


def _timestamp(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _fact(*, observed: bool = False, value: Any = None, reason: str | None = "not-observed", observed_at: str | None = None) -> dict[str, Any]:
    return {
        "observed": observed,
        "value": value if observed else None,
        "observedAt": observed_at if observed else None,
        "unavailableReason": None if observed else reason,
    }


def _failure_from(exc: BaseException | None, data: Mapping[str, Any] | None = None) -> tuple[str, str]:
    payload = data or {}
    code = str(getattr(exc, "code", "") or payload.get("problem_code") or "")
    if code == "permission_limited":
        return code, "runtime-permission"
    if code == "workspace_identity_mismatch":
        return code, "workspace-selection"
    if code in {"workspace_missing", "workspace_ambiguous", "workspace_configured_runtime_not_ready"}:
        return code, "workspace-selection"
    if code in {"observation_timeout", "timeout"} or isinstance(exc, TimeoutError):
        return "observation_timeout", "diagnostic-observation"
    if code == "observation_stale":
        return code, "runtime-contact"
    if code in {"runtime_identity_mismatch"}:
        return code, "runtime-process-identity"
    if code in PROBLEM_CODES:
        return code, "runtime-contact"
    return "runtime_unavailable", "runtime-contact"


def validate_diagnostic(report: Mapping[str, Any]) -> list[str]:
    """Return contract violations without changing or repairing the report."""
    errors: list[str] = []
    required = {"schemaVersion", "contractRevision", "contractDigest", "mode", "collectedAt", "timing", "problemCode", "failureBoundary", "facts", "limits", "captured", "truncated", "nextActions", "actionsExecuted", "redacted"}
    if set(report) != required:
        errors.append("top-level keys must match C2 exactly")
    if report.get("schemaVersion") != C2_SCHEMA_VERSION or report.get("contractRevision") != C2_CONTRACT_REVISION or report.get("contractDigest") != C2_CONTRACT_DIGEST:
        errors.append("C2 identity is invalid")
    if report.get("mode") not in {"local", "shared"}:
        errors.append("mode must be local or shared")
    timing = report.get("timing")
    if not isinstance(timing, Mapping) or set(timing) != {"deadlineScope", "deadlineMs", "elapsedMs", "timedOut"}:
        errors.append("timing shape is invalid")
    elif timing.get("deadlineScope") != "total-including-all-helpers" or not isinstance(timing.get("deadlineMs"), int) or not 1 <= timing["deadlineMs"] <= C2_DEADLINE_MS or not isinstance(timing.get("elapsedMs"), int) or not 0 <= timing["elapsedMs"] <= timing["deadlineMs"] or not isinstance(timing.get("timedOut"), bool):
        errors.append("timing values are invalid")
    if (report.get("problemCode") is None) != (report.get("failureBoundary") is None):
        errors.append("problemCode and failureBoundary must be paired")
    if report.get("problemCode") is not None and (report.get("problemCode") not in PROBLEM_CODES or report.get("failureBoundary") not in FAILURE_BOUNDARIES):
        errors.append("failure values are invalid")
    facts = report.get("facts")
    if not isinstance(facts, Mapping) or set(facts) != set(FACT_NAMES):
        errors.append("facts must contain the frozen independent fact names")
    else:
        for name in FACT_NAMES:
            fact = facts[name]
            if not isinstance(fact, Mapping) or set(fact) != {"observed", "value", "observedAt", "unavailableReason"}:
                errors.append(f"fact {name} shape is invalid")
                continue
            if not isinstance(fact.get("observed"), bool):
                errors.append(f"fact {name} observed must be boolean")
            if fact.get("observed") is True:
                if fact.get("value") is None or isinstance(fact.get("value"), (Mapping, list, tuple)) or fact.get("observedAt") is None or fact.get("unavailableReason") is not None:
                    errors.append(f"observed fact {name} is incomplete")
            elif fact.get("value") is not None or fact.get("observedAt") is not None or not fact.get("unavailableReason"):
                errors.append(f"unobserved fact {name} must remain unknown")
    if report.get("mode") == "shared" and report.get("redacted") is not True:
        errors.append("shared diagnostics must be redacted")
    if report.get("mode") == "local" and report.get("redacted") is not False:
        errors.append("local diagnostics must not claim shared redaction")
    limits = report.get("limits")
    captured = report.get("captured")
    if not isinstance(limits, Mapping) or set(limits) != set(C2_LIMITS) or not isinstance(captured, Mapping) or set(captured) != set(_CAPTURE_KEYS):
        errors.append("limits/captured shape is invalid")
    else:
        for captured_key, limit_key in _CAPTURE_KEYS.items():
            maximum = C2_LIMITS[limit_key]
            if not isinstance(limits[limit_key], int) or not 0 <= limits[limit_key] <= maximum or not isinstance(captured[captured_key], int) or not 0 <= captured[captured_key] <= limits[limit_key]:
                errors.append(f"bounded field {captured_key} is invalid")
    if report.get("actionsExecuted") != []:
        errors.append("actionsExecuted must be empty")
    actions = report.get("nextActions")
    if not isinstance(actions, list):
        errors.append("nextActions must be a list")
    else:
        for action in actions:
            if not isinstance(action, Mapping) or set(action) != {"commandId", "arguments", "effects", "authorizationRequired", "executable"}:
                errors.append("next action shape is invalid")
                continue
            command = action.get("commandId")
            effects = action.get("effects")
            if command not in COMMAND_EFFECTS or effects != COMMAND_EFFECTS[command] or any(effect not in C2_ALLOWED_EFFECTS for effect in effects if isinstance(effects, list)) or not isinstance(action.get("arguments"), list) or not isinstance(action.get("authorizationRequired"), bool) or not isinstance(action.get("executable"), bool):
                errors.append("next action command/effects are invalid")
            if any("<redacted" in str(arg).lower() or "[redacted" in str(arg).lower() for arg in action.get("arguments", [])) and action.get("executable"):
                errors.append("redacted next action cannot be executable")
    return errors


def _redact_shared(value: Any, *, key: str = "") -> Any:
    """Replace private transport material with inert, non-executable markers."""
    if _SENSITIVE_KEYS.search(key):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {str(name): _redact_shared(item, key=str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [_redact_shared(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [_redact_shared(item, key=key) for item in value]
    if isinstance(value, str) and _PRIVATE_STRING.search(value):
        return "<redacted>"
    return value


def redact_for_shared(value: Any) -> Any:
    """Return a JSON-safe shared projection without private local material."""
    return _redact_shared(value)


def build_diagnostic(*, mode: str, facts: Mapping[str, Mapping[str, Any]], problem_code: str | None = None, failure_boundary: str | None = None, elapsed_ms: int = 0, timed_out: bool = False, next_actions: list[dict[str, Any]] | None = None, collected_at: str | None = None) -> dict[str, Any]:
    action_values = [dict(action) for action in (next_actions or [])]
    if mode == "shared":
        action_values = []
        for action in next_actions or []:
            safe_action = dict(_redact_shared(action))
            # A shared action is advice only. It may contain an inert marker and
            # must never be copy/paste executable across the shared boundary.
            safe_action["executable"] = False
            action_values.append(safe_action)
    report = {
        "schemaVersion": C2_SCHEMA_VERSION,
        "contractRevision": C2_CONTRACT_REVISION,
        "contractDigest": C2_CONTRACT_DIGEST,
        "mode": mode,
        "collectedAt": collected_at or _timestamp(),
        "timing": {"deadlineScope": "total-including-all-helpers", "deadlineMs": C2_DEADLINE_MS, "elapsedMs": max(0, min(C2_DEADLINE_MS, int(elapsed_ms))), "timedOut": bool(timed_out)},
        "problemCode": problem_code,
        "failureBoundary": failure_boundary,
        "facts": {name: dict(facts.get(name, _fact())) for name in FACT_NAMES},
        "limits": dict(C2_LIMITS),
        "captured": {"events": 0, "logBytes": 0, "bundleBytes": 0},
        "truncated": False,
        "nextActions": action_values,
        "actionsExecuted": [],
        "redacted": mode == "shared",
    }
    if mode == "shared":
        report["facts"] = {name: dict(_redact_shared(value)) for name, value in report["facts"].items()}
    violations = validate_diagnostic(report)
    if violations:
        raise ValueError("invalid C2 diagnostic: " + "; ".join(violations))
    return report


def _call_with_remaining(method: Callable[..., Any], *args: Any, timeout: float, **kwargs: Any) -> Any:
    """Pass a bound when supported, retaining compatibility with test fakes."""
    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "timeout" in parameters or any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters.values()):
        kwargs["timeout"] = timeout
    return method(*args, **kwargs)


def collect_diagnostic(runtime: Any, *, support_root: str, mode: str = "local", command: str = "status") -> tuple[dict[str, Any], Any | None, Any | None]:
    """Observe through the existing Runtime client and return C2 plus raw local results."""
    started = time.monotonic()
    facts = {name: _fact() for name in FACT_NAMES}
    problem_code: str | None = None
    failure_boundary: str | None = None
    workspace_result = None
    runtime_result = None
    observed_at = _timestamp()

    def remaining_seconds() -> float:
        remaining = C2_DEADLINE_MS / 1000 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("C2 diagnostic observation deadline exceeded")
        return remaining

    try:
        if command == "status":
            workspace_result = _call_with_remaining(runtime.inspect, support_root=support_root, timeout=remaining_seconds())
            if getattr(workspace_result, "ok", False):
                facts["workspace"] = _fact(observed=True, value="selected", observed_at=observed_at)
            else:
                problem_code, failure_boundary = _failure_from(None, getattr(workspace_result, "data", {}))
                facts["workspace"] = _fact(observed=True, value="unavailable", observed_at=observed_at)
        runtime_result = _call_with_remaining(runtime.observe, command, support_root=support_root, timeout=remaining_seconds())
        if getattr(runtime_result, "ok", False):
            facts["runtime"] = _fact(observed=True, value="ready", observed_at=observed_at)
            facts["contact"] = _fact(observed=True, value="fresh", observed_at=observed_at)
        else:
            if problem_code is None:
                problem_code, failure_boundary = _failure_from(None, getattr(runtime_result, "data", {}))
            facts["runtime"] = _fact(observed=True, value="unavailable", observed_at=observed_at)
            facts["contact"] = _fact(observed=True, value="unavailable", observed_at=observed_at)
    except BaseException as exc:  # boundary adapter must turn failures into bounded evidence
        problem_code, failure_boundary = _failure_from(exc, getattr(exc, "result", None))
        if isinstance(exc, TimeoutError) or problem_code == "observation_timeout":
            facts["contact"] = _fact(observed=True, value="unavailable", observed_at=observed_at)
    elapsed = int((time.monotonic() - started) * 1000)
    timed_out = elapsed >= C2_DEADLINE_MS
    if timed_out and problem_code is None:
        problem_code, failure_boundary = "observation_timeout", "diagnostic-observation"
    next_actions: list[dict[str, Any]] = []
    if problem_code:
        shared_args = ["--data-root", "<redacted:path>"] if mode == "shared" else []
        next_actions = [{
            "commandId": "runtime-up" if problem_code in {"runtime_unavailable", "observation_timeout"} else "workspace-status",
            "arguments": shared_args,
            "effects": COMMAND_EFFECTS["runtime-up"] if problem_code in {"runtime_unavailable", "observation_timeout"} else COMMAND_EFFECTS["workspace-status"],
            "authorizationRequired": problem_code in {"runtime_unavailable", "observation_timeout"},
            "executable": mode != "shared",
        }]
    return build_diagnostic(mode=mode, facts=facts, problem_code=problem_code, failure_boundary=failure_boundary, elapsed_ms=elapsed, timed_out=timed_out, next_actions=next_actions), workspace_result, runtime_result
