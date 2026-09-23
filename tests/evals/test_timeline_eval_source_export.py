from __future__ import annotations

import hashlib

from evals.timeline.fixture import MediaRequirement
from evals.timeline.a01_smoke import a01_opening_precondition, derive_a01_old_video_baseline
from evals.timeline.a02_a10_smoke import _preflight
from evals.timeline.runtime_adapter import RuntimeFixtureAdapter
from evals.timeline.source_export import _active_media_records, collect_active_media


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def test_media_collection_includes_closure_registry_references_and_paths():
    selected = _digest(b"selected")
    historical = _digest(b"historical")
    parent = {
        "payload": {
            "registry": {"assets": {
                "overlay": {"media_id": selected, "type": "image"},
                "old-output": {"media_id": historical, "type": "video"},
            }},
            "clips": [{"id": "frame", "asset": "overlay", "track": "frame"}],
        }
    }
    shot = {"revision_id": "shot-r1", "payload": {"items": [
        {"item_id": "caption", "media_id": selected, "metadata": {"role": "caption"}},
    ]}}
    internal = {"revision_id": "timeline-r1", "payload": {
        "registry": {"assets": {
            "active": {"content_sha256": selected.removeprefix("sha256:"), "type": "image"},
            "unused-history": {"media_id": historical, "type": "video"},
        }},
        "clips": [{"id": "picture", "asset": "active", "track": "picture"}],
    }}

    rows = collect_active_media(parent, [shot], [internal])

    by_digest = {row.digest: row for row in rows}
    assert set(by_digest) == {selected, historical}
    assert by_digest[selected].media_type == "image/png"
    assert set(by_digest[selected].required_by) >= {
        "parent:clips[0].asset", "shot:shot-r1:items[0]", "internal:timeline-r1:clips[0].asset",
    }
    assert any("unused-history" in path for path in by_digest[historical].required_by)


def test_active_media_records_resolves_typed_direct_clip_object():
    selected = _digest(b"audio")
    payload = {"clips": [{"id": "vo", "media_id": selected, "media_type": "audio/wav"}]}
    assert _active_media_records(payload, "shot:r1") == [
        (selected, "audio/wav", "shot:r1:clips[0].media_id"),
    ]


def test_export_source_handles_are_attempt_relative():
    requirement = MediaRequirement(
        digest=_digest(b"x"), source_object_id="sha256:x", media_type="image/png",
        required_by=("shot:r1:items[0]",), source_handle="media/abc",
    )
    assert not requirement.source_handle.startswith("/")
    assert ".." not in requirement.source_handle.split("/")


def test_a01_derivative_selects_old_video_and_keeps_charcoal_as_distinct_admitted_asset():
    from evals.timeline.fixture import Baseline

    parent = {"revision_id": "parent", "project_id": "p", "timeline_id": "t", "content_digest": _digest(b"p"), "payload": {
        "occurrences": [{"occurrence_id": "shot-ee383f695b10431c", "shot_id": "s", "shot_revision_id": "sr"}],
    }}
    shot = {"revision_id": "sr", "shot_id": "s", "internal_timeline_revision_id": "ir", "payload": {"internal_timeline_revision_id": "ir"}}
    internal = {"revision_id": "ir", "timeline_id": "t", "payload": {
        "clips": [{"id": "shot_b01", "asset": "charcoal_20260922_intro", "track": "picture"}],
        "registry": {"assets": {
            "h3_intro_revision_s01_16b8227b40f2": {"type": "video", "media_id": "sha256:16b8227b40f27df8d9a5e21d063a63b9f0f50d3994da0c8154fd83c85a784194"},
            "charcoal_20260922_intro": {"type": "image", "media_id": _digest(b"charcoal")},
        }},
    }}
    baseline = Baseline(1, "test", "61d1078d029e42a9af8540c0d5647ae3", "astrid-intro", "2652b5567c8e4e9aa4d35c1df0eb2742", "authoring-parent-revision-x", _digest(b"parent"), _digest(b"closure"), _digest(b"semantic"), {"numerator": 30, "denominator": 1}, {}, {"parent_revision": parent, "shot_revisions": [shot], "internal_timeline_revisions": [internal]}, ())

    derivative, disclosure = derive_a01_old_video_baseline(baseline)

    assert internal["payload"]["clips"][0]["asset"] == "charcoal_20260922_intro"  # input is untouched
    assert derivative.closure["internal_timeline_revisions"][0]["payload"]["clips"][0]["asset"] == "h3_intro_revision_s01_16b8227b40f2"
    assert disclosure["canonical_source_changed"] is False
    assert derivative.semantic_digest != baseline.semantic_digest


def test_media_ingest_idempotency_key_covers_all_request_metadata():
    class FakeWorkspace:
        def __init__(self):
            self.keys = []

        def ingest_project_object(self, project_id, data, *, media_type, filename, idempotency_key):
            self.keys.append(idempotency_key)
            return {"data": {"object_id": _digest(data)}}

        def get_project_object_location(self, project_id, object_id):
            return {"data": {"verified": True, "digest": object_id}}

    workspace = FakeWorkspace()
    adapter = object.__new__(RuntimeFixtureAdapter)
    adapter.workspace = workspace
    data = b"same bytes"
    digest = _digest(data)
    for media_type in ("image/png", "video/mp4"):
        requirement = MediaRequirement(digest, digest, media_type, (), "media/same-bytes")
        adapter.ensure_media_owned("project", requirement, data)

    assert workspace.keys[0] != workspace.keys[1]


def test_a01_precondition_resolves_remapped_occurrence_from_source_provenance():
    candidate = {
        "source_mapping": {"placements": {"runtime-occurrence": {
            "occurrence_id": "runtime-occurrence", "shot_id": "runtime-shot",
            "provenance": {"legacy_source": {"occurrence_id": "shot-ee383f695b10431c"}},
        }}},
        "shots": {"runtime-shot": {"internal_timeline": {
            "clips": [{"id": "picture", "asset": "old-video", "track": "picture", "clipType": "media"}],
            "registry": {"assets": {
                "old-video": {"type": "video", "media_id": _digest(b"old")},
                "charcoal_pixel_mink": {"type": "image", "media_id": _digest(b"new")},
            }},
        }}},
    }
    result = a01_opening_precondition(candidate, "shot-ee383f695b10431c")
    assert result["ready"] is True
    assert result["active_video_count"] == 1
    assert result["admitted_charcoal_image_alternative_count"] == 1


def test_a02_a10_preflight_blocks_without_case_fixture_contracts():
    from types import SimpleNamespace

    baseline = SimpleNamespace(
        source_head="pinned-parent-r1",
        media=(),
        closure={
            "parent_revision": {"payload": {"occurrences": [{"occurrence_id": "one"}], "clips": [{"track": "frame"}]}},
            "internal_timeline_revisions": [{"payload": {"clips": []}}],
            "shot_revisions": [],
        },
    )
    for number in range(2, 11):
        result = _preflight(f"A{number:02}", baseline)
        assert result["ready"] is False
        assert result["blockers"]
        assert result["hidden_checks"][-1]["passed"] is True
