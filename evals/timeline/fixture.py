"""Pinned, isolated fixture contract for the Astrid timeline action evals.

This module deliberately separates canonical-source export from disposable
Runtime seeding.  The adapter is a narrow seam for E04 to bind to the existing
Runtime client; no function here can write to the canonical project.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


FIXTURE_BUILDER_VERSION = "astrid-timeline-fixture-v1"
SUITE_VERSION = "astrid-timeline-eval-v1"
SOURCE_PROJECT_ID = "61d1078d029e42a9af8540c0d5647ae3"
SOURCE_PROJECT_SLUG = "astrid-intro"
SOURCE_TIMELINE_ID = "2652b5567c8e4e9aa4d35c1df0eb2742"
EXPECTED_SOURCE_HEAD = (
    "authoring-parent-revision-40593333b299b3de0bc4789f9b65a1e638bba745e4729b7ca6602c7e56824e2c"
)
ACTION_CASES = tuple(f"A{i:02d}" for i in range(1, 11))

# These are public semantic locators, not answers.  The source IDs are used
# only while seeding to translate the locator to server-assigned disposable
# IDs.  The expected replacement digest remains in the private action
# manifest and is never placed in the agent-visible target package.
_PUBLIC_TARGETS: Mapping[str, Mapping[str, Any]] = {
    "A01": {
        "role": "opening-shot-active-picture",
        "readback_projection": "active_media_replacement.v1",
        "source_occurrence_id": "shot-ee383f695b10431c",
        "source_shot_id": "5024db66-8472-5eeb-8fba-bd05bac13337",
        "selector_clip_id": "shot_b01",
        # Public semantic handle for the admitted replacement.  The hidden
        # expected digest remains private; the agent must resolve this key via
        # the disposable Runtime before calling the edit route.
        "replacement_asset_key": "charcoal_20260922_intro",
        "replacement_role": "charcoal-pixel-mink-image",
        "voice_clip_id": "vo_b01",
        "frame_overlay_clip_id": "canonical_tight_frame_overlay_v1",
        "preserve_roles": ["timing", "voiceover", "frame-overlay"],
    },
}


class FixtureError(ValueError):
    """Fixture inputs or Runtime isolation do not satisfy the eval contract."""


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:32]


@dataclass(frozen=True)
class MediaRequirement:
    """Content needed by the closure and its explicit destination ownership."""

    digest: str
    source_object_id: str
    media_type: str
    required_by: tuple[str, ...]
    # Relative to one eval attempt's media directory; never a canonical path.
    source_handle: str


@dataclass(frozen=True)
class Baseline:
    schema_version: int
    fixture_builder_version: str
    source_project_id: str
    source_project_slug: str
    source_timeline_id: str
    source_head: str
    source_parent_digest: str
    closure_digest: str
    semantic_digest: str
    frame_rate: Mapping[str, int]
    source_hashes: Mapping[str, str]
    closure: Mapping[str, Any]
    media: tuple[MediaRequirement, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fixture_builder_version": self.fixture_builder_version,
            "source": {
                "project_id": self.source_project_id,
                "project_slug": self.source_project_slug,
                "timeline_id": self.source_timeline_id,
                "head": self.source_head,
                "parent_content_digest": self.source_parent_digest,
            },
            "closure_digest": self.closure_digest,
            "semantic_digest": self.semantic_digest,
            "frame_rate": dict(self.frame_rate),
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "closure": self.closure,
            "media": [
                {
                    "digest": row.digest,
                    "source_object_id": row.source_object_id,
                    "media_type": row.media_type,
                    "required_by": list(row.required_by),
                    "source_handle": row.source_handle,
                    "ownership": "must_be_ingested_or_verified_in_destination_project",
                }
                for row in self.media
            ],
        }


def export_baseline(
    *,
    project_id: str,
    project_slug: str,
    timeline_id: str,
    observed_head: str,
    parent_revision: Mapping[str, Any],
    shot_revisions: Sequence[Mapping[str, Any]],
    internal_timeline_revisions: Sequence[Mapping[str, Any]],
    media: Sequence[MediaRequirement],
    frame_rate: Mapping[str, int],
    source_hashes: Mapping[str, str],
) -> Baseline:
    """Freeze a previously read exact closure; fail closed on changed source.

    The caller is the sole source reader and must fetch children by the exact
    parent dependency manifest. This function never consults mutable child heads.
    """
    if (project_id, project_slug, timeline_id) != (
        SOURCE_PROJECT_ID, SOURCE_PROJECT_SLUG, SOURCE_TIMELINE_ID
    ):
        raise FixtureError("source must be the recorded Astrid intro project and timeline")
    if observed_head != EXPECTED_SOURCE_HEAD:
        raise FixtureError(
            f"source head changed: expected {EXPECTED_SOURCE_HEAD}, observed {observed_head}; "
            "refusing to silently rebase fixture"
        )
    if parent_revision.get("revision_id") != observed_head:
        raise FixtureError("parent read is not the exact observed source head")
    if parent_revision.get("project_id") != project_id or parent_revision.get("timeline_id") != timeline_id:
        raise FixtureError("parent revision belongs to a different project or timeline")
    if not (isinstance(frame_rate.get("numerator"), int) and isinstance(frame_rate.get("denominator"), int)):
        raise FixtureError("frame_rate must explicitly provide integer numerator and denominator")
    if frame_rate["numerator"] <= 0 or frame_rate["denominator"] <= 0:
        raise FixtureError("frame_rate must be positive")
    if not source_hashes:
        raise FixtureError("source_hashes are required for reproducible export")
    closure = {
        "parent_revision": dict(parent_revision),
        "shot_revisions": sorted((dict(row) for row in shot_revisions), key=lambda row: row["revision_id"]),
        "internal_timeline_revisions": sorted(
            (dict(row) for row in internal_timeline_revisions), key=lambda row: row["revision_id"]
        ),
    }
    for key, rows in (("shot_revisions", closure["shot_revisions"]), ("internal_timeline_revisions", closure["internal_timeline_revisions"])):
        if not rows:
            raise FixtureError(f"exact closure is missing {key}")
    parent_digest = str(parent_revision.get("content_digest") or "")
    if not parent_digest.startswith("sha256:"):
        raise FixtureError("parent revision has no verified content digest")
    semantic = {
        "parent": parent_revision.get("payload"),
        "shots": [row.get("payload") for row in closure["shot_revisions"]],
        "internal_timelines": [row.get("payload") for row in closure["internal_timeline_revisions"]],
    }
    return Baseline(
        schema_version=1,
        fixture_builder_version=FIXTURE_BUILDER_VERSION,
        source_project_id=project_id,
        source_project_slug=project_slug,
        source_timeline_id=timeline_id,
        source_head=observed_head,
        source_parent_digest=parent_digest,
        closure_digest=_digest(closure),
        semantic_digest=_digest(semantic),
        frame_rate=dict(frame_rate),
        source_hashes=dict(source_hashes),
        closure=closure,
        media=tuple(sorted(media, key=lambda row: row.digest)),
    )


@dataclass(frozen=True)
class CaseIdentities:
    case_id: str
    project_alias: str
    timeline_alias: str
    project_id: str
    timeline_id: str
    parent_revision_id: str
    occurrence_ids: Mapping[str, str]
    shot_ids: Mapping[str, str]
    shot_revision_ids: Mapping[str, str]
    item_ids: Mapping[str, str]
    internal_timeline_ids: Mapping[str, str]
    internal_revision_ids: Mapping[str, str]

    def all_child_ids(self) -> frozenset[str]:
        return frozenset(
            [*self.occurrence_ids.values(), *self.shot_ids.values(), *self.shot_revision_ids.values(),
             *self.item_ids.values(), *self.internal_timeline_ids.values(), *self.internal_revision_ids.values()]
        )


def public_target_receipt(
    seed: Mapping[str, Any], *, read_only: bool = False,
) -> dict[str, Any]:
    """Return the minimal case target package safe to expose to an agent.

    The receipt contains only the server-assigned disposable target and its
    child identities. It intentionally omits the baseline closure, expected
    answers, hidden checks, sibling cases, and source paths. The coordinator
    writes this after seeding; agents never discover a target from ambient
    Runtime configuration.
    """
    identities = seed.get("identities")
    if not isinstance(identities, CaseIdentities):
        raise FixtureError("seed receipt has no CaseIdentities")
    project_id = seed.get("project_id")
    timeline_id = seed.get("timeline_id")
    head = seed.get("receipt", {}).get("new_head") if isinstance(seed.get("receipt"), Mapping) else None
    endpoint_url = seed.get("endpoint_url")
    if not all(isinstance(value, str) and value for value in (endpoint_url, project_id, timeline_id, head)):
        raise FixtureError("seed receipt must include endpoint_url, project_id, timeline_id, and new_head")
    locator = seed.get("target_locator")
    a01_route_available = (
        not read_only
        and identities.case_id == "A01"
        and isinstance(locator, Mapping)
        and all(locator.get(key) for key in ("occurrence_id", "selector_clip_id", "replacement_asset_key"))
    )
    edit_capability = (
        {"status": "available", "route": "timelines replace-parent-media"}
        if a01_route_available
        else {
            "status": "unavailable" if not read_only else "not_permitted",
            "reason": (
                f"No case-specific publication route is admitted for {identities.case_id}. "
                "Only the A01 receipt can currently declare timelines replace-parent-media; "
                "do not infer an action route from the general authoring-bundle helpers."
                if not read_only
                else "This navigation case is read-only."
            ),
        }
    )
    receipt = {
        "kind": "astrid.timeline-eval.public-target.v1",
        "case_id": identities.case_id,
        "scope": "selected-case-only",
        "representation": "parent_composition",
        "capabilities": {
            "inspect": {"status": "available", "route": "timelines show / timelines visualize"},
            "edit": edit_capability,
        },
        "connection": {
            "endpoint_env": "ASTRID_TIMELINE_EVAL_ENDPOINT",
            "credential_env": "ASTRID_TIMELINE_EVAL_CREDENTIAL",
            "source_access": "false",
        },
        "read_only": bool(read_only),
        "endpoint": endpoint_url,
        "project_id": project_id,
        "timeline_id": timeline_id,
        "head_revision_id": head,
        "occurrence_ids": sorted(identities.occurrence_ids.values()),
        "shot_ids": sorted(identities.shot_ids.values()),
        "shot_revision_ids": sorted(identities.shot_revision_ids.values()),
        "item_ids": sorted(identities.item_ids.values()),
        "internal_timeline_ids": sorted(identities.internal_timeline_ids.values()),
        "internal_revision_ids": sorted(identities.internal_revision_ids.values()),
        "owned_media_ids": sorted(str(value) for value in seed.get("owned_media", {}).values()),
    }
    if read_only:
        # A navigation receipt observes the whole exact closure. It does not
        # inherit the active-media replacement projection or A01 role checks.
        receipt["readback_projection"] = "exact_closure_navigation.v1"
    if isinstance(locator, Mapping):
        receipt["target_locator"] = dict(locator)
    if a01_route_available:
        # Keep the convenient legacy field only when the exact A01 locator is
        # present. Other seeded parent compositions must not appear writable
        # through a route whose target contract they do not satisfy.
        receipt["edit_route"] = "timelines replace-parent-media"
    return receipt


def materialize_public_navigation_entrypoint(
    case_id: str, *, fixture_root: Path, destination: Path,
) -> dict[str, Any]:
    """Copy only a selected navigation case's pinned public inputs.

    No suite, grader, or sibling-case data is copied into the worker directory.
    The offline copy is read-only by contract and reset by discarding this
    selected-case directory and materializing it again from the pinned export.
    """
    fixture_root = fixture_root.expanduser().absolute()
    manifest_path = fixture_root / "informational" / "fixture.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest.get("cases", [])
    row = next((value for value in cases if isinstance(value, Mapping) and value.get("id") == case_id), None)
    if not isinstance(row, Mapping):
        raise FixtureError(f"navigation case {case_id} has no pinned public fixture entry")
    targets = manifest.get("targets", {})
    aliases = row.get("targets", [])
    if not isinstance(aliases, list) or not aliases:
        raise FixtureError(f"navigation case {case_id} has no selected target aliases")
    selected: dict[str, Any] = {}
    for alias in aliases:
        if not isinstance(alias, str):
            raise FixtureError(f"navigation case {case_id} has a malformed target alias")
        cursor: Any = targets
        for part in alias.split("."):
            cursor = cursor.get(part) if isinstance(cursor, Mapping) else None
        if cursor is None:
            raise FixtureError(f"navigation target alias {alias!r} is not present in the pinned fixture")
        selected[alias] = json.loads(json.dumps(cursor))

    source = manifest.get("source", {})
    media_root_value = source.get("media_root") if isinstance(source, Mapping) else None
    media_root = (manifest_path.parent / str(media_root_value)).resolve() if media_root_value else None
    eval_root = fixture_root.parent.parent.resolve()
    if media_root is not None:
        try:
            media_root.relative_to(eval_root)
        except ValueError as exc:
            raise FixtureError("pinned navigation media root escapes the evaluation evidence root") from exc

    destination = destination.expanduser().absolute()
    if destination.is_symlink() or not destination.is_dir():
        raise FixtureError(f"selected navigation destination must be an existing directory: {destination}")
    entry_root = destination / "entrypoint"
    if entry_root.exists():
        if entry_root.is_symlink() or not entry_root.is_dir() or any(entry_root.iterdir()):
            raise FixtureError(f"selected navigation entrypoint must be new and empty: {entry_root}")
    else:
        entry_root.mkdir()
    copied_media: dict[str, str] = {}

    def copy_media(media_id: Any, handle: Any, *, source_root: Path | None = None) -> str | None:
        if not isinstance(media_id, str) or not media_id.startswith("sha256:") or not isinstance(handle, str):
            return None
        source_root = source_root or media_root
        if source_root is None:
            raise FixtureError("pinned navigation media root is unavailable")
        unresolved_source_path = source_root / handle
        if unresolved_source_path.is_symlink():
            raise FixtureError(f"selected navigation media handle is a symlink: {media_id}")
        source_path = unresolved_source_path.resolve()
        try:
            source_path.relative_to(source_root.resolve())
        except ValueError as exc:
            raise FixtureError("selected media handle escapes its pinned fixture root") from exc
        if not source_path.is_file() or source_path.is_symlink():
            raise FixtureError(f"selected navigation media bytes are missing: {media_id}")
        digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if digest != media_id.removeprefix("sha256:"):
            raise FixtureError(f"selected navigation media bytes fail their digest: {media_id}")
        filename = media_id.removeprefix("sha256:")
        relative = f"media/{filename}"
        target_path = entry_root / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if not target_path.exists():
            shutil.copyfile(source_path, target_path)
        copied_media[media_id] = relative
        return relative

    def rewrite_handles(value: Any) -> None:
        if isinstance(value, dict):
            if "media_id" in value and "handle" in value:
                local_path = copy_media(value.get("media_id"), value.get("handle"))
                if local_path:
                    value["local_path"] = local_path
            for child in value.values():
                rewrite_handles(child)
        elif isinstance(value, list):
            for child in value:
                rewrite_handles(child)

    rewrite_handles(selected)
    related_inputs: dict[str, Any] = {}
    if case_id == "L06":
        # The detached candidate and validator diagnostic are an explicit
        # public input for this read-only recovery probe.  Copy only this
        # selected sidecar; the coordinator keeps the suite/oracle private.
        candidate_path = fixture_root / "informational" / "L06-stale-invalid-candidate.json"
        if candidate_path.is_symlink() or not candidate_path.is_file():
            raise FixtureError("L06 invalid-candidate sidecar is missing or unsafe")
        candidate_bytes = candidate_path.read_bytes()
        candidate_copy = entry_root / "L06-stale-invalid-candidate.json"
        candidate_copy.write_bytes(candidate_bytes)
        candidate = json.loads(candidate_bytes.decode("utf-8"))
        if not isinstance(candidate, Mapping) or not isinstance(candidate.get("diagnostic"), Mapping):
            raise FixtureError("L06 invalid-candidate sidecar has no diagnostic object")
        related_inputs["invalid_candidate"] = {
            "path": "L06-stale-invalid-candidate.json",
            "sha256": hashlib.sha256(candidate_bytes).hexdigest(),
            "read_only": True,
            "diagnostic": dict(candidate["diagnostic"]),
        }
    if case_id == "L03":
        action_root = fixture_root / "action"
        collection = json.loads((action_root / "A09-images.json").read_text(encoding="utf-8"))
        collection_rows = collection.get("images", [])
        for item in collection_rows:
            if isinstance(item, Mapping):
                item["local_path"] = copy_media(
                    item.get("media_id"), item.get("path"), source_root=action_root,
                )
        related_inputs["montage_collection"] = collection
        related_inputs["music_cue_times_seconds"] = list(collection.get("cue_times_seconds", []))
        related_inputs["cue_source"] = "supplied A09 fixture cue list; no beat detection is implied"

    entrypoint = {
        "kind": "astrid.timeline-eval.offline-navigation-entry.v1",
        "case_id": case_id,
        "read_only": True,
        "reset": "discard this selected-case copy and rematerialize from the same pinned fixture",
        "source": {
            "project_slug": source.get("project_slug"),
            "timeline_id": source.get("timeline_id"),
            "head_revision_id": source.get("head"),
            "closure_digest": source.get("closure_digest"),
            "frame_rate": source.get("frame_rate"),
        },
        "target_receipt": {
            "kind": "astrid.timeline-eval.offline-navigation-target.v1",
            "case_id": case_id,
            "target_aliases": list(aliases),
            "readback_projection": "exact_closure_navigation.v1",
            "source_head": source.get("head"),
            "source_closure_digest": source.get("closure_digest"),
            "media_ids": sorted(copied_media),
            "offline_only": True,
        },
        "targets": selected,
        "related_inputs": related_inputs,
        "media": copied_media,
    }
    if case_id == "L10":
        # The selected voice bytes are already copied and digest-verified
        # above. On macOS, afplay is the existing local playback adapter; do
        # not claim playback support on hosts where it is absent.
        player = shutil.which("afplay")
        entrypoint["surface_adapters"] = {
            "voice_player": {
                "status": "available" if player else "unavailable",
                "command": "afplay",
                "resolved_executable": player,
                "input_role": "voice_source",
                "scope": "local_audio_output",
            }
        }
    (entry_root / "entrypoint.json").write_text(
        json.dumps(entrypoint, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return entrypoint


def derive_invalid_authoring_candidate(baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Derive a real, detached L06 invalid-candidate diagnostic.

    The candidate is opened from the exact pinned closure and then deliberately
    writes the derived parent ``occurrences`` projection. The product validator
    must reject it. This does not publish, mutate, or rebase any source record.
    """
    from astrid.core.timeline.authoring_bundle import (
        UnsupportedAuthoringEditError,
        open_authoring_bundle,
        validate_authoring_candidate,
    )

    source = baseline.get("source")
    closure = baseline.get("closure")
    if not isinstance(source, Mapping) or not isinstance(closure, Mapping):
        raise FixtureError("L06 requires the complete pinned baseline source and closure")
    parent = closure.get("parent_revision")
    shots = closure.get("shot_revisions")
    internals = closure.get("internal_timeline_revisions")
    if not isinstance(parent, Mapping) or not isinstance(shots, list) or not isinstance(internals, list):
        raise FixtureError("L06 baseline is missing exact parent/shot/internal revisions")
    candidate = open_authoring_bundle(
        parent, shot_revisions=shots, internal_timeline_revisions=internals,
    )
    candidate["parent"] = dict(candidate["parent"])
    candidate["parent"]["occurrences"] = []
    try:
        validate_authoring_candidate(candidate)
    except UnsupportedAuthoringEditError as exc:
        diagnostic = {
            "status": "invalid",
            "error_type": type(exc).__name__,
            "message": str(exc),
            "base_parent_revision_id": candidate["base_parent"]["revision_id"],
            "recovery": "Edit candidate.placements; parent occurrences are derived from those placements.",
        }
    else:
        raise FixtureError("authoring validator unexpectedly accepted the derived-field mutation")
    if diagnostic["base_parent_revision_id"] != source.get("head"):
        raise FixtureError("L06 invalid candidate does not use the exact pinned parent head")
    return {
        "kind": "astrid.timeline-eval.invalid-authoring-candidate.v1",
        "case_id": "L06",
        "source_head": source.get("head"),
        "source_closure_digest": baseline.get("closure_digest"),
        "candidate": candidate,
        "diagnostic": diagnostic,
        "publication_performed": False,
        "reset": "discard this detached candidate; canonical source was never mutated",
    }


def _public_target_locator(
    baseline: Baseline, identities: CaseIdentities,
) -> dict[str, Any] | None:
    """Translate a case's semantic target to disposable server IDs.

    A locator is deliberately narrower than a closure export: it tells an
    agent which committed occurrence and selector to inspect, but not which
    replacement media or hidden assertion is expected.  Unknown/synthetic
    baselines simply omit the locator rather than guessing a target.
    """
    public = _PUBLIC_TARGETS.get(identities.case_id)
    if not isinstance(public, Mapping):
        return None
    source_occurrence = str(public.get("source_occurrence_id", ""))
    source_shot = str(public.get("source_shot_id", ""))
    occurrence_id = identities.occurrence_ids.get(source_occurrence)
    shot_id = identities.shot_ids.get(source_shot)
    if not occurrence_id or not shot_id:
        return None
    source_revision = None
    parent_payload = baseline.closure.get("parent_revision", {}).get("payload", {})
    for row in parent_payload.get("occurrences", []) if isinstance(parent_payload, Mapping) else ():
        if isinstance(row, Mapping) and str(row.get("occurrence_id")) == source_occurrence:
            source_revision = str(row.get("shot_revision_id", ""))
            break
    shot_revision_id = identities.shot_revision_ids.get(source_revision or "")
    if not shot_revision_id:
        return None
    result: dict[str, Any] = {
        "role": str(public["role"]),
        "readback_projection": str(public["readback_projection"]),
        "occurrence_id": occurrence_id,
        "shot_id": shot_id,
        "shot_revision_id": shot_revision_id,
        "selector_clip_id": str(public["selector_clip_id"]),
        "replacement_asset_key": str(public["replacement_asset_key"]),
        "replacement_role": str(public["replacement_role"]),
        "voice_clip_id": str(public["voice_clip_id"]),
        "frame_overlay_clip_id": str(public["frame_overlay_clip_id"]),
        "preserve_roles": [str(value) for value in public.get("preserve_roles", ())],
    }
    return result


def derive_case_identities(
    baseline: Baseline, *, attempt_id: str, case_id: str,
    runtime_project_id: str, runtime_timeline_id: str,
) -> CaseIdentities:
    if not attempt_id or case_id not in ACTION_CASES:
        raise FixtureError("attempt_id and a known A01–A10 case_id are required")
    if not runtime_project_id or not runtime_timeline_id:
        raise FixtureError("Runtime-assigned project_id and created timeline_id are required")
    parent_payload = baseline.closure["parent_revision"]["payload"]
    occurrences = parent_payload.get("occurrences", [])
    shot_rows = baseline.closure["shot_revisions"]
    internal_rows = baseline.closure["internal_timeline_revisions"]
    shot_by_revision = {row["revision_id"]: row for row in shot_rows}
    shot_sources = {str(row.get("shot_id")): row for row in shot_rows}
    internal_sources = {str(row.get("timeline_id")): row for row in internal_rows}
    def ident(kind: str, source_id: Any) -> str:
        return _stable_id(SUITE_VERSION, attempt_id, case_id, kind, str(source_id))
    occurrence_ids = {str(row["occurrence_id"]): ident("occurrence", row["occurrence_id"]) for row in occurrences}
    shot_ids = {source: ident("shot", source) for source in shot_sources}
    shot_revision_ids = {str(row["revision_id"]): ident("shot-revision", row["revision_id"]) for row in shot_rows}
    item_sources: set[str] = set()
    for row in shot_rows:
        for item in row.get("payload", {}).get("items", []):
            item_id = item.get("item_id", item.get("id"))
            if item_id is not None:
                item_sources.add(str(item_id))
    item_ids = {source: ident("item", source) for source in sorted(item_sources)}
    internal_timeline_ids = {source: ident("internal-timeline", source) for source in internal_sources}
    internal_revision_ids = {str(row["revision_id"]): ident("internal-revision", row["revision_id"]) for row in internal_rows}
    return CaseIdentities(
        case_id=case_id,
        project_alias="timeline-eval-" + _stable_id(SUITE_VERSION, attempt_id, "suite", baseline.source_project_id),
        timeline_alias="eval-" + _stable_id(SUITE_VERSION, attempt_id, case_id, "timeline", baseline.source_timeline_id),
        project_id=runtime_project_id,
        timeline_id=runtime_timeline_id,
        parent_revision_id=ident("parent-revision", baseline.source_head),
        occurrence_ids=occurrence_ids,
        shot_ids=shot_ids,
        shot_revision_ids=shot_revision_ids,
        item_ids=item_ids,
        internal_timeline_ids=internal_timeline_ids,
        internal_revision_ids=internal_revision_ids,
    )


def idempotency_key(*, attempt_id: str, case_id: str, operation: str, request: Mapping[str, Any]) -> str:
    if not attempt_id or case_id not in ACTION_CASES or not operation:
        raise FixtureError("attempt, A01–A10 case, and operation are required")
    return "eval-" + _stable_id(attempt_id, case_id, operation, _digest(request))


@dataclass(frozen=True)
class DisposableEndpoint:
    url: str
    realm_id: str
    credential_ref: str
    purpose: str


def require_disposable_endpoint(endpoint: DisposableEndpoint | None) -> DisposableEndpoint:
    """Refuse absent or ambiguous live configuration; there is no canonical fallback."""
    if endpoint is None:
        raise FixtureError("explicit disposable Runtime endpoint required; refusing canonical/default fallback")
    if not endpoint.url.startswith(("http://", "https://")) or not endpoint.realm_id or not endpoint.credential_ref:
        raise FixtureError("disposable endpoint requires URL, realm_id, and credential_ref")
    if endpoint.purpose != "timeline-eval-disposable-realm":
        raise FixtureError("Runtime endpoint purpose must be timeline-eval-disposable-realm")
    return endpoint


class FixtureRuntime(Protocol):
    """Adapter over ordinary Runtime APIs; deliberately no database rewind API."""

    endpoint: DisposableEndpoint

    def create_suite_project(self, project_alias: str, *, idempotency_key: str) -> Mapping[str, Any]: ...
    def create_case_timeline(self, project_id: str, timeline_alias: str, *, idempotency_key: str) -> Mapping[str, Any]: ...
    def ensure_media_owned(self, project_id: str, requirement: MediaRequirement, media_bytes: bytes) -> Mapping[str, Any]: ...
    def seed_case(self, project_id: str, identities: CaseIdentities, baseline: Baseline, owned_media: Mapping[str, str], *, idempotency_key: str) -> Mapping[str, Any]: ...
    def read_case_semantic_digest(self, project_id: str, timeline_id: str) -> str: ...
    def read_current_closure(self, project_id: str, timeline_id: str, *, head: str | None = None) -> Mapping[str, Any]: ...
    def read_current_semantic_digest(self, project_id: str, timeline_id: str) -> str: ...
    def current_head(self, project_id: str, timeline_id: str) -> str: ...
    def publish_baseline(self, project_id: str, timeline_id: str, baseline: Baseline, *, expected_head: str, idempotency_key: str) -> Mapping[str, Any]: ...


def _runtime_data(value: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    data = value.get("data", value)
    if not isinstance(data, Mapping):
        raise FixtureError(f"Runtime {field} response has no data record")
    return data


def _load_attempt_media(baseline: Baseline, media_root: Path) -> dict[str, bytes]:
    """Read and hash-check every required byte before the first Runtime write."""
    root = media_root.expanduser().absolute()
    if not root.is_dir() or root.is_symlink():
        raise FixtureError("explicit attempt media directory is missing or unsafe")
    result: dict[str, bytes] = {}
    for row in baseline.media:
        relative = Path(row.source_handle)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise FixtureError(f"media source_handle must be attempt-relative: {row.source_handle!r}")
        path = root / relative
        cursor = root
        traverses_symlink = False
        for part in relative.parts:
            cursor = cursor / part
            traverses_symlink = traverses_symlink or cursor.is_symlink()
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root.resolve(strict=True))
        except (OSError, ValueError) as exc:
            raise FixtureError(f"media source_handle escapes or is missing from attempt media: {row.source_handle}") from exc
        if traverses_symlink or not resolved.is_file():
            raise FixtureError(f"media source_handle must name a regular non-symlink file: {row.source_handle}")
        payload = resolved.read_bytes()
        expected = row.digest.removeprefix("sha256:")
        if len(expected) != 64 or hashlib.sha256(payload).hexdigest() != expected:
            raise FixtureError(f"media bytes do not match declared digest {row.digest}")
        result[row.digest] = payload
    return result


def seed_case(
    runtime: FixtureRuntime, baseline: Baseline, *, attempt_id: str, case_id: str,
    media_root: Path,
) -> Mapping[str, Any]:
    endpoint = require_disposable_endpoint(getattr(runtime, "endpoint", None))
    # Preflight all bytes before creating even the disposable project. Missing or
    # corrupt fixture media therefore fails without partial Runtime writes.
    media_bytes = _load_attempt_media(baseline, media_root)
    project_key = idempotency_key(attempt_id=attempt_id, case_id="A01", operation="create-suite-project", request={"source": baseline.semantic_digest})
    project_record = _runtime_data(runtime.create_suite_project(
        "timeline-eval-" + _stable_id(SUITE_VERSION, attempt_id, "suite", baseline.source_project_id),
        idempotency_key=project_key,
    ), "create_suite_project")
    project_id = project_record.get("project_id", project_record.get("id"))
    if not isinstance(project_id, str) or not project_id:
        raise FixtureError("Runtime create_suite_project did not return its server-assigned project ID")
    timeline_alias = "eval-" + _stable_id(SUITE_VERSION, attempt_id, case_id, "timeline", baseline.source_timeline_id)
    timeline_key = idempotency_key(attempt_id=attempt_id, case_id=case_id, operation="create-case-timeline", request={"baseline": baseline.semantic_digest, "timeline_alias": timeline_alias})
    timeline_record = _runtime_data(runtime.create_case_timeline(project_id, timeline_alias, idempotency_key=timeline_key), "create_case_timeline")
    timeline_id = timeline_record.get("timeline_id", timeline_record.get("id"))
    if not isinstance(timeline_id, str) or not timeline_id:
        raise FixtureError("Runtime create_case_timeline did not return the created timeline ID")
    identities = derive_case_identities(
        baseline, attempt_id=attempt_id, case_id=case_id,
        runtime_project_id=project_id, runtime_timeline_id=timeline_id,
    )
    owned: dict[str, str] = {}
    for requirement in baseline.media:
        record = _runtime_data(runtime.ensure_media_owned(project_id, requirement, media_bytes[requirement.digest]), "ensure_media_owned")
        if record.get("project_id") != project_id or record.get("digest") != requirement.digest:
            raise FixtureError(f"media {requirement.digest} is not verified as owned by destination project")
        object_id = record.get("object_id")
        if not isinstance(object_id, str) or not object_id:
            raise FixtureError(f"media {requirement.digest} has no destination object_id")
        owned[requirement.digest] = object_id
    key = idempotency_key(attempt_id=attempt_id, case_id=case_id, operation="seed", request={"baseline": baseline.semantic_digest})
    receipt = _runtime_data(runtime.seed_case(project_id, identities, baseline, owned, idempotency_key=key), "seed_case")
    if receipt.get("project_id") != project_id or receipt.get("timeline_id") != timeline_id:
        raise FixtureError("seed receipt does not identify the isolated case target")
    if receipt.get("semantic_digest") != baseline.semantic_digest:
        raise FixtureError("seed readback does not match baseline semantic digest")
    return {"endpoint_url": endpoint.url, "endpoint_realm_id": endpoint.realm_id, "project_alias": identities.project_alias, "timeline_alias": identities.timeline_alias, "project_id": project_id, "timeline_id": timeline_id, "identities": identities, "owned_media": owned, "target_locator": _public_target_locator(baseline, identities), "project_idempotency_key": project_key, "timeline_idempotency_key": timeline_key, "idempotency_key": key, "receipt": dict(receipt)}


def reset_case(
    runtime: FixtureRuntime, baseline: Baseline, *, attempt_id: str, case_id: str,
    project_id: str, timeline_id: str,
) -> Mapping[str, Any]:
    """Restore semantics by publishing baseline as a new head, preserving history."""
    endpoint = require_disposable_endpoint(getattr(runtime, "endpoint", None))
    if not project_id or not timeline_id:
        raise FixtureError("reset requires the Runtime-assigned project_id and timeline_id from the seed receipt")
    current = runtime.current_head(project_id, timeline_id)
    if not current:
        raise FixtureError("cannot reset an unseeded case")
    key = idempotency_key(
        attempt_id=attempt_id, case_id=case_id, operation="reset-baseline",
        request={"baseline": baseline.semantic_digest, "expected_head": current},
    )
    receipt = runtime.publish_baseline(
        project_id, timeline_id, baseline,
        expected_head=current, idempotency_key=key,
    )
    if receipt.get("new_head") is None:
        raise FixtureError("reset must produce a new canonical head through publication")
    actual = runtime.read_case_semantic_digest(project_id, timeline_id)
    if actual != baseline.semantic_digest:
        raise FixtureError("reset publication readback differs from baseline semantics")
    return {"endpoint_realm_id": endpoint.realm_id, "new_head": receipt["new_head"], "semantic_digest": actual, "idempotency_key": key}


__all__ = [
    "ACTION_CASES", "Baseline", "CaseIdentities", "DisposableEndpoint", "FIXTURE_BUILDER_VERSION",
    "FixtureError", "FixtureRuntime", "MediaRequirement", "export_baseline", "derive_case_identities",
    "public_target_receipt",
    "materialize_public_navigation_entrypoint",
    "idempotency_key", "require_disposable_endpoint", "reset_case", "seed_case",
]
