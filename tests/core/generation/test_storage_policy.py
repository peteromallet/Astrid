"""Tests for the enforced cloud image-to-image storage envelope."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from astrid.core.generation.storage_policy import (
    CLOUD_EDIT_STORAGE_POLICY,
    CLOUD_I2I_STORAGE_POLICY,
    CLOUD_T2I_STORAGE_POLICY,
    CloudT2IStoragePolicy,
    CloudI2IStoragePolicy,
    ImageStoragePolicyError,
)


_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _params(source: Path, **overrides):
    value = {
        "prompt": "bounded proof",
        "count": 1,
        "size": "1024x1024",
        "strength": 0.5,
        "image_ref": str(source),
    }
    value.update(overrides)
    return value


def test_policy_derives_documented_whole_task_ceiling() -> None:
    policy = CLOUD_I2I_STORAGE_POLICY
    assert policy.estimate == {
        "scratch_bytes": 512_000 + 2 * (64 * 1024 * 1024) + 1 * 1024 * 1024 + 1 * 1024 * 1024,
        "output_bytes": 65 * 1024 * 1024,
    }


def test_t2i_policy_derives_exact_registered_envelope() -> None:
    assert CLOUD_T2I_STORAGE_POLICY.estimate == {
        "scratch_bytes": 69_206_016,
        "output_bytes": 269_484_032,
    }


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"count": 5}, "between 1 and 4"),
        ({"prompt": "x" * 4097}, "prompt exceeds"),
        ({"size": "2049x1024"}, "at most"),
        ({"mode": "i2i"}, "outside bounded storage policy"),
    ],
)
def test_t2i_policy_rejects_out_of_domain_requests(overrides, message: str) -> None:
    params = {
        "prompt": "bounded t2i proof",
        "count": 1,
        "seed": 19,
        "steps": 28,
        "size": "1536x1024",
    }
    model = "flux-dev"
    mode = "t2i"
    params.update({key: value for key, value in overrides.items() if key not in {"mode"}})
    mode = overrides.get("mode", mode)
    with pytest.raises(ImageStoragePolicyError, match=message):
        CLOUD_T2I_STORAGE_POLICY.validate_task_request(
            model=model,
            mode=mode,
            execution="cloud",
            params=params,
        )


def test_t2i_policy_accepts_typed_request_and_checks_final_metadata_growth(tmp_path: Path) -> None:
    params = {
        "prompt": "bounded t2i proof",
        "count": 2,
        "seed": 19,
        "steps": 28,
        "size": "1536x1024",
    }
    CLOUD_T2I_STORAGE_POLICY.validate_task_request(
        model="flux-dev",
        mode="t2i",
        execution="cloud",
        params=params,
    )
    result = tmp_path / "result.png"
    result.write_bytes(_PNG + b"x")
    policy = CloudT2IStoragePolicy(output_max_bytes=len(_PNG))
    with pytest.raises(ImageStoragePolicyError, match="after metadata embedding"):
        policy.validate_final_output(result)


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"count": 2}, "count=1"),
        ({"size": "4096x1024"}, "at most"),
        ({"prompt": "x" * 4097}, "prompt exceeds"),
    ],
)
def test_policy_rejects_out_of_domain_requests(tmp_path: Path, overrides, message: str) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    with pytest.raises(ImageStoragePolicyError, match=message):
        CLOUD_I2I_STORAGE_POLICY.validate_request(
            model="z-image",
            mode="i2i",
            execution="cloud",
            params=_params(source, **overrides),
        )


def test_policy_accepts_exact_bounded_request(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    CLOUD_I2I_STORAGE_POLICY.validate_request(
        model="z-image",
        mode="i2i",
        execution="cloud",
        params=_params(source),
    )


def test_policy_validates_immutable_cas_descriptor_and_controls() -> None:
    descriptor = {
        "digest": "sha256:" + "a" * 64,
        "filename": "source.png",
        "media_type": "image/png",
    }
    params = {
        "model": "z-image",
        "mode": "i2i",
        "execution": "cloud",
        "prompt": "bounded proof",
        "count": 1,
        "size": "1024x1024",
        "strength": 0.5,
        "image_ref": descriptor,
    }
    CLOUD_I2I_STORAGE_POLICY.validate_admission_request(
        model="z-image",
        mode="i2i",
        execution="cloud",
        params=params,
    )
    for strength in (-0.1, 1.1, "0.5", float("nan")):
        with pytest.raises(ImageStoragePolicyError, match="strength"):
            CLOUD_I2I_STORAGE_POLICY.validate_admission_request(
                model="z-image",
                mode="i2i",
                execution="cloud",
                params={**params, "strength": strength},
            )


def test_policy_rejects_non_image_source_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_text("not an image", encoding="utf-8")
    with pytest.raises(ImageStoragePolicyError, match="decodable image"):
        CLOUD_I2I_STORAGE_POLICY.validate_request(
            model="z-image",
            mode="i2i",
            execution="cloud",
            params=_params(source),
        )


def test_policy_reconciles_materialized_bytes_with_media_type(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    with pytest.raises(ImageStoragePolicyError, match="media_type"):
        CLOUD_I2I_STORAGE_POLICY.validate_materialized_source(
            source,
            media_type="image/jpeg",
        )


def test_source_only_edit_profile_has_a_distinct_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    params = _params(source)
    params.pop("strength")
    assert CLOUD_EDIT_STORAGE_POLICY.version == "astrid.cloud-edit.qwen-source.v1"
    CLOUD_EDIT_STORAGE_POLICY.validate_request(
        model="qwen-image-edit-2511",
        mode="edit",
        execution="cloud",
        params=params,
    )
    with pytest.raises(ImageStoragePolicyError, match="does not admit mask_ref"):
        CLOUD_EDIT_STORAGE_POLICY.validate_request(
            model="qwen-image-edit-2511",
            mode="edit",
            execution="cloud",
            params={**params, "mask_ref": str(source)},
        )


def test_source_only_edit_profile_validates_typed_admission_descriptor() -> None:
    descriptor = {
        "digest": "sha256:" + "b" * 64,
        "filename": "source.png",
        "media_type": "image/png",
    }
    params = {
        "model": "qwen-image-edit-2511",
        "mode": "edit",
        "execution": "cloud",
        "prompt": "q" * 64,
        "count": 1,
        "size": "1024x1024",
        "seed": 19,
        "image_ref": descriptor,
    }
    CLOUD_EDIT_STORAGE_POLICY.validate_admission_request(
        model="qwen-image-edit-2511",
        mode="edit",
        execution="cloud",
        params=params,
    )
    with pytest.raises(ImageStoragePolicyError, match="does not admit strength"):
        CLOUD_EDIT_STORAGE_POLICY.validate_admission_request(
            model="qwen-image-edit-2511",
            mode="edit",
            execution="cloud",
            params={**params, "strength": 0.5},
        )
    with pytest.raises(ImageStoragePolicyError, match="filename and media_type"):
        CLOUD_EDIT_STORAGE_POLICY.validate_admission_request(
            model="qwen-image-edit-2511",
            mode="edit",
            execution="cloud",
            params={
                **params,
                "image_ref": {**descriptor, "filename": "source.jpg"},
            },
        )


def _cas_descriptor(filename: str = "source.png") -> dict[str, str]:
    return {
        "digest": "sha256:" + "c" * 64,
        "filename": filename,
        "media_type": "image/png",
    }


def test_unified_edit_policy_has_disjoint_source_and_mask_envelopes() -> None:
    from astrid.core.generation.storage_policy import CLOUD_UNIFIED_EDIT_STORAGE_POLICY

    policy = CLOUD_UNIFIED_EDIT_STORAGE_POLICY
    assert policy.estimate == {
        "scratch_bytes": 512_000 + 512_000 + 2 * (64 * 1024 * 1024) + 2 * 1024 * 1024,
        "output_bytes": 64 * 1024 * 1024 + 1 * 1024 * 1024,
    }

    for model in ("qwen-image-edit-2511", "flux2-klein-4b", "flux2-klein-9b"):
        policy.validate_admission_request(
            model=model,
            mode="edit",
            execution="cloud",
            params={
                "prompt": "source edit",
                "count": 1,
                "size": "1024x1024",
                "image_ref": _cas_descriptor(),
            },
        )


def test_unified_inpaint_policy_requires_typed_mask_and_matching_materialized_images(
    tmp_path: Path,
) -> None:
    from astrid.core.generation.storage_policy import CLOUD_UNIFIED_EDIT_STORAGE_POLICY

    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    source.write_bytes(_PNG)
    mask.write_bytes(_PNG)
    params = {
        "prompt": "masked edit",
        "count": 1,
        "size": "1024x1024",
        "strength": 0.93,
        "image_ref": _cas_descriptor("source.png"),
        "mask_ref": _cas_descriptor("mask.png"),
    }
    policy = CLOUD_UNIFIED_EDIT_STORAGE_POLICY
    policy.validate_admission_request(
        model="qwen-image-edit-inpaint",
        mode="inpaint",
        execution="cloud",
        params=params,
    )
    policy.validate_materialized_inputs(
        model="qwen-image-edit-inpaint",
        mode="inpaint",
        execution="cloud",
        params={**params, "image_ref": source, "mask_ref": mask},
        image_media_type="image/png",
        mask_media_type="image/png",
    )
    policy.validate_request(
        model="qwen-image-edit-inpaint",
        mode="inpaint",
        execution="cloud",
        params={**params, "image_ref": source, "mask_ref": mask},
    )

    with pytest.raises(ImageStoragePolicyError, match="requires mask_ref"):
        policy.validate_admission_request(
            model="qwen-image-edit-inpaint",
            mode="inpaint",
            execution="cloud",
            params={key: value for key, value in params.items() if key != "mask_ref"},
        )


def test_unified_inpaint_policy_rejects_mismatched_materialized_dimensions(
    tmp_path: Path,
) -> None:
    from astrid.core.generation.storage_policy import CLOUD_UNIFIED_EDIT_STORAGE_POLICY
    from PIL import Image

    source = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    source.write_bytes(_PNG)
    Image.new("RGBA", (2, 1), (255, 255, 255, 255)).save(mask)
    with pytest.raises(ImageStoragePolicyError, match="dimensions must match"):
        CLOUD_UNIFIED_EDIT_STORAGE_POLICY.validate_materialized_inputs(
            model="qwen-image-edit-inpaint",
            mode="inpaint",
            execution="cloud",
            params={
                "prompt": "masked edit",
                "count": 1,
                "size": "1024x1024",
                "strength": 0.93,
                "image_ref": source,
                "mask_ref": mask,
            },
            image_media_type="image/png",
            mask_media_type="image/png",
        )


def test_policy_rejects_download_at_limit_plus_one_and_checks_dimensions() -> None:
    policy = CloudI2IStoragePolicy(
        output_max_bytes=len(_PNG),
        max_width=1,
        max_height=1,
    )
    assert policy.validate_download(_PNG) == (1, 1)
    with pytest.raises(ImageStoragePolicyError, match="exceeds"):
        policy.validate_download(_PNG + b"x")


def test_policy_rejects_final_output_growth_after_metadata(tmp_path: Path) -> None:
    path = tmp_path / "result.png"
    path.write_bytes(_PNG + b"x")
    policy = CloudI2IStoragePolicy(output_max_bytes=len(_PNG))
    with pytest.raises(ImageStoragePolicyError, match="after metadata embedding"):
        policy.validate_final_output(path)
