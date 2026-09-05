from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

from astrid.sdk import host_bootstrap


def test_host_bootstrap_binds_manifest_in_argv_and_reuses_exact_binding(
    tmp_path: Path, monkeypatch
) -> None:
    support = tmp_path / "support"
    credentials = support / "credentials"
    credentials.mkdir(parents=True)
    worker_file = credentials / "astrid-pack-host.token"
    worker_file.write_text("worker-token\n", encoding="utf-8")
    worker_file.chmod(0o600)
    source = Path(__file__).resolve().parents[2]
    captured: list[list[str]] = []

    class FakeRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        def health(self):
            return {
                "status": "ok",
                "protocol": "workspace.v1",
                "runtime_epoch": 7,
                "runtime_instance_id": "runtime-7",
                "schema_digest": "sha256:" + "1" * 64,
            }

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_popen(argv, **_kwargs):
        captured.append(list(argv))
        ready = Path(argv[argv.index("--ready-file") + 1])
        manifest = Path(argv[argv.index("--boot-manifest-path") + 1])
        from astrid.core.integrations.reigh.boot_manifest import load_boot_manifest_hash

        expected = {
            "status": "ready",
            "pid": FakeProcess.pid,
            "process_birth_id": "birth-4242",
            "endpoint": "http://127.0.0.1:9999",
            "executor_id": "astrid-pack-host",
            "ready_file": str(ready),
            "credential_file": str(worker_file.resolve()),
            "support_root": str(support.resolve()),
            "source_checkout": str(source.resolve()),
            "source_checkout_digest": "source-digest",
            "runtime_instance_id": "runtime-7",
            "runtime_epoch": 7,
            "schema_digest": "sha256:" + "1" * 64,
            "boot_manifest_path": str(manifest),
            "boot_manifest_hash": load_boot_manifest_hash(manifest, support_root=support),
            "readiness_profile_path": str(support / "worker-readiness-profile.json"),
            "readiness_profile_hash": profile_hash,
            "ready_capabilities": ["shots.example"],
        }
        ready.parent.mkdir(parents=True, exist_ok=True)
        ready.write_text(json.dumps(expected), encoding="utf-8")
        return FakeProcess()

    monkeypatch.setattr(host_bootstrap, "RuntimeProtocolClient", FakeRuntime, raising=False)
    monkeypatch.setattr(host_bootstrap.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(host_bootstrap, "_host_birth_identity", lambda _pid: "birth-4242")
    monkeypatch.setattr(host_bootstrap, "_host_identity_matches", lambda _state: True)
    monkeypatch.setattr(host_bootstrap, "_host_pid_alive", lambda _pid: True)
    monkeypatch.setattr(host_bootstrap, "_our_host", lambda _pid: True)
    monkeypatch.setattr(host_bootstrap, "source_checkout_digest", lambda _path: "source-digest", raising=False)

    # The bootstrap module imports these two symbols lazily in ensure_pack_host.
    monkeypatch.setattr(
        "astrid.core.execution.generic_host.RuntimeProtocolClient",
        FakeRuntime,
    )
    monkeypatch.setattr(
        "astrid.core.execution.generic_host.source_checkout_digest",
        lambda _path: "source-digest",
    )

    from astrid.core.gateway.dispatch import compose_profile_handoff
    monkeypatch.setattr(
        "astrid.core.execution.generic_host._process_birth_identity",
        lambda _pid: "proc-start-ticks:fixture",
    )
    monkeypatch.setattr(
        "astrid.core.execution.generic_host._process_snapshot",
        lambda: {os.getpid(): object()},
    )

    manifest = support / "astrid-host" / "boot-manifest.json"
    manifest_hash = compose_profile_handoff(manifest, support_root=support)["sha256"]
    output = support / "outputs"
    output.mkdir()
    facts = {
        "exact": {
            "interpreter": str(Path(sys.executable).resolve()),
            "runtime_lock": "sha256:" + "2" * 64,
            "engine_lock": "sha256:" + "3" * 64,
            "model_digest": "sha256:" + "4" * 64,
            "custom_node_digest": "sha256:" + "5" * 64,
            "driver": "fixture-driver",
            "root": "sha256:" + "6" * 64,
            "port": 9999,
        },
        "minimum": {"vram_bytes": 1, "scratch_bytes": 1},
    }
    facts_digest = "sha256:" + hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    profile = {
        "schema_version": "hc03-worker-readiness.v1",
        "status": "ready",
        "verified_facts": facts,
        "verified_facts_digest": facts_digest,
        "runtime": {
            "endpoint": "http://127.0.0.1:9999", "port": 9999, "pid": os.getpid(),
            "process_birth_id": "proc-start-ticks:fixture", "runtime_instance_id": "runtime-7",
            "runtime_epoch": 7, "schema_digest": "sha256:" + "1" * 64,
            "coordinator_epoch": "runtime-7", "active_realm": "realm-1",
            "credential_reference": str(worker_file.resolve()), "discovery_digest": "sha256:" + "7" * 64,
        },
        "launch": {
            "host_interpreter": str(Path(sys.executable).resolve()), "source_checkout": str(source.resolve()),
            "engine_interpreter": str(Path(sys.executable).resolve()), "output_root": str(output.resolve()),
            "pack_root": str((source / "astrid" / "packs").resolve()), "support_root": str(support.resolve()),
            "ready_file": str((support / "generic-host.ready.json").resolve()),
            "state_file": str((support / "generic-host.json").resolve()),
            "boot_manifest_path": str(manifest.resolve()), "boot_manifest_hash": manifest_hash,
        },
        "worker_actor": host_bootstrap.PACK_HOST_ACTOR,
        "worker_scopes": list(host_bootstrap.PACK_HOST_SCOPES),
    }
    profile_path = support / "worker-readiness-profile.json"
    profile_path.write_text(json.dumps(profile, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    profile_path.chmod(0o600)
    profile_hash = "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest()

    value = {
        "worker_credential_file": str(worker_file),
        "worker_actor": host_bootstrap.PACK_HOST_ACTOR,
        "worker_scopes": host_bootstrap.PACK_HOST_SCOPES,
        "source_checkout": str(source),
        "endpoint": "http://127.0.0.1:9999",
        "runtime_epoch": 7,
        "runtime_instance_id": "runtime-7",
        "readiness_profile_path": str(profile_path),
        "readiness_profile_hash": profile_hash,
    }
    first = host_bootstrap.ensure_pack_host(value, reconfigure_action="reconfigure")
    manifest = support / "astrid-host" / "boot-manifest.json"
    assert manifest.is_file()
    assert "--boot-manifest-path" in captured[0]
    assert captured[0][captured[0].index("--boot-manifest-path") + 1] == str(manifest)
    assert "--boot-manifest-hash" in captured[0]
    assert captured[0][captured[0].index("--boot-manifest-hash") + 1] == first["host_boot_manifest_hash"]
    assert first["host_boot_manifest_path"] == str(manifest)
    assert first["host_boot_manifest_hash"]

    second = host_bootstrap.ensure_pack_host(value, reconfigure_action="reconfigure")
    assert second == first
    assert len(captured) == 1
    assert not (tmp_path / ".astrid" / "astrid.sqlite3").exists()
