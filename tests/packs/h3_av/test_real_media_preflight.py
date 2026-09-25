from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrid.packs.vibecomfy import invocation_preflight
from astrid.packs.vibecomfy.executors.run import run as worker_run


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg and ffprobe are required for real media preflight tests",
)


def _ffmpeg(*arguments: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *arguments],
        check=True,
        capture_output=True,
    )


def _write_cfr(path: Path, *, rate: str = "24", duration: str = "1") -> None:
    _ffmpeg(
        "-f", "lavfi",
        "-i", f"color=c=blue:s=16x16:r={rate}",
        "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=32000",
        "-t", duration,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(path),
    )


def _write_vfr(path: Path) -> None:
    first = path.with_name("vfr-first.mp4")
    second = path.with_name("vfr-second.mp4")
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=blue:s=16x16:r=24", "-t", "0.5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(first),
    )
    _ffmpeg(
        "-f", "lavfi", "-i", "color=c=red:s=16x16:r=12", "-t", "0.5",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(second),
    )
    concat = path.with_name("vfr-input.txt")
    concat.write_text(f"file '{first}'\nfile '{second}'\n", encoding="utf-8")
    _ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(path))


def _write_short_audio(path: Path) -> None:
    _ffmpeg(
        "-f", "lavfi",
        "-i", "color=c=blue:s=16x16:r=24",
        "-f", "lavfi",
        "-i", "sine=frequency=440:sample_rate=32000",
        "-filter_complex", "[1:a]atrim=duration=0.7[a]",
        "-map", "0:v",
        "-map", "[a]",
        "-t", "1",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(path),
    )


def _loaded_h3_workflow() -> SimpleNamespace:
    class Workflow:
        inputs = {
            "source_video": SimpleNamespace(
                node_id="7", field="video", media_semantics="video"
            )
        }
        outputs = [SimpleNamespace(node_id="3")]
        edges = [SimpleNamespace(from_node="7", to_node="3")]

        def compile(self, _kind: str, *, run_inputs: dict[str, object]) -> dict[str, object]:
            return {
                "7": {
                    "class_type": "H3LoadVideo",
                    "inputs": {"video": run_inputs["source_video"]},
                },
                "3": {"class_type": "H3Output", "inputs": {}},
            }

    return SimpleNamespace(
        resolved=SimpleNamespace(
            workflow=Workflow(),
            workflow_identity="h3-media-fixture",
            revision_id="rev-1",
            semantic_digest="sha256:" + "1" * 64,
        ),
        workflow_content_digest="sha256:" + "2" * 64,
    )


def _assert_worker_rejects_before_production(
    media: Path,
    workflow_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    match: str,
) -> None:
    monkeypatch.setattr(
        "astrid.packs.vibecomfy.production_engine.load_workflow_path",
        lambda *_args, **_kwargs: _loaded_h3_workflow(),
    )
    production = Mock(side_effect=AssertionError("production execution was reached"))
    monkeypatch.setattr(
        "astrid.packs.vibecomfy.production_engine.run_workflow_result_path",
        production,
    )

    with pytest.raises(invocation_preflight.InvocationPreflightError, match=match):
        worker_run._run_and_settle(
            workflow_path,
            tmp_path / "run",
            task_identity="task-1",
            source_video=str(media),
            source_video_node="7",
        )

    production.assert_not_called()


def test_worker_rejects_real_23_98_cfr_source_before_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "cfr-2398.mp4"
    _write_cfr(media, rate="24000/1001")
    workflow = tmp_path / "workflow.py"
    workflow.write_text("workflow = 'fixture'", encoding="utf-8")

    _assert_worker_rejects_before_production(
        media, workflow, tmp_path, monkeypatch, match="H3_SOURCE_AV_RATE"
    )


def test_worker_rejects_real_vfr_source_before_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "vfr.mp4"
    _write_vfr(media)
    workflow = tmp_path / "workflow.py"
    workflow.write_text("workflow = 'fixture'", encoding="utf-8")

    _assert_worker_rejects_before_production(
        media, workflow, tmp_path, monkeypatch, match="H3_SOURCE_AV_RATE"
    )


def test_worker_rejects_real_audio_duration_mismatch_before_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "short-audio.mp4"
    _write_short_audio(media)
    workflow = tmp_path / "workflow.py"
    workflow.write_text("workflow = 'fixture'", encoding="utf-8")

    _assert_worker_rejects_before_production(
        media, workflow, tmp_path, monkeypatch, match="H3_SOURCE_AV_MISMATCH"
    )
