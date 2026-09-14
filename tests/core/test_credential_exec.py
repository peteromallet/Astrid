from __future__ import annotations

import os
from types import SimpleNamespace

from astrid.core.contracts.errors import AstridError
from astrid.core.util import credential_exec
from astrid.core.util.credentials_scope import CredentialsScope, ResolvedCredential


def test_launcher_passes_secret_only_in_child_environment(monkeypatch, capsys) -> None:
    secret = "never-print-this-runpod-key"
    resolved = ResolvedCredential(
        provider="runpod",
        reference="RUNPOD_API_KEY",
        source="astrid_env_file",
        value=secret,
    )
    monkeypatch.delenv("RUNPOD_API_KEY", raising=False)
    monkeypatch.setattr(
        CredentialsScope,
        "resolve_local",
        classmethod(lambda cls, provider, **kwargs: resolved),
    )
    calls: list[tuple[list[str], dict[str, str]]] = []
    def fake_run(command, *, env, check):
        calls.append((list(command), dict(env)))
        return SimpleNamespace(returncode=7)

    monkeypatch.setattr(credential_exec.subprocess, "run", fake_run)

    result = credential_exec.main(
        ["--provider", "runpod", "--", "runpod-lifecycle", "list", "--json"]
    )

    output = capsys.readouterr()
    assert result == 7
    assert calls[0][0] == ["runpod-lifecycle", "list", "--json"]
    assert calls[0][1]["RUNPOD_API_KEY"] == secret
    assert secret not in " ".join(calls[0][0])
    assert "RUNPOD_API_KEY" not in os.environ
    assert "using astrid_env_file" in output.err
    assert secret not in output.err


def test_launcher_reports_missing_reference_without_starting_child(monkeypatch, capsys) -> None:
    def missing(cls, provider, **kwargs):
        raise AstridError(
            "RUNPOD_API_KEY not found",
            recovery_command="store the key with astrid-credential set runpod",
        )

    monkeypatch.setattr(CredentialsScope, "resolve_local", classmethod(missing))
    monkeypatch.setattr(
        credential_exec.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("child must not start")),
    )

    result = credential_exec.main(["--provider", "runpod", "--", "runpod-lifecycle", "list"])

    output = capsys.readouterr()
    assert result == 1
    assert "RUNPOD_API_KEY not found" in output.err
    assert "store the key with astrid-credential set runpod" in output.err
