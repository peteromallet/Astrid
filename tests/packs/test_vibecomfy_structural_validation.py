"""Exercise the real validator without allowing Comfy lifecycle or network I/O."""

from __future__ import annotations

import importlib
import json
import socket
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def offline_validator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("vibecomfy")
    from vibecomfy.runtime import server
    from vibecomfy.schema import provider

    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    monkeypatch.chdir(tmp_path)  # No local node_index.json may override auto selection.
    monkeypatch.setattr(provider, "has_comfyui_runtime", lambda: True)
    monkeypatch.setattr(provider.RuntimeSchemaProvider, "_load_valid_cached_object_info", lambda _: None)
    assert isinstance(provider.get_schema_provider("auto"), provider.RuntimeSchemaProvider)

    # Simulate the occupied endpoint at the launch boundary. Nothing is started
    # or contacted, even if a regression takes the old automatic-schema path.
    launch = AsyncMock(side_effect=RuntimeError("Managed Comfy endpoint 127.0.0.1:8188 is already in use"))
    shutdown = AsyncMock(side_effect=AssertionError("validation attempted server shutdown"))
    network = AsyncMock(side_effect=AssertionError("validation requested target schemas"))
    connect = Mock(side_effect=AssertionError("validation attempted a network connection"))
    monkeypatch.setattr(server, "_spawn_comfy_server", launch)
    monkeypatch.setattr(server, "_stop_managed_process", shutdown)
    monkeypatch.setattr(provider.ComfyClient, "object_info", network)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect)
    monkeypatch.setattr(socket, "create_connection", connect)
    validator = importlib.import_module("astrid.packs.vibecomfy.executors.validate.run")
    return validator, (launch, shutdown, network, connect)


def _bundle_args(tmp_path: Path, *, empty: bool = False) -> list[str]:
    from vibecomfy.workflow import VibeWorkflow, WorkflowSource
    from vibecomfy.workflow_bundle import emit_bundle

    workflow = VibeWorkflow("structural-regression", WorkflowSource("structural-regression"))
    if not empty:
        workflow.add_node("Integer", uid="integer-node", value=7)
    emit_bundle(workflow, tmp_path / "workflow.py", {"operation": "authored"})
    (tmp_path / "source.json").write_text('{"nodes":[],"links":[]}\n')
    return [
        "validate", "", "--python", str(tmp_path / "workflow.py"),
        "--companion", str(tmp_path / "workflow.vibe.json"),
        "--source", str(tmp_path / "source.json"),
        "--python-execution-consent", "confirmed", "--out", str(tmp_path / "out"),
    ]


def test_real_canonical_validation_is_structural_with_comfy_installed_and_port_occupied(
    tmp_path: Path, offline_validator,
) -> None:
    validator, forbidden = offline_validator
    args = _bundle_args(tmp_path)
    assert validator.main(args) == 0
    report = json.loads((tmp_path / "out" / "validation-report.json").read_text())
    assert report["ok"] is True
    assert report["authority"] == "canonical_workflow_bundle"
    assert report["validation_mode"] == "canonical_bundle_structural"
    assert report["runtime_validation"] == {
        "status": "deferred", "executor": "vibecomfy.run",
        "checks": ["session_identity", "target_schema"],
    }
    assert report["python_execution_consent"] == "confirmed"
    assert any(entry["decision"] == "allow" for entry in report["security_gate_audit"])
    for operation in forbidden:
        operation.assert_not_called()


def test_occupied_endpoint_fixture_exposes_old_default_schema_path(
    tmp_path: Path, offline_validator, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    """Negative control: removing the fix reaches the trapped server launch."""
    from vibecomfy import cli

    validator, (launch, shutdown, network, connect) = offline_validator
    args = _bundle_args(tmp_path)
    real_main = cli.main
    monkeypatch.setattr(cli, "main", lambda argv: real_main([arg for arg in argv if arg != "--no-schema"]))
    assert validator.main(args) == 1
    assert "already in use" in capsys.readouterr().err
    launch.assert_called_once()
    for operation in (shutdown, network, connect):
        operation.assert_not_called()


@pytest.mark.parametrize("defect", ["empty_graph", "bad_companion", "missing_member"])
def test_real_structural_validation_rejects_malformed_inputs(
    tmp_path: Path, offline_validator, defect: str, capsys,
) -> None:
    validator, forbidden = offline_validator
    args = _bundle_args(tmp_path, empty=defect == "empty_graph")
    if defect == "bad_companion":
        (tmp_path / "workflow.vibe.json").write_text("{invalid-json")
    elif defect == "missing_member":
        args[args.index("--source") + 1] = ""
    assert validator.main(args) == 1
    error = capsys.readouterr().err
    assert "vibecomfy.validate:" in error
    if defect == "empty_graph":
        assert "empty_workflow" in error
    assert not (tmp_path / "out" / "validation-report.json").exists()
    for operation in forbidden:
        operation.assert_not_called()


@pytest.mark.parametrize("consent", [None, "true"])
def test_real_canonical_validation_requires_exact_consent_before_python_load(
    tmp_path: Path, offline_validator, consent: str | None,
    monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    from vibecomfy import cli

    validator, forbidden = offline_validator
    args = _bundle_args(tmp_path)
    index = args.index("--python-execution-consent")
    if consent is None:
        del args[index:index + 2]
    else:
        args[index + 1] = consent
    load = Mock(side_effect=AssertionError("CLI reached without Python consent"))
    monkeypatch.setattr(cli, "main", load)
    assert validator.main(args) == 1
    assert "python_execution_consent" in capsys.readouterr().err
    load.assert_not_called()
    for operation in forbidden:
        operation.assert_not_called()
