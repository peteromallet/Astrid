from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from astrid.core.execution.generic_host import (
    GenericPackHost,
    HostError,
    RuntimeProtocolClient,
    _process_birth_identity,
    load_worker_readiness_profile,
    validate_readiness_profile_health,
)


def _fixture(tmp_path: Path) -> tuple[dict[str, object], Path, str]:
    source = tmp_path / "Astrid"
    pack_root = source / "astrid" / "packs"
    pack_root.mkdir(parents=True)
    support = tmp_path / "support"
    credentials = support / "credentials"
    credentials.mkdir(parents=True)
    credential = credentials / "worker.token"
    credential.write_text("sentinel-worker-token\n", encoding="utf-8")
    credential.chmod(0o600)
    output = tmp_path / "output"
    output.mkdir()
    manifest = support / "astrid-host" / "boot-manifest.json"
    manifest.parent.mkdir()
    manifest.write_text("{}", encoding="utf-8")
    ready = support / "generic-host.ready.json"
    state = support / "generic-host.json"
    facts = {
        "exact": {
            "interpreter": str(Path(sys.executable).resolve()),
            "runtime_lock": "sha256:" + "1" * 64,
            "engine_lock": "sha256:" + "2" * 64,
            "model_digest": "sha256:" + "3" * 64,
            "custom_node_digest": "sha256:" + "4" * 64,
            "driver": "fixture-driver",
            "root": "sha256:" + "5" * 64,
            "port": 18765,
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
            "endpoint": "http://127.0.0.1:18765",
            "port": 18765,
            "pid": os.getpid(),
            "process_birth_id": _process_birth_identity(os.getpid()),
            "runtime_instance_id": "runtime-1",
            "runtime_epoch": 1,
            "schema_digest": "sha256:" + "6" * 64,
            "coordinator_epoch": "runtime-1",
            "active_realm": "realm-1",
            "credential_reference": str(credential),
            "discovery_digest": "sha256:" + "7" * 64,
        },
        "launch": {
            "host_interpreter": str(Path(sys.executable).resolve()),
            "source_checkout": str(source),
            "engine_interpreter": str(Path(sys.executable).resolve()),
            "output_root": str(output),
            "pack_root": str(pack_root),
            "support_root": str(support),
            "ready_file": str(ready),
            "state_file": str(state),
            "boot_manifest_path": str(manifest),
            "boot_manifest_hash": "sha256:" + hashlib.sha256(manifest.read_bytes()).hexdigest(),
        },
        "worker_actor": "astrid-pack-host",
        "worker_scopes": [
            "handshake", "worker:register", "worker:execute", "tasks:read", "objects:read", "objects:write",
        ],
    }
    profile_path = support / "worker-readiness-profile.json"
    raw = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    profile_path.write_bytes(raw)
    profile_path.chmod(0o600)
    context = {
        "support_root": support,
        "source_checkout": source,
        "pack_root": pack_root,
        "runtime_endpoint": "http://127.0.0.1:18765",
        "runtime_instance_id": "runtime-1",
        "credential_path": credential,
        "ready_file": ready,
        "state_file": state,
        "boot_manifest_path": manifest,
        "boot_manifest_hash": profile["launch"]["boot_manifest_hash"],
    }
    return context, profile_path, "sha256:" + hashlib.sha256(raw).hexdigest()


def _load(context: dict[str, object], profile_path: Path, profile_hash: str) -> dict[str, object]:
    return load_worker_readiness_profile(
        profile_path,
        profile_hash,
        **context,
        host_interpreter=sys.executable,
        credential=Path(context["credential_path"]).read_text(encoding="utf-8").strip(),
    )


def test_profile_consumer_validates_binding_and_health(tmp_path: Path) -> None:
    context, profile_path, profile_hash = _fixture(tmp_path)
    profile = _load(context, profile_path, profile_hash)
    validate_readiness_profile_health(
        profile,
        {"status": "ok", "protocol": "workspace.v1", "schema_digest": profile["runtime"]["schema_digest"], "runtime_epoch": 1},
    )
    assert profile["verified_facts"]["exact"]["port"] == 18765
    assert "sentinel-worker-token" not in profile_path.read_text(encoding="utf-8")


@pytest.mark.parametrize("mutation", ["missing", "tampered", "stale"])
def test_profile_consumer_fails_before_registration_for_invalid_profile(tmp_path: Path, mutation: str) -> None:
    context, profile_path, profile_hash = _fixture(tmp_path)
    if mutation == "missing":
        profile_path.unlink()
    elif mutation == "tampered":
        profile_path.write_bytes(profile_path.read_bytes().replace(b"runtime-1", b"runtime-2", 1))
    else:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        profile["runtime"]["runtime_epoch"] = 2
        profile_path.write_text(json.dumps(profile, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        profile_path.chmod(0o600)
    with pytest.raises(HostError):
        _load(context, profile_path, profile_hash)


def test_generic_host_forwards_exact_verified_facts(tmp_path: Path) -> None:
    context, profile_path, profile_hash = _fixture(tmp_path)
    profile = _load(context, profile_path, profile_hash)

    pack = Path(context["pack_root"]) / "echo"
    pack.mkdir()
    (pack / "executor.yaml").write_text(
        json.dumps({
            "schema_version": 1,
            "id": "test.echo",
            "name": "Echo",
            "kind": "external",
            "version": "1.0",
            "command": {"argv": ["{python_exec}", "-c", "print('ok')"]},
            "outputs": [],
            "metadata": {"resource_keys": ["cpu"]},
        }),
        encoding="utf-8",
    )

    class Runtime:
        schema_digest = profile["runtime"]["schema_digest"]

        def health(self):
            return {"status": "ok", "protocol": "workspace.v1", "schema_digest": self.schema_digest, "runtime_epoch": 1}

        def register_capability(self, *_args, **_kwargs):
            return None

        def register_executor(self, executor_id, **payload):
            self.registration = (executor_id, payload)
            return {"executor_id": executor_id}

    runtime = Runtime()
    host = GenericPackHost(
        pack_roots=[Path(context["pack_root"])],
        client=runtime,
        readiness_profile_path=profile_path,
        readiness_profile_hash=profile_hash,
        runtime_authority=True,
    )
    host.bind_readiness_profile(profile)
    host.discover()
    host.register()
    assert runtime.registration[1]["verified_facts"] == profile["verified_facts"]
    assert runtime.registration[1]["readiness"] == "ready"


class _RuntimeAuthorityProbe:
    worker_authority = True

    def __init__(self, profile: dict[str, object]):
        self.schema_digest = profile["runtime"]["schema_digest"]
        self.registrations: list[object] = []
        self.claims: list[object] = []

    def health(self):
        return {
            "status": "ok",
            "protocol": "workspace.v1",
            "schema_digest": self.schema_digest,
            "runtime_epoch": 1,
        }

    def register_capability(self, *_args, **_kwargs):
        return None

    def register_executor(self, *args, **kwargs):
        self.registrations.append((args, kwargs))
        return {"executor_id": args[0] if args else ""}

    def claim_next(self, **kwargs):
        self.claims.append(kwargs)
        return None


def test_runtime_host_requires_profile_before_registration_and_claim(tmp_path: Path) -> None:
    context, _profile_path, _profile_hash = _fixture(tmp_path)
    runtime = _RuntimeAuthorityProbe(_load(context, _profile_path, _profile_hash))
    host = GenericPackHost(
        pack_roots=[Path(context["pack_root"])],
        client=runtime,
        runtime_authority=False,
    )

    with pytest.raises(HostError, match="explicit Worker readiness profile path and hash"):
        host.register()
    with pytest.raises(HostError, match="explicit Worker readiness profile path and hash"):
        host.claim_once()
    assert runtime.registrations == []
    assert runtime.claims == []


def test_default_runtime_protocol_client_cannot_be_downgraded_before_registration_and_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Generated:
        def __init__(self, *_args):
            self.registrations = []
            self.claims = []

        def register_executor(self, *args, **kwargs):
            self.registrations.append((args, kwargs))

        def claim_task(self, **kwargs):
            self.claims.append(kwargs)

    monkeypatch.setattr("banodoco_workspace_client.WorkspaceClient", Generated)
    client = RuntimeProtocolClient("http://127.0.0.1:18765", "worker-token")
    host = GenericPackHost(
        pack_roots=[tmp_path],
        client=client,
        runtime_authority=False,
    )

    assert client.worker_authority is True
    assert host._runtime_authority is True
    with pytest.raises(HostError, match="explicit Worker readiness profile path and hash"):
        host.register()
    with pytest.raises(HostError, match="explicit Worker readiness profile path and hash"):
        host.claim_once()
    assert client.generated.registrations == []
    assert client.generated.claims == []


@pytest.mark.parametrize(
    ("section", "key", "value"),
    (
        ("runtime", "port", 18766),
        ("runtime", "credential_reference", "changed-worker.token"),
        ("launch", "source_checkout", "/private/var/empty/changed-source"),
    ),
)
def test_runtime_host_revalidates_nested_profile_against_immutable_context(
    tmp_path: Path, section: str, key: str, value: object
) -> None:
    context, profile_path, profile_hash = _fixture(tmp_path)
    profile = _load(context, profile_path, profile_hash)
    runtime = _RuntimeAuthorityProbe(profile)
    host = GenericPackHost(
        pack_roots=[Path(context["pack_root"])],
        client=runtime,
        readiness_profile_path=profile_path,
        readiness_profile_hash=profile_hash,
        runtime_authority=True,
    )
    host.bind_readiness_profile(profile)
    host.discover()

    mutated = json.loads(profile_path.read_text(encoding="utf-8"))
    mutated[section][key] = value
    profile_path.write_text(json.dumps(mutated, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    profile_path.chmod(0o600)
    # The supplied hash is recomputed, but the original validation context is
    # intentionally immutable inside the host.
    host.readiness_profile_hash = "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest()

    with pytest.raises(HostError):
        host.register()
    with pytest.raises(HostError):
        host.claim_once()
    assert runtime.registrations == []
    assert runtime.claims == []
