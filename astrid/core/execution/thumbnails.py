"""Small, deterministic thumbnails for visual task outputs.

This module deliberately knows only about local media bytes and MIME types. It
does not know about a pack, model, task, Runtime, or storage provider. The
generic host owns when the helper is called and how the resulting file is
published.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

THUMBNAIL_RECIPE_VERSION = 1
THUMBNAIL_MAX_EDGE = 320
THUMBNAIL_JPEG_QUALITY = 85
THUMBNAIL_FFMPEG_TIMEOUT_SECONDS = 10
THUMBNAIL_MAX_BYTES = 512 * 1024


class ThumbnailError(RuntimeError):
    """A bounded, user-actionable thumbnail extraction failure."""


class UnsupportedThumbnailMedia(ThumbnailError):
    """The source is not a visual MIME type supported by this helper."""


@dataclass(frozen=True)
class ThumbnailResult:
    path: Path
    media_type: str
    width: int
    height: int
    recipe_version: int = THUMBNAIL_RECIPE_VERSION


def is_visual_media_type(media_type: str | None) -> bool:
    normalized = str(media_type or "").strip().lower()
    return normalized.startswith("image/") or normalized.startswith("video/")


def _resize_for_thumbnail(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image)
    if getattr(image, "is_animated", False):
        image.seek(0)
    if image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGBA")
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((THUMBNAIL_MAX_EDGE, THUMBNAIL_MAX_EDGE), Image.Resampling.LANCZOS)
    return image


def _write_image_thumbnail(source: Path, destination: Path) -> tuple[int, int]:
    try:
        with Image.open(source) as image:
            thumbnail = _resize_for_thumbnail(image)
            width, height = thumbnail.size
            thumbnail.save(
                destination,
                format="JPEG",
                quality=THUMBNAIL_JPEG_QUALITY,
                optimize=True,
                progressive=True,
            )
    except (Image.DecompressionBombError, OSError, ValueError, SyntaxError) as exc:
        raise ThumbnailError(f"could not decode image {source.name}: {exc}") from exc
    return width, height


def _write_video_thumbnail(source: Path, destination: Path, ffmpeg: str) -> tuple[int, int]:
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        "0.001",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        "scale=w='min(320,iw)':h='min(320,ih)':force_original_aspect_ratio=decrease",
        "-f",
        "image2",
        str(destination),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=THUMBNAIL_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise ThumbnailError(f"video thumbnail extraction timed out for {source.name}") from exc
    except OSError as exc:
        raise ThumbnailError(f"could not start ffmpeg for {source.name}: {exc}") from exc
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or "ffmpeg produced no frame").strip()[-500:]
        raise ThumbnailError(f"could not decode video {source.name}: {detail}")
    try:
        with Image.open(destination) as image:
            image.load()
            width, height = image.size
    except (OSError, ValueError, SyntaxError) as exc:
        raise ThumbnailError(f"ffmpeg produced an invalid thumbnail for {source.name}: {exc}") from exc
    return width, height


def extract_thumbnail(
    source: Path,
    destination: Path,
    media_type: str,
    *,
    ffmpeg_path: str | None = None,
) -> ThumbnailResult:
    """Extract a bounded JPEG thumbnail from one local visual media file."""

    source = Path(source)
    destination = Path(destination)
    normalized_type = str(media_type or "").strip().lower()
    if not source.is_file():
        raise ThumbnailError(f"thumbnail source does not exist: {source}")
    if normalized_type.startswith("image/"):
        destination.parent.mkdir(parents=True, exist_ok=True)
        width, height = _write_image_thumbnail(source, destination)
    elif normalized_type.startswith("video/"):
        ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
        if not ffmpeg:
            raise ThumbnailError("ffmpeg is required for video thumbnail extraction")
        destination.parent.mkdir(parents=True, exist_ok=True)
        width, height = _write_video_thumbnail(source, destination, ffmpeg)
    else:
        raise UnsupportedThumbnailMedia(normalized_type or "missing media type")

    size = destination.stat().st_size
    if size <= 0 or size > THUMBNAIL_MAX_BYTES:
        raise ThumbnailError(
            f"thumbnail size {size} is outside the allowed range 1..{THUMBNAIL_MAX_BYTES}"
        )
    return ThumbnailResult(
        path=destination,
        media_type="image/jpeg",
        width=width,
        height=height,
    )
