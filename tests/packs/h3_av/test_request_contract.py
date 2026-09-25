from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.request import H3RequestError, normalize_request, read_prepared_request


def media(asset: str, role: str, modality: str, **extra: object) -> dict[str, object]:
    return {"asset": asset, "role": role, "modality": modality, **extra}


def base_request() -> dict[str, object]:
    return {"version": 2, "prompt": "A continuous audiovisual result.", "duration": 15, "media": [], "settings": {"steps": 8, "seed": 42}}


def _fixture_a() -> dict[str, object]:
    raw = base_request()
    raw["media"] = [media(f"look-{i}.png", "reference", "image", id=f"look-{i}") for i in range(1, 5)]
    return raw


def _fixture_b() -> dict[str, object]:
    raw = base_request()
    raw["media"] = [
        media(
            "source-b.mp4",
            "timeline",
            "video",
            id="source-b",
            at={"frame": 0},
            range=[0, 8],
            edit=[
                {"stream": "video", "during": [1, 2], "mask": {"rectangle": [8, 12, 24, 18]}, "guides": ["region-b"]},
                {"stream": "video", "during": [3, 6], "mask": {"asset": "moving-b.json", "range": [72, 144], "shape": {"frames": 72, "height": 576, "width": 1024}}, "guides": ["region-b"]},
            ],
        ),
        media("region-b.png", "reference", "image", id="region-b"),
    ]
    return raw


def _fixture_c() -> dict[str, object]:
    raw = base_request()
    raw["media"] = [
        media(
            "source-c.wav",
            "timeline",
            "audio",
            id="source-c",
            at={"frame": 0},
            range=[0, 15],
            edit=[
                {"stream": "audio", "during": [3, 6], "text": "The left channel line.", "channels": [0], "guides": ["voice-c"]},
                {"stream": "audio", "during": [8, 9], "text": "The right channel line.", "channels": [1], "guides": ["voice-c"]},
            ],
        ),
        media("voice-c.wav", "reference", "audio", id="voice-c"),
    ]
    return raw


def _fixture_d() -> dict[str, object]:
    raw = base_request()
    raw["media"] = [
        media("start-0.png", "timeline", "image", id="start-0", at={"frame": 0}, hard=True),
        media("start-1.png", "timeline", "image", id="start-1", at={"frame": 1}, hard=True),
        media("start-2.png", "timeline", "image", id="start-2", at={"frame": 2}, hard=True),
        media("look-d.png", "reference", "image", id="look-d"),
        media("motion-d.mp4", "reference", "video", id="motion-d", audio=False),
    ]
    return raw


def _fixture_e() -> dict[str, object]:
    raw = base_request()
    raw["media"] = [
        media(
            "source-e.mp4",
            "timeline",
            "video",
            id="source-e",
            at={"frame": 0},
            range=[0, 8],
            edit=[
                {"stream": "video", "during": [2, 3], "mask": {"full_frame": True}, "guides": ["look-e"]},
                {"stream": "audio", "during": [4, 5], "text": "Selective ending speech.", "channels": [1], "guides": ["voice-e"]},
            ],
        ),
        media("ending-e.png", "timeline", "image", id="ending-e", at={"seconds": 8}, hard=True),
        media("look-e.png", "reference", "image", id="look-e"),
        media("motion-e.mp4", "reference", "video", id="motion-e", audio=False),
        media("voice-e.wav", "reference", "audio", id="voice-e"),
    ]
    return raw


def _fixture_f() -> dict[str, object]:
    raw = base_request()
    raw["media"] = [
        media(
            "source-f.mp4",
            "timeline",
            "video",
            id="source-f",
            at={"frame": 0},
            range=[0, 8],
            edit=[
                {"stream": "video", "during": [3, 6], "mask": "mouth-f.png", "guides": ["performance-f"]},
                {"stream": "audio", "during": [3, 6], "text": "Keep the replacement speech moving.", "guides": ["voice-f"]},
            ],
        ),
        media("performance-f.mp4", "reference", "video", id="performance-f", audio=False),
        media("voice-f.wav", "reference", "audio", id="voice-f"),
    ]
    return raw


def _fixture_x() -> dict[str, object]:
    raw = base_request()
    raw["media"] = [
        media("start-x-0.png", "timeline", "image", id="start-x-0", at={"frame": 0}, hard=True),
        media("start-x-1.png", "timeline", "image", id="start-x-1", at={"frame": 1}, hard=True),
        media("start-x-2.png", "timeline", "image", id="start-x-2", at={"frame": 2}, hard=True),
        media(
            "source-x.mp4",
            "timeline",
            "video",
            id="source-x",
            at={"seconds": 3},
            range=[0, 8],
            edit=[
                {"stream": "video", "during": [3, 6], "mask": {"asset": "moving-x.json", "range": [72, 144], "shape": {"frames": 72, "height": 576, "width": 1024}}, "guides": ["look-x-1", "performance-x"]},
                {"stream": "audio", "during": [3, 6], "text": "The combined replacement line.", "channels": [0], "guides": ["voice-x"]},
            ],
        ),
        media("ending-x.png", "timeline", "image", id="ending-x", at={"seconds": 11}, hard=True),
        *[media(f"look-x-{i}.png", "reference", "image", id=f"look-x-{i}") for i in range(1, 5)],
        media("performance-x.mp4", "reference", "video", id="performance-x", audio=False),
        media("voice-x.wav", "reference", "audio", id="voice-x"),
    ]
    return raw


FIXTURES = {
    "A": _fixture_a,
    "B": _fixture_b,
    "C": _fixture_c,
    "D": _fixture_d,
    "E": _fixture_e,
    "F": _fixture_f,
    "X": _fixture_x,
}


def test_named_fixtures_are_deterministic_and_one_output() -> None:
    for label, build in FIXTURES.items():
        raw = build()
        first = normalize_request(raw)
        second = normalize_request(json.loads(json.dumps(raw)))
        assert first.digest == second.digest, label
        assert first.value["output_count"] == 1, label
        assert first.value["profile"] == "h3_av.native.v2", label


@pytest.mark.parametrize("label", tuple(FIXTURES))
def test_serialized_normalized_v2_preparation_round_trips_through_shared_reader(label: str) -> None:
    produced = normalize_request(FIXTURES[label]())
    serialized = json.loads(json.dumps(produced.value))

    consumed = read_prepared_request(serialized, produced.digest, require_normalized_v2=True)

    assert consumed.value == produced.value
    assert consumed.digest == produced.digest


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.pop("profile"), "missing derived profile fields"),
        (lambda value: value["media"][0].__setitem__("occurrence_id", "contradictory"), "contradictory derived fields"),
        (lambda value: value["media"][0].__setitem__("model_tag", "<Picture 99>"), "contradictory derived fields"),
        (lambda value: value["media"][0].__setitem__("resolved_at", {"unit": "frames", "value": 17}), "contradictory derived fields"),
        (lambda value: value.__setitem__("unknown", True), "unsupported field"),
    ],
)
def test_shared_prepared_reader_rejects_missing_or_contradictory_normalized_fields(mutation, message: str) -> None:
    produced = normalize_request(_fixture_a())
    serialized = json.loads(json.dumps(produced.value))
    mutation(serialized)

    with pytest.raises(H3RequestError, match=message):
        read_prepared_request(serialized, produced.digest, require_normalized_v2=True)


def test_shared_prepared_reader_rejects_stale_digest_and_keeps_v1_support() -> None:
    produced = normalize_request(_fixture_a())
    with pytest.raises(H3RequestError, match="digest"):
        read_prepared_request(produced.value, "0" * 64, require_normalized_v2=True)
    legacy = normalize_request(
        {
            "version": 1,
            "operation": "edit",
            "source": {"asset": "source", "range": [0, 1]},
            "output": {"duration": 1},
            "content": {"prompt": "legacy"},
            "changes": {"video": [], "audio": []},
            "references": [],
            "overrides": {},
        }
    )
    assert read_prepared_request(legacy.value, legacy.digest, require_normalized_v2=True) == legacy


def test_graph_compile_consumer_uses_the_shared_prepared_reader() -> None:
    from astrid.packs.h3_av.src.graph import GraphBindingError, _request_from_preparation

    produced = normalize_request(_fixture_b())
    preparation = {"request": produced.value, "request_digest": produced.digest}
    artifact = {"request": produced.value, "request_digest": produced.digest}
    assert _request_from_preparation(preparation, artifact) == produced

    contradictory = json.loads(json.dumps(produced.value))
    contradictory["media"][0]["edit"][0]["resolved"]["range"][0] += 1
    with pytest.raises(GraphBindingError, match="prepared request is invalid"):
        _request_from_preparation(
            {"request": contradictory, "request_digest": produced.digest}, artifact
        )


def test_a_four_references_are_ordered_guidance_and_one_output() -> None:
    normalized = normalize_request(_fixture_a()).value
    references = [item for item in normalized["media"] if item["role"] == "reference"]
    assert len(references) == 4
    assert [item["model_tag"] for item in references] == ["<Picture 1>", "<Picture 2>", "<Picture 3>", "<Picture 4>"]
    assert all("at" not in item and "edit" not in item for item in references)
    assert normalized["output_count"] == 1


@pytest.mark.parametrize("label", tuple(FIXTURES))
def test_named_fixture_semantics_are_explicit(label: str) -> None:
    normalized = normalize_request(FIXTURES[label]()).value
    by_id = {item["id"]: item for item in normalized["media"] if "id" in item}
    timelines = [item for item in normalized["media"] if item["role"] == "timeline"]
    references = [item for item in normalized["media"] if item["role"] == "reference"]

    if label == "A":
        assert len(references) == 4
        assert not timelines
    elif label == "B":
        source = by_id["source-b"]
        assert source["role"] == "timeline" and source["resolved_at"]["value"] == 0
        assert [edit["stream"] for edit in source["edit"]] == ["video", "video"]
        assert source["edit"][0]["mask"] == {"rectangle": [8.0, 12.0, 24.0, 18.0], "polarity": "black_preserve_white_edit"}
        assert source["edit"][1]["mask"]["asset"] == "moving-b.json"
        assert source["edit"][1]["mask"]["range"] == [72, 144]
        assert source["edit"][0]["guides"] == ["region-b"]
    elif label == "C":
        source = by_id["source-c"]
        assert source["modality"] == "audio" and source["resolved_at"]["value"] == 0
        assert [edit["channels"] for edit in source["edit"]] == [[0], [1]]
        assert [edit["guides"] for edit in source["edit"]] == [["voice-c"], ["voice-c"]]
        assert [edit["resolved"]["range"] for edit in source["edit"]] == [[144000, 288000], [384000, 432000]]
    elif label == "D":
        assert [(by_id[f"start-{i}"]["resolved_at"]["value"], by_id[f"start-{i}"]["hard"]) for i in range(3)] == [(0, True), (1, True), (2, True)]
        assert {item["modality"] for item in references} == {"image", "video"}
    elif label == "E":
        assert by_id["source-e"]["resolved_range"] == [0, 192]
        assert by_id["ending-e"]["resolved_at"]["value"] == 192 and by_id["ending-e"]["hard"] is True
        assert [edit["stream"] for edit in by_id["source-e"]["edit"]] == ["video", "audio"]
        assert by_id["source-e"]["edit"][1]["channels"] == [1]
    elif label == "F":
        source = by_id["source-f"]
        assert source["edit"][0]["mask"]["asset"] == "mouth-f.png"
        assert source["edit"][0]["guides"] == ["performance-f"]
        assert source["edit"][1]["text"] == "Keep the replacement speech moving."
        assert source["edit"][1]["guides"] == ["voice-f"]
        assert source["edit"][1]["channels"] == "all"
        assert by_id["performance-f"]["audio"] is False
    elif label == "X":
        source = by_id["source-x"]
        assert [by_id[f"start-x-{i}"]["resolved_at"]["value"] for i in range(3)] == [0, 1, 2]
        assert len([item for item in references if item["modality"] == "image"]) == 4
        assert source["resolved_at"]["value"] == 72 and by_id["ending-x"]["resolved_at"]["value"] == 264
        assert source["edit"][0]["mask"]["asset"] == "moving-x.json"
        assert source["edit"][0]["mask"]["range"] == [72, 144]
        assert source["edit"][0]["guides"] == ["look-x-1", "performance-x"]
        assert source["edit"][1]["guides"] == ["voice-x"]
        assert source["edit"][1]["channels"] == [0]
        assert {by_id["performance-x"]["modality"], by_id["voice-x"]["modality"]} == {"video", "audio"}
    else:  # pragma: no cover - the parameter source is the named fixture map above.
        raise AssertionError(f"unhandled fixture {label}")


FIXTURE_DIGESTS = {
    "A": "952f07e531e26cc49d6de3918c9c5d7489963e63a1fa4a83722a7025e01e0b1c",
    "B": "8651c0c5a8501e4dd5a149ab50659af601152821fdd9c7e81469253a9453b64f",
    "C": "4fdd9ca7d5f22744577e77dbf991dd15e9bf7cf5aa8d6cd5d5f997cf160ac201",
    "D": "74c6c818e66e3ab0549a0e49461c669a984eea18bd326a8c2b6ce7b941d36699",
    "E": "a5aeb9945fbcd077d354a2c14f278e6b8776a559bbbfe17b0349a61e23a801b2",
    "F": "325d084ce126a673542f8e6986cd83e73d7860ed22e458c1dba0142c77c3ab9b",
    "X": "b304547d8bafefa1e2fa4afbf4bb516d26d624ed1dfd788cdbdcb2e43a6b0b71",
}


def test_named_fixture_digests_are_recorded() -> None:
    assert set(FIXTURE_DIGESTS) == set(FIXTURES)
    for label, expected in FIXTURE_DIGESTS.items():
        assert normalize_request(FIXTURES[label]()).digest == expected, label


@pytest.mark.parametrize(
    "case",
    [
        {"media": [media("source.mp4", "timeline", "video", id="source", at={"frame": 0}, edit=[{"stream": "video", "during": [3, 6], "mask": "mouth.png", "guides": ["mouth"]}]), media("mouth.mp4", "reference", "video", id="mouth", audio=False)]},
        {"media": [media("anchor-0.png", "timeline", "image", id="anchor-0", at={"frame": 0}), media("anchor-1.png", "timeline", "image", id="anchor-1", at={"frame": 1}), media("anchor-2.png", "timeline", "image", id="anchor-2", at={"frame": 2})]},
        {"media": [media("source.mp4", "timeline", "video", id="source", at={"frame": 0}, edit=[{"stream": "audio", "during": [3, 6], "text": "The literal line.", "channels": [0], "guides": ["voice"]}]), media("voice.wav", "reference", "audio", id="voice")]},
        {"media": [media("source.mp4", "timeline", "video", id="source", at={"frame": 0}, range=[0, 8], edit=[{"stream": "video"}]), media("ending.png", "timeline", "image", id="ending", at={"seconds": 8})]},
        {"media": [media("source.mp4", "timeline", "video", id="source", at={"frame": 0}, edit=[{"stream": "video", "during": [3, 6], "mask": {"rectangle": [0, 0, 100, 100]}, "guides": ["performance"]}, {"stream": "audio", "during": [3, 6], "text": "Exact speech.", "guides": ["voice"]}]), media("performance.mp4", "reference", "video", id="performance", audio=False), media("voice.wav", "reference", "audio", id="voice")]},
        {"media": [media("source.mp4", "timeline", "video", id="source", at={"frame": 0}, edit=[{"stream": "video", "during": [3, 6], "mask": "mouth.png", "guides": ["performance"]}, {"stream": "audio", "during": [3, 6], "text": "Keep moving.", "guides": ["voice"]}]), media("performance.mp4", "reference", "video", id="performance", audio=False), media("voice.wav", "reference", "audio", id="voice")]},
    ],
)
def test_b_to_f_and_x_normalize(case: dict[str, object]) -> None:
    normalized = normalize_request({**base_request(), **case})
    assert normalized.value["version"] == 2
    assert normalized.digest
    assert normalized.value["output_count"] == 1


def test_inspected_asset_modalities_are_explicit_and_not_filename_inferred() -> None:
    raw = base_request()
    raw["media"] = [media("opaque-alias", "reference", "image", id="picture")]
    assert normalize_request(raw, asset_modalities={"opaque-alias": "image"}).value["media"][0]["modality"] == "image"
    with pytest.raises(H3RequestError, match="wrong modality"):
        normalize_request({**raw, "media": [media("sound.wav", "timeline", "audio", id="source", at={"frame": 0}, range=[0, 1], edit=[{"stream": "video", "during": [0, 1]}]) ]})


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda r: r["media"].__getitem__(0).update({"edit": [{"stream": "video", "guides": ["missing"]}]}), "dangling"),
        (lambda r: r["media"].append(media("source.mp4", "reference", "video", id="source-ref", at={"frame": 0})), "reference entries"),
        (lambda r: r["media"].__getitem__(0).update({"edit": [{"stream": "video", "during": [1, 1]}]}), "end > start"),
        (lambda r: r["media"].__getitem__(0).pop("at"), "at is required"),
        (lambda r: r["media"].__getitem__(0).update({"edit": [{"stream": "video", "during": [0, 1], "mask": {"full_frame": True, "polarity": "white_preserve_black_edit"}}]}), "polarity"),
        (lambda r: r["media"].__getitem__(0).update({"edit": [{"stream": "video", "during": [0, 1], "mask": {"asset": "mask.png", "shape": {"frames": 0, "height": 10, "width": 10}}}]}), "shape"),
        (lambda r: r["media"].__getitem__(0).update({"edit": [{"stream": "audio", "during": [0, 1], "text": "{dialogue}"}]}), "placeholder"),
        (lambda r: r["media"].__getitem__(0).update({"edit": [{"stream": "video", "during": [0, 1], "guides": ["source"]}]}), "timeline media"),
        (lambda r: r.update({"settings": {"workflow": "ignored"}}), "unsupported field"),
    ],
)
def test_negative_contracts_fail_closed(mutate, message: str) -> None:
    raw = base_request()
    raw["media"] = [media("source.mp4", "timeline", "video", id="source", at={"frame": 0}, range=[0, 15])]
    mutate(raw)
    with pytest.raises(H3RequestError, match=message):
        normalize_request(raw)


def test_conflicting_anchors_and_unrepresentable_placement_fail() -> None:
    raw = base_request()
    raw["media"] = [
        media("a.png", "timeline", "image", id="a", at={"frame": 4}),
        media("b.png", "timeline", "image", id="b", at={"frame": 4}),
    ]
    with pytest.raises(H3RequestError, match="conflicting"):
        normalize_request(raw)
    raw["media"][1]["at"] = {"seconds": 0.1}
    with pytest.raises(H3RequestError, match="representable"):
        normalize_request(raw)


def test_receipt_fixtures_are_json_serializable(tmp_path: Path) -> None:
    raw = base_request()
    raw["media"] = [media("one.png", "reference", "image", id="one")]
    request = normalize_request(raw)
    receipt = {"fixture": "A", "normalized": request.value, "digest": request.digest}
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8"))["digest"] == request.digest
