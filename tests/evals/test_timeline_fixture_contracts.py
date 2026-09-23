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
            "readback_projection": "exact_closure_navigation.v1",
            "target_aliases": ["intro_b01"],
        },
        "targets": {"intro_b01": {"occurrence_id": "occ-1"}},
    }
    assert validate_navigation_entrypoint(entrypoint, contract) == []
    entrypoint["targets"] = {}
    assert "selected target aliases are missing" in " ".join(
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


def test_action_contract_blocks_unmaterialized_a02_and_rejects_synthetic_receipt() -> None:
    contract = action_target_contract({"id": "A02"})
    assert contract.status == "blocked"
    errors = validate_action_target_receipt({"case_id": "A02"}, contract)
    assert errors and "no materialized disposable target" in errors[0]


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
    }
