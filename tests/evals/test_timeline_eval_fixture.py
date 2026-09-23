from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from evals.timeline.fixture import (
    ACTION_CASES,
    EXPECTED_SOURCE_HEAD,
    SOURCE_PROJECT_ID,
    SOURCE_PROJECT_SLUG,
    SOURCE_TIMELINE_ID,
    Baseline,
    DisposableEndpoint,
    FixtureError,
    MediaRequirement,
    derive_case_identities,
    export_baseline,
    idempotency_key,
    materialize_public_navigation_entrypoint,
    public_target_receipt,
    reset_case,
    seed_case,
)
from evals.timeline.fixture_manifest import DEFAULT_FIXTURE_ROOT

MEDIA_BYTES = b"fixture-image-bytes-v1"
MEDIA_DIGEST = "sha256:" + sha256(MEDIA_BYTES).hexdigest()


def _baseline() -> Baseline:
    parent = {
        "project_id": SOURCE_PROJECT_ID,
        "timeline_id": SOURCE_TIMELINE_ID,
        "revision_id": EXPECTED_SOURCE_HEAD,
        "content_digest": "sha256:" + "1" * 64,
        "payload": {"occurrences": [{"occurrence_id": "occ-1", "shot_id": "shot-1", "shot_revision_id": "shot-r1"}]},
    }
    shot = {
        "project_id": SOURCE_PROJECT_ID,
        "shot_id": "shot-1",
        "revision_id": "shot-r1",
        "internal_timeline_revision_id": "internal-r1",
        "content_digest": "sha256:" + "2" * 64,
        "payload": {"items": [{"item_id": "item-1", "text": "leave opaque IDs in prose"}]},
    }
    internal = {
        "project_id": SOURCE_PROJECT_ID,
        "timeline_id": "internal-1",
        "revision_id": "internal-r1",
        "content_digest": "sha256:" + "3" * 64,
        "payload": {"clips": [{"clip_id": "clip-1", "asset": "charcoal"}], "registry": {}},
    }
    return export_baseline(
        project_id=SOURCE_PROJECT_ID,
        project_slug=SOURCE_PROJECT_SLUG,
        timeline_id=SOURCE_TIMELINE_ID,
        observed_head=EXPECTED_SOURCE_HEAD,
        parent_revision=parent,
        shot_revisions=[shot],
        internal_timeline_revisions=[internal],
        media=[MediaRequirement(MEDIA_DIGEST, "source-object", "image/png", ("A01",), "media/image.bin")],
        frame_rate={"numerator": 30, "denominator": 1},
        source_hashes={"Astrid/astrid/core/timeline/authoring_bundle.py": "sha256:" + "b" * 64},
    )


class FakeRuntime:
    endpoint = DisposableEndpoint(
        "http://127.0.0.1:9000", "realm-test-1", "credential:test-only", "timeline-eval-disposable-realm"
    )

    def __init__(self, baseline: Baseline):
        self.baseline = baseline
        self.semantic = {}
        self.head = {}
        self.published = []
        self.seed_requests = []
        self.create_project_calls = 0
        self.project_id = "runtime-project-1"

    def create_suite_project(self, project_alias, *, idempotency_key):
        self.create_project_calls += 1
        return {"data": {"project_id": self.project_id, "slug": project_alias}}

    def create_case_timeline(self, project_id, timeline_alias, *, idempotency_key):
        return {"data": {"timeline_id": timeline_alias}}

    def ensure_media_owned(self, project_id, requirement, media_bytes):
        assert sha256(media_bytes).hexdigest() == requirement.digest.removeprefix("sha256:")
        return {"project_id": project_id, "digest": requirement.digest, "object_id": "dest-" + requirement.digest[-8:]}

    def seed_case(self, project_id, identities, baseline, owned_media, *, idempotency_key):
        self.seed_requests.append((project_id, identities, dict(owned_media), idempotency_key))
        self.semantic[identities.timeline_id] = baseline.semantic_digest
        self.head[identities.timeline_id] = identities.parent_revision_id
        return {"project_id": project_id, "timeline_id": identities.timeline_id,
                "new_head": identities.parent_revision_id, "semantic_digest": baseline.semantic_digest}

    def read_case_semantic_digest(self, project_id, timeline_id):
        return self.semantic[timeline_id]

    def current_head(self, project_id, timeline_id):
        return self.head.get(timeline_id, "")

    def publish_baseline(self, project_id, timeline_id, baseline, *, expected_head, idempotency_key):
        assert self.head[timeline_id] == expected_head
        self.published.append((project_id, timeline_id, expected_head, idempotency_key))
        next_head = "reset-" + str(len(self.published))
        self.head[timeline_id] = next_head
        self.semantic[timeline_id] = baseline.semantic_digest
        return {"new_head": next_head}


def test_export_pins_source_head_closure_media_fps_and_hashes():
    baseline = _baseline()
    record = baseline.as_dict()
    assert baseline.source_head == EXPECTED_SOURCE_HEAD
    assert record["source"]["parent_content_digest"].startswith("sha256:")
    assert record["frame_rate"] == {"numerator": 30, "denominator": 1}
    assert record["media"][0]["ownership"] == "must_be_ingested_or_verified_in_destination_project"
    assert baseline.semantic_digest == _baseline().semantic_digest


def test_export_refuses_changed_head_instead_of_silently_rebasing():
    parent = {"project_id": SOURCE_PROJECT_ID, "timeline_id": SOURCE_TIMELINE_ID, "revision_id": "new-head", "content_digest": "sha256:" + "1" * 64, "payload": {"occurrences": []}}
    with pytest.raises(FixtureError, match="refusing to silently rebase"):
        export_baseline(
            project_id=SOURCE_PROJECT_ID, project_slug=SOURCE_PROJECT_SLUG,
            timeline_id=SOURCE_TIMELINE_ID, observed_head="new-head", parent_revision=parent,
            shot_revisions=[{"revision_id": "s", "payload": {}}],
            internal_timeline_revisions=[{"revision_id": "i", "payload": {}}], media=[],
            frame_rate={"numerator": 30, "denominator": 1}, source_hashes={"x": "sha256:x"},
        )


def test_case_identities_are_repeatable_and_disjoint_across_all_ten_cases():
    baseline = _baseline()
    first = {case: derive_case_identities(baseline, attempt_id="attempt-1", case_id=case, runtime_project_id="runtime-project", runtime_timeline_id="timeline-" + case) for case in ACTION_CASES}
    second = {case: derive_case_identities(baseline, attempt_id="attempt-1", case_id=case, runtime_project_id="runtime-project", runtime_timeline_id="timeline-" + case) for case in ACTION_CASES}
    assert first == second
    for left in ACTION_CASES:
        for right in ACTION_CASES:
            if left != right:
                assert first[left].all_child_ids().isdisjoint(first[right].all_child_ids())
                assert first[left].project_alias == first[right].project_alias
                assert first[left].project_id == first[right].project_id == "runtime-project"
                assert first[left].timeline_alias != first[right].timeline_alias
                assert first[left].timeline_id != first[right].timeline_id


def test_idempotency_key_binds_operation_case_attempt_and_request_digest():
    base = {"op": "move", "start_ms": 900}
    key = idempotency_key(attempt_id="attempt-1", case_id="A03", operation="publish", request=base)
    assert key == idempotency_key(attempt_id="attempt-1", case_id="A03", operation="publish", request=deepcopy(base))
    assert key != idempotency_key(attempt_id="attempt-1", case_id="A03", operation="publish", request={"op": "move", "start_ms": 901})
    assert key != idempotency_key(attempt_id="attempt-2", case_id="A03", operation="publish", request=base)


def test_seed_uses_server_ids_and_destination_media_ownership(tmp_path):
    baseline = _baseline()
    runtime = FakeRuntime(baseline)
    media_root = tmp_path / "attempt-media"
    (media_root / "media").mkdir(parents=True)
    (media_root / "media/image.bin").write_bytes(MEDIA_BYTES)
    result = seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A01", media_root=media_root)
    assert result["receipt"]["semantic_digest"] == baseline.semantic_digest
    assert result["project_id"] == runtime.project_id
    assert result["timeline_id"] == result["identities"].timeline_id
    assert result["owned_media"][baseline.media[0].digest].startswith("dest-")
    replay = seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A01", media_root=media_root)
    assert replay["idempotency_key"] == result["idempotency_key"]


def test_public_target_receipt_contains_only_disposable_ids(tmp_path):
    baseline = _baseline()
    runtime = FakeRuntime(baseline)
    media_root = tmp_path / "attempt-media"
    (media_root / "media").mkdir(parents=True)
    (media_root / "media/image.bin").write_bytes(MEDIA_BYTES)
    seed = seed_case(runtime, baseline, attempt_id="attempt-public", case_id="A01", media_root=media_root)
    seed["target_locator"] = {
        "occurrence_id": "runtime-occurrence",
        "selector_clip_id": "shot_b01",
        "replacement_asset_key": "charcoal_20260922_intro",
    }
    target = public_target_receipt(seed)
    assert target["kind"] == "astrid.timeline-eval.public-target.v1"
    assert target["endpoint"] == runtime.endpoint.url
    assert target["project_id"] == runtime.project_id
    assert target["timeline_id"] == seed["timeline_id"]
    assert target["head_revision_id"] == seed["identities"].parent_revision_id
    assert "closure" not in target
    assert "semantic_digest" not in target
    assert target["owned_media_ids"] == ["dest-" + MEDIA_DIGEST[-8:]]
    assert target["capabilities"]["edit"]["status"] == "available"
    assert target["edit_route"] == "timelines replace-parent-media"


def test_public_target_receipt_does_not_advertise_a01_route_for_other_cases(tmp_path):
    baseline = _baseline()
    runtime = FakeRuntime(baseline)
    media_root = tmp_path / "attempt-media"
    (media_root / "media").mkdir(parents=True)
    (media_root / "media/image.bin").write_bytes(MEDIA_BYTES)
    seed = seed_case(runtime, baseline, attempt_id="attempt-public", case_id="A02", media_root=media_root)
    target = public_target_receipt(seed)
    assert target["case_id"] == "A02"
    assert target["capabilities"]["edit"]["status"] == "unavailable"
    assert "edit_route" not in target


def test_offline_navigation_entrypoint_materializes_only_selected_case_and_receipt(tmp_path):
    destination = tmp_path / "case-L03"
    destination.mkdir()
    entrypoint = materialize_public_navigation_entrypoint(
        "L03", fixture_root=DEFAULT_FIXTURE_ROOT, destination=destination,
    )
    assert entrypoint["kind"] == "astrid.timeline-eval.offline-navigation-entry.v1"
    assert entrypoint["read_only"] is True
    assert entrypoint["target_receipt"]["kind"] == "astrid.timeline-eval.offline-navigation-target.v1"
    assert entrypoint["target_receipt"]["offline_only"] is True
    assert entrypoint["target_receipt"]["readback_projection"] == "exact_closure_navigation.v1"
    assert set(entrypoint["targets"]) == {"intro_b01", "ideas_b02", "ideas_b03", "closing_sign"}
    assert entrypoint["related_inputs"]["music_cue_times_seconds"]
    for media_id, relative in entrypoint["media"].items():
        media_path = destination / "entrypoint" / relative
        assert media_path.is_file()
        assert "sha256:" + sha256(media_path.read_bytes()).hexdigest() == media_id
    with pytest.raises(FixtureError, match="must be new and empty"):
        materialize_public_navigation_entrypoint(
            "L03", fixture_root=DEFAULT_FIXTURE_ROOT, destination=destination,
        )


def test_cases_share_runtime_project_but_keep_distinct_runtime_timeline_ids(tmp_path):
    baseline = _baseline()
    runtime = FakeRuntime(baseline)
    media_root = tmp_path / "attempt-media"
    (media_root / "media").mkdir(parents=True)
    (media_root / "media/image.bin").write_bytes(MEDIA_BYTES)
    first = seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A01", media_root=media_root)
    second = seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A02", media_root=media_root)
    assert first["project_id"] == second["project_id"] == runtime.project_id
    assert first["project_idempotency_key"] == second["project_idempotency_key"]
    assert first["timeline_id"] != second["timeline_id"]
    assert first["timeline_alias"] != second["timeline_alias"]


def test_seed_refuses_unconfigured_endpoint_and_bad_media_ownership(tmp_path):
    baseline = _baseline()
    runtime = FakeRuntime(baseline)
    runtime.endpoint = None
    with pytest.raises(FixtureError, match="explicit disposable Runtime endpoint"):
        seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A01", media_root=tmp_path)

    runtime.endpoint = FakeRuntime.endpoint
    media_root = tmp_path / "media-root"
    (media_root / "media").mkdir(parents=True)
    (media_root / "media/image.bin").write_bytes(MEDIA_BYTES)
    runtime.ensure_media_owned = lambda *_: {"project_id": "wrong", "digest": baseline.media[0].digest, "object_id": "x"}
    with pytest.raises(FixtureError, match="not verified as owned"):
        seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A01", media_root=media_root)


def test_missing_or_corrupt_attempt_media_fails_before_any_runtime_write(tmp_path):
    baseline = _baseline()
    runtime = FakeRuntime(baseline)
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    with pytest.raises(FixtureError, match="missing from attempt media"):
        seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A01", media_root=missing_root)
    assert runtime.create_project_calls == 0

    corrupt_root = tmp_path / "corrupt"
    (corrupt_root / "media").mkdir(parents=True)
    (corrupt_root / "media/image.bin").write_bytes(b"wrong")
    with pytest.raises(FixtureError, match="do not match declared digest"):
        seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A01", media_root=corrupt_root)
    assert runtime.create_project_calls == 0


def test_reset_publishes_baseline_as_new_head_and_preserves_history_semantics(tmp_path):
    baseline = _baseline()
    runtime = FakeRuntime(baseline)
    media_root = tmp_path / "media-root"
    (media_root / "media").mkdir(parents=True)
    (media_root / "media/image.bin").write_bytes(MEDIA_BYTES)
    seeded = seed_case(runtime, baseline, attempt_id="attempt-1", case_id="A05", media_root=media_root)
    ids = seeded["identities"]
    runtime.head[ids.timeline_id] = "edited-head"
    runtime.semantic[ids.timeline_id] = "sha256:" + "f" * 64
    result = reset_case(runtime, baseline, attempt_id="attempt-1", case_id="A05", project_id=seeded["project_id"], timeline_id=seeded["timeline_id"])
    assert result["new_head"] != "edited-head"
    assert result["semantic_digest"] == baseline.semantic_digest
    assert runtime.published[0][2] == "edited-head"
    assert result["idempotency_key"]
