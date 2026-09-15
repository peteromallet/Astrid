from __future__ import annotations

import pytest

from astrid.core.execution.managed_tool_session import (
    CapabilityDescriptor,
    ManagedToolSession,
    SessionBinding,
    SessionCapacityError,
    StaleAdmissionError,
    UncertainCancellation,
)


class _Adapter:
    def __init__(self, *, fail_release: bool = False) -> None:
        self.events: list[tuple[str, str]] = []
        self.fail_release = fail_release

    def fence(self, *, reason: str) -> None:
        self.events.append(("fence", reason))

    def release(self, *, reason: str) -> dict[str, bool]:
        self.events.append(("release", reason))
        if self.fail_release:
            raise RuntimeError("release not observed")
        return {"ok": True, "released": True}


def _binding(suffix: str) -> SessionBinding:
    return SessionBinding(
        session_id=f"session-{suffix}",
        runtime_instance_id=f"runtime-{suffix}",
        process_birth_id=f"birth-{suffix}",
        endpoint=f"http://127.0.0.1:{8000 + len(suffix)}",
        source_digest=f"source-{suffix}",
        config_digest=f"config-{suffix}",
    )


def test_serial_admission_and_settlement_are_one_shot() -> None:
    manager = ManagedToolSession()
    adapter = _Adapter()
    envelope = manager.open(
        capability=CapabilityDescriptor("vibecomfy.run"),
        binding=_binding("a"),
        adapter=adapter,
    )
    token = manager.admit(capability_id="vibecomfy.run", invocation_id="task-a")
    assert envelope.schema_version == "astrid.managed-tool-session.v1"
    with pytest.raises(SessionCapacityError):
        manager.admit(capability_id="vibecomfy.run", invocation_id="task-b")
    evidence = {
        "cas": "sha256:output",
        "generation": token.generation,
        "binding_identity": list(token.binding_identity),
    }
    settled = manager.settle(token, result_evidence=evidence)
    assert settled.state == "settled"
    with pytest.raises(StaleAdmissionError):
        manager.settle(token, result_evidence=evidence)


def test_incompatible_binding_fences_and_releases_before_replacement() -> None:
    manager = ManagedToolSession()
    old_adapter = _Adapter()
    manager.open(
        capability=CapabilityDescriptor("vibecomfy.run"),
        binding=_binding("a"),
        adapter=old_adapter,
    )
    old_token = manager.admit(capability_id="vibecomfy.run", invocation_id="task-a")
    new_adapter = _Adapter()
    replacement = manager.open(
        capability=CapabilityDescriptor("vibecomfy.run"),
        binding=_binding("b"),
        adapter=new_adapter,
    )
    assert replacement.binding.session_id == "session-b"
    assert old_adapter.events == [
        ("fence", "capacity_replacement"),
        ("release", "capacity_replacement"),
    ]
    with pytest.raises(StaleAdmissionError):
        manager.settle(
            old_token,
            result_evidence={
                "cas": "sha256:stale",
                "generation": old_token.generation,
                "binding_identity": list(old_token.binding_identity),
            },
        )


def test_execution_identity_change_replaces_same_process_session() -> None:
    manager = ManagedToolSession()
    first = _binding("a")
    second = SessionBinding(
        session_id=first.session_id,
        runtime_instance_id=first.runtime_instance_id,
        process_birth_id=first.process_birth_id,
        endpoint=first.endpoint,
        source_digest=first.source_digest,
        config_digest=first.config_digest,
        execution_identity="model-b-template-b",
    )
    old_adapter = _Adapter()
    manager.open(
        capability=CapabilityDescriptor("vibecomfy.run"),
        binding=first,
        adapter=old_adapter,
    )
    replacement = manager.open(
        capability=CapabilityDescriptor("vibecomfy.run"),
        binding=second,
        adapter=_Adapter(),
    )
    assert replacement.binding.execution_identity == "model-b-template-b"
    assert old_adapter.events == [
        ("fence", "capacity_replacement"),
        ("release", "capacity_replacement"),
    ]


def test_uncertain_cancellation_fences_the_session() -> None:
    manager = ManagedToolSession()
    adapter = _Adapter()
    manager.open(
        capability=CapabilityDescriptor("checkout_server"),
        binding=_binding("a"),
        adapter=adapter,
    )
    token = manager.admit(capability_id="checkout_server", invocation_id="task-a")
    with pytest.raises(UncertainCancellation):
        manager.cancel(token, outcome="uncertain")
    assert manager.generation == 2
    with pytest.raises(StaleAdmissionError):
        manager.settle(
            token,
            result_evidence={
                "cas": "sha256:late",
                "generation": token.generation,
                "binding_identity": list(token.binding_identity),
            },
        )


def test_release_failure_keeps_the_slot_poisoned() -> None:
    manager = ManagedToolSession()
    adapter = _Adapter(fail_release=True)
    manager.open(
        capability=CapabilityDescriptor("checkout_server"),
        binding=_binding("a"),
        adapter=adapter,
    )
    with pytest.raises(SessionCapacityError):
        manager.open(
            capability=CapabilityDescriptor("other"),
            binding=_binding("b"),
            adapter=_Adapter(),
        )
    assert manager.active is False
    assert manager.occupied is True
    assert manager.generation == 2
