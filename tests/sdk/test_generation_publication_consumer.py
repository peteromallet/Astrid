from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrid.core.execution.generic_host import GenericPackHost, HostError
from astrid.sdk.invocation import _generation_publish_effect, _kernel_invoke


def _capability() -> SimpleNamespace:
    outputs = (
        SimpleNamespace(name="generated_videos", type="file", artifact_type="video/clip"),
        SimpleNamespace(name="video_manifest", type="file", artifact_type=None),
        SimpleNamespace(name="thumbnail", type="file", artifact_type="image"),
    )
    return SimpleNamespace(
        id="generation.generate_video",
        outputs=outputs,
        definition={
            "outputs": [
                {"name": "generated_videos", "type": "file", "artifact_type": "video/clip"},
                {"name": "video_manifest", "type": "file", "artifact_type": None},
            ]
        },
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


def test_effect_resolves_each_real_sdk_modality_port_and_excludes_extras() -> None:
    for modality, port, artifact in (
        ("image", "generated_images", "image"),
        ("video", "generated_videos", "video/clip"),
        ("audio", "generated_audio", "audio"),
    ):
        capability = SimpleNamespace(
            id=f"generation.generate_{modality}",
            outputs=(
                SimpleNamespace(name=port, type="file", artifact_type=artifact),
                SimpleNamespace(name=f"{modality}_manifest", type="file", artifact_type=None),
                SimpleNamespace(name="auxiliary", type="file", artifact_type="application/json"),
            ),
            # This is the real SDK Capability shape: definition is a mapping.
            definition={"outputs": [{"name": "wrong", "type": "file", "artifact_type": artifact}]},
        )
        intent = {
            "version": 1,
            "modality": modality,
            "partial_success_policy": "allow",
            "groups": [{"group_key": "g", "selectors": [{"selector": "s", "ordinal": 0, "variant_key": "v"}]}],
        }
        effect = _generation_publish_effect(capability, project="project-1", generation_intent=intent)
        assert effect["payload"]["groups"][0]["selectors"][0]["output_port"] == port


def _host_record() -> SimpleNamespace:
    return SimpleNamespace(
        definition=SimpleNamespace(
            outputs=(
                SimpleNamespace(name="generated_videos", type="file", artifact_type="video/clip"),
                SimpleNamespace(name="video_manifest", type="file", artifact_type=None),
                SimpleNamespace(name="aux", type="file", artifact_type="application/json"),
            )
        )
    )


def _descriptor(root, name: str, value: bytes, ordinal: int, **metadata):
    path = root / f"{name}-{ordinal}.bin"
    path.write_bytes(value)
    import hashlib

    return {
        "name": name,
        "path": str(path),
        "ordinal": ordinal,
        "content_hash": "sha256:" + hashlib.sha256(value).hexdigest(),
        "bytes": len(value),
        "role": "result",
        "is_primary": ordinal == 0,
        "ordinal_explicit": True,
        **metadata,
    }


def _intent(policy: str = "reject", *, collision: bool = False):
    return {
        "version": 1,
        "modality": "video",
        "partial_success_policy": policy,
        "groups": [
            {"group_key": "left", "selectors": [{"selector": "left-0", "ordinal": 0, "variant_key": "left-v"}]},
            {"group_key": "right", "selectors": [{"selector": "right-1", "ordinal": 1 if not collision else 0, "variant_key": "right-v"}]},
        ],
    }


def test_host_binds_out_of_order_generated_outputs_by_ordinal_and_selector(tmp_path) -> None:
    intent = _intent()
    host = GenericPackHost.__new__(GenericPackHost)
    outputs = host._typed_outputs(
        _host_record(),
        [
            _descriptor(tmp_path, "generated_videos", b"right", 1, selector={"group_key": "right", "variant_key": "right-v"}, producer={"source": "p"}),
            _descriptor(tmp_path, "generated_videos", b"left", 0, selector={"group_key": "left", "variant_key": "left-v"}, provenance={"trace": "t"}),
            _descriptor(tmp_path, "video_manifest", b"manifest", 9, role="auxiliary"),
            _descriptor(tmp_path, "aux", b"aux", 3, role="auxiliary"),
        ],
        tmp_path,
        generation_intent=intent,
    )
    assert [(item["group_key"], item["variant_key"], item["selector"], item["ordinal"]) for item in outputs[:2]] == [
        ("right", "right-v", {"group_key": "right", "variant_key": "right-v"}, 1),
        ("left", "left-v", {"group_key": "left", "variant_key": "left-v"}, 0),
    ]
    assert outputs[0]["producer"] == {"source": "p"}
    assert outputs[1]["provenance"] == {"trace": "t"}
    assert "group_key" not in outputs[2]
    assert "output_port" not in outputs[3]


def test_host_generation_policy_zero_and_ambiguous_binding_fail_closed(tmp_path) -> None:
    host = GenericPackHost.__new__(GenericPackHost)
    one = _descriptor(tmp_path, "generated_videos", b"one", 0, selector={"group_key": "left", "variant_key": "left-v"})
    with pytest.raises(HostError, match="reject policy"):
        host._typed_outputs(_host_record(), [one], tmp_path, generation_intent=_intent("reject"))
    allowed = host._typed_outputs(_host_record(), [one], tmp_path, generation_intent=_intent("allow"))
    assert len(allowed) == 1 and allowed[0]["group_key"] == "left"
    with pytest.raises(HostError, match="no successful"):
        host._typed_outputs(_host_record(), [], tmp_path, generation_intent=_intent("allow"))

    collision = _descriptor(tmp_path, "generated_videos", b"collision", 0)
    with pytest.raises(HostError, match="unauthorized ambiguous"):
        host._typed_outputs(_host_record(), [collision], tmp_path, generation_intent=_intent("allow", collision=True))
    mismatch = _descriptor(tmp_path, "generated_videos", b"mismatch", 0, selector={"group_key": "right", "variant_key": "right-v"})
    with pytest.raises(HostError, match="no successful|unauthorized"):
        host._typed_outputs(_host_record(), [mismatch], tmp_path, generation_intent=_intent("allow"))
    string_selector = _descriptor(tmp_path, "generated_videos", b"string", 0, selector="left-0")
    with pytest.raises(HostError, match="must be an object"):
        host._typed_outputs(_host_record(), [string_selector], tmp_path, generation_intent=_intent("allow"))


def test_host_rejects_positional_ordinal_injected_by_manifest_harvest(tmp_path) -> None:
    host = GenericPackHost.__new__(GenericPackHost)
    positional = _descriptor(
        tmp_path,
        "generated_videos",
        b"positional",
        0,
        selector={"group_key": "left", "variant_key": "left-v"},
        ordinal_explicit=False,
    )
    with pytest.raises(HostError, match="original ordinal"):
        host._typed_outputs(_host_record(), [positional], tmp_path, generation_intent=_intent("allow"))


def test_host_upload_keeps_runtime_selector_object_wire_safe(tmp_path) -> None:
    host = GenericPackHost.__new__(GenericPackHost)
    host.client = SimpleNamespace(
        INLINE_SETTLEMENT_OUTPUTS=True,
        upload_object=lambda *args, **kwargs: SimpleNamespace(digest="sha256:" + "0" * 64, size=1),
    )
    descriptor = _descriptor(
        tmp_path, "generated_videos", b"wire", 0,
        output_port="generated_videos",
        group_key="left",
        variant_key="left-v",
        selector={"group_key": "left", "variant_key": "left-v"},
    )
    uploaded = host._upload_outputs(
        [{**descriptor, "artifact_type": "video/clip"}], project_id="project-1"
    )
    assert uploaded[0]["selector"] == {"group_key": "left", "variant_key": "left-v"}
    assert not isinstance(uploaded[0]["selector"], str)
