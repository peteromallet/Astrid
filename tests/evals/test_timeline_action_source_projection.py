from __future__ import annotations

from pathlib import Path

from evals.timeline.action_source_projection import derive_action_source_projection


ROOT = Path(__file__).resolve().parents[3]
RUN_ROOT = ROOT / ".otto/runs/timeline-text-inspection-20260922"
MANIFEST = RUN_ROOT / "evals/fixtures/action/manifest.json"
BASELINE = RUN_ROOT / "evals/attempts/e05-a01/source/baseline.json"


def test_source_projection_uses_real_a02_locator_but_stays_blocked_without_music() -> None:
    projection = derive_action_source_projection(
        manifest_path=MANIFEST, baseline_path=BASELINE, case_id="A02",
    )
    assert projection["status"] == "source_projection_only"
    assert projection["launchable"] is False
    assert projection["target_locator"]["remove_occurrence_id"] == "shot-63979db219fd7599"
    assert projection["target_locator"]["remove_voice_clip_ids"] == ["vo_b02"]
    assert len(projection["source_media_ids"]) > 0
    assert projection["destination_owned_media_ids"] == []
    assert any("continuous music" in reason for reason in projection["missing_prerequisites"])


def test_source_projection_derives_a03_and_a04_real_ids_but_not_ready_routes() -> None:
    a03 = derive_action_source_projection(
        manifest_path=MANIFEST, baseline_path=BASELINE, case_id="A03",
    )
    assert a03["target_locator"]["closing_occurrence_id"] == "shot-closing-v6-sign"
    assert a03["target_locator"]["middle_occurrence_id"] == "shot-49829dff799aa392"
    assert any("caption/title binding" in reason for reason in a03["missing_prerequisites"])
    assert any("target receipt" in reason for reason in a03["missing_prerequisites"])

    a04 = derive_action_source_projection(
        manifest_path=MANIFEST, baseline_path=BASELINE, case_id="A04",
    )
    assert a04["target_locator"]["feature_occurrence_id"] == "shot-49829dff799aa392"
    assert a04["target_locator"]["alternate_image_source_media_id"].startswith("sha256:")
    assert any("title/text binding" in reason for reason in a04["missing_prerequisites"])
    assert any("copy-local" in reason for reason in a04["missing_prerequisites"])
    assert a04["destination_owned_media_ids"] == []
