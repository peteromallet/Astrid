"""Focused I-08 gateway, C2 diagnostic, and public-surface checks."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

import pytest

from astrid.core.gateway import main
from astrid.core.gateway.diagnostics import (
    C2_DEADLINE_MS,
    build_diagnostic,
    collect_diagnostic,
    validate_diagnostic,
)
from astrid.runtime_cli import RuntimeResult


def _fact(value: object, *, observed: bool = True) -> dict[str, object]:
    if observed:
        return {
            "observed": True,
            "value": value,
            "observedAt": "2026-09-24T12:00:00Z",
            "unavailableReason": None,
        }
    return {
        "observed": False,
        "value": None,
        "observedAt": None,
        "unavailableReason": "fixture-not-observed",
    }


def _action() -> dict[str, object]:
    return {
        "commandId": "runtime-up",
        "arguments": ["--data-root", "/Users/private/runtime-data"],
        "effects": [
            "start-stop-local-service",
            "configure-install",
            "write-relocate-change-data",
        ],
        "authorizationRequired": True,
        "executable": True,
    }


def test_c2_healthy_pairing_limits_and_local_shared_redaction() -> None:
    facts = {"workspace": _fact("/Users/private/runtime-data"), "runtime": _fact("ready")}
    local = build_diagnostic(mode="local", facts=facts, next_actions=[_action()])
    shared = build_diagnostic(mode="shared", facts=facts, next_actions=[_action()])

    assert validate_diagnostic(local) == []
    assert validate_diagnostic(shared) == []
    assert local["facts"]["workspace"]["value"] == "/Users/private/runtime-data"
    assert shared["facts"]["workspace"]["value"] == "<redacted>"
    assert shared["nextActions"][0]["arguments"][-1] == "<redacted>"
    assert shared["nextActions"][0]["executable"] is False
    assert shared["actionsExecuted"] == []
    assert shared["limits"] == {"maxEvents": 200, "maxLogBytes": 65536, "maxBundleBytes": 1048576}
    assert shared["captured"] == {"events": 0, "logBytes": 0, "bundleBytes": 0}


def test_c2_rejects_unpaired_failure_and_over_limit_capture() -> None:
    report = build_diagnostic(mode="local", facts={})
    report["problemCode"] = "runtime_unavailable"
    assert any("paired" in error for error in validate_diagnostic(report))

    bounded = build_diagnostic(mode="local", facts={})
    bounded["captured"]["events"] = bounded["limits"]["maxEvents"] + 1
    assert any("bounded field events" in error for error in validate_diagnostic(bounded))


@dataclass
class _Observer:
    inspect_data: dict[str, object] | None = None
    observe_data: dict[str, object] | None = None
    inspect_calls: int = 0
    observe_calls: int = 0

    def inspect(self, *, support_root: str, timeout: float = 5.0) -> RuntimeResult:
        self.inspect_calls += 1
        data = self.inspect_data or {"ok": True, "realm_id": "selected"}
        return RuntimeResult(("runtime", "workspace", "inspect"), 0 if data.get("ok") else 1, data)

    def observe(self, command: str, *, support_root: str, timeout: float = 5.0) -> RuntimeResult:
        self.observe_calls += 1
        data = self.observe_data or {"ok": True, "state": "ready"}
        return RuntimeResult(("runtime", command), 0 if data.get("ok") else 1, data)


@pytest.mark.parametrize(
    ("problem_code", "failure_boundary"),
    [
        ("runtime_unavailable", "runtime-contact"),
        ("observation_stale", "runtime-contact"),
        ("workspace_identity_mismatch", "workspace-selection"),
        ("permission_limited", "runtime-permission"),
    ],
)
def test_c2_bounded_failure_cases_have_paired_semantics(problem_code: str, failure_boundary: str) -> None:
    runtime = _Observer(
        inspect_data={"ok": False, "problem_code": problem_code},
        observe_data={"ok": False, "problem_code": problem_code},
    )
    report, _, _ = collect_diagnostic(runtime, support_root="/Users/private/support")

    assert validate_diagnostic(report) == []
    assert report["problemCode"] == problem_code
    assert report["failureBoundary"] == failure_boundary
    assert report["actionsExecuted"] == []
    assert report["timing"]["elapsedMs"] <= C2_DEADLINE_MS


def test_c2_timeout_is_paired_and_does_not_start_a_second_observer() -> None:
    class TimeoutObserver:
        def inspect(self, *, support_root: str, timeout: float = 5.0) -> RuntimeResult:
            return RuntimeResult(("runtime", "workspace", "inspect"), 0, {"ok": True})

        def observe(self, command: str, *, support_root: str, timeout: float = 5.0) -> RuntimeResult:
            raise TimeoutError("fixture timeout")

    runtime = TimeoutObserver()
    report, _, _ = collect_diagnostic(runtime, support_root="/Users/private/support")

    assert validate_diagnostic(report) == []
    assert report["problemCode"] == "observation_timeout"
    assert report["failureBoundary"] == "diagnostic-observation"
    assert report["timing"]["elapsedMs"] <= C2_DEADLINE_MS


def test_runtime_cli_timeout_maps_to_c2_timeout() -> None:
    from astrid.runtime_cli import RuntimeCLI

    def runner(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    report, _, _ = collect_diagnostic(
        RuntimeCLI(command=("banodoco-local",), runner=runner),
        support_root="/Users/private/support",
        command="doctor",
    )

    assert validate_diagnostic(report) == []
    assert report["problemCode"] == "observation_timeout"
    assert report["failureBoundary"] == "diagnostic-observation"


def test_total_deadline_stops_after_first_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    from astrid.core.gateway import diagnostics

    ticks = iter((0.0, 0.0, 5.001, 5.001))
    monkeypatch.setattr(diagnostics.time, "monotonic", lambda: next(ticks))
    runtime = _Observer()
    report, _, _ = collect_diagnostic(runtime, support_root="/Users/private/support")

    assert runtime.inspect_calls == 1
    assert runtime.observe_calls == 0
    assert report["problemCode"] == "observation_timeout"
    assert report["failureBoundary"] == "diagnostic-observation"


def test_public_help_auth_and_status_diagnostic_routes(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    assert main(["help"]) == 0
    help_text = capsys.readouterr().out
    assert "Family census (exactly seven families)" in help_text
    assert "Reserved workspace commands" in help_text
    assert "auth        [hivemind] login/status/logout/revoke" in help_text

    auth_calls: list[list[str]] = []
    monkeypatch.setattr("astrid.core.auth.run_auth", lambda argv: auth_calls.append(list(argv or [])) or 0)
    assert main(["auth", "status"]) == 0
    assert auth_calls == [["status"]]

    assert main(["tasks", "--help"]) == 0
    assert "follow" in capsys.readouterr().out

    observer = _Observer(
        inspect_data={"ok": False, "problem_code": "workspace_missing", "support_root": str(tmp_path / "private")},
        observe_data={"ok": False, "problem_code": "runtime_unavailable", "error": "/Users/private/runtime.log"},
    )
    monkeypatch.setattr("astrid.runtime_cli.RuntimeCLI", lambda: observer)
    monkeypatch.setattr("astrid.sdk.storage_root.resolve_runtime_data_root", lambda: tmp_path / "private")
    assert main(["status", "--diagnostic", "--shared"]) == 1
    diagnostic = json.loads(capsys.readouterr().out)
    assert validate_diagnostic(diagnostic) == []
    assert diagnostic["mode"] == "shared"
    assert "/Users/private" not in json.dumps(diagnostic)
    assert diagnostic["nextActions"][0]["executable"] is False


def test_public_doctor_permission_diagnostic_is_observer_only(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys) -> None:
    observer = _Observer(
        observe_data={"ok": False, "problem_code": "permission_limited", "error": "/Users/private/doctor.log"}
    )
    monkeypatch.setattr("astrid.runtime_cli.RuntimeCLI", lambda: observer)
    monkeypatch.setattr("astrid.sdk.storage_root.resolve_runtime_data_root", lambda: tmp_path / "private")

    assert main(["doctor", "--diagnostic", "--shared"]) == 1
    diagnostic = json.loads(capsys.readouterr().out)
    assert validate_diagnostic(diagnostic) == []
    assert diagnostic["problemCode"] == "permission_limited"
    assert diagnostic["failureBoundary"] == "runtime-permission"
    assert observer.observe_calls == 1
