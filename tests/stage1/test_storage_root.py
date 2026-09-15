from pathlib import Path

import pytest

from astrid.sdk.storage_root import ensure_no_unmigrated_runtime, resolve_runtime_data_root


def test_checkout_default_is_stable_and_cwd_independent(monkeypatch, tmp_path):
    monkeypatch.delenv("BANODOCO_LOCAL_DATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)

    assert resolve_runtime_data_root() == Path(__file__).resolve().parents[2] / ".astrid-data"


def test_explicit_data_root_wins(monkeypatch, tmp_path):
    target = tmp_path / "runtime-state"
    monkeypatch.setenv("BANODOCO_LOCAL_DATA_ROOT", str(target))
    assert resolve_runtime_data_root() == target


def test_explicit_data_root_must_be_absolute(monkeypatch):
    monkeypatch.setenv("BANODOCO_LOCAL_DATA_ROOT", ".astrid-data")
    with pytest.raises(ValueError, match="absolute"):
        resolve_runtime_data_root()


def test_missing_checkout_config_uses_persistent_user_root(monkeypatch, tmp_path):
    monkeypatch.delenv("BANODOCO_LOCAL_DATA_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "astrid.sdk.storage_root.CONFIG_PATH", tmp_path / "missing-config.json"
    )

    assert resolve_runtime_data_root() == tmp_path / ".astrid-data"


def test_default_does_not_create_blank_realm_over_existing_external_catalog(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("BANODOCO_LOCAL_DATA_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    old_catalog = tmp_path / "Library" / "Application Support" / "Banodoco" / "runtime" / "catalog.json"
    old_catalog.parent.mkdir(parents=True)
    old_catalog.write_text('{"selected_realm_id":"existing"}', encoding="utf-8")

    with pytest.raises(ValueError, match="existing neutral runtime"):
        ensure_no_unmigrated_runtime(tmp_path / "Astrid" / ".astrid-data")
