from pathlib import Path

import pytest
from PIL import Image

from astrid.core.execution.thumbnails import (
    THUMBNAIL_MAX_EDGE,
    ThumbnailError,
    UnsupportedThumbnailMedia,
    extract_thumbnail,
)


def test_extract_thumbnail_downsizes_image_and_flattens_alpha(tmp_path: Path):
    source = tmp_path / "source.png"
    destination = tmp_path / "thumb.jpg"
    image = Image.new("RGBA", (900, 450), (255, 0, 0, 128))
    image.save(source)

    result = extract_thumbnail(source, destination, "image/png")

    assert result.media_type == "image/jpeg"
    assert result.width == THUMBNAIL_MAX_EDGE
    assert result.height == 160
    assert destination.stat().st_size > 0
    with Image.open(destination) as output:
        assert output.format == "JPEG"
        assert output.size == (THUMBNAIL_MAX_EDGE, 160)


def test_extract_thumbnail_rejects_nonvisual_media(tmp_path: Path):
    source = tmp_path / "audio.bin"
    source.write_bytes(b"audio")

    with pytest.raises(UnsupportedThumbnailMedia):
        extract_thumbnail(source, tmp_path / "thumb.jpg", "audio/mpeg")


def test_extract_thumbnail_converts_pillow_decompression_bomb_to_bounded_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    source = tmp_path / "oversized.png"
    source.write_bytes(b"image bytes")

    def raise_decompression_bomb(_source: Path):
        raise Image.DecompressionBombError("image is too large")

    monkeypatch.setattr(Image, "open", raise_decompression_bomb)

    with pytest.raises(ThumbnailError, match="could not decode image oversized.png"):
        extract_thumbnail(source, tmp_path / "thumb.jpg", "image/png")


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg is required")
def test_extract_thumbnail_extracts_video_frame(tmp_path: Path):
    source = tmp_path / "source.mp4"
    destination = tmp_path / "thumb.jpg"
    import subprocess

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=640x360:d=0.2",
            "-pix_fmt", "yuv420p", str(source),
        ],
        check=True,
    )

    result = extract_thumbnail(source, destination, "video/mp4")

    assert result.media_type == "image/jpeg"
    assert result.width <= THUMBNAIL_MAX_EDGE
    assert result.height <= THUMBNAIL_MAX_EDGE
    with Image.open(destination) as output:
        assert output.format == "JPEG"
