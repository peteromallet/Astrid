from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from astrid.core.execution.generic_host import GenericPackHost
from astrid.core.pack.discovery import discover_canonical_pack_metadata, discover_pack_metadata
from astrid.core.pack.source_setup import (
    DEFAULT_HIVEMIND_REPOSITORY,
    DEFAULT_HIVEMIND_REVISION,
    SourceDeclaration,
    SourceSetupError,
    active_source_inventory,
    declarations_from_json,
    default_source_declarations,
    provision,
)
from astrid.sdk.discovery import _discover_pack_inventory
from astrid.sdk.discovery import _pack_record


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def _fixture_repo(root: Path, *, schema_version: int = 2) -> str:
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "fixture@example.test")
    _git(root, "config", "user.name", "Astrid fixture")
    pack = root
    executor = pack / "executors" / "echo"
    executor.mkdir(parents=True)
    (pack / "pack.yaml").write_text(
        f"schema_version: {schema_version}\nid: demo\nname: Demo Pack\nversion: 1.0.0\n"
        "capabilities: [testing]\n",
        encoding="utf-8",
    )
    (executor / "executor.yaml").write_text(
        json.dumps(
            {
                "id": "demo.echo",
                "name": "Demo Echo",
                "kind": "external",
                "version": "1.0",
                "command": {"argv": ["echo", "ok"]},
                "cache": {"mode": "none"},
            }
        ),
        encoding="utf-8",
    )
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "fixture")
    return _git(root, "rev-parse", "HEAD")


def test_default_source_policy_pins_the_canonical_external_hivemind_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ASTRID_SOURCE_DECLARATIONS", raising=False)
    declarations = default_source_declarations()
    assert declarations == (
        SourceDeclaration(
            pack_id="hivemind",
            repository=DEFAULT_HIVEMIND_REPOSITORY,
            revision=DEFAULT_HIVEMIND_REVISION,
        ),
    )
    assert declarations_from_json() == declarations


def test_local_git_v2_source_is_staged_once_and_shared(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    revision = _fixture_repo(repository)
    state_path = tmp_path / "state" / "pack-sources.json"
    data_root = tmp_path / "data"
    declaration = SourceDeclaration.from_mapping(
        {"pack_id": "demo", "repository": str(repository), "revision": revision}
    )
    monkeypatch.setenv("ASTRID_SOURCE_STATE", str(state_path))

    result = provision((declaration,), state_path=state_path, data_root=data_root)
    assert result["ok"] is True
    inventory = active_source_inventory(state_path=state_path)
    assert inventory.sources[0].pack_root.is_dir()
    assert inventory.sources[0].revision == revision

    discovered = discover_pack_metadata(discover_packs_fn=lambda *args: ())
    managed = next(item for item in discovered if item.id == "demo")
    assert managed.source_kind == "managed"
    assert managed.source_inventory_identity == inventory.identity
    assert managed.source_revision == revision
    canonical = next(item for item in discover_canonical_pack_metadata() if item.id == "demo")
    assert canonical.source_kind == "managed"
    assert canonical.source_inventory_identity == inventory.identity
    sdk_record = _pack_record(next(item for item in _discover_pack_inventory() if item.id == "demo"))
    assert sdk_record["source_kind"] == "managed"
    assert sdk_record["source_inventory_identity"] == inventory.identity

    host = GenericPackHost(
        pack_roots=[*map(str, inventory.roots)],
        source_inventory_identity=inventory.identity,
    )
    record = next(item for item in host.discover() if item.id == "demo.echo")
    assert Path(record.definition.metadata["pack_root"]) == inventory.sources[0].pack_root
    assert host.source_inventory_identity == inventory.identity
    assert host.source_epoch != "uninitialized"

    before = state_path.read_bytes()
    checked = provision((declaration,), check=True, state_path=state_path, data_root=data_root)
    assert checked["changed"] is False
    assert state_path.read_bytes() == before

    offline = provision((declaration,), offline=True, state_path=state_path, data_root=data_root)
    assert offline["ok"] is True
    disabled = provision((), disable_pack="demo", state_path=state_path, data_root=data_root)
    assert disabled["active"] == []
    assert active_source_inventory(state_path=state_path).sources == ()
    restored = provision(
        (declaration,), offline=True, restore_pack="demo", state_path=state_path, data_root=data_root
    )
    assert restored["ok"] is True
    assert active_source_inventory(state_path=state_path).sources[0].revision == revision


def test_invalid_update_keeps_prior_active_state(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    revision = _fixture_repo(repository)
    state_path = tmp_path / "state" / "pack-sources.json"
    data_root = tmp_path / "data"
    first = SourceDeclaration.from_mapping(
        {"pack_id": "demo", "repository": str(repository), "revision": revision}
    )
    provision((first,), state_path=state_path, data_root=data_root)
    prior_state = state_path.read_bytes()

    (repository / "pack.yaml").write_text(
        "schema_version: 1\nid: demo\nname: Broken\nversion: 1.0.0\n", encoding="utf-8"
    )
    _git(repository, "add", "pack.yaml")
    _git(repository, "commit", "-q", "-m", "invalid-update")
    bad_revision = _git(repository, "rev-parse", "HEAD")
    bad = SourceDeclaration.from_mapping(
        {"pack_id": "demo", "repository": str(repository), "revision": bad_revision}
    )

    with pytest.raises(SourceSetupError, match="strict v2 admission"):
        provision((bad,), state_path=state_path, data_root=data_root)
    assert state_path.read_bytes() == prior_state
    assert active_source_inventory(state_path=state_path).sources[0].revision == revision


def test_active_checkout_tamper_fails_closed(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    revision = _fixture_repo(repository)
    state_path = tmp_path / "state" / "pack-sources.json"
    data_root = tmp_path / "data"
    declaration = SourceDeclaration.from_mapping(
        {"pack_id": "demo", "repository": str(repository), "revision": revision}
    )
    provision((declaration,), state_path=state_path, data_root=data_root)
    active_root = active_source_inventory(state_path=state_path).sources[0].pack_root
    (active_root / "pack.yaml").write_text(
        (active_root / "pack.yaml").read_text(encoding="utf-8") + "\n# tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceSetupError, match="dirty|digest mismatch"):
        active_source_inventory(state_path=state_path)


def test_failed_stage_removes_temporary_checkout_and_keeps_state_absent(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    _fixture_repo(repository)
    state_path = tmp_path / "state" / "pack-sources.json"
    data_root = tmp_path / "data"
    declaration = SourceDeclaration.from_mapping(
        {
            "pack_id": "demo",
            "repository": str(repository),
            "revision": "0" * 40,
        }
    )
    with pytest.raises(SourceSetupError):
        provision((declaration,), state_path=state_path, data_root=data_root)
    if (data_root / "demo").exists():
        assert not list((data_root / "demo").glob("stage-*"))
    assert not state_path.exists()


def test_offline_missing_cache_and_tamper_fail_closed(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    revision = _fixture_repo(repository)
    state_path = tmp_path / "state" / "pack-sources.json"
    data_root = tmp_path / "data"
    declaration = SourceDeclaration.from_mapping(
        {"pack_id": "demo", "repository": str(repository), "revision": revision}
    )

    missing = provision(
        (declaration,), offline=True, check=True, state_path=state_path, data_root=data_root
    )
    assert missing["ok"] is False
    assert "cached revision is missing" in missing["errors"][0]

    provision((declaration,), state_path=state_path, data_root=data_root)
    active = active_source_inventory(state_path=state_path)
    (active.sources[0].pack_root / "pack.yaml").write_text(
        (active.sources[0].pack_root / "pack.yaml").read_text(encoding="utf-8")
        + "\n# tampered\n",
        encoding="utf-8",
    )
    with pytest.raises(SourceSetupError, match="dirty"):
        active_source_inventory(state_path=state_path)
