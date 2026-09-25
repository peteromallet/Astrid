from __future__ import annotations

import hashlib
import importlib.util
import json
import mimetypes
from pathlib import Path
import subprocess

import pytest

from astrid.core.execution import t9_model_substitute as substitute


def _profile(source: Path) -> dict[str, object]:
    digest = "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
    return {
        "t9_model_substitute": {
            "approved": True,
            "mode": "deterministic_cpu_model_boundary_v1",
            "source_path": str(source),
            "source_sha256": digest,
        }
    }


def test_approved_source_requires_exact_hash_and_explicit_approval(tmp_path: Path) -> None:
    source = tmp_path / "sitecustomize.py"
    source.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    assert substitute.approved_source(_profile(source)) == (
        source.resolve(),
        "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    profile = _profile(source)
    source.write_text("changed\n", encoding="utf-8")
    with pytest.raises(substitute.T9SubstituteError, match="hash"):
        substitute.approved_source(profile)


def test_child_marker_must_match_approved_source(tmp_path: Path) -> None:
    source = tmp_path / "sitecustomize.py"
    source.write_text("hook\n", encoding="utf-8")
    marker = tmp_path / "activated.json"
    environment = {
        substitute.SOURCE_ENV: str(source),
        substitute.HASH_ENV: "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest(),
        substitute.MARKER_ENV: str(marker),
    }
    marker.write_text(json.dumps({"source": str(source.resolve()), "sha256": environment[substitute.HASH_ENV]}), encoding="utf-8")
    substitute.require_active_marker(environment)
    marker.unlink()
    with pytest.raises(substitute.T9SubstituteError, match="marker is missing"):
        substitute.require_active_marker(environment)


def test_approved_fixture_emits_one_muxed_mp4_with_audio_and_no_wav(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture_root = next(
        (
            parent / ".otto/runs/h3-transform-pack-20260923/fixtures/t9-public-h3-20260925-9"
            for parent in Path(__file__).resolve().parents
            if (parent / ".otto/runs/h3-transform-pack-20260923/fixtures/t9-public-h3-20260925-9/model-stub/site-packages/sitecustomize.py").is_file()
        ),
        None,
    )
    if fixture_root is None:
        pytest.skip("the approved T9 fixture is not present in this checkout")

    source = fixture_root / "model-stub/site-packages/sitecustomize.py"
    spec = importlib.util.spec_from_file_location("t9_test_sitecustomize", source)
    assert spec is not None and spec.loader is not None
    hook = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hook)

    workflow = tmp_path / "compiled-workflow.json"
    workflow.write_text("{}", encoding="utf-8")
    output_root = tmp_path / "private-output"
    monkeypatch.setenv("ASTRID_T9_MODEL_SUBSTITUTE_CALLS", str(tmp_path / "calls.jsonl"))
    result = hook._stub_run(
        workflow,
        output_root,
        task_identity="test-task",
        attempt_identity="test-attempt",
        profile_id="t9_cpu_stub",
    )

    assert len(result.outputs) == 1
    output = Path(result.outputs[0])
    assert output.name == "t9-deterministic-av.mp4"
    assert mimetypes.guess_type(output.name)[0] == "video/mp4"
    assert not list(output_root.rglob("*.wav"))
    assert sorted(path.name for path in output_root.iterdir()) == [output.name]

    probe = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames", "-show_streams", "-show_format",
            "-of", "json", str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    streams = metadata["streams"]
    video = [stream for stream in streams if stream["codec_type"] == "video"]
    audio = [stream for stream in streams if stream["codec_type"] == "audio"]
    assert len(video) == len(audio) == 1
    assert metadata["format"]["format_name"].startswith("mov,mp4")
    assert (video[0]["width"], video[0]["height"], video[0]["avg_frame_rate"]) == (1024, 576, "24/1")
    assert video[0]["nb_read_frames"] == "360"
    assert (audio[0]["sample_rate"], audio[0]["channels"]) == ("48000", 2)

    decoded_audio = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(output), "-map", "0:a:0", "-f", "s16le", "-acodec", "pcm_s16le", "pipe:1"],
        check=True,
        capture_output=True,
    )
    assert len(decoded_audio.stdout) == 15 * 48_000 * 2 * 2
