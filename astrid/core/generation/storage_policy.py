"""Versioned resource ceilings for narrowly admitted image routes.

The policy in this module is a hard upper bound, not a claim about typical
provider usage.  A producer may advertise these numbers only when the
executor enforces the same limits before settlement.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, Mapping


class ImageStoragePolicyError(ValueError):
    """Raised when a request or provider result is outside the bounded profile."""


@dataclass(frozen=True, slots=True)
class CloudI2IStoragePolicy:
    """The first bounded cloud image-to-image execution profile."""

    version: str = "astrid.cloud-i2i.z-image.v1"
    source_max_bytes: int = 512_000
    output_max_bytes: int = 64 * 1024 * 1024
    manifest_max_bytes: int = 1 * 1024 * 1024
    control_max_bytes: int = 1 * 1024 * 1024
    max_prompt_chars: int = 4_096
    max_width: int = 2_048
    max_height: int = 2_048
    max_count: int = 1

    @property
    def estimated_output_bytes(self) -> int:
        """Maximum final image plus the published result manifest."""
        return self.output_max_bytes + self.manifest_max_bytes

    @property
    def estimated_scratch_bytes(self) -> int:
        """Input, staged/temporary copies, and bounded control evidence.

        The two output terms cover the downloaded/staged copy and the
        sibling temporary copy used by metadata embedding.  Published output
        remains a separate settlement estimate.
        """
        return (
            self.source_max_bytes
            + 2 * self.output_max_bytes
            + self.manifest_max_bytes
            + self.control_max_bytes
        )

    @property
    def estimate(self) -> dict[str, int]:
        return {
            "scratch_bytes": self.estimated_scratch_bytes,
            "output_bytes": self.estimated_output_bytes,
        }

    def validate_request(
        self,
        *,
        model: str,
        mode: str,
        execution: str,
        params: Mapping[str, Any],
    ) -> None:
        """Reject every request outside the profile; never silently clamp it."""
        if (model, mode, execution) != ("z-image", "i2i", "cloud"):
            raise ImageStoragePolicyError(
                f"request is outside bounded storage policy {self.version}"
            )
        if params.get("count", 1) != self.max_count:
            raise ImageStoragePolicyError(
                f"bounded cloud i2i requires count={self.max_count}"
            )
        prompt = params.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ImageStoragePolicyError("bounded cloud i2i requires a prompt")
        if len(prompt) > self.max_prompt_chars:
            raise ImageStoragePolicyError(
                f"prompt exceeds bounded limit of {self.max_prompt_chars} characters"
            )
        image_ref = params.get("image_ref")
        if not isinstance(image_ref, str) or not image_ref.strip():
            raise ImageStoragePolicyError("bounded cloud i2i requires a materialized image_ref")
        source = Path(image_ref)
        if not source.is_file():
            raise ImageStoragePolicyError("bounded cloud i2i image_ref is not a file")
        if source.stat().st_size > self.source_max_bytes:
            raise ImageStoragePolicyError(
                f"image_ref exceeds bounded source limit of {self.source_max_bytes} bytes"
            )
        size = params.get("size")
        if not isinstance(size, str) or "x" not in size.lower():
            raise ImageStoragePolicyError("bounded cloud i2i requires explicit WIDTHxHEIGHT size")
        try:
            width_text, height_text = size.lower().split("x", 1)
            width, height = int(width_text), int(height_text)
        except (TypeError, ValueError) as exc:
            raise ImageStoragePolicyError("bounded cloud i2i size must be WIDTHxHEIGHT") from exc
        if not (1 <= width <= self.max_width and 1 <= height <= self.max_height):
            raise ImageStoragePolicyError(
                f"bounded cloud i2i dimensions must be at most {self.max_width}x{self.max_height}"
            )

    def validate_download(self, data: bytes, *, index: int = 0) -> tuple[int, int]:
        """Validate byte size and decoded image dimensions before staging."""
        if len(data) > self.output_max_bytes:
            raise ImageStoragePolicyError(
                f"provider output {index} exceeds {self.output_max_bytes} bytes"
            )
        try:
            from PIL import Image

            with Image.open(BytesIO(data)) as image:
                width, height = image.size
                image.load()
        except Exception as exc:
            raise ImageStoragePolicyError(
                f"provider output {index} is not a decodable image"
            ) from exc
        if width > self.max_width or height > self.max_height:
            raise ImageStoragePolicyError(
                f"provider output {index} dimensions {width}x{height} exceed "
                f"{self.max_width}x{self.max_height}"
            )
        return width, height

    def validate_final_output(self, path: str | Path, *, index: int = 0) -> int:
        """Check the bytes after metadata embedding and any atomic rewrite."""
        size = Path(path).stat().st_size
        if size > self.output_max_bytes:
            raise ImageStoragePolicyError(
                f"final provider output {index} exceeds {self.output_max_bytes} bytes "
                "after metadata embedding"
            )
        return size

    def validate_manifest(self, path: str | Path) -> int:
        """Check the published manifest before the host harvests it."""
        size = Path(path).stat().st_size
        if size > self.manifest_max_bytes:
            raise ImageStoragePolicyError(
                f"image result manifest exceeds {self.manifest_max_bytes} bytes"
            )
        return size


CLOUD_I2I_STORAGE_POLICY = CloudI2IStoragePolicy()


__all__ = [
    "CLOUD_I2I_STORAGE_POLICY",
    "CloudI2IStoragePolicy",
    "ImageStoragePolicyError",
]
