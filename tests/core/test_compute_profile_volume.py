from __future__ import annotations

import json

from astrid.core.compute_profile import resolve_compute_profile


def test_volume_profile_values_follow_profile_and_explicit_precedence(tmp_path):
    profile_dir = tmp_path / ".astrid" / "compute-profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "default.json").write_text(
        json.dumps(
            {
                "schema": "astrid.compute_profile.v1",
                "schema_version": 1,
                "id": "default",
                "volume_in_gb": 64,
                "volume_mount_path": "/profile-volume",
                "credentials": {"runpod_api_key": "RUNPOD_API_KEY"},
            }
        )
    )

    resolved = resolve_compute_profile(
        explicit={"volume_in_gb": 128},
        env={"RUNPOD_VOLUME_IN_GB": "256"},
        executor_defaults={"volume_in_gb": 8, "volume_mount_path": "/default"},
        home=tmp_path,
    )

    assert resolved["volume_in_gb"] == 128
    assert resolved["volume_mount_path"] == "/profile-volume"
    assert resolved["credentials"] == {"runpod_api_key": "RUNPOD_API_KEY"}


def test_volume_fields_are_rejected_before_porting_unknown_profile_data():
    from astrid.core.compute_profile import validate_profile

    profile = {
        "schema": "astrid.compute_profile.v1",
        "schema_version": 1,
        "id": "default",
        "volume_in_gb": 32,
        "volume_mount_path": "/workspace",
    }
    assert validate_profile(profile)["volume_in_gb"] == 32


def test_volume_profile_extraction_ignores_untyped_mock_values(tmp_path):
    from argparse import Namespace
    from unittest.mock import MagicMock

    from astrid.packs.runpod.executors._common import _resolve_compute_profile

    args = MagicMock(spec=Namespace)
    args.volume_in_gb = MagicMock()
    args.volume_mount_path = MagicMock()
    args.compute_profile = None
    resolved = _resolve_compute_profile(args, tmp_path)

    assert resolved["volume_in_gb"] == 0
    assert resolved["volume_mount_path"] == "/workspace"
