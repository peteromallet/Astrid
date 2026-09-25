from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.masks import PreparedAVMask, PreparedAVMaskError, load_prepared_av_mask
from astrid.packs.h3_av.src.prepare import PreparationError, prepare_request, write_preparation
from astrid.packs.h3_av.src.request import normalize_request


def _request() -> object:
    return normalize_request(
        {
            "version": 2,
            "prompt": "A bounded audiovisual edit.",
            "duration": 1,
            "media": [
                {
                    "id": "source",
                    "asset": "source.mp4",
                    "role": "timeline",
                    "modality": "video",
                    "at": {"frame": 0},
                    "range": [0, 1],
                    "edit": [
                        {"stream": "video", "during": [0, 1], "mask": {"rectangle": [1, 1, 2, 2]}},
                        {"stream": "audio", "during": [0, 1], "channels": [0]},
                    ],
                }
            ],
            "settings": {"steps": 8, "seed": 4},
        }
    )


def _source_only_request(*, source_range: list[float] | None = None, include_range: bool = True, continuation: bool = False) -> object:
    source: dict[str, object] = {
        "id": "source",
        "asset": "source.mp4",
        "role": "timeline",
        "modality": "video",
        "at": {"frame": 0},
        "edit": [],
    }
    if include_range:
        source["range"] = source_range or [0, 1]
    return normalize_request(
        {
            "version": 2,
            "prompt": "A source-only audiovisual baseline.",
            "duration": 1,
            "continuation": continuation,
            "media": [source],
            "settings": {"steps": 8, "seed": 4},
        }
    )


def test_v2_preparation_emits_lossless_delivery_artifact_and_roundtrips(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"immutable baseline")
    preparation = prepare_request(_request(), asset_map={"source.mp4": str(source)}, width=4, height=4)
    artifact = load_prepared_av_mask(preparation["prepared_av_mask"])

    assert artifact.video_shape == (24, 4, 4)
    assert artifact.audio_shape == (2, 48000)
    assert artifact.video_coverage == ((0, 24),)
    assert artifact.audio_coverage == ((0, 48000),)
    assert artifact.video_delivery()[0][1][1:3] == (1, 1)
    assert artifact.audio_delivery()[0][0] == 1
    assert artifact.audio_delivery()[1][0] == 0
    assert artifact.to_manifest()["audio"]["sampling_policy"].startswith("union_all_channels")
    assert artifact.to_manifest()["video"]["payload"]["encoding"] == "bitpack-msb-v1"
    assert preparation["artifact_digest"] == artifact.artifact_digest

    path = write_preparation(tmp_path / "preparation.json", preparation)
    reloaded = load_prepared_av_mask(path)
    assert reloaded.artifact_digest == artifact.artifact_digest
    assert reloaded.video_delivery() == artifact.video_delivery()
    assert reloaded.audio_delivery() == artifact.audio_delivery()


def test_source_only_normalized_extent_covers_full_video_and_audio_domains(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"immutable baseline")

    preparation = prepare_request(
        _source_only_request(), asset_map={"source.mp4": str(source)}, width=2, height=2
    )
    artifact = load_prepared_av_mask(preparation["prepared_av_mask"])

    assert artifact.video_shape == (24, 2, 2)
    assert artifact.audio_shape == (2, 48000)
    assert artifact.video_coverage == ((0, 24),)
    assert artifact.audio_coverage == ((0, 48000),)
    assert artifact.mapping["baseline_identity"]["kind"] == "source"
    assert artifact.mapping["baseline_identity"]["digest"] == artifact.source_baseline_digest


def test_explicit_continuation_allows_a_short_authoritative_prefix(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"immutable baseline")
    preparation = prepare_request(
        _source_only_request(source_range=[0, 0.5], continuation=True),
        asset_map={"source.mp4": str(source)}, width=2, height=2,
    )
    artifact = load_prepared_av_mask(preparation["prepared_av_mask"])
    assert artifact.video_coverage == ((0, 12),)
    assert artifact.audio_coverage == ((0, 24000),)


@pytest.mark.parametrize(
    ("request_kwargs", "message"),
    [
        ({"include_range": False}, "missing inspected coverage"),
        ({"source_range": [0, 0.5]}, "short"),
        ({"source_range": [0, 2]}, "outside the output"),
    ],
)
def test_v2_preparation_rejects_missing_short_and_out_of_domain_baseline_coverage(
    tmp_path: Path, request_kwargs: dict[str, object], message: str
) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"immutable baseline")

    with pytest.raises(PreparationError, match=message):
        prepare_request(
            _source_only_request(**request_kwargs),
            asset_map={"source.mp4": str(source)},
            width=2,
            height=2,
        )


def test_preparation_rejects_unresolved_v2_baseline(tmp_path: Path) -> None:
    with pytest.raises(PreparationError, match="every managed baseline"):
        prepare_request(_request(), width=4, height=4)


def test_preserve_edit_requires_authoritative_baseline_coverage(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"baseline prefix only")
    request = normalize_request({
        "version": 2, "prompt": "Protect the requested region.", "duration": 4,
        "media": [{"id": "source", "asset": "source.mp4", "role": "timeline", "modality": "video",
                   "at": {"frame": 0}, "range": [0, 2],
                   "edit": [{"stream": "video", "during": [2, 3], "action": "preserve", "mask": {"full_frame": True}}]}],
        "settings": {},
    })
    with pytest.raises(PreparationError, match="not covered by an authoritative baseline"):
        prepare_request(request, asset_map={"source.mp4": str(source)}, width=2, height=2)


def test_video_mask_asset_range_and_shape_are_applied(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"baseline")
    mask = tmp_path / "mask.json"
    mask.write_text(json.dumps([[[1, 0], [0, 0]], [[0, 1], [0, 0]], [[0, 0], [1, 0]]]))
    request = normalize_request({
        "version": 2, "prompt": "Use selected mask frames.", "duration": 1,
        "media": [{"id": "source", "asset": "source.mp4", "role": "timeline", "modality": "video",
                   "at": {"frame": 0}, "range": [0, 1],
                   "edit": [{"stream": "video", "during": [0, "1/12"], "mask": {
                       "asset": "mask.json", "range": [1, 3], "shape": {"frames": 3, "height": 2, "width": 2}}}]}],
        "settings": {},
    })
    artifact = load_prepared_av_mask(prepare_request(
        request, asset_map={"source.mp4": str(source), "mask.json": str(mask)}, width=2, height=2,
    )["prepared_av_mask"])
    assert artifact.video_delivery()[0] == ((0, 1), (0, 0))
    assert artifact.video_delivery()[1] == ((0, 0), (1, 0))


def test_binary_permissions_reject_nan_fractional_and_wrong_shapes() -> None:
    with pytest.raises(PreparedAVMaskError, match="binary"):
        PreparedAVMask.from_arrays(
            video_delivery=[[[0.5]]],
            audio_delivery=[[0]],
            source_baseline_digest=None,
            channel_layout="mono",
        )
    with pytest.raises(PreparedAVMaskError, match="finite"):
        PreparedAVMask.from_arrays(
            video_delivery=[[[float("nan")]]],
            audio_delivery=[[0]],
            source_baseline_digest=None,
            channel_layout="mono",
        )
    with pytest.raises(PreparedAVMaskError, match="rectangular"):
        PreparedAVMask.from_arrays(
            video_delivery=[[[0], [1, 0]]],
            audio_delivery=[[0]],
            source_baseline_digest=None,
            channel_layout="mono",
        )


def test_manifest_tampering_is_rejected() -> None:
    artifact = PreparedAVMask.from_arrays(
        video_delivery=[[[0]]],
        audio_delivery=[[0]],
        source_baseline_digest=None,
        video_coverage=[[0, 1]],
        audio_coverage=[[0, 1]],
        channel_layout="mono",
    )
    manifest = artifact.to_manifest()
    manifest["audio"]["sampling_policy"] = "independent latent channels"
    with pytest.raises(PreparedAVMaskError, match="digest"):
        PreparedAVMask.from_manifest(manifest)
