"""Runtime snapshot projection tests.

The live snapshot API accepts already-materialized runtime events.  It does
not acquire event logs or registry files from a project directory.
"""

from __future__ import annotations

import pytest

pytest.importorskip("banodoco_timeline_schema")

from astrid.core.timeline.events.schema import TimelineActor, TimelineEvent, with_event_hash
from astrid.core.timeline.snapshot import (
    SnapshotIntegrityError,
    snapshot_from_runtime,
    verify_frozen,
)

TIMELINE_ID = "ed70ef66-43da-4182-9f14-69361c6c5e10"
TIMELINE_ULID = "01KYPVKMW5STB4W6FE05ED8242"


def test_empty_runtime_materialization_is_deterministic_and_verifiable() -> None:
    snapshot = snapshot_from_runtime(
        timeline_id=TIMELINE_ID,
        timeline_ulid=TIMELINE_ULID,
        slug="main",
        project_slug="demo",
        events=[],
    )
    assert snapshot.assembly == {"clips": [], "tracks": []}
    assert snapshot.registry == {"assets": {}}
    assert snapshot.head_version == 0
    assert verify_frozen(snapshot) == list(snapshot.diagnostics)


def test_opaque_runtime_timeline_id_survives_event_snapshot_and_sns() -> None:
    timeline_id = "astrid-v1-timeline-full-20260912"
    event = TimelineEvent(
        event_id="01KZS6CCD73SYEC924B5XR12XG",
        timeline_id=timeline_id,
        ts="2026-09-12T00:00:00+00:00",
        actor=TimelineActor(type="system", id="astrid.kernel", display="Astrid kernel"),
        prev_hash=None,
        hash=None,
        kind="timeline.config_replaced",
        payload={"config": {"tracks": [], "clips": []}, "source": "other"},
        expected_version=0,
        source_backend="astrid.kernel",
        source_timeline_id=timeline_id,
        source_event_id="timeline-head",
        source_version=1,
        source_hash="a" * 64,
    )
    event = with_event_hash(event, prev_hash=None)

    snapshot = snapshot_from_runtime(
        timeline_id=timeline_id,
        timeline_ulid=TIMELINE_ULID,
        slug="full-fixture",
        project_slug="demo",
        events=[event.to_json_obj()],
    )

    assert snapshot.timeline_id == timeline_id
    assert snapshot.sns().startswith("SNS:")
    assert verify_frozen(snapshot) == list(snapshot.diagnostics)


def test_runtime_snapshot_rejects_noncanonical_identity() -> None:
    with pytest.raises(SnapshotIntegrityError, match="timeline_ulid"):
        snapshot_from_runtime(
            timeline_id=TIMELINE_ID,
            timeline_ulid=TIMELINE_ULID.lower(),
            slug="main",
            project_slug="demo",
            events=[],
        )


def test_runtime_snapshot_never_accepts_a_path_as_event_input() -> None:
    with pytest.raises(SnapshotIntegrityError, match="event 1 is schema-invalid"):
        snapshot_from_runtime(
            timeline_id=TIMELINE_ID,
            timeline_ulid=TIMELINE_ULID,
            slug="main",
            project_slug="demo",
            events=["assembly.jsonl"],  # type: ignore[list-item]
        )
