"""Plan and apply Astrid's one-workspace setup composition.

Workspace identity and lifecycle are delegated to the installed Runtime CLI.
Astrid composes its existing source and skill setup only after Runtime has
atomically created or attached the requested selected workspace.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from uuid import UUID

from astrid.core.pack.source_setup import declarations_from_json, provision
from astrid.runtime_cli import RuntimeCLI, RuntimeCLIError, validate_selected_workspace
from astrid.sdk.storage_root import ensure_no_unmigrated_runtime, resolve_runtime_data_root

SETUP_SCHEMA_VERSION = 1
DEFAULT_TARGET_PROFILE = "astrid-beta-current-mac"
_CONFIGURE_EFFECTS = ("configure-install", "write-relocate-change-data")
_START_EFFECTS = ("start-stop-local-service", "configure-install", "write-relocate-change-data")


@dataclass(frozen=True)
class SetupRequest:
    operation: str
    workspace_id: str
    support_root: Path
    realm_root: Path
    display_name: str = "Astrid Workspace"
    runtime_profile: str = "astrid"
    # ``None`` preserves omission from an input document.  The durable setup
    # selection owner resolves it against a same-identity prior selection (or
    # the first-run defaults); an explicit empty integrations array remains a
    # real request to clear the retained selection.
    target_profile: str | None = None
    integrations: tuple[str, ...] | None = None
    disabled_packs: tuple[str, ...] = ()
    source_manifest: Path | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SetupRequest":
        if value.get("schema_version", SETUP_SCHEMA_VERSION) != SETUP_SCHEMA_VERSION:
            raise ValueError(f"setup input schema_version must be {SETUP_SCHEMA_VERSION}")
        workspace = value.get("workspace", value)
        choices = value.get("choices", value)
        if not isinstance(workspace, Mapping) or not isinstance(choices, Mapping):
            raise ValueError("setup input workspace and choices must be objects")
        operation = str(value.get("operation") or workspace.get("operation") or "").strip().lower()
        if operation not in {"create", "attach"}:
            raise ValueError("setup input must explicitly choose operation create or attach")
        workspace_id = str(
            workspace.get("workspace_id")
            or workspace.get("realm_id")
            or value.get("workspace_id")
            or ""
        ).strip()
        try:
            workspace_id = str(UUID(workspace_id))
        except (ValueError, AttributeError) as exc:
            raise ValueError("setup input workspace_id must be an explicit UUID") from exc
        support_root = _absolute_path(
            workspace.get("support_root") or workspace.get("data_root") or value.get("support_root"),
            label="support_root",
        )
        realm_root = _absolute_path(
            workspace.get("realm_root") or value.get("realm_root"),
            label="realm_root",
        )
        runtime_profile = str(choices.get("runtime_profile", "astrid")).strip()
        if runtime_profile != "astrid":
            raise ValueError("runtime_profile must be 'astrid'")
        target_profile = (
            str(choices["target_profile"]).strip()
            if "target_profile" in choices
            else None
        )
        if target_profile is not None and not target_profile:
            raise ValueError("target_profile must be non-blank")
        integrations = (
            _string_tuple(choices["integrations"], "integrations")
            if "integrations" in choices
            else None
        )
        source_manifest_raw = value.get("source_manifest") or workspace.get("source_manifest")
        source_manifest = (
            _absolute_path(source_manifest_raw, label="source_manifest")
            if source_manifest_raw
            else None
        )
        return cls(
            operation=operation,
            workspace_id=workspace_id,
            support_root=support_root,
            realm_root=realm_root,
            display_name=str(workspace.get("display_name", "Astrid Workspace")).strip() or "Astrid Workspace",
            runtime_profile=runtime_profile,
            target_profile=target_profile,
            integrations=integrations,
            disabled_packs=_string_tuple(choices.get("disabled_packs", ()), "disabled_packs"),
            source_manifest=source_manifest,
        )

    def to_document(self) -> dict[str, Any]:
        return {
            "schema_version": SETUP_SCHEMA_VERSION,
            "operation": self.operation,
            "workspace": {
                "workspace_id": self.workspace_id,
                "support_root": str(self.support_root),
                "realm_root": str(self.realm_root),
                "display_name": self.display_name,
                **({"source_manifest": str(self.source_manifest)} if self.source_manifest else {}),
            },
            "choices": {
                "runtime_profile": self.runtime_profile,
                **({"target_profile": self.target_profile} if self.target_profile is not None else {}),
                **({"integrations": list(self.integrations)} if self.integrations is not None else {}),
                "disabled_packs": list(self.disabled_packs),
            },
        }


@dataclass(frozen=True)
class SetupStage:
    name: str
    status: str
    effects: tuple[str, ...]
    detail: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "effects": list(self.effects),
            "detail": dict(self.detail),
        }


def _absolute_path(value: Any, *, label: str) -> Path:
    if not isinstance(value, (str, os.PathLike)) or not str(value).strip():
        raise ValueError(f"setup input {label} is required")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError(f"setup input {label} must be an absolute path; cwd fallback is forbidden")
    path = Path(os.path.abspath(path))
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"setup input {label} contains a symlink component: {path}")
    return path


def _string_tuple(value: Any, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"setup input {label} must be an array of non-blank strings")
    return tuple(dict.fromkeys(item.strip() for item in value))


def _problem_code(data: Mapping[str, Any], default: str) -> str:
    return str(data.get("problem_code") or data.get("code") or data.get("state") or default)


def _stage(name: str, status: str, effects: tuple[str, ...] = (), **detail: Any) -> SetupStage:
    return SetupStage(name, status, effects, detail)


def _compose(
    *,
    apply: bool,
    offline: bool,
    declarations: Path | None,
    deep: bool,
    disable_pack: str | None,
    restore_pack: str | None,
    disabled_packs: tuple[str, ...],
    workspace_id: str,
    support_root: Path,
    realm_root: Path,
    runtime_profile: str,
    target_profile: str | None,
    integrations: tuple[str, ...] | None,
) -> Mapping[str, Any]:
    declared = declarations_from_json(declarations)
    declared_ids = {item.pack_id for item in declared}
    requested_disables = tuple(dict.fromkeys((*disabled_packs, *((disable_pack,) if disable_pack else ()))))
    for pack_id in requested_disables:
        if pack_id in declared_ids:
            provision(declared, offline=offline, check=not apply, disable_pack=pack_id)
    restore_succeeded = False
    if restore_pack:
        restore_report = provision(
            declared, offline=offline, check=not apply, restore_pack=restore_pack
        )
        restore_succeeded = bool(restore_report.get("ok", False))
    source = provision(declared, offline=offline, check=not apply)
    from astrid.skills import list_skills, sync
    from astrid.skills import state as skill_state

    skill_choices = skill_state.load()
    changed_skill_choices = False
    for harness in skill_state.HARNESSES:
        disabled = skill_choices["disabled_defaults"].setdefault(harness, [])
        for pack_id in requested_disables:
            if pack_id not in disabled:
                disabled.append(pack_id)
                changed_skill_choices = True
        if restore_succeeded and restore_pack in disabled:
            skill_choices["disabled_defaults"][harness] = [
                pack_id for pack_id in disabled if pack_id != restore_pack
            ]
            changed_skill_choices = True
    setup_selection_changed = skill_state.record_setup_selection(
        skill_choices,
        workspace_id=workspace_id,
        support_root=str(support_root),
        realm_root=str(realm_root),
        runtime_profile=runtime_profile,
        target_profile=target_profile,
        integrations=list(integrations) if integrations is not None else None,
        default_target_profile=DEFAULT_TARGET_PROFILE,
    )
    effective_selection = skill_choices["setup_selection"]
    effective_integrations = tuple(effective_selection["integrations"])
    available_integrations = {descriptor.pack_id for descriptor in list_skills()}
    missing_integrations = sorted(set(effective_integrations) - available_integrations)
    if missing_integrations:
        raise ValueError(
            "setup integrations are not available in the admitted source inventory: "
            + ", ".join(missing_integrations)
        )
    if apply and (changed_skill_choices or setup_selection_changed):
        skill_state.save(skill_choices)

    skills = sync(
        deep=deep,
        dry_run=not apply,
        selected_pack_ids=effective_integrations,
        proposed_state=skill_choices if not apply else None,
    )
    return {
        "ok": bool(source.get("ok", False)),
        "source": source,
        "skills": skills,
        "disabled_packs": list(requested_disables),
        "disabled_choices_changed": changed_skill_choices,
        "setup_selection": dict(skill_choices["setup_selection"]),
        "setup_selection_changed": setup_selection_changed,
    }


def _composition_kwargs(
    request: SetupRequest,
    *,
    apply: bool,
    offline: bool,
    declarations: Path | None,
    deep: bool,
    disable_pack: str | None,
    restore_pack: str | None,
) -> dict[str, Any]:
    return {
        "apply": apply,
        "offline": offline,
        "declarations": declarations,
        "deep": deep,
        "disable_pack": disable_pack,
        "restore_pack": restore_pack,
        "disabled_packs": request.disabled_packs,
        "workspace_id": request.workspace_id,
        "support_root": request.support_root,
        "realm_root": request.realm_root,
        "runtime_profile": request.runtime_profile,
        "target_profile": request.target_profile,
        "integrations": request.integrations,
    }


def _runtime_up_command(request: SetupRequest) -> str:
    """Return the copyable retry bound to the already-selected support root."""

    return shlex.join(
        (
            "astrid-runtime", "up", "--profile", request.runtime_profile,
            "--data-root", str(request.support_root), "--json",
        )
    )


def execute_setup(
    request: SetupRequest,
    *,
    apply: bool = False,
    check: bool = False,
    offline: bool = False,
    declarations: Path | None = None,
    deep: bool = False,
    disable_pack: str | None = None,
    restore_pack: str | None = None,
    runtime: RuntimeCLI | None = None,
    compose: Callable[..., Mapping[str, Any]] = _compose,
) -> tuple[int, dict[str, Any]]:
    """Run preview/check/apply through one plan core and typed stages."""

    runtime = runtime or RuntimeCLI()
    stages: list[SetupStage] = []
    mode = "apply" if apply else "check" if check else "preview"
    base: dict[str, Any] = {
        "schema_version": SETUP_SCHEMA_VERSION,
        "mode": mode,
        "input": request.to_document(),
        "workspace": {
            "workspace_id": request.workspace_id,
            "support_root": str(request.support_root),
            "realm_root": str(request.realm_root),
            "selection": request.operation,
        },
        "choices": request.to_document()["choices"],
        "offline": offline,
        "authorization_required": apply,
    }
    try:
        ensure_no_unmigrated_runtime(request.support_root)
        inspected = runtime.inspect(
            support_root=request.support_root,
            realm_root=request.realm_root,
            expected_realm_id=request.workspace_id,
        )
    except (RuntimeCLIError, ValueError) as exc:
        result = {
            **base,
            "ok": False,
            "problem_code": getattr(exc, "code", "runtime_unavailable"),
            "error": str(exc),
            "stages": [_stage("inspect", "failed", ("observe",), error=str(exc)).to_dict()],
        }
        return 1, result

    inspect_code = _problem_code(inspected.data, "workspace_missing")
    fresh_create = request.operation == "create" and inspect_code == "workspace_missing"
    if inspected.ok:
        try:
            validate_selected_workspace(
                inspected.data,
                expected_realm_id=request.workspace_id,
                expected_realm_root=request.realm_root,
                expected_support_root=request.support_root,
            )
        except RuntimeCLIError as exc:
            return 1, {
                **base,
                "ok": False,
                "problem_code": exc.code,
                "error": str(exc),
                "stages": [_stage("inspect", "failed", ("observe",), observed=dict(inspected.data), error=str(exc)).to_dict()],
            }
        stages.append(_stage("inspect", "complete", ("observe",), observed=dict(inspected.data)))
    elif fresh_create:
        stages.append(_stage("inspect", "complete", ("observe",), observed=dict(inspected.data), candidate="fresh"))
    else:
        problem = inspect_code if inspect_code in {
            "workspace_missing", "workspace_ambiguous", "workspace_identity_mismatch"
        } else "workspace_identity_mismatch"
        return 1, {
            **base,
            "ok": False,
            "problem_code": problem,
            "error": inspected.data.get("error", "workspace inspection failed closed"),
            "stages": [_stage("inspect", "failed", ("observe",), observed=dict(inspected.data)).to_dict()],
        }

    try:
        composition = compose(**_composition_kwargs(
            request,
            apply=False,
            offline=offline,
            declarations=declarations,
            deep=deep,
            disable_pack=disable_pack,
            restore_pack=restore_pack,
        ))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        composition = {"ok": False, "error": str(exc)}

    if not apply:
        proposed = "unchanged" if inspected.ok else "proposed"
        stages.extend(
            [
                _stage("Create-or-Attach", proposed, _CONFIGURE_EFFECTS, operation=request.operation),
                _stage("select-default", proposed, _CONFIGURE_EFFECTS, workspace_id=request.workspace_id),
                _stage("compose", "unchanged" if composition.get("ok") else "proposed", _CONFIGURE_EFFECTS, report=composition),
                _stage("Setup applied", "not_run"),
                _stage("Starting Astrid Runtime", "not_run", _START_EFFECTS),
                _stage("Runtime ready", "not_run", ("observe",)),
            ]
        )
        ready = inspected.ok and bool(composition.get("ok"))
        return (0 if not check or ready else 1), {
            **base,
            "ok": True if not check else ready,
            "ready": ready,
            "problem_code": None if ready else ("workspace_missing" if fresh_create else "capability_unavailable"),
            "proposed_effects": list(dict.fromkeys((*_CONFIGURE_EFFECTS, *_START_EFFECTS))),
            "composition": composition,
            "stages": [item.to_dict() for item in stages],
        }

    try:
        configured = runtime.configure(
            request.operation,
            support_root=request.support_root,
            realm_root=request.realm_root,
            realm_id=request.workspace_id,
            display_name=request.display_name,
            source_manifest=request.source_manifest,
        )
    except RuntimeCLIError as exc:
        return 1, {
            **base,
            "ok": False,
            "problem_code": exc.code,
            "error": str(exc),
            "stages": [*map(SetupStage.to_dict, stages), _stage("Create-or-Attach", "failed", _CONFIGURE_EFFECTS, observed=exc.result).to_dict()],
        }
    if not configured.ok:
        return 1, {
            **base,
            "ok": False,
            "problem_code": _problem_code(configured.data, "workspace_identity_mismatch"),
            "error": configured.data.get("error", "Runtime workspace configuration failed"),
            "stages": [*map(SetupStage.to_dict, stages), _stage("Create-or-Attach", "failed", _CONFIGURE_EFFECTS, observed=dict(configured.data)).to_dict()],
        }
    try:
        validate_selected_workspace(
            configured.data,
            expected_realm_id=request.workspace_id,
            expected_realm_root=request.realm_root,
            expected_support_root=request.support_root,
        )
    except RuntimeCLIError as exc:
        return 1, {
            **base,
            "ok": False,
            "problem_code": exc.code,
            "error": str(exc),
            "stages": [*map(SetupStage.to_dict, stages), _stage("Create-or-Attach", "failed", _CONFIGURE_EFFECTS, observed=dict(configured.data)).to_dict()],
        }
    unchanged = str(configured.data.get("status", "")).endswith("unchanged")
    stages.extend(
        [
            _stage("Create-or-Attach", "unchanged" if unchanged else "complete", _CONFIGURE_EFFECTS, observed=dict(configured.data)),
            _stage("select-default", "unchanged" if unchanged else "complete", _CONFIGURE_EFFECTS, workspace_id=request.workspace_id, realm_root=str(request.realm_root)),
        ]
    )
    try:
        composition = compose(**_composition_kwargs(
            request,
            apply=True,
            offline=offline,
            declarations=declarations,
            deep=deep,
            disable_pack=disable_pack,
            restore_pack=restore_pack,
        ))
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        stages.append(_stage("compose", "failed", _CONFIGURE_EFFECTS, error=str(exc)))
        return 1, {
            **base,
            "ok": False,
            "workspace_configured": True,
            "problem_code": "capability_unavailable",
            "error": str(exc),
            "stages": [item.to_dict() for item in stages],
        }
    if not composition.get("ok"):
        stages.append(_stage("compose", "failed", _CONFIGURE_EFFECTS, report=composition))
        return 1, {
            **base,
            "ok": False,
            "workspace_configured": True,
            "problem_code": "capability_unavailable",
            "composition": composition,
            "stages": [item.to_dict() for item in stages],
        }
    stages.extend(
        [
            _stage("compose", "complete", _CONFIGURE_EFFECTS, report=composition),
            _stage("Setup applied", "complete", (), workspace_id=request.workspace_id, realm_root=str(request.realm_root)),
            _stage("Starting Astrid Runtime", "running", _START_EFFECTS),
        ]
    )
    try:
        started = runtime.up(
            support_root=request.support_root,
            expected_realm_id=request.workspace_id,
            realm_root=request.realm_root,
        )
    except RuntimeCLIError as exc:
        started = None
        startup_error = str(exc)
        startup_data: Mapping[str, Any] = exc.result
    else:
        startup_error = str(started.data.get("error", "Runtime failed to start")) if not started.ok else ""
        startup_data = started.data
    if started is None or not started.ok:
        stages[-1] = _stage("Starting Astrid Runtime", "failed", _START_EFFECTS, observed=dict(startup_data), error=startup_error)
        stages.append(_stage("Runtime ready", "not_run", ("observe",)))
        return 1, {
            **base,
            "ok": False,
            "workspace_configured": True,
            "runtime_ready": False,
            "problem_code": "workspace_configured_runtime_not_ready",
            "error": startup_error,
            "next_action": {
                "command": _runtime_up_command(request),
                "effects": list(_START_EFFECTS),
                "authorization_required": True,
            },
            "composition": composition,
            "stages": [item.to_dict() for item in stages],
        }
    stages[-1] = _stage("Starting Astrid Runtime", "complete", _START_EFFECTS, observed=dict(started.data))
    stages.append(_stage("Runtime ready", "complete", ("observe",), observed=dict(started.data)))
    return 0, {
        **base,
        "ok": True,
        "workspace_configured": True,
        "runtime_ready": True,
        "composition": composition,
        "stages": [item.to_dict() for item in stages],
    }


def _read_input(path: str) -> Mapping[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8")
    value = json.loads(text)
    if not isinstance(value, Mapping):
        raise ValueError("setup input document must be a JSON object")
    return value


def _request_from_args(args: argparse.Namespace) -> SetupRequest:
    if args.input:
        return SetupRequest.from_mapping(_read_input(args.input))
    operation = "create" if args.create else "attach" if args.attach else ""
    if not operation and sys.stdin.isatty():
        return _guided_request(args)
    if not operation:
        raise ValueError("choose --create or --attach, or pass --input FILE")
    return SetupRequest.from_mapping(
        {
            "schema_version": SETUP_SCHEMA_VERSION,
            "operation": operation,
            "workspace": {
                "workspace_id": args.workspace_id,
                "support_root": str(args.data_root or resolve_runtime_data_root()),
                "realm_root": args.realm_root,
                "display_name": args.display_name,
                **({"source_manifest": str(args.source_manifest)} if args.source_manifest else {}),
            },
            "choices": {
                "runtime_profile": "astrid",
                **(
                    {"target_profile": args.target_profile}
                    if args.target_profile is not None
                    else {}
                ),
                **(
                    {"integrations": args.integration}
                    if args.integration is not None
                    else {}
                ),
                "disabled_packs": args.disabled_choice,
            },
        }
    )


def _guided_request(args: argparse.Namespace) -> SetupRequest:
    """Collect human answers, then normalize through the shared input schema."""

    default_support = args.data_root or resolve_runtime_data_root()
    operation = input("Create or attach workspace? [create/attach]: ").strip().lower()
    workspace_id = input("Workspace UUID: ").strip()
    support = input(f"Runtime support root [{default_support}]: ").strip() or str(default_support)
    realm = input("Absolute workspace realm root: ").strip()
    display_name = input(f"Display name [{args.display_name}]: ").strip() or args.display_name
    default_target = args.target_profile or DEFAULT_TARGET_PROFILE
    target_profile = input(f"Target profile [{default_target}]: ").strip() or default_target
    integrations = [item.strip() for item in input("Enabled integrations (comma separated, optional): ").split(",") if item.strip()]
    disabled = [item.strip() for item in input("Disabled packs (comma separated, optional): ").split(",") if item.strip()]
    return SetupRequest.from_mapping(
        {
            "schema_version": SETUP_SCHEMA_VERSION,
            "operation": operation,
            "workspace": {
                "workspace_id": workspace_id,
                "support_root": support,
                "realm_root": realm,
                "display_name": display_name,
            },
            "choices": {
                "runtime_profile": "astrid",
                "target_profile": target_profile,
                "integrations": integrations,
                "disabled_packs": disabled,
            },
        }
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="astrid setup")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="apply the reviewed local plan and start Runtime")
    mode.add_argument("--check", action="store_true", help="strictly read-only readiness check")
    parser.add_argument("--offline", action="store_true", help="forbid acquisition; authorized local apply remains allowed")
    parser.add_argument("--input", help="deterministic JSON setup document, or - for stdin")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--create", action="store_true")
    choice.add_argument("--attach", action="store_true")
    parser.add_argument("--workspace-id")
    parser.add_argument("--data-root", type=Path, help="absolute Runtime support root")
    parser.add_argument("--realm-root", type=Path)
    parser.add_argument("--display-name", default="Astrid Workspace")
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--target-profile")
    parser.add_argument("--integration", action="append")
    parser.add_argument("--disabled-choice", action="append", default=[])
    parser.add_argument("--disable-pack")
    parser.add_argument("--restore-pack")
    parser.add_argument("--declarations", type=Path)
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        request = _request_from_args(args)
        code, result = execute_setup(
            request,
            apply=args.apply,
            check=args.check,
            offline=args.offline,
            declarations=args.declarations,
            deep=args.deep,
            disable_pack=args.disable_pack,
            restore_pack=args.restore_pack,
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        code = 2
        result = {"ok": False, "problem_code": "invalid_setup_input", "error": str(exc)}
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return code


__all__ = [
    "DEFAULT_TARGET_PROFILE",
    "SETUP_SCHEMA_VERSION",
    "SetupRequest",
    "SetupStage",
    "execute_setup",
    "main",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
