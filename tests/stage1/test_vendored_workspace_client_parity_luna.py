"""Immutable release gates for Astrid's vendored workspace client.

The runtime repository owns generation.  Astrid deliberately does not invoke
that repository's generator at test time: this gate proves that the checked-in
client is the exact, reviewed artifact identified by its source commit and
that its declared operation/signature surface has not drifted in-place.
"""

from __future__ import annotations

import ast
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

# These values are intentionally duplicated in the release gate. A future
# contract refresh must update the canonical component/schema digests and this
# test in one reviewed change; no ambient sibling checkout can silently alter
# the shipped transport.
PINNED_COMPONENT_MANIFEST_SHA256 = "sha256:889a00e55cf2e3b5d6ae1832579c7540fd8bc9c71ae5a31a0f0ea358b441af1e"
PINNED_PROTOCOL = "workspace.v1"
PINNED_SCHEMA_DIGEST = "sha256:8c3b3cf30bedf4c2487da83763446c66a76f46ad86521724e38ff397762fec55"
PINNED_GENERATED_CLIENT_SHA256 = "sha256:6a3ebd34d59e4b01d503b3d630cfb4325eff5b448cad96951f0931940a86910a"
PINNED_SIGNATURE_SHA256 = "sha256:d833b3002ced1c8440e4b960ec64b2209b3d4691d244d62bf1ab65013254239f"


def _signature_digest() -> str:
    tree = ast.parse(GENERATED_PATH.read_text(encoding="utf-8"))
    client = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "WorkspaceClient"
    )
    signatures = [
        f"{node.name}:{ast.unparse(node.args)}\n"
        for node in client.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]
    return "sha256:" + hashlib.sha256("".join(signatures).encode()).hexdigest()


def _camel_to_snake(value: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value).lower()


def test_vendored_client_is_the_frozen_runtime_artifact() -> None:
    assert COMPONENT_MANIFEST_SHA256 == PINNED_COMPONENT_MANIFEST_SHA256
    assert PROTOCOL == PINNED_PROTOCOL == generated.PROTOCOL
    assert SCHEMA_DIGEST == PINNED_SCHEMA_DIGEST == generated.SCHEMA_DIGEST
    assert "sha256:" + hashlib.sha256(GENERATED_PATH.read_bytes()).hexdigest() == PINNED_GENERATED_CLIENT_SHA256
    assert _signature_digest() == PINNED_SIGNATURE_SHA256


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
    assert methods - operation_methods == composed_helpers
    assert operation_methods <= methods


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
