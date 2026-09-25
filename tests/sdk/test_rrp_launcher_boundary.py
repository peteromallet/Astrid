from __future__ import annotations

import multiprocessing
import subprocess
import threading
import time
from pathlib import Path

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


def _hold_acquisition_lock(data_root: str, entered, release) -> None:
    with autobootstrap._acquisition_file_lock(Path(data_root), timeout=2.0):
        entered.set()
        release.wait(5.0)


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


def test_acquisition_lock_is_canonical_and_cross_process_serialized(launcher_data_root):
    assert autobootstrap._acquisition_lock_path(launcher_data_root) == (
        launcher_data_root / "runtime" / "acquisition.lock"
    )

    context = multiprocessing.get_context("spawn")
    entered = context.Event()
    release = context.Event()
    holder = context.Process(
        target=_hold_acquisition_lock,
        args=(str(launcher_data_root), entered, release),
    )
    holder.start()
    releaser = None
    try:
        assert entered.wait(5.0)
        releaser = threading.Timer(0.15, release.set)
        releaser.start()
        started = time.monotonic()
        with autobootstrap._acquisition_file_lock(launcher_data_root, timeout=2.0):
            elapsed = time.monotonic() - started
        assert elapsed >= 0.10
    finally:
        if releaser is not None:
            releaser.join(5.0)
        release.set()
        holder.join(5.0)
        if holder.is_alive():
            holder.terminate()
            holder.join(5.0)
    assert holder.exitcode == 0


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


def test_doctor_uses_nonstarting_runtime_observer(monkeypatch, capsys, tmp_path):
    from astrid.core.gateway import dispatch
    from astrid import runtime_cli

    seen: list[str] = []

    class _Runtime:
        def observe(self, command, *, support_root):
            seen.append(command)
            return runtime_cli.RuntimeResult(("banodoco-local", command), 0, {"ok": True, "state": "ready"})

    monkeypatch.setattr(runtime_cli, "RuntimeCLI", _Runtime)
    monkeypatch.setattr("astrid.sdk.storage_root.resolve_runtime_data_root", lambda: tmp_path / "support")

    assert dispatch._dispatch_doctor(["--json"]) == 0
    assert seen == ["doctor"]
    assert '"state": "ready"' in capsys.readouterr().out
