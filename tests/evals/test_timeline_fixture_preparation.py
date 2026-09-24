from __future__ import annotations

import json
from pathlib import Path

from evals.timeline.fixture_preparation import (
    build_preparation_table,
    inspect_action_sidecars,
    materialize_action_sidecar_inputs,
    materialize_action_target_receipts,
    prepare_public_case,
    write_preparation_table,
)


ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "Astrid/evals/timeline/suite.json"
FIXTURES = ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"


def test_preparation_table_has_all_cases_and_preserves_real_blockers(tmp_path: Path) -> None:
    rows = build_preparation_table(SUITE, FIXTURES)
    assert len(rows) == 20
    by_id = {row.case_id: row for row in rows}
    assert by_id["A01"].kind == "action"
    assert "action/manifest.json" in by_id["A01"].input
    assert by_id["L05"].status == "blocked-essential-input"
    assert any("historical video alternative" in blocker for blocker in by_id["L05"].blockers)
    assert by_id["L10"].kind == "navigation"
    assert any("afplay" in tool for tool in by_id["L10"].available_tools)
    table = write_preparation_table(rows, tmp_path / "preparation.md")
    text = table.read_text(encoding="utf-8")
    assert text.count("| A") + text.count("| L") >= 20
    assert "answer" not in text.lower()


def test_action_receipt_preparation_copies_only_real_available_receipts(tmp_path: Path) -> None:
    source = tmp_path / "coordinator-source" / "A01"
    source.mkdir(parents=True)
    target = {
        "kind": "astrid.timeline-eval.public-target.v1",
        "case_id": "A01",
        "endpoint": "http://127.0.0.1:18787",
        "project_id": "disposable-project",
        "timeline_id": "disposable-timeline",
        "head_revision_id": "revision-1",
        "read_only": False,
        "owned_media_ids": ["sha256:old", "sha256:new"],
        "capabilities": {"edit": {"status": "available", "route": "timelines replace-parent-media"}},
        "target_locator": {"readback_projection": "active_media_replacement.v1"},
    }
    (source / "target.json").write_text(json.dumps(target), encoding="utf-8")

    rows = materialize_action_target_receipts(
        source_root=source.parent, destination_root=tmp_path / "prepared",
    )

    assert rows["A01"]["status"] == "prepared"
    assert rows["A01"]["owned_media_count"] == 2
    assert rows["A02"]["status"] == "blocked-essential-input"
    copied = json.loads((tmp_path / "prepared/A01/target.json").read_text())
    assert copied["project_id"] == "disposable-project"
    assert not (tmp_path / "prepared/A02/target.json").exists()
    preparation = json.loads((tmp_path / "prepared/preparation.json").read_text())
    assert preparation["owner"] == "coordinator"
    assert preparation["cases"]["A02"]["status"] == "blocked-essential-input"


def test_action_receipt_preparation_rejects_blocked_contract_even_with_json(tmp_path: Path) -> None:
    source = tmp_path / "source" / "A02"
    source.mkdir(parents=True)
    (source / "target.json").write_text(json.dumps({
        "kind": "astrid.timeline-eval.public-target.v1",
        "case_id": "A02",
        "endpoint": "http://127.0.0.1:18787",
        "project_id": "p", "timeline_id": "t", "head_revision_id": "r",
        "read_only": False, "owned_media_ids": ["sha256:media"],
        "capabilities": {"edit": {"status": "available", "route": "invented"}},
        "target_locator": {"readback_projection": "invented.v1"},
    }), encoding="utf-8")
    rows = materialize_action_target_receipts(
        source_root=source.parent, destination_root=tmp_path / "prepared",
    )
    assert rows["A02"]["status"] == "blocked-essential-input"
    assert "no materialized disposable target" in rows["A02"]["reason"]
    assert not (tmp_path / "prepared/A02/target.json").exists()


def test_action_sidecar_inventory_verifies_pinned_image_bytes(tmp_path: Path) -> None:
    fixture = tmp_path / "fixtures"
    action = fixture / "action"
    image = action / "A09-images" / "one.bin"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"pinned image")
    import hashlib
    digest = hashlib.sha256(b"pinned image").hexdigest()
    (action / "A09-images.json").write_text(json.dumps({
        "case_id": "A09", "images": [{
            "path": "A09-images/one.bin", "sha256": digest,
            "media_id": "sha256:" + digest,
        }],
    }), encoding="utf-8")
    checked = inspect_action_sidecars(fixture_root=fixture, case_id="A09")
    assert checked["status"] == "verified-inputs"
    assert checked["media"] == [{"path": "A09-images/one.bin", "media_id": "sha256:" + digest}]

    image.write_bytes(b"changed")
    rejected = inspect_action_sidecars(fixture_root=fixture, case_id="A09")
    assert rejected["status"] == "blocked"
    assert any("digest mismatch" in error for error in rejected["errors"])


def test_action_sidecar_inventory_does_not_turn_non_media_sidecar_into_target(tmp_path: Path) -> None:
    fixture = tmp_path / "fixtures"
    action = fixture / "action"
    action.mkdir(parents=True)
    (action / "A06-text-roles.json").write_text(json.dumps({
        "case_id": "A06", "bindings": [{"role": "visible_title"}],
    }), encoding="utf-8")
    checked = inspect_action_sidecars(fixture_root=fixture, case_id="A06")
    assert checked["status"] == "verified-inputs"
    assert checked["media"] == []
    assert "target" not in checked


def test_action_sidecar_inventory_preserves_missing_case_input(tmp_path: Path) -> None:
    checked = inspect_action_sidecars(fixture_root=tmp_path, case_id="A07")
    assert checked["status"] == "blocked"
    assert checked["missing"] == ["no pinned case sidecar"]


def test_sidecar_preparation_copies_verified_inputs_without_target_receipts(tmp_path: Path) -> None:
    destination = tmp_path / "prepared"
    rows = materialize_action_sidecar_inputs(
        fixture_root=FIXTURES, destination_root=destination,
    )
    assert set(rows) == {"A05", "A06", "A09", "A10"}
    assert all(row["status"] == "prepared-inputs" for row in rows.values())
    assert all(row["launchable"] is False and row["target_receipt"] is None for row in rows.values())
    assert rows["A09"]["input_count"] == 5
    assert rows["A10"]["input_count"] == 201
    assert (destination / "A05/A05-vo-endpoints.json").is_file()
    assert (destination / "A09/A09-images/image-01-002e1ef76ef2.png").is_file()
    assert (destination / "A10/A10-images/brightness-200.png").is_file()
    assert not (destination / "A09/target.json").exists()
    manifest = json.loads((destination / "preparation.json").read_text(encoding="utf-8"))
    assert manifest["launchable"] is False
    assert manifest["cases"]["A10"]["input_count"] == 201


def test_sidecar_preparation_is_idempotent_and_refuses_changed_destination(tmp_path: Path) -> None:
    destination = tmp_path / "prepared"
    materialize_action_sidecar_inputs(fixture_root=FIXTURES, destination_root=destination)
    materialize_action_sidecar_inputs(fixture_root=FIXTURES, destination_root=destination)
    changed = destination / "A06/A06-text-roles.json"
    changed.write_text("changed\n", encoding="utf-8")
    import pytest
    with pytest.raises(ValueError, match="different sidecar input"):
        materialize_action_sidecar_inputs(fixture_root=FIXTURES, destination_root=destination)


def test_prepare_public_action_case_fails_closed_without_target(tmp_path: Path) -> None:
    result = prepare_public_case(
        {"id": "A02", "kind": "action"}, fixture_root=FIXTURES,
        destination=tmp_path / "A02",
    )
    assert result["status"] == "blocked-essential-input"
    assert not (tmp_path / "A02" / "target.json").exists()


def test_prepare_public_navigation_case_materializes_selected_entrypoint(tmp_path: Path) -> None:
    result = prepare_public_case(
        {"id": "L01", "kind": "navigation"}, fixture_root=FIXTURES,
        destination=tmp_path / "L01",
    )
    assert result["status"] == "prepared"
    entrypoint = json.loads((tmp_path / "L01/entrypoint/entrypoint.json").read_text())
    assert entrypoint["read_only"] is True
    assert entrypoint["case_id"] == "L01"


def test_prepare_public_legacy_case_copies_only_labelled_comparison_sidecar(tmp_path: Path) -> None:
    result = prepare_public_case(
        {"id": "L07", "kind": "navigation"}, fixture_root=FIXTURES,
        destination=tmp_path / "L07",
    )
    assert result["status"] == "prepared"
    entrypoint = json.loads((tmp_path / "L07/entrypoint/entrypoint.json").read_text())
    assert entrypoint["read_only"] is True
    assert entrypoint["case_id"] == "L07"
    related = entrypoint["related_inputs"]["legacy_canonical_compare"]
    assert related["path"] == "L07-legacy-compare.json"
    sidecar = json.loads((tmp_path / "L07/entrypoint/L07-legacy-compare.json").read_text())
    assert sidecar["legacy_clips"][0]["clipType"] == "shot"
    assert sidecar["canonical_fixture"]["canonical_clip_type"] == "media"
