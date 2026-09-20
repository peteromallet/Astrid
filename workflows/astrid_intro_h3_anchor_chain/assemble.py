"""Prepare reviewed H3 segments; explicitly --apply to import and select them.

Example: python3 workflows/astrid_intro_h3_anchor_chain/assemble.py s01.mp4
         s02.mp4 s03.mp4 s04.mp4 s05.mp4 [--apply]

Default preparation creates temporary derived media and a provenance manifest,
but does not import objects or change timelines. Never use raw private CAS paths.

The five inputs may be native generation outputs or explicitly finished
derivatives. With --source-manifest, each input can be pinned to its local
path/hash, raw generation managed object, and optional finishing recipe or
evidence identifiers. The manifest is provenance only; it never authorizes an
unverified object relation.

Canonical row names are ``path``/``sha256``,
``raw_generation_object_id``, ``finishing_recipe_id``, and
``finishing_evidence_ids``. ``sources`` may be an array or a path/hash-keyed
mapping; ``segments`` and ``files`` are accepted aliases for compatibility.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path

PROJECT = "astrid-intro"
PARENT = "2652b5567c8e4e9aa4d35c1df0eb2742"
SOURCE_FRAMES = (175, 260, 175, 175, 294)
FRAMES = (212, 279, 177, 169, 311)
# Child, picture clip, expected old anchor, segment index, source start, length.
SHOTS = (
    ("b0f1f21cfdf3581eb13e0647183cbf3e", "shot_b01", "anchor_shot_v03", 0, 0, 212),
    ("77e146741d20557eb9d4424b4210def7", "shot_b02", "anchor_shot_v04", 1, 0, 96),
    ("5157d8c097cf52b58d3237a47954c86c", "shot_b03", "anchor_shot_v04", 1, 96, 183),
    ("d46d3069475257a1b911a2b5c5630281", "shot_b04", "anchor_shot_v05", 2, 0, 177),
    ("930d51fd99105cd29541171eb3c42a1f", "shot_b05", "v12_mink_pointing", 3, 0, 169),
    ("7c22d84f97c85400ad83de923b6d7380", "shot_b06", "terminal_v1_background", 4, 0, 311),
)


def _normalized_sha256(value):
    """Return a canonical bare SHA-256 or reject a malformed identity."""
    if not isinstance(value, str):
        raise ValueError("source manifest SHA-256 must be a string")
    normalized = value.strip().removeprefix("sha256:").lower()
    if len(normalized) != 64 or any(char not in "0123456789abcdef" for char in normalized):
        raise ValueError(f"invalid SHA-256 identity: {value!r}")
    return normalized


def _manifest_rows(payload):
    """Extract source rows from the accepted source-manifest envelopes."""
    if not isinstance(payload, dict):
        raise ValueError("source manifest must be a JSON object")
    rows = payload.get("sources", payload.get("segments", payload.get("files")))
    if rows is None:
        # Also accept a direct path/hash -> record mapping, keeping envelope
        # metadata keys out of the source rows.
        rows = {
            key: value for key, value in payload.items()
            if key not in {"schema", "project", "metadata"}
        }
    if isinstance(rows, dict):
        converted = []
        for key, value in rows.items():
            if not isinstance(value, dict):
                raise ValueError("source manifest mapping values must be objects")
            row = dict(value)
            if isinstance(key, str) and key.strip().lower().startswith("sha256:"):
                row.setdefault("sha256", key)
            else:
                row.setdefault("path", key)
            converted.append(row)
        rows = converted
    if not isinstance(rows, list) or not rows:
        raise ValueError("source manifest must contain a non-empty sources array")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("source manifest sources must be objects")
    return rows


def _manifest_path_value(row):
    for key in ("source_path", "path", "file", "source"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _manifest_hash_value(row):
    for key in ("source_sha256", "sha256", "content_sha256", "digest"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def load_source_manifest(path, sources):
    """Match every input to one manifest row and verify any supplied hash.

    Matching is by resolved path and/or source hash. A row must identify the
    corresponding input by at least one of those values; ambiguous or missing
    matches fail closed before any runtime import.
    """
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read source manifest {path}: {exc}") from exc
    rows = _manifest_rows(payload)
    source_digests = [digest(source) for source in sources]
    matched = []
    used = set()
    for source, source_digest in zip(sources, source_digests):
        candidates = []
        for index, row in enumerate(rows):
            if index in used:
                continue
            path_value = _manifest_path_value(row)
            hash_value = _manifest_hash_value(row)
            path_match = False
            if path_value is not None:
                declared_path = Path(path_value)
                if not declared_path.is_absolute():
                    declared_path = path.parent / declared_path
                path_match = declared_path.resolve() == source
            hash_match = False
            if hash_value is not None:
                hash_match = _normalized_sha256(hash_value) == source_digest
            if path_match or hash_match:
                candidates.append(index)
        if len(candidates) != 1:
            raise ValueError(
                f"source manifest must match exactly one row for {source}; "
                f"matched {len(candidates)}"
            )
        row_index = candidates[0]
        row = dict(rows[row_index])
        declared_hash = _manifest_hash_value(row)
        if declared_hash is not None and _normalized_sha256(declared_hash) != source_digest:
            raise ValueError(f"source manifest hash mismatch for {source}")
        used.add(row_index)
        row["source_path"] = str(source)
        row["source_sha256"] = f"sha256:{source_digest}"
        matched.append(row)
    return {
        "manifest_path": str(path),
        "schema": payload.get("schema"),
        "sources": matched,
    }


def _object_id(value):
    if isinstance(value, dict):
        for key in ("object_id", "media_id", "managed_object_id", "managed_object", "digest"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _manifest_identity(row, *keys):
    for key in keys:
        value = row.get(key)
        identity = _object_id(value)
        if identity:
            return identity
    return None


def _source_lineage_ids(row):
    """Return explicit managed source/raw ids, never inferred ids."""
    raw = row.get("raw_generation")
    finishing = row.get("finishing")
    raw_id = _manifest_identity(
        row,
        "raw_generation_object_id",
        "raw_generation_media_id",
        "raw_object_id",
        "raw_media_id",
        "raw_generation_id",
    )
    if raw_id is None:
        raw_id = _object_id(raw)
    source_id = _manifest_identity(
        row,
        "source_object_id",
        "source_media_id",
    )
    recipe_id = _manifest_identity(
        row,
        "finishing_recipe_object_id",
        "finishing_recipe_media_id",
        "recipe_object_id",
        "recipe_media_id",
    )
    if recipe_id is None and isinstance(finishing, dict):
        recipe_id = _manifest_identity(finishing, "recipe_object_id", "recipe_media_id", "recipe_id")
        if recipe_id is None:
            recipe_id = _object_id(finishing.get("recipe"))
    evidence = row.get(
        "finishing_evidence_object_ids",
        row.get("finishing_evidence_media_ids", row.get("evidence_ids")),
    )
    if evidence in (None, []) and isinstance(finishing, dict):
        evidence = finishing.get("evidence_object_ids", finishing.get("evidence_media_ids"))
        if evidence is None:
            evidence = finishing.get("evidence", [])
    if isinstance(evidence, (str, dict)):
        evidence = [evidence]
    evidence_ids = [_object_id(item) for item in evidence] if isinstance(evidence, list) else []
    return {
        "source_object_id": source_id,
        "raw_generation_object_id": raw_id,
        "finishing_recipe_id": recipe_id,
        "finishing_evidence_ids": [item for item in evidence_ids if item],
    }


def _relation_key(from_object_id, to_object_id):
    payload = f"{PROJECT}:h3-anchor-chain:derived_from:{from_object_id}:{to_object_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def link_derived_from(client, project, from_object_id, to_object_id, *, role):
    """Create one verified media lineage edge, or record why it was skipped."""
    if not from_object_id or not to_object_id:
        return {"status": "skipped", "role": role, "reason": "missing_managed_id"}
    if from_object_id == to_object_id:
        return {"status": "skipped", "role": role, "reason": "same_object"}
    # media.show is the project-scoped read authority; do not invent an edge
    # from an arbitrary recipe/evidence label or an unregistered digest.
    for object_id in (from_object_id, to_object_id):
        existing = client.media.show(project, object_id)
        if not existing.ok:
            return {
                "status": "skipped",
                "role": role,
                "reason": "managed_object_unavailable",
                "object_id": object_id,
            }
    if not callable(getattr(client.media, "relate", None)):
        return {"status": "skipped", "role": role, "reason": "relation_api_unavailable"}
    result = client.media.relate(
        project,
        from_object_id=from_object_id,
        to_object_id=to_object_id,
        kind="derived_from",
        metadata={"assembly": "astrid-intro-h3-anchor-chain", "role": role},
        idempotency_key=_relation_key(from_object_id, to_object_id),
    )
    if not result.ok:
        return {
            "status": "skipped",
            "role": role,
            "reason": "relation_rejected",
            "error": result.error.as_dict() if result.error is not None else None,
        }
    relation = result.data if isinstance(result.data, dict) else {}
    return {
        "status": "linked",
        "role": role,
        "from_object_id": from_object_id,
        "to_object_id": to_object_id,
        "relation": relation,
    }


def checked(result):
    if not result.ok:
        raise RuntimeError(str(result.error))
    return result.data


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def probe(path):
    result = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames",
        "-of", "json", str(path),
    ]))
    return result["streams"][0]


def timing_filter(count, skip, target):
    return (f"trim=start_frame={skip}:end_frame={count},settb=AVTB,"
            f"setpts=(N*{target-1})/({count-skip-1}*30*TB),"
            "tpad=stop_mode=clone:stop_duration=0.1,fps=30:round=near")


def bridge_filter(target, dx, dy):
    # Perspective in destination mode is an affine translation when all four
    # corners move equally. A generous black pad prevents edge replication,
    # and linear interpolation retains fractional-pixel endpoint placement.
    u = f"clip((on-{target-31})/30,0,1)"
    ease = f"({u})*({u})*(3-2*({u}))"
    x, y = f"({dx})*({ease})", f"({dy})*({ease})"
    return ("format=gbrp,pad=iw+256:ih+256:128:128:color=black,"
            f"perspective=sense=destination:eval=frame:interpolation=linear:"
            f"x0='{x}':y0='{y}':x1='W+{x}':y1='{y}':"
            f"x2='{x}':y2='H+{y}':x3='W+{x}':y3='H+{y}',"
            "crop=1920:1080:128:128")


def bridge_deltas(selections):
    positions = []
    for selection in selections:
        doc = selection["before"]
        clip = next(c for c in doc["config"]["clips"] if c["id"] == selection["clip_id"])
        track = next(t for t in doc["config"]["tracks"] if t["id"] == clip["track"])
        if track.get("fit", "contain") != "contain":
            raise ValueError("Bridge expects current default contain track fit")
        if any(clip.get(k, 0) for k in ("cropTop", "cropBottom", "cropLeft", "cropRight")):
            raise ValueError("Bridge does not support authored crop")
        if clip.get("width", 1920) != 1920 or clip.get("height", 1080) != 1080:
            raise ValueError("Bridge expects full-canvas authored bounds")
        # VisualClip uses full-canvas centered objectFit:contain when unplaced.
        # Our derived 1920x1080 video therefore has effective origin (0,0).
        positions.append((float(clip.get("x", 0)), float(clip.get("y", 0))))
    if positions[1] != positions[2]:
        raise ValueError("Shared segment02 child transforms differ")
    unique = [positions[i] for i in (0, 2, 3, 4, 5)]
    return [(b[0]-a[0], b[1]-a[1]) for a,b in zip(unique, unique[1:])] + [(0,0)]


def conform(source, dest, index, bridge=None):
    info = probe(source)
    count = int(info["nb_read_frames"])
    if count != SOURCE_FRAMES[index] or Fraction(info["avg_frame_rate"]) != 24:
        raise ValueError(f"Unexpected source {source}: {info}; expected {SOURCE_FRAMES[index]} frames at24fps")
    if (info["width"], info["height"]) not in ((1920, 1088), (1920, 1080)):
        raise ValueError(f"Unexpected source canvas: {info}")
    skip = 0 if index == 0 else 39
    target = FRAMES[index]
    # Map FIRST and LAST new source frame to FIRST and LAST target timestamp.
    # Nearest-frame resampling avoids optical-flow inventions in pixel typography.
    # A one-frame cloned tail gives fps the final endpoint's display interval.
    filters = timing_filter(count, skip, target) + ",scale=1920:1080:flags=neighbor,setsar=1"
    if bridge and any(bridge):
        filters += "," + bridge_filter(target, *bridge)
    subprocess.run([
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-an",
        "-vf", filters, "-frames:v", str(target), "-c:v", "libx264",
        "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(dest),
    ], check=True)
    output = probe(dest)
    if int(output["nb_read_frames"]) != target or Fraction(output["avg_frame_rate"]) != 30:
        raise RuntimeError(f"Conform verification failed: {output}")
    return {
        "source_sha256": digest(source), "source_probe": info,
        "discarded_context_frames": skip, "new_source_frames": count-skip,
        "target_frames": target, "target_fps": 30, "filter": filters,
        "output_sha256": digest(dest), "output_probe": output,
        "bridge_translation": {"enabled": bridge is not None, "delta_xy": bridge,
                               "duration_seconds": 1, "easing": "smoothstep"},
        "endpoint_policy": "source new-frame0 and final frame mapped to target0 and final frame",
    }


def parent_check(parent):
    by_child = {c.get("params", {}).get("timeline_document_id"): c
                for c in parent["config"]["clips"] if c.get("clipType") == "shot"}
    cursor = 0
    for ref, _, _, _, _, length in SHOTS:
        clip = by_child[ref]
        if round(clip["at"] * 30) != cursor or round(clip["hold"] * 30) != length:
            raise RuntimeError(f"Parent editorial timing changed for {ref}; review before applying")
        cursor += length


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", nargs=5, type=Path,
                        help="Five native or finished H3 segments, in chain order")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Import verified media and CAS-save six picture selections")
    mode.add_argument("--prepare-only", action="store_true", help="Default: conform only; no runtime mutation")
    parser.add_argument("--bridge-transforms", action="store_true",
                        help="Gradually compensate outgoing placement during its last1sec; default off")
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=None,
        help=(
            "Optional JSON provenance mapping each source path/hash to explicit "
            "managed raw-generation and finishing identities."
        ),
    )
    args = parser.parse_args()
    sources = [p.resolve(strict=True) for p in args.clips]
    source_manifest = None
    if args.source_manifest is not None:
        source_manifest = args.source_manifest.resolve(strict=True)
        if source_manifest in sources:
            raise ValueError("--source-manifest must not also be a source clip")
    stage = Path(tempfile.mkdtemp(prefix="astrid-intro-h3-conform-"))
    outputs = [stage / f"s{i+1:02}-30fps.mp4" for i in range(5)]
    print(f"Staging: {stage}", flush=True)
    manifest = {"schema": "astrid-intro-h3-selection-v1", "project": PROJECT,
                "segments": [], "selections": [], "saved": []}
    manifest_path = stage / "assembly-provenance.json"

    source_records = load_source_manifest(source_manifest, sources) if source_manifest else None
    if source_records is not None:
        manifest["source_manifest"] = source_records

    def persist():
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    from astrid.sdk import AstridClient
    with AstridClient.open_from_launcher() as client:
        parent = checked(client.timelines.show(PROJECT, PARENT))
        parent_check(parent)
        manifest["parent_snapshot"] = parent
        for ref, clip_id, old_asset, segment, start, length in SHOTS:
            doc = checked(client.timelines.show(PROJECT, ref))
            clip = next(c for c in doc["config"]["clips"] if c["id"] == clip_id)
            if clip.get("clipType") != "image" or clip.get("asset") != old_asset:
                raise RuntimeError(f"{clip_id} is no longer the original anchor; inspect current selection")
            manifest["selections"].append({"timeline_id": ref, "clip_id": clip_id,
                "segment": segment, "source_start_frame": start, "frames": length,
                "before": doc})
        persist()
        bridges = bridge_deltas(manifest["selections"]) if args.bridge_transforms else [None]*5
        for i, (source, output) in enumerate(zip(sources, outputs)):
            row = conform(source, output, i, bridges[i])
            row["source_kind"] = (
                source_records["sources"][i].get("source_kind", "source")
                if source_records else "source"
            )
            if source_records:
                row["source_manifest"] = source_records["sources"][i]
                row["lineage"] = _source_lineage_ids(source_records["sources"][i])
            manifest["segments"].append(row)
            persist()
        if not args.apply:
            print(f"Prepared only; review all five clips in {stage}. No runtime mutations.\n{manifest_path}")
            return
        # Re-read before imports and before each save. A concurrent picture edit
        # fails clearly; unrelated changes are merged into the fresh document.
        fresh_parent = checked(client.timelines.show(PROJECT, PARENT))
        parent_check(fresh_parent)
        for i, (source, output) in enumerate(zip(sources, outputs)):
            row = manifest["segments"][i]
            row["source_object"] = checked(client.media.import_file(project=PROJECT, path=source))
            row["conformed_object"] = checked(client.media.import_file(project=PROJECT, path=output))
            if source_records:
                row["lineage"] = _source_lineage_ids(source_records["sources"][i])
            source_object_id = _object_id(row["source_object"])
            conformed_object_id = _object_id(row["conformed_object"])
            row["lineage_relations"] = [link_derived_from(
                client, PROJECT, conformed_object_id, source_object_id, role="source"
            )]
            raw_object_id = row.get("lineage", {}).get("raw_generation_object_id")
            if raw_object_id:
                row["lineage_relations"].append(link_derived_from(
                    client, PROJECT, conformed_object_id, raw_object_id,
                    role="raw_generation"
                ))
            persist()
        # Managed provenance contains original documents for exact restoration,
        # source object identity, conformance, and planned selection boundaries.
        evidence = checked(client.media.import_file(project=PROJECT, path=manifest_path))
        evidence_id = evidence.get("object_id", evidence.get("digest"))
        print(f"Managed pre-selection provenance: {evidence_id}", flush=True)
        for selection in manifest["selections"]:
            ref, clip_id = selection["timeline_id"], selection["clip_id"]
            doc = checked(client.timelines.show(PROJECT, ref))
            config, registry = copy.deepcopy(doc["config"]), copy.deepcopy(doc["registry"])
            clip = next(c for c in config["clips"] if c["id"] == clip_id)
            original = next(c for c in selection["before"]["config"]["clips"] if c["id"] == clip_id)
            if clip != original:
                raise RuntimeError(f"Concurrent picture edit in {ref}; stopped. Prior saves recorded in {manifest_path}")
            i = selection["segment"]
            row = manifest["segments"][i]
            media = row["conformed_object"]
            media_id = media.get("object_id", media.get("digest"))
            key = f"h3_anchor_chain_s{i+1:02}_{row['output_sha256'][:12]}"
            registry["assets"][key] = {"media_id": media_id,
                "content_sha256": row["output_sha256"], "type": "video",
                "resolution": "1920x1080", "duration": FRAMES[i]/30}
            # Keep position, scale, track, id, at and any authored effects.
            clip.pop("hold", None)
            clip.update({"clipType": "media", "asset": key,
                "from": selection["source_start_frame"]/30,
                "to": (selection["source_start_frame"]+selection["frames"])/30,
                "speed": 1, "volume": 0})
            saved = checked(client.timelines.save(PROJECT, ref, config=config,
                registry=registry, expected_version=doc["config_version"]))
            manifest["saved"].append({"timeline_id": ref,
                "before_version": doc["config_version"], "result": saved})
            persist()
        manifest["pre_selection_provenance_object"] = evidence_id
        persist()
        final = checked(client.media.import_file(project=PROJECT, path=manifest_path))
        print(json.dumps({"ok": True, "provenance": final, "staging": str(stage)}, indent=2))


if __name__ == "__main__":
    main()
