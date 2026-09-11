from __future__ import annotations

from types import SimpleNamespace

from astrid.sdk.invocation import _generation_publish_effect, _kernel_invoke


def _capability() -> SimpleNamespace:
    return SimpleNamespace(
        id="generation.generate_video",
        definition=SimpleNamespace(
            outputs=(
                SimpleNamespace(name="generated_videos", artifact_type="video/clip"),
                SimpleNamespace(name="video_manifest", artifact_type=None),
                SimpleNamespace(name="thumbnail", artifact_type="image"),
            )
        ),
    )


def test_effect_preserves_group_selector_order_and_schema_port() -> None:
    intent = {
        "version": 1,
        "modality": "video",
        "partial_success_policy": "allow",
        "groups": [
            {"group_key": "second", "selectors": [{"selector": "b", "ordinal": 7, "variant_key": "v7"}]},
            {"group_key": "first", "selectors": [{"selector": "a", "ordinal": 2, "variant_key": "v2"}]},
        ],
    }
    effect = _generation_publish_effect(_capability(), project="project-1", generation_intent=intent)
    assert effect == {
        "effect_type": "generation.publish_v1",
        "target_id": "project-1",
        "payload": {
            "version": 1,
            "modality": "video",
            "generation_type": "generation.generate_video",
            "metadata": {},
            "partial_success_policy": "allow",
            "groups": [
                {"group_key": "second", "selectors": [{"selector": "b", "ordinal": 7, "variant_key": "v7", "output_port": "generated_videos"}]},
                {"group_key": "first", "selectors": [{"selector": "a", "ordinal": 2, "variant_key": "v2", "output_port": "generated_videos"}]},
            ],
        },
    }


def test_kernel_admission_predeclares_typed_effect_and_omits_it_without_intent() -> None:
    calls = []

    class Tasks:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(ok=True, data={"run_id": "r", "task_id": "t", "attempt_id": "a"})

    client = SimpleNamespace(tasks=Tasks())
    intent = {
        "version": 1, "modality": "video", "partial_success_policy": "reject",
        "groups": [{"group_key": "g", "selectors": [{"selector": "s", "ordinal": 0, "variant_key": "v"}]}],
    }
    _kernel_invoke(_capability(), kind="executor", project="project-1", inputs={}, outputs={}, generation_intent=intent, _client=client)
    _kernel_invoke(_capability(), kind="executor", project="project-1", inputs={}, outputs={}, _client=client)
    assert calls[0]["settlement_effect"]["effect_type"] == "generation.publish_v1"
    assert calls[0]["settlement_effect"]["payload"]["groups"][0]["selectors"][0]["output_port"] == "generated_videos"
    assert "settlement_effect" not in calls[1]
