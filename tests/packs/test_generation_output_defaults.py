"""Generation executors must never invent a cwd-relative output location."""

from __future__ import annotations

from astrid.packs.generation.executors.generate_audio.run import (
    build_parser as build_audio_parser,
)
from astrid.packs.generation.executors.generate_image.run import (
    build_parser as build_image_parser,
)
from astrid.packs.generation.executors.generate_image_openai.run import (
    build_parser as build_openai_parser,
)
from astrid.packs.generation.executors.generate_video.run import (
    build_parser as build_video_parser,
)


def test_generation_parsers_have_no_implicit_cwd_output(monkeypatch, tmp_path):
    """Managed callers supply host staging; direct callers must choose output."""
    monkeypatch.chdir(tmp_path)

    image = build_image_parser().parse_args(
        ["--model", "flux-dev", "--mode", "t2i", "--execution", "cloud", "--prompt", "test"]
    )
    video = build_video_parser().parse_args(
        ["--model", "wan-2.2", "--mode", "t2v", "--execution", "cloud", "--prompt", "test"]
    )
    audio = build_audio_parser().parse_args(
        ["--model", "stable-audio-3-medium", "--mode", "music", "--execution", "cloud", "--prompt", "test"]
    )
    openai = build_openai_parser().parse_args(["--prompt", "test"])

    assert image.out is None
    assert video.out is None
    assert audio.out is None
    assert openai.out_dir is None
