from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.sdk import autobootstrap, host_bootstrap, workspace_client
from astrid.sdk.client import AstridClient
from banodoco_workspace_client.contract_metadata import PROTOCOL, SCHEMA_DIGEST
from banodoco_workspace_client.generated import Health
from astrid.core.execution.host_lane_policy import effective_host_capacity


def _handoff_file(tmp_path: Path, *, issuer_pid: int | None = None) -> tuple[Path, str]:
    from astrid.core.execution.process_group import _process_snapshot

    info = _process_snapshot()[os.getpid()]
    value = {
        "schema_version": 1,
        "issuer_pid": os.getpid() if issuer_pid is None else issuer_pid,
        "issuer_birth_id": info.birth,
        "attempt_id": "task-attempt",
        "support_root": str(tmp_path / "data" / "runtime"),
        "endpoint": "http://127.0.0.1:63540",
        "runtime_instance_id": "runtime-1",
        "runtime_epoch": 3,
        "schema_digest": SCHEMA_DIGEST,
        "executor_id": "astrid-pack-host",
        "ready_file": str(tmp_path / "generic-host.ready.json"),
        "source_checkout": str(tmp_path / "source"),
        "source_checkout_digest": "sha256:" + "a" * 64,
        "source_inventory_identity": "inventory-1",
        "boot_manifest_path": str(tmp_path / "data" / "runtime" / "astrid-host" / "boot-manifest.json"),
        "boot_manifest_hash": "sha256:" + "b" * 64,
        "readiness_profile_path": None,
        "readiness_profile_hash": None,
        "vibecomfy_execution_attestation": None,
        "effective_capacity": {"max_concurrency": 2},
        "python_executable": os.sys.executable,
    }
    path = tmp_path / ".astrid-runtime-handoff.json"
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(raw)
    path.chmod(0o600)
    return path, "sha256:" + hashlib.sha256(raw).hexdigest()


def _configure_nested(monkeypatch, path: Path, digest: str) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    monkeypatch.setenv(host_bootstrap.NESTED_HANDOFF_PATH_ENV, str(path))
    monkeypatch.setenv(host_bootstrap.NESTED_HANDOFF_HASH_ENV, digest)
    monkeypatch.delenv("BANODOCO_RUNTIME_CREDENTIAL", raising=False)
    monkeypatch.setenv("BANODOCO_LOCAL_LAUNCHER", "/usr/bin/banodoco-local")
    monkeypatch.delenv("BANODOCO_LOCAL_SOURCE_MANIFEST", raising=False)


def test_nested_attach_connects_only_and_reuses_host(monkeypatch, tmp_path: Path) -> None:
    path, digest = _handoff_file(tmp_path)
    _configure_nested(monkeypatch, path, digest)
    credential = tmp_path / "owner.credential"
    credential.write_text("owner-token", encoding="utf-8")
    worker_credential = tmp_path / "worker.credential"
    worker_credential.write_text("worker-token", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(autobootstrap, "_discovery_present", lambda _root: False)
    monkeypatch.setattr(
        autobootstrap,
        "_invoke_launcher",
        lambda command, **_kwargs: calls.append(command[1]) or {
            "status": "reconnected", "endpoint": "http://127.0.0.1:63540",
            "realm_id": "realm", "actor_id": "owner", "credential_file": str(credential),
            "worker_credential_file": str(worker_credential),
        },
    )
    health = Health(
        status="ok", protocol=PROTOCOL, schema_digest=SCHEMA_DIGEST,
        runtime_epoch=3, runtime_session_id="different-service-session",
        runtime_instance_id="runtime-1",
    )
    health_credentials: list[Path] = []
    original_read_credential = workspace_client._read_credential

    def read_worker_credential(path: Path) -> str:
        health_credentials.append(path)
        return original_read_credential(path)

    monkeypatch.setattr("astrid.sdk.workspace_client._read_credential", read_worker_credential)
    monkeypatch.setattr("astrid.sdk.workspace_client.WorkspaceClient.health", lambda _self: health)
    monkeypatch.setattr(autobootstrap, "_bootstrap_with_recovery", lambda *_a: pytest.fail("nested attach called up"))
    monkeypatch.setattr(host_bootstrap, "ensure_pack_host", lambda *_a, **_k: pytest.fail("nested attach reconfigured host"))
    attached: list[dict[str, object]] = []
    monkeypatch.setattr(host_bootstrap, "attach_pack_host", lambda context, runtime: attached.append({**dict(context), **{"observed_runtime": dict(runtime)}}) or {"host_status": "ready", "host_pid": context["issuer_pid"]})

    result = autobootstrap.ensure_runtime(data_root=tmp_path / "data")

    assert calls == ["connect"]
    assert result["host_status"] == "ready"
    assert attached[0]["readiness_profile_path"] is None
    assert attached[0]["effective_capacity"] == {"max_concurrency": 2}
    assert attached[0]["observed_runtime"]["runtime_instance_id"] == "runtime-1"
    assert attached[0]["observed_runtime"]["runtime_epoch"] == 3
    assert attached[0]["observed_runtime"]["schema_digest"] == SCHEMA_DIGEST
    assert result["status"] == "reconnected"
    assert health_credentials == [worker_credential]


def test_nested_attach_succeeds_with_live_health_and_canonical_b6(
    monkeypatch, tmp_path: Path
) -> None:
    from astrid.core.gateway.dispatch import compose_profile_handoff
    from astrid.core.execution.generic_host import GenericPackHost

    handoff_path, _ = _handoff_file(tmp_path)
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    support = Path(handoff["support_root"])
    support.mkdir(parents=True, exist_ok=True)
    boot_path = Path(handoff["boot_manifest_path"])
    boot = compose_profile_handoff(boot_path, support_root=support)
    handoff["boot_manifest_hash"] = boot["sha256"]
    handoff["effective_capacity"] = effective_host_capacity(
        2, parallel_lanes_enabled=True,
        resource_keys=("astrid-orchestration", "cpu"),
    )
    source = Path(handoff["source_checkout"])
    source.mkdir()
    handoff_path.write_text(json.dumps(handoff, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    handoff_path.chmod(0o600)
    handoff_hash = "sha256:" + hashlib.sha256(handoff_path.read_bytes()).hexdigest()
    _configure_nested(monkeypatch, handoff_path, handoff_hash)

    state = {
        key: value for key, value in handoff.items()
        if key not in {"schema_version", "attempt_id", "issuer_pid", "issuer_birth_id"}
    }
    state.update(pid=handoff["issuer_pid"], process_birth_id=handoff["issuer_birth_id"])
    ready = {
        **state, "status": "ready", "ready_capabilities": [],
        "registration": {"effective_capacity": handoff["effective_capacity"]},
    }
    support.mkdir(parents=True, exist_ok=True)
    (support / "generic-host.json").write_text(json.dumps(state), encoding="utf-8")
    Path(handoff["ready_file"]).write_text(json.dumps(ready), encoding="utf-8")
    monkeypatch.setattr(host_bootstrap, "_host_identity_matches", lambda _state: True)
    monkeypatch.setattr(
        "astrid.core.execution.generic_host.source_checkout_digest",
        lambda _path: handoff["source_checkout_digest"],
    )
    monkeypatch.setattr(
        "astrid.core.pack.source_setup.active_source_inventory",
        lambda: SimpleNamespace(identity=handoff["source_inventory_identity"], sources=("fixture",)),
    )

    credential = tmp_path / "owner.credential"
    credential.write_text("owner-token", encoding="utf-8")
    worker_credential = tmp_path / "worker.credential"
    worker_credential.write_text("worker-token", encoding="utf-8")
    health = Health(
        status="ok", protocol=PROTOCOL, schema_digest=SCHEMA_DIGEST,
        runtime_epoch=handoff["runtime_epoch"], runtime_session_id="service-session",
        runtime_instance_id=handoff["runtime_instance_id"],
    )
    monkeypatch.setattr("astrid.sdk.workspace_client.WorkspaceClient.health", lambda _self: health)
    monkeypatch.setattr(autobootstrap, "_discovery_present", lambda _root: False)
    monkeypatch.setattr(
        autobootstrap, "_invoke_launcher",
        lambda _command, **_kwargs: {
            "status": "reconnected", "endpoint": handoff["endpoint"],
            "realm_id": "realm", "actor_id": "owner", "credential_file": str(credential),
            "worker_credential_file": str(worker_credential),
        },
    )

    result = autobootstrap.ensure_runtime(data_root=tmp_path / "data")
    assert result["host_pid"] == handoff["issuer_pid"]
    assert result["host_runtime_instance_id"] == health.runtime_instance_id
    assert result["host_runtime_epoch"] == health.runtime_epoch
    assert result["status"] == "reconnected"
    assert "sha256:" + hashlib.sha256(boot_path.read_bytes()).hexdigest() != handoff["boot_manifest_hash"]

    host = object.__new__(GenericPackHost)
    host.client = SimpleNamespace(schema_digest=SCHEMA_DIGEST, health=lambda: health)
    assert host._runtime_compatibility()["runtime_instance_id"] == health.runtime_instance_id


@pytest.mark.parametrize(
    "health,launcher_assertion",
    [
        (Health("ok", PROTOCOL, SCHEMA_DIGEST, 3, "session", None), None),
        (Health("ok", PROTOCOL, SCHEMA_DIGEST, True, "session", "runtime-1"), None),
        (Health("ok", PROTOCOL, "wrong-schema", 3, "session", "runtime-1"), None),
        (Health("ok", "wrong-protocol", SCHEMA_DIGEST, 3, "session", "runtime-1"), None),
        (Health("ok", PROTOCOL, SCHEMA_DIGEST, 3, "session", "runtime-1"), "stale-runtime"),
    ],
)
def test_live_health_identity_rejects_missing_or_conflicting_identity(
    monkeypatch, tmp_path: Path, health: Health, launcher_assertion: str | None
) -> None:
    credential = tmp_path / "owner.credential"
    credential.write_text("owner-token", encoding="utf-8")
    monkeypatch.setattr("astrid.sdk.workspace_client.WorkspaceClient.health", lambda _self: health)
    connection = {
        "endpoint": "http://127.0.0.1:63540", "worker_credential_file": str(credential),
    }
    if launcher_assertion is not None:
        connection["runtime_instance_id"] = launcher_assertion
    with pytest.raises(autobootstrap.AutoBootstrapError):
        autobootstrap._live_runtime_identity(connection)


@pytest.mark.parametrize("damage", ["missing-hash", "foreign-issuer", "corrupt-bytes"])
def test_nested_handoff_rejects_invalid_or_foreign_context(monkeypatch, tmp_path: Path, damage: str) -> None:
    path, digest = _handoff_file(tmp_path, issuer_pid=999999 if damage == "foreign-issuer" else None)
    if damage == "corrupt-bytes":
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o600)
    _configure_nested(monkeypatch, path, digest if damage != "missing-hash" else "")
    if damage == "missing-hash":
        monkeypatch.delenv(host_bootstrap.NESTED_HANDOFF_HASH_ENV)
    calls: list[str] = []
    monkeypatch.setattr(autobootstrap, "_invoke_launcher", lambda command, **_kw: calls.append(command[1]))
    with pytest.raises(autobootstrap.AutoBootstrapError):
        autobootstrap.ensure_runtime(data_root=tmp_path / "data")
    assert calls == []


def test_launcher_lifecycle_result_preserves_optional_runtime_identity() -> None:
    identity = {
        "runtime_instance_id": "instance-from-launcher",
        "runtime_epoch": 9,
        "schema_digest": SCHEMA_DIGEST,
    }
    result = autobootstrap._lifecycle_result(
        {
            "status": "reconnected", "realm_id": "realm", "endpoint": "http://127.0.0.1:1",
            "actor_id": "owner", **identity,
        },
        action="connection", started=time.monotonic(),
        allowed_statuses=frozenset({"reconnected"}),
    )
    assert {field: result[field] for field in identity} == identity


@pytest.mark.parametrize("field", ["runtime_instance_id", "runtime_epoch", "schema_digest"])
def test_attach_rejects_missing_expected_identity(field: str, tmp_path: Path) -> None:
    path, _digest = _handoff_file(tmp_path)
    context = json.loads(path.read_text(encoding="utf-8"))
    context[field] = None
    with pytest.raises(host_bootstrap.PackHostBootstrapError, match="identity is incomplete"):
        host_bootstrap.attach_pack_host(context, {})


def test_internal_marker_without_handoff_cannot_fall_back_to_external_launch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    monkeypatch.delenv(host_bootstrap.NESTED_HANDOFF_PATH_ENV, raising=False)
    monkeypatch.delenv(host_bootstrap.NESTED_HANDOFF_HASH_ENV, raising=False)
    monkeypatch.setenv("BANODOCO_LOCAL_LAUNCHER", "/usr/bin/banodoco-local")
    calls: list[str] = []
    monkeypatch.setattr(autobootstrap, "_invoke_launcher", lambda command, **_kw: calls.append(command[1]))
    with pytest.raises(autobootstrap.AutoBootstrapError, match="requires a validated host handoff"):
        autobootstrap.ensure_runtime(data_root=tmp_path / "data")
    assert calls == []


def test_nested_client_uses_launcher_owner_credential_not_worker_environment(monkeypatch, tmp_path: Path) -> None:
    credential = tmp_path / "owner.credential"
    credential.write_text("owner-token", encoding="utf-8")
    monkeypatch.setenv(host_bootstrap.NESTED_HANDOFF_PATH_ENV, "/host/issued/context")
    monkeypatch.setenv(host_bootstrap.NESTED_HANDOFF_HASH_ENV, "sha256:" + "a" * 64)
    monkeypatch.setenv("BANODOCO_RUNTIME_CREDENTIAL", "worker-token")
    monkeypatch.setattr(
        "astrid.sdk.autobootstrap.ensure_runtime",
        lambda **_kwargs: {
            "endpoint": "http://runtime.test", "realm_id": "realm", "actor_id": "owner",
            "credential_file": str(credential),
        },
    )
    observed: dict[str, object] = {}
    monkeypatch.setattr(AstridClient, "open", classmethod(lambda cls, **kwargs: observed.update(kwargs) or object()))

    AstridClient.open_from_launcher()

    assert observed["credential"] == credential
    assert observed["realm_id"] == "realm"
    assert observed["actor_id"] == "owner"


@pytest.mark.parametrize("mismatch", [
    None, "endpoint", "runtime_instance_id", "runtime_epoch", "schema_digest",
    "missing_runtime_instance_id", "missing_runtime_epoch", "missing_schema_digest",
    "capacity", "attestation", "source", "interpreter",
])
def test_attach_validator_reuses_exact_profile_free_host_read_only(
    monkeypatch, tmp_path: Path, mismatch: str | None
) -> None:
    path, _digest = _handoff_file(tmp_path)
    context = json.loads(path.read_text(encoding="utf-8"))
    source = Path(context["source_checkout"])
    source.mkdir()
    boot = Path(context["boot_manifest_path"])
    boot.parent.mkdir(parents=True, exist_ok=True)
    from astrid.core.gateway.dispatch import compose_profile_handoff

    boot_handoff = compose_profile_handoff(boot, support_root=Path(context["support_root"]))
    context["boot_manifest_hash"] = boot_handoff["sha256"]
    # The handoff hash is semantic; deliberately make the file's byte hash differ.
    boot.write_text(json.dumps(json.loads(boot.read_text()), indent=3) + "\n", encoding="utf-8")
    assert "sha256:" + hashlib.sha256(boot.read_bytes()).hexdigest() != context["boot_manifest_hash"]
    context["source_checkout_digest"] = "checkout-digest"
    state = {key: value for key, value in context.items() if key not in {"schema_version", "attempt_id", "issuer_pid", "issuer_birth_id"}}
    state.update(pid=context["issuer_pid"], process_birth_id=context["issuer_birth_id"])
    ready = {**state, "status": "ready", "ready_capabilities": []}
    support = Path(context["support_root"])
    support.mkdir(parents=True, exist_ok=True)
    (support / "generic-host.json").write_text(json.dumps(state), encoding="utf-8")
    Path(context["ready_file"]).write_text(json.dumps(ready), encoding="utf-8")
    if mismatch == "capacity":
        ready["effective_capacity"] = {"max_concurrency": 1}
    if mismatch == "attestation":
        ready["vibecomfy_execution_attestation"] = {"approved": True}
    monkeypatch.setattr(host_bootstrap, "_read_object", lambda candidate: state if candidate.name == "generic-host.json" else ready)
    monkeypatch.setattr(host_bootstrap, "_host_identity_matches", lambda _state: True)
    monkeypatch.setattr(host_bootstrap, "_capacity_readiness_matches", lambda _ready: mismatch != "capacity")
    monkeypatch.setattr(host_bootstrap, "_readiness_profile_ack_matches", lambda *_args, **_kwargs: mismatch != "attestation")
    monkeypatch.setattr(
        "astrid.core.execution.generic_host.source_checkout_digest",
        lambda _source: "changed-checkout" if mismatch == "source" else "checkout-digest",
    )
    monkeypatch.setattr(
        "astrid.core.pack.source_setup.active_source_inventory",
        lambda: SimpleNamespace(identity="inventory-1", sources=("fixture",)),
    )
    if mismatch == "interpreter":
        monkeypatch.setattr(host_bootstrap.sys, "executable", "/foreign/python")
    runtime = {
        "endpoint": context["endpoint"],
        "runtime_instance_id": context["runtime_instance_id"],
        "runtime_epoch": context["runtime_epoch"],
        "schema_digest": context["schema_digest"],
    }
    if mismatch == "endpoint":
        runtime["endpoint"] = "http://foreign-runtime.test"
    elif mismatch in {"runtime_instance_id", "runtime_epoch", "schema_digest"}:
        runtime[mismatch] = {"runtime_instance_id": "foreign", "runtime_epoch": 4, "schema_digest": "foreign-schema"}[mismatch]
    elif mismatch and mismatch.startswith("missing_runtime_"):
        runtime[mismatch.removeprefix("missing_")] = None
    elif mismatch == "missing_schema_digest":
        runtime["schema_digest"] = None

    if mismatch is None:
        attached = host_bootstrap.attach_pack_host(context, runtime)
        assert attached["host_pid"] == context["issuer_pid"]
        assert attached["host_ready_capabilities"] == []
        assert attached["effective_capacity"] == context["effective_capacity"]
    else:
        with pytest.raises(host_bootstrap.PackHostBootstrapError):
            host_bootstrap.attach_pack_host(context, runtime)
