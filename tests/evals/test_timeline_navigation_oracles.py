from __future__ import annotations

import json
import shutil
from pathlib import Path

from evals.timeline.fixture import materialize_public_navigation_entrypoint
from evals.timeline.fixture_contracts import validate_l10_playback_evidence
from evals.timeline.fixture_manifest import build_readiness
from evals.timeline.fixture_preparation import prepare_case
from evals.timeline.navigation_oracles import build_l07_legacy_canonical_oracle


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT.parent / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"


def test_l07_oracle_is_coordinator_only_and_worker_sidecar_reference_resolves(tmp_path: Path) -> None:
    destination = tmp_path / "case-L07"
    destination.mkdir()
    entry = materialize_public_navigation_entrypoint(
        "L07", fixture_root=FIXTURES, destination=destination,
    )
    assert "independent_comparison_oracle" not in entry["related_inputs"]
    oracle = build_l07_legacy_canonical_oracle(fixture_root=FIXTURES, repo_root=REPO_ROOT.parent)
    assert oracle["status"] == "verified_from_source_bytes"
    assert oracle["legacy_artifact_sha256"] == "sha256:97cf9b00c4b683996189e6411bf14d792625f323475423ff8f0c5379f4822d12"
    assert len(oracle["rows"]) == 2
    by_id = {row["occurrence_id"]: row for row in oracle["rows"]}
    intro = by_id["shot-ee383f695b10431c"]
    ideas = by_id["shot-6f6b80fbe16c0877"]
    assert intro["comparison"]["shot_identity_matches"] is True
    assert intro["comparison"]["duration_delta_ms"] == 0
    assert ideas["comparison"]["shot_identity_matches"] is True
    assert ideas["comparison"]["start_delta_ms"] == 0
    # The real legacy timeline has a shorter B03 hold than the canonical pin.
    assert ideas["comparison"]["duration_delta_ms"] == -1434
    assert ideas["comparison"]["legacy_is_canonical_authority"] is False
    sidecar = destination / "entrypoint" / "L07-legacy-compare.json"
    sidecar_json = json.loads(sidecar.read_text(encoding="utf-8"))
    referenced = sidecar.parent / sidecar_json["canonical_fixture"]["fixture_manifest"]
    assert referenced == destination / "entrypoint" / "entrypoint.json"
    assert referenced.is_file()


def test_materialized_l06_l07_l10_contracts_reconcile_proven_inputs(tmp_path: Path) -> None:
    for case_id in ("L06", "L07", "L10"):
        destination = tmp_path / case_id
        destination.mkdir()
        entry = materialize_public_navigation_entrypoint(
            case_id, fixture_root=FIXTURES, destination=destination,
        )
        if case_id in {"L06", "L07"} or (case_id == "L10" and shutil.which("afplay")):
            assert entry["fixture_contract"]["status"] == "ready"


def test_l07_computed_oracle_is_written_only_to_coordinator_area(tmp_path: Path) -> None:
    project = tmp_path / "cases" / "L07" / "work" / "project"
    prepared = prepare_case(
        "L07", case_root=project, fixture_root=FIXTURES,
        canonical_endpoint="", canonical_realm_id="", canonical_root=tmp_path,
    )
    try:
        private = project.parents[1] / "coordinator" / "independent-comparison-oracle.json"
        public = project / "entrypoint" / "entrypoint.json"
        assert private.is_file()
        assert "independent_comparison_oracle" not in json.loads(public.read_text())["related_inputs"]
    finally:
        prepared.close()


def test_l10_playback_contract_requires_completion_then_pinned_parent_return(tmp_path: Path) -> None:
    destination = tmp_path / "case-L10"
    destination.mkdir()
    entry = materialize_public_navigation_entrypoint(
        "L10", fixture_root=FIXTURES, destination=destination,
    )
    contract = entry["related_inputs"]["playback_completion_contract"]
    assert contract["kind"] == "astrid.timeline-eval.l10-playback-evidence.v1"
    assert contract["evidence_path"] == "evidence/navigation-path.json"
    assert contract["evidence_is_observed_only"] is True
    assert any("playback completion" in item for item in entry["fixture_contract"]["coordinator_evidence_required"])

    good = {
        "kind": "astrid.timeline-eval.l10-playback-evidence.v1",
        "case_id": "L10",
        "voice_media_id": "sha256:voice",
        "player": {"resolved_executable": "/usr/bin/afplay", "exit_status": 0},
        "playback": {"completed": True},
        "trace_ordinals": {"player_started": 4, "playback_completed": 5, "parent_returned": 6},
        "parent_return": {
            "returned": True, "alias": "parent", "source_head": "head-1",
            "closure_digest": "sha256:closure",
        },
    }
    assert validate_l10_playback_evidence(good) == []
    errors = validate_l10_playback_evidence({
        **good,
        "playback": {"completed": False},
        "trace_ordinals": {"player_started": 6, "playback_completed": 5, "parent_returned": 4},
        "parent_return": {"returned": False},
    })
    assert "L10 playback completion is not evidenced" in errors
    assert "L10 trace must order player start, playback completion, then parent return" in errors
    assert "L10 return to the parent composition is not evidenced" in errors


def test_l04_l05_l09_keep_precise_fixture_gaps_typed_and_blocked() -> None:
    rows = {row.case_id: row for row in build_readiness(fixture_root=FIXTURES)}
    expected = {
        "L04": {"surface_adapters.text_reader", "surface_adapters.visualizer_reader",
                "surface_adapters.browser_reader", "surface_adapters.managed_renderer"},
        "L05": {"ideas_b03.historical_video_alternatives"},
        "L09": {"output_records.current_canonical_output.artifact_handle",
                "output_records.historical_output.artifact_handle",
                "output_records.candidate_preview.artifact_handle"},
    }
    for case_id, paths in expected.items():
        row = rows[case_id]
        assert row.readiness == "blocked"
        requirements = row.contract["required_inputs"]
        assert {item["path"] for item in requirements} == paths
        expected_kind = "environmental_capability" if case_id == "L04" else "missing_fixture_input"
        assert all(item["kind"] == expected_kind for item in requirements)
        assert all(item["reason"] for item in requirements)
