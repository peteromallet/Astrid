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
PINNED_COMPONENT_MANIFEST_SHA256 = "sha256:fcae767eaba85e406658ac3b14f3c3447e11073dffcb5e1256e223bdb84f51f4"
PINNED_SCHEMA_DIGEST = "sha256:f47cff3ee8939b6caa23bd8a2cb32e4df82fb4c3cd6fa2d77aa02df69a7a0dee"
PINNED_GENERATED_SHA256 = "c9efb120637753c0422b9f8e058a11965d367691dd40038ee7f86315115c26f9"
PINNED_METADATA_SHA256 = "63e2de4ffca15f1055e44069ed28134ffb03cf94bf3cb5ef55a842d6889c48df"


def _camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()


def test_vendored_client_is_the_frozen_runtime_artifact() -> None:
    assert SOURCE_COMMIT == "04fee31cba2a9b7c095e1c64313b8d8b6ab0e3dd"
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


def test_vendored_health_preserves_runtime_identity() -> None:
    health = generated.Health.from_json({
        "status": "ok",
        "protocol": "workspace.v1",
        "schema_digest": SCHEMA_DIGEST,
        "runtime_epoch": 1,
        "runtime_session_id": "runtime-session-1",
        "runtime_instance_id": "runtime-instance-1",
    })
    assert health.runtime_session_id == "runtime-session-1"
    assert health.runtime_instance_id == "runtime-instance-1"


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
