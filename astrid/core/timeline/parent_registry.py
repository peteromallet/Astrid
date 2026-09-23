"""One authority rule for a Runtime parent composition's asset registry."""

from collections.abc import Mapping
from typing import Any


class ParentRegistryError(ValueError):
    pass


def effective_parent_registry(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Prefer the direct registry; a second declaration must be identical.

    A config registry is a legacy location for the same namespace, not an
    additional source of assets. Keeping this rule shared prevents authoring
    admission from resolving a selector that rendering would not resolve.
    """
    config = payload.get("config")
    if config is not None and not isinstance(config, Mapping):
        raise ParentRegistryError("parent.config must be an object")
    direct = payload.get("registry")
    nested = config.get("registry") if isinstance(config, Mapping) else None
    for path, registry in (("parent.registry", direct), ("parent.config.registry", nested)):
        if registry is not None and not isinstance(registry, Mapping):
            raise ParentRegistryError(f"{path} must be an object")
        if isinstance(registry, Mapping) and "assets" in registry and not isinstance(registry["assets"], Mapping):
            raise ParentRegistryError(f"{path}.assets must be an object")
    if direct is not None and nested is not None and direct != nested:
        raise ParentRegistryError("parent.registry conflicts with parent.config.registry")
    return direct if isinstance(direct, Mapping) else nested if isinstance(nested, Mapping) else {"assets": {}}
