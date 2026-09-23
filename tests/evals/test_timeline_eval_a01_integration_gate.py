from __future__ import annotations

from types import SimpleNamespace

import pytest

from evals.timeline import a01_integration_gate as gate
from evals.timeline.independent_readback import CaseReadbackResult, ReadbackObservation


OLD = "sha256:" + "1" * 64
NEW = "sha256:" + "2" * 64


def _target(label: str) -> dict:
    return {
        "project_id": f"project-{label}",
        "timeline_id": f"timeline-{label}",
        "head_revision_id": f"head-{label}",
        "target_locator": {
            "occurrence_id": "occ-target",
            "selector_clip_id": "clip-target",
        },
    }


def _before(target: dict) -> ReadbackObservation:
    return ReadbackObservation(
        head_revision_id=target["head_revision_id"],
        target={"active_media_digest": OLD},
        parent_protected_fingerprint="parent-protected",
        target_protected={},
        sibling_occurrence_fingerprints={"occ-wrong": "sibling-before"},
        sibling_timeline_fingerprints={},
        source_fingerprint=None,
    )


def _result(*, negative: bool) -> CaseReadbackResult:
    return CaseReadbackResult(
        status="fail" if negative else "unavailable",
        before_observed=True,
        after_observed=True,
        committed_revisions={"returned_parent": "new-head"},
        semantic_changed_fields=("active_media_digest",),
        media_digest_evidence={"matched": not negative, "before": OLD, "after": NEW},
        protected_fingerprints={},
        safety={"source_unchanged": None, "test_target_only": False if negative else True},
        reasons=(
            "edit escaped the declared target timeline/selector"
            if negative else "canonical source fingerprint proof is unavailable",
        ),
        before={"active_media_digest": OLD},
        after={"active_media_digest": OLD if negative else NEW},
    )


class _Workspace:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def replace_parent_composition_media(self, project_id, timeline_id, **kwargs):
        self.calls.append({"project_id": project_id, "timeline_id": timeline_id, **kwargs})
        return {"data": {
            "new_head": "new-head",
            "old_head": kwargs["expected_head"],
            "dependency_manifest": {"shots": [], "internal_timelines": []},
        }}


class _Adapter:
    _plain = staticmethod(gate._plain)

    def __init__(self, realm_id: str = "disposable-realm") -> None:
        self.proof = SimpleNamespace(realm_id=realm_id)
        self.workspace = _Workspace()

    def read_current_closure(self, project_id, timeline_id, *, head=None):
        return {
            "head_revision_id": head,
            "parent_revision": {"revision_id": head, "payload": {"occurrences": [
                {"occurrence_id": "occ-target", "shot_id": "shot-target", "shot_revision_id": "rev-target"},
                {"occurrence_id": "occ-wrong", "shot_id": "shot-wrong", "shot_revision_id": "rev-wrong"},
            ]}},
            "shot_revisions": [
                {"shot_id": "shot-target", "revision_id": "rev-target", "internal_timeline_revision_id": "internal-target"},
                {"shot_id": "shot-wrong", "revision_id": "rev-wrong", "internal_timeline_revision_id": "internal-wrong"},
            ],
            "internal_timeline_revisions": [
                {"revision_id": "internal-target", "payload": {"clips": [{"id": "clip-target", "track": "picture"}]}},
                {"revision_id": "internal-wrong", "payload": {"clips": [{"id": "clip-wrong", "track": "picture"}]}},
            ],
        }


def _install_gate_fakes(monkeypatch, *, reject_wrong_shot: bool = True) -> list[str]:
    seeded: list[str] = []
    monkeypatch.setattr(gate, "derive_a01_old_video_baseline", lambda baseline: (
        baseline,
        {
            "selected_old_video_digest": OLD,
            "admitted_new_charcoal_image_digest": NEW,
        },
    ))

    def seed(adapter, baseline, *, media_root, attempt_id):
        label = attempt_id.rsplit("-", 1)[-1]
        seeded.append(label)
        return ({"owned_media": {NEW: NEW}}, _target(label))

    monkeypatch.setattr(gate, "_seed_target", seed)
    monkeypatch.setattr(gate, "observe_case_before", lambda adapter, target, contract: _before(target))

    def verify(adapter, target, contract, before, publication):
        negative = target["project_id"] == "project-negative"
        return _result(negative=negative and reject_wrong_shot)

    monkeypatch.setattr(gate, "verify_case_after", verify)
    return seeded


def test_gate_uses_supported_edits_rejects_wrong_shot_and_exports_third_untouched_target(
    tmp_path, monkeypatch,
):
    seeded = _install_gate_fakes(monkeypatch)
    examples_adapter = _Adapter("examples-realm")
    launch_adapter = _Adapter("launch-realm")

    receipt, target = gate.run_a01_integration_gate(
        examples_adapter, launch_adapter, object(),
        media_root=tmp_path, attempt_id="attempt-7",
    )

    assert seeded == ["positive", "negative", "launch"]
    assert receipt["status"] == "pass"
    assert receipt["wrong_shot_negative"]["rejected"] is True
    assert receipt["source_safety"]["status"] == "outside_gate_boundary"
    assert receipt["examples_realm_id"] == "examples-realm"
    assert receipt["launch_realm_id"] == "launch-realm"
    assert receipt["realm_id"] == "launch-realm"
    assert receipt["realm_separation"] == {
        "status": "pass", "distinct": True, "examples_available_to_worker": False,
    }
    assert target == _target("launch")
    assert "positive" not in target and "wrong_shot_negative" not in target
    assert [call["occurrence_id"] for call in examples_adapter.workspace.calls] == [
        "occ-target", "occ-wrong",
    ]
    assert [call["clip_id"] for call in examples_adapter.workspace.calls] == [
        "clip-target", "clip-wrong",
    ]
    assert launch_adapter.workspace.calls == []


def test_gate_fails_closed_if_wrong_shot_readback_is_not_rejected(tmp_path, monkeypatch):
    _install_gate_fakes(monkeypatch, reject_wrong_shot=False)
    with pytest.raises(RuntimeError, match="wrong-shot publication was not rejected"):
        gate.run_a01_integration_gate(
            _Adapter("examples-realm"), _Adapter("launch-realm"), object(),
            media_root=tmp_path, attempt_id="attempt-8",
        )


def test_gate_rejects_same_realm_before_seeding_any_solved_example(tmp_path, monkeypatch):
    seeded = _install_gate_fakes(monkeypatch)
    with pytest.raises(RuntimeError, match="must use distinct Runtime realms"):
        gate.run_a01_integration_gate(
            _Adapter("shared-realm"), _Adapter("shared-realm"), object(),
            media_root=tmp_path, attempt_id="adversarial-same-realm",
        )
    assert seeded == []


def test_wrong_shot_locator_rejects_shared_or_missing_picture_candidates():
    adapter = _Adapter()
    target = _target("negative")
    closure = adapter.read_current_closure("project", "timeline", head="head")
    closure["parent_revision"]["payload"]["occurrences"][1]["shot_revision_id"] = "rev-target"
    adapter.read_current_closure = lambda *args, **kwargs: closure
    with pytest.raises(RuntimeError, match="no uniquely pinned sibling picture clip"):
        gate._wrong_shot_locator(adapter, target)
