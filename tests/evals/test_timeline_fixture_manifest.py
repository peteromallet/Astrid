import json
from pathlib import Path

from evals.timeline.fixture_manifest import build_readiness, validate_case


def _dump(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_fixture_case_readiness_checks_targets_media_units_and_lifecycle(tmp_path):
    ready = {
        "id": "L01",
        "targets": {"occurrence_id": "occ-1", "head": "rev-1"},
        "media_handles": [{"id": "img-1", "digest": "sha256:abc"}],
        "units": {"time": "milliseconds", "frame_rate": "source_manifest"},
        "lifecycle": {"state": "read_only", "reset": "fresh_fixture"},
    }
    partial = {
        "id": "L02",
        "targets": {"occurrence_id": "{UNRESOLVED}"},
        "media_handles": [],
        "media_requirement": "none",
        "units": {"time": "not_applicable"},
        "lifecycle": {"state": "read_only"},
    }

    result_ready = validate_case(ready, "navigation", tmp_path / "info.json")
    result_partial = validate_case(partial, "navigation", tmp_path / "info.json")

    assert result_ready.readiness == "ready"
    assert result_partial.readiness == "blocked"
    assert any("target identities" in reason for reason in result_partial.reasons)


def test_build_readiness_reports_actual_fixture_states_per_case(tmp_path):
    suite_path = tmp_path / "suite.json"
    fixture_root = tmp_path / "fixtures"
    _dump(suite_path, {"cases": [
        {"id": "L01", "kind": "navigation"},
        {"id": "L02", "kind": "navigation"},
        {"id": "A01", "kind": "action"},
    ]})
    _dump(fixture_root / "informational" / "fixture.json", {"cases": [
        {
            "id": "L01", "targets": {"occurrence_id": "occ-1"},
            "media_handles": [{"id": "img-1", "digest": "sha256:abc"}],
            "units": {"time": "milliseconds"}, "lifecycle": {"state": "read_only"},
        }
    ]})
    _dump(fixture_root / "action" / "manifest.json", {"cases": [
        {
            "id": "A01", "targets": {"occurrence_id": "occ-1"},
            "media": [{"id": "new-img", "digest": "sha256:def"}],
            "units": {"time": "frames", "fps": "30/1"},
            "lifecycle": {"state": "fresh_derived_timeline", "reset": "new_timeline"},
        }
    ]})

    rows = {row.case_id: row for row in build_readiness(suite_path, fixture_root)}

    assert rows["L01"].readiness == "ready"
    assert rows["L02"].readiness == "blocked"
    assert rows["A01"].readiness == "ready"
    assert rows["L02"].reasons == ["case entry is missing from fixture manifest"]
