from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from astrid.sdk import host_bootstrap
from astrid.core.execution.generic_host import source_checkout_digest
from astrid.core.integrations.reigh.boot_manifest import load_boot_manifest_hash


def test_bootstrap_passes_inventory_identity_and_restarts_on_change(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "source"
    (source / "astrid" / "packs").mkdir(parents=True)
    (source / "astrid" / "packs" / "marker.txt").write_text("pack", encoding="utf-8")
    managed = tmp_path / "managed-pack"
    managed.mkdir()
    support = tmp_path / "support" / "nested"
    support.mkdir(parents=True)
    credential = support.parent / "worker.token"
    credential.write_text("worker", encoding="utf-8")
    os.chmod(credential, 0o600)
    value = {
        "worker_credential_file": str(credential),
        "source_checkout": str(source),
        "worker_actor": host_bootstrap.PACK_HOST_ACTOR,
        "worker_scopes": list(host_bootstrap.PACK_HOST_SCOPES),
        "endpoint": "http://runtime.test",
        "runtime_epoch": "epoch-1",
        "runtime_instance_id": "instance-1",
        "schema_digest": "schema-1",
    }
    inventory = SimpleNamespace(identity="inventory-1", roots=(managed,), sources=(managed,))
    inventory_calls: list[object] = []

    def active_inventory():
        inventory_calls.append(inventory)
        return inventory

    monkeypatch.setattr("astrid.core.pack.source_setup.active_source_inventory", active_inventory)
    from astrid.core.execution import generic_host
    class FakeRuntimeClient:
        def __init__(self, endpoint, credential):
            assert endpoint == "http://runtime.test"
            assert credential == "worker"

        def health(self):
            return {"runtime_epoch": "epoch-1", "runtime_instance_id": "instance-1", "schema_digest": "schema-1"}

    monkeypatch.setattr(generic_host, "RuntimeProtocolClient", FakeRuntimeClient)
    state: dict = {}
    ready: dict = {}
    launches: list[list[str]] = []
    terminated: list[dict] = []

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_read(path: Path):
        if path.name == "generic-host.json":
            return state or None
        return ready or None

    def fake_write(path: Path, payload: dict):
        state.update(payload)

    def fake_popen(argv, **_kwargs):
        launches.append(list(argv))
        boot_manifest = credential.parent.parent / "astrid-host" / "boot-manifest.json"
        ready.update({
            "status": "ready",
            "pid": 4242,
            "process_birth_id": "birth-1",
            "python_executable": os.path.abspath(__import__("sys").executable),
            "endpoint": "http://runtime.test",
            "executor_id": host_bootstrap.PACK_HOST_ACTOR,
                "ready_file": str(credential.parent.parent / "generic-host.ready.json"),
            "credential_file": str(credential),
                "support_root": str(credential.parent.parent),
            "source_checkout": str(source),
            "source_checkout_digest": source_checkout_digest(source),
            "source_inventory_identity": inventory.identity,
            "boot_manifest_path": str(boot_manifest),
            "boot_manifest_hash": load_boot_manifest_hash(
                boot_manifest, support_root=credential.parent.parent
            ),
            "runtime_instance_id": "instance-1",
            "runtime_epoch": "epoch-1",
            "schema_digest": "schema-1",
            "ready_capabilities": [],
        })
        return FakeProcess()

    monkeypatch.setattr(host_bootstrap, "_read_object", fake_read)
    monkeypatch.setattr(host_bootstrap, "_write_object", fake_write)
    monkeypatch.setattr(host_bootstrap.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(host_bootstrap, "_host_birth_identity", lambda _pid: "birth-1")
    monkeypatch.setattr(host_bootstrap, "_terminate_old_host", lambda current: terminated.append(dict(current)))

    result = host_bootstrap.ensure_pack_host(value, reconfigure_action="reconfigure")
    assert result["host_status"] == "ready"
    assert result["host_source_inventory_identity"] == "inventory-1"
    assert len(inventory_calls) == 1
    assert "--source-inventory-identity" in launches[0]
    assert launches[0][launches[0].index("--source-inventory-identity") + 1] == "inventory-1"
    assert launches[0].count("--pack-root") == 2

    inventory.identity = "inventory-2"
    ready.clear()
    result2 = host_bootstrap.ensure_pack_host(value, reconfigure_action="reconfigure")
    assert result2["host_status"] == "ready"
    assert len(launches) == 2
    assert len(inventory_calls) == 2
    assert terminated, "changed source inventory must not reuse the old ready host"

    # Disabling the last managed source must not reuse a host that still
    # advertises the previously selected nonempty inventory.
    inventory.identity = ""
    inventory.sources = ()
    inventory.roots = ()
    result3 = host_bootstrap.ensure_pack_host(value, reconfigure_action="reconfigure")
    assert result3["host_status"] == "ready"
    assert len(launches) == 3
    assert len(inventory_calls) == 3
