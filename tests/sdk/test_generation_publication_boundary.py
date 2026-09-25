from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrid.core.contracts.schema import Output
from astrid.sdk.exceptions import CapabilityValidationError
from astrid.sdk.invocation import (
    _generation_primary_output_port,
    _generation_publish_effect,
    _kernel_invoke,
)
from astrid.sdk.results import Capability


def _capability() -> Capability:
    definition = {
        "metadata": {
            "output_result_manifest": True,
            "generation_publication": {
                "version": 1,
                "modality": "video",
                "output_port": "verified_candidate",
            },
        },
        "outputs": [
            {"name": "verified_candidate", "type": "file", "artifact_type": "video/mp4"},
            {"name": "verification", "type": "file", "artifact_type": "application/json"},
        ],
    }
    return Capability(
        id="h3_av.verify",
        capability_type="executor",
        native_kind="external",
        handle=SimpleNamespace(),
        outputs=(
            Output(name="verified_candidate", type="file", artifact_type="video/mp4"),
            Output(name="verification", type="file", artifact_type="application/json"),
        ),
        definition=definition,
    )


def _intent() -> dict[str, object]:
    return {
        "version": 1,
        "modality": "video",
        "partial_success_policy": "reject",
        "groups": [{
            "group_key": "main",
            "selectors": [{
                "selector": "main-0",
                "ordinal": 0,
                "variant_key": "original",
            }],
        }],
    }


def test_sdk_resolves_definition_port_and_builds_explicit_effect() -> None:
    capability = _capability()
    assert _generation_primary_output_port(capability, "video") == "verified_candidate"
    effect = _generation_publish_effect(
        capability,
        project="project-1",
        generation_intent=_intent(),
    )
    assert effect["payload"]["groups"][0]["selectors"][0]["output_port"] == "verified_candidate"


def test_public_projection_cannot_override_definition_owned_port() -> None:
    capability = _capability()
    object.__setattr__(capability, "outputs", (Output(name="caller_selected", type="file", artifact_type="video/mp4"),))
    assert _generation_primary_output_port(capability, "video") == "verified_candidate"


def test_explicit_only_declaration_does_not_auto_publish_without_intent() -> None:
    calls = []

    class Tasks:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(ok=True, data={"run_id": "r", "task_id": "t", "attempt_id": "a"})

    _kernel_invoke(
        _capability(),
        kind="executor",
        project="project-1",
        inputs={},
        outputs={},
        _client=SimpleNamespace(tasks=Tasks()),
    )
    assert "settlement_effect" not in calls[0]


def test_declared_publication_still_requires_project() -> None:
    with pytest.raises(CapabilityValidationError, match="requires a project"):
        _generation_publish_effect(
            _capability(), project=None, generation_intent=_intent()
        )
