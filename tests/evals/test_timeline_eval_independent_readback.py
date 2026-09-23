from __future__ import annotations

from evals.timeline.independent_readback import read_target_snapshot
from evals.timeline.checks import run_checks


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


def test_readback_rejects_occurrence_pointing_at_different_shot():
    closure = _closure()
    closure["parent_revision"]["payload"]["occurrences"][0]["shot_id"] = "wrong-shot"
    try:
        read_target_snapshot(FakeAdapter(closure), _target())
    except Exception as exc:
        assert "different shot identity" in str(exc)
    else:  # pragma: no cover - assertion makes failure explicit
        raise AssertionError("readback accepted a locator pointing at the wrong shot")


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
