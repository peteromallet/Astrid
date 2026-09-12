from astrid.core.execution.generic_host import _settlement_media_type


def test_clip_visual_video_outputs_publish_mime_type_by_filename() -> None:
    assert _settlement_media_type(
        {"artifact_type": "clip/visual", "filename": "render.mp4"}
    ) == "video/mp4"
    assert _settlement_media_type(
        {"artifact_type": "clip/visual", "filename": "render.mov"}
    ) == "video/quicktime"


def test_explicit_media_type_wins_over_artifact_semantics() -> None:
    assert _settlement_media_type(
        {
            "artifact_type": "clip/visual",
            "filename": "render.mp4",
            "media_type": "video/custom",
        }
    ) == "video/custom"
