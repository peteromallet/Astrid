"""Code-declared kernel schema-pack manifest and composition helpers.

The kernel vocabulary belongs to schema composition, while runtime event
validation consumes the resulting frozen registry. Keeping the declaration
here lets schema-pack composition stay below the event service instead of
creating a schema-packs/events import cycle.
"""

from __future__ import annotations

from astrid.core.kernel.vocabulary import (
    CORE_COMMAND_KINDS,
    CORE_CONFORMANCE_DIMENSIONS,
    CORE_EVENT_KINDS,
    CORE_MANIFEST_VERSION,
    CORE_PACK_ID,
    CORE_REPOSITORIES,
    CORE_STREAM_TYPES,
    core_schema_pack_payload,
)
from astrid.core.schema_packs.manifest import (
    SchemaPackManifest,
    parse_schema_pack_manifest,
)
from astrid.core.schema_packs.registry import (
    FrozenSchemaPackRegistry,
    SchemaPackRegistry,
)

def core_schema_pack_manifest() -> SchemaPackManifest:
    """Build the strict, validated kernel manifest without YAML."""
    return parse_schema_pack_manifest(core_schema_pack_payload(), source_path=None)


def register_core_vocabulary(registry: SchemaPackRegistry) -> SchemaPackRegistry:
    """Register the kernel vocabulary without consulting Astrid packs."""
    return registry.register_pack(core_schema_pack_manifest())


def core_only_registry() -> FrozenSchemaPackRegistry:
    """Compose the frozen kernel-only registry (no Astrid packs)."""
    return register_core_vocabulary(SchemaPackRegistry()).freeze()


__all__ = [
    "CORE_COMMAND_KINDS",
    "CORE_CONFORMANCE_DIMENSIONS",
    "CORE_EVENT_KINDS",
    "CORE_MANIFEST_VERSION",
    "CORE_PACK_ID",
    "CORE_REPOSITORIES",
    "CORE_STREAM_TYPES",
    "core_only_registry",
    "core_schema_pack_manifest",
    "register_core_vocabulary",
]

