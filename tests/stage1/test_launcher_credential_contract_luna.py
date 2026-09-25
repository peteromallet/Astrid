"""Real first-launch coverage for the launcher credential-file handoff."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

pytest.importorskip("runtime_protocol.daemon")
from runtime_protocol.daemon import RuntimeDaemon  # noqa: E402
from tests.helpers.runtime import assert_t9_runtime_selection, initialize_runtime_realm


assert_t9_runtime_selection()


_RuntimeDaemon = RuntimeDaemon


def RuntimeDaemon(root, *args, **kwargs):
    initialize_runtime_realm(root)
    return _RuntimeDaemon(root, *args, **kwargs)

from astrid.core.gateway import main as gateway_main  # noqa: E402
from astrid.sdk.client import AstridClient  # noqa: E402


def _launcher_result(daemon: RuntimeDaemon) -> dict[str, str]:
    credential_file = daemon.credential_path
    assert credential_file is not None and credential_file.is_file()
    return {
        "status": "started",
        "endpoint": daemon.endpoint,
        "realm_id": daemon.service.realm["id"],
        "actor_id": "owner",
        "credential_file": str(credential_file),
    }


def test_first_launch_cli_reads_launcher_credential_file_without_secret_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    daemon = RuntimeDaemon(tmp_path / "realm", support_root=tmp_path / "support").start()
    try:
        credential_file = daemon.credential_path
        assert credential_file is not None
        monkeypatch.delenv("BANODOCO_RUNTIME_CREDENTIAL", raising=False)
        calls: list[tuple[bool, object]] = []

        def fake_ensure_runtime(*, start_pack_host: bool = True, data_root=None):
            calls.append((start_pack_host, data_root))
            return _launcher_result(daemon)

        monkeypatch.setattr(
            "astrid.sdk.autobootstrap.ensure_runtime", fake_ensure_runtime
        )
        assert gateway_main(
            [
                "projects",
                "create",
                "first-launch",
                "--name",
                "First Launch",
                "--idempotency-key",
                "first-launch-project",
                "--json",
            ]
        ) == 0
        output = capsys.readouterr().out
        result = json.loads(output)
        assert result["ok"] is True
        assert result["data"]["slug"] == "first-launch"
        assert result["receipt"] is not None
        assert str(credential_file) not in output
        assert calls == [(False, None)]
    finally:
        daemon.stop()


def test_launcher_path_is_forwarded_as_path_not_bearer_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    daemon = RuntimeDaemon(tmp_path / "realm", support_root=tmp_path / "support").start()
    try:
        monkeypatch.delenv("BANODOCO_RUNTIME_CREDENTIAL", raising=False)
        calls: list[tuple[bool, object]] = []

        def fake_ensure_runtime(*, start_pack_host: bool = True, data_root=None):
            calls.append((start_pack_host, data_root))
            return _launcher_result(daemon)

        monkeypatch.setattr(
            "astrid.sdk.autobootstrap.ensure_runtime", fake_ensure_runtime
        )
        observed: dict[str, object] = {}
        original_open = AstridClient.open

        def capture(cls, **kwargs):
            observed["credential"] = kwargs["credential"]
            return original_open(**kwargs)

        monkeypatch.setattr(AstridClient, "open", classmethod(capture))
        with AstridClient.open_from_launcher(
            client_name="launcher-contract-test",
            client_version="stage1",
            protocol_version="workspace.v1",
        ) as client:
            assert client.projects.list().ok
        assert observed["credential"] == daemon.credential_path
        assert isinstance(observed["credential"], Path)
        assert calls == [(True, None)]
    finally:
        daemon.stop()
