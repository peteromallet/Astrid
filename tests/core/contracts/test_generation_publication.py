from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrid.core.contracts.generation_publication import (
    GenerationPublicationError,
    resolve_generation_publication,
)


def _definition(*, metadata=None, outputs=None, kind="executor"):
    return SimpleNamespace(
        metadata={
            "output_result_manifest": True,
            "generation_publication": {
                "version": 1,
                "modality": "video",
                "output_port": "verified_candidate",
            },
            **(metadata or {}),
        },
        outputs=outputs or (
            SimpleNamespace(
                name="verified_candidate",
                type="file",
                artifact_type="video/mp4",
            ),
            SimpleNamespace(
                name="verification",
                type="file",
                artifact_type="application/json",
            ),
        ),
        kind=kind,
    )


def test_resolver_accepts_closed_definition_owned_video_declaration() -> None:
    resolved = resolve_generation_publication(_definition())
    assert resolved is not None
    assert (resolved.version, resolved.modality, resolved.output_port) == (
        1,
        "video",
        "verified_candidate",
    )


@pytest.mark.parametrize(
    "metadata, outputs, match",
    [
        ({"output_result_manifest": False}, None, "output_result_manifest"),
        ({"generation_publication": {"version": 1, "modality": "video", "output_port": "verified_candidate", "extra": True}}, None, "exactly"),
        ({"generation_publication": {"version": 2, "modality": "video", "output_port": "verified_candidate"}}, None, "version"),
        ({"generation_publication": {"version": 1, "modality": "video", "output_port": "missing"}}, None, "exactly one"),
        ({"generation_publication": {"version": 1, "modality": "video", "output_port": "verification"}}, None, "compatible"),
    ],
)
def test_resolver_rejects_malformed_or_conflicting_declarations(metadata, outputs, match) -> None:
    with pytest.raises(GenerationPublicationError, match=match):
        resolve_generation_publication(_definition(metadata=metadata, outputs=outputs))


def test_resolver_rejects_non_executor_declaration() -> None:
    with pytest.raises(GenerationPublicationError, match="executor"):
        resolve_generation_publication(_definition(), capability_type="orchestrator")


def test_absent_declaration_preserves_legacy_none_result() -> None:
    definition = _definition(metadata={"generation_publication": None})
    # A present null is malformed; absence is the legacy case.
    definition.metadata.pop("generation_publication")
    assert resolve_generation_publication(definition) is None
