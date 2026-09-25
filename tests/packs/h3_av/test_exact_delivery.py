from __future__ import annotations

import json
import hashlib
import shutil
import subprocess
import zipfile
from fractions import Fraction
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.baseline import BaselineError, render_timeline_baseline
from astrid.packs.h3_av.src.compose import CompositionError, _decode_exact_audio, _decode_exact_video, compose_candidate
from astrid.packs.h3_av.src.masks import PreparedAVMask, load_prepared_av_mask
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.h3_av.src.verify import VerificationError, verify_candidate


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for exact delivery tests",
)


def _request() -> object:
    return normalize_request(
        {
            "version": 2,
            "prompt": "Exact delivery test.",
            "duration": 1,
            "media": [
                {
                    "id": "source",
                    "asset": "source.mkv",
                    "role": "timeline",
                    "modality": "video",
                    "at": {"frame": 0},
                    "range": [0, 1],
                    "edit": [
                        {"stream": "video", "during": ["1/6", "1/3"], "mask": {"rectangle": [1, 0, 1, 1]}},
                        {"stream": "audio", "during": ["123/48000", "124/48000"], "channels": [0]},
                    ],
                }
            ],
        }
    )


def _media(path: Path, *, colour: str, tone: int, channels: int = 2, sample_rate: int = 48000, duration: int = 1) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={colour}:s=4x2:r=24",
            "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate={sample_rate}",
            "-t", str(duration), "-c:v", "ffv1", "-pix_fmt", "rgba", "-c:a", "pcm_s32le", "-ar", str(sample_rate),
            "-ac", str(channels), str(path),
        ],
        check=True,
    )


def _video_only(path: Path, *, colour: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={colour}:s=4x2:r=24", "-t", "1",
            "-an", "-c:v", "ffv1", "-pix_fmt", "rgba", str(path),
        ],
        check=True,
    )


def _still(path: Path, *, colour: str) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"color=c={colour}:s=4x2", "-frames:v", "1",
            str(path),
        ],
        check=True,
    )


def _audio_only(path: Path, *, tone: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", f"sine=frequency={tone}:sample_rate=48000", "-t", "1",
            "-vn", "-c:a", "pcm_s32le", "-ac", "2", str(path),
        ],
        check=True,
    )


def _bundle(path: Path, video: Path, audio: Path) -> None:
    members = [("video.mkv", video), ("audio.mkv", audio)]
    manifest = {
        "schema_version": 1,
        "kind": "h3_av_generated_av",
        "outputs": [
            {
                "role": role,
                "member": member,
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "size": source.stat().st_size,
            }
            for role, (member, source) in zip(("video", "audio"), members)
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
        for member, source in members:
            archive.write(source, member)


def _refresh_candidate(composition: dict[str, object], path: Path) -> None:
    record = composition["candidate"]
    assert isinstance(record, dict)
    record["path"] = str(path)
    record["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    record["size"] = path.stat().st_size


def test_exact_cpu_delivery_restores_pixels_and_pcm_and_rejects_digest_tamper(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    generated = tmp_path / "generated.mkv"
    _media(source, colour="blue", tone=440)
    _media(generated, colour="red", tone=880)
    preparation = prepare_request(
        _request(),
        asset_map={"source.mkv": str(source)},
        fps=24,
        width=4,
        height=2,
        sample_rate=48000,
    )

    composition = compose_candidate(
        preparation=preparation,
        generated=generated,
        source=source,
        out_dir=tmp_path / "composition",
    )
    assert composition["composition"]["method"] == "cpu-exact-delivery-compose-v1"
    assert composition["delivery_contract"]["lossless_master"]["video_codec"] == "ffv1"
    report = verify_candidate(preparation=preparation, composition=composition, source=source)
    assert report["preservation"]["status"] == "exact_delivery_domain"
    assert report["exact_equality"]["video"]["mismatch_count"] == 0
    assert report["exact_equality"]["audio"]["mismatch_count"] == 0

    tampered = json.loads(json.dumps(composition))
    tampered["candidate"]["sha256"] = "0" * 64
    with pytest.raises(VerificationError, match="digest"):
        verify_candidate(preparation=preparation, composition=tampered, source=source)


def test_source_free_multi_image_anchors_restore_exactly_without_source_baseline(tmp_path: Path) -> None:
    anchors = []
    asset_map: dict[str, str] = {}
    for frame, colour in enumerate(("green", "yellow", "magenta")):
        asset = f"anchor-{frame}.png"
        path = tmp_path / asset
        _still(path, colour=colour)
        asset_map[asset] = str(path)
        anchors.append({
            "id": f"anchor-{frame}",
            "asset": asset,
            "role": "timeline",
            "modality": "image",
            "at": {"frame": frame},
            "hard": True,
        })
    request = normalize_request({
        "version": 2,
        "prompt": "A generated AV baseline with three exact opening frames.",
        "duration": 1,
        "media": anchors,
    })
    generated = tmp_path / "generated.mkv"
    _media(generated, colour="blue", tone=880)
    preparation = prepare_request(
        request,
        asset_map=asset_map,
        fps=24,
        width=4,
        height=2,
        sample_rate=48000,
        target_model_dimensions={"frames": 7, "height": 1, "width": 1},
    )

    composition = compose_candidate(
        preparation=preparation,
        generated=generated,
        out_dir=tmp_path / "composition",
    )
    report = verify_candidate(preparation=preparation, composition=composition)
    assert [row["frame"] for row in report["exact_equality"]["anchors"]] == [0, 1, 2]
    assert all(row["exact"] for row in report["exact_equality"]["anchors"])
    assert report["preservation"]["status"] == "exact_delivery_domain"


def test_exact_cpu_delivery_keeps_separate_video_and_audio_outputs_independent(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    generated_video = tmp_path / "generated-video.mkv"
    generated_audio = tmp_path / "generated-audio.mkv"
    generated_bundle = tmp_path / "generated.zip"
    _media(source, colour="blue", tone=440)
    _video_only(generated_video, colour="red")
    _audio_only(generated_audio, tone=880)
    _bundle(generated_bundle, generated_video, generated_audio)
    preparation = prepare_request(
        _request(), asset_map={"source.mkv": str(source)}, fps=24, width=4, height=2, sample_rate=48000
    )

    composition = compose_candidate(
        preparation=preparation, generated=generated_bundle, source=source, out_dir=tmp_path / "composition"
    )
    report = verify_candidate(preparation=preparation, composition=composition, source=source)
    assert report["preservation"]["status"] == "exact_delivery_domain"
    assert report["exact_equality"]["video"]["mismatch_count"] == 0
    assert report["exact_equality"]["audio"]["mismatch_count"] == 0
    assert composition["delivery_contract"]["baseline_representation"]["audio"]["channel_order"] == "prepared_channel_order"


def test_managed_audio_timeline_baseline_composes_and_verifies_through_public_executors(tmp_path: Path) -> None:
    from astrid.packs.h3_av.executors.compose.run import main as compose_main
    from astrid.packs.h3_av.executors.verify.run import main as verify_main
    from astrid.packs.h3_av.src.input_bundle import build_input_bundle, bundle_digest

    baseline = tmp_path / "baseline.wav"
    generated = tmp_path / "generated.mkv"
    _audio_only(baseline, tone=440)
    _media(generated, colour="red", tone=880)
    request = normalize_request(
        {
            "version": 2,
            "prompt": "Audio baseline exactness.",
            "duration": 1,
            "media": [
                {
                    "id": "baseline-audio",
                    "asset": "baseline.wav",
                    "role": "timeline",
                    "modality": "audio",
                    "at": {"seconds": 0},
                    "range": [0, 1],
                }
            ],
        }
    )
    bundle = build_input_bundle(request, {"baseline.wav": baseline}, tmp_path / "input.zip")
    preparation = prepare_request(
        request,
        asset_map={"baseline.wav": str(baseline)},
        fps=24,
        width=4,
        height=2,
        sample_rate=48000,
    )
    preparation["input_bundle_sha256"] = bundle_digest(bundle)
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(json.dumps(preparation), encoding="utf-8")

    compose_dir = tmp_path / "compose"
    assert compose_main(
        ["--preparation", str(preparation_path), "--generated", str(generated), "--input-bundle", str(bundle), "--out", str(compose_dir)]
    ) == 0
    composition = json.loads((compose_dir / "composition-manifest.json").read_text(encoding="utf-8"))
    assert composition["source"]["sha256"] == hashlib.sha256(baseline.read_bytes()).hexdigest()
    compose_manifest = json.loads((compose_dir / "manifest.json").read_text(encoding="utf-8"))
    candidate = compose_dir / compose_manifest["outputs"][0]["path"]

    verify_dir = tmp_path / "verify"
    assert verify_main(
        ["--preparation", str(preparation_path), "--composition", str(compose_dir / "composition-manifest.json"), "--candidate", str(candidate), "--input-bundle", str(bundle), "--out", str(verify_dir)]
    ) == 0
    verification = json.loads((verify_dir / "verification.json").read_text(encoding="utf-8"))
    assert verification["exact_equality"]["audio"]["mismatch_count"] == 0
    assert verification["preservation"]["status"] == "exact_delivery_domain"


def _source_plus_timeline_material_request(material_id: str, material_asset: str, frame: int) -> object:
    return normalize_request(
        {
            "version": 2,
            "prompt": "Exact composite baseline delivery test.",
            "duration": 1,
            "media": [
                {
                    "id": "source",
                    "asset": "source.mkv",
                    "role": "timeline",
                    "modality": "video",
                    "at": {"frame": 0},
                    "range": [0, 1],
                    "edit": [
                        {"stream": "video", "during": ["1/6", "1/3"], "mask": {"rectangle": [1, 0, 1, 1]}},
                        {"stream": "audio", "during": ["123/48000", "124/48000"], "channels": [0]},
                    ],
                },
                {
                    "id": material_id,
                    "asset": material_asset,
                    "role": "timeline",
                    "modality": "image",
                    "at": {"frame": frame},
                },
            ],
        }
    )


def _assert_composite_baseline_delivery(
    *, tmp_path: Path, material_id: str, material_asset: str, frame: int
) -> None:
    source = tmp_path / "source.mkv"
    material = tmp_path / material_asset
    generated = tmp_path / "generated.mkv"
    _media(source, colour="blue", tone=440)
    _video_only(material, colour="green")
    _media(generated, colour="red", tone=880)
    preparation = prepare_request(
        _source_plus_timeline_material_request(material_id, material_asset, frame),
        asset_map={"source.mkv": str(source), material_asset: str(material)},
        fps=24,
        width=4,
        height=2,
        sample_rate=48000,
    )
    artifact = load_prepared_av_mask(preparation["prepared_av_mask"])
    identity = artifact.mapping["baseline_identity"]
    assert identity["kind"] == "composite"
    assert identity["primary_occurrence"] == "source"
    assert {member["occurrence_id"] for member in identity["members"]} == {"source", material_id}
    assert artifact.source_baseline_digest == identity["members"][0]["sha256"]

    composition = compose_candidate(
        preparation=preparation, generated=generated, source=source, out_dir=tmp_path / "composition"
    )
    report = verify_candidate(preparation=preparation, composition=composition, source=source)
    assert composition["composition"]["baseline_identity"] == identity
    assert composition["delivery_contract"]["baseline_representation"]["identity"] == identity
    assert report["preservation"]["video_pixels"] == 188
    assert report["preservation"]["audio_samples"] == 95_999
    assert report["preservation"]["video_mismatches"] == 0
    assert report["preservation"]["audio_mismatches"] == 0
    assert {anchor["id"]: anchor["frame"] for anchor in report["exact_equality"]["anchors"]} == {
        material_id: frame,
    }


def test_exact_composite_baseline_source_plus_independent_anchor(tmp_path: Path) -> None:
    _assert_composite_baseline_delivery(tmp_path=tmp_path, material_id="anchor", material_asset="anchor.mkv", frame=2)


def test_exact_composite_baseline_source_plus_ending_material(tmp_path: Path) -> None:
    _assert_composite_baseline_delivery(tmp_path=tmp_path, material_id="ending", material_asset="ending.mkv", frame=23)


def test_exact_cpu_delivery_supports_mono_44100_decoded_domain(tmp_path: Path) -> None:
    source = tmp_path / "source-mono.mkv"
    generated = tmp_path / "generated-mono.mkv"
    _media(source, colour="blue", tone=440, channels=1, sample_rate=44100)
    _media(generated, colour="red", tone=880, channels=1, sample_rate=44100)
    preparation = prepare_request(
        _request(), asset_map={"source.mkv": str(source)}, fps=24, width=4, height=2, sample_rate=44100
    )
    stereo_artifact = load_prepared_av_mask(preparation["prepared_av_mask"])
    mono_artifact = PreparedAVMask.from_arrays(
        video_delivery=stereo_artifact.video_delivery(),
        audio_delivery=[stereo_artifact.audio_delivery()[0]],
        fps=(24, 1),
        sample_rate=44100,
        source_baseline_digest=hashlib.sha256(source.read_bytes()).hexdigest(),
        video_coverage=stereo_artifact.video_coverage,
        audio_coverage=stereo_artifact.audio_coverage,
        mapping=stereo_artifact.mapping,
        channel_layout="mono",
        source_hashes=stereo_artifact.source_hashes,
        native_padding_trim=stereo_artifact.native_padding_trim,
        target_model_dimensions=stereo_artifact.target_model_dimensions,
        anchor_classification=stereo_artifact.anchor_classification,
    )
    preparation["prepared_av_mask"] = mono_artifact.to_manifest()
    preparation["artifact_digest"] = mono_artifact.artifact_digest

    composition = compose_candidate(
        preparation=preparation, generated=generated, source=source, out_dir=tmp_path / "composition"
    )
    report = verify_candidate(preparation=preparation, composition=composition, source=source)
    assert composition["delivery_contract"]["baseline_representation"]["audio"]["sample_rate"] == 44100
    assert composition["delivery_contract"]["baseline_representation"]["audio"]["channels"] == 1
    assert report["preservation"]["audio_mismatches"] == 0
    wrong_channels = tmp_path / "generated-stereo.mkv"
    _media(wrong_channels, colour="red", tone=880, channels=2, sample_rate=44100)
    with pytest.raises(CompositionError, match="audio format"):
        compose_candidate(
            preparation=preparation, generated=wrong_channels, source=source,
            out_dir=tmp_path / "wrong-channels",
        )


@pytest.mark.parametrize("sample_rate", [44100, 48000])
def test_timeline_baseline_preserves_placed_ranges_and_native_padding(tmp_path: Path, sample_rate: int) -> None:
    source = tmp_path / "source.mkv"
    other = tmp_path / "other.mkv"
    _media(source, colour="blue", tone=440, sample_rate=sample_rate, duration=2)
    _media(other, colour="blue", tone=880, sample_rate=sample_rate, duration=2)
    request = normalize_request({
        "version": 2,
        "prompt": "Place the second source second before the first.",
        "duration": 2,
        "media": [
            {"id": "late", "asset": "source.mkv", "role": "timeline", "modality": "video",
             "at": {"frame": 0}, "range": [1, 2]},
            {"id": "early", "asset": "source.mkv", "role": "timeline", "modality": "video",
             "at": {"frame": 24}, "range": [0, 1]},
        ],
    })
    preparation = prepare_request(
        request, asset_map={"source.mkv": str(source)}, fps=24, width=4, height=2, sample_rate=sample_rate,
    )
    artifact = load_prepared_av_mask(preparation["prepared_av_mask"])
    video, audio = render_timeline_baseline(preparation, artifact, tmp_path / "baseline", primary_source=source)

    expected_video: list[bytes] = []
    expected_audio: list[bytes] = []
    for start in (24, 0):
        video_part = tmp_path / f"expected-{start}.rgba"
        audio_part = tmp_path / f"expected-{start}.s32le"
        _decode_exact_video(source, video_part, frames=24, width=4, height=2, fps=Fraction(24), start_frame=start)
        _decode_exact_audio(
            source, audio_part, samples=sample_rate, sample_rate=sample_rate, channels=2,
            start_sample=start * sample_rate // 24,
        )
        expected_video.append(video_part.read_bytes())
        expected_audio.append(audio_part.read_bytes())
    assert video.read_bytes() == b"".join(expected_video)
    assert audio.read_bytes() == b"".join(expected_audio)

    with pytest.raises(BaselineError, match="failed identity check"):
        render_timeline_baseline(preparation, artifact, tmp_path / "wrong-source", primary_source=other)
    if sample_rate == 48000:
        native_video, native_audio = render_timeline_baseline(
            preparation, artifact, tmp_path / "native", native_frames=56,
        )
        assert native_video.read_bytes() == video.read_bytes() + bytes(8 * 4 * 2 * 4)
        assert native_audio.read_bytes() == audio.read_bytes() + bytes(16000 * 2 * 4)
    else:
        with pytest.raises(BaselineError, match="native baseline requires"):
            render_timeline_baseline(preparation, artifact, tmp_path / "native", native_frames=56)


def test_exact_verification_rejects_short_or_corrupt_candidate_after_digest_refresh(tmp_path: Path) -> None:
    source = tmp_path / "source.mkv"
    generated = tmp_path / "generated.mkv"
    _media(source, colour="blue", tone=440)
    _media(generated, colour="red", tone=880)
    preparation = prepare_request(
        _request(), asset_map={"source.mkv": str(source)}, fps=24, width=4, height=2, sample_rate=48000
    )
    composition = compose_candidate(
        preparation=preparation, generated=generated, source=source, out_dir=tmp_path / "composition"
    )
    candidate = Path(str(composition["candidate"]["path"]))
    truncated = tmp_path / "truncated.mkv"
    truncated.write_bytes(candidate.read_bytes()[:-257])
    _refresh_candidate(composition, truncated)
    with pytest.raises(VerificationError, match="short|corrupt|decoded format"):
        verify_candidate(preparation=preparation, composition=composition, source=source)


@pytest.mark.parametrize(
    ("filter_args", "message"),
    [
        (("-vf", "drawbox=x=0:y=0:w=1:h=1:color=white:t=fill"), "protected decoded pixels|anchor"),
        (("-af", "volume=0.5"), "PCM samples"),
    ],
)
def test_exact_verification_rejects_decoded_pixel_or_pcm_mutation(
    tmp_path: Path, filter_args: tuple[str, str], message: str
) -> None:
    source = tmp_path / "source.mkv"
    generated = tmp_path / "generated.mkv"
    _media(source, colour="blue", tone=440)
    _media(generated, colour="red", tone=880)
    preparation = prepare_request(
        _request(), asset_map={"source.mkv": str(source)}, fps=24, width=4, height=2, sample_rate=48000
    )
    composition = compose_candidate(
        preparation=preparation, generated=generated, source=source, out_dir=tmp_path / "composition"
    )
    candidate = Path(str(composition["candidate"]["path"]))
    mutated = tmp_path / "mutated.mkv"
    stream_args = ["-c:v", "ffv1", "-pix_fmt", "rgba", "-c:a", "pcm_s32le"]
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(candidate), *filter_args, *stream_args, str(mutated)],
        check=True,
    )
    _refresh_candidate(composition, mutated)
    with pytest.raises(VerificationError, match=message):
        verify_candidate(preparation=preparation, composition=composition, source=source)
