"""Host reuse must respect the caller's dependency environment."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.sdk import host_bootstrap as bootstrap
from astrid.core.execution import generic_host
from astrid.core.gateway.dispatch import compose_profile_handoff
from astrid.core.integrations.reigh.boot_manifest import load_boot_manifest_hash


@pytest.mark.parametrize("source_changed", [False, True])
@pytest.mark.parametrize("active_children", [False, True])
@pytest.mark.parametrize("previous_python", [None, "/other-venv/bin/python", "/selected-venv/bin/python"])
def test_bootstrap_reuses_only_the_selected_interpreter(tmp_path, monkeypatch, previous_python, active_children, source_changed):
    source = tmp_path / "source"
    (source / "astrid" / "packs").mkdir(parents=True)
    worker = tmp_path / "support" / "credentials" / "worker"
    worker.parent.mkdir(parents=True)
    worker.write_text("test-token")
    worker.chmod(0o600)
    support = worker.parent.parent
    ready_path = support / "generic-host.ready.json"
    boot_manifest = support / "astrid-host" / "boot-manifest.json"
    compose_profile_handoff(boot_manifest, support_root=support)
    current = {
        "endpoint": "http://localhost:1234", "executor_id": bootstrap.PACK_HOST_ACTOR,
        "ready_file": str(ready_path), "credential_file": str(worker),
        "support_root": str(support), "source_checkout": str(source),
        "source_checkout_digest": "source-digest", "runtime_instance_id": "instance",
        "runtime_epoch": 1, "schema_digest": "schema", "pid": 101,
        "process_birth_id": "birth",
        "boot_manifest_path": str(boot_manifest),
        "boot_manifest_hash": load_boot_manifest_hash(boot_manifest, support_root=support),
    }
    if source_changed:
        current["source_checkout_digest"] = "previous-source-digest"
    if previous_python is not None:
        current["python_executable"] = previous_python
    bootstrap._write_object(support / "generic-host.json", current)
    bootstrap._write_object(ready_path, {**current, "status": "ready"})
    monkeypatch.setattr(bootstrap.sys, "executable", "/selected-venv/bin/python")
    monkeypatch.setattr(generic_host, "source_checkout_digest", lambda _: "source-digest")
    monkeypatch.setattr(generic_host, "RuntimeProtocolClient", lambda *args: SimpleNamespace(
        health=lambda: {"status": "ok", "runtime_epoch": 1, "schema_digest": "schema"}))
    monkeypatch.setattr(
        "astrid.core.pack.source_setup.active_source_inventory",
        lambda: SimpleNamespace(identity="", roots=(), sources=()),
    )
    monkeypatch.setattr(bootstrap, "_host_identity_matches", lambda _: True)
    monkeypatch.setattr(bootstrap, "_host_birth_identity", lambda _: "new-birth")
    monkeypatch.setattr(bootstrap, "_descendant_snapshot",
                        lambda _: {303: ("child-birth", 303)} if active_children else {})
    terminated = []
    launched = []
    monkeypatch.setattr(bootstrap, "_terminate_old_host", lambda state: terminated.append(state["pid"]))

    def launch(argv, **kwargs):
        launched.append(argv[0])
        boot_manifest_hash = load_boot_manifest_hash(boot_manifest, support_root=support)
        bootstrap._write_object(ready_path, {
            **current, "python_executable": argv[0], "status": "ready",
            "source_checkout_digest": "source-digest",
            "boot_manifest_hash": boot_manifest_hash,
            "pid": 202, "process_birth_id": "new-birth",
        })
        return SimpleNamespace(pid=202, poll=lambda: None)

    monkeypatch.setattr(bootstrap.subprocess, "Popen", launch)
    handoff = {
        "worker_credential_file": str(worker), "source_checkout": str(source),
        "endpoint": current["endpoint"], "worker_actor": bootstrap.PACK_HOST_ACTOR,
        "worker_scopes": bootstrap.PACK_HOST_SCOPES, "runtime_instance_id": "instance",
    }
    reusable = previous_python == "/selected-venv/bin/python" and not source_changed
    if active_children and not reusable:
        with pytest.raises(bootstrap.PackHostBootstrapError, match="busy with active child processes"):
            bootstrap.ensure_pack_host(handoff, reconfigure_action="reconfigure")
        assert terminated == launched == []
        assert bootstrap._read_object(support / "generic-host.json") == current
        assert bootstrap._read_object(ready_path)["pid"] == 101
        return
    result = bootstrap.ensure_pack_host(handoff, reconfigure_action="reconfigure")
    if reusable:
        assert result["host_pid"] == 101
        assert terminated == launched == []
    else:
        assert result["host_pid"] == 202
        assert terminated == [101]
        assert launched == ["/selected-venv/bin/python"]
        assert bootstrap._read_object(support / "generic-host.json")["python_executable"] == launched[0]
