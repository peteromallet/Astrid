from __future__ import annotations

import hashlib
import json
from pathlib import Path
from banodoco_workspace_client.contract_metadata import PROTOCOL

from astrid.core.execution.generic_host import GenericPackHost
from astrid.sdk.remote import _task_admission_idempotency_key


ROOT = Path(__file__).resolve().parents[3]
VIBECOMFY_EXECUTORS = ROOT / "astrid/packs/vibecomfy/executors"


def _write_profile(path: Path, hook: Path, *, liveness: int, reordered: bool = False) -> None:
    hook_digest = "sha256:" + hashlib.sha256(hook.read_bytes()).hexdigest()
    profile = {
        "verified_facts": {"exact": {}, "minimum": {}},
        "runtime": {"pid": 1400 + liveness, "observed_at": f"2026-09-25T00:00:{liveness:02d}Z"},
        "vibecomfy_candidate": {
            "kind": "local_snapshot",
            "revision": "fixture-revision",
            "source_content_digest": "sha256:" + "a" * 64,
        },
        "t9_model_substitute": {
            "approved": True,
            "mode": "deterministic_cpu_model_boundary_v1",
            "source_path": str(hook),
            "source_sha256": hook_digest,
        },
    }
    path.write_text(
        json.dumps(profile, sort_keys=not reordered, separators=(",", ":")),
        encoding="utf-8",
    )


def _host(profile_path: Path, monkeypatch) -> GenericPackHost:
    profile_hash = "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest()
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_HASH", profile_hash)
    return GenericPackHost(pack_roots=[VIBECOMFY_EXECUTORS])


def _automatic_key(capability_digest: str) -> str:
    return _task_admission_idempotency_key(
        capability_id="vibecomfy.run",
        capability_digest=capability_digest,
        project_id="same-project",
        spec={"workflow": {"digest": "sha256:" + "b" * 64}},
        input_object_ids=["sha256:" + "c" * 64],
        execution_request=None,
    )


def test_same_validated_profile_keeps_definition_digest_and_key_stable(
    tmp_path: Path, monkeypatch
) -> None:
    hook_a = tmp_path / "hook-a.py"
    hook_b = tmp_path / "relocated-hook.py"
    hook_a.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    hook_b.write_bytes(hook_a.read_bytes())
    profile_a = tmp_path / "profile-a.json"
    profile_b = tmp_path / "profile-b.json"
    _write_profile(profile_a, hook_a, liveness=1)
    _write_profile(profile_b, hook_b, liveness=2, reordered=True)

    first_host = _host(profile_a, monkeypatch)
    first_host.discover()
    first_record = first_host.capabilities["vibecomfy.run"]
    first_registration = first_host.register()

    second_host = _host(profile_b, monkeypatch)
    second_host.discover()
    second_record = second_host.capabilities["vibecomfy.run"]
    second_registration = second_host.register()

    assert first_record.capability_digest == second_record.capability_digest
    assert _automatic_key(first_record.capability_digest) == _automatic_key(
        second_record.capability_digest
    )
    attestation_key = "_astrid_execution_attestation"
    assert (
        first_record.definition.metadata[attestation_key]
        == second_record.definition.metadata[attestation_key]
    )
    registered = next(
        item for item in first_registration["capabilities"] if item["id"] == "vibecomfy.run"
    )
    assert registered["definition"]["metadata"][attestation_key] == first_record.definition.metadata[attestation_key]
    assert registered["preflight"]["execution_attestation"] == {
        "ok": True,
        "identity": first_record.definition.metadata[attestation_key],
    }
    assert second_registration["capabilities"]


def test_valid_attestation_is_a_positive_readiness_check_and_runtime_advertisement(
    tmp_path: Path, monkeypatch
) -> None:
    hook = tmp_path / "approved-hook.py"
    profile = tmp_path / "readiness.json"
    hook.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    _write_profile(profile, hook, liveness=1)
    _host(profile, monkeypatch)
    advertised: list[dict] = []

    class FakeRuntime:
        schema_digest = "schema-test"

        def health(self):
            return {
                "status": "ok",
                "protocol": PROTOCOL,
                "schema_digest": self.schema_digest,
                "runtime_epoch": 1,
            }

        def register_capability(self, *_args, **_kwargs):
            return None

        def register_executor(self, _executor_id, **payload):
            advertised.extend(payload["capabilities"])
            return {
                "max_concurrency": payload["max_concurrency"],
                "resource_keys": payload["resource_keys"],
            }

    host = GenericPackHost(pack_roots=[VIBECOMFY_EXECUTORS], client=FakeRuntime())
    host.discover()
    record = host.preflight("vibecomfy.run")[0]
    attestation = record.definition.metadata["_astrid_execution_attestation"]
    assert record.ready is True
    assert record.preflight["execution_attestation"] == {
        "ok": True,
        "identity": attestation,
    }

    registration = host.register()
    manifest = next(item for item in registration["capabilities"] if item["id"] == "vibecomfy.run")
    runtime_row = next(item for item in advertised if item["capability_id"] == "vibecomfy.run")
    assert manifest["ready"] is True
    assert runtime_row["status"] == "ready"
    assert manifest["definition"]["metadata"]["_astrid_execution_attestation"] == attestation


def test_missing_or_hash_invalid_profile_fails_closed(tmp_path: Path, monkeypatch) -> None:
    hook = tmp_path / "approved-hook.py"
    profile = tmp_path / "readiness.json"
    hook.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    _write_profile(profile, hook, liveness=1)
    _host(profile, monkeypatch)
    monkeypatch.delenv("ASTRID_HOST_READINESS_PROFILE_PATH")
    monkeypatch.delenv("ASTRID_HOST_READINESS_PROFILE_HASH")

    missing_host = GenericPackHost(pack_roots=[VIBECOMFY_EXECUTORS])
    missing_host.discover()
    missing_record = missing_host.preflight("vibecomfy.run")[0]
    assert missing_record.ready is False
    assert missing_record.preflight["vibecomfy_runtime"]["ok"] is False

    _host(profile, monkeypatch)
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_HASH", "sha256:" + "0" * 64)
    invalid_host = GenericPackHost(pack_roots=[VIBECOMFY_EXECUTORS])
    invalid_host.discover()
    invalid_record = invalid_host.preflight("vibecomfy.run")[0]
    assert invalid_record.ready is False
    assert invalid_record.preflight["vibecomfy_runtime"]["ok"] is False


def test_changed_approved_source_changes_definition_and_child_key(
    tmp_path: Path, monkeypatch
) -> None:
    hook = tmp_path / "approved-hook.py"
    profile = tmp_path / "readiness.json"
    hook.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    _write_profile(profile, hook, liveness=1)
    host_a = _host(profile, monkeypatch)
    host_a.discover()
    record_a = host_a.capabilities["vibecomfy.run"]
    key_a = _automatic_key(record_a.capability_digest)

    hook.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n# approved revision B\n", encoding="utf-8")
    _write_profile(profile, hook, liveness=2)
    host_b = _host(profile, monkeypatch)
    host_b.discover()
    record_b = host_b.capabilities["vibecomfy.run"]
    key_b = _automatic_key(record_b.capability_digest)

    assert record_a.capability_digest != record_b.capability_digest
    assert key_a != key_b
    assert key_b == _automatic_key(record_b.capability_digest)


def test_profile_mutation_after_discovery_makes_vibecomfy_unready(
    tmp_path: Path, monkeypatch
) -> None:
    hook = tmp_path / "approved-hook-a.py"
    hook_b = tmp_path / "approved-hook-b.py"
    profile = tmp_path / "readiness.json"
    hook.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    hook_b.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n# B\n", encoding="utf-8")
    _write_profile(profile, hook, liveness=1)
    host = _host(profile, monkeypatch)
    host.discover()

    _write_profile(profile, hook_b, liveness=2)
    monkeypatch.setenv(
        "ASTRID_HOST_READINESS_PROFILE_HASH",
        "sha256:" + hashlib.sha256(profile.read_bytes()).hexdigest(),
    )
    updated = host.preflight("vibecomfy.run")[0]

    assert not updated.ready
    assert not updated.preflight["vibecomfy_runtime"]["ok"]
    assert "attestation changed" in updated.preflight["vibecomfy_runtime"]["reason"]


def test_hook_mutation_after_discovery_fails_closed(tmp_path: Path, monkeypatch) -> None:
    hook = tmp_path / "approved-hook.py"
    profile = tmp_path / "readiness.json"
    hook.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    _write_profile(profile, hook, liveness=1)
    host = _host(profile, monkeypatch)
    host.discover()

    hook.write_text("changed after discovery\n", encoding="utf-8")
    updated = host.preflight("vibecomfy.run")[0]

    assert not updated.ready
    assert not updated.preflight["vibecomfy_runtime"]["ok"]
    assert "source hash does not match readiness" in updated.preflight["vibecomfy_runtime"]["reason"]
