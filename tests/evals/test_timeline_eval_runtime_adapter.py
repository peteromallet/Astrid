from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from evals.timeline.fixture import CaseIdentities
from evals.timeline.runtime_adapter import (
    ISOLATION_CONTRACT_KIND,
    ISOLATION_MARKER_NAME,
    RuntimeAdapterError,
    RuntimeFixtureAdapter,
    WorkspaceClosureReader,
    isolation_contract_template,
    verify_isolation_contract,
)


def _write_contract(
    tmp_path: Path,
    *,
    endpoint: str = "http://127.0.0.1:63212",
    realm_id: str = "timeline-eval-realm",
    credential_file: Path | None = None,
    realm_root: Path | None = None,
    canonical_endpoint: str = "http://127.0.0.1:63541",
    canonical_realm_id: str = "astrid-live-realm",
    canonical_root: Path | None = None,
) -> tuple[Path, Path, Path, Path]:
    runtime_root = realm_root or tmp_path / "disposable-realm"
    runtime_root.mkdir(parents=True, exist_ok=True)
    canonical = canonical_root or tmp_path / "canonical-realm"
    canonical.mkdir(parents=True, exist_ok=True)
    credential = credential_file or tmp_path / "credential.json"
    if not credential.exists():
        credential.write_text(json.dumps({"token": "test-token"}), encoding="utf-8")
    marker = {
        "kind": ISOLATION_CONTRACT_KIND,
        "purpose": "timeline-eval-disposable-realm",
        "realm_id": realm_id,
    }
    (runtime_root / ISOLATION_MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
    contract = isolation_contract_template(
        endpoint=endpoint,
        realm_id=realm_id,
        credential_file=credential,
        realm_root=runtime_root,
        canonical_endpoint=canonical_endpoint,
        canonical_realm_id=canonical_realm_id,
        canonical_root=canonical,
    )
    contract_file = tmp_path / "isolation-contract.json"
    contract_file.write_text(json.dumps(contract), encoding="utf-8")
    return contract_file, credential, runtime_root, canonical


class FakeWorkspace:
    def __init__(self, endpoint, credential):
        self.endpoint = endpoint
        self.credential = credential
        self._generated = type("Generated", (), {"publish_parent_composition": lambda *_a, **_k: None})()
        self.calls: list[tuple[str, object]] = []
        self.realm_id = "timeline-eval-realm"

    def health(self):
        self.calls.append(("health", None))
        return {"status": "ok", "runtime_epoch": 1}

    def handshake(self, client_name, client_version, requested_scopes):
        self.calls.append(("handshake", tuple(requested_scopes)))
        return {
            "realm_id": self.realm_id,
            "actor_id": "eval-owner",
            "scopes": ["projects:read", "projects:write", "objects:read", "objects:write"],
        }


def test_isolation_contract_requires_explicit_matching_inputs_and_separate_roots(tmp_path):
    contract, credential, runtime_root, canonical_root = _write_contract(tmp_path)
    verified = verify_isolation_contract(
        endpoint="http://127.0.0.1:63212",
        credential_file=credential,
        contract_path=contract,
    )
    assert verified.realm_root == runtime_root.resolve()
    assert verified.canonical_root == canonical_root.resolve()
    assert verified.fixture_endpoint().realm_id == "timeline-eval-realm"

    with pytest.raises(RuntimeAdapterError, match="refusing canonical/default fallback"):
        verify_isolation_contract(endpoint=None, credential_file=credential, contract_path=contract)
    with pytest.raises(RuntimeAdapterError, match="does not match"):
        verify_isolation_contract(
            endpoint="http://127.0.0.1:63213",
            credential_file=credential,
            contract_path=contract,
        )


def test_isolation_contract_rejects_nested_canonical_root(tmp_path):
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    nested = canonical / "eval"
    nested.mkdir()
    contract, credential, _runtime_root, _canonical_root = _write_contract(
        tmp_path,
        realm_root=nested,
        canonical_root=canonical,
    )
    with pytest.raises(RuntimeAdapterError, match="inside the canonical realm root"):
        verify_isolation_contract(
            endpoint="http://127.0.0.1:63212",
            credential_file=credential,
            contract_path=contract,
        )


def test_adapter_requires_server_observed_realm_and_write_scopes(tmp_path):
    contract, credential, _runtime_root, _canonical_root = _write_contract(tmp_path)
    client = FakeWorkspace("http://127.0.0.1:63212", credential)
    adapter = RuntimeFixtureAdapter.connect(
        endpoint="http://127.0.0.1:63212",
        credential_file=credential,
        contract_path=contract,
        client_factory=lambda *_args: client,
    )
    assert adapter.proof.realm_id == "timeline-eval-realm"
    assert [name for name, _ in client.calls] == ["health", "handshake"]

    client.realm_id = "astrid-live-realm"
    with pytest.raises(RuntimeAdapterError, match="differs from the isolated contract"):
        RuntimeFixtureAdapter.connect(
            endpoint="http://127.0.0.1:63212",
            credential_file=credential,
            contract_path=contract,
            client_factory=lambda *_args: client,
        )


def test_seed_rejects_mismatched_runtime_assigned_identity_before_mutation(tmp_path):
    contract, credential, _runtime_root, _canonical_root = _write_contract(tmp_path)
    client = FakeWorkspace("http://127.0.0.1:63212", credential)
    adapter = RuntimeFixtureAdapter.connect(
        endpoint="http://127.0.0.1:63212",
        credential_file=credential,
        contract_path=contract,
        client_factory=lambda *_args: client,
    )
    identities = CaseIdentities(
        case_id="A01",
        project_alias="timeline-eval-suite",
        timeline_alias="eval-A01",
        project_id="runtime-assigned-project-id",
        timeline_id="runtime-assigned-timeline-id",
        parent_revision_id="parent-revision",
        occurrence_ids={}, shot_ids={}, shot_revision_ids={}, item_ids={},
        internal_timeline_ids={}, internal_revision_ids={},
    )
    with pytest.raises(RuntimeAdapterError, match="does not match Runtime-assigned"):
        adapter.seed_case("different-project-id", identities, object(), {}, idempotency_key="seed")
    assert [name for name, _ in client.calls] == ["health", "handshake"]
    assert not any(name in {"create_project", "publish_parent_composition", "ingest_project_object"}
                   for name, _ in client.calls)


def test_fixture_item_remap_fallback_changes_only_schema_known_references(monkeypatch):
    """The minimal prep image can seed without importing optional core deps."""
    import builtins

    real_import = builtins.__import__

    def without_authoring_bundle(name, *args, **kwargs):
        if name == "astrid.core.timeline.authoring_bundle":
            raise ModuleNotFoundError("optional authoring dependencies are absent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_authoring_bundle)
    payload = {
        "items": [{
            "item_id": "old-item",
            "source_item_id": "old-item",
            "nested": {"selected_item_id": "old-item", "related_item_ids": ["old-item", 7]},
            "opaque": "old-item",
        }],
        "metadata": {"parent_item_id": "old-item", "description": "old-item"},
    }

    remapped = RuntimeFixtureAdapter._remap_item_payload(payload, {"old-item": "new-item"})

    assert remapped["items"][0]["item_id"] == "new-item"
    assert remapped["items"][0]["source_item_id"] == "new-item"
    assert remapped["items"][0]["nested"]["selected_item_id"] == "new-item"
    assert remapped["items"][0]["nested"]["related_item_ids"] == ["new-item", 7]
    assert remapped["metadata"]["parent_item_id"] == "new-item"
    assert remapped["items"][0]["opaque"] == "old-item"
    assert remapped["metadata"]["description"] == "old-item"
    assert payload["items"][0]["item_id"] == "old-item"


def test_real_disposable_runtime_handshake_and_project_id_allocation(tmp_path):
    """Exercise the generated Runtime transport against a fresh temporary realm."""
    from runtime_protocol.daemon import RuntimeDaemon
    from runtime_protocol.store import RealmStore

    from astrid.sdk.workspace_client import WorkspaceClient

    runtime_root = tmp_path / "isolated-runtime"
    canonical_root = tmp_path / "canonical-source"
    canonical_root.mkdir()
    RealmStore.initialize(runtime_root, display_name="Timeline eval isolated test").close()
    daemon = RuntimeDaemon(
        runtime_root,
        support_root=tmp_path / "runtime-support",
        display_name="Timeline eval isolated test",
    ).start()
    try:
        credential = Path(daemon.credential_path)
        marker = {
            "kind": ISOLATION_CONTRACT_KIND,
            "purpose": "timeline-eval-disposable-realm",
            "realm_id": daemon.service.realm["id"],
        }
        (runtime_root / ISOLATION_MARKER_NAME).write_text(json.dumps(marker), encoding="utf-8")
        contract = isolation_contract_template(
            endpoint=daemon.endpoint,
            realm_id=daemon.service.realm["id"],
            credential_file=credential,
            realm_root=runtime_root,
            canonical_endpoint="http://127.0.0.1:63541",
            canonical_realm_id="astrid-live-realm",
            canonical_root=canonical_root,
        )
        contract_file = tmp_path / "runtime-isolation.json"
        contract_file.write_text(json.dumps(contract), encoding="utf-8")
        adapter = RuntimeFixtureAdapter.connect(
            endpoint=daemon.endpoint,
            credential_file=credential,
            contract_path=contract_file,
            client_factory=WorkspaceClient,
        )
        assert adapter.proof.realm_id == daemon.service.realm["id"]

        # Exercise the actual adapter setup path against only this temporary
        # realm. The suite project ID must be returned by Runtime, and the
        # case timeline is then created inside that project.
        project = adapter.create_suite_project(
            "timeline-eval-project-test",
            idempotency_key="adapter-project-id-proof",
        )
        actual_id = project["project_id"]
        assert actual_id
        timeline = adapter.create_case_timeline(
            actual_id,
            "eval-adapter-proof",
            idempotency_key="adapter-timeline-id-proof",
        )
        assert timeline["timeline_id"] == "eval-adapter-proof"
        assert "project_id" not in inspect.signature(adapter.workspace.create_project).parameters
        assert callable(adapter.workspace._generated.publish_parent_composition)
    finally:
        daemon.stop()


def test_current_closure_follows_post_edit_parent_dependencies_without_seed_map(tmp_path):
    """Post-edit readback follows the committed parent, including new IDs."""
    class CurrentWorkspace:
        _generated = type("Generated", (), {})()

        def get_timeline(self, timeline_id, *, project_id):
            return {"data": {"head_revision_id": "head-new"}}

        def get_project_parent_composition_revision(self, project_id, timeline_id, revision):
            assert (project_id, timeline_id, revision) == ("project", "timeline", "head-new")
            return {"data": {"revision_id": revision, "payload": {"occurrences": [
                {"occurrence_id": "occ-new", "shot_id": "shot-new", "shot_revision_id": "shot-rev-new"},
                {"occurrence_id": "occ-duplicate", "shot_id": "shot-new", "shot_revision_id": "shot-rev-new"},
            ]}}}

        def get_project_shot_revision(self, project_id, shot_id, revision):
            assert (project_id, shot_id, revision) == ("project", "shot-new", "shot-rev-new")
            return {"data": {"shot_id": shot_id, "revision_id": revision,
                              "internal_timeline_revision_id": "internal-new",
                              "payload": {"items": [{"id": "item-new"}]}}}

        def get_project_timeline_revision(self, project_id, timeline_id, revision):
            assert (project_id, timeline_id, revision) == ("project", "timeline", "internal-new")
            return {"data": {"timeline_id": timeline_id, "revision_id": revision,
                              "payload": {"clips": [{"id": "clip-new"}]}}}

    adapter = RuntimeFixtureAdapter.__new__(RuntimeFixtureAdapter)
    adapter.workspace = CurrentWorkspace()
    closure = adapter.read_current_closure("project", "timeline")

    assert closure["head_revision_id"] == "head-new"
    assert [row["shot_id"] for row in closure["shot_revisions"]] == ["shot-new"]
    assert [row["revision_id"] for row in closure["internal_timeline_revisions"]] == ["internal-new"]
    assert adapter.read_current_semantic_digest("project", "timeline").startswith("sha256:")
    source_reader = WorkspaceClosureReader(adapter.workspace)
    assert source_reader.current_head("project", "timeline") == "head-new"
    assert source_reader.read_current_closure("project", "timeline", head="head-new")["head_revision_id"] == "head-new"


def test_project_timeline_inventory_pages_and_rejects_duplicate_ids():
    class Workspace:
        def list_timelines(self, project_id, *, cursor=None, limit=100):
            if cursor is None:
                return ([{"timeline_id": "target", "head_revision_id": "head-a"}], "next")
            return ([{"timeline_id": "sibling", "head_revision_id": None}], None)

    adapter = RuntimeFixtureAdapter.__new__(RuntimeFixtureAdapter)
    adapter.workspace = Workspace()
    assert adapter.list_project_timeline_heads("project") == {"target": "head-a", "sibling": None}

    class DuplicateWorkspace(Workspace):
        def list_timelines(self, project_id, *, cursor=None, limit=100):
            return ([{"timeline_id": "target", "head_revision_id": "head-a"}], "next")

    adapter.workspace = DuplicateWorkspace()
    with pytest.raises(RuntimeAdapterError, match="duplicate timeline ID"):
        adapter.list_project_timeline_heads("project")
