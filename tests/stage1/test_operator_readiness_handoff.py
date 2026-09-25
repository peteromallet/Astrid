from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from astrid.sdk import autobootstrap
from astrid.sdk import host_bootstrap


def _profile(tmp_path: Path, name: str = "readiness.json") -> tuple[Path, str]:
    hook = tmp_path / f"{name}.py"
    hook.write_text("ASTRID_T9_MODEL_SUBSTITUTE_ACTIVE = True\n", encoding="utf-8")
    profile_path = tmp_path / name
    profile = {
        "verified_facts": {"exact": {}, "minimum": {}},
        "vibecomfy_candidate": {
            "kind": "local_snapshot",
            "revision": "fixture-revision",
            "source_content_digest": "sha256:" + "a" * 64,
        },
        "t9_model_substitute": {
            "approved": True,
            "mode": "deterministic_cpu_model_boundary_v1",
            "source_path": str(hook),
            "source_sha256": "sha256:" + hashlib.sha256(hook.read_bytes()).hexdigest(),
        },
    }
    profile_path.write_text(json.dumps(profile, sort_keys=True), encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest()
    return profile_path, digest


def _runtime_response(tmp_path: Path) -> dict[str, object]:
    worker = tmp_path / "worker.token"
    worker.write_text("worker-secret", encoding="utf-8")
    return {
        "status": "reconnected",
        "endpoint": "http://runtime.test",
        "actor_id": "owner",
        "worker_credential_file": str(worker),
        "worker_actor": "astrid-pack-host",
        "worker_scopes": ["worker:register", "worker:execute"],
        "source_checkout": str(tmp_path / "source"),
        "source_checkout_digest": "sha256:" + "b" * 64,
        "boot_manifest_path": str(tmp_path / "boot.json"),
        "boot_manifest_hash": "sha256:" + "c" * 64,
        "runtime_instance_id": "runtime-1",
        "runtime_epoch": "epoch-1",
        "capacity": {"max_concurrency": 2},
    }


def _install_launcher(monkeypatch, response, *, connect: bool) -> list[str]:
    calls: list[str] = []
    # These cases exercise the external operator path even when the test
    # runner itself was launched from an Astrid child environment.
    monkeypatch.delenv("ASTRID_INTERNAL_INVOCATION", raising=False)
    monkeypatch.delenv(host_bootstrap.NESTED_HANDOFF_PATH_ENV, raising=False)
    monkeypatch.delenv(host_bootstrap.NESTED_HANDOFF_HASH_ENV, raising=False)
    monkeypatch.setenv("BANODOCO_LOCAL_LAUNCHER", "/usr/bin/banodoco-local")
    monkeypatch.delenv("BANODOCO_LOCAL_SOURCE_MANIFEST", raising=False)
    monkeypatch.setattr(autobootstrap, "_discovery_present", lambda _root: connect)
    monkeypatch.setattr(
        autobootstrap,
        "_invoke_launcher",
        lambda command, **_kwargs: calls.append(command[1]) or dict(response),
    )
    monkeypatch.setattr(
        autobootstrap,
        "_bootstrap_with_recovery",
        lambda command: calls.append(command[1]) or dict(response),
    )
    return calls


@pytest.mark.parametrize("connect", [False, True], ids=["cold-up", "warm-connect"])
def test_operator_readiness_pair_is_validated_and_forwarded(
    monkeypatch, tmp_path: Path, connect: bool
) -> None:
    profile_path, digest = _profile(tmp_path)
    response = _runtime_response(tmp_path)
    original = dict(response)
    calls = _install_launcher(monkeypatch, response, connect=connect)
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_HASH", digest)
    handoffs: list[dict[str, object]] = []

    def ensure_pack_host(value, **_kwargs):
        handoffs.append(dict(value))
        return {"host_status": "ready"}

    monkeypatch.setattr(host_bootstrap, "ensure_pack_host", ensure_pack_host)

    result = autobootstrap.ensure_runtime(data_root=tmp_path / "runtime-data")

    assert calls == ["connect" if connect else "up"]
    assert result["host_status"] == "ready"
    assert len(handoffs) == 1
    assert handoffs[0]["readiness_profile_path"] == str(profile_path)
    assert handoffs[0]["readiness_profile_hash"] == digest
    for name in (
        "source_checkout",
        "source_checkout_digest",
        "boot_manifest_path",
        "boot_manifest_hash",
        "runtime_instance_id",
        "runtime_epoch",
        "capacity",
    ):
        assert handoffs[0][name] == response[name]
    assert response == original


@pytest.mark.parametrize(
    "selection",
    [
        {"ASTRID_HOST_READINESS_PROFILE_PATH": "only-path"},
        {"ASTRID_HOST_READINESS_PROFILE_HASH": "sha256:" + "a" * 64},
        {
            "ASTRID_HOST_READINESS_PROFILE_PATH": "",
            "ASTRID_HOST_READINESS_PROFILE_HASH": "",
        },
        {
            "ASTRID_HOST_READINESS_PROFILE_PATH": "relative.json",
            "ASTRID_HOST_READINESS_PROFILE_HASH": "sha256:" + "a" * 64,
        },
    ],
    ids=["path-only", "hash-only", "blank-pair", "relative-path"],
)
def test_invalid_operator_pair_fails_before_host_handoff(
    monkeypatch, tmp_path: Path, selection: dict[str, str]
) -> None:
    response = _runtime_response(tmp_path)
    _install_launcher(monkeypatch, response, connect=False)
    for key in ("ASTRID_HOST_READINESS_PROFILE_PATH", "ASTRID_HOST_READINESS_PROFILE_HASH"):
        monkeypatch.delenv(key, raising=False)
    for key, value in selection.items():
        monkeypatch.setenv(key, value)
    called: list[bool] = []
    monkeypatch.setattr(
        host_bootstrap,
        "ensure_pack_host",
        lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(autobootstrap.AutoBootstrapError):
        autobootstrap.ensure_runtime(data_root=tmp_path / "runtime-data")
    assert called == []


@pytest.mark.parametrize("kind", ["missing", "symlink", "wrong-hash", "bad-json", "bad-attestation"])
def test_unusable_operator_profile_fails_before_host_handoff(
    monkeypatch, tmp_path: Path, kind: str
) -> None:
    profile_path, digest = _profile(tmp_path)
    if kind == "missing":
        profile_path.unlink()
    elif kind == "symlink":
        target = tmp_path / "target.json"
        target.write_bytes(profile_path.read_bytes())
        profile_path.unlink()
        profile_path.symlink_to(target)
    elif kind == "bad-json":
        profile_path.write_text("not-json", encoding="utf-8")
        digest = "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest()
    elif kind == "bad-attestation":
        profile_path.write_text(
            json.dumps({"vibecomfy_candidate": {"kind": "local_snapshot"}}),
            encoding="utf-8",
        )
        digest = "sha256:" + hashlib.sha256(profile_path.read_bytes()).hexdigest()
    elif kind == "wrong-hash":
        digest = "sha256:" + "0" * 64

    _install_launcher(monkeypatch, _runtime_response(tmp_path), connect=False)
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(profile_path))
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_HASH", digest)
    called: list[bool] = []
    monkeypatch.setattr(
        host_bootstrap,
        "ensure_pack_host",
        lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(autobootstrap.AutoBootstrapError):
        autobootstrap.ensure_runtime(data_root=tmp_path / "runtime-data")
    assert called == []


def test_conflicting_launcher_and_operator_profiles_fail_closed(monkeypatch, tmp_path: Path) -> None:
    launcher_path, launcher_hash = _profile(tmp_path, "launcher.json")
    operator_path, operator_hash = _profile(tmp_path, "operator.json")
    response = _runtime_response(tmp_path)
    response.update(
        readiness_profile_path=str(launcher_path),
        readiness_profile_hash=launcher_hash,
    )
    _install_launcher(monkeypatch, response, connect=False)
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(operator_path))
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_HASH", operator_hash)
    called: list[bool] = []
    monkeypatch.setattr(
        host_bootstrap,
        "ensure_pack_host",
        lambda *_args, **_kwargs: called.append(True),
    )

    with pytest.raises(autobootstrap.AutoBootstrapError, match="conflicts"):
        autobootstrap.ensure_runtime(data_root=tmp_path / "runtime-data")
    assert called == []


def test_profile_free_host_handoff_and_runtime_only_ignore_host_environment(
    monkeypatch, tmp_path: Path
) -> None:
    response = _runtime_response(tmp_path)
    _install_launcher(monkeypatch, response, connect=False)
    monkeypatch.delenv("ASTRID_HOST_READINESS_PROFILE_PATH", raising=False)
    monkeypatch.delenv("ASTRID_HOST_READINESS_PROFILE_HASH", raising=False)
    handoffs: list[dict[str, object]] = []
    monkeypatch.setattr(
        host_bootstrap,
        "ensure_pack_host",
        lambda value, **_kwargs: handoffs.append(dict(value)) or {"host_status": "ready"},
    )

    autobootstrap.ensure_runtime(data_root=tmp_path / "runtime-data")
    assert len(handoffs) == 1
    assert "readiness_profile_path" not in handoffs[0]
    assert "readiness_profile_hash" not in handoffs[0]

    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", "relative-invalid.json")
    monkeypatch.delenv("ASTRID_HOST_READINESS_PROFILE_HASH", raising=False)
    handoffs.clear()
    autobootstrap.ensure_runtime(start_pack_host=False, data_root=tmp_path / "runtime-data")
    assert handoffs == []
