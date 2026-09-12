from types import SimpleNamespace

from astrid.core.execution.generic_host import GenericPackHost, _settlement_media_type


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


def test_upload_boundary_preserves_filename_for_video_mime_mapping(tmp_path) -> None:
    output = tmp_path / "render.mp4"
    output.write_bytes(b"video")

    class Client:
        INLINE_SETTLEMENT_OUTPUTS = False

        def upload_object(self, path, *, project_id, media_type, filename=None):
            return SimpleNamespace(
                digest="sha256:" + "0" * 64,
                size=path.stat().st_size,
                project_id=project_id,
                media_type=media_type,
                filename=filename,
            )

    host = object.__new__(GenericPackHost)
    host.client = Client()
    uploaded = host._upload_outputs(
        [
            {
                "name": "video",
                "artifact_type": "clip/visual",
                "path": str(output),
                "filename": "render.mp4",
            }
        ],
        project_id="project",
    )
    assert uploaded[0]["media_type"] == "video/mp4"
