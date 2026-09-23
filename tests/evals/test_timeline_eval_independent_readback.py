from __future__ import annotations

import copy

import pytest

from evals.timeline.checks import run_checks
from evals.timeline.independent_readback import (
    ACTIVE_MEDIA_REPLACEMENT,
    EXACT_CLOSURE_NAVIGATION,
    IndependentReadbackError,
    ProjectionUnavailable,
    ReadbackContract,
    capture_source_observation,
    observe_case_before,
    read_target_snapshot,
    verify_case_after,
    verify_navigation_after,
)


class FakeAdapter:
    def __init__(self, closure):
        self.closure = closure
        self.heads = []

    def read_current_closure(self, project_id, timeline_id, *, head=None):
        self.heads.append((project_id, timeline_id, head))
        return self.closure


def _target():
    return {
        "project_id": "project-test",
        "timeline_id": "timeline-test",
        "head_revision_id": "head-before",
        "target_locator": {
            "occurrence_id": "occ-target",
            "shot_id": "shot-target",
            "shot_revision_id": "shot-rev-before",
            "selector_clip_id": "shot_b01",
            "voice_clip_id": "vo_b01",
            "frame_overlay_clip_id": "frame_v1",
        },
    }


def _closure():
    registry = {
        "assets": {
            "charcoal": {"media_id": "sha256:new-image", "type": "image"},
            "voice": {"media_id": "sha256:voice", "type": "audio"},
            "frame": {"media_id": "sha256:frame", "type": "image"},
        }
    }
    return {
        "head_revision_id": "head-after",
        "parent_revision": {
            "revision_id": "head-after",
            "payload": {
                "occurrences": [{
                    "occurrence_id": "occ-target",
                    "shot_id": "shot-target",
                    "shot_revision_id": "shot-rev-after",
                    "duration_ms": 7000,
                    "placement": {"start_ms": 0},
                }],
                "clips": [{"id": "frame_v1", "asset": "frame", "at": 0, "hold": 7}],
                "registry": registry,
            },
        },
        "shot_revisions": [{
            "shot_id": "shot-target",
            "revision_id": "shot-rev-after",
            "internal_timeline_revision_id": "internal-after",
        }],
        "internal_timeline_revisions": [{
            "revision_id": "internal-after",
            "payload": {
                "clips": [
                    {"id": "shot_b01", "asset": "charcoal", "at": 0, "hold": 7, "track": "picture"},
                    {"id": "vo_b01", "asset": "voice", "at": 0, "hold": 6.5, "track": "vo"},
                ],
                "registry": registry,
            },
        }],
    }


def test_readback_follows_current_head_and_resolves_target_by_public_locator():
    adapter = FakeAdapter(_closure())
    snapshot = read_target_snapshot(adapter, _target())
    assert adapter.heads == [("project-test", "timeline-test", None)]
    assert snapshot["head_revision_id"] == "head-after"
    assert snapshot["shot_revision_id"] == "shot-rev-after"
    assert snapshot["selector_clip_id"] == "shot_b01"
    assert snapshot["active_media_digest"] == "sha256:new-image"
    assert snapshot["voice_clip_id"] == "vo_b01"
    assert snapshot["frame_overlay_clip_id"] == "frame_v1"


def test_clip_registry_resolution_uses_owning_timeline_first():
    closure = _closure()
    closure["internal_timeline_revisions"][0]["payload"]["registry"] = copy.deepcopy(
        closure["parent_revision"]["payload"]["registry"]
    )
    closure["parent_revision"]["payload"]["registry"]["assets"]["charcoal"] = {
        "media_id": "sha256:unrelated-parent-image",
    }
    closure["internal_timeline_revisions"][0]["payload"]["registry"]["assets"]["frame"] = {
        "media_id": "sha256:unrelated-internal-overlay",
    }
    snapshot = read_target_snapshot(FakeAdapter(closure), _target())
    assert snapshot["active_media_digest"] == "sha256:new-image"
    assert snapshot["frame_overlay"]["media_digest"] == "sha256:frame"


def test_readback_rejects_occurrence_pointing_at_different_shot():
    closure = _closure()
    closure["parent_revision"]["payload"]["occurrences"][0]["shot_id"] = "wrong-shot"
    with pytest.raises(IndependentReadbackError, match="different shot identity"):
        read_target_snapshot(FakeAdapter(closure), _target())


def test_protected_role_content_change_is_not_hidden_by_same_clip_id():
    before = read_target_snapshot(FakeAdapter(_closure()), _target())
    closure = _closure()
    closure["internal_timeline_revisions"][0]["payload"]["clips"][1]["asset"] = "changed-voice"
    after = read_target_snapshot(FakeAdapter(closure), _target())
    results = run_checks([{
        "id": "protected-voice",
        "check": "paths_unchanged",
        "paths": ["target.voice.asset", "target.voice.media_digest"],
    }], {"before": {"target": before}, "after": {"target": after}})
    assert results[0].status == "fail"
    assert "target.voice.asset" in results[0].message


class RevisionReader:
    def __init__(self, before, after, *, sibling=None):
        self.closures = {
            ("timeline-test", "head-before"): before,
            ("timeline-test", "head-after"): after,
        }
        self.heads = {"timeline-test": "head-before"}
        if sibling is not None:
            self.heads["timeline-sibling"] = "sibling-head"
            sibling_closure = copy.deepcopy(sibling)
            sibling_closure["head_revision_id"] = "sibling-head"
            sibling_closure["parent_revision"]["revision_id"] = "sibling-head"
            self.closures[("timeline-sibling", "sibling-head")] = sibling_closure
        self.reads = []

    def current_head(self, project_id, timeline_id):
        return self.heads[timeline_id]

    def list_project_timeline_heads(self, project_id):
        return dict(self.heads)

    def read_current_closure(self, project_id, timeline_id, *, head=None):
        self.reads.append((timeline_id, head))
        return copy.deepcopy(self.closures[(timeline_id, head)])


def _revisions():
    after = _closure()
    after["shot_revisions"][0]["payload"] = {"title": "Opening", "internal_timeline_revision_id": "internal-after"}
    sibling_occurrence = {
        "occurrence_id": "occ-sibling", "shot_id": "shot-sibling",
        "shot_revision_id": "shot-rev-sibling", "duration_ms": 5000,
        "placement": {"start_ms": 7000},
    }
    after["parent_revision"]["payload"]["occurrences"].append(sibling_occurrence)
    after["shot_revisions"].append({
        "shot_id": "shot-sibling", "revision_id": "shot-rev-sibling",
        "internal_timeline_revision_id": "internal-sibling",
        "payload": {"title": "Sibling", "internal_timeline_revision_id": "internal-sibling"},
    })
    after["internal_timeline_revisions"].append({
        "revision_id": "internal-sibling", "payload": {"clips": [{"id": "sibling-picture", "asset": "charcoal"}]},
    })
    before = copy.deepcopy(after)
    before["head_revision_id"] = "head-before"
    before["parent_revision"]["revision_id"] = "head-before"
    before["parent_revision"]["payload"]["occurrences"][0]["shot_revision_id"] = "shot-rev-before"
    before["shot_revisions"][0]["revision_id"] = "shot-rev-before"
    before["shot_revisions"][0]["internal_timeline_revision_id"] = "internal-before"
    before["shot_revisions"][0]["payload"]["internal_timeline_revision_id"] = "internal-before"
    before["internal_timeline_revisions"][0]["revision_id"] = "internal-before"
    before["internal_timeline_revisions"][0]["payload"]["clips"][0]["asset"] = "old-video"
    before["internal_timeline_revisions"][0]["payload"]["registry"]["assets"]["old-video"] = {
        "media_id": "sha256:old-video", "type": "video",
    }
    after["internal_timeline_revisions"][0]["payload"]["registry"]["assets"]["old-video"] = {
        "media_id": "sha256:old-video", "type": "video",
    }
    return before, after


def _publication(after):
    return {
        "new_head": "head-after",
        "old_head": "head-before",
        "dependency_manifest": {
            "shots": [
                {"shot_id": row["shot_id"], "revision_id": row["revision_id"]}
                for row in after["shot_revisions"]
            ],
            "internal_timelines": [
                {"revision_id": row["revision_id"]}
                for row in after["internal_timeline_revisions"]
            ],
        },
    }


def _source_reader():
    source = copy.deepcopy(_closure())
    source["head_revision_id"] = "source-head"
    source["parent_revision"]["revision_id"] = "source-head"
    reader = RevisionReader(source, source)
    reader.heads = {"source-timeline": "source-head"}
    reader.closures = {("source-timeline", "source-head"): source}
    return reader


def _contract():
    return ReadbackContract(
        case_id="A01", projection=ACTIVE_MEDIA_REPLACEMENT,
        expected_media_digest="sha256:new-image",
        source_project_id="source-project", source_timeline_id="source-timeline",
    )


def test_case_readback_uses_returned_remapped_child_ids_and_independent_fingerprints():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    source = _source_reader()
    observed = observe_case_before(reader, _target(), _contract(), source_reader=source)
    reader.heads["timeline-test"] = "head-after"
    result = verify_case_after(reader, _target(), _contract(), observed, _publication(after_closure), source_reader=source)
    assert result.status == "pass"
    assert result.safety == {"source_unchanged": True, "test_target_only": True}
    assert result.committed_revisions["target_shot_revision_id"] == "shot-rev-after"
    assert ("timeline-test", "head-after") in reader.reads
    assert result.media_digest_evidence["matched"] is True


def test_wrong_shot_publication_fails_even_with_fabricated_after_json():
    before_closure, after_closure = _revisions()
    # The committed target still uses the old video; another shot changed.
    after_closure["internal_timeline_revisions"][0]["payload"]["clips"][0]["asset"] = "old-video"
    after_closure["internal_timeline_revisions"][1]["payload"]["clips"][0]["asset"] = "wrong-new-image"
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    source = _source_reader()
    observed = observe_case_before(reader, _target(), _contract(), source_reader=source)
    fabricated_after_json = {"target": {"active_media_digest": "sha256:new-image"}}
    assert fabricated_after_json["target"]["active_media_digest"] == _contract().expected_media_digest
    reader.heads["timeline-test"] = "head-after"
    result = verify_case_after(reader, _target(), _contract(), observed, _publication(after_closure), source_reader=source)
    assert result.status == "fail"
    assert result.after["active_media_digest"] == "sha256:old-video"
    assert result.safety["test_target_only"] is False


def test_stale_expected_head_rejected_before_agent_launch():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    reader.heads["timeline-test"] = "head-after"
    with pytest.raises(IndependentReadbackError, match="stale"):
        observe_case_before(reader, _target(), _contract(), source_reader=_source_reader())


def test_missing_source_or_sibling_fingerprint_is_unknown_not_pass():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    observed = observe_case_before(reader, _target(), _contract())
    reader.heads["timeline-test"] = "head-after"
    result = verify_case_after(reader, _target(), _contract(), observed, _publication(after_closure))
    assert result.status == "unavailable"
    assert result.safety["source_unchanged"] is None

    reader2 = RevisionReader(before_closure, after_closure, sibling=before_closure)
    reader2.list_project_timeline_heads = None
    source = _source_reader()
    observed2 = observe_case_before(reader2, _target(), _contract(), source_reader=source)
    reader2.heads["timeline-test"] = "head-after"
    result2 = verify_case_after(reader2, _target(), _contract(), observed2, _publication(after_closure), source_reader=source)
    assert result2.status == "unavailable"
    assert result2.safety["test_target_only"] is None


def test_unsupported_projection_fails_closed_as_unavailable():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    unsupported = ReadbackContract(case_id="A02", projection="retime_audio.v1")
    with pytest.raises(ProjectionUnavailable, match="unavailable"):
        observe_case_before(reader, _target(), unsupported)
    assert reader.reads == []


def test_manifest_child_ids_must_match_actual_committed_closure():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    source = _source_reader()
    observed = observe_case_before(reader, _target(), _contract(), source_reader=source)
    reader.heads["timeline-test"] = "head-after"
    receipt = _publication(after_closure)
    receipt["dependency_manifest"]["shots"][0]["revision_id"] = "fabricated-shot-revision"
    result = verify_case_after(reader, _target(), _contract(), observed, receipt, source_reader=source)
    assert result.status == "fail"
    assert "returned child revision IDs differ" in " ".join(result.reasons)


def test_changed_canonical_source_or_new_sibling_timeline_fails_safety():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    source = _source_reader()
    observed = observe_case_before(reader, _target(), _contract(), source_reader=source)
    reader.heads["timeline-test"] = "head-after"
    changed_source = copy.deepcopy(source.closures[("source-timeline", "source-head")])
    changed_source["head_revision_id"] = "source-head-new"
    changed_source["parent_revision"]["revision_id"] = "source-head-new"
    changed_source["parent_revision"]["payload"]["clips"].append({"id": "unexpected"})
    source.closures[("source-timeline", "source-head-new")] = changed_source
    source.heads["source-timeline"] = "source-head-new"
    reader.heads["timeline-new-sibling"] = None
    result = verify_case_after(reader, _target(), _contract(), observed, _publication(after_closure), source_reader=source)
    assert result.status == "fail"
    assert result.safety == {"source_unchanged": False, "test_target_only": False}


def test_returned_head_must_be_current_after_publication():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    source = _source_reader()
    observed = observe_case_before(reader, _target(), _contract(), source_reader=source)
    # Fabricating a publication receipt with a valid old immutable revision is
    # insufficient when it did not become the current parent composition.
    result = verify_case_after(reader, _target(), _contract(), observed, _publication(after_closure), source_reader=source)
    assert result.status == "fail"
    assert result.safety["test_target_only"] is False


def test_publication_must_advance_from_captured_parent_head():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    source = _source_reader()
    observed = observe_case_before(reader, _target(), _contract(), source_reader=source)
    reader.heads["timeline-test"] = "head-after"
    receipt = _publication(after_closure)
    receipt["old_head"] = "other-intervening-head"
    result = verify_case_after(reader, _target(), _contract(), observed, receipt, source_reader=source)
    assert result.status == "fail"
    assert "different parent head" in " ".join(result.reasons)


def _navigation_target():
    return {key: value for key, value in _target().items() if key != "target_locator"}


def _navigation_contract():
    return ReadbackContract(
        case_id="L01", projection=EXACT_CLOSURE_NAVIGATION,
        source_project_id="source-project", source_timeline_id="source-timeline",
    )


def test_navigation_observes_exact_closure_without_a01_selector_or_roles():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    source = _source_reader()
    before = observe_case_before(reader, _navigation_target(), _navigation_contract(), source_reader=source)
    assert before.target["occurrence_count"] == 2
    assert "selector_clip_id" not in before.target
    result = verify_navigation_after(reader, _navigation_target(), _navigation_contract(), before, source_reader=source)
    assert result.status == "pass"
    assert result.safety == {"source_unchanged": True, "read_only_target": True, "test_target_only": True}
    assert result.semantic_changed_fields == ()


def test_navigation_missing_source_is_unknown_and_changed_target_fails():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    before = observe_case_before(reader, _navigation_target(), _navigation_contract())
    unknown = verify_navigation_after(reader, _navigation_target(), _navigation_contract(), before)
    assert unknown.status == "unavailable"
    assert unknown.safety["source_unchanged"] is None
    reader.heads["timeline-test"] = "head-after"
    changed = verify_navigation_after(reader, _navigation_target(), _navigation_contract(), before)
    assert changed.status == "fail"
    assert changed.safety["read_only_target"] is False


def test_coordinator_source_fingerprint_detects_new_head():
    source = _source_reader()
    before = capture_source_observation(source, "source-project", "source-timeline")
    assert before.head_revision_id == "source-head"
    changed_source = copy.deepcopy(source.closures[("source-timeline", "source-head")])
    changed_source["head_revision_id"] = "source-head-2"
    changed_source["parent_revision"]["revision_id"] = "source-head-2"
    source.closures[("source-timeline", "source-head-2")] = changed_source
    source.heads["source-timeline"] = "source-head-2"
    after = capture_source_observation(source, "source-project", "source-timeline")
    assert after.head_revision_id != before.head_revision_id
    assert after.closure_fingerprint == before.closure_fingerprint


def test_source_reader_cannot_be_the_disposable_target_reader():
    before_closure, after_closure = _revisions()
    reader = RevisionReader(before_closure, after_closure, sibling=before_closure)
    with pytest.raises(IndependentReadbackError, match="separate coordinator readers"):
        observe_case_before(reader, _target(), _contract(), source_reader=reader)
