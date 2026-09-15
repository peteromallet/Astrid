"""Immutable release gates for Astrid's vendored workspace client.

The runtime repository owns generation. Astrid deliberately does not invoke
that repository's generator at test time: this gate proves that the checked-in
client is the exact reviewed upstream artifact, identified by immutable file
hashes and an upstream commit pin alongside the contract metadata.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
from pathlib import Path

from banodoco_workspace_client import ManagedOutput, ObjectLocation, WorkspaceClient, generated
from banodoco_workspace_client.contract_metadata import (
    COMPONENT_MANIFEST_SHA256,
    OPERATIONS,
    PROTOCOL,
    SCHEMA_DIGEST,
    SOURCE_COMMIT,
)

ROOT = Path(__file__).resolve().parents[2]
GENERATED_PATH = ROOT / "banodoco_workspace_client" / "generated.py"
METADATA_PATH = ROOT / "banodoco_workspace_client" / "contract_metadata.py"

# These values are intentionally duplicated in the immutable test gate. A
# future runtime contract refresh must update the contract exports, file
# hashes, and this test in one reviewed change; no ambient sibling checkout can
# silently alter the shipped transport.
PINNED_PROTOCOL = "workspace.v1"
PINNED_COMPONENT_MANIFEST_SHA256 = "sha256:dc91a45390f33582f0299f81285d165128e1885a9fd62b4ccffa7b8e465ed63a"
PINNED_SCHEMA_DIGEST = "sha256:e64d2bd291f7e746d66cc688e673ee98dd240117e42131dbcde613080993c2d4"
PINNED_GENERATED_SHA256 = "d574962df19db3591ea1070adbeaf0746b3bbcbae77031cdafe322233ba37f7d"
PINNED_METADATA_SHA256 = "bbf698e8c2d1e7c4af3bcbc615603f7419c41877b804a41b25ea2be9eb2865a2"


def _camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()


def test_vendored_client_is_the_frozen_runtime_artifact() -> None:
    assert SOURCE_COMMIT == "90f4a9f22764bc66fa8b30d7d9081c6ac6307328"
    assert PROTOCOL == PINNED_PROTOCOL == generated.PROTOCOL
    assert COMPONENT_MANIFEST_SHA256 == PINNED_COMPONENT_MANIFEST_SHA256
    assert SCHEMA_DIGEST == PINNED_SCHEMA_DIGEST == generated.SCHEMA_DIGEST
    assert hashlib.sha256(GENERATED_PATH.read_bytes()).hexdigest() == PINNED_GENERATED_SHA256
    assert hashlib.sha256(METADATA_PATH.read_bytes()).hexdigest() == PINNED_METADATA_SHA256


def test_vendored_client_operation_catalog_matches_typed_methods() -> None:
    assert tuple(OPERATIONS) == tuple(generated.OPERATIONS)
    methods = {
        name
        for name, value in inspect.getmembers(WorkspaceClient, inspect.isfunction)
        if not name.startswith("_")
    }
    operation_methods = {_camel_to_snake(operation) for operation in OPERATIONS}
    # This is a generated typed composition, not an independent OpenAPI
    # operation ID: it composes updateDocument while retaining a convenient
    # resource-scoped method for product adapters.
    composed_helpers = {"update_timeline_document"}
    assert methods == operation_methods | composed_helpers


def test_frozen_mutation_signatures_require_idempotency_keys() -> None:
    for name in (
        "update_timeline_document",
        "create_generation",
        "create_variant",
        "export_managed_output",
        "adopt_managed_output",
        "update_managed_output_lifecycle",
        "promote_project_shot_candidate",
    ):
        parameter = inspect.signature(getattr(WorkspaceClient, name)).parameters["idempotency_key"]
        assert parameter.default is inspect.Parameter.empty


def test_object_location_preserves_typed_wire_contract(monkeypatch) -> None:
    payload = {
        "object_id": "object", "digest": "sha256:abc", "size": 12,
        "media_type": "video/mp4", "local_path": "/runtime/object.mp4",
        "storage": "local", "verified": True, "filename": "object.mp4",
    }
    calls = []

    def request(self, method, path):
        calls.append((method, path))
        return 200, {}, json.dumps(payload).encode()

    monkeypatch.setattr(WorkspaceClient, "_request", request)
    client = object.__new__(WorkspaceClient)
    result = client.get_project_object_location("project/one", "object/two")
    assert isinstance(result, ObjectLocation)
    assert result == ObjectLocation(**payload)
    assert calls == [("GET", "/v1/projects/project%2Fone/objects/object%2Ftwo/location")]


def test_both_api_families_are_exported() -> None:
    assert ObjectLocation is generated.ObjectLocation
    assert ManagedOutput is generated.ManagedOutput
    assert "getProjectObjectLocation" in OPERATIONS
    for name in (
        "list_managed_outputs", "get_managed_output", "export_managed_output",
        "adopt_managed_output", "update_managed_output_lifecycle",
    ):
        assert callable(getattr(WorkspaceClient, name))


def test_obsolete_generic_client_artifact_is_absent() -> None:
    assert not (ROOT / "generated" / "runtime_client.py").exists()
    assert not (ROOT / "generated" / "runtime_client_metadata.py").exists()
    assert not (ROOT / "scripts" / "generate_runtime_client.py").exists()


def test_generation_preserves_source_task_identity():
    row = generated.Generation.from_json({"generation_id": "g", "project_id": "p", "source_task_id": "task-1", "type": "image", "status": "completed", "version": 1, "created_at": "now", "updated_at": "now"})
    assert row.source_task_id == "task-1"
