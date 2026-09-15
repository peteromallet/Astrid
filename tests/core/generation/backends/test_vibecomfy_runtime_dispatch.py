"""Focused tests for the canonical local VibeComfy runtime boundary."""

from __future__ import annotations

import sys
import types

from astrid.core.generation.backends.vibecomfy import VibeComfyBackend


def test_real_vibe_workflow_crosses_compiled_bundle_boundary(monkeypatch) -> None:
    class FakeWorkflow:
        pass

    class FakeBundle:
        def require_canonical_authority(self, purpose: str) -> None:
            assert purpose == "runtime execution"

        def compile(self) -> object:
            return "approved-projection"

    bundle = FakeBundle()
    calls: list[tuple[object, ...]] = []

    vibecomfy = types.ModuleType("vibecomfy")
    vibecomfy.__path__ = []  # type: ignore[attr-defined]
    workflow_module = types.ModuleType("vibecomfy.workflow")
    workflow_module.VibeWorkflow = FakeWorkflow  # type: ignore[attr-defined]
    workflow_bundle_module = types.ModuleType("vibecomfy.workflow_bundle")
    workflow_bundle_module.load_bundle = lambda value: bundle  # type: ignore[attr-defined]
    runtime = types.ModuleType("vibecomfy.runtime")
    runtime.__path__ = []  # type: ignore[attr-defined]
    runtime_run = types.ModuleType("vibecomfy.runtime.run")

    def run_sync(*args):
        calls.append(args)
        return "runtime-result"

    runtime_run.run_sync = run_sync  # type: ignore[attr-defined]
    for name, module in {
        "vibecomfy": vibecomfy,
        "vibecomfy.workflow": workflow_module,
        "vibecomfy.workflow_bundle": workflow_bundle_module,
        "vibecomfy.runtime": runtime,
        "vibecomfy.runtime.run": runtime_run,
    }.items():
        monkeypatch.setitem(sys.modules, name, module)

    result = VibeComfyBackend()._run_workflow(FakeWorkflow())

    assert result == "runtime-result"
    assert calls == [("approved-projection", bundle)]
