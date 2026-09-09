from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from astrid.packs.wan2gp.src.compiler import (
    compile_from_inputs,
    portable_digest,
    runner_fingerprint,
    warmth_identity,
)
from astrid.packs.wan2gp.src.driver import (
    CancellationPolicy,
    CancellationToken,
    FakePersistentRunner,
    PersistentRunnerState,
    _canonicalize_generated_files,
)


@pytest.fixture
def settings() -> dict[str, object]:
    return compile_from_inputs(
        {
            "prompt": "a paper kite over a quiet lake",
            "model": "wan-2.2",
            "resolution": "320x240",
            "frames": 3,
            "fps": 12,
            "seed": 17,
            "wan2gp_path": "/machine/checkout-a",
            "attempt_root": "/machine/attempt-a",
        }
    )


def test_cancellation_token_is_cooperative_and_idempotent() -> None:
    token = CancellationToken()
    assert token.cancelled is False
    assert token.cancel("fixture stop") is True
    assert token.cancel("ignored second stop") is False
    assert token.cancelled is True
    assert token.reason == "fixture stop"
    with pytest.raises(RuntimeError, match="fixture stop"):
        token.raise_if_cancelled()


def test_fake_cancellation_leaves_persistent_runner_warm(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    state_path = tmp_path / "runner-state.jsonl"
    runner = FakePersistentRunner(state_path, output_root=tmp_path / "outputs")

    result = runner.run(
        settings,
        policy=CancellationPolicy(cancel_after_steps=1),
        work_steps=3,
    )

    assert result.status == "cancelled"
    assert result.cancelled is True
    assert result.generated_files == []
    assert result.runner_alive is True
    assert result.state.status == PersistentRunnerState.WARM
    events = [json.loads(line) for line in state_path.read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "runner_created",
        "runner_started",
        "run_started",
        "run_cancelled",
    ]
    assert events[-1]["reason"] == "cancelled by policy at step 1"


def test_persistent_state_reopens_and_reuses_warm_identity(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    state_path = tmp_path / "runner-state.jsonl"
    output_root = tmp_path / "outputs"
    first = FakePersistentRunner(state_path, output_root=output_root, runner_id="fixture-runner")
    first_result = first.run(settings, fixture={"fixture": "one"})
    assert first_result.status == "succeeded"
    assert first.is_alive() is True

    reopened_state = PersistentRunnerState.load(state_path)
    assert reopened_state.snapshot.status == PersistentRunnerState.WARM
    assert reopened_state.is_alive() is True
    second = FakePersistentRunner(
        state_path,
        output_root=output_root,
        runner_id="fixture-runner",
    )
    second_result = second.run(settings, output_name="second.json", fixture={"fixture": "two"})
    assert second_result.status == "succeeded"
    assert second_result.fingerprint == first_result.fingerprint
    assert second_result.warmth_identity == first_result.warmth_identity
    assert second_result.state.total_runs == 2
    assert second_result.state.successful_runs == 2
    assert second_result.state.status == PersistentRunnerState.WARM
    assert json.loads((output_root / "second.json").read_text()) == {"fixture": "two"}


def test_runner_and_warmth_identity_are_portable_and_deterministic(
    settings: dict[str, object],
) -> None:
    relocated = dict(settings)
    relocated.update(
        {
            "wan2gp_path": "/another/machine/checkout",
            "attempt_root": "/another/machine/attempt",
            "device": "cuda:7",
        }
    )
    assert portable_digest(settings) == portable_digest(relocated)
    assert runner_fingerprint(settings) == runner_fingerprint(relocated)
    assert warmth_identity(settings, warmth_profile="cpu-fake") == warmth_identity(
        relocated, warmth_profile="cpu-fake"
    )
    assert warmth_identity(settings, warmth_profile="cpu-fake") != warmth_identity(
        settings, warmth_profile="cpu-fake-v2"
    )
    assert runner_fingerprint(settings) == runner_fingerprint(settings)


def test_fake_output_containment_rejects_escape_without_writing_outside(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    state_path = tmp_path / "runner-state.jsonl"
    output_root = tmp_path / "outputs"
    runner = FakePersistentRunner(state_path, output_root=output_root)

    result = runner.run(settings, escape_output=True)

    escaped = tmp_path / "escaped-fake-output.json"
    assert result.status == "failed"
    assert result.containment_ok is False
    assert result.generated_files == []
    assert "output containment violated" in result.errors[0]
    assert escaped.exists() is False
    assert result.runner_alive is True
    assert runner.state.snapshot.failed_runs == 1


def test_one_shot_cancellation_is_structured_before_engine_lookup(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    from astrid.packs.wan2gp.src.driver import one_shot_run

    result = one_shot_run(
        settings=settings,
        attempt_root=tmp_path / "attempt",
        wan2gp_root=tmp_path / "missing-engine",
        cancelled=lambda: True,
    )
    assert result.success is False
    assert result.errors == ["cancelled: cancelled"]
    assert result.spool == (tmp_path / "attempt").resolve()


def test_generate_core_fail_closes_success_without_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from argparse import Namespace

    from astrid.packs.wan2gp.executors.generate_video.run import generate_core
    from astrid.packs.wan2gp.src.driver import DriverResult

    def fake_one_shot_run(**_kwargs):
        spool = tmp_path / "spool"
        spool.mkdir(parents=True, exist_ok=True)
        return DriverResult(
            success=True,
            generated_files=[],
            errors=[],
            total_tasks=1,
            successful_tasks=1,
            failed_tasks=0,
            disclosed_engine={"engine": "wan2gp", "route": "owned"},
            spool=spool,
        )

    monkeypatch.setattr(
        "astrid.packs.wan2gp.executors.generate_video.run.one_shot_run",
        fake_one_shot_run,
    )
    code, payload = generate_core(
        Namespace(
            prompt="a kite",
            model="wan-2.2",
            negative_prompt=None,
            resolution="512x512",
            video_length=9,
            fps="8",
            seed=7,
            guidance_scale=5.0,
            num_inference_steps=4,
            loras=None,
            out=tmp_path / "spool",
            wan2gp_path=None,
        )
    )
    assert code == 1
    assert payload["ok"] is False
    assert "no files" in str(payload["error"])


def test_generate_core_receipt_identifies_video_collection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from argparse import Namespace

    from astrid.packs.wan2gp.executors.generate_video.run import generate_core
    from astrid.packs.wan2gp.src.driver import DriverResult

    spool = tmp_path / "spool"

    def fake_one_shot_run(**_kwargs):
        spool.mkdir(parents=True, exist_ok=True)
        clips = [spool / "first.mp4", spool / "second.mp4"]
        source = Path(__file__).parent / "fixtures" / "reshape" / "hype_regression" / "main.mp4"
        for clip in clips:
            shutil.copyfile(source, clip)
        return DriverResult(
            success=True,
            generated_files=[str(clip) for clip in clips],
            errors=[],
            total_tasks=2,
            successful_tasks=2,
            failed_tasks=0,
            disclosed_engine={"engine": "wan2gp", "route": "owned"},
            spool=spool,
        )

    monkeypatch.setattr(
        "astrid.packs.wan2gp.executors.generate_video.run.one_shot_run",
        fake_one_shot_run,
    )
    code, payload = generate_core(
        Namespace(
            prompt="a kite",
            model="wan-2.2",
            negative_prompt=None,
            resolution="512x512",
            video_length=9,
            fps="8",
            seed=7,
            guidance_scale=5.0,
            num_inference_steps=4,
            loras=None,
            out=spool,
            wan2gp_path=None,
        )
    )

    assert code == 0
    outputs = payload["manifest"]["outputs"]
    assert [entry["name"] for entry in outputs] == [
        "generated_videos",
        "generated_videos",
    ]
    assert [entry["ordinal"] for entry in outputs] == [0, 1]
    assert [entry["role"] for entry in outputs] == ["result", "result"]
    assert [entry["is_primary"] for entry in outputs] == [True, False]
    assert all(entry["content_hash"].startswith("sha256:") for entry in outputs)
    assert all(entry["bytes"] > 0 for entry in outputs)


def test_generated_mp4_wall_clock_comments_canonicalize_to_equal_digest(
    tmp_path: Path,
) -> None:
    mutagen_mp4 = pytest.importorskip("mutagen.mp4")
    source = Path(__file__).parent / "fixtures" / "reshape" / "hype_regression" / "main.mp4"
    cold = tmp_path / "cold.mp4"
    warm = tmp_path / "warm.mp4"
    shutil.copyfile(source, cold)
    shutil.copyfile(source, warm)

    timestamps = ("2026-09-08T10:00:00.000000Z", "2026-09-08T10:00:01.000000Z")
    for path, timestamp in zip((cold, warm), timestamps, strict=True):
        media = mutagen_mp4.MP4(path)
        if media.tags is None:
            media.add_tags()
        media.tags["©cmt"] = [
            json.dumps(
                {
                    "creation_date": timestamp,
                    "creation_timestamp": timestamp,
                    "generation_time": timestamp,
                    "prompt": "fixed prompt",
                }
            )
        ]
        media.save()

    before = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (cold, warm)]
    assert before[0] != before[1]

    _canonicalize_generated_files([str(cold), str(warm)])

    after = [hashlib.sha256(path.read_bytes()).hexdigest() for path in (cold, warm)]
    assert after[0] == after[1]
    assert mutagen_mp4.MP4(cold).tags["©cmt"] == ['{"prompt":"fixed prompt"}']
