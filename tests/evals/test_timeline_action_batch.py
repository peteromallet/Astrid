from __future__ import annotations

from evals.timeline.action_batch import CASE_IDS, EXECUTOR_KIND, _case_blocker


def test_action_batch_covers_exactly_a02_through_a10() -> None:
    assert CASE_IDS == tuple(f"A{number:02d}" for number in range(2, 11))
    assert EXECUTOR_KIND == "deterministic_fixture_action"


def test_every_action_case_reports_fixture_blocker_without_false_success() -> None:
    facts = {
        "counts": {"occurrences": 16, "unique_shots": True},
        "parent_tracks": ["frame", "fx", "picture", "terminal-background"],
        "parent_audio_clips": 0,
    }
    for case_id in CASE_IDS:
        reason, missing = _case_blocker(case_id, facts)
        assert reason
        assert missing
        assert "success" not in reason.lower()


def test_a02_and_a07_report_missing_parent_music_explicitly() -> None:
    facts = {"counts": {"occurrences": 16, "unique_shots": True}, "parent_tracks": ["picture"], "parent_audio_clips": 0}
    for case_id in ("A02", "A07"):
        reason, missing = _case_blocker(case_id, facts)
        assert "music" in reason.lower()
        assert missing
