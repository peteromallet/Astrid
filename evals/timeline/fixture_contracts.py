"""Typed, deterministic contracts for materialized timeline-eval fixtures.

This module describes what a coordinator must materialize before a worker may
run.  It intentionally does not build media, seed Runtime, or infer targets:
missing inputs remain blocked until a real receipt and readback projection are
provided.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .a02_projection import A02_PROJECTION


CONTRACT_KIND = "astrid.timeline-eval.fixture-contract.v1"
EXACT_NAVIGATION_PROJECTION = "exact_closure_navigation.v1"


@dataclass(frozen=True)
class FixtureInput:
    path: str
    scope: str
    reason: str
    kind: str = "missing_fixture_input"

    def as_dict(self) -> dict[str, str]:
        return {
            "path": self.path, "scope": self.scope, "reason": self.reason,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class NavigationFixtureContract:
    case_id: str
    target_aliases: tuple[str, ...]
    projection: str = EXACT_NAVIGATION_PROJECTION
    required_inputs: tuple[FixtureInput, ...] = ()

    @property
    def status(self) -> str:
        if not self.required_inputs:
            return "ready"
        if all(item.kind == "environmental_capability" for item in self.required_inputs):
            return "environment_unavailable"
        return "blocked"

    @property
    def diagnostic_code(self) -> str:
        return (
            "ready" if self.status == "ready" else
            "surface_capability_unavailable" if self.status == "environment_unavailable" else
            "missing_pinned_fixture_input"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": CONTRACT_KIND,
            "case_id": self.case_id,
            "workflow": "offline_read_only_navigation",
            "status": self.status,
            "diagnostic_code": self.diagnostic_code,
            "target_aliases": list(self.target_aliases),
            "readback_projection": self.projection,
            "required_inputs": [item.as_dict() for item in self.required_inputs],
        }


@dataclass(frozen=True)
class ActionTargetContract:
    case_id: str
    edit_route: str | None
    readback_projection: str | None
    required_inputs: tuple[FixtureInput, ...]
    reason: str | None = None

    @property
    def status(self) -> str:
        return "ready" if self.edit_route and self.readback_projection else "blocked"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": CONTRACT_KIND,
            "case_id": self.case_id,
            "workflow": "disposable_action",
            "status": self.status,
            "edit_route": self.edit_route,
            "readback_projection": self.readback_projection,
            "required_inputs": [item.as_dict() for item in self.required_inputs],
            "reason": self.reason,
        }


def navigation_fixture_contract(case: Mapping[str, Any]) -> NavigationFixtureContract:
    """Describe a navigation case without claiming its optional surfaces exist."""
    case_id = str(case.get("id", ""))
    aliases = tuple(str(value) for value in case.get("targets", ()) if isinstance(value, str))
    requirements: list[FixtureInput] = []
    for requirement in case.get("fixture_requirements", ()):
        if not isinstance(requirement, Mapping):
            continue
        requirements.append(FixtureInput(
            path=str(requirement.get("path", "")),
            scope=str(requirement.get("scope", "manifest")),
            reason=str(requirement.get("reason", "required navigation input is unavailable")),
            kind=(
                "environmental_capability"
                if str(requirement.get("path", "")).startswith("surface_adapters.")
                or str(requirement.get("reason", "")).endswith("on this host")
                else "missing_fixture_input"
            ),
        ))
    return NavigationFixtureContract(case_id=case_id, target_aliases=aliases,
                                     required_inputs=tuple(requirements))


def action_target_contract(case: Mapping[str, Any]) -> ActionTargetContract:
    """Describe the currently implemented action route, never infer one."""
    case_id = str(case.get("id", ""))
    if case_id == "A01":
        return ActionTargetContract(
            case_id=case_id,
            edit_route="timelines replace-parent-media",
            readback_projection="active_media_replacement.v1",
            required_inputs=(FixtureInput(
                path="target.json", scope="coordinator",
                reason="prepared disposable A01 target receipt",
            ),),
        )
    if case_id == "A02":
        return ActionTargetContract(
            case_id=case_id,
            edit_route=None,
            readback_projection=A02_PROJECTION,
            required_inputs=(FixtureInput(
                path="target.json", scope="coordinator",
                reason="four-shot derivative target and disposable remove-occurrence route",
            ),),
            reason=(
                "A02 has a typed remove-occurrence projection, but no materialized "
                "disposable target (four-shot derivative) or edit route"
            ),
        )
    return ActionTargetContract(
        case_id=case_id,
        edit_route=None,
        readback_projection=None,
        required_inputs=(FixtureInput(
            path="target.json", scope="coordinator",
            reason="case-specific disposable target, owned media, edit route, and readback projection",
        ),),
        reason=(
            f"{case_id} has no materialized disposable target/readback contract; "
            "do not launch a worker or infer an edit route from generic authoring helpers"
        ),
    )


def validate_navigation_entrypoint(
    entrypoint: Mapping[str, Any], contract: NavigationFixtureContract,
) -> list[str]:
    """Validate a selected-case offline entrypoint against its typed contract."""
    errors: list[str] = []
    if entrypoint.get("kind") != "astrid.timeline-eval.offline-navigation-entry.v1":
        errors.append("entrypoint kind is not the versioned offline navigation contract")
    if entrypoint.get("case_id") != contract.case_id:
        errors.append("entrypoint case_id does not match the selected contract")
    if entrypoint.get("read_only") is not True:
        errors.append("navigation entrypoint must assert read_only=true")
    receipt = entrypoint.get("target_receipt")
    if not isinstance(receipt, Mapping):
        errors.append("navigation entrypoint has no target_receipt")
    else:
        if receipt.get("readback_projection") != contract.projection:
            errors.append("navigation target receipt has the wrong readback projection")
        actual = tuple(str(value) for value in receipt.get("target_aliases", ())
                       if isinstance(value, str))
        if actual != contract.target_aliases:
            errors.append("navigation target aliases do not match the selected fixture")
    targets = entrypoint.get("targets")
    if not isinstance(targets, Mapping):
        errors.append("navigation entrypoint has no selected targets object")
    else:
        missing = [alias for alias in contract.target_aliases if alias not in targets]
        if missing:
            errors.append("selected target aliases are missing: " + ", ".join(missing))
    return errors


def validate_action_target_receipt(
    target: Mapping[str, Any], contract: ActionTargetContract,
) -> list[str]:
    """Validate a coordinator target receipt; blocked contracts reject all receipts."""
    if contract.status != "ready":
        return [contract.reason or f"{contract.case_id} action contract is blocked"]
    errors: list[str] = []
    if target.get("kind") != "astrid.timeline-eval.public-target.v1":
        errors.append("target receipt kind is not the versioned public-target contract")
    if target.get("case_id") != contract.case_id:
        errors.append("target receipt case_id does not match the action contract")
    if target.get("read_only") is True:
        errors.append("action target receipt must not be read-only")
    capabilities = target.get("capabilities")
    edit = capabilities.get("edit") if isinstance(capabilities, Mapping) else None
    if not isinstance(edit, Mapping) or edit.get("status") != "available":
        errors.append("action target does not declare an available edit capability")
    elif edit.get("route") != contract.edit_route:
        errors.append("action target edit route disagrees with the typed contract")
    locator = target.get("target_locator")
    if not isinstance(locator, Mapping):
        errors.append("action target has no target_locator")
    elif locator.get("readback_projection") != contract.readback_projection:
        errors.append("action target locator has the wrong readback projection")
    for key in ("endpoint", "project_id", "timeline_id", "head_revision_id"):
        if not isinstance(target.get(key), str) or not target[key]:
            errors.append(f"action target is missing {key}")
    return errors


__all__ = [
    "ActionTargetContract", "CONTRACT_KIND", "EXACT_NAVIGATION_PROJECTION",
    "FixtureInput", "NavigationFixtureContract", "action_target_contract",
    "navigation_fixture_contract", "validate_action_target_receipt",
    "validate_navigation_entrypoint",
]
