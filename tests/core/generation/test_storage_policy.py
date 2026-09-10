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


def test_source_only_edit_profile_has_a_distinct_identity(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(_PNG)
    assert CLOUD_EDIT_STORAGE_POLICY.version == "astrid.cloud-edit.qwen-source.v1"
    CLOUD_EDIT_STORAGE_POLICY.validate_request(
        model="qwen-image-edit-2511",
        mode="edit",
        execution="cloud",
        params=_params(source),
    )
    with pytest.raises(ImageStoragePolicyError, match="does not admit mask_ref"):
        CLOUD_EDIT_STORAGE_POLICY.validate_request(
            model="qwen-image-edit-2511",
            mode="edit",
            execution="cloud",
            params=_params(source, mask_ref=str(source)),
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
