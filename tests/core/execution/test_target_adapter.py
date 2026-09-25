from __future__ import annotations

import pytest

from astrid.core.execution.target_adapter import LocalMachineTargetAdapter, TargetAdapterError


def _observation() -> dict[str, object]:
    return {
        "kind": "machine",
        "target_id": "machine-1",
        "live": True,
        "runtime_epoch": 3,
        "launch_generation": "launch-1",
        "process_birth_id": "process-1",
        "engine_birth_id": "engine-1",
        "output_root": "/tmp/astrid-target-test",
        "profile_revision": "profile-rev-2",
        "profile_digest": "sha256:profile",
    }


def test_local_adapter_fences_profile_revision_identity() -> None:
    adapter = LocalMachineTargetAdapter(
        {
            "kind": "machine",
            "id": "machine-1",
            "profile_revision": "profile-rev-1",
        },
        observer=_observation,
    )
    with pytest.raises(TargetAdapterError, match="profile_revision mismatch"):
        adapter.attach_or_start_owned()
