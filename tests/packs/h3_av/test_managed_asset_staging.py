from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from astrid.packs.h3_av.src.compile import _DEFAULT_PROMPT, compile_preparation
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.vibecomfy.executors.run import run
from astrid.packs.vibecomfy.executors.run.run import _stage_managed_assets


def _readiness_profile(tmp_path: Path) -> tuple[str, str]:
    profile_path = tmp_path / "readiness-profile.json"
    profile_bytes = json.dumps({"vibecomfy_session": {}}).encode("utf-8")
    profile_path.write_bytes(profile_bytes)
    profile_hash = "sha256:" + hashlib.sha256(profile_bytes).hexdigest()
    return str(profile_path), profile_hash


def test_compiler_archive_stages_to_comfy_input(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    request = normalize_request(
        {
            "version": 1,
            "operation": "continue",
            "source": {"asset": "source", "range": [0, 1]},
            "output": {"duration": 2},
            "content": {"prompt": _DEFAULT_PROMPT},
            "changes": {
                "video": [{"during": [1, 2], "area": {"full_frame": True}, "action": "generate"}],
                "audio": [{"during": [1, 2], "action": "generate"}],
            },
            "references": [],
            "overrides": {},
        }
    )
    compiled = compile_preparation(
        prepare_request(request, asset_map={"source": str(source)}),
        out_dir=tmp_path / "compiled",
    )

    bindings = _stage_managed_assets(
        compiled["managed_assets"]["path"],
        readiness_profile=None,
        output_root=tmp_path / "run",
    )

    assert bindings == {"source_video": compiled["workflow_inputs"]["source_video"]}
    assert (tmp_path / "run" / "engine-input" / bindings["source_video"]).read_bytes() == b"fixture-video"


def test_run_accepts_matching_workflow_and_managed_asset_binding(
    tmp_path: Path, monkeypatch,
) -> None:
    workflow = tmp_path / "workflow.py"
    workflow.write_text("# fixture\n", encoding="utf-8")
    engine_output = tmp_path / "run" / "engine-output" / "result.mp4"
    engine_output.parent.mkdir(parents=True)
    engine_output.write_bytes(b"result")
    monkeypatch.setattr(run, "_stage_managed_assets", lambda *_args, **_kwargs: {"source_video": "source.mp4"})
    monkeypatch.setattr(run, "_source_video_input_directory", lambda *_args, **_kwargs: tmp_path)
    preflight = Mock()
    monkeypatch.setattr("astrid.packs.vibecomfy.invocation_preflight.preflight_invocation", preflight)
    managed_run = Mock(return_value=(engine_output,))
    monkeypatch.setattr("astrid.packs.vibecomfy.production_engine.run_workflow_path", managed_run)
    readiness_profile_path, readiness_profile_hash = _readiness_profile(tmp_path)

    run._run_and_settle(
        workflow,
        tmp_path / "run",
        task_identity="task-1",
        readiness_profile_path=readiness_profile_path,
        readiness_profile_hash=readiness_profile_hash,
        managed_assets=str(tmp_path / "managed-assets.zip"),
        workflow_inputs=json.dumps({"source_video": "source.mp4"}),
    )

    assert managed_run.call_args.kwargs["workflow_input_bindings"] == {
        "source_video": "source.mp4"
    }
    assert preflight.call_args.kwargs["run_inputs"] == {"source_video": "source.mp4"}


def test_run_rejects_different_workflow_and_managed_asset_binding(
    tmp_path: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(run, "_stage_managed_assets", lambda *_args, **_kwargs: {"source_video": "staged.mp4"})
    readiness_profile_path, readiness_profile_hash = _readiness_profile(tmp_path)

    with pytest.raises(ValueError, match="managed assets conflict with workflow inputs: source_video"):
        run._run_and_settle(
            tmp_path / "workflow.py",
            tmp_path / "run",
            task_identity="task-1",
            readiness_profile_path=readiness_profile_path,
            readiness_profile_hash=readiness_profile_hash,
            managed_assets=str(tmp_path / "managed-assets.zip"),
            workflow_inputs=json.dumps({"source_video": "different.mp4"}),
        )
