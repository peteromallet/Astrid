"""Explicit runtime setup for Astrid integration fixtures."""

from pathlib import Path


def initialize_runtime_realm(root: str | Path) -> Path:
    """Provision a missing fixture root through Runtime's canonical creator."""
    root = Path(root)
    if not root.exists():
        from runtime_protocol.store import RealmStore

        RealmStore.initialize(root).close()
    return root
