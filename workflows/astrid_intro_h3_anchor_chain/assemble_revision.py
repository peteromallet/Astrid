"""Prepare the six-segment Astrid Intro H3 revision chain.

This is deliberately separate from the historical ``assemble.py``.  It keeps
the existing first-four selection mapping, splits ``shot_b06`` into a typing
hold and a new run-away exit, and never applies bridge transforms, masks, or
stabilization.  Preparation is the default; ``--apply`` is the only mutating
mode.  ``--check-plan`` validates the frame/timing contract without media or
runtime access.  ``--normalize-placement`` is an explicit opt-in that sets
only the newly selected full-canvas clips to static ``x=0,y=0,width=1920,
height=1080`` and records the before/after placement rationale.

Example (prepare only)::

    python3 workflows/astrid_intro_h3_anchor_chain/assemble_revision.py \
        s01.mp4 s02.mp4 s03.mp4 s04.mp4 s05.mp4 s06.mp4

The native sources must be 1920x1088 (or 1920x1080) at 24 fps with source
frame counts ``175/260/175/175/209/124``.  Outputs conform to
``212/279/177/169/205/106`` frames at 30 fps.  The second output is shared by
the two child timelines and is split at 96/183 frames; the last two outputs
split the existing 311-frame ``b06`` child at 205/106 frames.

For a bounded partial review, ``--prefix-count`` accepts only 1, 2, 3, 4, or
6.  A prefix of 2 includes both b02 and b03 selections because they share the
s02 source.  Count 5 is intentionally rejected: the b06 hold and run-away
exit must be replaced atomically.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

from assemble import (
    _object_id,
    _source_lineage_ids,
    checked,
    digest,
    link_derived_from,
    load_source_manifest,
    probe,
    timing_filter,
)

PROJECT = "astrid-intro"
PARENT = "2652b5567c8e4e9aa4d35c1df0eb2742"

SOURCE_FRAMES = (175, 260, 175, 175, 209, 124)
TARGET_FRAMES = (212, 279, 177, 169, 205, 106)
CONTEXT_FRAMES = (0, 39, 39, 39, 39, 39)

# Source index, child timeline, original picture clip, local source start,
# target frames in that child, and replacement clip id.  s02 is one conformed
# object split across two child timelines.  s05/s06 occupy one child timeline.
SELECTIONS = (
    {"source": 0, "timeline": "b0f1f21cfdf3581eb13e0647183cbf3e", "clip": "shot_b01", "start": 0, "frames": 212},
    {"source": 1, "timeline": "77e146741d20557eb9d4424b4210def7", "clip": "shot_b02", "start": 0, "frames": 96},
    {"source": 1, "timeline": "5157d8c097cf52b58d3237a47954c86c", "clip": "shot_b03", "start": 96, "frames": 183},
    {"source": 2, "timeline": "d46d3069475257a1b911a2b5c5630281", "clip": "shot_b04", "start": 0, "frames": 177},
    {"source": 3, "timeline": "930d51fd99105cd29541171eb3c42a1f", "clip": "shot_b05", "start": 0, "frames": 169},
    {"source": 4, "timeline": "7c22d84f97c85400ad83de923b6d7380", "clip": "shot_b06", "start": 0, "frames": 205},
    {"source": 5, "timeline": "7c22d84f97c85400ad83de923b6d7380", "clip": "shot_b06_exit_new", "start": 0, "frames": 106, "at_frame": 205},
)

# Parent windows are unchanged: only the b06 child document's picture track
# is split.  Keep this check independent from the generated media.
PARENT_WINDOWS = (
    ("b0f1f21cfdf3581eb13e0647183cbf3e", 0, 212),
    ("77e146741d20557eb9d4424b4210def7", 212, 96),
    ("5157d8c097cf52b58d3237a47954c86c", 308, 183),
    ("d46d3069475257a1b911a2b5c5630281", 491, 177),
    ("930d51fd99105cd29541171eb3c42a1f", 668, 169),
    ("7c22d84f97c85400ad83de923b6d7380", 837, 311),
)

# Observed authored placements at the current snapshot.  These are evidence
# only; the script reports them and preserves them.  It never auto-shifts.
AUTHORED_PLACEMENTS = {
    "shot_b01": (1.0, -32.5),
    "shot_b02": (1.5, 5.0),
    "shot_b03": (1.5, 5.0),
    "shot_b04": (-2.0, 27.5),
    "shot_b05": (0.0, 0.0),  # omitted x/y: default contain origin
    "shot_b06": (20.0, 64.0),
}


def _frame_seconds(frames: int) -> float:
    return frames / 30.0


def _placement(clip: dict) -> dict:
    # Keep None distinct in the snapshot while also exposing the effective
    # default origin used for the comparison report.
    x, y = clip.get("x"), clip.get("y")
    return {
        "x": x,
        "y": y,
        "effective_x": 0.0 if x is None else float(x),
        "effective_y": 0.0 if y is None else float(y),
        "width": clip.get("width"),
        "height": clip.get("height"),
    }


def _clip_duration_frames(clip: dict) -> int:
    if clip.get("hold") is not None:
        return round(float(clip["hold"]) * 30)
    if clip.get("from") is not None and clip.get("to") is not None:
        return round((float(clip["to"]) - float(clip["from"])) * 30)
    raise ValueError(f"picture clip has no measurable duration: {clip.get('id')}")


ALLOWED_PREFIX_COUNTS = (1, 2, 3, 4, 6)


def _selection_prefix_count(selection: dict) -> int:
    """Return the native source count at which a child selection becomes active."""
    # The two b02/b03 selections both consume s02; b06's two selections are
    # deliberately activated together at the complete six-segment boundary.
    if selection["source"] <= 0:
        return 1
    if selection["source"] == 1:
        return 2
    if selection["source"] == 2:
        return 3
    if selection["source"] == 3:
        return 4
    return 6


def _active_selections(prefix_count: int) -> tuple[dict, ...]:
    if prefix_count not in ALLOWED_PREFIX_COUNTS:
        raise ValueError(
            f"prefix-count must be one of {', '.join(map(str, ALLOWED_PREFIX_COUNTS))}; "
            "5 is rejected because the b06 hold/exit pair is atomic"
        )
    return tuple(item for item in SELECTIONS if _selection_prefix_count(item) <= prefix_count)


def validate_plan(*, normalize_placement: bool = False, prefix_count: int = 6) -> dict:
    active = _active_selections(prefix_count)
    if len(SELECTIONS) != 7:
        raise AssertionError("expected seven child selections including b06 split")
    if sum(item["frames"] for item in SELECTIONS) != 1148:
        raise AssertionError("child selection frames must preserve 1148-frame opening")
    if SELECTIONS[1]["frames"] + SELECTIONS[2]["frames"] != TARGET_FRAMES[1]:
        raise AssertionError("s02 split does not equal 279 frames")
    if SELECTIONS[5]["frames"] + SELECTIONS[6]["frames"] != 311:
        raise AssertionError("b06 split does not equal 311 frames")
    for index, (source, target, context) in enumerate(zip(SOURCE_FRAMES, TARGET_FRAMES, CONTEXT_FRAMES)):
        if source <= context or target <= 0:
            raise AssertionError(f"invalid frame contract at source {index}")
    return {
        "prefix_count": prefix_count,
        "partial_revision": prefix_count != 6,
        "selected_native_segments": list(range(prefix_count)),
        "remaining_native_segments": list(range(prefix_count, 6)),
        "active_selection_indices": [SELECTIONS.index(item) for item in active],
        "source_frames_24fps": list(SOURCE_FRAMES),
        "context_frames": list(CONTEXT_FRAMES),
        "target_frames_30fps": list(TARGET_FRAMES),
        "child_selection_frames": [item["frames"] for item in SELECTIONS],
        "s02_split": [96, 183],
        "b06_split": [205, 106],
        "placement_policy": (
            "normalize new full-canvas clips to static (0,0,1920,1080); report deltas; no bridge transforms"
            if normalize_placement
            else "preserve authored positions; report deltas; no bridge transforms"
        ),
        "placement_normalization": {
            "enabled": normalize_placement,
            "static_origin": [0.0, 0.0, 1920, 1080],
            "animated_motion": False,
            "crop": False,
            "mask": False,
        },
        "authored_placement_reference": AUTHORED_PLACEMENTS,
    }


def _revision_conform(source: Path, dest: Path, index: int) -> dict:
    info = probe(source)
    count = int(info["nb_read_frames"])
    if count != SOURCE_FRAMES[index] or Fraction(info["avg_frame_rate"]) != 24:
        raise ValueError(
            f"Unexpected source {source}: {info}; expected {SOURCE_FRAMES[index]} frames at 24fps"
        )
    if (int(info["width"]), int(info["height"])) not in ((1920, 1088), (1920, 1080)):
        raise ValueError(f"Unexpected source canvas: {info}")
    skip = CONTEXT_FRAMES[index]
    target = TARGET_FRAMES[index]
    filters = timing_filter(count, skip, target) + ",scale=1920:1080:flags=neighbor,setsar=1"
    subprocess.run(
        [
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-an",
            "-vf", filters, "-frames:v", str(target), "-c:v", "libx264",
            "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(dest),
        ],
        check=True,
    )
    output = probe(dest)
    if int(output["nb_read_frames"]) != target or Fraction(output["avg_frame_rate"]) != 30:
        raise RuntimeError(f"Conform verification failed: {output}")
    return {
        "source_sha256": digest(source),
        "source_probe": info,
        "discarded_context_frames": skip,
        "new_source_frames": count - skip,
        "target_frames": target,
        "target_fps": 30,
        "filter": filters,
        "output_sha256": digest(dest),
        "output_probe": output,
        "bridge_translation": {"enabled": False, "reason": "revision explicitly preserves authored placements"},
        "post_processing": {"mask": False, "stabilization": False, "heading_replacement": False},
    }


def _parent_check(parent: dict) -> None:
    by_child = {
        clip.get("params", {}).get("timeline_document_id"): clip
        for clip in parent["config"]["clips"]
        if clip.get("clipType") == "shot"
    }
    for child, start_frame, length in PARENT_WINDOWS:
        clip = by_child.get(child)
        if clip is None:
            raise RuntimeError(f"parent is missing child timeline {child}")
        if round(float(clip["at"]) * 30) != start_frame or round(float(clip["hold"]) * 30) != length:
            raise RuntimeError(f"parent timing changed for {child}; expected {start_frame}:{length}")


def _picture_clip(doc: dict, clip_id: str) -> dict:
    matches = [
        clip for clip in doc["config"]["clips"]
        if clip.get("id") == clip_id and clip.get("track") == "picture"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one picture clip {clip_id}; found {len(matches)}")
    return matches[0]


def _snapshot_selection(client, selection: dict, manifest: dict) -> None:
    timeline = selection["timeline"]
    doc = checked(client.timelines.show(PROJECT, timeline))
    clip = _picture_clip(doc, "shot_b06" if timeline == "7c22d84f97c85400ad83de923b6d7380" else selection["clip"])
    if timeline == "7c22d84f97c85400ad83de923b6d7380":
        if selection["clip"] == "shot_b06_exit_new":
            raise RuntimeError("b06 exit clip must not already exist before applying revision")
        if _clip_duration_frames(clip) != 311:
            raise RuntimeError("current b06 picture clip no longer spans the 311-frame child window")
    elif _clip_duration_frames(clip) != selection["frames"]:
        # b02/b03 carry their already-conformed split lengths; other child
        # durations are the exact parent windows.
        raise RuntimeError(f"current {selection['clip']} duration changed")
    if timeline != "7c22d84f97c85400ad83de923b6d7380" and selection["clip"] in {"shot_b01", "shot_b02", "shot_b03", "shot_b04", "shot_b05"}:
        placement = _placement(clip)
        manifest.setdefault("placement_comparison", []).append({
            "clip_id": selection["clip"],
            "observed": placement,
            "reference": AUTHORED_PLACEMENTS.get(selection["clip"]),
            "auto_shift": False,
        })
    if timeline == "7c22d84f97c85400ad83de923b6d7380" and selection["clip"] == "shot_b06":
        manifest.setdefault("placement_comparison", []).append({
            "clip_id": selection["clip"],
            "observed": _placement(clip),
            "reference": AUTHORED_PLACEMENTS["shot_b06"],
            "auto_shift": False,
        })
    key = (timeline, selection["clip"])
    if key not in {(item["timeline_id"], item["clip_id"]) for item in manifest["selections"]}:
        manifest["selections"].append({
            "timeline_id": timeline,
            "clip_id": selection["clip"],
            "segment": selection["source"],
            "source_start_frame": selection["start"],
            "frames": selection["frames"],
            "at_frame": selection.get("at_frame", 0),
            "before": doc,
        })


def _assert_unchanged(before: dict, fresh: dict, *, clip_ids: set[str]) -> None:
    for clip_id in clip_ids:
        old = next((clip for clip in before["config"]["clips"] if clip.get("id") == clip_id), None)
        new = next((clip for clip in fresh["config"]["clips"] if clip.get("id") == clip_id), None)
        if old != new:
            raise RuntimeError(f"concurrent edit detected for {clip_id}; no save attempted")


def _media_clip(
    original: dict,
    *,
    asset: str,
    duration_frames: int,
    at_frame: int = 0,
    normalize_placement: bool = False,
) -> dict:
    clip = copy.deepcopy(original)
    clip.pop("hold", None)
    clip.update({
        "at": _frame_seconds(at_frame),
        "clipType": "media",
        "asset": asset,
        "from": 0,
        "to": _frame_seconds(duration_frames),
        "speed": 1,
        "volume": 0,
    })
    if normalize_placement:
        # This is deliberately a static full-canvas placement.  It does not
        # crop, mask, scale over time, or introduce an animated bridge.
        clip.update({"x": 0.0, "y": 0.0, "width": 1920, "height": 1080})
    return clip


def _replace_picture_clip(config: dict, clip_id: str, replacement: dict) -> None:
    for index, clip in enumerate(config["clips"]):
        if clip.get("id") == clip_id:
            config["clips"][index] = replacement
            return
    raise RuntimeError(f"could not replace missing clip {clip_id}")


def _split_b06(config: dict, first: dict, exit_clip: dict) -> None:
    if any(clip.get("id") == "shot_b06_exit_new" for clip in config["clips"]):
        raise RuntimeError("b06 exit clip already exists; refuse duplicate insertion")
    clips = []
    inserted = False
    for clip in config["clips"]:
        if clip.get("id") == "shot_b06":
            clips.extend([first, exit_clip])
            inserted = True
        else:
            clips.append(clip)
    if not inserted:
        raise RuntimeError("b06 picture clip disappeared before split")
    config["clips"] = clips


def _plan_output(*, normalize_placement: bool = False, prefix_count: int = 6) -> None:
    print(json.dumps(
        validate_plan(
            normalize_placement=normalize_placement,
            prefix_count=prefix_count,
        ),
        indent=2,
        sort_keys=True,
    ))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", nargs="*", type=Path, help="Six native H3 segments in chain order")
    parser.add_argument("--apply", action="store_true", help="Import media and CAS-save child selections")
    parser.add_argument("--prepare-only", action="store_true", help="Default: conform only; no runtime mutation")
    parser.add_argument("--check-plan", action="store_true", help="Validate frame/timing contract without media or runtime")
    parser.add_argument(
        "--prefix-count",
        type=int,
        default=6,
        help=(
            "Number of native segments to assemble; allowed values are 1, 2, 3, 4, or 6. "
            "5 is rejected because the b06 hold/exit pair is atomic (default: 6)"
        ),
    )
    parser.add_argument(
        "--normalize-placement",
        action="store_true",
        help=(
            "Opt in to static x=0,y=0,width=1920,height=1080 for every new "
            "full-canvas picture clip; record before/after placement evidence"
        ),
    )
    parser.add_argument("--source-manifest", type=Path, default=None, help="Optional provenance manifest for six sources")
    args = parser.parse_args()
    try:
        plan = validate_plan(
            normalize_placement=args.normalize_placement,
            prefix_count=args.prefix_count,
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.check_plan:
        if args.clips:
            parser.error("--check-plan accepts no clip paths")
        _plan_output(
            normalize_placement=args.normalize_placement,
            prefix_count=args.prefix_count,
        )
        return
    if len(args.clips) != args.prefix_count:
        parser.error(
            f"{args.prefix_count} native clips are required for --prefix-count {args.prefix_count}"
        )
    if args.apply and args.prepare_only:
        parser.error("--apply and --prepare-only are mutually exclusive")
    sources = [path.resolve(strict=True) for path in args.clips]
    source_manifest = args.source_manifest.resolve(strict=True) if args.source_manifest else None
    if source_manifest and source_manifest in sources:
        parser.error("--source-manifest must not also be a source clip")

    stage = Path(tempfile.mkdtemp(prefix="astrid-intro-h3-revision-conform-"))
    outputs = [stage / f"s{i + 1:02}-30fps.mp4" for i in range(args.prefix_count)]
    manifest = {
        "schema": "astrid-intro-h3-selection-revision-v1",
        "project": PROJECT,
        "parent_timeline_id": PARENT,
        "frame_plan": plan,
        "partial_revision": args.prefix_count != 6,
        "remaining_native_segments": list(range(args.prefix_count, 6)),
        "segments": [],
        "selections": [],
        "saved": [],
        "placement_policy": (
            "normalize new full-canvas clips to static (0,0,1920,1080); no bridge transforms, masks, or stabilization"
            if args.normalize_placement
            else "preserve authored positions; no bridge transforms, masks, or stabilization"
        ),
        "placement_normalization": {
            "enabled": bool(args.normalize_placement),
            "rationale": (
                "Normalize newly selected full-canvas clips to one static origin "
                "to remove known authored placement discontinuities; frame overlay "
                "and all non-picture tracks remain separate."
                if args.normalize_placement
                else "Disabled by default; preserve authored placement and report offsets only."
            ),
            "before_after": [],
            "constraints": {
                "x": 0.0,
                "y": 0.0,
                "width": 1920,
                "height": 1080,
                "animated_motion": False,
                "crop": False,
                "mask": False,
            },
        },
    }
    manifest["partial_revision_rationale"] = (
        "Only the approved native prefix is selected; all remaining child timelines, tracks, assets, and parent timing remain unmodified."
        if args.prefix_count != 6
        else "Complete six-segment revision; b06 hold and run-away exit are replaced atomically."
    )
    manifest_path = stage / "assembly-provenance.json"
    source_records = load_source_manifest(source_manifest, sources) if source_manifest else None
    if source_records:
        manifest["source_manifest"] = source_records
    active_selections = _active_selections(args.prefix_count)

    def persist() -> None:
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"Staging: {stage}", flush=True)
    for index, (source, output) in enumerate(zip(sources, outputs)):
        row = _revision_conform(source, output, index)
        if source_records:
            row["source_manifest"] = source_records["sources"][index]
            row["lineage"] = _source_lineage_ids(source_records["sources"][index])
        manifest["segments"].append(row)
        persist()

    # Runtime reads begin only after all admitted files pass native/probe/conform
    # gates.  The launcher option avoids starting an unrelated pack host.
    from astrid.sdk import AstridClient

    with AstridClient.open_from_launcher(start_pack_host=False) as client:
        parent = checked(client.timelines.show(PROJECT, PARENT))
        _parent_check(parent)
        # Snapshot every child once.  Current selected media are accepted; the
        # exact clip object is compared again immediately before each save.
        for selection in active_selections:
            # The exit clip is intentionally absent from the pre-apply
            # snapshot; b06's existing 311-frame picture clip is the one
            # compared before the split save below.
            if selection["clip"] == "shot_b06_exit_new":
                continue
            _snapshot_selection(client, selection, manifest)
        manifest["parent_snapshot"] = parent
        persist()
        if not args.apply:
            print(
                f"Prepared only; {args.prefix_count} conformed clip(s) are in {stage}. "
                f"No runtime mutations. Partial revision={args.prefix_count != 6}.\n{manifest_path}"
            )
            return

        # Import each source and conformed object once.  Existing registry rows
        # remain untouched; only new revision asset keys are added below.
        for index, (source, output) in enumerate(zip(sources, outputs)):
            row = manifest["segments"][index]
            row["source_object"] = checked(client.media.import_file(project=PROJECT, path=source))
            row["conformed_object"] = checked(client.media.import_file(project=PROJECT, path=output))
            source_object_id = _object_id(row["source_object"])
            conformed_object_id = _object_id(row["conformed_object"])
            row["lineage_relations"] = [link_derived_from(
                client, PROJECT, conformed_object_id, source_object_id, role="source"
            )]
            raw_object_id = row.get("lineage", {}).get("raw_generation_object_id")
            if raw_object_id:
                row["lineage_relations"].append(link_derived_from(
                    client, PROJECT, conformed_object_id, raw_object_id, role="raw_generation"
                ))
            persist()

        evidence = checked(client.media.import_file(project=PROJECT, path=manifest_path))
        evidence_id = _object_id(evidence)
        manifest["pre_selection_provenance_object"] = evidence_id
        persist()

        asset_keys = {}
        for index, row in enumerate(manifest["segments"]):
            media_id = _object_id(row["conformed_object"])
            key = f"h3_intro_revision_s{index + 1:02}_{row['output_sha256'][:12]}"
            asset_keys[index] = key
            # Build the registry entry once per conformed object; all existing
            # assets stay intact and b02/b03 share the s02 entry.
            row["registry_asset_key"] = key

        saved_timelines = set()
        for timeline in sorted({selection["timeline"] for selection in active_selections}):
            selections = [item for item in active_selections if item["timeline"] == timeline]
            before = next(item["before"] for item in manifest["selections"] if item["timeline_id"] == timeline)
            doc = checked(client.timelines.show(PROJECT, timeline))
            _assert_unchanged(before, doc, clip_ids={"shot_b06"} if timeline == "7c22d84f97c85400ad83de923b6d7380" else {item["clip"] for item in selections})
            config, registry = copy.deepcopy(doc["config"]), copy.deepcopy(doc["registry"])
            registry.setdefault("assets", {})
            for source_index in sorted({item["source"] for item in selections}):
                row = manifest["segments"][source_index]
                registry["assets"][asset_keys[source_index]] = {
                    "media_id": _object_id(row["conformed_object"]),
                    "content_sha256": row["output_sha256"],
                    "type": "video",
                    "resolution": "1920x1080",
                    "duration": _frame_seconds(TARGET_FRAMES[source_index]),
                }
            original = _picture_clip(doc, "shot_b06" if timeline == "7c22d84f97c85400ad83de923b6d7380" else selections[0]["clip"])
            if timeline == "7c22d84f97c85400ad83de923b6d7380":
                if args.prefix_count != 6:
                    raise RuntimeError("b06 timeline is only active for the complete six-segment revision")
                first = _media_clip(
                    original,
                    asset=asset_keys[4],
                    duration_frames=205,
                    normalize_placement=args.normalize_placement,
                )
                exit_clip = _media_clip(
                    original,
                    asset=asset_keys[5],
                    duration_frames=106,
                    at_frame=205,
                    normalize_placement=args.normalize_placement,
                )
                exit_clip["id"] = "shot_b06_exit_new"
                manifest["placement_normalization"]["before_after"].extend([
                    {
                        "timeline_id": timeline,
                        "clip_id": "shot_b06",
                        "before": _placement(original),
                        "after": _placement(first),
                    },
                    {
                        "timeline_id": timeline,
                        "clip_id": "shot_b06_exit_new",
                        "before": _placement(original),
                        "after": _placement(exit_clip),
                    },
                ])
                _split_b06(config, first, exit_clip)
            else:
                for selection in selections:
                    current = _picture_clip({"config": config}, selection["clip"])
                    replacement = _media_clip(
                        current,
                        asset=asset_keys[selection["source"]],
                        duration_frames=selection["frames"],
                        at_frame=selection.get("at_frame", 0),
                        normalize_placement=args.normalize_placement,
                    )
                    replacement["from"] = _frame_seconds(selection["start"])
                    replacement["to"] = _frame_seconds(selection["start"] + selection["frames"])
                    manifest["placement_normalization"]["before_after"].append({
                        "timeline_id": timeline,
                        "clip_id": selection["clip"],
                        "before": _placement(current),
                        "after": _placement(replacement),
                    })
                    _replace_picture_clip(config, selection["clip"], replacement)
            # The parent is not mutated by this operation, but its timing is
            # part of the save contract. Re-read immediately before every
            # child save so a concurrent parent edit stops this run before the
            # next child document is written.
            latest_parent = checked(client.timelines.show(PROJECT, PARENT))
            _parent_check(latest_parent)
            saved = checked(client.timelines.save(
                PROJECT,
                timeline,
                config=config,
                registry=registry,
                expected_version=doc["config_version"],
            ))
            manifest["saved"].append({"timeline_id": timeline, "before_version": doc["config_version"], "result": saved})
            saved_timelines.add(timeline)
            persist()

        final = checked(client.media.import_file(project=PROJECT, path=manifest_path))
        print(json.dumps({"ok": True, "saved_timelines": sorted(saved_timelines), "provenance": final, "staging": str(stage)}, indent=2))


if __name__ == "__main__":
    main()
