import json
from pathlib import Path

import pytest

from astrid.sdk import upgrade


def _catalog(root: Path, *, realm_id: str = "realm-1", realms=None) -> None:
    path = root / "runtime" / "catalog.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "selected_realm_id": realm_id,
                "realms": realms
                if realms is not None
                else [{"realm_id": realm_id, "data_root": str(root / "runtime" / "realms" / realm_id)}],
            }
        ),
        encoding="utf-8",
    )


def test_upgrade_roots_use_configured_target_and_known_legacy_source(monkeypatch, tmp_path):
    target = tmp_path / "Astrid" / ".astrid-data"
    legacy = tmp_path / "Library" / "Application Support" / "Banodoco"
    _catalog(legacy)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(upgrade, "resolve_runtime_data_root", lambda: target)

    source, resolved_target, realm_id = upgrade.resolve_upgrade_roots()

    assert source == legacy
    assert resolved_target == target
    assert realm_id == "realm-1"
    assert not target.exists()


def test_upgrade_refuses_empty_target_without_source(monkeypatch, tmp_path):
    target = tmp_path / "Astrid" / ".astrid-data"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(upgrade, "resolve_runtime_data_root", lambda: target)

    with pytest.raises(upgrade.UpgradeError, match="empty realm"):
        upgrade.resolve_upgrade_roots()


def test_upgrade_accepts_selected_realm_in_multi_realm_catalog(tmp_path):
    source = tmp_path / "source"
    _catalog(
        source,
        realms=[
            {"realm_id": "realm-1", "data_root": str(source / "runtime" / "realms" / "realm-1")},
            {"realm_id": "realm-2", "data_root": str(source / "runtime" / "realms" / "realm-2")},
        ],
    )

    resolved_source, _, realm_id = upgrade.resolve_upgrade_roots(
        source=source, destination=tmp_path / "target"
    )

    assert resolved_source == source
    assert realm_id == "realm-1"


def test_upgrade_refuses_ambiguous_explicit_source(tmp_path):
    source = tmp_path / "source"
    _catalog(
        source,
        realm_id="missing",
        realms=[
            {"realm_id": "realm-1", "data_root": str(source / "runtime" / "realms" / "realm-1")},
            {"realm_id": "realm-1", "data_root": str(source / "runtime" / "realms" / "realm-duplicate")},
        ],
    )

    with pytest.raises(upgrade.UpgradeError, match="ambiguous"):
        upgrade.resolve_upgrade_roots(source=source, destination=tmp_path / "target")


def test_upgrade_delegates_cutover_then_relaunches_target(monkeypatch, tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _catalog(target)
    calls = []
    monkeypatch.setattr(upgrade, "resolve_upgrade_roots", lambda **_: (source, target, "realm-1"))
    monkeypatch.setattr(upgrade, "stop_pack_host", lambda root: {"host_status": "stopped"})
    monkeypatch.setattr(upgrade, "_launcher_upgrade", lambda *args: calls.append(("upgrade", args)) or {"status": "activated"})
    monkeypatch.setattr(
        upgrade,
        "ensure_runtime",
        lambda **kwargs: calls.append(("runtime", kwargs))
        or {"status": "started", "credential_file": "/private/secret", "worker_credential_file": "/private/worker"},
    )

    result = upgrade.upgrade()

    assert result["ok"] is True
    assert result["realm_id"] == "realm-1"
    assert "credential_file" not in result["runtime"]
    assert "worker_credential_file" not in result["runtime"]
    assert calls[0] == ("upgrade", (source, target, None))
    assert calls[1] == ("runtime", {"start_pack_host": True, "data_root": target})


def test_launcher_upgrade_uses_reviewed_neutral_command(monkeypatch, tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    manifest = tmp_path / "profile.json"
    manifest.write_text("{}", encoding="utf-8")
    seen = {}

    class Completed:
        returncode = 0
        stdout = '{"ok": true, "status": "activated"}'

    monkeypatch.setattr(upgrade, "_launcher_command", lambda: ["/opt/banodoco-local"])
    monkeypatch.setattr(upgrade.subprocess, "run", lambda command, **kwargs: seen.update(command=command, kwargs=kwargs) or Completed())

    result = upgrade._launcher_upgrade(source, target, manifest)

    assert result == {"ok": True, "status": "activated"}
    assert seen["command"] == [
        "/opt/banodoco-local", "upgrade", "--profile", "astrid", "--data-root", str(source),
        "--destination", str(target), "--source-manifest", str(manifest), "--json",
    ]
    assert "timeout" not in seen["kwargs"]


def test_upgrade_restarts_source_host_when_cutover_rejected(monkeypatch, tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _catalog(source)
    restarts = []
    monkeypatch.setattr(upgrade, "resolve_upgrade_roots", lambda **_: (source, target, "realm-1"))
    monkeypatch.setattr(upgrade, "stop_pack_host", lambda root: {"host_status": "stopped"})
    monkeypatch.setattr(upgrade, "_launcher_upgrade", lambda *args: (_ for _ in ()).throw(upgrade.UpgradeError("rejected")))
    monkeypatch.setattr(upgrade, "ensure_runtime", lambda **kwargs: restarts.append(kwargs) or {"status": "started"})

    with pytest.raises(upgrade.UpgradeError, match="rejected"):
        upgrade.upgrade()

    assert restarts == [{"start_pack_host": True, "data_root": source}]
