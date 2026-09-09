from __future__ import annotations

from astrid.packs.rendering.executors.timeline_visualize.filmstrip_cards import plan_filmstrip


def test_audio_targets_are_unique_and_render_scoped():
    snapshot = {
        "project_slug": "demo", "timeline_id": "tl", "render_run_id": "run", "video_digest": "sha256:" + "a" * 64,
        "fps_rational": [24, 1], "duration_frames": 48, "clips": [], "tracks": [], "scripts": [],
        "audio": {
            "analysis_identity": "sha256:" + "b" * 64,
            "stream": {"sample_rate": 10},
            "presentation_origin": {"seconds": [0, 1]},
            "waveform": {"levels": [{"id": "level-2", "bin_width_samples": 5, "bins": [{"index": 0, "start_sample": 0, "end_sample": 5}, {"index": 1, "start_sample": 5, "end_sample": 10}]}, {"id": "level-4", "bin_width_samples": 3, "bins": [{"index": 0, "start_sample": 0, "end_sample": 3}]}]},
            "quiet_gaps": [{"id": "gap-1", "start": [1, 1], "end": [3, 1], "duration_seconds": 2, "measurement": "low_amplitude", "threshold": 0.01}],
            "speech": {"annotation_identity": "sha256:" + "c" * 64, "phrases": [{"id": "phrase-1", "canonical_text": "Hello", "render_interval": {"start": [0, 1], "end": [1, 1]}}]},
        },
    }
    index = plan_filmstrip(snapshot, {"every_frames": 24})
    targets = [item["target"] for item in index["navigation"]["waveforms"] + index["navigation"]["gaps"] + index["navigation"]["phrases"]]
    assert len(targets) == len(set(targets)) == 5
    assert all(item["analysis_identity"] == snapshot["audio"]["analysis_identity"] for item in index["navigation"]["waveforms"])
    assert all("--range" in item["actions"]["focus_command"] for item in index["navigation"]["gaps"] + index["navigation"]["phrases"])
    assert index["navigation"]["frames"][0]["active_audio_targets"]
