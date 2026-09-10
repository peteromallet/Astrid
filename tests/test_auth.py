from __future__ import annotations

from pathlib import Path

from astrid.core import auth


def test_auth_system_notice_is_non_blocking_when_logged_out(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("HIVEMIND_CONTRIBUTOR_KEY", raising=False)

    notice = auth.contributor_auth_system_notice()

    assert "not logged in" in notice
    assert "ordinary Astrid work remain available" in notice
    assert "astrid login" in notice
    assert "do not block unrelated work" in notice


def test_auth_system_notice_does_not_expose_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("HIVEMIND_CONTRIBUTOR_KEY", raising=False)
    key = "hm_" + "a" * 64
    key_path = tmp_path / ".hivemind" / "key"
    key_path.parent.mkdir()
    key_path.write_text(key, encoding="utf-8")

    notice = auth.contributor_auth_system_notice()

    assert "logged in" in notice
    assert key not in notice


def test_run_auth_forwards_to_managed_hivemind_cli(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(auth, "_resolve_auth_cli", lambda provision_if_missing: ["python", "cli.py"])
    monkeypatch.setattr(
        auth.subprocess,
        "run",
        lambda argv, check: calls.append(list(argv)) or type("Result", (), {"returncode": 0})(),
    )

    assert auth.run_auth(["login", "--machine", "studio", "--timeout", "42"]) == 0
    assert calls == [[
        "python", "cli.py", "auth", "login", "--machine", "studio", "--ttl", "600",
        "--timeout", "42.0", "--interval", "2.0",
    ]]
