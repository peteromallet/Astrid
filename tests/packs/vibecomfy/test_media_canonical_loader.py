from __future__ import annotations

from pathlib import Path

import pytest

vibecomfy = pytest.importorskip("vibecomfy")

from astrid.packs.vibecomfy.media.compiler import (  # noqa: E402
    CharacterAnimationRequest,
    VideoEnhanceRequest,
    compile_character_animation,
    compile_video_enhance,
)
from astrid.packs.vibecomfy.production_engine import _load_workflow  # noqa: E402


def test_bounded_video_profile_uses_canonical_ready_loader(tmp_path: Path) -> None:
    compiled = compile_video_enhance(VideoEnhanceRequest(video_ref="/cas/source.mp4"))

    workflow = _load_workflow(
        {"template_id": compiled.template_id, "bindings": dict(compiled.bindings)},
        {},
        tmp_path,
    )
    api = workflow.compile("api")

    assert workflow.metadata["ready_template"] == "video/basic_video_enhance"
    assert api["1"]["inputs"]["video"] == "/cas/source.mp4"
    assert api["2"]["inputs"]["scale_by"] == 2.0
    assert api["3"]["inputs"]["audio"] == ["1", 2]
    assert api["3"]["inputs"]["frame_rate"] == ["1", 3]


def test_bounded_character_profile_uses_canonical_two_media_bindings(tmp_path: Path) -> None:
    compiled = compile_character_animation(
        CharacterAnimationRequest(
            reference_image_ref="/cas/reference.png",
            driving_video_ref="/cas/motion.mp4",
            mode="animate",
            resolution="720p",
            prompt="walk forward",
            negative_prompt="blurry",
            seed=7,
            frames=41,
            fps=24,
            steps=4,
        )
    )

    workflow = _load_workflow(
        {"template_id": compiled.template_id, "bindings": dict(compiled.bindings)},
        {},
        tmp_path,
    )
    api = workflow.compile("api")

    assert workflow.metadata["ready_template"] == "video/wan22_animate_native_first_stage"
    assert api["4"]["inputs"]["image"] == "/cas/reference.png"
    assert api["7"]["inputs"]["file"] == "/cas/motion.mp4"
    assert api["15"]["inputs"]["width"] == 1280
    assert api["15"]["inputs"]["height"] == 720
    assert api["25"]["inputs"]["seed"] == 7
    assert api["25"]["inputs"]["steps"] == 4
