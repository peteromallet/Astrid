"""Shared declaration for explicit generation publication outputs.

The declaration is capability-definition metadata, not caller-provided
publication authority.  Both the SDK and the pack host use this module so
they cannot independently infer different output ports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SUPPORTED_GENERATION_MODALITIES = frozenset(("image", "video", "audio"))


class GenerationPublicationError(ValueError):
    """A registered executor's publication declaration is invalid."""


@dataclass(frozen=True)
class GenerationPublication:
    """Validated, definition-owned explicit publication declaration."""

    version: int
    modality: str
    output_port: str


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


def _definition_metadata(definition: Any) -> Mapping[str, Any]:
    metadata = _field(definition, "metadata")
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise GenerationPublicationError("executor metadata must be an object")
    return metadata


def _definition_outputs(definition: Any) -> tuple[Any, ...]:
    outputs = _field(definition, "outputs")
    if outputs is None:
        return ()
    if isinstance(outputs, (str, bytes)) or not isinstance(outputs, (tuple, list)):
        raise GenerationPublicationError("executor outputs must be a list")
    return tuple(outputs)


def _is_compatible_media_artifact(artifact_type: Any, modality: str) -> bool:
    if not isinstance(artifact_type, str):
        return False
    value = artifact_type.strip().lower()
    if not value:
        return False
    if modality == "image":
        return value == "image" or value.startswith("image/")
    if modality == "video":
        return value in {"video", "clip"} or value.startswith("video/")
    if modality == "audio":
        return value == "audio" or value.startswith("audio/")
    return False


def resolve_generation_publication(
    definition: Any,
    *,
    capability_type: str | None = "executor",
) -> GenerationPublication | None:
    """Validate and resolve a definition-owned explicit publication contract.

    A missing declaration is a normal legacy case and returns ``None``.  Once
    the metadata key is present, every field and the selected output port are
    closed and validated.  The public ``Capability.outputs`` projection is
    intentionally not consulted; callers must pass the discovered definition.
    """

    if capability_type is not None and capability_type != "executor":
        raise GenerationPublicationError(
            "generation_publication is only valid on executor definitions"
        )
    metadata = _definition_metadata(definition)
    if "generation_publication" not in metadata:
        return None
    if metadata.get("output_result_manifest") is not True:
        raise GenerationPublicationError(
            "generation_publication requires output_result_manifest: true"
        )

    raw = metadata["generation_publication"]
    if not isinstance(raw, Mapping):
        raise GenerationPublicationError("generation_publication must be an object")
    if set(raw) != {"version", "modality", "output_port"}:
        raise GenerationPublicationError(
            "generation_publication must contain exactly version, modality, and output_port"
        )
    version = raw["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise GenerationPublicationError("generation_publication.version must be 1")
    modality = raw["modality"]
    if modality not in SUPPORTED_GENERATION_MODALITIES:
        raise GenerationPublicationError(
            "generation_publication.modality must be image, video, or audio"
        )
    output_port = raw["output_port"]
    if not isinstance(output_port, str) or not output_port.strip():
        raise GenerationPublicationError(
            "generation_publication.output_port must be a non-empty string"
        )

    matches = [
        output
        for output in _definition_outputs(definition)
        if _field(output, "name") == output_port
    ]
    if len(matches) != 1:
        raise GenerationPublicationError(
            f"generation_publication.output_port {output_port!r} must identify exactly one declared output"
        )
    output = matches[0]
    if _field(output, "type") != "file":
        raise GenerationPublicationError(
            f"generation_publication.output_port {output_port!r} must be a file port"
        )
    if not _is_compatible_media_artifact(_field(output, "artifact_type"), modality):
        raise GenerationPublicationError(
            f"generation_publication.output_port {output_port!r} is not a compatible {modality} media port"
        )

    return GenerationPublication(
        version=version,
        modality=modality,
        output_port=output_port,
    )


__all__ = [
    "GenerationPublication",
    "GenerationPublicationError",
    "SUPPORTED_GENERATION_MODALITIES",
    "resolve_generation_publication",
]
