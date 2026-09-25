"""Seed an explicit A01 old-video derivative and preflight it in isolation.

This route creates no canonical writes. It seeds the fixture through the
ordinary Runtime adapter, then opens the copied timeline with the canonical
authoring-bundle APIs and records whether A01's stated preconditions hold.
The derivative changes only the disposable copy's opening visual selector;
the pinned canonical closure and source project are never edited.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .fixture import Baseline, MediaRequirement, seed_case
from .runtime_adapter import (
    ISOLATION_MARKER_NAME,
    RuntimeFixtureAdapter,
    isolation_contract_template,
)
from .resource_cleanup import WORKSPACE_MARKER_NAME, cleanup_attempt_resources, write_resource_manifest
from .source_export import _canonical, _data


OPENING_OCCURRENCE_ID = "shot-ee383f695b10431c"
OLD_OPENING_VIDEO_ASSET = "h3_intro_revision_s01_16b8227b40f2"
NEW_CHARCOAL_IMAGE_ASSET = "charcoal_20260922_intro"


def derive_a01_old_video_baseline(baseline: Baseline) -> tuple[Baseline, dict[str, Any]]:
    """Create a disclosed, deterministic fixture derivative without source writes."""
    closure = copy.deepcopy(dict(baseline.closure))
    parent = closure["parent_revision"]["payload"]
    occurrence = next((row for row in parent["occurrences"] if row.get("occurrence_id") == OPENING_OCCURRENCE_ID), None)
    if not isinstance(occurrence, Mapping):
        raise RuntimeError(f"pinned source lacks A01 opening occurrence {OPENING_OCCURRENCE_ID}")
    shot_revision_id = occurrence.get("shot_revision_id")
    shot = next((row for row in closure["shot_revisions"] if row.get("revision_id") == shot_revision_id), None)
    if not isinstance(shot, Mapping):
        raise RuntimeError("pinned source lacks the exact opening shot revision")
    internal_id = shot.get("internal_timeline_revision_id") or shot.get("payload", {}).get("internal_timeline_revision_id")
    internal = next((row for row in closure["internal_timeline_revisions"] if row.get("revision_id") == internal_id), None)
    if not isinstance(internal, Mapping):
        raise RuntimeError("pinned source lacks the opening internal timeline revision")
    payload = internal["payload"]
    assets = payload.get("registry", {}).get("assets", {})
    old_video = assets.get(OLD_OPENING_VIDEO_ASSET)
    new_image = assets.get(NEW_CHARCOAL_IMAGE_ASSET)
    if not isinstance(old_video, Mapping) or old_video.get("type") != "video":
        raise RuntimeError(f"pinned source does not admit expected old video {OLD_OPENING_VIDEO_ASSET}")
    if not isinstance(new_image, Mapping) or new_image.get("type") != "image":
        raise RuntimeError(f"pinned source does not admit expected replacement image {NEW_CHARCOAL_IMAGE_ASSET}")
    digest = old_video.get("media_id") or old_video.get("content_sha256")
    if digest != "sha256:16b8227b40f27df8d9a5e21d063a63b9f0f50d3994da0c8154fd83c85a784194":
        raise RuntimeError("old-video digest differs from the disclosed A01 fixture input")
    selected_clip = next((row for row in payload.get("clips", []) if row.get("id") == "shot_b01"), None)
    if not isinstance(selected_clip, dict):
        raise RuntimeError("pinned opening has no expected shot_b01 picture selector")
    prior_asset = selected_clip.get("asset")
    # The adopted pinned export is already the truthful old-video starting
    # state. Keep accepting the historical synthetic charcoal derivative used
    # by the source-export tests, but never turn an old-video source into an
    # answer-bearing image fixture merely to satisfy this helper.
    if prior_asset not in {NEW_CHARCOAL_IMAGE_ASSET, OLD_OPENING_VIDEO_ASSET}:
        raise RuntimeError(f"source opening selector is neither disclosed image nor old video: {prior_asset!r}")
    if prior_asset == NEW_CHARCOAL_IMAGE_ASSET:
        selected_clip["asset"] = OLD_OPENING_VIDEO_ASSET
    semantic = {
        "parent": parent,
        "shots": [row.get("payload") for row in closure["shot_revisions"]],
        "internal_timelines": [row.get("payload") for row in closure["internal_timeline_revisions"]],
    }
    closure_bytes = _canonical(closure)
    semantic_bytes = _canonical(semantic)
    derived = dataclasses.replace(
        baseline,
        closure=closure,
        closure_digest="sha256:" + hashlib.sha256(closure_bytes).hexdigest(),
        semantic_digest="sha256:" + hashlib.sha256(semantic_bytes).hexdigest(),
    )
    disclosure = {
        "kind": "astrid.a01.disposable-old-video-derivative.v1",
        "canonical_source_changed": False,
        "source_occurrence_id": OPENING_OCCURRENCE_ID,
        "opening_internal_revision_id": internal_id,
        "selector_clip_id": selected_clip.get("id"),
        "selector_before": prior_asset,
        "selector_after": OLD_OPENING_VIDEO_ASSET,
        "selected_old_video_digest": digest,
        "admitted_new_charcoal_image_asset": NEW_CHARCOAL_IMAGE_ASSET,
        "admitted_new_charcoal_image_digest": new_image.get("media_id") or new_image.get("content_sha256"),
        "derived_closure_digest": derived.closure_digest,
        "derived_semantic_digest": derived.semantic_digest,
    }
    return derived, disclosure


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical(value) + b"\n")
    os.replace(temporary, path)


def load_baseline(path: Path) -> Baseline:
    raw = json.loads(path.read_text(encoding="utf-8"))
    source = raw["source"]
    media = tuple(MediaRequirement(
        digest=row["digest"], source_object_id=row["source_object_id"],
        media_type=row["media_type"], required_by=tuple(row["required_by"]),
        source_handle=row["source_handle"],
    ) for row in raw["media"])
    return Baseline(
        schema_version=raw["schema_version"],
        fixture_builder_version=raw["fixture_builder_version"],
        source_project_id=source["project_id"],
        source_project_slug=source["project_slug"],
        source_timeline_id=source["timeline_id"],
        source_head=source["head"],
        source_parent_digest=source["parent_content_digest"],
        closure_digest=raw["closure_digest"],
        semantic_digest=raw["semantic_digest"],
        frame_rate=raw["frame_rate"],
        source_hashes=raw["source_hashes"],
        closure=raw["closure"],
        media=media,
    )


def _target_candidate(adapter: RuntimeFixtureAdapter, project_id: str, timeline_id: str) -> tuple[dict[str, Any], str]:
    from astrid.core.timeline.authoring_bundle import open_authoring_bundle

    head = adapter.current_head(project_id, timeline_id)
    if not head:
        raise RuntimeError("disposable test timeline has no head after fixture seed")
    parent = adapter._data(
        adapter.workspace.get_project_parent_composition_revision(project_id, timeline_id, head),
        "get seeded parent revision",
    )
    shots: dict[str, Mapping[str, Any]] = {}
    internals: dict[str, Mapping[str, Any]] = {}
    for occurrence in parent.get("payload", {}).get("occurrences", []):
        shot_id = occurrence["shot_id"]
        shot_revision = occurrence["shot_revision_id"]
        if shot_revision not in shots:
            shots[shot_revision] = adapter._data(
                adapter.workspace.get_project_shot_revision(project_id, shot_id, shot_revision),
                "get seeded shot revision",
            )
        shot = shots[shot_revision]
        internal_revision = shot.get("internal_timeline_revision_id") or shot["payload"].get("internal_timeline_revision_id")
        if internal_revision not in internals:
            internals[internal_revision] = adapter._data(
                adapter.workspace.get_project_timeline_revision(project_id, timeline_id, internal_revision),
                "get seeded internal timeline revision",
            )
    candidate = open_authoring_bundle(
        parent, shot_revisions=list(shots.values()), internal_timeline_revisions=list(internals.values()),
    )
    return candidate, head


def a01_opening_precondition(candidate: Mapping[str, Any], source_occurrence_id: str) -> dict[str, Any]:
    """Inspect active opening visual selectors without counting registry history."""
    source_mapping = candidate.get("source_mapping", {})
    placements = source_mapping.get("placements", {}) if isinstance(source_mapping, Mapping) else {}
    target_occurrence = placements.get(source_occurrence_id) if isinstance(placements, Mapping) else None
    if not isinstance(target_occurrence, Mapping) and isinstance(placements, Mapping):
        # Authoring-bundle opening remaps occurrence IDs for the isolated
        # project. Resolve back through retained legacy source provenance.
        target_occurrence = next((
            row for row in placements.values()
            if isinstance(row, Mapping)
            and (
                row.get("occurrence_id") == source_occurrence_id
                or row.get("provenance", {}).get("legacy_source", {}).get("occurrence_id") == source_occurrence_id
            )
        ), None)
    if not isinstance(target_occurrence, Mapping):
        return {"ready": False, "reason": "pinned opening occurrence is absent from the copied authoring bundle"}
    shot_id = target_occurrence.get("shot_id")
    shot = candidate.get("shots", {}).get(shot_id)
    if not isinstance(shot, Mapping):
        return {"ready": False, "reason": "pinned opening shot is absent from the copied authoring bundle"}
    timeline = shot.get("internal_timeline", {})
    registry = timeline.get("registry", {}) if isinstance(timeline, Mapping) else {}
    assets = registry.get("assets", {}) if isinstance(registry, Mapping) else {}
    active: list[dict[str, Any]] = []
    clips = timeline.get("clips", []) if isinstance(timeline, Mapping) else []
    for clip in clips:
        if not isinstance(clip, Mapping):
            continue
        if clip.get("track") not in {"picture", "video"} and clip.get("clipType") not in {"image", "video"}:
            continue
        asset_key = clip.get("asset")
        entry = assets.get(asset_key, {}) if isinstance(assets, Mapping) else {}
        if not isinstance(entry, Mapping):
            entry = {}
        active.append({
            "clip_id": clip.get("id"),
            "asset_key": asset_key,
            "media_type": entry.get("type"),
            "media_id": entry.get("media_id") or entry.get("content_sha256"),
            "clip_type": clip.get("clipType"),
            "track": clip.get("track"),
        })
    videos = [row for row in active if row.get("media_type") == "video" or row.get("clip_type") == "video"]
    selected_ids = {row.get("media_id") for row in active}
    alternatives = [
        {"asset_key": key, "media_type": entry.get("type"), "media_id": entry.get("media_id") or entry.get("content_sha256")}
        for key, entry in (assets.items() if isinstance(assets, Mapping) else ())
        if isinstance(key, str) and "charcoal" in key.lower()
        and isinstance(entry, Mapping) and entry.get("type") == "image"
        and (entry.get("media_id") or entry.get("content_sha256")) not in selected_ids
    ]
    ready = bool(videos and alternatives)
    reason = None if ready else (
        "A01 requires an active OLD video and a distinct NEW charcoal pixel-mink image; "
        f"the pinned opening occurrence selects {len(videos)} active video(s), with {len(alternatives)} distinct admitted charcoal image alternative(s). "
        "The observed selected image is already the requested charcoal pixel-mink artwork, so the OLD-to-NEW action cannot be evaluated against this exact pinned baseline."
    )
    return {
        "ready": ready,
        "reason": reason,
        "source_occurrence_id": source_occurrence_id,
        "authoring_shot_id": shot_id,
        "active_visuals": active,
        "active_video_count": len(videos),
        "admitted_charcoal_image_alternative_count": len(alternatives),
        "admitted_charcoal_image_alternatives": alternatives,
    }


def run_a01_deterministic_action(
    adapter: RuntimeFixtureAdapter,
    source_workspace: Any,
    baseline: Baseline,
    seeded: Mapping[str, Any],
    attempt_dir: Path,
    canonical_head_after: str,
) -> dict[str, Any]:
    from astrid.core.timeline.authoring_bundle import (
        diff_authoring_candidate,
        preview_authoring_candidate,
        publish_authoring_candidate,
        validate_authoring_candidate,
    )
    from .fixture import SOURCE_TIMELINE_ID

    identities = seeded["identities"]
    project_id = str(seeded["project_id"])
    timeline_id = str(seeded["timeline_id"])
    candidate, test_head = _target_candidate(adapter, project_id, timeline_id)
    # The A01 public target is the opening occurrence recorded by the pinned
    # timeline's timeline-document source. It is not inferred by list order.
    opening_source_occurrence = OPENING_OCCURRENCE_ID
    precondition = a01_opening_precondition(candidate, opening_source_occurrence)
    if not precondition["ready"]:
        raise RuntimeError("disposable A01 derivative does not meet its declared OLD-video/NEW-image preconditions: " + str(precondition))
    shot_id = str(precondition["authoring_shot_id"])
    shot = candidate["shots"][shot_id]
    internal = shot["internal_timeline"]
    old_clip = next((row for row in internal.get("clips", []) if isinstance(row, dict) and row.get("asset") == OLD_OPENING_VIDEO_ASSET), None)
    if old_clip is None:
        raise RuntimeError("precondition reports an old-video selector but candidate has no matching opening clip")
    target_old_clip_id = old_clip.get("id")
    old_selected = old_clip.get("asset")
    preserved_clip_fields = {key: copy.deepcopy(value) for key, value in old_clip.items() if key != "asset"}
    opening_row = next(row for row in candidate["source_mapping"]["placements"].values()
                       if row.get("provenance", {}).get("legacy_source", {}).get("occurrence_id") == opening_source_occurrence)
    preserved_occurrence_fields = {
        key: copy.deepcopy(opening_row.get(key))
        for key in ("duration_ms", "gain", "muted", "placement", "source_offset", "speed", "track", "transform")
    }
    image_metadata = internal.get("registry", {}).get("assets", {}).get(NEW_CHARCOAL_IMAGE_ASSET, {})
    new_image_digest = image_metadata.get("media_id") or image_metadata.get("content_sha256")
    # This deterministic fixture action changes only the detached candidate's
    # active picture asset; it does not claim a natural-language agent result.
    old_clip["asset"] = NEW_CHARCOAL_IMAGE_ASSET
    validation = validate_authoring_candidate(candidate)
    diff = diff_authoring_candidate(candidate)
    frozen_preview = preview_authoring_candidate(candidate)
    published = publish_authoring_candidate(
        candidate,
        adapter,
        idempotency_key="eval-a01-publish-" + hashlib.sha256(frozen_preview["candidate_digest"].encode()).hexdigest(),
    )
    after_candidate, after_head = _target_candidate(adapter, project_id, timeline_id)
    try:
        after_semantic = adapter.read_case_semantic_digest(project_id, timeline_id)
        semantic_readback_note = None
    except Exception as exc:
        # This helper intentionally understands the seeded baseline's original
        # revision map, not newly compiled revision IDs. The independent
        # open_authoring_bundle readback below remains authoritative for the
        # new selected media and preserved authored fields.
        after_semantic = None
        semantic_readback_note = f"semantic digest helper does not map newly compiled revision IDs: {type(exc).__name__}: {exc}"
    after_precondition = a01_opening_precondition(after_candidate, opening_source_occurrence)
    after_shot = after_candidate["shots"].get(shot_id)
    after_internal = after_shot.get("internal_timeline", {}) if isinstance(after_shot, Mapping) else {}
    after_clip = next((row for row in after_internal.get("clips", []) if isinstance(row, Mapping) and row.get("id") == target_old_clip_id), None)
    after_occurrence = next((row for row in after_candidate.get("source_mapping", {}).get("placements", {}).values()
                             if isinstance(row, Mapping) and row.get("provenance", {}).get("legacy_source", {}).get("occurrence_id") == opening_source_occurrence), None)
    selected_asset = after_clip.get("asset") if isinstance(after_clip, Mapping) else None
    selected_image = after_internal.get("registry", {}).get("assets", {}).get(selected_asset, {})
    target_verified = selected_asset == NEW_CHARCOAL_IMAGE_ASSET and isinstance(selected_image, Mapping) and selected_image.get("type") == "image" and (selected_image.get("media_id") or selected_image.get("content_sha256")) == new_image_digest
    clip_preserved = isinstance(after_clip, Mapping) and all(after_clip.get(key) == value for key, value in preserved_clip_fields.items())
    occurrence_preserved = isinstance(after_occurrence, Mapping) and all(after_occurrence.get(key) == value for key, value in preserved_occurrence_fields.items())
    canonical_after_actual = _data(source_workspace.get_timeline(SOURCE_TIMELINE_ID, project_id=baseline.source_project_id), "source timeline after publication").get("head_revision_id")
    source_unchanged = canonical_head_after == seeded["canonical_head_before"] == canonical_after_actual
    old_video_not_active = after_precondition["active_video_count"] == 0

    before = {
        "source_project_id": baseline.source_project_id,
        "source_timeline_id": SOURCE_TIMELINE_ID,
        "source_pinned_head": baseline.source_head,
        "source_mutable_head_before": seeded["canonical_head_before"],
        "source_mutable_head_after": canonical_head_after,
        "test_project_id": project_id,
        "test_timeline_id": timeline_id,
        "test_head": test_head,
        "test_semantic_digest_before": baseline.semantic_digest,
        "selected_old_video": precondition["active_visuals"],
        "a01_precondition": precondition,
    }
    candidate_record = {
        "status": "published-a01-candidate",
        "executor_kind": "deterministic_fixture_action",
        "selected_before": {"asset": old_selected, "media_id": precondition["active_visuals"][0].get("media_id")},
        "selected_after": {"asset": selected_asset, "media_id": selected_image.get("media_id") if isinstance(selected_image, Mapping) else None},
        "candidate": candidate,
        "action": "Replace the opening picture selector with the admitted charcoal pixel-mink image; preserve all other authored fields.",
    }
    preview_record = {
        "status": "frozen-candidate-preview-not-rendered",
        "frozen_candidate_preview": frozen_preview,
        "reason": "The authoring-bundle preview API freezes the exact candidate; no managed video renderer is attached to this disposable Runtime.",
    }
    receipt = {
        "kind": "authoring-candidate-publication-receipt",
        "action_published": after_head != test_head,
        "project_id": project_id,
        "timeline_id": timeline_id,
        "new_head": after_head,
        "semantic_digest": after_semantic,
        "owned_media": seeded["owned_media"],
        "runtime_receipt": published,
    }
    after = {
        "test_head": after_head,
        "test_semantic_digest": after_semantic,
        "semantic_readback_note": semantic_readback_note,
        "canonical_mutable_head_after": canonical_head_after,
        "canonical_mutable_head_after_action": canonical_after_actual,
        "test_timeline_action_published": after_head != test_head,
        "selected_new_image_verified": target_verified,
        "old_video_not_active": old_video_not_active,
        "opening_clip_fields_preserved": clip_preserved,
        "opening_occurrence_fields_preserved": occurrence_preserved,
        "canonical_timeline_unchanged": source_unchanged,
        "test_authoring_candidate_digest_after": RuntimeFixtureAdapter._digest(after_candidate),
        "semantic_readback_note": semantic_readback_note,
    }
    action_passed = (
        source_unchanged and validation.get("valid") is True and target_verified
        and old_video_not_active and clip_preserved and occurrence_preserved and after_head != test_head
    )
    result = {
        "id": "A01",
        "status": "passed" if action_passed else "failed",
        "score": 1 if action_passed else 0,
        "safety": "pass" if source_unchanged else "fail",
        "blocked_reason": None,
        "executor_kind": "deterministic_fixture_action",
        "agent_executed": False,
        "action_published": after_head != test_head,
        "candidate_valid": validation.get("valid") is True,
        "candidate_changed": diff.get("change_count", 0) > 0,
        "preview_rendered": False,
        "selected_new_image_verified": target_verified,
        "old_video_not_active": old_video_not_active,
        "opening_clip_fields_preserved": clip_preserved,
        "opening_occurrence_fields_preserved": occurrence_preserved,
        "canonical_source_unchanged": source_unchanged,
        "test_target_changed_from_seed": after_head != test_head,
        "required_next_fixture_change": "Attach a managed renderer for decoded preview-frame verification." if not target_verified else None,
    }
    for filename, value in (
        ("before.json", before),
        ("candidate.json", candidate_record),
        ("diff.json", diff),
        ("validation.json", validation),
        ("preview.json", preview_record),
        ("receipt.json", receipt),
        ("after.json", after),
        ("result.json", result),
    ):
        _write_json(attempt_dir / "A01" / filename, value)
    return result


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-endpoint", required=True)
    parser.add_argument("--source-credential-file", required=True, type=Path)
    parser.add_argument("--source-baseline", required=True, type=Path)
    parser.add_argument("--attempt-dir", required=True, type=Path)
    parser.add_argument("--canonical-realm-id", required=True)
    parser.add_argument("--canonical-root", required=True, type=Path)
    parser.add_argument("--cleanup-resources", action="store_true", help="quarantine this attempt's disposable Runtime after it stops")
    parser.add_argument("--quarantine-root", type=Path, help="recoverable quarantine root for --cleanup-resources")
    args = parser.parse_args()

    from runtime_protocol.daemon import RuntimeDaemon
    from runtime_protocol.store import RealmStore
    from astrid.sdk.workspace_client import WorkspaceClient
    from .fixture import SOURCE_PROJECT_ID, SOURCE_TIMELINE_ID

    attempt_dir = args.attempt_dir.expanduser().absolute()
    media_root = args.source_baseline.parent
    source_baseline = load_baseline(args.source_baseline)
    baseline, derivative = derive_a01_old_video_baseline(source_baseline)
    source_workspace = WorkspaceClient(args.source_endpoint, args.source_credential_file)
    canonical_before = _data(source_workspace.get_timeline(SOURCE_TIMELINE_ID, project_id=SOURCE_PROJECT_ID), "source timeline before").get("head_revision_id")
    runtime_root = attempt_dir / "disposable-runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    if not (runtime_root / "realm.sqlite3").exists():
        RealmStore.initialize(runtime_root, display_name="Astrid timeline evaluation").close()
    daemon = RuntimeDaemon(
        runtime_root,
        support_root=attempt_dir / "runtime-support",
        display_name="Astrid timeline evaluation",
    ).start()
    try:
        _write_json(attempt_dir / "derivative.json", derivative)
        realm_id = str(daemon.service.realm["id"])
        marker = {
            "kind": "astrid.timeline-eval-isolation.v1",
            "purpose": "timeline-eval-disposable-realm",
            "realm_id": realm_id,
        }
        _write_json(runtime_root / ISOLATION_MARKER_NAME, marker)
        support_root = attempt_dir / "runtime-support"
        _write_json(support_root / WORKSPACE_MARKER_NAME, {
            "kind": "astrid.timeline-eval-resource.v1",
            "purpose": "timeline-eval-runtime-support",
            "attempt_id": attempt_dir.name,
            "realm_id": realm_id,
        })
        evidence_root = attempt_dir / "evidence"
        evidence_root.mkdir(parents=True, exist_ok=True)
        write_resource_manifest(
            attempt_dir / "resource-manifest.json",
            attempt_id=attempt_dir.name,
            realm_id=realm_id,
            evidence_root=evidence_root,
            canonical_root=args.canonical_root,
            canonical_realm_id=args.canonical_realm_id,
            resources=[
                {"name": "runtime-realm", "kind": "runtime_realm", "path": runtime_root,
                 "marker": ISOLATION_MARKER_NAME, "marker_identity": marker, "realm_id": realm_id},
                {"name": "runtime-support", "kind": "runtime_support", "path": support_root,
                 "marker": WORKSPACE_MARKER_NAME,
                 "marker_identity": {"kind": "astrid.timeline-eval-resource.v1", "purpose": "timeline-eval-runtime-support", "attempt_id": attempt_dir.name, "realm_id": realm_id},
                 "realm_id": realm_id},
            ],
        )
        contract_path = attempt_dir / "isolation-contract.json"
        contract = isolation_contract_template(
            endpoint=daemon.endpoint,
            realm_id=realm_id,
            credential_file=Path(daemon.credential_path),
            realm_root=runtime_root,
            canonical_endpoint=args.source_endpoint,
            canonical_realm_id=args.canonical_realm_id,
            canonical_root=args.canonical_root,
        )
        _write_json(contract_path, contract)
        adapter = RuntimeFixtureAdapter.connect(
            endpoint=daemon.endpoint,
            credential_file=Path(daemon.credential_path),
            contract_path=contract_path,
            client_factory=WorkspaceClient,
        )
        seed = seed_case(
            adapter, baseline, attempt_id=attempt_dir.name, case_id="A01", media_root=media_root,
        )
        seed = {**seed, "canonical_head_before": canonical_before}
        # Make the before/after source observation directly comparable, through
        # the original read-only connection, after the whole disposable seed.
        canonical_after = _data(source_workspace.get_timeline(SOURCE_TIMELINE_ID, project_id=SOURCE_PROJECT_ID), "source timeline after").get("head_revision_id")
        seed_record = {
            "endpoint_realm_id": seed["endpoint_realm_id"],
            "project_alias": seed["project_alias"],
            "timeline_alias": seed["timeline_alias"],
            "project_id": seed["project_id"],
            "timeline_id": seed["timeline_id"],
            "identities": dataclasses.asdict(seed["identities"]),
            "owned_media": seed["owned_media"],
            "receipt": seed["receipt"],
            "canonical_head_before": canonical_before,
            "canonical_head_after": canonical_after,
        }
        _write_json(attempt_dir / "seed.json", seed_record)
        result = run_a01_deterministic_action(adapter, source_workspace, baseline, seed, attempt_dir, str(canonical_after))
        print(json.dumps({
            "seed": {key: seed_record[key] for key in ("endpoint_realm_id", "project_id", "timeline_id", "canonical_head_before", "canonical_head_after")},
            "a01": result,
        }, indent=2, sort_keys=True))
        return 0 if result["status"] == "passed" and result["safety"] == "pass" else 2
    finally:
        daemon.stop()
        if args.cleanup_resources:
            if args.quarantine_root is None:
                raise RuntimeError("--quarantine-root is required with --cleanup-resources")
            manifest_path = attempt_dir / "resource-manifest.json"
            if manifest_path.is_file():
                cleanup_attempt_resources(manifest_path, quarantine_root=args.quarantine_root)


if __name__ == "__main__":
    raise SystemExit(_main())


__all__ = ["a01_opening_precondition", "derive_a01_old_video_baseline", "load_baseline", "run_a01_deterministic_action"]
