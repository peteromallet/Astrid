from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from astrid.core.timeline.shot_composition_projection import project_runtime_parent_composition
from astrid.packs.rendering.executors.render.managed_timeline import (
    ManagedRenderSnapshot,
    _render_compatible_projection,
    validate_managed_render_snapshot,
)
from evals.timeline.a01_smoke import OLD_OPENING_VIDEO_ASSET, load_baseline
from evals.timeline.fixture_preparation import (
    _case_baseline,
    build_preparation_table,
    inspect_action_sidecars,
    materialize_action_sidecar_inputs,
    materialize_action_target_receipts,
    prepare_case,
    prepare_public_case,
    render_case_brief,
    write_preparation_table,
)

ROOT = Path(__file__).resolve().parents[3]
SUITE = ROOT / "Astrid/evals/timeline/suite.json"
FIXTURES = ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"
UNBLOCKED = ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures-unblock-20260924"


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
        "scope": "selected-case-only",
        "read_only": False,
        "occurrence_ids": ["occ-1"],
        "shot_ids": ["shot-1"],
        "shot_revision_ids": ["shot-rev-1"],
        "internal_revision_ids": ["internal-1"],
        "owned_media_ids": ["sha256:old", "sha256:new"],
        "capabilities": {"edit": {"status": "available", "route": "timelines replace-parent-media"}},
        "target_locator": {
            "readback_projection": "active_media_replacement.v1", "occurrence_id": "occ-1",
            "shot_id": "shot-1", "shot_revision_id": "shot-rev-1", "selector_clip_id": "picture-1",
            "voice_clip_id": "voice-1", "frame_overlay_clip_id": "overlay-1",
            "replacement_asset_key": "new-image", "preserve_roles": ["timing", "voiceover", "frame-overlay"],
        },
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
    assert "edit route disagrees" in rows["A02"]["reason"]
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


def test_live_navigation_preparation_renders_runtime_brief(tmp_path: Path, monkeypatch) -> None:
    from contextlib import contextmanager
    from evals.timeline import fixture, runtime_adapter
    from evals.timeline.a01_smoke import load_baseline
    from evals.timeline.fixture import derive_case_identities

    project_id, timeline_id = "runtime-project-live", "runtime-timeline-live"
    baseline = load_baseline(UNBLOCKED.parent / "attempts" / "e05-a01" / "source" / "baseline.json")
    identities = derive_case_identities(
        baseline, attempt_id="test-L10", case_id="A01",
        runtime_project_id=project_id, runtime_timeline_id=timeline_id,
    )

    class Adapter:
        isolation = SimpleNamespace(credential_file=tmp_path / "credential.token")

        def current_head(self, project, timeline):
            return identities.parent_revision_id

        def list_project_timeline_heads(self, project):
            return {timeline_id: identities.parent_revision_id}

        def read_current_semantic_digest(self, project, timeline):
            return baseline.semantic_digest

        def read_current_closure(self, project, timeline, *, head=None):
            return {"project_id": project, "timeline_id": timeline, "head_revision_id": head}

    adapter = Adapter()

    @contextmanager
    def fake_runtime(**kwargs):
        yield SimpleNamespace(
            adapter=adapter, endpoint="http://127.0.0.1:45678", realm_id="runtime-realm-live",
            root=tmp_path / "runtime", contract_path=tmp_path / "contract.json",
        )

    def fake_seed(*args, **kwargs):
        return {
            "endpoint_url": "http://127.0.0.1:45678", "endpoint_realm_id": "runtime-realm-live",
            "project_id": project_id, "timeline_id": timeline_id, "identities": identities,
            "owned_media": {row.digest: "owned-" + row.digest[-8:] for row in baseline.media},
            "target_locator": None, "receipt": {"new_head": identities.parent_revision_id},
        }

    monkeypatch.setattr(runtime_adapter, "local_disposable_runtime", fake_runtime)
    monkeypatch.setattr(fixture, "seed_case", fake_seed)
    (tmp_path / "canonical").mkdir()
    prepared = prepare_case(
        "L10", case_root=tmp_path / "work" / "project", fixture_root=UNBLOCKED,
        canonical_endpoint="http://127.0.0.1:1", canonical_realm_id="sentinel",
        canonical_root=tmp_path / "canonical",
    )
    try:
        brief = render_case_brief("L10", prepared=prepared)
        assert prepared.kind == "action"
        assert prepared.project_id == project_id
        assert prepared.realm_id == "runtime-realm-live"
        assert prepared.endpoint == "http://127.0.0.1:45678"
        assert "play its voice" in brief
        assert "timelines.open_composition" in brief
        assert "ASTRID_TIMELINE_EVAL_CREDENTIAL" in brief
        assert "offline entrypoint" in brief
        assert brief.count("Documentation:") == 1
        assert "What is the capital" not in brief
        assert "Write exactly one JSON object to `result.json` in your current working" in brief
        assert "`status`, `answer`, and `evidence`" in brief
        assert "Make no unsupported claims" in brief
        before = prepared.baseline_observer()
        assert before["project_id"] == project_id
        assert before["timeline_id"] == timeline_id
    finally:
        prepared.close()


def test_action_brief_paths_are_relative_to_omp_working_directory(tmp_path: Path) -> None:
    project = tmp_path / "work" / "project"
    project.mkdir(parents=True)
    (project / "task-inputs.json").write_text(json.dumps({
        "task_inputs": {"targets": {}, "timing": {}}, "assets": [],
    }), encoding="utf-8")
    prepared = SimpleNamespace(project_dir=project, project_id="p", timeline_id="t")
    expected = {
        "A04": "project/media/alternate-image",
        "A05": "project/public-sidecars/A05/A05-vo-endpoints.json",
        "A06": "project/public-sidecars/A06/A06-text-roles.json",
        "A09": "project/public-sidecars/A09/A09-images.json",
        "A10": "project/sidecars/A10/A10-images/",
    }
    for case_id, path in expected.items():
        assert path in render_case_brief(case_id, prepared=prepared)


def test_case_derivatives_match_brief_starting_conditions() -> None:
    baseline_path = FIXTURES.parent / "attempts" / "e05-a01" / "source" / "baseline.json"
    baseline = load_baseline(baseline_path)
    a01, _ = _case_baseline("A01", baseline, FIXTURES)
    opening = next(row for row in a01.closure["parent_revision"]["payload"]["occurrences"]
                   if row["occurrence_id"] == "shot-ee383f695b10431c")
    shot = next(row for row in a01.closure["shot_revisions"] if row["revision_id"] == opening["shot_revision_id"])
    internal = next(row for row in a01.closure["internal_timeline_revisions"]
                    if row["revision_id"] == shot["internal_timeline_revision_id"])
    assert next(row for row in internal["payload"]["clips"] if row["id"] == "shot_b01")["asset"] == OLD_OPENING_VIDEO_ASSET

    for case_id in ("A02", "A05", "A07"):
        derived, extra = _case_baseline(case_id, baseline, FIXTURES)
        parent = derived.closure["parent_revision"]["payload"]
        music_clip = next(row for row in parent["clips"] if row.get("id") == "eval_music_bed_clip")
        music_asset = parent["registry"]["assets"][music_clip["asset"]]
        assert music_clip["track"] == "music"
        assert any(row.get("id") == "music" and row.get("kind") == "audio"
                   for row in parent["config"]["tracks"])
        assert music_asset["origin"] == "opaque-foreign"
        assert music_asset["media_id"] in extra
        assert len(extra) == 1
    a06, _ = _case_baseline("A06", baseline, FIXTURES)
    title_internal = next(
        internal["payload"]
        for internal in a06.closure["internal_timeline_revisions"]
        if any(row.get("id") == "a06-visible-title" for row in internal["payload"].get("clips", []))
    )
    title = next(row for row in title_internal["clips"] if row.get("id") == "a06-visible-title")
    assert title["clipType"] == "text"
    assert title["text"] == {
        "content": "Astrid", "align": "center", "color": "#ffffff", "fontSize": 96,
    }
    assert "style" not in title
    assert any(row.get("id") == "titles" and row.get("kind") == "visual"
               for row in title_internal["tracks"])


def test_truthful_music_and_title_derivatives_pass_managed_render_validation() -> None:
    baseline_path = FIXTURES.parent / "attempts" / "e05-a01" / "source" / "baseline.json"
    baseline = load_baseline(baseline_path)

    for case_id in ("A02", "A05", "A06", "A07"):
        derived, _ = _case_baseline(case_id, baseline, FIXTURES)
        closure = derived.closure
        projected = project_runtime_parent_composition(
            closure["parent_revision"],
            shot_revisions=closure["shot_revisions"],
            internal_timeline_revisions=closure["internal_timeline_revisions"],
        )
        config, registry = _render_compatible_projection(projected.config, projected.registry)
        snapshot = ManagedRenderSnapshot(
            project_id="fixture-project", project_slug="fixture-project",
            timeline_id="fixture-timeline", timeline_ulid="fixture-timeline",
            timeline_slug=case_id, config_version=1, head_event_id="fixture-head",
            head_hash="0" * 64, config=config, registry=registry,
            config_hash="0" * 64, registry_hash="0" * 64,
            materialized_registry_hash="0" * 64,
        )

        validate_managed_render_snapshot(snapshot)

        track_ids = {row["id"] for row in config["tracks"]}
        if case_id == "A06":
            title = next(row for row in config["clips"] if row["id"].endswith(":a06-visible-title"))
            assert title["track"] == "titles"
            assert title["text"]["content"] == "Astrid"
            assert "titles" in track_ids
        else:
            music = next(row for row in config["clips"] if row["id"] == "eval_music_bed_clip")
            assert music["track"] == "music"
            assert music["asset"] in registry["assets"]
            assert "music" in track_ids


def test_a09_brief_uses_concrete_montage_occurrence(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    (project / "task-inputs.json").write_text(json.dumps({
        "task_inputs": {"targets": {"montage_occurrence": "occurrence-42"}, "timing": {}},
        "assets": [],
    }), encoding="utf-8")
    prepared = SimpleNamespace(project_dir=project, project_id="p", timeline_id="t")
    brief = render_case_brief("A09", prepared=prepared)
    assert "occurrence-42" in brief
    assert "{montage shot}" not in brief


def test_action_preparation_uses_server_target_ids_and_keeps_runtime_alive(tmp_path: Path, monkeypatch) -> None:
    from evals.timeline import fixture, runtime_adapter
    from evals.timeline.a01_smoke import load_baseline
    from evals.timeline.fixture import derive_case_identities

    closed = {"value": False}
    project_id, timeline_id = "runtime-project-123", "runtime-timeline-456"
    baseline_path = UNBLOCKED.parent / "attempts" / "e05-a01" / "source" / "baseline.json"
    baseline = load_baseline(baseline_path)
    identities = derive_case_identities(baseline, attempt_id="test", case_id="A01",
                                        runtime_project_id=project_id, runtime_timeline_id=timeline_id)

    class Adapter:
        isolation = SimpleNamespace(credential_file=tmp_path / "credential.token")
        proof = SimpleNamespace(realm_id="runtime-realm-789")

        def current_head(self, project, timeline):
            assert (project, timeline) == (project_id, timeline_id)
            return identities.parent_revision_id

        def list_project_timeline_heads(self, project):
            return {timeline_id: identities.parent_revision_id}

        def read_current_semantic_digest(self, project, timeline):
            return baseline.semantic_digest

        def read_current_closure(self, project, timeline, *, head=None):
            return {"project_id": project, "timeline_id": timeline, "head_revision_id": head}

    adapter = Adapter()

    @contextmanager
    def fake_runtime(**kwargs):
        yield SimpleNamespace(adapter=adapter, endpoint="http://127.0.0.1:45678",
                              realm_id="runtime-realm-789", root=tmp_path / "runtime")
        closed["value"] = True

    def fake_seed(*args, **kwargs):
        return {"endpoint_url": "http://127.0.0.1:45678", "endpoint_realm_id": "runtime-realm-789",
                "project_id": project_id, "timeline_id": timeline_id, "identities": identities,
                "owned_media": {row.digest: "owned-" + row.digest[-8:] for row in baseline.media},
                "target_locator": {"occurrence_id": identities.occurrence_ids["shot-ee383f695b10431c"],
                                   "selector_clip_id": "shot_b01", "replacement_asset_key": "charcoal_20260922_intro"},
                "receipt": {"new_head": identities.parent_revision_id}}

    monkeypatch.setattr(runtime_adapter, "local_disposable_runtime", fake_runtime)
    monkeypatch.setattr(fixture, "seed_case", fake_seed)
    (tmp_path / "canonical").mkdir()
    prepared = prepare_case("A01", case_root=tmp_path / "work" / "project", fixture_root=UNBLOCKED,
                            canonical_endpoint="http://127.0.0.1:1", canonical_realm_id="sentinel",
                            canonical_root=tmp_path / "canonical")
    try:
        target = json.loads((prepared.project_dir / "target.json").read_text())
        inputs = json.loads((prepared.project_dir / "task-inputs.json").read_text())
        brief = render_case_brief("A01", prepared=prepared)
        assert inputs["project_root"] == str(prepared.project_dir)
        assert all(
            asset["absolute_path"].startswith(str(prepared.project_dir) + "/")
            and asset["project_path"].startswith("project/")
            for asset in inputs["assets"]
        )
        assert target["project_id"] == project_id
        assert target["timeline_id"] == timeline_id
        assert target["endpoint"] == prepared.endpoint
        assert identities.occurrence_ids["shot-ee383f695b10431c"] in target["occurrence_ids"]
        assert "shot-ee383f695b10431c" not in json.dumps(inputs)
        assert "runtime-project-123" in brief
        assert "{opening shot}" not in brief
        assert "Write exactly one JSON object to `result.json` in your current working" in brief
        assert "`status`, `answer`, and `evidence`" in brief
        assert "Make no unsupported claims" in brief
        assert not closed["value"]
        assert prepared.baseline_observer()["head_revision_id"] == identities.parent_revision_id
    finally:
        prepared.close()
    assert closed["value"]


def test_live_navigation_briefs_require_public_inspection_and_visual_artifacts(tmp_path: Path) -> None:
    target = {
        "endpoint": "http://127.0.0.1:45678", "realm_id": "live-realm",
        "project_id": "live-project", "timeline_id": "live-timeline",
        "head_revision_id": "live-head", "occurrence_ids": ["live-occurrence"],
    }
    prepared = SimpleNamespace(
        project_dir=tmp_path / "project", endpoint=target["endpoint"],
        credential_file=tmp_path / "credential.token", realm_id=target["realm_id"],
        project_id=target["project_id"], timeline_id=target["timeline_id"], target=target,
    )
    for case_id in (f"L{index:02d}" for index in range(1, 11)):
        brief = render_case_brief(case_id, prepared=prepared)
        assert "client.timelines.show" in brief
        assert "client.timelines.open_composition" in brief
        assert "live-project" in brief and "live-timeline" in brief
        assert "ASTRID_TIMELINE_EVAL_CREDENTIAL" in brief
        if case_id in {"L04", "L09"}:
            assert "client.timelines.visualize" in brief
            assert "Open every returned `md`, `png`, and `manifest` artifact" in brief
