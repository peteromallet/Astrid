from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.sdk import host_bootstrap
from astrid.core.execution.generic_host import source_checkout_digest
from astrid.core.integrations.reigh.boot_manifest import load_boot_manifest_hash


def test_host_pid_alive_rejects_macos_zombie(monkeypatch) -> None:
    """A defunct host must not make its persisted marker block relaunch."""
    monkeypatch.setattr(host_bootstrap.os, "kill", lambda _pid, _signal: None)

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return "Z\n"

    monkeypatch.setattr(host_bootstrap.os, "popen", lambda *args, **kwargs: Probe())
    assert host_bootstrap._host_pid_alive(4242) is False


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
            return {"status": "ok", "runtime_epoch": "epoch-1", "runtime_instance_id": "instance-1", "schema_digest": "schema-1"}

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


def test_bootstrap_stops_on_correlated_terminal_registration_failure(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    (source / "astrid" / "packs").mkdir(parents=True)
    (source / "astrid" / "packs" / "marker.txt").write_text(
        "pack", encoding="utf-8"
    )
    support = tmp_path / "support"
    credentials = support / "credentials"
    credentials.mkdir(parents=True)
    credential = credentials / "worker.token"
    credential.write_text("worker", encoding="utf-8")
    os.chmod(credential, 0o600)
    value = {
        "worker_credential_file": str(credential),
        "source_checkout": str(source),
        "worker_actor": host_bootstrap.PACK_HOST_ACTOR,
        "worker_scopes": list(host_bootstrap.PACK_HOST_SCOPES),
        "endpoint": "http://runtime.test",
        "runtime_epoch": 1,
        "runtime_instance_id": "instance-1",
        "schema_digest": "schema-1",
    }
    inventory = SimpleNamespace(identity="", roots=(), sources=())
    monkeypatch.setattr(
        "astrid.core.pack.source_setup.active_source_inventory", lambda: inventory
    )

    from astrid.core.execution import generic_host

    class FakeRuntimeClient:
        def __init__(self, endpoint, credential):
            assert endpoint == "http://runtime.test"
            assert credential == "worker"

        def health(self):
            return {
                "status": "ok",
                "runtime_epoch": 1,
                "runtime_instance_id": "instance-1",
                "schema_digest": "schema-1",
            }

    monkeypatch.setattr(generic_host, "RuntimeProtocolClient", FakeRuntimeClient)
    ready: dict[str, object] = {}
    launches: list[list[str]] = []
    terminated: list[dict[str, object]] = []

    class FakeProcess:
        pid = 4242

        def poll(self):
            return None

    def fake_read(path: Path):
        if path.name == "generic-host.ready.json":
            return ready or None
        return None

    def fake_popen(argv, **_kwargs):
        launches.append(list(argv))
        ready.update(
            {
                "status": "failed",
                "terminal": True,
                "pid": 4242,
                "process_birth_id": "birth-failed",
                "error": {
                    "code": "registration_unavailable",
                    "request_id": "request-bootstrap-1",
                    "message": "executor registration unavailable",
                },
            }
        )
        return FakeProcess()

    monkeypatch.setattr(host_bootstrap, "_read_object", fake_read)
    monkeypatch.setattr(host_bootstrap.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        host_bootstrap, "_host_birth_identity", lambda _pid: "birth-failed"
    )
    monkeypatch.setattr(
        host_bootstrap,
        "_terminate_old_host",
        lambda current: terminated.append(dict(current)),
    )

    with pytest.raises(host_bootstrap.PackHostBootstrapError) as caught:
        host_bootstrap.ensure_pack_host(value, reconfigure_action="reconfigure")

    assert caught.value.code == "registration_unavailable"
    assert caught.value.request_id == "request-bootstrap-1"
    assert caught.value.terminal is True
    assert "request-bootstrap-1" in str(caught.value)
    assert len(launches) == 1
    assert len(terminated) == 1


def test_bootstrap_refuses_runtime_health_without_ok_status(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source"
    (source / "astrid" / "packs").mkdir(parents=True)
    credentials = tmp_path / "support" / "credentials"
    credentials.mkdir(parents=True)
    credential = credentials / "worker.token"
    credential.write_text("worker", encoding="utf-8")
    os.chmod(credential, 0o600)
    value = {
        "worker_credential_file": str(credential),
        "source_checkout": str(source),
        "worker_actor": host_bootstrap.PACK_HOST_ACTOR,
        "worker_scopes": list(host_bootstrap.PACK_HOST_SCOPES),
        "endpoint": "http://runtime.test",
    }
    monkeypatch.setattr(
        "astrid.core.pack.source_setup.active_source_inventory",
        lambda: SimpleNamespace(identity="", roots=(), sources=()),
    )
    from astrid.core.execution import generic_host

    class UnhealthyRuntime:
        def __init__(self, *_args):
            pass

        def health(self):
            return {
                "status": "unhealthy",
                "runtime_epoch": 1,
                "runtime_instance_id": "instance-1",
                "schema_digest": "schema-1",
            }

    monkeypatch.setattr(generic_host, "RuntimeProtocolClient", UnhealthyRuntime)
    monkeypatch.setattr(
        host_bootstrap.subprocess,
        "Popen",
        lambda *_args, **_kwargs: pytest.fail("unhealthy runtime launched pack host"),
    )

    with pytest.raises(host_bootstrap.PackHostBootstrapError) as caught:
        host_bootstrap.ensure_pack_host(value, reconfigure_action="reconfigure")

    assert caught.value.code == "runtime_not_ready"
    assert caught.value.terminal is True
