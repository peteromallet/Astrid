"""Executable CPU C12 inventory for session-aware lifecycle evidence.

This is intentionally a CPU harness.  It exercises the manager-issued custody
envelope and the durable JSONL settlement boundary; it does not claim GPU,
Wan, VibeComfy, or provider acceptance.  The inventory is a tracked input so
the case count cannot be inferred from an old receipt or a test-count guess.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrid.core.execution.managed_tool_session import (
    CapabilityDescriptor,
    ManagedToolSession,
    SessionBinding,
    SessionCapacityError,
    StaleAdmissionError,
    UncertainCancellation,
)
from astrid.core.execution.persistent_supervisor import PersistentJsonlSupervisor


INVENTORY = Path(__file__).with_name("c12_cpu_case_inventory.json")


class _ObservedAdapter:
    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def observe(self, *, binding: SessionBinding) -> dict[str, object]:
        self.events.append({"kind": "observe", "session_id": binding.session_id})
        return {"ok": True, "session_id": binding.session_id}

    def cancel(self, *, reason: str) -> dict[str, object]:
        self.events.append({"kind": "cancel", "reason": reason})
        return {"ok": True, "cancelled": True}

    def fence(self, *, reason: str) -> None:
        self.events.append({"kind": "fence", "reason": reason})

    def release(self, *, reason: str) -> dict[str, object]:
        self.events.append({"kind": "release", "reason": reason})
        return {"ok": True, "released": True}


def _binding(*, incarnation: str, execution_identity: str = "model-a/template-a") -> SessionBinding:
    return SessionBinding(
        session_id="c12-session",
        runtime_instance_id="c12-runtime",
        process_birth_id=f"birth-{incarnation}",
        endpoint="http://127.0.0.1:8787",
        source_digest="sha256:" + "1" * 64,
        config_digest="sha256:" + "2" * 64,
        execution_identity=execution_identity,
    )


def _token_evidence(token, *, binding: SessionBinding | None = None) -> dict[str, object]:
    return {
        "cas": "sha256:" + "3" * 64,
        "generation": token.generation,
        "binding_identity": list((binding or _binding(incarnation="a")).identity_key),
    }


def _load_inventory() -> list[str]:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["gpu_claim"] is False
    assert payload["warm_reuse_expected"] is False
    cases = payload["cases"]
    assert isinstance(cases, list)
    assert all(isinstance(case, str) and case for case in cases)
    assert len(cases) == len(set(cases))
    assert set(payload["evidence_sources"]) == set(cases)
    assert all(
        isinstance(source, list) and source
        for source in payload["evidence_sources"].values()
    )
    return cases


def _manager_cases() -> set[str]:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))
    return {
        str(case)
        for case, sources in payload["evidence_sources"].items()
        if "manager" in sources
    }


def test_c12_cpu_inventory_is_frozen_and_complete() -> None:
    cases = _load_inventory()
    assert cases == [
        "cold_success",
        "cancel_confirmed",
        "cancel_uncertain_fences",
        "deadline_contained",
        "changed_identity",
        "restart_replaces_incarnation",
        "stale_fence_rejected",
        "cas_settlement_exactly_once",
        "cleanup_releases_owned_session",
    ]


def test_c12_cpu_session_aware_lifecycle_harness(tmp_path: Path) -> None:
    cases = _load_inventory()
    evidence: dict[str, dict[str, object]] = {}
    manager = ManagedToolSession(manager_id="c12-cpu-harness")
    adapter = _ObservedAdapter()
    binding_a = _binding(incarnation="a")
    opened = manager.open(
        capability=CapabilityDescriptor("c12.echo"),
        binding=binding_a,
        adapter=adapter,
    )
    assert opened.state == "cold"
    token = manager.admit(capability_id="c12.echo", invocation_id="cold-success")
    observed = manager.observe(binding_a)
    assert observed.state == "warm"
    settled = manager.settle(token, result_evidence=_token_evidence(token, binding=binding_a))
    assert settled.state == "settled"
    evidence["cold_success"] = {
        "generation": settled.generation,
        "custody_digest": settled.digest,
        "observed": any(event.get("kind") == "observe" for event in adapter.events),
    }
    assert evidence["cold_success"]["observed"] is True

    cancel_token = manager.admit(capability_id="c12.echo", invocation_id="cancel-confirmed")
    cancelled = manager.cancel(cancel_token, outcome="confirmed")
    assert cancelled.state == "cancelled"
    evidence["cancel_confirmed"] = {
        "generation": cancelled.generation,
        "adapter_cancel_observed": any(event["kind"] == "cancel" for event in adapter.events),
    }
    assert evidence["cancel_confirmed"]["adapter_cancel_observed"] is True

    uncertain_token = manager.admit(capability_id="c12.echo", invocation_id="cancel-uncertain")
    with pytest.raises(UncertainCancellation):
        manager.cancel(uncertain_token, outcome="uncertain")
    assert manager.active is False
    evidence["cancel_uncertain_fences"] = {
        "generation": manager.generation,
        "fence_observed": any(
            event.get("kind") == "fence" and event.get("reason") == "uncertain_cancellation"
            for event in adapter.events
        ),
    }

    binding_b = _binding(incarnation="b", execution_identity="model-b/template-b")
    replacement_adapter = _ObservedAdapter()
    replacement = manager.restart(binding=binding_b, adapter=replacement_adapter)
    assert replacement.state == "cold"
    evidence["restart_replaces_incarnation"] = {
        "generation": replacement.generation,
        "process_birth_id": replacement.binding.process_birth_id,
        "execution_identity": replacement.binding.execution_identity,
    }
    replacement_token = manager.admit(capability_id="c12.echo", invocation_id="changed-identity")
    binding_c = _binding(incarnation="b", execution_identity="model-c/template-c")
    changed_adapter = _ObservedAdapter()
    manager.open(
        capability=CapabilityDescriptor("c12.echo"),
        binding=binding_c,
        adapter=changed_adapter,
    )
    manager.observe(binding_c)
    assert any(event.get("kind") == "observe" for event in changed_adapter.events)
    with pytest.raises(StaleAdmissionError):
        manager.settle(
            replacement_token,
            result_evidence=_token_evidence(replacement_token, binding=binding_b),
        )
    changed_token = manager.admit(capability_id="c12.echo", invocation_id="changed-identity-new")
    changed = manager.settle(
        changed_token,
        result_evidence=_token_evidence(changed_token, binding=binding_c),
    )
    assert changed.binding.execution_identity == "model-c/template-c"
    evidence["changed_identity"] = {
        "generation": changed.generation,
        "execution_identity": changed.binding.execution_identity,
        "old_admission_rejected": True,
    }
    assert changed.binding.execution_identity == "model-c/template-c"

    stale_token = manager.admit(capability_id="c12.echo", invocation_id="stale-fence")
    manager.restart(binding=_binding(incarnation="c"), adapter=_ObservedAdapter())
    with pytest.raises(StaleAdmissionError):
        manager.settle(stale_token, result_evidence=_token_evidence(stale_token, binding=binding_b))
    evidence["stale_fence_rejected"] = {"rejected": True, "old_generation": stale_token.generation}
    assert evidence["stale_fence_rejected"]["rejected"] is True

    # The persistent supervisor is the independent durable observation for
    # exactly-once terminal handling. Duplicate and post-restart frames must
    # not publish a second terminal transition.
    state = tmp_path / "c12-supervisor.jsonl"
    failures: list[str] = []
    supervisor = PersistentJsonlSupervisor(
        state,
        launch=lambda _frame: None,
        complete=lambda frame: failures.append(str(frame["result"]["outputs"][0]["digest"])),
    )
    frame = {
        "op": "start",
        "task_id": "c12-task",
        "attempt_id": "c12-attempt",
        "lease_id": "c12-lease",
        "fence": 1,
        "task": {"id": "c12-task"},
    }
    supervisor.handle(frame)
    completion_frame = {
        **frame,
        "op": "complete",
        "result": {"outputs": [{"digest": "sha256:" + "4" * 64}]},
    }
    first = supervisor.handle(completion_frame)
    duplicate = supervisor.handle({**completion_frame, "result": {"outputs": []}})
    restarted = PersistentJsonlSupervisor(
        state,
        complete=lambda frame: failures.append(str(frame["result"]["outputs"][0]["digest"])),
    )
    after_restart = restarted.handle({**completion_frame, "result": {"outputs": []}})
    assert first["status"] == duplicate["status"] == after_restart["status"] == "completed"
    assert duplicate["duplicate"] is True
    assert after_restart["duplicate"] is True
    assert failures == ["sha256:" + "4" * 64]
    evidence["cas_settlement_exactly_once"] = {
        "terminal_status": first["status"],
        "duplicate_suppressed": duplicate["duplicate"],
        "terminal_callbacks": len(failures),
    }

    cleanup_adapter = _ObservedAdapter()
    manager.restart(binding=_binding(incarnation="cleanup"), adapter=cleanup_adapter)
    manager.close(reason="c12-cleanup")
    assert manager.active is False
    assert manager.occupied is False
    evidence["cleanup_releases_owned_session"] = {
        "manager_closed": True,
        "slot_released": True,
        "release_observed": any(event["kind"] == "release" for event in cleanup_adapter.events),
    }
    assert evidence["cleanup_releases_owned_session"]["release_observed"] is True

    assert set(evidence) == _manager_cases()
    assert all(evidence[case] for case in _manager_cases())
