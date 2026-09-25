"""Explicit Runtime setup and provenance checks for Astrid fixtures."""

import json
import os
from importlib import metadata
from pathlib import Path
import sys
from urllib.parse import unquote, urlparse


def assert_t9_runtime_selection() -> None:
    """Reject a conflicting Runtime checkout in the qualified T9 process tree."""
    manifest_value = os.environ.get("BANODOCO_LOCAL_SOURCE_MANIFEST", "").strip()
    if not manifest_value:
        return
    manifest = Path(manifest_value).expanduser().resolve()
    if not manifest.is_file():
        raise AssertionError(f"T9 Runtime source manifest is missing: {manifest}")
    profile = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(profile, dict):
        raise AssertionError("T9 Runtime source profile must be an object")
    expected_checkout = Path(str(profile["runtime_checkout"])).expanduser().resolve()
    expected_environment = Path(str(profile["runtime_environment"])).expanduser().resolve()
    interpreter_environment = Path(sys.prefix).resolve()
    if not interpreter_environment.is_relative_to(expected_environment):
        raise AssertionError(
            "T9 Runtime interpreter conflicts with source profile: "
            f"{interpreter_environment} is not under {expected_environment}"
        )

    configured_checkout = os.environ.get("BANODOCO_RUNTIME_CHECKOUT", "").strip()
    if configured_checkout and Path(configured_checkout).expanduser().resolve() != expected_checkout:
        raise AssertionError(
            "BANODOCO_RUNTIME_CHECKOUT conflicts with the T9 source profile: "
            f"{configured_checkout} != {expected_checkout}"
        )

    imported = []
    for name in ("runtime_protocol", "runtime_protocol.daemon", "runtime_protocol.store", "banodoco_local"):
        module = sys.modules.get(name)
        origin = getattr(module, "__file__", None)
        if origin:
            imported.append(Path(origin).resolve())
    if not imported:
        raise AssertionError("T9 Runtime modules were not imported")
    for origin in imported:
        if origin.is_relative_to(expected_checkout):
            continue
        if not origin.is_relative_to(expected_environment):
            raise AssertionError(
                "T9 Runtime import escaped the qualified checkout/environment: "
                f"{origin}"
            )

    try:
        direct_url = metadata.distribution("banodoco-workspace-runtime").read_text("direct_url.json")
    except (metadata.PackageNotFoundError, FileNotFoundError):
        direct_url = None
    if direct_url:
        source_url = json.loads(direct_url).get("url", "")
        parsed = urlparse(str(source_url))
        selected_source = Path(unquote(parsed.path)).resolve() if parsed.scheme == "file" else None
        if selected_source != expected_checkout:
            raise AssertionError(
                "T9 Runtime package provenance conflicts with source profile: "
                f"{selected_source} != {expected_checkout}"
            )


def initialize_runtime_realm(root: str | Path) -> Path:
    """Provision a missing fixture root through Runtime's canonical creator."""
    root = Path(root)
    if not root.exists():
        from runtime_protocol.store import RealmStore

        initialize = getattr(RealmStore, "initialize", None)
        if callable(initialize):
            initialize(root).close()
        else:
            ensure_realm = getattr(RealmStore, "ensure_realm", None)
            if not callable(ensure_realm):
                raise RuntimeError(
                    "installed Runtime RealmStore exposes neither the public "
                    "initialize(root) creator nor the legacy ensure_realm() creator"
                )
            store = RealmStore(root)
            try:
                store.ensure_realm()
            finally:
                store.close()
    return root
