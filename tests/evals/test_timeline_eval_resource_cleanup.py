from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.timeline.resource_cleanup import (
    QUARANTINE_RECEIPT_KIND,
    ResourceCleanupError,
    cleanup_attempt_resources,
    write_resource_manifest,
)


def _roots(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    attempt = tmp_path / "attempt-eval"
    evidence = attempt / "evidence"
    canonical = tmp_path / "canonical"
    quarantine = tmp_path / "quarantine"
    evidence.mkdir(parents=True)
    canonical.mkdir()
    (evidence / "trace.jsonl").write_text('{"event":"kept"}\n', encoding="utf-8")
    return attempt, evidence, canonical, quarantine


def _marker(root: Path, *, attempt_id: str = "attempt-eval", realm_id: str = "disposable-realm") -> dict[str, object]:
    identity = {
        "kind": "astrid.timeline-eval-resource.v1",
        "purpose": "timeline-eval-disposable-realm",
        "attempt_id": attempt_id,
        "realm_id": realm_id,
    }
    (root / ".resource-marker.json").write_text(json.dumps(identity), encoding="utf-8")
    return identity


def _manifest(
    tmp_path: Path,
    resource: Path,
    evidence: Path,
    canonical: Path,
    *,
    state: str = "ready",
    identity: dict[str, object] | None = None,
) -> Path:
    identity = identity or _marker(resource)
    path = tmp_path / "attempt-eval" / "resource-manifest.json"
    write_resource_manifest(
        path,
        attempt_id="attempt-eval",
        realm_id="disposable-realm",
        evidence_root=evidence,
        canonical_root=canonical,
        canonical_realm_id="canonical-realm",
        resources=[
            {
                "name": "runtime-realm",
                "kind": "runtime_realm",
                "path": resource,
                "marker": ".resource-marker.json",
                "marker_identity": identity,
                "realm_id": "disposable-realm",
                "state": state,
            }
        ],
    )
    return path


def test_cleanup_refuses_changed_marker_and_preserves_resource(tmp_path: Path) -> None:
    _attempt, evidence, canonical, quarantine = _roots(tmp_path)
    resource = tmp_path / "runtime"
    resource.mkdir()
    _manifest(tmp_path, resource, evidence, canonical)
    (resource / ".resource-marker.json").write_text(
        json.dumps({"kind": "wrong", "realm_id": "canonical-realm"}), encoding="utf-8"
    )

    with pytest.raises(ResourceCleanupError, match="marker identity mismatch"):
        cleanup_attempt_resources(tmp_path / "attempt-eval" / "resource-manifest.json", quarantine_root=quarantine)
    assert resource.is_dir()
    assert not (quarantine / "attempt-eval").exists()
    assert (evidence / "trace.jsonl").is_file()


def test_cleanup_refuses_canonical_target_before_move(tmp_path: Path) -> None:
    attempt, evidence, canonical, quarantine = _roots(tmp_path)
    resource = canonical / "runtime"
    resource.mkdir()
    identity = _marker(resource)
    with pytest.raises(ResourceCleanupError, match="overlaps canonical root"):
        _manifest(tmp_path, resource, evidence, canonical, identity=identity)
    assert resource.is_dir()
    assert not (attempt / "resource-manifest.json").exists()


def test_cleanup_is_idempotent_and_returns_quarantine_receipt(tmp_path: Path) -> None:
    _attempt, evidence, canonical, quarantine = _roots(tmp_path)
    resource = tmp_path / "runtime"
    resource.mkdir()
    manifest = _manifest(tmp_path, resource, evidence, canonical)

    first = cleanup_attempt_resources(manifest, quarantine_root=quarantine)
    second = cleanup_attempt_resources(manifest, quarantine_root=quarantine)

    assert first == second
    assert first["kind"] == QUARANTINE_RECEIPT_KIND
    assert first["resources"] == [{
        "name": "runtime-realm",
        "status": "quarantined",
        "path": str(quarantine / "attempt-eval" / "runtime-realm"),
    }]
    receipt = quarantine / "attempt-eval" / "quarantine-receipt.json"
    assert receipt.is_file()
    assert not resource.exists()
    assert (quarantine / "attempt-eval" / "runtime-realm" / ".resource-marker.json").is_file()
    assert (evidence / "trace.jsonl").read_text(encoding="utf-8").startswith('{"event":"kept"}')


def test_interrupted_setup_is_reclaimable_without_touching_evidence(tmp_path: Path) -> None:
    _attempt, evidence, canonical, quarantine = _roots(tmp_path)
    planned = tmp_path / "runtime-created-after-manifest"
    manifest = _manifest(tmp_path, planned, evidence, canonical, state="planned", identity={
        "kind": "astrid.timeline-eval-resource.v1",
        "purpose": "timeline-eval-disposable-realm",
        "attempt_id": "attempt-eval",
        "realm_id": "disposable-realm",
    })

    receipt = cleanup_attempt_resources(manifest, quarantine_root=quarantine)

    assert receipt["resources"] == [{
        "name": "runtime-realm",
        "status": "not_created",
        "path": str(planned),
    }]
    assert (evidence / "trace.jsonl").is_file()
    assert not quarantine.joinpath("attempt-eval", "runtime-realm").exists()
