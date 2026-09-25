"""Product timelines family CLI (m4 plan step 26, task T28).

This module is the product parser for the runtime-owned ``timelines``
family. Every verb is **argument parsing plus exactly one SDK
call** on the composed :class:`~astrid.sdk.client.AstridClient` (stamped
onto every subparser by
:func:`astrid.core.cli.registration.register_product_commands`), and every
handler renders through the shared product output layer
(:mod:`astrid.core.cli.domain_output`) so the exact five-key JSON envelope,
concise human output, and stable exit codes stay aligned with the frozen SDK
contract.

The parser also mounts the runtime-owned nested ``shots`` family beneath
``timelines``: ``astrid timelines shots <verb>`` embeds the shots
product parser (``astrid/packs/shots/cli.py``) so project-level reusable shot
``list/create/show/add/remove/reorder`` commands are executable only beneath timelines
(plan step 26, task T29). There is **no top-level shots family**.

Verbs (the product routes plus the nested ``shots`` mount; read/write routes
are thin SDK adapters, while ``retime-clip`` is an intentionally bounded
read/CAS-save convenience operation):

- ``create`` — ``client.timelines.create`` (project id/slug, slug, name,
  optional ``--config``/``--registry`` JSON, ``--default``, and
  ``--idempotency-key``; a fresh key is generated and returned when absent);
- ``list`` — ``client.timelines.list`` (active timelines only), rendered as
  compact identity/count summaries; use ``show`` for the full document;
- ``show`` — ``client.timelines.show`` by UUID, ULID, or slug; ``--summary``
  returns a bounded editor-oriented clip/track view instead of the full
  document;
- ``retime-clip`` — one scoped read/CAS-save operation for changing a clip's
  start; the safe non-rippling default preserves the existing end, while
  ``--preserve-duration`` explicitly slides the clip without changing length;
- ``save`` — whole-document CAS ``client.timelines.save`` with
  ``--config``/``--registry`` and ``--expected-version``;
- ``replace-clip`` — atomically replace one explicit managed-media clip through
  ``client.timelines.replace_clip`` with ``--expected-version`` and
  ``preserve-duration`` timing;
- ``replace-parent-media`` — replace one selected clip in the canonical
  parent-composition closure through ``client.timelines.replace_parent_media``;
- ``archive`` — reversible event-backed ``client.timelines.archive``;
- ``recover`` — idempotent recovery through ``client.timelines.recover``;
- ``history`` — ordered lifecycle events (read);
- ``diff`` — deterministic adjacent-version diffs (read).
- ``visualize`` — synchronous ``client.invoke`` of the public
  ``rendering.timeline_visualize`` capability.
- ``render`` — version-pinned kernel timeline render through the explicit
  ``rendering.render`` `timeline_ref` mode.

**Negative routes (sense check SC28):** the legacy timeline verbs
``migration``, ``push``, ``pull``, ``sync``, ``audit``, ``erase``, and
``repair`` are **absent** from this product parser, as are all obsolete
aliases (``ls``, ``tl``, ...), and ``copy`` is **absent** — the reserved
save-as-copy route is contractually deferred to m6 (plan step 2 / watch
item) and must never be registered here.

This module contains **no SQL**, **no repository logic**, and **no
domain rules**: it parses argv, makes one SDK call, and renders the
returned envelope.
"""

from __future__ import annotations

import argparse
import json
import shlex
from collections.abc import Mapping
from typing import Any

from astrid.core.cli.domain_output import print_result
from astrid.core.cli.registration import CommandSpec, register_product_commands
from astrid.core.cli.task_progress import task_handoff

__all__ = ["COMMANDS", "build_parser"]

_FAMILY = "timelines"


def _parse_json_object(value: str) -> dict[str, Any]:
    """Parse a ``--config``/``--registry`` JSON object argument."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON object: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("must be a JSON object")
    return parsed


def _add_json_flag(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Print the exact SDK envelope (ok/data/error/receipt/idempotency_key); default output.",
    )


def _add_idempotency_key(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--idempotency-key",
        dest="idempotency_key",
        default=None,
        help="Caller idempotency key (a fresh key is generated when absent).",
    )


def _add_project_arg(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument(
        "--project",
        required=True,
        default=None,
        help="Owning project id or immutable slug.",
    )


# -- handlers (one SDK call each, no domain rules) -------------------------


def _cmd_create(parsed: argparse.Namespace) -> int:
    # An asset-free timeline still has a canonical empty registry.  The
    # generated runtime client accepts mappings only and calls ``dict(...)``
    # at the transport boundary, so forwarding argparse's optional ``None``
    # would turn the documented minimal create command into a TypeError.
    # Preserve explicit empty or populated JSON objects exactly as supplied.
    config = parsed.config if parsed.config is not None else {}
    registry = parsed.registry if parsed.registry is not None else {"assets": {}}
    result = parsed.client.timelines.create(
        project=parsed.project,
        slug=parsed.slug,
        name=parsed.name,
        config=config,
        registry=registry,
        idempotency_key=parsed.idempotency_key,
    )
    return print_result(result, as_json=parsed.json)


def _cmd_list(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.list(
        parsed.project, include_archived=parsed.include_archived
    )
    # Listing is a discovery route.  Keep the full document available through
    # ``show`` while preventing a registry/config blob from flooding the
    # terminal (and agent context) during the common list operation.
    if result.ok and isinstance(result.data, (list, tuple)):
        from astrid.sdk.contracts import DomainResult

        data: Any = list(result.data)
        # Runtime list reads are cursor pages: [rows, next_cursor]. Keep the
        # cursor in the envelope while compacting only the document rows.
        if (
            len(data) == 2
            and isinstance(data[0], list)
            and (data[1] is None or isinstance(data[1], str))
        ):
            data = [[_timeline_summary(item) for item in data[0]], data[1]]
        else:
            data = [_timeline_summary(item) for item in data]
        result = DomainResult.success(
            data,
            receipt=result.receipt,
            idempotency_key=result.idempotency_key,
        )
    return print_result(result, as_json=parsed.json)


def _timeline_summary(item: Any) -> Any:
    """Return a compact identity/count view for one listed timeline."""
    if not isinstance(item, Mapping):
        return item

    summary: dict[str, Any] = {}
    # These are the stable identity/lifecycle fields emitted by the runtime.
    for key in (
        "timeline_id", "id", "slug", "name", "version", "config_version",
        "archived", "archived_at", "is_default", "default",
    ):
        if key in item:
            summary[key] = item[key]
    # Some runtime projections keep the display metadata nested.
    display = item.get("display")
    if "is_default" not in summary and isinstance(display, Mapping):
        if "is_default" in display:
            summary["is_default"] = display["is_default"]

    config = item.get("config")
    registry = item.get("registry")
    counts: dict[str, int] = {}
    if isinstance(config, Mapping):
        counts["config_keys"] = len(config)
        for key in ("clips", "tracks", "shots", "scenes"):
            value = config.get(key)
            if isinstance(value, (list, tuple, Mapping)):
                counts[key] = len(value)
    if isinstance(registry, Mapping):
        assets = registry.get("assets")
        if isinstance(assets, (list, tuple, Mapping)):
            counts["assets"] = len(assets)
    if counts:
        summary["counts"] = counts
    return summary


def _cmd_show(parsed: argparse.Namespace) -> int:
    # Prefer the SDK's single bounded composition adapter when the client has
    # one.  Test doubles and older clients fall back to the same projection
    # below, so this remains backwards-compatible without creating a second
    # storage authority.
    from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import (
        inspection_options,
        project_timeline_document,
    )
    values = {
        name: getattr(parsed, name, None)
        for name in ("clip", "occurrence", "shot", "track", "asset", "range", "detail", "limit", "cursor")
    }
    normalized = inspection_options(values)
    selectors = {
        "clip": normalized["clip"], "occurrence": normalized["occurrence"],
        "shot": normalized["shot"], "track": normalized["tracks"],
        "asset": normalized["asset"],
        "range": values.get("range"), "detail": normalized["detail"],
    }
    has_selector = any(
        selectors[name] not in (None, "", [], ())
        for name in ("clip", "occurrence", "shot", "track", "asset", "range")
    ) or selectors["detail"] is True
    opener = getattr(parsed.client.timelines, "open_composition", None)
    if callable(opener) and (parsed.summary or has_selector):
        result = opener(
            parsed.project,
            parsed.ref,
            limit=values.get("limit") or 50,
            cursor=values.get("cursor"),
            clip=normalized["clip"],
            occurrence=normalized["occurrence"],
            shot=normalized["shot"],
            track=normalized["tracks"],
            asset=normalized["asset"],
            range_value=values.get("range"),
            detail=normalized["detail"],
        )
    else:
        result = parsed.client.timelines.show(parsed.project, parsed.ref)
    if result.ok and isinstance(result.data, Mapping):
        # Keep the legacy bounded summary shape, but derive its inspection
        # metadata through the same shared projection used by visualize. This
        # makes occurrence/selected-media/output identity agree without
        # exposing storage internals or changing the ordinary full show route.
        # ``detail`` is a presentation flag, not a scope selector. In
        # particular, its default False must not turn ordinary ``show`` into
        # the bounded inspection projection.
        if parsed.summary or has_selector:
            if result.data.get("kind") == "timeline-inspection":
                return print_result(result, as_json=parsed.json)
            projection = project_timeline_document(
                result.data,
                clip=normalized["clip"], occurrence=normalized["occurrence"],
                shot=normalized["shot"], track=normalized["tracks"],
                asset=normalized.get("asset"), range_value=values.get("range"),
                detail=normalized["detail"], limit=values.get("limit") or 50,
                cursor=values.get("cursor"),
            )
            if parsed.summary:
                result = _summary_result(result, projection=projection)
            else:
                from astrid.sdk.contracts import DomainResult

                result = DomainResult.success(
                    {"kind": "timeline-inspection", **projection},
                    receipt=result.receipt,
                    idempotency_key=result.idempotency_key,
                )
    return print_result(result, as_json=parsed.json)


def _numeric(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _clip_duration(clip: Mapping[str, Any]) -> float | None:
    hold = clip.get("hold")
    if _numeric(hold):
        return float(hold)
    source_start = clip.get("from", 0)
    source_end = clip.get("to")
    speed = clip.get("speed", 1)
    if _numeric(source_start) and _numeric(source_end) and _numeric(speed) and float(speed) > 0:
        return max(0.0, (float(source_end) - float(source_start)) / float(speed))
    return None


def _compact_clip(clip: Any) -> Any:
    if not isinstance(clip, Mapping):
        return clip
    summary: dict[str, Any] = {}
    for source, target in (
        ("id", "id"),
        ("track", "track"),
        ("clipType", "clip_type"),
        ("clip_type", "clip_type"),
        ("asset", "asset"),
        ("shot_id", "shot_id"),
    ):
        value = clip.get(source)
        if value is not None and target not in summary:
            summary[target] = value
    at = clip.get("at")
    if _numeric(at):
        summary["at"] = float(at)
    duration = _clip_duration(clip)
    if duration is not None:
        summary["duration"] = duration
        if _numeric(at):
            summary["end"] = float(at) + duration
    for key in ("hold", "from", "to", "speed"):
        value = clip.get(key)
        if value is not None and _numeric(value):
            summary[key] = value
    return summary


def _compact_track(track: Any) -> Any:
    if not isinstance(track, Mapping):
        return track
    summary: dict[str, Any] = {}
    for key in ("id", "name", "label", "kind", "type"):
        if track.get(key) is not None:
            summary[key] = track[key]
    return summary or dict(track)


def _timeline_document_summary(data: Any, *, projection: Mapping[str, Any] | None = None) -> Any:
    """Build the bounded read model used by editor agents.

    This intentionally keeps timing and identity, while excluding prompts,
    effect parameters, media URLs, and the full asset registry. The full
    document remains available through the normal ``show`` route.
    """
    if not isinstance(data, Mapping):
        return data
    config = data.get("config") if isinstance(data.get("config"), Mapping) else {}
    registry = data.get("registry") if isinstance(data.get("registry"), Mapping) else {}
    clips = config.get("clips") if isinstance(config.get("clips"), list) else []
    tracks = config.get("tracks") if isinstance(config.get("tracks"), list) else []
    summary: dict[str, Any] = {
        "kind": "timeline-summary",
        "timeline_id": data.get("timeline_id"),
        "project_id": data.get("project_id"),
        "slug": data.get("slug"),
        "name": data.get("name"),
        "config_version": data.get("config_version", data.get("version")),
        "archived": bool(data.get("archived", False)),
        "track_count": len(tracks),
        "clip_count": len(clips),
        "asset_count": len(registry.get("assets", {})) if isinstance(registry.get("assets"), (Mapping, list, tuple)) else 0,
        "tracks": [_compact_track(track) for track in tracks],
        "clips": sorted(
            [_compact_clip(clip) for clip in clips],
            key=lambda clip: (float(clip.get("at", 0)) if isinstance(clip, Mapping) and _numeric(clip.get("at")) else 0.0, str(clip.get("track", "")) if isinstance(clip, Mapping) else ""),
        ),
    }
    if isinstance(projection, Mapping):
        # This is deliberately nested so existing consumers of the bounded
        # summary's track/clip/count fields remain compatible.
        summary["inspection"] = {
            key: projection[key]
            for key in (
                "query", "targets", "clips", "media", "outputs",
                "diagnostics", "pagination",
            )
            if key in projection
        }
    return summary


def _summary_result(result: Any, *, projection: Mapping[str, Any] | None = None) -> Any:
    from astrid.sdk.contracts import DomainResult

    return DomainResult.success(
        _timeline_document_summary(result.data, projection=projection),
        receipt=result.receipt,
        idempotency_key=result.idempotency_key,
    )


def _timing_snapshot(clip: Mapping[str, Any]) -> dict[str, float | None]:
    at = float(clip.get("at", 0)) if _numeric(clip.get("at", 0)) else 0.0
    duration = _clip_duration(clip)
    return {
        "at": at,
        "duration": duration,
        "end": at + duration if duration is not None else None,
    }


def _cmd_retime_clip(parsed: argparse.Namespace) -> int:
    """Retiming convenience route: one bounded read followed by one CAS save.

    The default is deliberately non-rippling: preserve the existing end. A
    caller that means "slide this clip" must opt into ``preserve-duration``.
    """
    from copy import deepcopy

    shown = parsed.client.timelines.show(parsed.project, parsed.ref)
    if not shown.ok or not isinstance(shown.data, Mapping):
        return print_result(shown, as_json=parsed.json)
    data = shown.data
    config = data.get("config")
    registry = data.get("registry")
    version = data.get("config_version", data.get("version"))
    if not isinstance(config, Mapping) or not isinstance(registry, Mapping) or not _numeric(version):
        from astrid.sdk.contracts import DomainResult, ErrorObject
        return print_result(
            DomainResult.failure(ErrorObject("invalid_timeline", "timeline is missing config, registry, or config_version")),
            as_json=parsed.json,
        )
    if parsed.expected_version is not None and int(version) != parsed.expected_version:
        from astrid.sdk.contracts import DomainResult, ErrorObject
        return print_result(
            DomainResult.failure(ErrorObject(
                "stale_version",
                f"timeline is at version {int(version)}; expected {parsed.expected_version}",
                details={"expected_version": parsed.expected_version, "current_version": int(version)},
            )),
            as_json=parsed.json,
        )
    next_config = deepcopy(dict(config))
    clips = next_config.get("clips")
    if not isinstance(clips, list):
        from astrid.sdk.contracts import DomainResult, ErrorObject
        return print_result(
            DomainResult.failure(ErrorObject("invalid_timeline", "timeline config has no clips list")),
            as_json=parsed.json,
        )
    clip = next((item for item in clips if isinstance(item, Mapping) and item.get("id") == parsed.clip_id), None)
    if clip is None:
        from astrid.sdk.contracts import DomainResult, ErrorObject
        return print_result(
            DomainResult.failure(ErrorObject("not_found", f"clip not found: {parsed.clip_id}")),
            as_json=parsed.json,
        )
    old_timing = _timing_snapshot(clip)
    timing_policy = parsed.timing_policy
    if parsed.hold is not None:
        timing_policy = "preserve-duration"
        if parsed.hold <= 0:
            from astrid.sdk.contracts import DomainResult, ErrorObject
            return print_result(
                DomainResult.failure(ErrorObject("invalid_timing", "hold must be greater than zero")),
                as_json=parsed.json,
            )
    old_end = old_timing["end"]
    clip["at"] = parsed.at
    if timing_policy == "preserve-end":
        if old_end is None or old_end <= parsed.at:
            from astrid.sdk.contracts import DomainResult, ErrorObject
            return print_result(
                DomainResult.failure(ErrorObject("invalid_timing", "preserve-end requires the new start to be before the existing end")),
                as_json=parsed.json,
            )
        clip["hold"] = old_end - parsed.at
        clip.pop("from", None)
        clip.pop("to", None)
    elif parsed.hold is not None:
        clip["hold"] = parsed.hold
    saved = parsed.client.timelines.save(
        parsed.project,
        parsed.ref,
        config=next_config,
        registry=registry,
        expected_version=int(version),
        idempotency_key=parsed.idempotency_key,
    )
    if saved.ok:
        from astrid.sdk.contracts import DomainResult
        after_timing = _timing_snapshot(clip)
        saved_version = saved.data.get("config_version") if isinstance(saved.data, Mapping) else None
        if saved_version is None and isinstance(saved.data, Mapping):
            saved_version = saved.data.get("version")
        return print_result(
            DomainResult.success(
                {
                    "operation": "retime-clip",
                    "clip_id": parsed.clip_id,
                    "timing_policy": timing_policy,
                    "before": old_timing,
                    "after": after_timing,
                    "config_version": saved_version,
                },
                receipt=saved.receipt,
                idempotency_key=saved.idempotency_key,
            ),
            as_json=parsed.json,
        )
    return print_result(saved, as_json=parsed.json)


def _cmd_save(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.save(
        parsed.project,
        parsed.ref,
        config=parsed.config,
        registry=parsed.registry,
        expected_version=parsed.expected_version,
        idempotency_key=parsed.idempotency_key,
    )
    return print_result(result, as_json=parsed.json)


def _cmd_replace_clip(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.replace_clip(
        parsed.project,
        parsed.ref,
        clip_id=parsed.clip_id,
        source_object_id=parsed.source_object_id,
        expected_version=parsed.expected_version,
        timing=parsed.timing,
        idempotency_key=parsed.idempotency_key,
    )
    return print_result(result, as_json=parsed.json)


def _cmd_replace_parent_media(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.replace_parent_media(
        parsed.project,
        parsed.ref,
        occurrence_id=parsed.occurrence_id,
        clip_id=parsed.clip_id,
        source_object_id=parsed.source_object_id,
        expected_head=parsed.expected_head,
        idempotency_key=parsed.idempotency_key,
    )
    return print_result(result, as_json=parsed.json)


def _cmd_archive(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.archive(
        parsed.project,
        parsed.ref,
        idempotency_key=parsed.idempotency_key,
    )
    return print_result(result, as_json=parsed.json)


def _cmd_recover(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.recover(
        parsed.project,
        parsed.ref,
        idempotency_key=parsed.idempotency_key,
    )
    return print_result(result, as_json=parsed.json)


def _cmd_history(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.history(parsed.project, parsed.ref)
    return print_result(result, as_json=parsed.json)


def _cmd_diff(parsed: argparse.Namespace) -> int:
    result = parsed.client.timelines.diff(parsed.project, parsed.ref)
    return print_result(result, as_json=parsed.json)


def _visualize_format_argument(value: str) -> str:
    """Validate one bounded visualization format argument."""
    values = [part.strip().lower() for part in value.split(",") if part.strip()]
    if not values:
        raise argparse.ArgumentTypeError("format must name png or md")
    invalid = sorted(set(values) - {"png", "md"})
    if invalid:
        raise argparse.ArgumentTypeError(
            f"invalid visualization format(s): {', '.join(invalid)}; choose png or md"
        )
    return ",".join(values)


def _visualization_artifact_summary(outputs: Mapping[str, Any]) -> dict[str, Any] | None:
    """Summarize repeated visualization artifacts without dropping evidence."""
    raw_artifacts = outputs.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return None

    groups: dict[tuple[str, str], dict[str, Any]] = {}
    media_ids: set[str] = set()
    hashes: set[str] = set()
    for artifact in raw_artifacts:
        if not isinstance(artifact, Mapping):
            continue
        media_id = artifact.get("media_id")
        content_hash = artifact.get("content_hash")
        if isinstance(media_id, str) and media_id:
            media_ids.add(media_id)
        if isinstance(content_hash, str) and content_hash:
            hashes.add(content_hash)
        if not (
            isinstance(media_id, str)
            and media_id
            and isinstance(content_hash, str)
            and content_hash
        ):
            continue
        key = (media_id, content_hash)
        group = groups.setdefault(
            key,
            {"media_id": media_id, "content_hash": content_hash, "count": 0, "labels": []},
        )
        group["count"] += 1
        label = artifact.get("label")
        if isinstance(label, str) and label:
            group["labels"].append(label)

    duplicate_groups = [group for group in groups.values() if group["count"] > 1]
    duplicate_groups.sort(key=lambda group: (-group["count"], group["media_id"]))
    return {
        "artifact_count": len(raw_artifacts),
        "unique_media_count": len(media_ids),
        "unique_content_hash_count": len(hashes),
        "duplicate_reference_count": sum(group["count"] - 1 for group in duplicate_groups),
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_groups": duplicate_groups,
    }


def _cmd_visualize(parsed: argparse.Namespace) -> int:
    """Run visualization through the public SDK and product output layer."""
    from astrid.sdk.contracts import DomainResult, ErrorObject
    from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import inspection_options
    human_outputs: Mapping[str, Any] | None = None

    # Normalize repeatable and comma-separated spellings before the one
    # canonical SDK call.  The filmstrip is the only public visualization
    # path, and its presentation formats are deliberately bounded to PNG/MD.
    formats = [
        item.strip().lower()
        for value in (parsed.formats or ["png", "md"])
        for item in str(value).split(",")
        if item.strip()
    ]
    inputs: dict[str, Any] = {"formats": formats}
    timeline_slug = parsed.timeline_slug or parsed.timeline_ref
    for name in (
        "shot", "view", "sample", "every", "every_frames", "include_cuts",
        "render_run", "columns", "page_size", "resolution", "include_media",
        "range", "at", "clip", "asset", "context", "neighbors", "show", "hide",
        "track", "detail", "occurrence",
    ):
        value = getattr(parsed, name, None)
        if value not in (None, "", []):
            inputs[name] = value
    if timeline_slug not in (None, ""):
        inputs["timeline_slug"] = timeline_slug
    # The public text and visual routes use the same bounded selector
    # normalizer. Preserve all existing input spellings, but canonicalize the
    # occurrence identity before crossing the SDK boundary.
    inputs["occurrence"] = inspection_options({"occurrence": getattr(parsed, "occurrence", None)})["occurrence"]
    if inputs["occurrence"] is None:
        inputs.pop("occurrence")
    shown_components = inputs.get("show") or []
    hidden_components = inputs.get("hide") or []
    native_input_only = (
        "inputs" in shown_components
        and "output" in hidden_components
        and not inputs.get("render_run")
        and not inputs.get("include_media")
    )
    native_visualize = getattr(getattr(parsed.client, "timelines", None), "visualize", None)
    if native_input_only and callable(native_visualize):
        result = native_visualize(
            parsed.project,
            timeline_slug,
            formats=formats,
            occurrence=inputs.get("occurrence"),
            shot=inputs.get("shot"),
            clip=inputs.get("clip"),
            asset=inputs.get("asset"),
            track=inputs.get("track"),
            range_value=inputs.get("range"),
            detail=bool(inputs.get("detail")),
            neighbors=int(inputs.get("neighbors") or 0),
            out=getattr(parsed, "out", None),
        )
    else:
        result = parsed.client.invoke_result(
            "rendering.timeline_visualize",
            kind="executor",
            project=parsed.project,
            inputs=inputs,
            out=getattr(parsed, "out", None),
            # Wait for the admitted task so the CLI cannot report a successful run
            # before the PNG/manifest artifacts (or a terminal failure) exist.
            wait=True,
        )
    if result.ok:
        outputs = result.outputs
        if isinstance(outputs, Mapping):
            outputs = dict(outputs)
            summary = _visualization_artifact_summary(outputs)
            if summary is not None:
                outputs["artifact_summary"] = summary
            outputs["navigation"] = _visualization_navigation_help(
                project=parsed.project,
                inputs=inputs,
                outputs=outputs,
            )
            human_outputs = outputs
        envelope = DomainResult.success(
            {
                "capability_id": result.capability_id,
                "run_id": result.run_id,
                "kernel_run_id": result.kernel_run_id,
                "kernel_task_id": result.kernel_task_id,
                "kernel_attempt_id": result.kernel_attempt_id,
                "manifest_path": result.manifest_path,
                "outputs": outputs,
            }
        )
    else:
        detail = dict(result.error or {})
        category = str(detail.get("sdk_category") or "invocation")
        envelope = DomainResult.failure(
            ErrorObject(
                code="validation_error" if category == "validation" else "invocation_error",
                message=str(detail.get("message") or "timeline visualization failed"),
                details={
                    "sdk_error": detail.get("sdk_error"),
                    "sdk_category": category,
                    "validation": detail.get("validation"),
                    "run_id": result.run_id,
                    "kernel_run_id": result.kernel_run_id,
                    "kernel_task_id": result.kernel_task_id,
                    "kernel_attempt_id": result.kernel_attempt_id,
                },
            )
        )
    exit_status = print_result(envelope, as_json=parsed.json)
    if result.ok and not parsed.json:
        if human_outputs is not None:
            _print_visualization_navigation(human_outputs)
    return exit_status


def _visualization_navigation_help(
    *, project: str | None, inputs: Mapping[str, Any], outputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Expose copyable zoom/sampling/navigation guidance in CLI results."""
    identity = [
        "python3", "-m", "astrid", "timelines", "visualize",
        "--project", str(project or "<project>"),
    ]
    timeline = inputs.get("timeline_slug")
    if timeline not in (None, ""):
        identity += ["--timeline-slug", str(timeline)]
    render_run = inputs.get("render_run")
    if render_run not in (None, ""):
        identity += ["--render-run", str(render_run)]

    def tokens(value: Any) -> list[str]:
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value if str(item)]
        return [str(value)] if value not in (None, "") else []

    def base(*, components: bool = True, sampling: bool = True, resolution: bool = True) -> list[str]:
        argv = identity + ["--view", str(inputs.get("view") or "filmstrip")]
        if components:
            shown = tokens(inputs.get("show"))
            hidden = tokens(inputs.get("hide"))
            if shown:
                argv += ["--show", ",".join(shown)]
            if hidden:
                argv += ["--hide", ",".join(hidden)]
            for track in tokens(inputs.get("track")):
                argv += ["--track", track]
            for key, flag in (("shot", "--shot"), ("clip", "--clip"), ("occurrence", "--occurrence"), ("asset", "--asset")):
                value = inputs.get(key)
                if value not in (None, ""):
                    argv += [flag, str(value)]
        if inputs.get("detail"):
            argv += ["--detail"]
        if inputs.get("sample") not in (None, "", "interval"):
            argv += ["--sample", str(inputs["sample"])]
        if inputs.get("include_cuts"):
            argv += ["--include-cuts"]
        if inputs.get("columns") not in (None, ""):
            argv += ["--columns", str(inputs["columns"])]
        if inputs.get("page_size") not in (None, ""):
            argv += ["--page-size", str(inputs["page_size"])]
        if sampling:
            range_value = inputs.get("range")
            if isinstance(range_value, (list, tuple)) and len(range_value) == 2:
                range_value = f"{range_value[0]}..{range_value[1]}"
            if range_value not in (None, ""):
                argv += ["--range", str(range_value)]
            if inputs.get("at") not in (None, ""):
                argv += ["--at", str(inputs["at"])]
            if inputs.get("every") not in (None, ""):
                argv += ["--every", str(inputs["every"])]
            if inputs.get("every_frames") not in (None, ""):
                argv += ["--every-frames", str(inputs["every_frames"])]
        if resolution and inputs.get("resolution") not in (None, ""):
            value = inputs["resolution"]
            if isinstance(value, (list, tuple)) and len(value) == 2:
                value = f"{value[0]}x{value[1]}"
            argv += ["--resolution", str(value)]
        return argv

    # Build replacement commands from a clean base so mutually-exclusive
    # selectors (show/hide, every/every-frames, range/at) never duplicate.
    input_only = base(components=False, sampling=True, resolution=False) + [
        "--show", "inputs", "--hide", "output"
    ]
    clean = base(sampling=False, resolution=False)
    zoom_detail = [] if inputs.get("detail") else ["--detail"]
    pages = outputs.get("pages")
    primary_page = pages[0] if isinstance(pages, list) and pages else outputs.get("png")
    manifest_ref = outputs.get("manifest_path") or "MANIFEST"
    inspect_base = ["python3", "-m", "astrid", "timelines", "inspect", "--manifest", str(manifest_ref)]
    paired = "output" in tokens(inputs.get("show")) and "inputs" in tokens(inputs.get("show"))
    page_status = None
    if paired and isinstance(pages, list) and len(pages) > 1:
        page_status = f"Paired view generated {len(pages)} bite-sized pages; open them in numbered order."
    return {
        "primary_page": primary_page,
        "pages": pages,
        "markdown": outputs.get("markdown"),
        "inspection": shlex.join(inspect_base + ["--section", "summary"]),
        "status": page_status,
        "keyboard": [
            "Open the primary PNG page for visual inspection; use the bounded inspect command for exact card, placement, lane, or timing lookup.",
            "Use the rerun commands below to zoom, change sampling intervals, or narrow to input lanes.",
        ],
        "filters": [
            "Use Shot, Track, From/To, Samples, and Density by rerunning with the matching flags.",
            "Density only reduces captured frames; rerun for finer samples.",
        ],
        "commands": {
            "rerun": shlex.join(base()),
            "zoom": shlex.join(clean + ["--range", "START..END", "--every", "0.25", *zoom_detail]),
            "interval_seconds": shlex.join(clean + ["--every", "1"]),
            "interval_frames": shlex.join(clean + ["--every-frames", "12"]),
            "resolution": shlex.join(base(resolution=False) + ["--resolution", "960x540"]),
            "inputs_only": shlex.join(input_only),
            "pages": shlex.join(clean + ["--columns", "5", "--page-size", "10"]),
            "inspect_summary": shlex.join(inspect_base + ["--section", "summary"]),
            "inspect_cards": shlex.join(inspect_base + ["--section", "cards"]),
            "inspect_placements": shlex.join(inspect_base + ["--section", "placements"]),
            "inspect_audio": shlex.join(inspect_base + ["--section", "audio"]),
            "inspect_boundaries": shlex.join(inspect_base + ["--section", "boundaries"]),
        },
        "notes": [
            "--range uses a half-open START..END seconds window.",
            "--every and --every-frames are mutually exclusive.",
            "--columns/--page-size change static layout; --track narrows input lanes.",
            "paired output+inputs pages show one row by default (five cards across); use --columns 6 for six across, or pass --page-size N explicitly for a denser two-row page.",
        ],
    }


def _print_visualization_navigation(outputs: Mapping[str, Any]) -> None:
    """Print short, copyable navigation hints in human CLI mode.

    ``--json`` already carries the structured ``outputs.navigation`` object;
    human mode should still be actionable without requiring the operator to
    rerun the command with another flag.
    """
    navigation = outputs.get("navigation")
    if not isinstance(navigation, Mapping):
        return
    print("navigation:")
    primary_page = navigation.get("primary_page")
    if primary_page:
        print(f"  open PNG: {primary_page}")
    inspection = navigation.get("inspection")
    if inspection:
        print(f"  inspect (bounded): {inspection}")
    status = navigation.get("status")
    if status:
        print(f"  status: {status}")
    commands = navigation.get("commands")
    if not isinstance(commands, Mapping):
        return
    for label, key in (
        ("zoom", "zoom"),
        ("interval (seconds)", "interval_seconds"),
        ("interval (frames)", "interval_frames"),
        ("resolution", "resolution"),
        ("inputs only", "inputs_only"),
        ("pages", "pages"),
    ):
        command = commands.get(key)
        if command:
            print(f"  {label}: {command}")


def _cmd_inspect(parsed: argparse.Namespace) -> int:
    from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import inspect_filmstrip

    result = inspect_filmstrip(parsed.manifest, section=parsed.section, limit=parsed.limit, cursor=parsed.cursor,
                              frame=parsed.frame, card=parsed.card, shot=parsed.shot, occurrence=parsed.occurrence,
                              clip=parsed.clip, track=parsed.track, asset=parsed.asset, range_value=parsed.range_value)
    # This exact compact serialization is included in the inspector's byte cap.
    print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


def _configure_inspect(subparser: argparse.ArgumentParser) -> None:
    from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import INSPECTION_SECTIONS

    subparser.description = "Inspect a verified materialized filmstrip offline; no runtime or render admission. Responses are capped at 8 KiB."
    subparser.add_argument("--manifest", required=True, help="Materialized filmstrip manifest.json; bundle members are verified before reading.")
    subparser.add_argument("--section", default="summary", help="Named section: " + ", ".join(INSPECTION_SECTIONS))
    subparser.add_argument("--limit", type=int, default=10, help="Records per response: 1–50, default 10; byte cap may reduce the page.")
    subparser.add_argument("--cursor", default=None, help="Opaque cursor from this bundle and identical query.")
    subparser.add_argument("--frame", type=int, default=None, help="Exact decoded frame number.")
    for selector in ("card", "shot", "occurrence", "clip", "track", "asset"):
        subparser.add_argument("--" + selector, default=None, help="Exact " + selector + " identity (shot also accepts an exact name).")
    subparser.add_argument("--range", dest="range_value", default=None, help="Half-open START..END seconds window.")
    subparser.add_argument("--json", action="store_true", help="Compact JSON envelope is always used.")
    subparser.set_defaults(handler=_cmd_inspect)


def offline_inspect_main(args: list[str]) -> int:
    """Separate parser keeps argument errors bounded and skips runtime startup."""
    class OfflineParser(argparse.ArgumentParser):
        def error(self, message):
            raise ValueError("invalid_arguments")

    parser = OfflineParser(prog="astrid timelines inspect")
    _configure_inspect(parser)
    try:
        return _cmd_inspect(parser.parse_args(args))
    except ValueError:
        from astrid.packs.rendering.executors.timeline_visualize.inspection_contract import _inspection_error
        print(json.dumps(_inspection_error("invalid_arguments"), separators=(",", ":")))
        return 2


def _resolve_timeline_ref(client: Any, project: str, ref: str | None) -> str | None:
    """Return the explicit ref, falling back to the project's default timeline."""
    if ref not in (None, ""):
        return ref
    shown = client.projects.show(project)
    data = getattr(shown, "data", None)
    if isinstance(data, Mapping):
        metadata = data.get("metadata")
        if isinstance(metadata, Mapping):
            default = metadata.get("default_timeline_id")
            if default not in (None, ""):
                return str(default)
    return None


def _cmd_render(parsed: argparse.Namespace) -> int:
    """Render one kernel timeline, defaulting to the project's default timeline."""
    from astrid.sdk.contracts import DomainResult, ErrorObject

    ref = _resolve_timeline_ref(parsed.client, parsed.project, parsed.ref)
    if ref is None:
        return print_result(
            DomainResult.failure(
                ErrorObject(
                    code="validation_error",
                    message=(
                        "no timeline ref given and project "
                        f"{parsed.project!r} has no resolvable default timeline "
                        "(missing project or no default set); pass a timeline "
                        "slug or set one with astrid projects update "
                        "<project> --settings "
                        "'{\"default_timeline_id\": \"<timeline-id>\"}'"
                    ),
                    details={"project": parsed.project},
                )
            ),
            as_json=parsed.json,
        )
    inputs: dict[str, Any] = {"timeline_ref": ref}
    for name in ("expected_version", "output_name", "profile", "review"):
        value = getattr(parsed, name, None)
        if value not in (None, ""):
            inputs[name] = value
    if parsed.backend not in (None, ""):
        # ``--backend`` is the product-language spelling.  The rendering
        # executor's stable input/CLI contract calls this value ``selector``;
        # forwarding it as ``backend`` made the public option silently inert
        # because the manifest has no such input port.
        inputs["selector"] = parsed.backend
    result = parsed.client.invoke_result(
        "rendering.render",
        kind="executor",
        project=parsed.project,
        inputs=inputs,
        wait=parsed.wait,
        timeout_seconds=parsed.timeout_seconds,
    )
    if result.ok:
        run_id = result.kernel_run_id or result.run_id
        task_id = result.kernel_task_id
        handoff = (
            task_handoff(project=parsed.project, task_id=task_id, run_id=run_id)
            if task_id
            else {}
        )
        envelope = DomainResult.success(
            {
                "capability_id": result.capability_id,
                "run_id": result.run_id,
                "kernel_run_id": result.kernel_run_id,
                "kernel_task_id": result.kernel_task_id,
                "kernel_attempt_id": result.kernel_attempt_id,
                "state": str((result.raw_result or {}).get("state") or ("completed" if parsed.wait else "admitted")),
                "handoff": handoff,
                "outputs": result.outputs,
            }
        )
    else:
        detail = dict(result.error or {})
        category = str(detail.get("sdk_category") or "invocation")
        task_id = result.kernel_task_id
        run_id = result.kernel_run_id or result.run_id
        handoff = task_handoff(project=parsed.project, task_id=task_id, run_id=run_id) if task_id else {}
        envelope = DomainResult.failure(
            ErrorObject(
                code="validation_error" if category == "validation" else "invocation_error",
                message=str(detail.get("message") or "timeline render failed"),
                details={
                    "sdk_error": detail.get("sdk_error"),
                    "sdk_category": category,
                    "validation": detail.get("validation"),
                    "run_id": result.run_id,
                    "kernel_run_id": result.kernel_run_id,
                    "kernel_task_id": result.kernel_task_id,
                    "kernel_attempt_id": result.kernel_attempt_id,
                    "state": (result.raw_result or {}).get("state"),
                    "handoff": handoff,
                },
            )
        )
    if parsed.json or not envelope.ok:
        return print_result(envelope, as_json=parsed.json)
    data = envelope.data
    assert isinstance(data, Mapping)
    print(f"render {data['state']}")
    durable_run_id = data.get("kernel_run_id") or data.get("run_id")
    if durable_run_id:
        print(f"run: {durable_run_id}")
    if data.get("kernel_task_id"):
        print(f"task: {data['kernel_task_id']}")
    handoff = data.get("handoff")
    if isinstance(handoff, Mapping):
        if handoff.get("follow"):
            print(f"follow: {handoff['follow']}")
        if handoff.get("inspect"):
            print(f"inspect: {handoff['inspect']}")
        if handoff.get("events"):
            print(f"events: {handoff['events']}")
        if handoff.get("open"):
            print(f"open: {handoff['open']}")
        if handoff.get("recent"):
            print(f"recent: {handoff['recent']}")
    outputs = data.get("outputs")
    if data.get("state") == "completed" and isinstance(outputs, Mapping):
        artifacts = outputs.get("artifacts")
        if isinstance(artifacts, list):
            for artifact in artifacts:
                if isinstance(artifact, str):
                    print(f"output: {artifact}")
                elif isinstance(artifact, Mapping):
                    location = next(
                        (artifact.get(key) for key in ("url", "path", "locator", "object_id") if artifact.get(key)),
                        None,
                    )
                    if location:
                        print(f"output: {location}")
    return 0


# -- parser ----------------------------------------------------------------


def _configure_create(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("slug", help="Timeline slug (immutable).")
    subparser.add_argument("--name", required=True, help="Display name.")
    subparser.add_argument(
        "--config",
        type=_parse_json_object,
        default=None,
        help="Document config as a JSON object.",
    )
    subparser.add_argument(
        "--registry",
        type=_parse_json_object,
        default=None,
        help="Document registry as a JSON object.",
    )
    subparser.add_argument(
        "--default",
        action="store_true",
        help="Set this timeline as the project default.",
    )
    _add_idempotency_key(subparser)
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_create)


def _configure_list(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument(
        "--include-archived",
        dest="include_archived",
        action="store_true",
        help="Include archived timelines and their archived_at state.",
    )
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_list)


def _configure_show(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    subparser.add_argument(
        "--summary",
        action="store_true",
        help="Return a bounded editor summary with tracks, clip timing, and counts.",
    )
    subparser.add_argument(
        "--occurrence",
        default=None,
        help="Restrict the bounded inspection projection to one exact authored occurrence id.",
    )
    subparser.add_argument("--clip", default=None, help="Restrict the inspection projection to one authored clip id.")
    subparser.add_argument("--shot", default=None, help="Restrict the inspection projection to one authored shot id.")
    subparser.add_argument("--track", action="append", default=None, help="Restrict the inspection projection to one or more tracks.")
    subparser.add_argument("--asset", default=None, help="Restrict the inspection projection to one canonical asset key.")
    subparser.add_argument("--range", dest="range", default=None, help="Half-open START..END seconds window.")
    subparser.add_argument("--limit", type=int, default=50, help="Maximum bounded inspection rows (1–100).")
    subparser.add_argument("--cursor", default=None, help="Continue a bounded inspection page from its cursor.")
    subparser.add_argument("--detail", action="store_true", default=False, help="Include full bounded text for selected clips.")
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_show)


def _configure_retime_clip(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    subparser.add_argument("--clip-id", required=True, help="Authored clip id to retime.")
    subparser.add_argument("--at", type=float, required=True, help="New timeline start in seconds.")
    timing = subparser.add_mutually_exclusive_group()
    timing.add_argument(
        "--preserve-end",
        dest="timing_policy",
        action="store_const",
        const="preserve-end",
        help="Trim/extend the clip so its existing end stays fixed (the default).",
    )
    timing.add_argument(
        "--preserve-duration",
        dest="timing_policy",
        action="store_const",
        const="preserve-duration",
        help="Slide the clip without changing its duration; downstream clips may move/overlap.",
    )
    timing.add_argument(
        "--hold",
        type=float,
        default=None,
        help="Set an explicit new timeline duration in seconds (implies preserve-duration).",
    )
    subparser.set_defaults(timing_policy="preserve-end")
    subparser.add_argument(
        "--expected-version",
        dest="expected_version",
        type=int,
        default=None,
        help="Optional exact version from the editor context; stale context fails before saving.",
    )
    _add_idempotency_key(subparser)
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_retime_clip)


def _configure_save(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    subparser.add_argument(
        "--config",
        type=_parse_json_object,
        required=True,
        help="Whole-document config as a JSON object.",
    )
    subparser.add_argument(
        "--registry",
        type=_parse_json_object,
        required=True,
        help="Whole-document registry as a JSON object.",
    )
    subparser.add_argument(
        "--expected-version",
        dest="expected_version",
        type=int,
        required=True,
        help="Expected document version for the CAS save.",
    )
    _add_idempotency_key(subparser)
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_save)


def _configure_replace_clip(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    subparser.add_argument("--clip-id", required=True, help="Authored clip id to replace.")
    subparser.add_argument("--source-object-id", required=True, help="Project-owned managed object id (sha256:<64 hex chars>).")
    subparser.add_argument(
        "--expected-version",
        dest="expected_version",
        type=int,
        required=True,
        help="Expected canonical timeline document version for the atomic replacement.",
    )
    subparser.add_argument(
        "--timing",
        choices=("preserve-duration",),
        default="preserve-duration",
        help="Timing policy (the only supported policy is preserve-duration).",
    )
    _add_idempotency_key(subparser)
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_replace_clip)


def _configure_replace_parent_media(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    subparser.add_argument("--occurrence-id", required=True, help="Exact parent-composition occurrence to edit.")
    subparser.add_argument("--clip-id", required=True, help="Exact internal-timeline clip id to replace.")
    subparser.add_argument("--source-object-id", required=True, help="Admitted project-owned media digest/object id.")
    subparser.add_argument(
        "--expected-head",
        required=True,
        help="Exact parent-composition revision id read from the target; stale heads fail closed.",
    )
    _add_idempotency_key(subparser)
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_replace_parent_media)


def _configure_archive(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    _add_idempotency_key(subparser)
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_archive)


def _configure_recover(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument(
        "ref",
        help="Timeline UUID, ULID, or slug from list --include-archived.",
    )
    _add_idempotency_key(subparser)
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_recover)


def _configure_history(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_history)


def _configure_diff(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("ref", help="Timeline UUID, ULID, or slug.")
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_diff)


def _configure_visualize(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument(
        "timeline_ref", nargs="?", default=None,
        help="Optional positional timeline slug, UUID, or ULID (prefer --timeline-slug).",
    )
    subparser.add_argument(
        "--timeline-slug",
        default=None,
        help="Timeline slug, UUID, or ULID; omit to use the project default.",
    )
    subparser.add_argument(
        "--shot", default=None,
        help=(
            "Focus an authored shot id or exact name; use 'first' or a positive "
            "one-based authored-order ordinal (for example 1) for friendly shot selection."
        ),
    )
    subparser.add_argument("--range", dest="range", default=None, help="Zoom to a closed-open START..END seconds window.")
    subparser.add_argument("--at", default=None, help="Focus a timestamp.")
    subparser.add_argument("--clip", default=None, help="Focus an authored clip id.")
    subparser.add_argument("--occurrence", default=None, help="Focus an exact authored shot occurrence id.")
    subparser.add_argument("--asset", default=None, help="Focus a canonical asset key.")
    subparser.add_argument(
        "--show", action="append", default=None, metavar="COMPONENT[,COMPONENT...]",
        help=(
            "Add synchronized components: inputs, output, text, or audio "
            "(default: output,text,audio; add inputs for the paired view)."
        ),
    )
    subparser.add_argument(
        "--hide", action="append", default=None, metavar="COMPONENT[,COMPONENT...]",
        help="Hide components from the resolved surface.",
    )
    subparser.add_argument(
        "--track", action="append", default=None, metavar="TRACK_ID",
        help="Restrict input lanes; repeat for multiple tracks.",
    )
    subparser.add_argument(
        "--detail", action="store_true", default=None,
        help="Use enlarged frame, waveform, and text panels; combine with --range/--shot for a focused inspection.",
    )
    subparser.add_argument("--context", type=float, default=None, help="Context seconds around a focus.")
    subparser.add_argument("--neighbors", type=int, default=None, help="Neighbor clips retained around a focus.")
    subparser.add_argument(
        "--format", dest="formats", action="append", default=None,
        metavar="FORMAT[,FORMAT...]",
        type=_visualize_format_argument,
        help="Repeatable/comma-separated png or md (default: png,md).",
    )
    subparser.add_argument(
        "--view",
        choices=("filmstrip",),
        default="filmstrip",
        help="Rendered paired filmstrip as static PNG/Markdown/JSON evidence (default and only view).",
    )
    subparser.add_argument("--sample", choices=("interval", "clips", "cuts", "shots"), default=None,
                           help="Filmstrip sampling: interval (default), picture clips, cut boundaries, or authored story beats.")
    sampling = subparser.add_mutually_exclusive_group()
    sampling.add_argument("--every", type=float, default=None,
                          help="Filmstrip interval in seconds (default: 0.5); rerun with --range START..END to zoom.")
    sampling.add_argument("--every-frames", type=int, default=None,
                          help="Filmstrip interval in exact rendered frames; replaces --every (rerun for finer samples).")
    subparser.add_argument(
        "--include-cuts", action="store_true", default=None,
        help="With interval sampling, also capture visual cut-neighbor frames.",
    )
    subparser.add_argument("--render-run", default=None,
                           help="Exact successful render run, or latest (filmstrip default).")
    subparser.add_argument("--columns", type=int, default=None,
                           help="Filmstrip contact sheet columns (default: 5; paired pages use one row by default).")
    subparser.add_argument("--page-size", type=int, default=None,
                           help="Filmstrip cards per static page (default: 50 standalone; paired pages use one row, or explicitly opt into up to two rows / 10 cards).")
    subparser.add_argument("--resolution", default=None, metavar="WIDTHxHEIGHT",
                           help="Filmstrip frame resolution, e.g. 960x540; recorded and applied exactly by the executor.")
    subparser.add_argument(
        "--include-media", action="store_true", default=None,
        help="Include a relative, digest-verified rendered video for offline filmstrip playback.",
    )
    subparser.add_argument(
        "--out", default=None,
        help=(
            "Unsupported compatibility option; project visualization owns output. "
            "Omit it and use the returned durable manifest_path."
        ),
    )
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_visualize)


def _configure_render(subparser: argparse.ArgumentParser) -> None:
    _add_project_arg(subparser)
    subparser.add_argument("--review", action="store_true", default=None, help="Burn in shot names/time plus pinned authored speech captions at the bottom (Remotion/Three.js).")
    subparser.add_argument(
        "ref",
        nargs="?",
        default=None,
        help=(
            "Canonical timeline UUID, ULID, or slug. "
            "When omitted, the project's default timeline is rendered."
        ),
    )
    subparser.add_argument(
        "--expected-version",
        dest="expected_version",
        type=int,
        default=None,
        help="Optional exact kernel config version; stale pins fail before admission.",
    )
    subparser.add_argument(
        "--backend",
        default=None,
        help="Qualified renderer id or supported compatibility selector.",
    )
    subparser.add_argument(
        "--profile",
        type=_parse_json_object,
        default=None,
        metavar="JSON",
        help=(
            "Flat RenderProfile v1 JSON object (no video/audio nesting). "
            "Complete Remotion MP4 example: "
            "{\"width\": 1920, \"height\": 1080, \"fps_rational\": [30, 1], "
            "\"time_base\": [1, 90000], \"container\": \"mp4\", "
            "\"video_codec\": \"h264\", \"video_profile\": null, "
            "\"video_level\": null, \"pixel_format\": \"yuv420p\", "
            "\"audio_codec\": \"aac\", \"audio_sample_rate\": 48000, "
            "\"audio_channel_layout\": \"stereo\", \"duration_tolerance\": 1}. "
            "The audio trio must be supplied together or all omitted. When omitted, the "
            "resolved theme canvas is used (default 1920x1080 at 30 fps), "
            "not legacy config.output resolution/fps hints. Explicit profiles must "
            "match the authoritative theme canvas; set theme_overrides.visual.canvas "
            "for a different size."
        ),
    )
    subparser.add_argument(
        "--output-name",
        default=None,
        help=(
            "Plain output filename (default hype.mp4). A canonical timeline stamped "
            "metadata.astrid_layer.alpha=true may request .mov for ProRes 4444/PCM output."
        ),
    )
    completion = subparser.add_mutually_exclusive_group()
    completion.add_argument(
        "--wait",
        dest="wait",
        action="store_true",
        default=True,
        help="Follow the render to completion and propagate terminal failure (default).",
    )
    completion.add_argument(
        "--detach",
        dest="wait",
        action="store_false",
        help="Return after admission with state=admitted; inspect the returned task/run later.",
    )
    subparser.add_argument(
        "--timeout-seconds",
        type=float,
        default=3600.0,
        help="Maximum wait for --wait before returning a non-success result (default: 3600).",
    )
    _add_json_flag(subparser)
    subparser.set_defaults(handler=_cmd_render)


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "create",
        help="Create a timeline (one SDK call, idempotency key returned).",
        configure=_configure_create,
    ),
    CommandSpec(
        "list",
        help="List active timelines in a project (slug ascending).",
        configure=_configure_list,
    ),
    CommandSpec(
        "show",
        help="Show one timeline by UUID, ULID, or slug (use --summary for editor context).",
        configure=_configure_show,
    ),
    CommandSpec(
        "retime-clip",
        help="Retime one clip; preserve-end is the safe default, preserve-duration explicitly slides it.",
        configure=_configure_retime_clip,
    ),
    CommandSpec(
        "save",
        help="Whole-document CAS save (one SDK call, stale_version mapped).",
        configure=_configure_save,
    ),
    CommandSpec(
        "replace-clip",
        help="Atomically replace one managed-media clip while preserving duration.",
        configure=_configure_replace_clip,
    ),
    CommandSpec(
        "replace-parent-media",
        help="Atomically replace one clip in an exact canonical parent-composition closure.",
        configure=_configure_replace_parent_media,
    ),
    CommandSpec(
        "archive",
        help="Archive a timeline (reversible with recover).",
        configure=_configure_archive,
    ),
    CommandSpec(
        "recover",
        help="Restore archived work; safe to repeat (changed=false when active).",
        configure=_configure_recover,
    ),
    CommandSpec(
        "history",
        help="Ordered lifecycle event history for one timeline.",
        configure=_configure_history,
    ),
    CommandSpec(
        "diff",
        help="Deterministic adjacent-version diffs for one timeline.",
        configure=_configure_diff,
    ),
    CommandSpec(
        "visualize",
        help="Build a timeline evidence pack synchronously through the public SDK.",
        configure=_configure_visualize,
        requires_pack_host=True,
    ),
    CommandSpec(
        "inspect",
        help="Read bounded named sections of a verified filmstrip bundle offline.",
        configure=_configure_inspect,
    ),
    CommandSpec(
        "render",
        help="Render a canonical kernel timeline with optional version pinning.",
        configure=_configure_render,
        requires_pack_host=True,
    ),
)


def build_parser(client: Any) -> argparse.ArgumentParser:
    """Build the ``timelines`` product-family parser stamped with *client*.

    Exactly the ten verbs above are registered — no aliases, no legacy
    migration/push/pull/sync/audit/erase/repair verbs, and no ``copy``
    (reserved for m6) — plus the manifest-declared nested ``shots`` mount
    (``astrid timelines shots <verb>``) embedded from the shots product
    parser.
    """
    from astrid.packs.shots import cli as shots_cli

    def _configure_shots(subparser: argparse.ArgumentParser) -> None:
        nested = subparser.add_subparsers(dest="shot_command", required=True)
        register_product_commands(nested, shots_cli.COMMANDS, family="shots", client=client)

    parser = argparse.ArgumentParser(
        prog="astrid timelines",
        description=(
            "Timeline create/list/show/retime-clip/save/replace-clip/archive/recover/history/diff/visualize/render "
            "(product family); nested shots beneath 'timelines shots'."
        ),
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_product_commands(
        subparsers,
        (
            *COMMANDS,
            CommandSpec(
                "shots",
                help="Nested project-level shot list/create/show/add/remove/reorder "
                "(manifest-owned mount).",
                configure=_configure_shots,
            ),
        ),
        family=_FAMILY,
        client=client,
    )
    return parser
