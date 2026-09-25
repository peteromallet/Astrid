from __future__ import annotations

from evals.timeline.fixture_contracts import (
    action_target_contract,
    navigation_fixture_contract,
    validate_action_target_receipt,
    validate_navigation_entrypoint,
)


def test_missing_navigation_surface_inputs_remain_typed_blockers() -> None:
    contract = navigation_fixture_contract({
        "id": "L04", "targets": ["ideas_b03"],
        "fixture_requirements": [
            {"scope": "manifest", "path": "surface_adapters.text_reader",
             "reason": "text reader adapter is not supplied"},
        ],
    })
    payload = contract.as_dict()
    assert payload["status"] == "environment_unavailable"
    assert payload["diagnostic_code"] == "surface_capability_unavailable"
    assert payload["readback_projection"] == "exact_closure_navigation.v1"
    assert payload["required_inputs"][0]["path"] == "surface_adapters.text_reader"


def test_materialized_navigation_entrypoint_is_checked_without_inventing_inputs() -> None:
    contract = navigation_fixture_contract({"id": "L10", "targets": ["intro_b01"]})
    entrypoint = {
        "kind": "astrid.timeline-eval.offline-navigation-entry.v1",
        "case_id": "L10", "read_only": True,
        "target_receipt": {
            "kind": "astrid.timeline-eval.offline-navigation-target.v1",
            "readback_projection": "exact_closure_navigation.v1",
            "target_aliases": ["intro_b01"],
            "source_head": "head-1",
            "source_closure_digest": "sha256:closure",
            "media_ids": ["sha256:media"],
        },
        "source": {
            "timeline_id": "timeline-1",
            "head_revision_id": "head-1",
            "closure_digest": "sha256:closure",
        },
        "targets": {"intro_b01": {"occurrence_id": "occ-1"}},
    }
    assert validate_navigation_entrypoint(entrypoint, contract) == []
    entrypoint["targets"] = {}
    assert "selected target aliases are missing" in " ".join(
        validate_navigation_entrypoint(entrypoint, contract)
    )


def test_l01_contract_requires_pinned_source_and_coordinator_readback_safety() -> None:
    contract = navigation_fixture_contract({"id": "L01", "targets": ["intro_b01"]})
    data = contract.as_dict()
    assert "coordinator before.json" in " ".join(data["coordinator_evidence_required"])
    assert any("source-unchanged" in item for item in data["coordinator_evidence_required"])
    entrypoint = {
        "kind": "astrid.timeline-eval.offline-navigation-entry.v1",
        "case_id": "L01", "read_only": True,
        "source": {"timeline_id": "timeline-1", "head_revision_id": "head-1",
                   "closure_digest": "sha256:closure"},
        "target_receipt": {"readback_projection": "exact_closure_navigation.v1",
                            "target_aliases": ["intro_b01"], "source_head": "wrong",
                            "source_closure_digest": "sha256:closure", "media_ids": []},
        "targets": {"intro_b01": {"occurrence_id": "occ-1"}},
    }
    assert "navigation receipt source head differs" in " ".join(
        validate_navigation_entrypoint(entrypoint, contract)
    )


def test_l05_and_l07_missing_media_and_legacy_inputs_are_fail_closed() -> None:
    l05 = navigation_fixture_contract({
        "id": "L05", "targets": ["ideas_b03"],
        "fixture_requirements": [{
            "scope": "targets", "path": "ideas_b03.historical_video_alternatives",
            "reason": "retained historical video alternative is absent from this closure",
        }],
    })
    l07 = navigation_fixture_contract({
        "id": "L07", "targets": ["intro_b01", "ideas_b03"],
        "fixture_requirements": [{
            "scope": "targets", "path": "legacy_clip_type_shot_fixture",
            "reason": "separate labelled legacy clipType=shot fixture is absent",
        }],
    })
    assert l05.status == l07.status == "blocked"
    assert l05.diagnostic_code == l07.diagnostic_code == "missing_pinned_fixture_input"
    assert l05.as_dict()["required_inputs"][0]["kind"] == "missing_fixture_input"


def test_action_contract_exposes_generic_edit_separately_from_readback() -> None:
    contract = action_target_contract({"id": "A02"})
    assert contract.status == "ready"
    assert contract.edit_route == "authoring-bundle validate/commit"
    assert contract.readback_projection == "remove_occurrence_compact.v1"
    errors = validate_action_target_receipt({"case_id": "A02"}, contract)
    assert errors and "target receipt kind" in errors[0]


def test_a04_to_a10_contracts_advertise_generic_edit_without_readback_claim() -> None:
    for case_id in ("A04", "A05", "A06", "A07", "A08", "A09", "A10"):
        contract = action_target_contract({"id": case_id})
        assert contract.status == "ready"
        assert contract.edit_route == "authoring-bundle validate/commit"
        assert contract.readback_projection is None
        assert contract.readback_status == "unavailable"


def test_a01_action_contract_requires_real_receipt_fields() -> None:
    contract = action_target_contract({"id": "A01"})
    errors = validate_action_target_receipt({
        "kind": "astrid.timeline-eval.public-target.v1", "case_id": "A01",
        "read_only": False,
        "capabilities": {"edit": {"status": "available",
                                      "route": "timelines replace-parent-media"}},
        "target_locator": {"readback_projection": "active_media_replacement.v1"},
    }, contract)
    assert set(errors) >= {
        "action target is missing endpoint",
        "action target is missing project_id",
        "action target is missing timeline_id",
        "action target is missing head_revision_id",
        "action target scope must be selected-case-only",
        "action target is missing a non-empty occurrence_ids inventory",
        "action target is missing a non-empty owned_media_ids inventory",
    }
    assert "publication receipt" in " ".join(contract.as_dict()["required_coordinator_evidence"])


def test_a01_complete_disposable_receipt_satisfies_route_contract() -> None:
    contract = action_target_contract({"id": "A01"})
    target = {
        "kind": "astrid.timeline-eval.public-target.v1", "case_id": "A01",
        "scope": "selected-case-only", "read_only": False,
        "endpoint": "http://127.0.0.1:9001", "project_id": "disposable-project",
        "timeline_id": "disposable-timeline", "head_revision_id": "head-before",
        "capabilities": {"edit": {"status": "available", "route": "timelines replace-parent-media"}},
        "target_locator": {
            "readback_projection": "active_media_replacement.v1", "occurrence_id": "occ-1",
            "shot_id": "shot-1", "shot_revision_id": "shot-rev-1", "selector_clip_id": "image-1",
            "voice_clip_id": "voice-1", "frame_overlay_clip_id": "overlay-1",
            "replacement_asset_key": "new-image", "preserve_roles": ["timing", "voiceover", "frame-overlay"],
        },
        "occurrence_ids": ["occ-1"], "shot_ids": ["shot-1"],
        "shot_revision_ids": ["shot-rev-1"], "internal_revision_ids": ["internal-1"],
        "owned_media_ids": ["sha256:old", "sha256:new"],
    }
    assert validate_action_target_receipt(target, contract) == []


def test_a03_exposes_group_move_and_independent_readback_contract() -> None:
    contract = action_target_contract({"id": "A03"})
    assert contract.status == "ready"
    assert contract.edit_route == "Astrid SDK move_occurrence_group() + publish_authoring_candidate"
    assert contract.readback_projection == "move_occurrence_group.v1"
    assert {item.path for item in contract.required_inputs} == {"target.json"}
    assert any("independent move_occurrence_group.v1 verification" in item
               for item in contract.required_coordinator_evidence)
    assert contract.reason is None
