"""Focused compatibility tests for the Runtime fixture realm creator."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from tests.helpers.runtime import initialize_runtime_realm


def _install_store(monkeypatch: pytest.MonkeyPatch, store: type) -> None:
    package = types.ModuleType("runtime_protocol")
    package.__path__ = []
    module = types.ModuleType("runtime_protocol.store")
    module.RealmStore = store
    monkeypatch.setitem(sys.modules, "runtime_protocol", package)
    monkeypatch.setitem(sys.modules, "runtime_protocol.store", module)


def test_fixture_creator_prefers_public_initialize(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, Path]] = []

    class RealmStore:
        @classmethod
        def initialize(cls, root: Path):
            calls.append(("initialize", root))
            return cls()

        def close(self) -> None:
            calls.append(("close", tmp_path / "unused"))

    _install_store(monkeypatch, RealmStore)
    root = tmp_path / "realm"

    assert initialize_runtime_realm(root) == root
    assert calls == [("initialize", root), ("close", tmp_path / "unused")]


def test_fixture_creator_supports_legacy_instance_ensure_realm(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[tuple[str, Path]] = []

    class RealmStore:
        def __init__(self, root: Path):
            calls.append(("construct", root))

        def ensure_realm(self) -> None:
            calls.append(("ensure_realm", tmp_path / "unused"))

        def close(self) -> None:
            calls.append(("close", tmp_path / "unused"))

    _install_store(monkeypatch, RealmStore)
    root = tmp_path / "realm"

    assert initialize_runtime_realm(root) == root
    assert calls == [
        ("construct", root),
        ("ensure_realm", tmp_path / "unused"),
        ("close", tmp_path / "unused"),
    ]


def test_fixture_creator_fails_clearly_without_supported_creator(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class RealmStore:
        pass

    _install_store(monkeypatch, RealmStore)

    with pytest.raises(RuntimeError, match="neither.*initialize.*ensure_realm"):
        initialize_runtime_realm(tmp_path / "realm")
