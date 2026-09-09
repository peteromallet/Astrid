from __future__ import annotations

import sys
import importlib
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrid.packs.vibecomfy import production_engine


@pytest.fixture
def _isolated_comfy_imports() -> Iterator[None]:
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "comfy" or name.startswith("comfy.")
    }
    original_path = list(sys.path)
    for name in original_modules:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in tuple(sys.modules):
            if name == "comfy" or name.startswith("comfy."):
                sys.modules.pop(name, None)
        sys.modules.update(original_modules)
        sys.path[:] = original_path


def test_pip_embedded_fails_closed_when_embedded_client_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _isolated_comfy_imports: None,
) -> None:
    monkeypatch.setenv("COMFYUI_PATH", str(tmp_path / "missing-client"))
    monkeypatch.setattr(production_engine, "_EMBEDDED_COMFY_FALLBACKS", ())

    with pytest.raises(
        production_engine.ProductionEngineError,
        match="comfy/client/embedded_comfy_client.py",
    ):
        production_engine._run_profile(
            object(),
            "pip_embedded",
            None,
            model_id="z_image_turbo",
            template_id="image/z_image",
            task_identity="test-task",
            destination=tmp_path / "outputs",
        )


def test_pip_embedded_inserts_tree_containing_embedded_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _isolated_comfy_imports: None,
) -> None:
    root = tmp_path / "comfyui-embedded"
    client = root / "comfy" / "client" / "embedded_comfy_client.py"
    client.parent.mkdir(parents=True)
    (root / "comfy" / "__init__.py").write_text("", encoding="utf-8")
    (client.parent / "__init__.py").write_text("", encoding="utf-8")
    client.write_text("class Comfy:\n    pass\n", encoding="utf-8")
    monkeypatch.setenv("COMFYUI_PATH", str(root))
    monkeypatch.setattr(production_engine, "_EMBEDDED_COMFY_FALLBACKS", ())

    selected = production_engine._bootstrap_embedded_comfy_client()

    assert selected == root.resolve()
    assert sys.path[0] == str(root.resolve())
    imported = sys.modules["comfy.client.embedded_comfy_client"]
    assert imported.__file__ is not None
    assert Path(imported.__file__).resolve() == client.resolve()


def test_pip_embedded_consumes_canonical_bundle_and_pinned_session_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _isolated_comfy_imports: None,
) -> None:
    root = tmp_path / "comfyui-embedded"
    client = root / "comfy" / "client" / "embedded_comfy_client.py"
    client.parent.mkdir(parents=True)
    (root / "comfy" / "__init__.py").write_text("", encoding="utf-8")
    (client.parent / "__init__.py").write_text("", encoding="utf-8")
    client.write_text("class Comfy:\n    pass\n", encoding="utf-8")
    monkeypatch.setenv("COMFYUI_PATH", str(root))
    monkeypatch.setattr(production_engine, "_EMBEDDED_COMFY_FALLBACKS", ())

    workflow = SimpleNamespace(metadata={"comfy_configuration": {"cache_none": True}})
    bundle = SimpleNamespace(workflow=workflow)
    record = object()
    monkeypatch.setattr(
        production_engine, "_canonical_bundle", lambda _resolved: (record, bundle)
    )
    runtime_run = importlib.import_module("vibecomfy.runtime.run")

    output = tmp_path / "engine-output" / "image.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"image")
    run_embedded_sync = Mock(return_value=SimpleNamespace(outputs=[output]))
    monkeypatch.setattr(runtime_run, "run_embedded_sync", run_embedded_sync)

    result = production_engine._run_profile(
        object(),
        "pip_embedded",
        None,
        model_id="z-image",
        template_id="image/z_image",
        task_identity="task-1",
        destination=tmp_path / "task-out",
    )

    assert result == (output.resolve(),)
    assert run_embedded_sync.call_args.args == (record, bundle)
    config = run_embedded_sync.call_args.kwargs["config"]
    assert config.cache_policy == "none"
    assert config.extra["base_directory"] == str(root.resolve())
    assert config.extra["disable_known_models"] is True
    assert config.extra["extra_model_paths_config"] == [
        str((root / "extra_model_paths.yaml").resolve())
    ]
    assert config.runtime_root == (tmp_path / "task-out" / ".vibecomfy-runtime").resolve()
    assert config.cwd == root.resolve()
