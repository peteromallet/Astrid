"""Group an existing edit through public runtime services, without rebuilding it.

The runtime has separate shot/document writes, so this is a resumable SDK
workflow, not an atomic transaction. The parent CAS is deliberately last.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import uuid

from .contracts import DomainResult, ErrorObject


def group_timeline_clips(*, shots, timelines, project, timeline, clip_ids,
                         name, expected_version, hold=None, idempotency_key=None):
    key = idempotency_key or uuid.uuid4().hex
    token = hashlib.sha256(key.encode()).hexdigest()
    shot_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"astrid:group-shot:{project}:{token}"))
    child_id = uuid.uuid5(uuid.NAMESPACE_URL, f"astrid:group-timeline:{project}:{token}").hex
    group_id = f"shot-{token[:16]}"
    identity = {"shot_id": shot_id, "timeline_document_id": child_id,
                "group_clip_id": group_id}

    def fail(code, message, **details):
        return DomainResult.failure(ErrorObject(code, message, {**identity, **details}),
                                    idempotency_key=key)

    def failed(result, stage):
        if result.ok:
            return None
        recovery = "Retry the same arguments and idempotency key; the parent save is last."
        if stage == "save_parent" and result.error.code in {"version_conflict", "conflict"}:
            recovery = "Parent changed. Inspect it, then use the current version and a new idempotency key; the reported unattached shot and child remain available."
        return fail(result.error.code, result.error.message, stage=stage,
                    cause=result.error.details,
                    recovery=recovery)

    if (not isinstance(expected_version, int) or isinstance(expected_version, bool)
            or expected_version < 1 or not isinstance(name, str) or not name.strip()
            or not clip_ids or len(set(clip_ids)) != len(clip_ids)):
        return fail("validation_error", "A name, unique clip IDs, and a positive expected version are required")
    if hold is not None and (isinstance(hold, bool) or not isinstance(hold, (int, float))
                             or not math.isfinite(hold) or hold <= 0):
        return fail("validation_error", "hold must be a finite positive duration")
    result = timelines.show(project, timeline)
    if not result.ok:
        return failed(result, "read_parent")
    parent = result.data
    config = deepcopy(parent["config"])
    registry = deepcopy(parent["registry"])
    request = {"timeline_id": parent["timeline_id"], "clip_ids": sorted(clip_ids),
               "name": name, "expected_version": expected_version, "hold": hold}
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()
    clips = config.get("clips", [])
    # A successful retry remains read-only, even after unrelated later edits.
    existing = next((c for c in clips if c.get("id") == group_id), None)
    if existing:
        registered = shots.show(project, shot_id)
        if not registered.ok:
            return failed(registered, "verify_replay")
        if registered.data.get("metadata", {}).get("group_request") != fingerprint:
            return fail("idempotency_conflict", "This idempotency key was used for another grouping request")
        if (existing.get("clipType") != "shot" or
                existing.get("params", {}).get("shot_id") != shot_id or
                existing.get("params", {}).get("timeline_document_id") != child_id):
            return fail("conflict", "The previously grouped clip has been changed")
        return DomainResult.success({**identity, "timeline_id": parent["timeline_id"],
                                     "config_version": parent["config_version"], "replayed": True},
                                    idempotency_key=key)
    if parent["config_version"] != expected_version:
        return fail("version_conflict", "Timeline changed; inspect it and retry with the current version",
                    expected_version=expected_version, actual_version=parent["config_version"])
    selected = [c for c in clips if c.get("id") in clip_ids]
    if len(selected) != len(clip_ids):
        return fail("validation_error", "Every selected clip must exist exactly once on this timeline")
    indices = [i for i, c in enumerate(clips) if c.get("id") in clip_ids]
    if indices != list(range(indices[0], indices[-1] + 1)):
        return fail("validation_error", "Selected clips must be adjacent in authored order to preserve compositing order")
    if any(c.get("clipType") == "shot" for c in selected):
        return fail("validation_error", "Nested shots are unsupported; select ungrouped clips")
    if any(set(g.get("clipIds", [])) & set(clip_ids) for g in config.get("pinnedShotGroups", [])):
        return fail("validation_error", "Selected clips already belong to a pinned shot group")
    try:
        start = min(float(c.get("at", 0)) for c in selected)
        ends = []
        for c in selected:
            speed = float(c.get("speed", 1))
            if speed <= 0:
                raise ValueError("Invalid clip speed")
            duration = float(c["hold"]) if "hold" in c else (float(c["to"]) - float(c.get("from", 0))) / speed
            end = float(c.get("at", 0)) + duration
            if duration <= 0 or not math.isfinite(end):
                raise ValueError("Unbounded clip")
            ends.append(end)
        natural_hold = max(ends) - start
        duration = natural_hold if hold is None else float(hold)
        if not math.isfinite(start) or duration < natural_hold - 1e-9:
            raise ValueError("Shot hold would truncate selected content")
    except (KeyError, TypeError, ValueError) as exc:
        return fail("validation_error", f"Selected clips require finite bounded timing: {exc}")
    child = deepcopy(config)
    child["clips"] = deepcopy(selected)
    child.pop("pinnedShotGroups", None)
    for c in child["clips"]:
        c["at"] = float(c.get("at", 0)) - start
    assets = registry.get("assets", {})
    selected_assets = list(dict.fromkeys(c["asset"] for c in selected if c.get("asset")))
    if any(a not in assets or not assets[a].get("media_id") for a in selected_assets):
        return fail("validation_error", "Every selected asset needs a managed media registry entry")
    # Retain the registry: custom elements can reference assets in params.
    composite = {"id": group_id, "clipType": "shot", "at": start,
                 "hold": duration, "params": identity.copy()}
    if selected[0].get("track") is not None:
        composite["track"] = selected[0]["track"]
    composite["params"].pop("group_clip_id")
    output_clips = []
    for c in clips:
        if c is selected[0]:
            output_clips.append(composite)
        if c.get("id") not in clip_ids:
            output_clips.append(c)
    config["clips"] = output_clips
    # Validate and prove expansion preserves the edit before creating resources.
    try:
        from banodoco_timeline_schema import validate_timeline
        from jsonschema.exceptions import ValidationError
        from astrid.core.timeline.expand_shots import expand_shot_clips
        validate_timeline(child)
        validate_timeline(config)
        expanded, _ = expand_shot_clips({**config, "clips": [composite]}, registry,
                                      load_timeline=lambda _: (child, registry))
        for before, after in zip(selected, expanded["clips"], strict=True):
            if "track" not in before and after.get("track") is None:
                after.pop("track", None)
            if before.keys() != after.keys():
                raise ValueError("Grouping would change clip fields")
            for k, value in before.items():
                if isinstance(value, (int, float)):
                    if not math.isclose(value, after[k], rel_tol=0, abs_tol=1e-9):
                        raise ValueError(f"Grouping would change {before['id']}.{k}")
                elif value != after[k]:
                    raise ValueError(f"Grouping would change {before['id']}.{k}")
    except (ValueError, TypeError, ValidationError) as exc:
        return fail("validation_error", str(exc))

    created = shots.create(project=project, shot={"shot_id": shot_id}, name=name,
                           metadata={"group_request": fingerprint, "source_clip_ids": list(clip_ids),
                                     "timeline_document_id": child_id, "master_timeline_id": parent["timeline_id"]},
                           idempotency_key=f"group-{token}-shot")
    if not created.ok:
        return failed(created, "create_shot")
    created = timelines.create(project=project, timeline_id=child_id, name=name,
                               slug=f"shot-{token[:16]}", config=child, registry=registry,
                               idempotency_key=f"group-{token}-timeline")
    if not created.ok:
        return failed(created, "create_child")
    # A partial-operation retry must not bind a child somebody has since edited.
    verified = timelines.show(project, child_id)
    if not verified.ok:
        return failed(verified, "verify_child")
    if verified.data.get("config") != child or verified.data.get("registry") != registry:
        return fail("conflict", "The prepared child timeline was edited; inspect it before retrying",
                    stage="verify_child")
    for position, asset in enumerate(selected_assets):
        attached = shots.add_item(project, shot_id, media_id=assets[asset]["media_id"],
                                  position=position, metadata={"asset_key": asset},
                                  idempotency_key=f"group-{token}-item-{position}")
        if not attached.ok:
            return failed(attached, "attach_media")
    saved = timelines.save(project, parent["timeline_id"], config=config, registry=registry,
                           expected_version=expected_version, idempotency_key=f"group-{token}-save")
    if not saved.ok:
        return failed(saved, "save_parent")
    return DomainResult.success({**identity, "timeline_id": parent["timeline_id"],
                                 "config_version": saved.data.get("config_version", expected_version + 1),
                                 "name": name, "at": start, "hold": duration,
                                 "clip_ids": list(clip_ids), "replayed": False},
                                receipt=saved.receipt, idempotency_key=key)
