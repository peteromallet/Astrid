from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from astrid.core.contracts.errors import AstridError
from astrid.core.util.secrets import (
    astrid_env_file_path,
    candidate_env_files,
    load_api_key,
    load_local_api_key_with_source,
    read_env_value,
    scrub_secret,
)

SENTINEL = "astrid-sentinel-secret-7f3c9d"


def test_read_env_value_uses_dotenv_syntax(tmp_path: Path) -> None:
    env_file = tmp_path / "this.env"
    env_file.write_text(
        "\n".join(
            [
                "# ignored",
                "EMPTY",
                "export API_KEY='quoted-value'",
                'OTHER="double-quoted"',
                "COMMENTED=plain-value # comment",
            ]
        ),
        encoding="utf-8",
    )

    assert read_env_value(env_file, "API_KEY") == "quoted-value"
    assert read_env_value(env_file, "OTHER") == "double-quoted"
    assert read_env_value(env_file, "COMMENTED") == "plain-value"
    assert read_env_value(env_file, "MISSING") == ""


def test_astrid_env_file_path_supports_override_and_home(tmp_path: Path) -> None:
    assert astrid_env_file_path({"ASTRID_ENV_FILE": str(tmp_path / "keys.env")}) == tmp_path / "keys.env"
    assert astrid_env_file_path({"ASTRID_HOME": str(tmp_path / "home")}) == tmp_path / "home" / "astrid.env"
    assert astrid_env_file_path(
        {"ASTRID_HOME": str(tmp_path / "home"), "ASTRID_ENV_FILE": "shared/keys.env"}
    ) == tmp_path / "home" / "shared" / "keys.env"


def test_candidate_env_files_return_only_explicit_file(tmp_path: Path) -> None:
    explicit = tmp_path / "custom.env"
    assert candidate_env_files(explicit) == [explicit.resolve()]
    assert candidate_env_files() == []


def test_shared_file_wins_over_stale_process_and_named_file(monkeypatch, tmp_path: Path) -> None:
    shared = tmp_path / "astrid.env"
    shared.write_text("ASTRID_T34_PROBE=from-shared-file\n", encoding="utf-8")
    fallback = tmp_path / "project.env"
    fallback.write_text("ASTRID_T34_PROBE=from-project-file\n", encoding="utf-8")
    monkeypatch.setenv("ASTRID_ENV_FILE", str(shared))
    monkeypatch.setenv("ASTRID_T34_PROBE", "stale-process-value")

    value, source = load_local_api_key_with_source(
        "ASTRID_T34_PROBE", env_file=fallback
    )

    assert (value, source) == ("from-shared-file", "astrid_env_file")


def test_explicit_value_wins_over_shared_file(monkeypatch, tmp_path: Path) -> None:
    shared = tmp_path / "astrid.env"
    shared.write_text("ASTRID_T34_PROBE=from-shared-file\n", encoding="utf-8")
    monkeypatch.setenv("ASTRID_ENV_FILE", str(shared))

    assert load_api_key("ASTRID_T34_PROBE", explicit="from-explicit") == "from-explicit"


def test_process_environment_fills_missing_shared_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASTRID_ENV_FILE", str(tmp_path / "absent.env"))
    monkeypatch.setenv("ASTRID_T34_PROBE", "from-environment")

    assert load_api_key("ASTRID_T34_PROBE") == "from-environment"


def test_named_env_file_is_final_explicit_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASTRID_ENV_FILE", str(tmp_path / "absent-shared.env"))
    monkeypatch.delenv("ASTRID_T34_PROBE", raising=False)
    fallback = tmp_path / "project.env"
    fallback.write_text("ASTRID_T34_PROBE=from-project-file\n", encoding="utf-8")

    assert load_api_key("ASTRID_T34_PROBE", env_file=fallback) == "from-project-file"


def test_unscavenged_cwd_env_file_is_never_consulted(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASTRID_ENV_FILE", str(tmp_path / "absent-shared.env"))
    monkeypatch.delenv("ASTRID_T34_PROBE", raising=False)
    (tmp_path / ".env").write_text("ASTRID_T34_PROBE=from-cwd-env\n", encoding="utf-8")

    with pytest.raises(AstridError):
        load_api_key("ASTRID_T34_PROBE")


def test_missing_key_error_is_actionable_and_never_leaks_other_values(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ASTRID_ENV_FILE", str(tmp_path / "absent-shared.env"))
    monkeypatch.delenv("ASTRID_T34_MISSING", raising=False)
    fallback = tmp_path / "keys.env"
    fallback.write_text(f"ASTRID_T34_PROBE={SENTINEL}\n", encoding="utf-8")

    with pytest.raises(AstridError) as exc_info:
        load_api_key("ASTRID_T34_MISSING", env_file=fallback)
    message = str(exc_info.value.cause)
    assert "explicit option" in message
    assert "shared astrid.env" in message
    assert "environment" in message
    assert "env file" in message
    assert SENTINEL not in message
    assert "set ASTRID_T34_MISSING" in exc_info.value.recovery_command


def test_missing_giphy_key_recovery_links_dashboard(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASTRID_ENV_FILE", str(tmp_path / "absent-shared.env"))
    monkeypatch.delenv("GIPHY_API_KEY", raising=False)

    with pytest.raises(AstridError) as exc_info:
        load_api_key("GIPHY_API_KEY")

    assert "https://developers.giphy.com/dashboard/" in exc_info.value.recovery_command


def test_scrub_secret_redacts_sentinel_from_diagnostics() -> None:
    diagnostic = json.dumps(
        {"receipt": {"result": {"key": SENTINEL}}, "log": f"provider used {SENTINEL}"}
    )
    scrubbed = scrub_secret(SENTINEL, diagnostic)
    assert SENTINEL not in scrubbed
    assert "***" in scrubbed
    assert SENTINEL not in json.dumps(json.loads(scrubbed))


def test_resolution_never_prints_the_secret(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setenv("ASTRID_ENV_FILE", str(tmp_path / "absent-shared.env"))
    monkeypatch.delenv("ASTRID_T34_PROBE", raising=False)
    fallback = tmp_path / "keys.env"
    fallback.write_text(f"ASTRID_T34_PROBE={SENTINEL}\n", encoding="utf-8")

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert load_api_key("ASTRID_T34_PROBE", env_file=fallback) == SENTINEL

    assert SENTINEL not in buffer.getvalue()
    assert SENTINEL not in capsys.readouterr().out
