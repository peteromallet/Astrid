"""Astrid product-version contracts."""

from __future__ import annotations

from pathlib import Path
import tomllib

from astrid import __version__
from astrid.core.gateway import main as gateway_main
from astrid import omp_agent


def test_version_is_read_from_project_metadata() -> None:
    metadata = Path(__file__).parents[1] / "pyproject.toml"
    with metadata.open("rb") as stream:
        project = tomllib.load(stream)["project"]
    assert __version__ == project["version"]


def test_astrid_version_flag_does_not_launch_omp(capsys, monkeypatch) -> None:
    monkeypatch.setattr(omp_agent.os, "execvp", lambda *_args: (_ for _ in ()).throw(AssertionError("OMP launched")))

    assert omp_agent.main(["--version"]) == 0
    assert capsys.readouterr().out == f"astrid/{__version__}\n"


def test_explicit_agent_version_flag_uses_astrid_version(capsys, monkeypatch) -> None:
    monkeypatch.setattr(omp_agent.os, "execvp", lambda *_args: (_ for _ in ()).throw(AssertionError("OMP launched")))

    assert omp_agent.main(["agent", "--version"]) == 0
    assert capsys.readouterr().out == f"astrid/{__version__}\n"


def test_gateway_version_flag_uses_the_same_astrid_version(capsys) -> None:
    assert gateway_main(["--version"]) == 0
    assert capsys.readouterr().out == f"astrid/{__version__}\n"
