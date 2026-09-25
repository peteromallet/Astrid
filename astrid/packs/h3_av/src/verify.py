"""Fail-closed verification of H3 candidate custody and preservation."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path
from typing import Any, Mapping

from .compose import (
    _anchor_items,
    _asset_paths,
    _baseline_identity_contract,
    _decode_anchor,
    _decode_exact_audio,
    _decode_exact_video,
    _exact_clock,
    _exact_offsets,
    _prepared_artifact,
    _primary_baseline_asset,
    _probe,
    _sample_digest,
)
from .request import read_prepared_request


class VerificationError(ValueError):
    """Candidate evidence is incomplete or contradictory."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_offset(preparation: Mapping[str, Any]) -> float:
    request = preparation.get("request")
    source = request.get("source") if isinstance(request, Mapping) else None
    value = source.get("range") if isinstance(source, Mapping) else None
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return float(value[0])
    return 0.0


def _interval_key(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return float(value[0]), float(value[1])
    except (TypeError, ValueError):
        return None


def _covers_whole(intervals: Any, duration: Any) -> bool:
    if not isinstance(intervals, list):
        return False
    try:
        target = float(duration)
        ordered = sorted((_interval_key(item) for item in intervals), key=lambda item: item[0] if item else 0.0)
    except (TypeError, ValueError):
        return False
    cursor = 0.0
    for item in ordered:
        if item is None or item[0] > cursor or item[1] <= item[0]:
            return False
        cursor = max(cursor, item[1])
    return cursor >= target


def _verify_sample_evidence(
    *,
    source: Path,
    candidate: Path,
    protected: Mapping[str, Any],
    preparation: Mapping[str, Any],
) -> None:
    for stream_type in ("video", "audio"):
        expected = [_interval_key(item) for item in protected[stream_type]]
        if any(item is None for item in expected):
            raise VerificationError(f"protected {stream_type} permissions are malformed")
        entries = protected.get("_evidence", {}).get(stream_type, [])
        if not isinstance(entries, list):
            raise VerificationError(f"protected {stream_type} samples are missing")
        by_interval: dict[tuple[float, float], Mapping[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping):
                raise VerificationError(f"protected {stream_type} sample evidence is malformed")
            key = _interval_key(entry.get("interval"))
            if key is None or key in by_interval:
                raise VerificationError(f"protected {stream_type} sample evidence has an invalid interval")
            by_interval[key] = entry
        for key in expected:
            assert key is not None
            entry = by_interval.get(key)
            if entry is None:
                raise VerificationError(f"protected {stream_type} sample evidence does not cover {list(key)}")
            source_hash = entry.get("source_sha256")
            candidate_hash = entry.get("candidate_sha256")
            method = entry.get("method")
            sample_count = entry.get("sample_count")
            if (
                not isinstance(source_hash, str)
                or not isinstance(candidate_hash, str)
                or source_hash != candidate_hash
                or not isinstance(method, str)
                or not method.strip()
                or isinstance(sample_count, bool)
                or not isinstance(sample_count, int)
                or sample_count <= 0
            ):
                raise VerificationError(f"protected {stream_type} evidence is not a positive matching sample witness")
            if method == "ffmpeg-decoded-samples-v1":
                try:
                    source_actual, source_count = _sample_digest(
                        source, stream_type, _source_offset(preparation) + key[0], key[1] - key[0]
                    )
                    candidate_actual, candidate_count = _sample_digest(
                        candidate, stream_type, key[0], key[1] - key[0]
                    )
                except Exception as exc:  # noqa: BLE001 - verification boundary
                    raise VerificationError(f"protected {stream_type} samples could not be decoded") from exc
                if (
                    source_actual != source_hash
                    or candidate_actual != candidate_hash
                    or source_count <= 0
                    or candidate_count <= 0
                ):
                    raise VerificationError(f"protected {stream_type} sample digest does not match candidate")
            elif not isinstance(entry.get("witness_digest"), str) or not entry["witness_digest"]:
                raise VerificationError(f"protected {stream_type} non-ffmpeg evidence lacks a witness digest")


def _verify_provenance(preparation: Mapping[str, Any], composition: Mapping[str, Any]) -> None:
    if composition.get("request_digest") != preparation.get("request_digest"):
        raise VerificationError("composition request provenance does not match preparation")
    schedule = preparation.get("mask_schedule")
    if not isinstance(schedule, Mapping) or composition.get("schedule_digest") != schedule.get("digest"):
        raise VerificationError("composition schedule provenance does not match preparation")
    provenance = composition.get("provenance")
    if provenance in (None, {}):
        return
    if not isinstance(provenance, Mapping) or provenance.get("request_digest") != preparation.get("request_digest"):
        raise VerificationError("composition provenance is missing the request identity")
    assets = provenance.get("assets")
    prepared_assets = preparation.get("assets")
    def identity_rows(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                key: identity_rows(item)
                for key, item in value.items()
                if key not in {"path", "local_path", "manifest_path", "relative_path"}
            }
        if isinstance(value, list):
            return [identity_rows(item) for item in value]
        return value
    if assets is not None and identity_rows(assets) != identity_rows(prepared_assets):
        raise VerificationError("composition asset provenance does not match preparation")


def _verify_full_decoded_extent(
    candidate: Path, root: Path, *, frames: int, width: int, height: int,
    samples: int, channels: int, sample_rate: int,
) -> None:
    """Count both entire decoded streams; prefix decodes alone hide trailing AV."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise VerificationError("exact verification requires ffmpeg")
    streams = (
        ("video", root / "full-video.rgba", width * height * 4, frames,
         ["-map", "0:v:0", "-an", "-sn", "-dn", "-fps_mode", "passthrough",
          "-f", "rawvideo", "-pix_fmt", "rgba"]),
        ("audio", root / "full-audio.s32le", channels * 4, samples,
         ["-map", "0:a:0", "-vn", "-sn", "-dn", "-f", "s32le",
          "-acodec", "pcm_s32le", "-ar", str(sample_rate), "-ac", str(channels)]),
    )
    for stream_type, destination, unit_bytes, expected, options in streams:
        try:
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(candidate),
                 *options, str(destination)], check=True, capture_output=True, text=True,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise VerificationError(f"candidate full {stream_type} stream is corrupt") from exc
        actual_bytes = destination.stat().st_size
        if actual_bytes != expected * unit_bytes:
            raise VerificationError(
                f"candidate {stream_type} decoded extent is {actual_bytes // unit_bytes} "
                f"{'frames' if stream_type == 'video' else 'samples'}; expected {expected}"
            )


def _verify_presentation_clock(
    candidate: Path, *, frames: int, fps: Fraction, samples: int, sample_rate: int,
) -> None:
    """Check the muxed presentation timeline independently of normalized decodes."""

    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise VerificationError("exact verification requires ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", "-show_streams", "-show_frames", "-show_format",
             "-show_entries",
             "stream=index,codec_type,time_base,start_pts,start_time:"
             "frame=media_type,stream_index,pts,nb_samples:format=start_time,duration",
             "-of", "json", str(candidate)],
            check=True, capture_output=True, text=True,
        )
        probe = json.loads(result.stdout)
        streams = probe["streams"]
        decoded_frames = probe["frames"]
        container = probe["format"]
        if not isinstance(streams, list) or not isinstance(decoded_frames, list):
            raise ValueError("missing stream or frame rows")
        duration = Fraction(frames, 1) / fps
        if Fraction(samples, sample_rate) != duration:
            raise ValueError("prepared video and audio clocks disagree")
        stream_rows = {}
        for kind in ("video", "audio"):
            matching = [row for row in streams if row.get("codec_type") == kind]
            if len(matching) != 1:
                raise ValueError(f"expected one {kind} stream")
            row = matching[0]
            tick = Fraction(row["time_base"])
            if tick <= 0:
                raise ValueError(f"invalid {kind} time base")
            origin = Fraction(int(row["start_pts"])) * tick
            tolerance = tick / 2 + Fraction(1, 1_000_000)
            if abs(origin) > tolerance or abs(Fraction(row["start_time"]) - origin) > tolerance:
                raise ValueError(f"{kind} stream origin is off the delivery clock")
            stream_rows[kind] = (row["index"], tick, tolerance)

        for kind, count in (("video", frames), ("audio", samples)):
            index, tick, tolerance = stream_rows[kind]
            items = [row for row in decoded_frames if row.get("stream_index") == index]
            if not items:
                raise ValueError(f"{kind} presentation frames are missing")
            elapsed = 0
            previous: Fraction | None = None
            for position, row in enumerate(items):
                stamp = Fraction(int(row["pts"])) * tick
                expected = Fraction(position, 1) / fps if kind == "video" else Fraction(elapsed, sample_rate)
                if previous is not None and stamp <= previous:
                    raise ValueError(f"{kind} presentation timestamps are not increasing")
                if abs(stamp - expected) > tolerance:
                    raise ValueError(f"{kind} presentation timestamp differs from delivery clock")
                previous = stamp
                if kind == "audio":
                    block = int(row["nb_samples"])
                    if block <= 0:
                        raise ValueError("audio presentation block is empty")
                    elapsed += block
            if (len(items) if kind == "video" else elapsed) != count:
                raise ValueError(f"{kind} presentation extent differs from delivery clock")
            end = previous + (Fraction(1, 1) / fps if kind == "video" else Fraction(int(items[-1]["nb_samples"]), sample_rate))
            if abs(end - duration) > tolerance:
                raise ValueError(f"{kind} presentation endpoint differs from delivery clock")

        format_tolerance = max(stream_rows["video"][2], stream_rows["audio"][2])
        if (abs(Fraction(container["start_time"])) > format_tolerance
                or abs(Fraction(container["duration"]) - duration) > format_tolerance):
            raise ValueError("container presentation duration differs from delivery clock")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, ZeroDivisionError) as exc:
        raise VerificationError(f"candidate presentation clock is invalid: {exc}") from exc


def _verify_audio_conversion_evidence(
    composition: Mapping[str, Any], method: Mapping[str, Any], *,
    sample_rate: int, channels: int, samples: int, fps: Any,
) -> None:
    evidence = method.get("generated_audio_conversion")
    delivery = composition["delivery_contract"]
    if delivery.get("audio_conversion") != evidence:
        raise VerificationError("delivery audio conversion evidence disagrees with composition")
    if evidence is None:
        if method.get("editable_counts", {}).get("audio_samples"):
            raise VerificationError("editable audio lacks generated conversion evidence")
        return
    if not isinstance(evidence, Mapping):
        raise VerificationError("generated audio conversion evidence is malformed")
    if (
        evidence.get("input_channels") != channels
        or evidence.get("channels") != channels
        or evidence.get("output_sample_rate") != sample_rate
        or evidence.get("placement_sample") != 0
        or evidence.get("delivery_samples") != samples
    ):
        raise VerificationError("generated audio conversion has the wrong clock, channels, or placement")
    digests = ["input_sha256", "delivery_pcm_sha256"]
    if evidence.get("method") == "ffmpeg-native-32000-to-delivery-48000-v1":
        digests += ["native_pcm_sha256", "resampled_pcm_sha256"]
        counts = [evidence.get(key) for key in (
            "input_samples", "resampled_samples", "trimmed_tail_samples", "padded_tail_samples",
        )]
        if any(type(value) is not int for value in counts):
            raise VerificationError("native audio conversion sample counts are malformed")
        input_samples, resampled, trimmed, padded = counts
        max_pad = (sample_rate * fps.denominator + fps.numerator - 1) // fps.numerator
        if (
            sample_rate != 48000 or channels != 2 or evidence.get("input_sample_rate") != 32000
            or input_samples < 1 or resampled < 1 or trimmed < 0 or padded < 0
            or trimmed != max(0, resampled - samples)
            or padded != max(0, samples - resampled) or padded > max_pad
        ):
            raise VerificationError("native audio conversion sample counts contradict delivery")
    elif evidence.get("method") != "decoded-delivery-pcm-v1" or evidence.get("input_sample_rate") != sample_rate:
        raise VerificationError("generated audio conversion method is unsupported")
    if any(
        not isinstance(evidence.get(key), str)
        or len(evidence[key]) != 64
        or any(character not in "0123456789abcdef" for character in evidence[key])
        for key in digests
    ):
        raise VerificationError("generated audio conversion digest evidence is malformed")
    outputs = composition.get("generated_outputs")
    if isinstance(outputs, list):
        audio = [row for row in outputs if isinstance(row, Mapping) and row.get("role") == "audio"]
        if audio and (len(audio) != 1 or audio[0].get("sha256") != evidence["input_sha256"]):
            raise VerificationError("generated audio conversion input disagrees with output custody")


def _verify_exact_candidate(
    *,
    preparation: Mapping[str, Any],
    composition: Mapping[str, Any],
    artifact: Any,
    candidate_path: Path,
    source_path: Path | None,
    actual_digest: str,
) -> dict[str, Any]:
    delivery = composition.get("delivery_contract")
    if not isinstance(delivery, Mapping) or delivery.get("prepared_av_mask_digest") != artifact.artifact_digest:
        raise VerificationError("exact delivery contract is missing the prepared AV mask identity")
    try:
        baseline_identity = _baseline_identity_contract(preparation, artifact)
    except ValueError as exc:
        raise VerificationError(str(exc)) from exc
    if composition.get("prepared_av_mask_digest") != artifact.artifact_digest:
        raise VerificationError("composition prepared AV mask digest does not match preparation")
    fps, sample_rate = _exact_clock(artifact)
    frames, height, width = artifact.video_shape
    channels, samples = artifact.audio_shape
    permissions_video = artifact.video_delivery()
    permissions_audio = artifact.audio_delivery()
    protected_video = sum(1 for frame in permissions_video for row in frame for value in row if value == 0)
    protected_audio = sum(1 for channel in permissions_audio for value in channel if value == 0)
    anchors = _anchor_items(preparation, artifact)
    if not baseline_identity.get("members") and source_path is None and (protected_video or protected_audio):
        raise VerificationError("exact protected verification requires an authoritative source baseline")
    composition_method = composition.get("composition")
    if not isinstance(composition_method, Mapping):
        raise VerificationError("exact composition method evidence is missing")
    if composition_method.get("baseline_identity") != baseline_identity:
        raise VerificationError("exact composition baseline identity does not match preparation")
    baseline_representation = delivery.get("baseline_representation")
    if (
        not isinstance(baseline_representation, Mapping)
        or baseline_representation.get("identity") != baseline_identity
    ):
        raise VerificationError("exact delivery baseline identity does not match preparation")
    declared_counts = composition_method.get("protected_counts")
    if declared_counts != {"video_pixels": protected_video, "audio_samples": protected_audio}:
        raise VerificationError("exact protected permission counts do not match the prepared AV mask")
    _verify_audio_conversion_evidence(
        composition, composition_method, sample_rate=sample_rate, channels=channels,
        samples=samples, fps=fps,
    )
    if isinstance(composition.get("source"), Mapping) and source_path is not None:
        if composition["source"].get("sha256") != _sha256(source_path):
            raise VerificationError("authoritative source does not match composition evidence")
    if source_path is not None and artifact.source_baseline_digest:
        if artifact.source_baseline_digest.removeprefix("sha256:") != _sha256(source_path):
            raise VerificationError("authoritative source does not match prepared baseline digest")

    with tempfile.TemporaryDirectory(prefix="h3-av-verify-") as raw_root:
        root = Path(raw_root)
        candidate_video = root / "candidate-video.rgba"
        candidate_audio = root / "candidate-audio.s32le"
        try:
            _decode_exact_video(candidate_path, candidate_video, frames=frames, width=width, height=height, fps=fps)
            _decode_exact_audio(candidate_path, candidate_audio, samples=samples, sample_rate=sample_rate, channels=channels)
        except Exception as exc:  # noqa: BLE001 - fail-closed verification boundary
            raise VerificationError("candidate media is missing, short, corrupt, or has the wrong decoded format") from exc
        _verify_full_decoded_extent(
            candidate_path, root, frames=frames, width=width, height=height,
            samples=samples, channels=channels, sample_rate=sample_rate,
        )
        _verify_presentation_clock(
            candidate_path, frames=frames, fps=fps, samples=samples, sample_rate=sample_rate,
        )
        candidate_decoded_digests = {
            "composed_video_rgba_sha256": _sha256(candidate_video),
            "composed_audio_pcm_sha256": _sha256(candidate_audio),
        }
        source_video = root / "source-video.rgba"
        source_audio = root / "source-audio.s32le"
        try:
            source_asset_for_anchors = _primary_baseline_asset(preparation, artifact)
            source_video_anchor = any(
                str(item.get("asset")) == source_asset_for_anchors and item.get("modality") == "video"
                for _anchor, item in anchors
            )
            if baseline_identity.get("members"):
                from .baseline import render_timeline_baseline

                render_timeline_baseline(preparation, artifact, root, primary_source=source_path)
                source_video = root / "baseline.rgba"
                source_audio = root / "baseline.s32le"
            else:
                if source_path is not None and (protected_video or source_video_anchor):
                    frame_offset, _ = _exact_offsets(preparation, fps, sample_rate)
                    _decode_exact_video(source_path, source_video, frames=frames, width=width, height=height, fps=fps, start_frame=frame_offset)
                if source_path is not None and protected_audio:
                    _, sample_offset = _exact_offsets(preparation, fps, sample_rate)
                    _decode_exact_audio(source_path, source_audio, samples=samples, sample_rate=sample_rate, channels=channels, start_sample=sample_offset)
        except Exception as exc:  # noqa: BLE001 - fail-closed verification boundary
            raise VerificationError("authoritative source media is missing, short, corrupt, or has the wrong decoded format") from exc

        video_source_hash = hashlib.sha256()
        video_candidate_hash = hashlib.sha256()
        audio_source_hash = hashlib.sha256()
        audio_candidate_hash = hashlib.sha256()
        video_count = audio_count = video_mismatches = audio_mismatches = 0
        frame_bytes = width * height * 4
        assets = _asset_paths(preparation)
        source_asset = _primary_baseline_asset(preparation, artifact)
        anchor_baselines: dict[int, bytes] = {}
        for index, (anchor, item) in enumerate(anchors):
            frame = anchor.get("frame")
            if type(frame) is not int or not 0 <= frame < frames or anchor.get("exact_final_restoration") is not True:
                raise VerificationError(f"anchor {anchor.get('id')!r} is not accepted for exact restoration")
            if frame in anchor_baselines:
                raise VerificationError(f"anchors share output frame {frame}")
            expected = root / f"anchor-{index}.rgba"
            if source_path is not None and str(item.get("asset")) == source_asset and item.get("modality") == "video":
                with source_video.open("rb") as source_handle:
                    source_handle.seek(frame * frame_bytes)
                    expected.write_bytes(source_handle.read(frame_bytes))
            else:
                anchor_path = assets.get(str(item.get("asset")))
                if anchor_path is None:
                    raise VerificationError(f"anchor asset {item.get('asset')!r} is unavailable")
                _decode_anchor(anchor_path, expected, width=width, height=height)
            expected_bytes = expected.read_bytes()
            if len(expected_bytes) != frame_bytes:
                raise VerificationError(f"anchor {anchor.get('id')!r} is short or corrupt")
            anchor_baselines[frame] = expected_bytes
        if protected_video:
            with source_video.open("rb") as source_handle, candidate_video.open("rb") as candidate_handle:
                for frame_index, frame in enumerate(permissions_video):
                    source_frame = source_handle.read(frame_bytes)
                    candidate_frame = candidate_handle.read(frame_bytes)
                    expected_frame = anchor_baselines.get(frame_index, source_frame)
                    for row_index, row in enumerate(frame):
                        for column_index, permission in enumerate(row):
                            if permission:
                                continue
                            offset = (row_index * width + column_index) * 4
                            source_pixel = expected_frame[offset : offset + 4]
                            candidate_pixel = candidate_frame[offset : offset + 4]
                            video_source_hash.update(source_pixel)
                            video_candidate_hash.update(candidate_pixel)
                            video_count += 1
                            video_mismatches += source_pixel != candidate_pixel
        sample_bytes = channels * 4
        if protected_audio:
            with source_audio.open("rb") as source_handle, candidate_audio.open("rb") as candidate_handle:
                for sample_index in range(samples):
                    source_sample = source_handle.read(sample_bytes)
                    candidate_sample = candidate_handle.read(sample_bytes)
                    for channel in range(channels):
                        if permissions_audio[channel][sample_index]:
                            continue
                        offset = channel * 4
                        source_value = source_sample[offset : offset + 4]
                        candidate_value = candidate_sample[offset : offset + 4]
                        audio_source_hash.update(source_value)
                        audio_candidate_hash.update(candidate_value)
                        audio_count += 1
                        audio_mismatches += source_value != candidate_value

        anchor_report: list[dict[str, Any]] = []
        frame_bytes = width * height * 4
        with candidate_video.open("rb") as candidate_handle:
            for anchor, _item in anchors:
                frame = anchor.get("frame")
                if type(frame) is not int or not 0 <= frame < frames or anchor.get("exact_final_restoration") is not True:
                    raise VerificationError(f"anchor {anchor.get('id')!r} is not accepted for exact restoration")
                candidate_handle.seek(frame * frame_bytes)
                expected_bytes = anchor_baselines[frame]
                actual_bytes = candidate_handle.read(frame_bytes)
                if actual_bytes != expected_bytes:
                    raise VerificationError(f"anchor {anchor.get('id')!r} is not exactly restored")
                anchor_report.append({"id": str(anchor.get("id")), "frame": frame, "exact": True})

    declared_equality = composition.get("exact_equality")
    equality = {
        "video": {"protected_pixel_count": video_count, "mismatch_count": video_mismatches, "source_sha256": video_source_hash.hexdigest(), "candidate_sha256": video_candidate_hash.hexdigest()},
        "audio": {"protected_sample_count": audio_count, "mismatch_count": audio_mismatches, "source_sha256": audio_source_hash.hexdigest(), "candidate_sha256": audio_candidate_hash.hexdigest()},
        "anchors": anchor_report,
    }
    if declared_equality is not None and declared_equality != equality:
        raise VerificationError("exact equality evidence does not match fresh decoded verification")
    if video_mismatches or audio_mismatches:
        raise VerificationError("protected decoded pixels or PCM samples differ")
    for field, actual in candidate_decoded_digests.items():
        declared = composition_method.get(field)
        if not isinstance(declared, str) or declared != actual:
            raise VerificationError(f"candidate {field} does not match fresh decoded media")
    return {
        "schema_version": 1,
        "kind": "h3_av_verification",
        "request_digest": preparation.get("request_digest"),
        "candidate_sha256": actual_digest,
        "candidate": {"output_port": "verified_candidate", "ordinal": 0, "media_type": "video/x-matroska", "sha256": actual_digest, "size": candidate_path.stat().st_size},
        "preservation": {"status": "exact_delivery_domain", "video_pixels": video_count, "audio_samples": audio_count, "video_mismatches": video_mismatches, "audio_mismatches": audio_mismatches},
        "exact_equality": equality,
        "provenance": composition.get("provenance", {}),
        "lifecycle": {"prepared": True, "composed": True, "verified": True},
        "status": "verified",
    }


def verify_candidate(
    *,
    preparation: Mapping[str, Any],
    composition: Mapping[str, Any],
    candidate: str | Path | None = None,
    source: str | Path | None = None,
    baseline: str | Path | None = None,
) -> dict[str, Any]:
    """Verify artifact custody and concrete preservation evidence."""

    try:
        read_prepared_request(
            preparation.get("request"),
            preparation.get("request_digest"),
            require_normalized_v2=True,
        )
    except (TypeError, ValueError) as exc:
        raise VerificationError(f"preparation request is invalid: {exc}") from exc

    if preparation.get("status") != "prepared":
        raise VerificationError("preparation is not ready")
    if composition.get("status") != "composed":
        raise VerificationError("composition is not settled")
    _verify_provenance(preparation, composition)
    candidate_info = composition.get("candidate")
    if not isinstance(candidate_info, Mapping):
        raise VerificationError("composition is missing candidate evidence")
    if candidate is None:
        # Compatibility for direct/local callers only.  The managed executor
        # always supplies the host-staged candidate explicitly.
        candidate_path = Path(str(candidate_info.get("path", ""))).expanduser().resolve()
    else:
        candidate_path = Path(candidate).expanduser()
        if candidate_path.is_symlink():
            raise VerificationError("managed candidate may not be a symlink")
        candidate_path = candidate_path.resolve()
    if not candidate_path.is_file():
        raise VerificationError(f"candidate is missing: {candidate_path}")
    actual_digest = _sha256(candidate_path)
    if candidate_info.get("sha256") != actual_digest:
        raise VerificationError("candidate digest does not match composition evidence")
    if "size" in candidate_info and candidate_info.get("size") != candidate_path.stat().st_size:
        raise VerificationError("candidate size does not match composition evidence")

    artifact = _prepared_artifact(preparation)
    if artifact is not None:
        if source is not None and baseline is not None:
            raise VerificationError("source and baseline are mutually exclusive")
        if source is None:
            source = baseline
        source_path = None if source is None else Path(source).expanduser().resolve()
        if source_path is not None and not source_path.is_file():
            raise VerificationError(f"source is missing: {source_path}")
        return _verify_exact_candidate(
            preparation=preparation,
            composition=composition,
            artifact=artifact,
            candidate_path=candidate_path,
            source_path=source_path,
            actual_digest=actual_digest,
        )

    schedule = preparation["mask_schedule"]
    protected_video = schedule["video"]["protected_intervals"]
    protected_audio = schedule["audio"]["protected_intervals"]
    protected = {"video": protected_video, "audio": protected_audio}
    evidence = composition.get("preservation_evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    if source is not None and baseline is not None:
        raise VerificationError("source and baseline are mutually exclusive")
    if source is None:
        source = baseline
    source_path: Path | None = None
    if source is not None:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise VerificationError(f"source is missing: {source_path}")
    source_info = composition.get("source")
    if source_path is not None and isinstance(source_info, Mapping):
        if source_info.get("sha256") != _sha256(source_path):
            raise VerificationError("authoritative source does not match composition evidence")

    wholly_protected = (
        _covers_whole(protected_video, schedule.get("duration"))
        and _covers_whole(protected_audio, schedule.get("duration"))
    )
    if schedule.get("source_protected") or wholly_protected:
        if source_path is None:
            raise VerificationError("a source is required to verify a protected request")
        if not protected_video or not protected_audio:
            raise VerificationError("protected request has incomplete protected permissions")
        if _sha256(source_path) != actual_digest:
            raise VerificationError("fully protected candidate is not byte-identical to source")
        preservation_status = "exact_whole_file_match"
    elif protected_video or protected_audio:
        if source_path is None:
            raise VerificationError("partial preservation requires an authoritative source")
        if _probe(source_path) is None or _probe(candidate_path) is None:
            raise VerificationError("partial preservation requires decodable media, not a copied/non-media candidate")
        samples = evidence.get("protected_samples")
        if not isinstance(samples, Mapping):
            raise VerificationError("partial preservation requires protected_samples evidence")
        sample_evidence = {"video": samples.get("video", []), "audio": samples.get("audio", [])}
        _verify_sample_evidence(
            source=source_path,
            candidate=candidate_path,
            protected={**protected, "_evidence": sample_evidence},
            preparation=preparation,
        )
        preservation_status = "protected_sample_evidence"
    else:
        preservation_status = "no_protected_permissions"

    return {
        "schema_version": 1,
        "kind": "h3_av_verification",
        "request_digest": preparation.get("request_digest"),
        "candidate_sha256": actual_digest,
        "candidate": {"output_port": "verified_candidate", "ordinal": 0, "media_type": "video/x-matroska", "sha256": actual_digest, "size": candidate_path.stat().st_size},
        "preservation": {"status": preservation_status, "video": protected_video, "audio": protected_audio},
        "provenance": composition.get("provenance", {}),
        "lifecycle": {"prepared": True, "composed": True, "verified": True},
        "status": "verified",
    }


__all__ = ["VerificationError", "verify_candidate"]
