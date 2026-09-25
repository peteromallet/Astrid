from __future__ import annotations

import threading
from types import SimpleNamespace

from astrid.core.execution.generic_host import (
    ORCHESTRATION_RESOURCE_KEY,
    CapabilityRecord,
    GenericPackHost,
)


def _record(capability_id: str, capability_kind: str) -> CapabilityRecord:
    definition = SimpleNamespace(
        id=capability_id,
        metadata={"resource_keys": ["cpu"]} if capability_kind == "executor" else {},
        isolation=SimpleNamespace(network=False),
    )
    return CapabilityRecord(
        definition=definition,
        capability_digest=f"digest-{capability_id}",
        source_digest="source",
        source_root=SimpleNamespace(is_dir=lambda: True),
        ready=True,
        capability_kind=capability_kind,
    )


def test_nested_parent_and_child_use_distinct_bounded_lanes() -> None:
    host = GenericPackHost(pack_roots=[], max_concurrency=2)
    host._parallel_enabled = True
    parent_started = threading.Event()
    child_started = threading.Event()
    child_finished = threading.Event()
    calls: list[str] = []
    completed: set[str] = set()

    def claim_once(*, lane: str | None = None):
        assert lane is not None
        calls.append(lane)
        if lane in completed:
            return None
        if lane == "orchestration":
            parent_started.set()
            assert child_started.wait(1.0)
            assert child_finished.wait(1.0)
            completed.add(lane)
            return {"task_id": "parent", "lane": lane}
        assert lane == "executor"
        assert parent_started.wait(1.0)
        child_started.set()
        child_finished.set()
        completed.add(lane)
        return {"task_id": "child", "lane": lane}

    host.claim_once = claim_once  # type: ignore[method-assign]
    results = host.run(poll_seconds=0.01, max_tasks=2)

    assert {item["task_id"] for item in results} == {"parent", "child"}
    assert set(calls) == {"executor", "orchestration"}


def test_lane_attempt_roots_and_managed_sessions_are_isolated(tmp_path) -> None:
    host = GenericPackHost(
        pack_roots=[],
        max_concurrency=2,
        attempt_base=tmp_path / "attempts",
    )
    host._parallel_enabled = True

    host._set_lane("orchestration")
    parent_root = host._allocate_attempt_root("parent", "attempt-parent")
    host._set_lane("executor")
    child_root = host._allocate_attempt_root("child", "attempt-child")

    assert parent_root.parent != child_root.parent
    assert parent_root.parent.name == "orchestration"
    assert child_root.parent.name == "executor"
    assert (
        host._lanes["orchestration"].managed_tool_session
        is not host._lanes["executor"].managed_tool_session
    )
    assert (
        host._lanes["orchestration"].active_processes
        is not host._lanes["executor"].active_processes
    )


def test_orchestrator_reservation_is_distinct_from_executor_cpu() -> None:
    orchestrator = _record("h3_av.transform", "orchestrator")
    executor = _record("h3_av.prepare", "executor")

    assert orchestrator.resource_keys == (ORCHESTRATION_RESOURCE_KEY,)
    assert executor.resource_keys == ("cpu",)
