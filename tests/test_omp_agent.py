"""Focused contract tests for Astrid's installed OMP launcher."""

from __future__ import annotations

import os
from pathlib import Path

from astrid import omp_agent


def test_main_execs_default_astrid_agent_with_auth_status_notice(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.delenv("ASTRID_SYSTEM_PROMPT", raising=False)
    monkeypatch.delenv("ASTRID_SYSTEM_PROMPT_FILE", raising=False)

    monkeypatch.setattr(omp_agent, "_find_launcher", lambda: Path("/fake/agent"))
    monkeypatch.setattr(omp_agent, "_select_omp_bin", lambda: None)
    monkeypatch.setattr(omp_agent.os, "execvp", lambda file, argv: captured.update(file=file, argv=argv))

    assert omp_agent.main(["make a shot list"]) == 1
    assert captured["file"] == "/fake/agent"
    argv = captured["argv"]
    assert argv[:3] == ["/fake/agent", "run", "astrid"]
    assert "--append-system-prompt" in argv
    assert "Hivemind contributor login status:" in argv[argv.index("--append-system-prompt") + 1]
    assert argv[-2:] == ["--print", "make a shot list"]


def test_explicit_astrid_prompt_override_is_appended(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setenv("ASTRID_SYSTEM_PROMPT", "extra Astrid guidance")
    monkeypatch.setattr(omp_agent, "_find_launcher", lambda: Path("/fake/agent"))
    monkeypatch.setattr(omp_agent, "_select_omp_bin", lambda: None)
    monkeypatch.setattr(omp_agent.os, "execvp", lambda file, argv: captured.update(file=file, argv=argv))

    omp_agent.main(["make a shot list"])

    argv = captured["argv"]
    prompt = argv[argv.index("--append-system-prompt") + 1]
    assert "extra Astrid guidance" in prompt
    assert "Hivemind contributor login status:" in prompt


def test_bundled_prompt_has_safe_startup_update_contract() -> None:
    prompt = omp_agent.ASTRID_SYSTEM_PROMPT
    assert "first action in each new session" in prompt
    assert "python3 -m astrid.skills sync" in prompt
    assert "bun run build" in prompt
    assert "never stash, reset, merge, rebase, or overwrite user work" in prompt
    assert "next `astrid` launch" in prompt


def test_installed_named_profile_has_safe_startup_update_contract() -> None:
    profile = Path.home() / ".omp" / "agent" / "agents" / "astrid.md"
    text = profile.read_text(encoding="utf-8")
    assert "first action in each new session" in text
    assert "git fetch" in text
    assert "fast-forward-only pull" in text
    assert "python3 -m astrid.skills sync" in text
    assert "bun run build" in text
    assert "/reload-plugins" in text
    assert "next `astrid` launch" in text


def test_gateway_console_script_is_astrid_tools_and_module_entry_is_unchanged() -> None:
    metadata = Path(__file__).parents[1] / "pyproject.toml"
    text = metadata.read_text(encoding="utf-8")
    assert 'astrid-tools = "astrid.core.gateway:main"' in text
    assert 'astrid = "astrid.omp_agent:main"' in text
    module_main = (metadata.parent / "astrid" / "__main__.py").read_text(encoding="utf-8")
    assert "from .core.gateway import main" in module_main


def test_omp_bin_override_and_astrid_identity(monkeypatch) -> None:
    monkeypatch.setenv("OMP_BIN", "/custom/omp")
    monkeypatch.delenv("ASTRID_STOCK_OMP", raising=False)
    assert omp_agent._resolve_omp_bin({"OMP_BIN": "/custom/omp"}) == "/custom/omp"

    captured: dict[str, object] = {}
    monkeypatch.setattr(omp_agent, "_find_launcher", lambda: Path("/fake/agent"))
    monkeypatch.setattr(omp_agent, "_select_omp_bin", lambda: None)
    monkeypatch.setattr(omp_agent.os, "execvp", lambda file, argv: captured.update(file=file, argv=argv))
    omp_agent.main([])
    assert os.environ["OMP_AGENT_IDENTITY"] == "astrid"
    assert os.environ["ASTRID_AGENT_IDENTITY"] == "astrid"
    assert captured["argv"][:3] == ["/fake/agent", "run", "astrid"]


def test_astrid_command_overrides_inherited_identity(monkeypatch) -> None:
    """A prior Arnold launch must not tint the next Astrid process."""
    monkeypatch.setenv("OMP_AGENT_IDENTITY", "arnold")
    monkeypatch.setenv("ASTRID_AGENT_IDENTITY", "arnold")
    captured: dict[str, object] = {}
    monkeypatch.setattr(omp_agent, "_find_launcher", lambda: Path("/fake/agent"))
    monkeypatch.setattr(omp_agent, "_select_omp_bin", lambda: None)
    monkeypatch.setattr(omp_agent.os, "execvp", lambda file, argv: captured.update(file=file, argv=argv))

    omp_agent.main([])

    assert os.environ["OMP_AGENT_IDENTITY"] == "astrid"
    assert os.environ["ASTRID_AGENT_IDENTITY"] == "astrid"
    assert captured["argv"][:3] == ["/fake/agent", "run", "astrid"]


def test_bare_agent_subcommand_is_an_explicit_interactive_agent_route(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(omp_agent, "_find_launcher", lambda: Path("/fake/agent"))
    monkeypatch.setattr(omp_agent, "_select_omp_bin", lambda: None)
    monkeypatch.setattr(omp_agent.os, "execvp", lambda file, argv: captured.update(file=file, argv=argv))

    assert omp_agent.main(["agent"]) == 1
    assert captured["argv"][:3] == ["/fake/agent", "run", "astrid"]
    assert "--print" not in captured["argv"]


def test_toolkit_families_and_help_delegate_to_gateway(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(omp_agent, "_dispatch_toolkit", lambda argv: calls.append(argv) or 7)

    assert omp_agent.main(["projects", "list", "--json"]) == 7
    assert omp_agent.main(["help"]) == 7
    assert calls == [["projects", "list", "--json"], ["help"]]


def test_top_level_help_describes_unified_agent_and_toolkit_surface(capsys) -> None:
    assert omp_agent.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert "interactive Astrid agent" in output
    assert "astrid agent" in output
    for family in ("projects", "timelines", "media", "tasks", "runs", "doctor", "backup"):
        assert family in output
    for command in ("astrid login", "astrid status", "astrid logout", "astrid revoke"):
        assert command in output
