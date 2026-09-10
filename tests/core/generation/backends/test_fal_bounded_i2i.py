"""Provider-boundary tests for the narrow cloud z-image i2i profile."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from astrid.core.generation.backends.fal import FalBackend
from astrid.core.generation.backends import fal as fal_module
from astrid.core.model_catalog.registry import ModelRegistry
from astrid.core.util.http import HttpClient


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _params(source: Path) -> dict[str, object]:
    return {
        "execution": "cloud",
        "storage_policy_version": "astrid.cloud-i2i.z-image.v1",
        "prompt": "bounded provider proof",
        "count": 1,
        "size": "1024x1024",
        "image_ref": str(source),
        "strength": 0.5,
    }


def _qwen_params(source: Path) -> dict[str, object]:
    return {
        "execution": "cloud",
        "storage_policy_version": "astrid.cloud-edit.qwen-source.v1",
        "prompt": "bounded edit provider proof",
        "count": 1,
        "size": "1024x1024",
        "image_ref": str(source),
    }


def test_bounded_i2i_caps_provider_response_and_download(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    client = HttpClient()
    backend = FalBackend(client=client)
    entry, _ = ModelRegistry.load_default().get_by_mode("z-image", "i2i")

    with (
        patch.object(FalBackend, "_resolve_api_key", return_value="test-key"),
        patch(
            "astrid.core.generation.backends.fal.fal_submit_and_poll",
            return_value={"images": [{"url": "https://cdn.example/result.png"}]},
        ) as submit,
        patch.object(client, "get_bytes", return_value=_PNG) as get_bytes,
    ):
        result = backend.generate(entry, "i2i", _params(source), tmp_path / "out")

    assert len(result.image_paths) == 1
    assert get_bytes.call_args.kwargs["max_bytes"] == 64 * 1024 * 1024
    assert submit.call_args.kwargs["max_response_bytes"] == 1 * 1024 * 1024


def test_bounded_i2i_rejects_extra_provider_output(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    backend = FalBackend(client=HttpClient())
    entry, _ = ModelRegistry.load_default().get_by_mode("z-image", "i2i")

    with (
        patch.object(FalBackend, "_resolve_api_key", return_value="test-key"),
        patch(
            "astrid.core.generation.backends.fal.fal_submit_and_poll",
            return_value={
                "images": [
                    {"url": "https://cdn.example/one.png"},
                    {"url": "https://cdn.example/two.png"},
                ]
            },
        ),
    ):
        with pytest.raises(ValueError, match="expected exactly 1"):
            backend.generate(entry, "i2i", _params(source), tmp_path / "out")


def test_bounded_i2i_rejects_download_limit_plus_one(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    backend = FalBackend(client=HttpClient())
    entry, _ = ModelRegistry.load_default().get_by_mode("z-image", "i2i")

    with (
        patch.object(
            fal_module,
            "CLOUD_I2I_STORAGE_POLICY",
            replace(fal_module.CLOUD_I2I_STORAGE_POLICY, output_max_bytes=len(_PNG)),
        ),
        patch.object(FalBackend, "_resolve_api_key", return_value="test-key"),
        patch(
            "astrid.core.generation.backends.fal.fal_submit_and_poll",
            return_value={"images": [{"url": "https://cdn.example/result.png"}]},
        ),
        patch.object(backend._client, "get_bytes", return_value=_PNG + b"x"),
        ):
        with pytest.raises(ValueError, match="exceeds"):
            backend.generate(entry, "i2i", _params(source), tmp_path / "out")


def test_bounded_qwen_2511_uses_versioned_image_urls_and_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    backend = FalBackend(client=HttpClient())
    entry, _ = ModelRegistry.load_default().get_by_mode("qwen-image-edit-2511", "edit")

    with (
        patch.object(FalBackend, "_resolve_api_key", return_value="test-key"),
        patch(
            "astrid.core.generation.backends.fal.fal_submit_and_poll",
            return_value={"images": [{"url": "https://cdn.example/result.png"}]},
        ) as submit,
        patch.object(backend._client, "get_bytes", return_value=_PNG),
    ):
        result = backend.generate(entry, "edit", _qwen_params(source), tmp_path / "out")

    assert len(result.image_paths) == 1
    payload = submit.call_args.args[2]
    assert payload["image_urls"] == [f"data:image/png;base64,{base64.b64encode(_PNG).decode()}"]
    assert payload["image_size"] == {"width": 1024, "height": 1024}


def test_bounded_qwen_2511_rejects_download_limit_plus_one(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    backend = FalBackend(client=HttpClient())
    entry, _ = ModelRegistry.load_default().get_by_mode("qwen-image-edit-2511", "edit")

    with (
        patch.object(
            fal_module,
            "CLOUD_EDIT_STORAGE_POLICY",
            replace(fal_module.CLOUD_EDIT_STORAGE_POLICY, output_max_bytes=len(_PNG)),
        ),
        patch.object(FalBackend, "_resolve_api_key", return_value="test-key"),
        patch(
            "astrid.core.generation.backends.fal.fal_submit_and_poll",
            return_value={"images": [{"url": "https://cdn.example/result.png"}]},
        ),
        patch.object(backend._client, "get_bytes", return_value=_PNG + b"x"),
    ):
        with pytest.raises(ValueError, match="exceeds"):
            backend.generate(entry, "edit", _qwen_params(source), tmp_path / "out")
