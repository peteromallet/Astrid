"""Tests for trusted dynamic provider route admission."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.core.execution.provider_route_resolvers import (
    ProviderRouteResolutionError,
    resolve_runpod_pod_handle_ssh_route,
)


def _handle(path: Path, *, ssh: str = "root@198.51.100.7 -p 53603") -> None:
    path.write_text(
        json.dumps(
            {
                "pod_id": "pod-123",
                "ssh": ssh,
                "config_snapshot": {"api_key_ref": "RUNPOD_API_KEY"},
            }
        ),
        encoding="utf-8",
    )


def test_runpod_route_requires_live_endpoint_match(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = tmp_path / "pod_handle.json"
    _handle(handle)
    monkeypatch.setattr(
        "astrid.core.util.credentials_scope.CredentialsScope.resolve_local",
        staticmethod(lambda *_args, **_kwargs: SimpleNamespace(value="api-key")),
    )
    monkeypatch.setattr(
        "runpod_lifecycle.api.get_pod_status",
        lambda _pod_id, _api_key: {
            "desired_status": "RUNNING",
            "ports": [{"privatePort": 22, "publicPort": 53603, "ip": "198.51.100.7"}],
        },
    )

    assert resolve_runpod_pod_handle_ssh_route(handle) == "tcp://198.51.100.7:53603"


def test_runpod_route_rejects_changed_live_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = tmp_path / "pod_handle.json"
    _handle(handle)
    monkeypatch.setattr(
        "astrid.core.util.credentials_scope.CredentialsScope.resolve_local",
        staticmethod(lambda *_args, **_kwargs: SimpleNamespace(value="api-key")),
    )
    monkeypatch.setattr(
        "runpod_lifecycle.api.get_pod_status",
        lambda _pod_id, _api_key: {
            "desired_status": "RUNNING",
            "ports": [{"privatePort": 22, "publicPort": 53604, "ip": "198.51.100.7"}],
        },
    )

    with pytest.raises(ProviderRouteResolutionError, match="endpoint changed"):
        resolve_runpod_pod_handle_ssh_route(handle)
