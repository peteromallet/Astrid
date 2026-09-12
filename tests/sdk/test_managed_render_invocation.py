from __future__ import annotations

from types import SimpleNamespace

from astrid.sdk import invocation
import astrid.core.rendering.storage as storage_module


def test_managed_render_snapshot_is_forwarded_to_runtime_task(monkeypatch) -> None:
    """The post-preflight snapshot must reach Runtime admission."""

    capability = SimpleNamespace(
        id="rendering.render",
        capability_type="executor",
        native_kind="built_in",
        inputs=(),
    )
    executor_definition = SimpleNamespace(to_dict=lambda: {"id": "rendering.render"})
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **_: ({"rendering.render": executor_definition}, None, None),
        get_capability=lambda *_, **__: capability,
    )
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)

    snapshot = {
        "timeline_id": "timeline-1",
        "project_id": "project-1",
        "config_version": 2,
        "config": {"clips": []},
        "registry": {"assets": {}},
    }
    prepared = {
        "timeline_ref": "timeline-1",
        "timeline_snapshot": snapshot,
        "timeline_authority": {"timeline_id": "timeline-1", "config_version": 2},
    }
    monkeypatch.setattr(
        invocation,
        "_prepare_managed_render_inputs",
        lambda inputs, **_: (prepared, {"timeline_id": "timeline-1"}),
    )

    monkeypatch.setattr(storage_module, "managed_object_sizes", lambda *_: {})
    monkeypatch.setattr(storage_module, "used_effect_asset_sizes", lambda *_: {})
    monkeypatch.setattr(
        storage_module,
        "estimate_managed_render_storage",
        lambda **_: {"estimated_scratch_bytes": 0, "estimated_output_bytes": 0},
    )

    captured: dict[str, object] = {}

    def fake_kernel(capability, **kwargs):
        captured.update(kwargs)
        return "run-1", "task-1", "attempt-1", None, {"ok": True}, True, None

    monkeypatch.setattr(invocation, "_kernel_invoke", fake_kernel)

    client = SimpleNamespace(
        media=SimpleNamespace(list=lambda *_args, **_kwargs: [[{"digest": "sha256:" + "a" * 64, "size": 1}], None])
    )
    result = invocation.invoke(
        "rendering.render",
        kind="executor",
        project="project-1",
        inputs={"timeline_ref": "timeline-1"},
        client=client,
    )

    assert result.ok
    assert captured["inputs"] == prepared
