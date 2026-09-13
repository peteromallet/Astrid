"""Immutable release gates for Astrid's vendored workspace client.

The runtime repository owns generation. Astrid deliberately does not invoke
that repository's generator at test time: this gate proves that the checked-in
client and metadata are the exact reviewed artifacts identified by their
contract exports and immutable file hashes.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from pathlib import Path

from banodoco_workspace_client import WorkspaceClient, generated
from banodoco_workspace_client.contract_metadata import (
    COMPONENT_MANIFEST_SHA256,
    OPERATIONS,
    PROTOCOL,
    SCHEMA_DIGEST,
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
PINNED_SCHEMA_DIGEST = "sha256:2043e7bc9b06fc19e20906aff8eaa429fcb8ab335bedc31bd34bff9ab5b71b75"
PINNED_GENERATED_SHA256 = "6f98f414f19848d477675b8483edacc3dc51b74c549466a29102cc7572f45d7e"
PINNED_METADATA_SHA256 = "e4cf9c340d61de0d2061c195ab8a2b7e88568177dbaf2a44f6e84fd1b599e5c4"


def _camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()


def test_vendored_client_is_the_frozen_runtime_artifact() -> None:
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
    wire_only_operations = {"adopt_managed_output", "update_managed_output_lifecycle"}
    assert methods - operation_methods == composed_helpers
    assert wire_only_operations <= operation_methods
    # Lifecycle operations remain generated wire parity only; Astrid's
    # product-facing client need not expose them.
    assert operation_methods - wire_only_operations <= methods


def test_frozen_mutation_signatures_require_idempotency_keys() -> None:
    for name in (
        "update_timeline_document",
        "create_generation",
        "create_variant",
        "promote_project_shot_candidate",
    ):
        parameter = inspect.signature(getattr(WorkspaceClient, name)).parameters["idempotency_key"]
        assert parameter.default is inspect.Parameter.empty


def test_obsolete_generic_client_artifact_is_absent() -> None:
    assert not (ROOT / "generated" / "runtime_client.py").exists()
    assert not (ROOT / "generated" / "runtime_client_metadata.py").exists()
    assert not (ROOT / "scripts" / "generate_runtime_client.py").exists()
