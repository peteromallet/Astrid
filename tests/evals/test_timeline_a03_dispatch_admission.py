from __future__ import annotations

import pytest

from evals.timeline.fixture_contracts import (
    action_target_contract,
    case_launch_prerequisites,
    validate_action_target_receipt,
)
from evals.timeline.independent_readback import (
    IndependentReadbackError,
    MOVE_OCCURRENCE_GROUP,
    ReadbackObservation,
    ReadbackContract,
)
from evals.timeline.luna_native import _verify_projected_readback


def _closure(order: str, starts: list[int]):
    durations = dict(zip("abcd", (100, 200, 300, 400)))
    occurrences, shots, internals = [], [], []
    for occurrence_id, start in zip(order, starts):
        shot_id, shot_revision_id = f"shot-{occurrence_id}", f"shot-rev-{occurrence_id}"
        internal_id = f"internal-{occurrence_id}"
        occurrences.append({
            "occurrence_id": occurrence_id,
            "shot_id": shot_id,
            "shot_revision_id": shot_revision_id,
            "duration_ms": durations[occurrence_id],
            "placement": {"start_ms": start, "track": "picture"},
        })
        shots.append({
            "shot_id": shot_id,
            "revision_id": shot_revision_id,
            "internal_timeline_revision_id": internal_id,
            "payload": {
                "picture": f"picture-{occurrence_id}",
                "voice": f"voice-{occurrence_id}",
                "caption": f"caption-{occurrence_id}",
                "internal_timeline_revision_id": internal_id,
            },
        })
        internals.append({"revision_id": internal_id, "payload": {"clips": [
            {"id": f"picture-{occurrence_id}", "track": "picture"},
            {"id": f"voice-{occurrence_id}", "track": "voice"},
            {"id": f"caption-{occurrence_id}", "track": "caption"},
        ]}})
    return {
        "head_revision_id": "head-after" if order != "abcd" else "head-before",
        "parent_revision": {"revision_id": "parent", "payload": {"occurrences": occurrences}},
        "shot_revisions": shots,
        "internal_timeline_revisions": internals,
    }


class _Reader:
    def __init__(self, closure):
        self.closure = closure

    def current_head(self, project_id, timeline_id):
        return self.closure["head_revision_id"]

    def read_current_closure(self, project_id, timeline_id, *, head=None):
        assert head in (None, self.closure["head_revision_id"])
        return self.closure

    def list_project_timeline_heads(self, project_id):
        return {"disposable-timeline": self.closure["head_revision_id"]}


def _target():
    return {
        "kind": "astrid.timeline-eval.public-target.v1",
        "case_id": "A03",
        "scope": "selected-case-only",
        "read_only": False,
        "endpoint": "http://127.0.0.1:9001",
        "project_id": "disposable-project",
        "timeline_id": "disposable-timeline",
        "head_revision_id": "head-before",
        "capabilities": {"edit": {
            "status": "available",
            "route": "Astrid SDK move_occurrence_group() + publish_authoring_candidate",
        }},
        "target_locator": {
            "readback_projection": MOVE_OCCURRENCE_GROUP,
            "closing_occurrence_id": "d",
            "middle_occurrence_id": "b",
        },
        "occurrence_ids": list("abcd"),
        "shot_ids": [f"shot-{item}" for item in "abcd"],
        "shot_revision_ids": [f"shot-rev-{item}" for item in "abcd"],
        "internal_revision_ids": [f"internal-{item}" for item in "abcd"],
        "owned_media_ids": [f"media-{item}" for item in "abcd"],
    }


def test_a03_static_route_is_distinct_from_missing_fresh_target_and_readback():
    case = {"id": "A03", "kind": "action"}
    contract = action_target_contract(case)
    assert contract.status == "ready"
    assert contract.edit_route
    assert contract.readback_projection == MOVE_OCCURRENCE_GROUP

    prerequisites = case_launch_prerequisites(
        case,
        fixture_ready=True,
        hidden_checks=[{"id": "a03_order", "check": "order"}],
        target_receipt=None,
        coordinator_readback_ready=False,
        coordinator_safety_ready=False,
    )
    assert any("target receipt is missing" in reason for reason in prerequisites)
    assert any("readback collector is not proven" in reason for reason in prerequisites)
    assert any("safety capture is not proven" in reason for reason in prerequisites)

    target_errors = validate_action_target_receipt(_target(), contract)
    assert target_errors == []


def test_native_dispatch_calls_independent_a03_verifier_on_exact_closures():
    before_closure = _closure("abcd", [0, 100, 300, 600])
    after_closure = _closure("adbc", [0, 100, 500, 700])
    before = ReadbackObservation(
        head_revision_id="head-before",
        target={"head_revision_id": "head-before"},
        parent_protected_fingerprint="",
        target_protected={},
        sibling_occurrence_fingerprints={},
        sibling_timeline_fingerprints={},
        source_fingerprint=None,
    )
    result = _verify_projected_readback(
        reader=_Reader(after_closure),
        target=_target(),
        contract=ReadbackContract(case_id="A03", projection=MOVE_OCCURRENCE_GROUP),
        before=before,
        before_closure=before_closure,
        publication={
            "case_id": "A03", "project_id": "disposable-project",
            "timeline_id": "disposable-timeline", "expected_head": "head-before",
            "parent_revision_id": "head-after",
        },
        source_reader=None,
    )
    assert result["projection"] == MOVE_OCCURRENCE_GROUP
    assert result["status"] == "pass"
    assert result["before_observed"] is True
    assert result["after_observed"] is True
    assert [row["occurrence_id"] for row in result["after"]["occurrences"]] == list("adbc")
    assert result["safety"]["test_target_only"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("project_id", "wrong-project"),
        ("timeline_id", "wrong-timeline"),
        ("case_id", "A01"),
    ],
)
def test_a03_rejects_publication_receipt_with_wrong_target_identity(field, value):
    before_closure = _closure("abcd", [0, 100, 300, 600])
    after_closure = _closure("adbc", [0, 100, 500, 700])
    before = ReadbackObservation(
        head_revision_id="head-before",
        target={"head_revision_id": "head-before"},
        parent_protected_fingerprint="",
        target_protected={},
        sibling_occurrence_fingerprints={},
        sibling_timeline_fingerprints={},
        source_fingerprint=None,
    )
    publication = {
        "case_id": "A03", "project_id": "disposable-project",
        "timeline_id": "disposable-timeline", "expected_head": "head-before",
        "parent_revision_id": "head-after",
    }
    publication[field] = value
    with pytest.raises(IndependentReadbackError, match=rf"receipt {field}"):
        _verify_projected_readback(
            reader=_Reader(after_closure), target=_target(),
            contract=ReadbackContract(case_id="A03", projection=MOVE_OCCURRENCE_GROUP),
            before=before, before_closure=before_closure, publication=publication,
            source_reader=None,
        )


def test_a03_after_artifact_uses_the_declared_occurrence_path(tmp_path):
    from evals.timeline.luna_native import _write_json
    from evals.timeline.run import load_json

    artifact = {
        "head_revision_id": "head-after",
        "occurrences": [{"occurrence_id": value} for value in "adbc"],
    }
    path = tmp_path / "after.json"
    _write_json(path, artifact)
    loaded = load_json(path)
    assert [row["occurrence_id"] for row in loaded["occurrences"]] == list("adbc")
