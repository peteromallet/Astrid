from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from astrid.core.execution.generic_host import (
    HostError,
    _startup_identity_attestation,
    source_checkout_digest,
)


def _source_checkout(tmp_path: Path) -> Path:
    checkout = tmp_path / "checkout"
    packs = checkout / "astrid" / "packs" / "h3_av"
    packs.mkdir(parents=True)
    (packs / "pack.yaml").write_text("id: h3_av\n", encoding="utf-8")
    return checkout


def test_startup_attestation_normalizes_and_records_exact_target(tmp_path: Path) -> None:
    checkout = _source_checkout(tmp_path)
    target = {
        "kind": "runpod",
        "pod_id": "pod-5090",
        "provider_account_ref": "runpod-default",
    }

    receipt = _startup_identity_attestation(
        source_checkout=checkout,
        source_inventory_identity="inventory-1",
        expected_source_checkout_digest=source_checkout_digest(checkout),
        boot_manifest_hash="sha256:boot",
        require_target=True,
        target_json=json.dumps(target),
    )

    assert receipt["target"] == target
    assert receipt["target_digest"] == "sha256:" + hashlib.sha256(
        json.dumps(target, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert receipt["source"] == {
        "checkout": str(checkout),
        "checkout_digest": source_checkout_digest(checkout),
        "inventory_identity": "inventory-1",
    }


def test_startup_fails_before_readiness_on_source_mismatch(tmp_path: Path) -> None:
    checkout = _source_checkout(tmp_path)

    with pytest.raises(HostError, match="source identity mismatch"):
        _startup_identity_attestation(
            source_checkout=checkout,
            source_inventory_identity="inventory-1",
            expected_source_checkout_digest="stale-source-digest",
            require_target=False,
        )


def test_startup_fails_before_readiness_when_required_target_is_missing(tmp_path: Path) -> None:
    with pytest.raises(HostError, match="requires an explicit execution target"):
        _startup_identity_attestation(
            source_checkout=_source_checkout(tmp_path),
            source_inventory_identity="inventory-1",
            require_target=True,
            target_json="",
        )


def test_startup_rejects_malformed_target_before_claims(tmp_path: Path) -> None:
    with pytest.raises(HostError, match="not a valid execution target"):
        _startup_identity_attestation(
            source_checkout=_source_checkout(tmp_path),
            source_inventory_identity="inventory-1",
            target_json=json.dumps({"kind": "runpod", "pod_id": "only-pod-id"}),
        )
