"""Public SDK discovery and invocation helpers.

This module keeps invocation orchestration behind the SDK package boundary.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from astrid.core.contracts.binding import (
    BindingError,
    assert_provided_inputs_bound,
    expand_command,
)

from ._module import _sdk_module
from .exceptions import (
    AstridSDKError,
    CapabilityInvocationError,
    CapabilityMissingInputError,
    CapabilityPreconditionError,
    CapabilityValidationError,
    UnsupportedCapabilityError,
    _sdk_error_from_exception,
)
from .results import DiscoveryResult, InvocationResult, _json_safe, _json_safe_mapping


def _expanded_config_hash(config: Mapping[str, Any]) -> str:
    """Hash the exact in-memory expansion sent to the renderer."""
    payload = json.dumps(
        config, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def discover(
    *,
    project_root: str | Path | None = None,
    extra_pack_roots: tuple[str, ...] = (),
    banodoco_config: Any | None = None,
    active_theme: str | Path | None = None,
    include_missing_roots: bool = False,
    kind: str | None = None,
) -> DiscoveryResult:
    sdk_module = _sdk_module()
    discovered_packs = sdk_module._discover_pack_inventory(
        project_root=project_root,
        extra_pack_roots=extra_pack_roots,
    )
    pack_permission_ids_by_pack_id = sdk_module._pack_permission_ids_by_pack_id(discovered_packs)
    executor_registry, orchestrator_registry, element_registry = sdk_module._load_registries(
        project_root=project_root,
        extra_pack_roots=extra_pack_roots,
        banodoco_config=banodoco_config,
        include_missing_roots=include_missing_roots,
        include_elements=True,
    )
    if element_registry is None:
        raise CapabilityInvocationError("element registry was not loaded")
    (
        packs,
        generation_backends,
        element_kinds,
        generation_features,
        generation_modes,
    ) = sdk_module._build_discovery_metadata(
        discovered_packs,
        element_registry=element_registry,
    )

    if pack_permission_ids_by_pack_id:
        executors = tuple(
            sdk_module._capability_from_executor(
                definition,
                executor_registry,
                pack_permission_ids_by_pack_id=pack_permission_ids_by_pack_id,
            )
            for definition in executor_registry.list()
        )
        orchestrators = tuple(
            sdk_module._capability_from_orchestrator(
                definition,
                orchestrator_registry,
                pack_permission_ids_by_pack_id=pack_permission_ids_by_pack_id,
            )
            for definition in orchestrator_registry.list()
        )
        elements = tuple(
            sdk_module._capability_from_element(
                definition,
                pack_permission_ids_by_pack_id=pack_permission_ids_by_pack_id,
            )
            for definition in element_registry.list()
        )
    else:
        executors = tuple(
            sdk_module._capability_from_executor(definition, executor_registry)
            for definition in executor_registry.list()
        )
        orchestrators = tuple(
            sdk_module._capability_from_orchestrator(definition, orchestrator_registry)
            for definition in orchestrator_registry.list()
        )
        elements = tuple(
            sdk_module._capability_from_element(definition)
            for definition in element_registry.list()
        )
    if kind is not None and kind not in ("executor", "orchestrator", "element"):
        raise CapabilityValidationError(
            f"discover(kind=...) must be one of 'executor', 'orchestrator', "
            f"'element' — got {kind!r}"
        )
    executors = executors if kind in (None, "executor") else ()
    orchestrators = orchestrators if kind in (None, "orchestrator") else ()
    elements = elements if kind in (None, "element") else ()
    return DiscoveryResult(
        executors=executors,
        orchestrators=orchestrators,
        elements=elements,
        capabilities=executors + orchestrators + elements,
        packs=packs,
        generation_backends=generation_backends,
        element_kinds=element_kinds,
        generation_features=generation_features,
        generation_modes=generation_modes,
    )


def get_capability(
    capability_id: str,
    *,
    kind: Any | None = None,
    element_kind: str | None = None,
    project_root: str | Path | None = None,
    extra_pack_roots: tuple[str, ...] = (),
    include_elements: bool = True,
    banodoco_config: Any | None = None,
    active_theme: str | Path | None = None,
    include_missing_roots: bool = False,
    _registries: tuple[Any, Any, Any | None] | None = None,
):
    sdk_module = _sdk_module()
    if _registries is None:
        executor_registry, orchestrator_registry, element_registry = sdk_module._load_registries(
            project_root=project_root,
            extra_pack_roots=extra_pack_roots,
            banodoco_config=banodoco_config,
            include_missing_roots=include_missing_roots,
            include_elements=include_elements or kind == "element" or kind is None,
        )
    else:
        executor_registry, orchestrator_registry, element_registry = _registries

    resolved = sdk_module._resolve_capability(
        capability_id,
        kind=kind,
        element_kind=element_kind,
        executor_registry=executor_registry,
        orchestrator_registry=orchestrator_registry,
        element_registry=element_registry,
    )
    # Keep direct describes consistent with discover(): pack-level and
    # capability-specific safety permissions are part of the public handle,
    # not only of the full inventory DTO.
    discovered_packs = sdk_module._discover_pack_inventory(
        project_root=project_root,
        extra_pack_roots=extra_pack_roots,
    )
    return sdk_module._apply_pack_permission_ids(
        resolved,
        pack_permission_ids_by_pack_id=sdk_module._pack_permission_ids_by_pack_id(discovered_packs),
    )


def _normalize_executor_result(result: Any) -> dict[str, Any]:
    payload = {
        "executor_id": result.executor_id,
        "kind": result.kind,
        "command": result.command,
        "cwd": result.cwd,
        "env": result.env,
        "payload": result.payload,
        "returncode": result.returncode,
        "dry_run": result.dry_run,
        "skipped": result.skipped,
        "skipped_reason": result.skipped_reason,
        "missing_binaries": result.missing_binaries,
        "error": result.error,
        "ok": result.ok,
        "run_id": getattr(result, "run_id", None),
        "run_root": getattr(result, "run_root", None),
        "outputs": getattr(result, "outputs", {}),
        "executor_version": getattr(result, "executor_version", None),
    }
    return _json_safe_mapping(payload)


def _normalize_orchestrator_result(result: Any) -> dict[str, Any]:
    return _json_safe_mapping(result.to_dict())


def _validate_manifest_preview_inputs(
    capability: Any,
    *,
    inputs: Mapping[str, Any] | None,
    orchestrator_args: tuple[str, ...],
) -> dict[str, Any]:
    """Validate only manifest-owned inputs for a read-only invocation preview.

    Dry-run is deliberately a ledger/manifest operation.  It must not build a
    runner request (which imports project/run helpers), inspect an output tree,
    or resolve a local project.  Port requirements and declared orchestrator
    inputs are still checked here so callers retain the useful typed failures
    they receive from a live admission attempt.
    """

    values = dict(inputs or {})
    ports = tuple(getattr(capability, "inputs", ()) or ())
    # Defaults belong to the manifest ledger.  Include them in the effective
    # preview values without consulting runtime or project state.
    for port in ports:
        if port.name not in values and getattr(port, "default", None) is not None:
            values[port.name] = port.default
    missing = [
        str(port.name)
        for port in ports
        if bool(getattr(port, "required", False))
        and getattr(port, "default", None) is None
        and values.get(port.name) in (None, "")
    ]
    if missing:
        raise CapabilityMissingInputError(
            f"{capability.capability_type} {capability.id!r} missing required input(s): "
            f"{', '.join(missing)}"
        )

    if capability.capability_type == "executor":
        metadata = capability.definition.get("metadata", {})
        choices = metadata.get("input_choices") if isinstance(metadata, Mapping) else None
        if isinstance(choices, Mapping):
            for input_name, raw_options in choices.items():
                if not isinstance(raw_options, (list, tuple)) or input_name not in values:
                    continue
                options = tuple(str(option) for option in raw_options)
                if str(values[input_name]) not in options:
                    rendered = ", ".join(options)
                    raise CapabilityValidationError(
                        f"invalid {input_name} {values[input_name]!r} for executor "
                        f"{capability.id!r}; valid options: {rendered}; recovery: retry with "
                        f"--{str(input_name).replace('_', '-')} <one of: {rendered}>"
                    )
        requirements = (
            metadata.get("input_requirements_by_choice")
            if isinstance(metadata, Mapping)
            else None
        )
        if isinstance(requirements, Mapping):
            for selector, choices_by_value in requirements.items():
                selected = values.get(str(selector))
                if selected is None or not isinstance(choices_by_value, Mapping):
                    continue
                required = choices_by_value.get(str(selected))
                if not isinstance(required, (list, tuple)):
                    continue
                missing_choice = [
                    str(name)
                    for name in required
                    if values.get(str(name)) in (None, "")
                ]
                if missing_choice:
                    raise CapabilityMissingInputError(
                        f"executor {capability.id!r} missing required input(s) for "
                        f"{selector}={selected!r}: {', '.join(missing_choice)}"
                    )
    else:
        declared = {str(port.name) for port in ports}
        unknown = sorted(set(values) - declared)
        if unknown:
            declared_hint = ", ".join(sorted(declared)) or "none"
            raise CapabilityValidationError(
                f"orchestrator {capability.id!r} does not declare SDK input(s): "
                f"{', '.join(unknown)}; declared inputs: {declared_hint}. recovery: pass the "
                "runtime flags through orchestrator_args=(\"--flag\", \"value\") and retry"
            )

    return _json_safe_mapping(values)


def _manifest_dry_run_result(
    capability: Any,
    *,
    inputs: Mapping[str, Any] | None,
    outputs: Mapping[str, Any] | None,
    brief: Path | str | None,
    python_exec: str | None,
    out: Path | str | None = None,
    orchestrator_args: tuple[str, ...] = (),
) -> tuple[dict[str, Any], bool]:
    """Build the stable no-side-effect preview envelope from a capability DTO."""

    validation_inputs = dict(inputs or {})
    if brief is not None:
        validation_inputs.setdefault("brief", brief)
    preview_inputs = _validate_manifest_preview_inputs(
        capability,
        inputs=validation_inputs,
        orchestrator_args=orchestrator_args,
    )
    if brief is not None:
        preview_inputs.setdefault("brief", _json_safe(brief))
    if python_exec is not None:
        preview_inputs.setdefault("python_exec", python_exec)
    preview = {
        "kind": "manifest-ledger",
        "capability_id": str(capability.id),
        "inputs": preview_inputs,
        "outputs": _json_safe_mapping(dict(outputs or {})),
    }
    command = _manifest_preview_command(
        capability,
        inputs=preview_inputs,
        outputs=outputs,
        brief=brief,
        python_exec=python_exec,
        out=out,
        orchestrator_args=orchestrator_args,
    )
    if capability.capability_type == "executor":
        return {
            "executor_id": capability.id,
            "kind": capability.native_kind,
            "command": command,
            "cwd": None,
            "env": {},
            "payload": {"preview": preview},
            "returncode": None,
            "dry_run": True,
            "skipped": False,
            "skipped_reason": "",
            "missing_binaries": [],
            "error": None,
            "ok": True,
            "run_id": None,
            "run_root": None,
            "outputs": {},
            "executor_version": None,
        }, True

    runtime = capability.definition.get("runtime", {})
    runtime_kind = runtime.get("kind") if isinstance(runtime, Mapping) else None
    return {
        "orchestrator_id": capability.id,
        "kind": capability.native_kind,
        "runtime_kind": runtime_kind or "unknown",
        "command": command,
        "planned_commands": [command] if command else [],
        "cwd": None,
        "env": {},
        "returncode": None,
        "dry_run": True,
        "outputs": {},
        "errors": [],
        "plan": {
            "steps": [],
            "summary": "manifest-ledger preview; execution deferred to the runtime",
        },
        "preview": preview,
        "ok": True,
    }, True


def _manifest_preview_command(
    capability: Any,
    *,
    inputs: Mapping[str, Any],
    outputs: Mapping[str, Any] | None,
    brief: Path | str | None,
    python_exec: str | None,
    out: Path | str | None = None,
    orchestrator_args: tuple[str, ...] = (),
) -> list[str]:
    """Expand a manifest command through the same lossless contract as execution."""

    definition = capability.definition
    ports = tuple(getattr(capability, "inputs", ()) or ())
    values: dict[str, Any] = {str(key): value for key, value in inputs.items()}
    for port in ports:
        if port.name not in values and getattr(port, "default", None) is not None:
            values[port.name] = port.default
    values.setdefault("brief", brief)
    values.setdefault("python_exec", python_exec or "python")
    values.setdefault("verbose", "false")
    if out not in (None, ""):
        values["out"] = out
    elif isinstance(outputs, Mapping) and "out" in outputs:
        values["out"] = outputs.get("out")

    metadata = definition.get("metadata", {})
    append_pipeline_out = False
    if capability.capability_type == "executor":
        raw_command = definition.get("command")
        if not isinstance(raw_command, Mapping):
            module = metadata.get("runtime_module") if isinstance(metadata, Mapping) else None
            if not isinstance(module, str) or not module:
                return []
            argv: list[str] = ["{python_exec}", "-m", module]
            append_pipeline_out = out not in (None, "")
            raw_command = {"argv": argv}
    else:
        runtime = definition.get("runtime")
        raw_command = runtime.get("command") if isinstance(runtime, Mapping) else None
    if not isinstance(raw_command, Mapping):
        return []
    raw_argv = raw_command.get("argv")
    if not isinstance(raw_argv, (list, tuple)):
        return []
    if "{orchestrator_args}" in raw_argv:
        flattened: list[Any] = []
        for part in raw_argv:
            if part == "{orchestrator_args}":
                flattened.extend(str(value) for value in orchestrator_args)
            else:
                flattened.append(part)
        raw_command = {**raw_command, "argv": flattened}
    try:
        result = expand_command(raw_command, ports, values, metadata)
        assert_provided_inputs_bound(result, ports, values, metadata)
    except BindingError as exc:
        if str(exc).startswith("missing mapped input"):
            raise CapabilityMissingInputError(
                f"capability {capability.id!r}: {exc}"
            ) from exc
        raise CapabilityValidationError(f"capability {capability.id!r}: {exc}") from exc
    command = list(result.argv)
    if append_pipeline_out:
        command.extend(("--out", str(values["out"])))
    return command


def _validate_timeline_visualize_inputs(
    inputs: Mapping[str, Any] | None,
    *,
    project: str | None,
    project_root: str | Path | None = None,
    out: str | Path | None = None,
    _client: Any | None = None,
) -> dict[str, Any]:
    """Validate visualization's selector/ownership contract before admission.

    This is intentionally read-only.  Timeline visualization's runner repeats
    the checks as defense-in-depth, but a public SDK call must reject a
    foreign, missing, or malformed timeline before kernel admission.
    """

    values = dict(inputs or {})
    raw_formats = values.get("formats")
    if raw_formats is not None:
        if isinstance(raw_formats, str):
            raw_formats = [raw_formats]
        if not isinstance(raw_formats, (list, tuple, set)):
            raise CapabilityValidationError(
                "rendering.timeline_visualize formats must be a list of png, svg, md, or all"
            )
        formats = {
            part.strip().lower()
            for token in raw_formats
            for part in str(token).split(",")
            if part.strip()
        }
        if not formats:
            raise CapabilityValidationError(
                "rendering.timeline_visualize formats must contain png, svg, md, or all"
            )
        allowed = {"png", "svg", "md", "all"}
        invalid = sorted(formats - allowed)
        if invalid:
            raise CapabilityValidationError(
                f"invalid visualization format(s): {', '.join(invalid)}; "
                "choose png, svg, md, or all"
            )
        if "all" in formats and len(formats) > 1:
            raise CapabilityValidationError(
                "visualization format 'all' cannot be combined with another format"
            )
    if out not in (None, ""):
        raise CapabilityValidationError(
            "--out is not supported for project timeline visualization; "
            "omit it and use the returned durable manifest_path"
        )
    # Timeline files are authoring/migration inputs only.  A live product
    # invocation must address a runtime-owned timeline by its stable ref.
    if "timeline_source" in values:
        raise CapabilityValidationError(
            "timeline_source is not a supported product input; use timeline_slug "
            "or the runtime-selected default"
        )
    if "filmstrip_authority" in values:
        raise CapabilityValidationError("filmstrip_authority is host-owned and cannot be supplied")
    view = values.get("view", "structure")
    if view not in {"structure", "filmstrip"}:
        raise CapabilityValidationError("view must be structure or filmstrip")
    if view == "filmstrip":
        if not isinstance(project, str) or not project.strip():
            raise CapabilityValidationError("filmstrip review requires project=<slug>")
        if values.get("project_slug") not in (None, "", project):
            raise CapabilityValidationError("project_slug does not match project")
        if any(values.get(key) for key in ("all", "from_view", "focus", "refresh_root")):
            raise CapabilityValidationError(
                "filmstrip review selects one managed render; all/from_view navigation "
                "belongs to the timeline view"
            )
        from .timeline_filmstrip import prepare_filmstrip
        from astrid.packs.rendering.executors.timeline_visualize.filmstrip_options import filmstrip_options
        try:
            filmstrip_options(values)
        except ValueError as exc:
            raise CapabilityValidationError(str(exc)) from exc
        return prepare_filmstrip(values, project=project, client=_client)
    if any(values.get(key) is not None for key in (
        "render_run", "sample", "every", "every_frames", "columns", "page_size", "include_media"
    )):
        raise CapabilityValidationError("filmstrip controls require view=filmstrip")

    has_ref = values.get("timeline_slug") not in (None, "")
    select_all = bool(values.get("all", False))
    if has_ref and select_all:
        raise CapabilityValidationError(
            "timeline_slug and all are mutually exclusive; choose one timeline ref or all"
        )
    from_view = values.get("from_view") not in (None, "")
    focus = values.get("focus") not in (None, "")
    if from_view != focus:
        raise CapabilityValidationError(
            "from_view and focus must be supplied together for visualization navigation"
        )
    cold_selectors = [
        name
        for name in ("shot", "range", "at", "clip", "asset")
        if values.get(name) not in (None, "")
    ]
    if len(cold_selectors) > 1:
        raise CapabilityValidationError(
            "cold selectors are mutually exclusive: "
            + ", ".join(f"--{name}" for name in cold_selectors)
        )
    refresh_root = bool(values.get("refresh_root", False))
    if refresh_root and not from_view:
        raise CapabilityValidationError("refresh_root requires from_view and focus")
    if from_view:
        conflicts = [
            name
            for name, present in (
                ("timeline_slug", has_ref),
                ("all", select_all),
                *((name, name in cold_selectors) for name in cold_selectors),
            )
            if present
        ]
        if conflicts:
            raise CapabilityValidationError(
                "from_view/focus cannot be combined with "
                + ", ".join(f"--{name.replace('_', '-')}" for name in conflicts)
            )
    filmstrip = values.get("filmstrip")
    rendered_video = values.get("rendered_video")
    layout = values.get("layout")
    if layout is not None and (
        not isinstance(layout, str) or layout not in {"time-scaled", "linear", "both"}
    ):
        raise CapabilityValidationError(
            "layout must be time-scaled, linear, or both"
        )
    if filmstrip is not None and (
        not isinstance(filmstrip, str)
        or filmstrip not in {"auto", "off", "assets", "rendered"}
    ):
        raise CapabilityValidationError(
            "filmstrip must be auto, off, assets, or rendered"
        )
    scope = values.get("scope")
    if scope is not None and (
        not isinstance(scope, str)
        or scope not in {
            "project",
            "timeline",
            "shot",
            "range",
            "clip",
            "asset",
            "timestamp",
        }
    ):
        raise CapabilityValidationError(
            "scope must be project, timeline, shot, range, clip, asset, or timestamp"
        )
    raw_context = values.get("context", 3.0)
    if (
        isinstance(raw_context, bool)
        or not isinstance(raw_context, (int, float))
        or not math.isfinite(float(raw_context))
        or float(raw_context) < 0
    ):
        raise CapabilityValidationError("context must be a finite non-negative number")
    raw_neighbors = values.get("neighbors", 0)
    if (
        isinstance(raw_neighbors, bool)
        or not isinstance(raw_neighbors, int)
        or raw_neighbors < 0
    ):
        raise CapabilityValidationError("neighbors must be a non-negative integer")
    if rendered_video not in (None, "") and filmstrip not in (None, "auto", "rendered"):
        raise CapabilityValidationError(
            "rendered_video requires filmstrip auto or rendered"
        )
    if filmstrip == "rendered" and rendered_video in (None, ""):
        raise CapabilityValidationError("filmstrip rendered requires rendered_video")
    requested_project = values.get("project_slug")
    if (
        requested_project not in (None, "")
        and project not in (None, "")
        and requested_project != project
    ):
        raise CapabilityValidationError(
            f"project_slug {requested_project!r} does not match project {project!r}"
        )

    if project is None or not str(project).strip():
        raise CapabilityValidationError(
            "rendering.timeline_visualize requires project=<slug> to resolve a managed timeline"
        )

    # Timeline identity and content come from the neutral runtime.  The
    # executor's local root is only a disposable materialization base for
    # frozen result rehydration; it is never scanned for a project or timeline.
    from astrid.packs.rendering.executors.timeline_visualize.select import (
        select_kernel_timelines,
    )

    managed_project = (
        Path(project_root).expanduser().resolve() if project_root is not None else None
    )

    if from_view:
        if managed_project is None:
            raise CapabilityValidationError(
                "from_view requires an explicit attempt-local project_root"
            )
        raw_view = Path(str(values["from_view"])).expanduser()
        if not raw_view.is_absolute():
            raise CapabilityValidationError(
                "from_view must be an absolute path; cwd-relative visualization paths "
                "are not accepted"
            )
        view_path = raw_view
        if not view_path.is_file():
            raise CapabilityValidationError(
                f"from_view must name an existing visualization manifest: {view_path}"
            )
        from astrid.packs.rendering.executors.timeline_visualize.frozen import (
            FrozenViewError,
            discard_rehydrated_pack,
            load_frozen_view,
            resolve_focus,
        )
        from astrid.packs.rendering.executors.timeline_visualize.ids import (
            parse_qualified_ref,
        )

        try:
            frozen = load_frozen_view(view_path, project_root=managed_project)
        except FrozenViewError as exc:
            raise CapabilityValidationError(f"from_view rejected: {exc}") from exc
        try:
            try:
                resolved_focus = resolve_focus(
                    frozen,
                    str(values["focus"]),
                    context_seconds=float(raw_context),
                    neighbors=raw_neighbors,
                )
                parsed_focus = parse_qualified_ref(str(values["focus"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise CapabilityValidationError(f"focus rejected: {exc}") from exc
            if refresh_root and (
                parsed_focus.kind != "TL" or resolved_focus.kind != "timeline"
            ):
                raise CapabilityValidationError(
                    "refresh_root focus must be the frozen timeline reference"
                )
            return {
                "mode": "frozen_view",
                "manifest_sha256": hashlib.sha256(view_path.read_bytes()).hexdigest(),
                "focus": str(values["focus"]),
                "snapshot_sns": frozen.snapshot_sns,
            }
        finally:
            discard_rehydrated_pack(frozen.pack_root)

    selected: list[Any] = []
    diagnostics: list[str] = []
    selected, diagnostics = select_kernel_timelines(
        managed_project,
        project_slug=str(project),
        slug=str(values["timeline_slug"]) if has_ref else None,
        all=select_all,
        default=not has_ref and not select_all,
        runtime_client=_client,
    )
    if not selected:
        detail = "; ".join(diagnostics) or "no eligible managed timeline was selected"
        raise CapabilityValidationError(f"timeline selection failed: {detail}")

    return {
        "mode": "kernel",
        "timelines": [
            {
                "timeline_id": row.timeline_id,
                "head_version": row.config_version,
                "head_event_id": row.head_event_id,
                "head_hash": row.head_hash,
            }
            for row in selected
        ],
        # The worker token used by the generic host is intentionally not
        # granted projects:read. Carry the already-authenticated admission
        # snapshot into the child so execution verifies the same rows without
        # attempting a second project discovery under worker credentials.
        "timeline_snapshots": [
            {
                "timeline_id": row.timeline_id,
                "timeline_ulid": row.timeline_ulid,
                "slug": row.slug,
                "name": row.name,
                "is_default": row.is_default,
                "config": row.config,
                "registry": row.registry,
                "config_version": row.config_version,
                "head_event_id": row.head_event_id,
                "head_hash": row.head_hash,
                "head_created_at": row.head_created_at,
            }
            for row in selected
        ],
    }


def _payload_manifest_path(raw_result: Mapping[str, Any]) -> str | None:
    payload = raw_result.get("payload")
    if not isinstance(payload, Mapping):
        return None
    for key in ("manifest_path", "manifest"):
        value = payload.get(key)
        if not isinstance(value, str):
            continue
        path = Path(value).expanduser().resolve()
        if path.name == "manifest.json":
            return str(path)
    return None


_RENDER_PROFILE_REQUIRED_FIELDS = (
    "width",
    "height",
    "fps_rational",
    "time_base",
    "container",
    "video_codec",
    "video_profile",
    "video_level",
    "pixel_format",
    "duration_tolerance",
)
_RENDER_PROFILE_AUDIO_FIELDS = (
    "audio_codec",
    "audio_sample_rate",
    "audio_channel_layout",
)
_RENDER_PROFILE_ALLOWED_FIELDS = frozenset(
    (*_RENDER_PROFILE_REQUIRED_FIELDS, *_RENDER_PROFILE_AUDIO_FIELDS)
)
_RENDER_PROFILE_EXAMPLE = {
    "width": 1920,
    "height": 1080,
    "fps_rational": [30, 1],
    "time_base": [1, 90000],
    "container": "mp4",
    "video_codec": "h264",
    "video_profile": None,
    "video_level": None,
    "pixel_format": "yuv420p",
    "audio_codec": "aac",
    "audio_sample_rate": 48000,
    "audio_channel_layout": "stereo",
    "duration_tolerance": 1,
}


def _render_profile_guidance() -> str:
    example = json.dumps(_RENDER_PROFILE_EXAMPLE, separators=(",", ":"))
    return (
        "--profile uses the flat RenderProfile v1 object (no video/audio nesting); "
        "audio_codec, audio_sample_rate, and audio_channel_layout must be supplied "
        "together or all omitted. Explicit profiles must match the authoritative "
        "theme canvas; set theme_overrides.visual.canvas for a different size. "
        f"Complete Remotion MP4 example: {example}"
    )


def _validate_explicit_render_profile(profile: Any) -> None:
    """Validate the frozen flat profile contract before kernel admission."""

    if profile is None:
        return
    if not isinstance(profile, Mapping):
        raise CapabilityValidationError(
            f"invalid render profile: expected a JSON object. {_render_profile_guidance()}"
        )
    missing = [field for field in _RENDER_PROFILE_REQUIRED_FIELDS if field not in profile]
    unknown = sorted(str(field) for field in profile if field not in _RENDER_PROFILE_ALLOWED_FIELDS)
    key_issues: list[str] = []
    if missing:
        key_issues.append("missing required field(s): " + ", ".join(missing))
    if unknown:
        key_issues.append("unknown field(s): " + ", ".join(unknown))
    if key_issues:
        raise CapabilityValidationError(
            "invalid render profile: " + "; ".join(key_issues) + ". " + _render_profile_guidance()
        )
    from astrid.core.rendering.contracts import RenderProfile

    try:
        RenderProfile.from_dict(profile)
    except (TypeError, ValueError) as exc:
        raise CapabilityValidationError(
            f"invalid render profile: {exc}. {_render_profile_guidance()}"
        ) from exc


def _validate_managed_profile_theme_compatibility(
    profile: Mapping[str, Any] | None,
    *,
    timeline: Mapping[str, Any],
    registry: Mapping[str, Any],
    timeline_slug: str,
) -> None:
    """Reject canvas/fps profiles that cannot match the canonical theme.

    This is intentionally managed-ref-only. Explicit file-mode callers retain
    the renderer's historical support-selection semantics.
    """

    if profile is None:
        return
    from astrid.core.rendering.profile import resolve_render_profile

    try:
        authoritative = resolve_render_profile(
            timeline,
            registry,
            audio_ownership="rendered",
        )
    except (TypeError, ValueError, OSError, FileNotFoundError) as exc:
        raise CapabilityValidationError(
            f"cannot resolve authoritative theme canvas for canonical timeline "
            f"{timeline_slug!r}: {exc}. Fix the timeline theme and retry"
        ) from exc

    mismatches: list[str] = []
    for field, expected in (
        ("width", authoritative.width),
        ("height", authoritative.height),
        ("fps_rational", list(authoritative.fps_rational)),
    ):
        requested = profile.get(field)
        if requested != expected:
            mismatches.append(
                f"{field}={requested!r} (authoritative theme canvas produces {expected!r})"
            )
    if mismatches:
        raise CapabilityValidationError(
            f"invalid render profile for canonical timeline {timeline_slug!r}: "
            + "; ".join(mismatches)
            + ". Explicit profiles must match the authoritative theme canvas; "
            "use the default profile from timelines render --help or set "
            "theme_overrides.visual.canvas to the requested width, height, and fps, then retry"
        )


def _prepare_managed_render_inputs(
    inputs: Mapping[str, Any] | None,
    *,
    project: str | None,
    _client: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Resolve the explicit render ref and hand it to the runtime host.

    Snapshot bytes remain in the admission envelope until the generic host
    materializes them beneath the assigned attempt.
    """

    values = dict(inputs or {})
    timeline_ref = values.get("timeline_ref")
    expected_version = values.get("expected_version")
    if timeline_ref in (None, ""):
        raise CapabilityValidationError(
            "rendering.render requires timeline_ref=<runtime timeline slug/UUID/ULID>; "
            "path-backed timeline inputs are not supported"
        )
    if values.get("timeline") not in (None, ""):
        raise CapabilityValidationError(
            "timeline and timeline_ref are mutually exclusive; use timeline for explicit "
            "file mode or timeline_ref for canonical managed mode"
        )
    if values.get("assets_registry") not in (None, ""):
        raise CapabilityValidationError(
            "assets_registry cannot be overridden with timeline_ref; the canonical timeline "
            "registry is pinned with the snapshot"
        )
    if project is None or not str(project).strip():
        raise CapabilityValidationError("rendering.render timeline_ref requires project=<slug>")
    if not isinstance(timeline_ref, str) or not timeline_ref.strip():
        raise CapabilityValidationError("timeline_ref must be a non-empty slug, UUID, or ULID")
    if expected_version is not None and (
        isinstance(expected_version, bool)
        or not isinstance(expected_version, int)
        or expected_version < 1
    ):
        raise CapabilityValidationError("expected_version must be a positive integer")
    _validate_explicit_render_profile(values.get("profile"))
    from astrid.packs.rendering.executors.render.managed_timeline import (
        ManagedRenderValidationError,
        _runtime_snapshot_registry,
        resolve_managed_render_snapshot,
        validate_managed_render_snapshot,
    )

    if _client is None:
        raise CapabilityInvocationError(
            "explicit generated runtime client is required for managed render admission"
        )
    try:
        snapshot = resolve_managed_render_snapshot(
            project_ref=str(project),
            timeline_ref=timeline_ref.strip(),
            expected_version=expected_version,
            client=_client,
        )
        from astrid.core.timeline.expand_shots import expand_shot_clips

        # Admission is intentionally split: the authoring parent may contain
        # composite ``shot`` clips, but every reference must resolve through
        # the SDK before expansion. The expander never invents or fetches a
        # missing shot and never talks to storage itself.
        child_records: list[dict[str, Any]] = []
        review_shots: list[dict[str, Any]] = []
        shot_occurrences: list[dict[str, Any]] = []
        shot_records: dict[str, dict[str, Any]] = {}
        from .render_shot_snapshot import shot_text_snapshot
        raw_clips = snapshot.config.get("clips", [])
        for index, clip in enumerate(raw_clips):
            if not isinstance(clip, Mapping) or clip.get("clipType") != "shot":
                continue
            if clip.get("shot_occurrence_id"):
                raise CapabilityValidationError(
                    f"canonical timeline {snapshot.timeline_slug!r} shot clip at index {index} "
                    "contains caller-authored shot_occurrence_id"
                )
            params = clip.get("params")
            shot_id = params.get("shot_id") if isinstance(params, Mapping) else None
            timeline_document_id = (
                params.get("timeline_document_id") if isinstance(params, Mapping) else None
            )
            if not isinstance(shot_id, str) or not shot_id:
                raise CapabilityValidationError(
                    f"canonical timeline {snapshot.timeline_slug!r} shot clip at index {index} "
                    "is missing a registered shot_id"
                )
            shot_result = _client.shots.show(str(project), shot_id)
            if not shot_result.ok or not shot_result.data:
                raise CapabilityValidationError(
                    f"canonical timeline {snapshot.timeline_slug!r} references unregistered shot "
                    f"{shot_id!r}"
                )
            if shot_id not in shot_records:
                shot_records[shot_id] = {
                    "shot_id": shot_id,
                    "name": str(shot_result.data.get("name") or shot_id),
                    "version": shot_result.data.get("version"),
                    "text_bindings": shot_text_snapshot(_client, str(project), shot_id),
                }
            # Placement is canonical render provenance, not a visual-only
            # review option.  Freeze every authored shot occurrence so later
            # filmstrip/visualizer consumers can map pinned bindings to the
            # rendered timeline even when review labels are disabled.
            occurrence_id = f"shot-occ-{len(shot_occurrences):04d}-{shot_id}"
            occurrence = {
                "shot_occurrence_id": occurrence_id,
                "shot_id": shot_id,
                "name": str(shot_result.data.get("name") or shot_id),
                "at": float(clip.get("at", 0)),
                "hold": float(clip.get("hold", 0)),
                "timeline_document_id": str(timeline_document_id or ""),
                "source_index": index,
            }
            shot_occurrences.append(occurrence)
            review_shots.append({"shot_id": shot_id, "name": occurrence["name"], "at": occurrence["at"], "hold": occurrence["hold"]})
            if not isinstance(timeline_document_id, str) or not timeline_document_id:
                raise CapabilityValidationError(
                    f"canonical timeline {snapshot.timeline_slug!r} shot {shot_id!r} "
                    "is missing timeline_document_id"
                )

        def load_child(ref: str) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
            child_result = _client.timelines.show(str(project), ref)
            if not child_result.ok or not child_result.data:
                raise ValueError(f"timeline {ref!r} was not found")
            child = child_result.data
            child_config = child.get("config")
            child_registry = child.get("registry")
            if not isinstance(child_config, Mapping) or not isinstance(child_registry, Mapping):
                raise ValueError(f"timeline {ref!r} has an invalid snapshot")
            child_records.append(
                {
                    "timeline_id": str(child["timeline_id"]),
                    "timeline_ulid": str(child.get("timeline_ulid") or child["timeline_id"]),
                    "slug": str(child["slug"]),
                    "config_version": int(child["config_version"]),
                    "config_hash": _expanded_config_hash(child_config),
                }
            )
            return child_config, child_registry

        try:
            expanded_config, expanded_registry = expand_shot_clips(
                snapshot.config,
                snapshot.registry,
                load_timeline=load_child,
            )
        except ValueError as exc:
            raise CapabilityValidationError(str(exc)) from exc
        # The pure expander can carry the registered id and authored-order
        # occurrence through arbitrary child payloads.  Pin the name here,
        # after reading it from the canonical shot registry; child/caller
        # metadata can never forge review provenance.
        occurrence_names = {
            item["shot_occurrence_id"]: item["name"] for item in shot_occurrences
        }
        for flat_clip in expanded_config.get("clips", []):
            if not isinstance(flat_clip, Mapping):
                continue
            occurrence_id = flat_clip.get("shot_occurrence_id")
            if occurrence_id is None:
                continue
            if occurrence_id not in occurrence_names:
                raise CapabilityValidationError(
                    f"expanded clip {flat_clip.get('id', '?')} has an unknown shot occurrence"
                )
            flat_clip["shot_name"] = occurrence_names[occurrence_id]
        from dataclasses import replace

        expanded_registry = _runtime_snapshot_registry(
            expanded_registry,
            project_ref=str(project),
            client=_client,
        )
        snapshot = replace(
            snapshot,
            config=expanded_config,
            registry=expanded_registry,
            materialized_registry_hash=_expanded_config_hash(expanded_registry),
            expansion={
                "children": child_records,
                "shots": [shot_records[key] for key in sorted(shot_records)],
                "occurrences": shot_occurrences,
                "expanded_config_hash": _expanded_config_hash(expanded_config),
            },
        )
        validate_managed_render_snapshot(snapshot)
    except ManagedRenderValidationError as exc:
        raise CapabilityValidationError(str(exc), details=exc.details) from exc
    except ValueError as exc:
        raise CapabilityValidationError(str(exc)) from exc
    _validate_managed_profile_theme_compatibility(
        values.get("profile"),
        timeline=snapshot.config,
        registry=snapshot.registry,
        timeline_slug=snapshot.timeline_slug,
    )
    from astrid.core.rendering.output_policy import (
        DEFAULT_RENDER_OUTPUT_NAME,
        RenderOutputPolicyError,
        validate_render_output_policy,
    )

    output_name = values.get("output_name", DEFAULT_RENDER_OUTPUT_NAME)
    if output_name is None:
        output_name = DEFAULT_RENDER_OUTPUT_NAME
    try:
        validate_render_output_policy(
            output_name,
            timeline=snapshot.config,
            profile=values.get("profile"),
        )
    except RenderOutputPolicyError as exc:
        raise CapabilityValidationError(str(exc), details=exc.details) from exc
    # Never trust caller-authored review labels: pin registered names alongside the render.
    values.pop("review_context", None)
    # ``review`` still controls only burned-in visual labels.  The occurrence
    # envelope is always pinned at admission for provenance and script maps.
    values["review_context"] = {"shots": review_shots}
    authority = snapshot.authority()
    values.update(
        {
            # The generic host materializes this immutable snapshot below the
            # assigned attempt.  The SDK never writes a project-side render
            # snapshot or hands a project-root locator to a renderer.
            "timeline_snapshot": {
                "config": dict(snapshot.config),
                "registry": dict(snapshot.registry),
            },
            "timeline_authority": authority,
        }
    )
    # The public selector and CAS guard are admission-only controls. The
    # resolved authority object below is the durable run input/cache identity;
    # do not leak these two controls as undeclared renderer CLI flags.
    values.pop("expected_version", None)
    return values, authority


def _discover_invocation_manifest_path(
    raw_result: Mapping[str, Any],
    *,
    out: Path | str | None,
) -> str | None:
    manifest_path = _payload_manifest_path(raw_result)
    if manifest_path is not None:
        return manifest_path
    outputs = raw_result.get("outputs")
    if isinstance(outputs, Mapping):
        output_manifest = outputs.get("manifest_path")
        if isinstance(output_manifest, str):
            candidate = Path(output_manifest).expanduser().resolve()
            if candidate.name == "manifest.json" and candidate.is_file():
                return str(candidate)
    roots: list[Path] = []
    for raw in (raw_result.get("run_root"), out):
        if raw in (None, ""):
            continue
        root = Path(str(raw)).expanduser().resolve()
        if root not in roots:
            roots.append(root)
    for root in roots:
        for candidate in (root / "manifest.json", root / "agent-view" / "manifest.json"):
            if candidate.is_file():
                return str(candidate)
    return None


def _filmstrip_cache_parent(
    *,
    project: str | None,
    cache_root: Path | str | None = None,
) -> Path:
    """Return the durable, project-namespaced filmstrip cache parent."""
    if cache_root is not None:
        base = Path(cache_root).expanduser().resolve()
    elif platform.system() == "Darwin":
        base = Path.home() / "Library" / "Caches" / "Astrid" / "timeline-visualize"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "astrid" / "timeline-visualize"
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", str(project or "unscoped")).strip("._") or "unscoped"
    return base / slug


def _materialize_filmstrip_outputs(
    raw_result: dict[str, Any],
    client: Any,
    *,
    project: str | None = None,
    cache_root: Path | str | None = None,
) -> str:
    """Rehydrate verified published evidence into a durable project cache."""
    import io
    import tempfile
    import zipfile
    from pathlib import PurePosixPath

    artifacts = raw_result.get("outputs", {}).get("artifacts", [])
    bundles = [a for a in artifacts if a.get("name") == "filmstrip_bundle"]
    if len(bundles) != 1:
        raise CapabilityInvocationError("filmstrip task did not publish its evidence bundle")
    artifact = bundles[0]
    digest = str(artifact.get("digest", "")).removeprefix("sha256:")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise CapabilityInvocationError("filmstrip bundle has an invalid digest")
    data = client.media.read_bytes("sha256:" + digest)
    if hashlib.sha256(data).hexdigest() != digest or len(data) != artifact.get("size"):
        raise CapabilityInvocationError("filmstrip bundle does not match its published digest and size")
    parent = _filmstrip_cache_parent(project=project, cache_root=cache_root)
    parent.mkdir(parents=True, exist_ok=True)
    root = parent / digest
    staging = Path(tempfile.mkdtemp(prefix=f".{digest[:12]}-", dir=parent))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > 10000 or sum(m.file_size for m in members) > 1024 ** 3:
                raise CapabilityInvocationError("filmstrip bundle exceeds evidence extraction limits")
            names: set[str] = set()
            for member in members:
                path = PurePosixPath(member.filename)
                if (path.is_absolute() or not path.parts or ".." in path.parts
                        or "\\" in member.filename or member.filename in names
                        or (member.external_attr >> 16) & 0o170000 == 0o120000):
                    raise CapabilityInvocationError("filmstrip bundle contains an unsafe or duplicate path")
                names.add(member.filename)
                destination = staging.joinpath(*path.parts)
                if member.is_dir():
                    destination.mkdir(parents=True, exist_ok=True)
                else:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(archive.read(member))
        manifest = staging / "manifest.json"
        document = json.loads(manifest.read_text(encoding="utf-8"))
        if document.get("kind") != "timeline_filmstrip" or not (staging / "filmstrip.html").is_file():
            raise CapabilityInvocationError("filmstrip bundle is missing its manifest or HTML entrypoint")
        declared = document.get("outputs")
        if not isinstance(declared, list):
            raise CapabilityInvocationError("filmstrip manifest lacks member integrity records")
        verified_members: set[str] = set()
        for member in declared:
            if not isinstance(member, Mapping):
                raise CapabilityInvocationError("filmstrip manifest has an invalid member")
            relative = member.get("path")
            if not isinstance(relative, str) or relative in verified_members:
                raise CapabilityInvocationError("filmstrip manifest has a duplicate or invalid path")
            member_path = PurePosixPath(relative)
            if member_path.is_absolute() or ".." in member_path.parts or "\\" in relative:
                raise CapabilityInvocationError("filmstrip manifest member escapes its bundle")
            path = staging.joinpath(*member_path.parts)
            if not path.is_file():
                raise CapabilityInvocationError("filmstrip manifest references a missing member")
            with path.open("rb") as stream:
                member_digest = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
            if member_digest != member.get("content_hash") or path.stat().st_size != member.get("bytes"):
                raise CapabilityInvocationError("filmstrip bundle member integrity mismatch")
            verified_members.add(relative)
        actual_members = {p.relative_to(staging).as_posix() for p in staging.rglob("*") if p.is_file()}
        if actual_members != verified_members | {"manifest.json"}:
            raise CapabilityInvocationError("filmstrip bundle has unrecorded members")
        index_path = staging / "frame-index.json"
        try:
            frame_index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CapabilityInvocationError("filmstrip frame index is invalid") from exc

        def verified_relative_member(value: object, label: str) -> Path | None:
            if value is None:
                return None
            if not isinstance(value, str):
                raise CapabilityInvocationError(f"filmstrip {label} path is invalid")
            relative = PurePosixPath(value)
            if relative.is_absolute() or not relative.parts or ".." in relative.parts or "\\" in value:
                raise CapabilityInvocationError(f"filmstrip {label} path is unsafe")
            candidate = staging.joinpath(*relative.parts)
            if not candidate.is_file() or value not in verified_members:
                raise CapabilityInvocationError(f"filmstrip {label} path is not verified")
            return candidate

        media = frame_index.get("media") if isinstance(frame_index, Mapping) else None
        audio_sidecar = frame_index.get("audio_sidecar") if isinstance(frame_index, Mapping) else None
        media_path = verified_relative_member(media.get("path") if isinstance(media, Mapping) else None, "media")
        audio_path = verified_relative_member(audio_sidecar.get("path") if isinstance(audio_sidecar, Mapping) else None, "audio sidecar")
        media_relative = media_path.relative_to(staging) if media_path is not None else None
        audio_relative = audio_path.relative_to(staging) if audio_path is not None else None
        # Publish only after the archive and every declared member have been
        # verified. A successful retry replaces the prior cache atomically;
        # a failed retry leaves an existing usable cache untouched.
        if root.exists():
            import shutil
            shutil.rmtree(root)
        os.replace(staging, root)
        staging = root
        manifest = root / "manifest.json"
        raw_result["outputs"].update({
            "pack_root": str(root), "manifest_path": str(manifest),
            "html": str(root / "filmstrip.html"),
            "pages": [str(p) for p in sorted(root.glob("filmstrip-*.png"))],
            "frame_index": str(root / "frame-index.json"),
        })
        if media_relative is not None:
            raw_result["outputs"]["media"] = str(root / media_relative)
        if audio_relative is not None:
            raw_result["outputs"]["audio_analysis"] = str(root / audio_relative)
        return str(manifest)
    except Exception:
        import shutil
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _invocation_outputs(
    raw_result: Mapping[str, Any],
    *,
    manifest_path: str | None,
    capability_id: str | None = None,
) -> dict[str, Any]:
    outputs: dict[str, Any] = {}
    declared = raw_result.get("outputs")
    if isinstance(declared, Mapping):
        outputs.update(declared)
    payload = raw_result.get("payload")
    if isinstance(payload, Mapping) and isinstance(payload.get("outputs"), Mapping):
        outputs.update(payload["outputs"])
    if manifest_path is not None:
        manifest = Path(manifest_path)
        try:
            document = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            document = None
        is_timeline_manifest = isinstance(document, dict) and document.get("kind") in {
            "timeline_visualize",
            "timeline_visualize_project",
        }
        if capability_id == "rendering.timeline_visualize" or is_timeline_manifest:
            pack_root = manifest.parent
            # Kernel completion publishes every evidence-pack member as its
            # own managed CAS object and removes private staging.  The parent
            # of the durable manifest is therefore a hash fan-out directory,
            # not the logical pack root.  Reuse the frozen loader's verified
            # task-output rehydration so the long-standing ``pack_root`` SDK
            # convenience remains an actually navigable directory.
            # The manifest is the runtime-owned result handle. Rehydration,
            # when needed for navigation, is persisted in the deterministic,
            # project-namespaced Astrid cache.
            outputs["pack_root"] = str(pack_root)
            outputs["manifest_path"] = str(manifest)
            page_pattern = "filmstrip-*.png" if isinstance(document, dict) and document.get("kind") == "timeline_filmstrip" else "PG*.png"
            if page_pattern == "filmstrip-*.png":
                outputs["html"] = str(pack_root / "filmstrip.html")
            outputs["pages"] = [
                str(path)
                for path in sorted(pack_root.rglob(page_pattern))
                if "filmstrip" not in path.relative_to(pack_root).parts
            ]
            outputs["file_hashes"] = {
                path.relative_to(pack_root).as_posix(): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in sorted(pack_root.rglob("*"))
                if path.is_file()
            }
    return _json_safe_mapping(outputs)


def _runtime_selected_project(client: Any | None = None) -> str | None:
    """Read the connected runtime's durable selection; never infer locally."""
    if client is None:
        return None
    current = getattr(getattr(client, "projects", None), "current", None)
    if not callable(current):
        raise CapabilityInvocationError("runtime client does not expose current project selection")
    result = current()
    if not result.ok:
        error = result.error
        if getattr(error, "code", None) == "not_found":
            return None
        from .exceptions import ServiceError, _SERVICE_ERROR_CLASSES
        error_type = _SERVICE_ERROR_CLASSES.get(error.code, ServiceError)
        raise error_type(error.message, details=error.details)
    data = result.data
    row = data.get("project") if isinstance(data, Mapping) else None
    if not isinstance(row, Mapping):
        raise CapabilityInvocationError("runtime current project returned an invalid selection")
    ref = row.get("project_id") or row.get("id") or row.get("slug")
    if not isinstance(ref, str) or not ref.strip():
        raise CapabilityInvocationError("runtime current project returned no project identity")
    return ref


def _project_scope(capability: Any) -> str:
    """Return validated executor project scope, defaulting old manifests to required."""
    definition = getattr(capability, "definition", None)
    metadata = definition.get("metadata", {}) if isinstance(definition, Mapping) else {}
    scope = metadata.get("project_scope", "required") if isinstance(metadata, Mapping) else "required"
    if scope not in {"required", "optional"}:
        raise CapabilityInvocationError(
            f"executor {getattr(capability, 'id', '<unknown>')!r} has invalid project_scope {scope!r}"
        )
    return str(scope)


def _kernel_invoke(
    capability: Any,
    *,
    kind: Any,
    project: str | None,
    inputs: Mapping[str, Any] | None,
    outputs: Mapping[str, Any] | None,
    extra_pack_roots: tuple[str, ...] = (),
    idempotency_context: Mapping[str, Any] | None = None,
    admission_metadata: Mapping[str, Any] | None = None,
    storage_estimate: Mapping[str, int] | None = None,
    registry: Any | None = None,
    _client: Any | None = None,
) -> tuple[str, str, str, Path | None, dict[str, Any], bool, Any]:
    """Admit an invocation through the runtime client and generic host.

    The SDK is a client of the workspace runtime.  It must not compose a
    local application, open SQLite, or execute a capability in-process on the
    normal invocation path. ``registry`` is an explicit dependency-injection
    seam for callers that provide test doubles and is intentionally unused by
    the runtime admission request.
    """
    del registry

    request_inputs = dict(inputs or {})
    # Runtime workers expand the manifest command directly and therefore do
    # not see the public SDK's separate ``project=`` argument.  Mirror the
    # in-process executor runner's derivation for declared project_slug ports
    # so project-scoped executors receive the same explicit input on either
    # path.  Callers can still provide the field, subject to preflight's
    # project identity check.
    input_ports = {
        str(port.name)
        for port in (getattr(capability, "inputs", ()) or ())
        if getattr(port, "name", None)
    }
    if project and "project_slug" in input_ports and "project_slug" not in request_inputs:
        request_inputs["project_slug"] = project

    spec: dict[str, Any] = {
        "capability_id": str(capability.id),
        "kind": str(kind),
        "inputs": _json_safe_mapping(request_inputs),
        "outputs": _json_safe_mapping(dict(outputs or {})),
        "extra_pack_roots": list(extra_pack_roots),
    }
    if idempotency_context:
        spec["authority_context"] = _json_safe_mapping(dict(idempotency_context))
    if admission_metadata:
        # Keep the transparent estimate out of capability inputs: it is task
        # admission evidence, not an executor-authored input.
        spec["admission_metadata"] = _json_safe_mapping(dict(admission_metadata))
    # Managed renders authorize their snapshot registry media at admission:
    # derive task input_object_ids from the immutable timeline snapshot so
    # the generic host can materialize registry assets below the attempt.
    input_manifest: list[str] = []
    raw_snapshot = request_inputs.get("timeline_snapshot")
    if isinstance(raw_snapshot, Mapping):
        raw_registry = raw_snapshot.get("registry")
        raw_assets = raw_registry.get("assets") if isinstance(raw_registry, Mapping) else None
        if isinstance(raw_assets, Mapping):
            seen: set[str] = set()
            for entry in raw_assets.values():
                if not isinstance(entry, Mapping):
                    continue
                candidate = next(
                    (
                        value
                        for value in (
                            entry.get("object_id"),
                            entry.get("media_id"),
                            entry.get("content_sha256"),
                            entry.get("digest"),
                            entry.get("sha256"),
                            entry.get("hash"),
                        )
                        if isinstance(value, str)
                        and len(value.removeprefix("sha256:")) == 64
                        and all(
                            ch in "0123456789abcdef"
                            for ch in value.removeprefix("sha256:")
                        )
                    ),
                    None,
                )
                if candidate is None:
                    continue
                normalized = candidate.removeprefix("sha256:")
                if normalized in seen:
                    continue
                seen.add(normalized)
                input_manifest.append(candidate)

    if (str(capability.id) == "rendering.timeline_visualize"
            and isinstance(idempotency_context, Mapping)
            and idempotency_context.get("mode") == "filmstrip"):
        # This authority is minted by managed-render preflight, never by a
        # public file argument. Generic-host materialization requires the
        # same immutable object in both inputs and the authorization manifest.
        video_id = idempotency_context.get("video_object_id")
        video_input = request_inputs.get("rendered_video")
        if (not isinstance(video_id, str) or not video_id.startswith("sha256:")
                or len(video_id) != 71
                or any(c not in "0123456789abcdef" for c in video_id[7:])
                or not isinstance(video_input, Mapping)
                or video_input.get("digest") != video_id
                or video_input.get("object_id") != video_id):
            raise CapabilityValidationError("filmstrip video admission identity mismatch")
        input_manifest.append(video_id)

    idempotency_key = hashlib.sha256(
        json.dumps(
            {
                "spec": spec,
                "input_object_ids": sorted(input_manifest),
                "storage_estimate": dict(storage_estimate or {}),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    if _client is None:
        raise CapabilityInvocationError(
            "explicit generated runtime client is required for task admission"
        )

    tasks = getattr(_client, "tasks", None)
    create_task = getattr(tasks, "create", None)
    if not callable(create_task):
        raise CapabilityInvocationError(
            "runtime client does not expose generated task admission"
        )
    result = create_task(
        project_id=project,
        capability=str(capability.id),
        spec=spec,
        input_manifest=input_manifest,
        idempotency_key=idempotency_key,
        storage_estimate=dict(storage_estimate) if storage_estimate is not None else None,
    )
    result_ok = bool(getattr(result, "ok", isinstance(result, Mapping)))
    data = getattr(result, "data", result if isinstance(result, Mapping) else None)
    if not result_ok:
        error = getattr(result, "error", None)
        if hasattr(error, "as_dict"):
            error = error.as_dict()
        elif isinstance(error, Mapping):
            error = dict(error)
        else:
            error = {
                "code": "runtime_error",
                "message": "runtime rejected task admission",
                "details": {},
            }
        return "", "", "", None, {"ok": False, "error": error}, False, None
    if not isinstance(data, Mapping):
        raise CapabilityInvocationError("runtime task admission returned no task resource")

    run_id = str(data.get("run_id") or "")
    task_id = str(data.get("task_id") or "")
    if not run_id or not task_id:
        raise CapabilityInvocationError(
            "runtime task admission returned an incomplete task resource"
        )
    attempt_id = str(data.get("attempt_id") or "")
    raw_result = {
        "ok": True,
        "run_id": run_id,
        "kernel_run_id": run_id,
        "kernel_task_id": task_id,
        "kernel_attempt_id": attempt_id,
        "task": dict(data),
    }
    return run_id, task_id, attempt_id, None, raw_result, True, None


def _wait_for_kernel_task(
    client: Any,
    *,
    task_id: str,
    run_id: str,
    timeout_seconds: float,
    poll_seconds: float,
) -> tuple[dict[str, Any], bool, str]:
    """Follow one admitted task to a terminal runtime-owned result."""
    if not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
        raise CapabilityValidationError("wait timeout_seconds must be positive")
    if not math.isfinite(float(poll_seconds)) or poll_seconds <= 0:
        raise CapabilityValidationError("wait poll_seconds must be positive")
    tasks = getattr(client, "tasks", None)
    show = getattr(tasks, "show", None)
    if not callable(show):
        raise CapabilityInvocationError(
            "runtime client does not expose task status for synchronous invocation"
        )

    deadline = time.monotonic() + float(timeout_seconds)
    while True:
        observed = show(task_id)
        observed_ok = bool(getattr(observed, "ok", isinstance(observed, Mapping)))
        data = getattr(observed, "data", observed if isinstance(observed, Mapping) else None)
        if not observed_ok or not isinstance(data, Mapping):
            error = getattr(observed, "error", None)
            if hasattr(error, "as_dict"):
                error = error.as_dict()
            return {
                "ok": False,
                "run_id": run_id,
                "kernel_run_id": run_id,
                "kernel_task_id": task_id,
                "error": {
                    "code": "task_status_unavailable",
                    "message": "render task status could not be read",
                    "details": dict(error) if isinstance(error, Mapping) else {},
                },
            }, False, ""

        task = dict(data)
        state = str(task.get("state") or task.get("status") or "").lower()
        attempt_id = str(task.get("attempt_id") or "")
        if state in {"succeeded", "completed"}:
            settled = task.get("result")
            settled = dict(settled) if isinstance(settled, Mapping) else {}
            output_rows = settled.get("outputs")
            return {
                "ok": True,
                "run_id": run_id,
                "kernel_run_id": run_id,
                "kernel_task_id": task_id,
                "kernel_attempt_id": attempt_id,
                "state": "completed",
                "task": task,
                "result": settled,
                "outputs": {
                    "artifacts": list(output_rows)
                    if isinstance(output_rows, list)
                    else []
                },
            }, True, attempt_id
        if state in {"failed", "cancelled"}:
            settled = task.get("result")
            settled = dict(settled) if isinstance(settled, Mapping) else {}
            failure = settled.get("error")
            if isinstance(failure, Mapping):
                message = str(failure.get("message") or f"render task {state}")
            else:
                message = str(failure or f"render task {state}")
            return {
                "ok": False,
                "run_id": run_id,
                "kernel_run_id": run_id,
                "kernel_task_id": task_id,
                "kernel_attempt_id": attempt_id,
                "state": state,
                "task": task,
                "error": {
                    "code": f"task_{state}",
                    "message": message,
                    "details": {"state": state, "result": settled},
                },
            }, False, attempt_id

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {
                "ok": False,
                "run_id": run_id,
                "kernel_run_id": run_id,
                "kernel_task_id": task_id,
                "kernel_attempt_id": attempt_id,
                "state": state or "unknown",
                "task": task,
                "error": {
                    "code": "task_wait_timeout",
                    "message": "render task did not reach a terminal state before the wait timeout",
                    "details": {
                        "state": state or "unknown",
                        "timeout_seconds": float(timeout_seconds),
                    },
                },
            }, False, attempt_id
        time.sleep(min(float(poll_seconds), remaining))


def invoke(
    capability_id: str,
    *,
    kind: Any,
    project_root: str | Path | None = None,
    extra_pack_roots: tuple[str, ...] = (),
    banodoco_config: Any | None = None,
    active_theme: str | Path | None = None,
    include_missing_roots: bool = False,
    out: Path | str | None = None,
    project: str | None = None,
    inputs: Mapping[str, Any] | None = None,
    outputs: Mapping[str, Any] | None = None,
    brief: Path | str | None = None,
    dry_run: bool = False,
    check_binaries: bool = False,
    python_exec: str | None = None,
    verbose: bool = False,
    argv: tuple[str, ...] = (),
    orchestrator_args: tuple[str, ...] = (),
    registry: Any | None = None,
    client: Any | None = None,
    wait: bool = False,
    timeout_seconds: float = 3600.0,
    poll_seconds: float = 1.0,
) -> InvocationResult:
    _client = client
    sdk_module = _sdk_module()
    include_elements = kind == "element"
    registries = sdk_module._load_registries(
        project_root=project_root,
        extra_pack_roots=extra_pack_roots,
        banodoco_config=banodoco_config,
        include_missing_roots=include_missing_roots,
        include_elements=include_elements,
    )
    capability = sdk_module.get_capability(
        capability_id,
        kind=kind,
        project_root=project_root,
        extra_pack_roots=extra_pack_roots,
        banodoco_config=banodoco_config,
        include_missing_roots=include_missing_roots,
        _registries=registries,
    )
    if capability.capability_type == "element":
        raise UnsupportedCapabilityError(f"elements are not invokable via the SDK: {capability.id}")

    if isinstance(project, str) and not project.strip():
        project = None
    project_scope = _project_scope(capability)
    if not dry_run and project is None and project_scope == "required":
        project = _runtime_selected_project(_client)
        if project is None:
            from astrid.core.project.guidance import format_project_required_guidance

            raise CapabilityPreconditionError(
                format_project_required_guidance(
                    operation=f"{capability.capability_type} invocation"
                )
            )

    # Validate the public selector/format contract before the runner can
    # create a ledger row or spawn a subprocess.  The runner repeats these
    # checks for direct CLI callers, but SDK callers should get the same
    # actionable typed error at admission time.
    invocation_authority_context: dict[str, Any] | None = None
    invocation_admission_metadata: dict[str, Any] | None = None
    invocation_storage_estimate: dict[str, int] | None = None
    # These are managed-authority checks, not manifest checks.  A dry-run is
    # intentionally limited to the source ledger and therefore cannot inspect
    # a project tree or materialize a render snapshot.
    if not dry_run:
        if capability.id == "rendering.timeline_visualize":
            invocation_authority_context = _validate_timeline_visualize_inputs(
                inputs,
                project=project,
                project_root=project_root,
                out=out,
                _client=_client,
            )
            if invocation_authority_context.get("mode") == "filmstrip":
                # Only preflight may turn a successful project-owned render
                # into a file input. Public paths were rejected above.
                inputs = dict(inputs or {})
                inputs["project_slug"] = invocation_authority_context["filmstrip_snapshot"]["project_slug"]
                inputs["rendered_video"] = {
                    "digest": invocation_authority_context["video_digest"],
                    "object_id": invocation_authority_context["video_object_id"],
                }
                inputs["filmstrip_authority"] = json.dumps(
                    invocation_authority_context, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False,
                )
        elif capability.id == "rendering.render":
            inputs, invocation_authority_context = _prepare_managed_render_inputs(
                inputs,
                project=project,
                _client=_client,
            )
            snapshot = (inputs or {}).get("timeline_snapshot")
            snapshot_config = snapshot.get("config") if isinstance(snapshot, Mapping) else None
            snapshot_registry = snapshot.get("registry") if isinstance(snapshot, Mapping) else None
            if not isinstance(snapshot_config, Mapping) or not isinstance(snapshot_registry, Mapping):
                raise CapabilityInvocationError(
                    "managed render storage estimation requires the expanded canonical snapshot"
                )
            from astrid.core.rendering.storage import (
                StorageEstimateError,
                estimate_managed_render_storage,
                managed_object_sizes,
                used_effect_asset_sizes,
            )
            from astrid.sdk.pagination import paged_rows

            media_rows = paged_rows(_client.media.list, str(project), limit=50)
            if media_rows is None:
                raise CapabilityInvocationError(
                    "runtime media listing is unavailable for exact render storage estimation"
                )
            try:
                exact_object_sizes = managed_object_sizes(snapshot_registry, media_rows)
                effect_sizes = used_effect_asset_sizes(snapshot_config)
                storage_estimate = estimate_managed_render_storage(
                    timeline=snapshot_config,
                    registry=snapshot_registry,
                    object_sizes=exact_object_sizes,
                    effect_asset_sizes=effect_sizes,
                    requested_profile=(inputs or {}).get("profile"),
                )
            except StorageEstimateError as exc:
                raise CapabilityValidationError(str(exc)) from exc
            invocation_admission_metadata = {
                "storage_estimate": storage_estimate,
                "runtime_enforced": True,
            }
            invocation_storage_estimate = {
                "scratch_bytes": int(storage_estimate["estimated_scratch_bytes"]),
                "output_bytes": int(storage_estimate["estimated_output_bytes"]),
            }

    # Generation requests have a single read-only preflight for both dry-run
    # and live invocation.  This keeps generic ``sdk.invoke`` from accepting
    # an impossible model/mode/backend cell (or FLF request missing its end
    # frame) and discovering the problem only after kernel admission.
    generation_modalities = {
        "generation.generate_image": "image",
        "generation.generate_video": "video",
        "generation.generate_audio": "audio",
    }
    modality = generation_modalities.get(capability.id)
    if modality is not None:
        request_inputs = dict(inputs or {})
        model_registry = sdk_module._load_model_registry(
            project_root=project_root,
            extra_pack_roots=extra_pack_roots,
        )
        from astrid.core.generation.preflight import (
            require_local_generation_readiness,
            validate_generation_request,
        )

        if capability.id == "generation.generate_image":
            recipe = request_inputs.get("shot_generation_recipe")
            if recipe is not None:
                from astrid.packs.generation.executors.generate_image.task_adapter import (
                    GenerateImageAdapterError,
                    validate_shot_generation_recipe,
                )

                try:
                    validate_shot_generation_recipe(
                        recipe,
                        model=request_inputs.get("model"),
                        mode=request_inputs.get("mode"),
                        execution=request_inputs.get("execution"),
                        resolved_settings=request_inputs,
                    )
                except GenerateImageAdapterError as exc:
                    raise CapabilityValidationError(str(exc)) from exc

        model_entry, _mode_spec = validate_generation_request(
            model_registry,
            model=request_inputs.get("model"),
            mode=request_inputs.get("mode"),
            execution=request_inputs.get("execution"),
            inputs=request_inputs,
            modality=modality,
        )
        if request_inputs.get("execution") == "local":
            require_local_generation_readiness(
                model_entry,
                request_inputs["mode"],
                python_executable=python_exec,
            )

    # Ledger exemption: dry_run never admitted.  The preview is built from the
    # already resolved manifest DTO and does not import either runner or any
    # local project/run authority.
    if dry_run:
        try:
            raw_result, preview_ok = _manifest_dry_run_result(
                capability,
                inputs=inputs,
                outputs=outputs,
                brief=brief,
                python_exec=python_exec,
                out=out,
                orchestrator_args=tuple(orchestrator_args),
            )
        except AstridSDKError:
            raise
        except Exception as exc:
            mapped = _sdk_error_from_exception(exc)
            if mapped is not None:
                raise mapped from exc
            raise CapabilityInvocationError(
                f"failed to invoke {capability.capability_type} {capability.id!r}"
            ) from exc
        error = raw_result.get("error") if isinstance(raw_result.get("error"), Mapping) else None
        manifest_path = None
        run_id_raw = None
        run_root_raw = None
        executor_version_raw = raw_result.get("executor_version")
        return InvocationResult(
            capability_id=capability.id,
            capability_type=capability.capability_type,
            native_kind=capability.native_kind,
            ok=preview_ok,
            error=error,
            manifest_path=manifest_path,
            raw_result=raw_result,
            run_id=run_id_raw if isinstance(run_id_raw, str) and run_id_raw else None,
            run_root=str(Path(run_root_raw).expanduser().resolve())
            if isinstance(run_root_raw, str) and run_root_raw
            else None,
            outputs={},
            executor_version=executor_version_raw
            if isinstance(executor_version_raw, str) and executor_version_raw
            else None,
            kernel_run_id=None,
            kernel_task_id=None,
            kernel_attempt_id=None,
        )

    # Project requirements were resolved above. Public knowledge reads may
    # enter the same runtime admission path without a project association.
    kernel_capability_version: str | None = None
    if capability.capability_type == "executor":
        from astrid.core.foundation.hash import executor_definition_digest

        executor_registry, _, _ = registries
        kernel_capability_version = executor_definition_digest(executor_registry.get(capability.id))
        invocation_authority_context = dict(invocation_authority_context or {})
        invocation_authority_context["executor_version"] = kernel_capability_version
    try:
        # Keep the private seam backwards-compatible for callers that replace
        # it with a narrow test double, while still forwarding an explicitly
        # composed registry for long-lived clients.  ``None`` means the
        # kernel will build its normal standard composition; passing it as a
        # keyword adds no information and needlessly breaks older doubles.
        kernel_kwargs: dict[str, Any] = {
            "kind": kind,
            "project": project,
            "inputs": inputs,
            "outputs": outputs,
            "extra_pack_roots": extra_pack_roots,
            "idempotency_context": invocation_authority_context,
            "admission_metadata": invocation_admission_metadata,
            "storage_estimate": invocation_storage_estimate,
        }
        if registry is not None:
            kernel_kwargs["registry"] = registry
        kr, kt, ka, mpath, raw_result, ok, _ = _kernel_invoke(
            capability,
            **kernel_kwargs,
            _client=_client,
        )
        if wait and ok:
            raw_result, ok, waited_attempt_id = _wait_for_kernel_task(
                _client,
                task_id=kt,
                run_id=kr,
                timeout_seconds=timeout_seconds,
                poll_seconds=poll_seconds,
            )
            if waited_attempt_id:
                ka = waited_attempt_id
        run_id_raw = raw_result.get("run_id") if isinstance(raw_result, dict) else None
        run_root_raw = raw_result.get("run_root") if isinstance(raw_result, dict) else None
        raw_result = dict(raw_result) if isinstance(raw_result, dict) else {}
        if kernel_capability_version is not None:
            raw_result.setdefault("executor_version", kernel_capability_version)
        executor_version_raw = raw_result.get("executor_version")
        raw_result.setdefault("kernel_run_id", kr)
        raw_result.setdefault("kernel_task_id", kt)
        raw_result.setdefault("kernel_attempt_id", ka)
        manifest_path = (
            str(mpath) if mpath else _discover_invocation_manifest_path(raw_result, out=out)
        )
        if (wait and ok and capability.id == "rendering.timeline_visualize"
                and (invocation_authority_context or {}).get("mode") == "filmstrip"):
            manifest_path = _materialize_filmstrip_outputs(
                raw_result,
                _client,
                project=project,
            )
        return InvocationResult(
            capability_id=capability.id,
            capability_type=capability.capability_type,
            native_kind=capability.native_kind,
            ok=ok,
            # Preserve the kernel's typed handler failure on the primary
            # result surface.  Historically this was only available under
            # ``raw_result.error`` and task events, forcing callers to make a
            # second ledger query to understand a failed invocation.
            error=(
                {
                    **dict(raw_result.get("error")),
                    "sdk_error": "CapabilityRuntimeError",
                    "sdk_category": "runtime",
                }
                if isinstance(raw_result.get("error"), Mapping)
                else None
            ),
            manifest_path=manifest_path,
            raw_result=raw_result,
            run_id=run_id_raw if isinstance(run_id_raw, str) and run_id_raw else kr,
            # Kernel-managed invocations publish through private staging and
            # then remove it. Only propagate a run_root explicitly supplied
            # by a durable/custom kernel result; never synthesize the projects
            # root or leak the attempt staging path.
            run_root=(
                str(Path(run_root_raw).expanduser().resolve())
                if isinstance(run_root_raw, str) and run_root_raw
                else None
            ),
            outputs=_invocation_outputs(
                raw_result,
                manifest_path=manifest_path,
                capability_id=capability.id,
            ),
            executor_version=executor_version_raw
            if isinstance(executor_version_raw, str) and executor_version_raw
            else None,
            kernel_run_id=kr,
            kernel_task_id=kt,
            kernel_attempt_id=ka,
        )
    except AstridSDKError:
        raise
    except Exception as exc:
        mapped = _sdk_error_from_exception(exc)
        if mapped is not None:
            raise mapped from exc
        raise CapabilityInvocationError(
            f"failed to invoke {capability.capability_type} {capability.id!r}"
        ) from exc


def invoke_result(
    capability_id: str,
    *,
    kind: Any,
    **kwargs: Any,
) -> InvocationResult:
    """Invoke while keeping typed preflight failures in the result contract.

    ``invoke`` remains the exception-oriented API for callers that want typed
    recovery branches.  Maker-facing agents that need one uniform JSON-safe
    branch can use this sibling: validation/precondition failures raised before
    kernel admission become an ``InvocationResult(ok=False)`` with the same
    ``error`` mapping used by a post-admission failure.  No run, task, staging
    directory, network call, or provider request is created by this adapter.
    """

    try:
        return invoke(capability_id, kind=kind, **kwargs)
    except AstridSDKError as exc:
        category = getattr(exc, "category", "invocation")
        error = {
            "type": type(exc).__name__,
            "message": str(exc),
            "sdk_error": type(exc).__name__,
            "sdk_category": category,
        }
        details = getattr(exc, "details", None)
        if isinstance(details, Mapping) and details:
            error["validation"] = _json_safe(dict(details))
        return InvocationResult(
            capability_id=capability_id,
            capability_type=kind if kind in ("executor", "orchestrator") else "executor",
            native_kind="unknown",
            ok=False,
            error=error,
            raw_result={"ok": False, "error": error},
        )
