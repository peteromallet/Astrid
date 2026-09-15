from __future__ import annotations

import subprocess

import pytest

from astrid.sdk import autobootstrap


@pytest.fixture
def launcher_data_root(monkeypatch, tmp_path):
    data_root = tmp_path.resolve() / "runtime-support"
    monkeypatch.setenv("BANODOCO_LOCAL_DATA_ROOT", str(data_root))
    monkeypatch.delenv("BANODOCO_LOCAL_SOURCE_MANIFEST", raising=False)
    monkeypatch.setenv("BANODOCO_LOCAL_LAUNCHER", "/usr/bin/banodoco-local")
    return data_root


def _launcher_result(status: str, *, ok: bool = True) -> str:
    return (
        '{"ok":false,"error":{"code":"conflict","message":"owner busy"}}'
        if not ok
        else '{"status":"' + status + '","realm_id":"realm-1",'
        '"endpoint":"http://127.0.0.1:1","actor_id":"astrid-owner"}'
    )


def test_thin_launcher_accepts_restarted_owner_and_preserves_normal_command(monkeypatch, launcher_data_root):
    seen: list[list[str]] = []
    monkeypatch.setattr(
        autobootstrap.subprocess,
        "run",
        lambda command, **kwargs: seen.append(command)
        or subprocess.CompletedProcess(command, 0, _launcher_result("restarted"), ""),
    )

    result = autobootstrap.ensure_runtime(start_pack_host=False)

    assert result["status"] == "restarted"
    assert seen == [[
        "/usr/bin/banodoco-local", "up", "--profile", "astrid",
        "--data-root", str(launcher_data_root), "--json"
    ]]


@pytest.mark.parametrize(
    "completed, message",
    [
        (subprocess.CompletedProcess([], 1, _launcher_result("conflict", ok=False), ""), "bootstrap was not ready"),
        (subprocess.CompletedProcess([], 0, "", "launcher interrupted"), "bootstrap returned invalid JSON"),
    ],
)
def test_thin_launcher_fails_closed_on_conflict_or_interruption(monkeypatch, launcher_data_root, completed, message):
    seen: list[list[str]] = []
    monkeypatch.setattr(
        autobootstrap.subprocess, "run",
        lambda command, **kwargs: seen.append(command) or completed,
    )

    with pytest.raises(autobootstrap.AutoBootstrapError, match=message):
        autobootstrap.ensure_runtime(start_pack_host=False)
    assert seen == [[
        "/usr/bin/banodoco-local", "up", "--profile", "astrid",
        "--data-root", str(launcher_data_root), "--json"
    ]]


def test_doctor_uses_cheap_launcher_boundary_without_pack_host(monkeypatch, capsys):
    from astrid.core.gateway import dispatch
    from astrid.sdk import client as sdk_client

    seen: list[bool] = []

    class _Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def doctor(self):
            return {"ok": True, "state": "ready"}

    def open_from_launcher(cls, **kwargs):
        seen.append(kwargs["start_pack_host"])
        return _Client()

    monkeypatch.setattr(
        sdk_client.AstridClient,
        "open_from_launcher",
        classmethod(open_from_launcher),
    )

    assert dispatch._dispatch_doctor(["--json"]) == 0
    assert seen == [False]
    assert '"state": "ready"' in capsys.readouterr().out
