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
GENERIC_AUTHORING_ROUTE = "authoring-bundle validate/commit"

NAVIGATION_COORDINATOR_EVIDENCE = (
    "entrypoint.json with source head and closure digest",
    "coordinator before.json from the pinned immutable fixture",
    "coordinator after.json or proof that the offline fixture remained unchanged",
    "independent source-unchanged and read-only-target safety evidence",
)
L10_PLAYBACK_COMPLETION_EVIDENCE = (
    "evidence/navigation-path.json bound to the selected voice media digest",
    "ordered trace references for player start, successful playback completion, and parent return",
    "parent return receipt bound to the same source head and closure digest",
)
A01_COORDINATOR_EVIDENCE = (
    "target.json with disposable project/timeline/head and resolved occurrence/shot/clip identities",
    "coordinator before.json read at the exact pinned target head",
    "candidate validation and decoded preview for the requested render window",
    "publication receipt with old/new parent heads and complete dependency manifest",
    "coordinator after.json read from the receipt's committed parent closure",
    "independent source-unchanged and test-target-only safety evidence after worker teardown",
)


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
        coordinator_evidence = list(NAVIGATION_COORDINATOR_EVIDENCE)
        if self.case_id == "L10":
            coordinator_evidence.extend(L10_PLAYBACK_COMPLETION_EVIDENCE)
        return {
            "kind": CONTRACT_KIND,
            "case_id": self.case_id,
            "workflow": "offline_read_only_navigation",
            "readiness_scope": "declared fixture inputs only; materialized entrypoint and coordinator evidence are checked separately",
            "status": self.status,
            "diagnostic_code": self.diagnostic_code,
            "target_aliases": list(self.target_aliases),
            "readback_projection": self.projection,
            "coordinator_evidence_required": coordinator_evidence,
            "required_inputs": [item.as_dict() for item in self.required_inputs],
        }


@dataclass(frozen=True)
class ActionTargetContract:
    case_id: str
    edit_route: str | None
    readback_projection: str | None
    required_inputs: tuple[FixtureInput, ...]
    reason: str | None = None
    required_coordinator_evidence: tuple[str, ...] = ()
    readback_reason: str | None = None

    @property
    def status(self) -> str:
        """Return edit-route readiness, independent of semantic readback readiness."""
        return "ready" if self.edit_route and not self.reason else "blocked"

    @property
    def edit_status(self) -> str:
        return "available" if self.status == "ready" else "unavailable"

    @property
    def readback_status(self) -> str:
        return "available" if self.readback_projection else "unavailable"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": CONTRACT_KIND,
            "case_id": self.case_id,
            "workflow": "disposable_action",
            "readiness_scope": "supported route/projection only; a fresh target receipt and coordinator evidence are required separately",
            "status": self.status,
            "edit_status": self.edit_status,
            "readback_status": self.readback_status,
            "edit_route": self.edit_route,
            "readback_projection": self.readback_projection,
            "required_inputs": [item.as_dict() for item in self.required_inputs],
            "required_coordinator_evidence": list(self.required_coordinator_evidence),
            "reason": self.reason,
            "readback_reason": self.readback_reason,
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


def validate_l10_playback_evidence(value: Mapping[str, Any]) -> list[str]:
    """Validate actual L10 playback and return observations, never infer them.

    The trace event ordinals must be captured from the worker's real navigation
    trace. This contract does not execute a player or manufacture completion.
    """
    errors: list[str] = []
    if value.get("kind") != "astrid.timeline-eval.l10-playback-evidence.v1":
        errors.append("L10 playback evidence has an unsupported kind")
    if value.get("case_id") != "L10":
        errors.append("L10 playback evidence is not bound to case L10")
    media_id = value.get("voice_media_id")
    if not isinstance(media_id, str) or not media_id.startswith("sha256:"):
        errors.append("L10 playback evidence is missing the selected voice media digest")
    player = value.get("player")
    if not isinstance(player, Mapping) or not player.get("resolved_executable"):
        errors.append("L10 playback evidence is missing the resolved player executable")
    elif player.get("exit_status") != 0:
        errors.append("L10 player process did not report successful completion")
    playback = value.get("playback")
    if not isinstance(playback, Mapping) or playback.get("completed") is not True:
        errors.append("L10 playback completion is not evidenced")
    trace = value.get("trace_ordinals")
    event_names = ("player_started", "playback_completed", "parent_returned")
    ordinals: list[int] = []
    if not isinstance(trace, Mapping):
        errors.append("L10 playback evidence is missing ordered trace event references")
    else:
        for name in event_names:
            ordinal = trace.get(name)
            if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0:
                errors.append(f"L10 trace is missing a valid {name} event ordinal")
            else:
                ordinals.append(ordinal)
        if len(ordinals) == len(event_names) and not ordinals[0] < ordinals[1] < ordinals[2]:
            errors.append("L10 trace must order player start, playback completion, then parent return")
    parent = value.get("parent_return")
    if not isinstance(parent, Mapping) or parent.get("returned") is not True:
        errors.append("L10 return to the parent composition is not evidenced")
    else:
        if not parent.get("alias"):
            errors.append("L10 parent return is missing its parent alias")
        if not parent.get("source_head") or not parent.get("closure_digest"):
            errors.append("L10 parent return is missing pinned source head or closure digest")
    return errors


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
            required_coordinator_evidence=A01_COORDINATOR_EVIDENCE,
        )
    if case_id == "A02":
        return ActionTargetContract(
            case_id=case_id,
            edit_route=GENERIC_AUTHORING_ROUTE,
            readback_projection=A02_PROJECTION,
            required_inputs=(FixtureInput(
                path="target.json", scope="coordinator",
                reason="disposable target for the generic detached authoring route",
            ),),
            readback_reason=(
                "A02's independent remove-occurrence projection is checked separately "
                "from generic candidate editing"
            ),
        )
    if case_id == "A03":
        return ActionTargetContract(
            case_id=case_id,
            edit_route="Astrid SDK move_occurrence_group() + publish_authoring_candidate",
            readback_projection="move_occurrence_group.v1",
            required_inputs=(FixtureInput(
                path="target.json", scope="coordinator",
                reason="four-occurrence disposable target with pinned parent head and destination-owned closure",
            ),),
            required_coordinator_evidence=(
                "target.json with disposable project/timeline/head and closing/middle occurrence IDs",
                "coordinator before.json read at the exact pinned target head",
                "one public SDK group move followed by detached-candidate validation and publication",
                "publication receipt with old/new parent heads and complete dependency manifest",
                "coordinator after.json read from the receipt's committed parent closure",
                "independent move_occurrence_group.v1 verification of order, timings, and picture/voice/caption child bindings",
                "independent source-unchanged and test-target-only safety evidence after worker teardown",
            ),
        )
    if case_id in {f"A{index:02d}" for index in range(4, 11)}:
        return ActionTargetContract(
            case_id=case_id,
            edit_route=GENERIC_AUTHORING_ROUTE,
            readback_projection=None,
            required_inputs=(FixtureInput(
                path="target.json", scope="coordinator",
                reason="disposable target for the generic detached authoring route",
            ),),
            readback_reason=(
                f"{case_id} has no materialized independent readback projection; "
                "semantic judging remains an external coordinator responsibility"
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
        source = entrypoint.get("source")
        if not isinstance(source, Mapping):
            errors.append("navigation entrypoint has no pinned source identity")
        else:
            for field in ("timeline_id", "head_revision_id", "closure_digest"):
                if not isinstance(source.get(field), str) or not source[field]:
                    errors.append(f"navigation entrypoint source is missing {field}")
            if source.get("head_revision_id") != receipt.get("source_head"):
                errors.append("navigation receipt source head differs from pinned source identity")
            if source.get("closure_digest") != receipt.get("source_closure_digest"):
                errors.append("navigation receipt closure digest differs from pinned source identity")
        if not isinstance(receipt.get("media_ids"), list):
            errors.append("navigation receipt has no pinned media identity list")
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
    if isinstance(locator, Mapping) and contract.readback_projection and locator.get("readback_projection") != contract.readback_projection:
        errors.append("action target locator has the wrong readback projection")
    for key in ("endpoint", "project_id", "timeline_id", "head_revision_id"):
        if not isinstance(target.get(key), str) or not target[key]:
            errors.append(f"action target is missing {key}")
    if target.get("scope") != "selected-case-only":
        errors.append("action target scope must be selected-case-only")
    for key in ("occurrence_ids", "shot_ids", "shot_revision_ids", "internal_revision_ids", "owned_media_ids"):
        values = target.get(key)
        if not isinstance(values, list) or not values or any(not isinstance(value, str) or not value for value in values):
            errors.append(f"action target is missing a non-empty {key} inventory")
    locator = _mapping(target.get("target_locator"))
    if contract.case_id == "A01":
        for key in (
            "occurrence_id", "shot_id", "shot_revision_id", "selector_clip_id",
            "voice_clip_id", "frame_overlay_clip_id", "replacement_asset_key",
        ):
            if not isinstance(locator.get(key), str) or not locator[key]:
                errors.append(f"A01 target locator is missing {key}")
        if locator.get("preserve_roles") != ["timing", "voiceover", "frame-overlay"]:
            errors.append("A01 target locator does not pin timing/voiceover/frame-overlay preservation")
        inventories = {
            "occurrence_id": "occurrence_ids", "shot_id": "shot_ids",
            "shot_revision_id": "shot_revision_ids",
        }
        for field, inventory in inventories.items():
            value = locator.get(field)
            if isinstance(value, str) and value not in (target.get(inventory) or []):
                errors.append(f"A01 target locator {field} is absent from {inventory}")
    elif contract.case_id == "A03":
        for field in ("closing_occurrence_id", "middle_occurrence_id"):
            if not isinstance(locator.get(field), str) or not locator[field]:
                errors.append(f"A03 target locator is missing {field}")
        occurrence_ids = target.get("occurrence_ids")
        if isinstance(occurrence_ids, list) and len(occurrence_ids) != 4:
            errors.append("A03 target must pin exactly four occurrences")
        if isinstance(occurrence_ids, list):
            for field in ("closing_occurrence_id", "middle_occurrence_id"):
                value = locator.get(field)
                if isinstance(value, str) and value not in occurrence_ids:
                    errors.append(f"A03 target locator {field} is absent from occurrence_ids")
        if locator.get("closing_occurrence_id") == locator.get("middle_occurrence_id"):
            errors.append("A03 closing and middle target occurrences must differ")
    return errors


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def case_launch_prerequisites(
    case: Mapping[str, Any],
    *,
    fixture_ready: bool,
    hidden_checks: Any,
    target_receipt: Mapping[str, Any] | None,
    coordinator_readback_ready: bool,
    coordinator_safety_ready: bool,
) -> list[str]:
    """Return coordinator-owned reasons a scored worker must not launch.

    This is the shared, fail-closed predicate used by rehearsal and the live
    launcher.  It checks only evidence and routes known before launch; it does
    not claim that a future after/readback artifact already exists.
    """
    case_id = str(case.get("id", ""))
    reasons: list[str] = []
    if not fixture_ready:
        reasons.append("validated fixture/entrypoint is not ready")

    if not isinstance(hidden_checks, list) or not hidden_checks:
        reasons.append("case-specific semantic oracle is missing")
    elif any(
        isinstance(check, Mapping)
        and check.get("check") == "semantic_oracle_unavailable"
        for check in hidden_checks
    ):
        reasons.append("case-specific semantic oracle is explicitly unavailable")

    if case.get("kind") == "action":
        contract = action_target_contract(case)
        if contract.status != "ready":
            reasons.append(contract.reason or f"{case_id} has no admitted edit/readback route")
        elif target_receipt is None:
            reasons.append("coordinator-prepared target receipt is missing")
        else:
            reasons.extend(validate_action_target_receipt(target_receipt, contract))
    elif case.get("kind") != "navigation":
        reasons.append(f"unsupported case kind {case.get('kind')!r}")

    if not coordinator_readback_ready:
        reasons.append("coordinator before/after readback collector is not proven available")
    if not coordinator_safety_ready:
        reasons.append("independent coordinator safety capture is not proven available")
    return list(dict.fromkeys(reasons))


__all__ = [
    "ActionTargetContract", "CONTRACT_KIND", "EXACT_NAVIGATION_PROJECTION",
    "GENERIC_AUTHORING_ROUTE",
    "FixtureInput", "NavigationFixtureContract", "action_target_contract",
    "case_launch_prerequisites", "navigation_fixture_contract", "validate_action_target_receipt",
    "validate_l10_playback_evidence", "validate_navigation_entrypoint",
]
