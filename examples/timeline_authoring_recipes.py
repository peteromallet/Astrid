"""Small, runnable examples for common detached authoring edits.

Each function mutates the supplied working copy only. Callers should validate,
preview, and publish the returned candidate through the canonical bundle API.
Media IDs are already-admitted Runtime identities; importing a local file stays
at the existing ``client.media`` boundary.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any

from astrid.sdk import (
    add_authoring_shot,
    add_track,
    grid,
    place_media,
    sequence,
)


def brightness_sequence(
    work: MutableMapping[str, Any],
    image_ids: Sequence[str],
    brightness_key: Callable[[str], Any],
    *,
    shot_id: str = "brightness-montage",
    occurrence_id: str = "brightness-montage",
    duration: float = 0.1,
) -> MutableMapping[str, Any]:
    """Place admitted images in brightness order at a fixed duration."""

    if duration <= 0:
        raise ValueError("duration must be positive")
    shot = add_authoring_shot(work, shot_id=shot_id, occurrence_id=occurrence_id, name="Brightness")
    track = add_track(shot, kind="visual", track_id=f"{shot_id}-track")
    ordered_ids = sorted(image_ids, key=lambda media_id: (brightness_key(media_id), media_id))
    clips = [
        place_media(shot, media_id, track=track, start=0, end=duration, clip_id=f"{shot_id}-{index}")
        for index, media_id in enumerate(ordered_ids)
    ]
    sequence(clips, start=0, durations=[duration] * len(clips))
    placement = next(row for row in work["placements"] if row.get("occurrence_id") == occurrence_id)
    placement["placement"]["start_ms"] = 0
    placement["duration_ms"] = round(len(clips) * duration * 1000)
    return shot


def timed_quadrants(
    work: MutableMapping[str, Any],
    shot_id: str,
    media_ids: Sequence[str],
    starts: Sequence[float],
    *,
    duration: float = 1.0,
) -> list[MutableMapping[str, Any]]:
    """Stack four admitted media items in a 2x2 grid at explicit times."""

    if len(media_ids) != 4 or len(starts) != 4:
        raise ValueError("timed_quadrants requires exactly four media IDs and starts")
    if duration <= 0:
        raise ValueError("duration must be positive")
    shot = work["shots"][shot_id]
    clips = []
    for index, (media_id, start, rect) in enumerate(zip(media_ids, starts, grid(2, 2))):
        track = add_track(shot, kind="visual", track_id=f"{shot_id}-quad-{index}")
        clips.append(
            place_media(
                shot,
                media_id,
                track=track,
                start=start,
                end=start + duration,
                rect=rect,
                clip_id=f"{shot_id}-quad-clip-{index}",
            )
        )
    return clips


def source_offset_beats(
    work: MutableMapping[str, Any],
    shot_id: str,
    beats: Sequence[Mapping[str, Any]],
) -> list[MutableMapping[str, Any]]:
    """Place beat-aligned clips while retaining explicit source offsets."""

    shot = work["shots"][shot_id]
    track = add_track(shot, kind="visual", track_id=f"{shot_id}-beats")
    clips = []
    for index, beat in enumerate(beats):
        source_start = beat["source_start"]
        source_end = beat["source_end"]
        start = beat["start"]
        clips.append(
            place_media(
                shot,
                str(beat["media_id"]),
                track=track,
                start=start,
                end=start + (source_end - source_start),
                source_start=source_start,
                source_end=source_end,
                clip_id=f"{shot_id}-beat-{index}",
            )
        )
    return clips


def audio_reactive_arrangement(
    work: MutableMapping[str, Any],
    shot_id: str,
    audio_id: str,
    *,
    duration: float,
    analysis_seed: int,
) -> MutableMapping[str, Any]:
    """Place admitted audio and freeze analysis provenance on its clip."""

    if duration <= 0:
        raise ValueError("duration must be positive")
    shot = work["shots"][shot_id]
    track = add_track(shot, kind="audio", track_id=f"{shot_id}-music")
    clip = place_media(shot, audio_id, track=track, start=0, end=duration, clip_id=f"{shot_id}-audio")
    clip["analysis"] = {"frozen": True, "seed": analysis_seed}
    return clip


__all__ = [
    "audio_reactive_arrangement",
    "brightness_sequence",
    "source_offset_beats",
    "timed_quadrants",
]
