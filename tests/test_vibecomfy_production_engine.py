from __future__ import annotations

import sys
import importlib
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrid.packs.vibecomfy import production_engine


def test_execution_identity_digest_is_stable_and_model_bound() -> None:
    first = production_engine.execution_identity_digest(
        "model-a", "image/a", model_digest="sha256:" + "a" * 64
    )
    second = production_engine.execution_identity_digest(
        "model-b", "image/a", model_digest="sha256:" + "a" * 64
    )
    assert first != second
    assert first == production_engine.execution_identity_digest(
        "model-a", "image/a", model_digest="sha256:" + "a" * 64
    )


def test_loaded_identity_is_bound_to_canonical_metadata_and_content() -> None:
    base = production_engine.LoadedWorkflow(
        resolved=object(),
        model_id="model-a",
        template_id="image/a",
        workflow_identity="portrait",
        workflow_revision="revision-a",
        workflow_content_digest="sha256:" + "b" * 64,
    )
    changed = production_engine.LoadedWorkflow(
        resolved=object(),
        model_id=base.model_id,
        template_id=base.template_id,
        workflow_identity=base.workflow_identity,
        workflow_revision=base.workflow_revision,
        workflow_content_digest="sha256:" + "c" * 64,
    )

    assert production_engine.loaded_workflow_execution_identity(
        base
    ) != production_engine.loaded_workflow_execution_identity(changed)


def test_load_workflow_path_unions_ready_template_and_ui_canonicalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = tmp_path / "ready.json"
    ready.write_text('{"template_id":"image/a","bindings":{}}', encoding="utf-8")
    ui = tmp_path / "ui.json"
    ui.write_text('{"nodes":[],"links":[]}', encoding="utf-8")
    ready_workflow = object()
    ui_workflow = object()
    ready_bundle = SimpleNamespace(
        workflow=SimpleNamespace(
            metadata={"ready_template": "image/a", "model_id": "model-a"}
        ),
        workflow_identity="ready-identity",
        revision_id="ready-revision",
        require_canonical_authority=Mock(),
    )
    ui_bundle = SimpleNamespace(
        workflow=SimpleNamespace(metadata={}),
        workflow_identity="ui-identity",
        revision_id="ui-revision",
        require_canonical_authority=Mock(),
    )
    monkeypatch.setattr(
        production_engine,
        "_load_workflow",
        Mock(return_value=ready_workflow),
    )
    canonicalize = Mock(return_value=ui_workflow)
    monkeypatch.setattr(production_engine, "_canonicalize_ui_workflow", canonicalize)
    monkeypatch.setattr(
        production_engine,
        "_canonical_bundle_value",
        lambda value: ready_bundle if value is ready_workflow else ui_bundle,
    )

    loaded_ready = production_engine.load_workflow_path(ready, tmp_path / "ready-scratch")
    loaded_ui = production_engine.load_workflow_path(ui, tmp_path / "ui-scratch")

    assert (loaded_ready.model_id, loaded_ready.template_id) == ("model-a", "image/a")
    assert loaded_ready.workflow_revision == "ready-revision"
    assert (loaded_ui.model_id, loaded_ui.template_id) == ("vibecomfy", "ui-identity")
    assert loaded_ui.workflow_revision == "ui-revision"
    canonicalize.assert_called_once_with(ui.resolve(), {"nodes": [], "links": []}, (tmp_path / "ui-scratch").resolve())


def test_canonical_bundle_compiles_through_single_production_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = object()
    bundle = SimpleNamespace(compile=Mock(return_value=approved))
    monkeypatch.setattr(production_engine, "_canonical_bundle_value", lambda _: bundle)

    assert production_engine._canonical_bundle(object()) == (approved, bundle)
    bundle.compile.assert_called_once_with()


def test_run_workflow_path_rejects_execution_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workflow = tmp_path / "workflow.json"
    workflow.write_text('{"template_id":"image/a","bindings":{}}', encoding="utf-8")
    monkeypatch.setattr(
        production_engine,
        "load_workflow_path",
        lambda *_args, **_kwargs: production_engine.LoadedWorkflow(
            resolved=SimpleNamespace(metadata={}),
            model_id="model-a",
            template_id="image/a",
            workflow_identity="portrait",
            workflow_revision="revision-a",
            workflow_content_digest="sha256:" + "b" * 64,
        ),
    )
    with pytest.raises(
        production_engine.ProductionEngineError,
        match="execution identity changed",
    ):
        production_engine.run_workflow_path(
            workflow,
            tmp_path / "out",
            task_identity="task-1",
            expected_execution_identity="wrong",
        )


def test_run_executor_verifies_checkout_readiness_pair_and_selects_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    run = importlib.import_module("astrid.packs.vibecomfy.executors.run.run")
    workflow = tmp_path / "workflow.json"
    workflow.write_text('{"template_id":"image/a","bindings":{}}', encoding="utf-8")
    output_root = tmp_path / "outputs"
    engine_output = output_root / "engine-output" / "image.png"
    engine_output.parent.mkdir(parents=True)
    engine_output.write_bytes(b"image")
    readiness = tmp_path / "readiness.json"
    readiness_bytes = json.dumps({"vibecomfy_session": {}}).encode("utf-8")
    readiness.write_bytes(readiness_bytes)
    readiness_hash = "sha256:" + hashlib.sha256(readiness_bytes).hexdigest()
    managed_run = Mock(return_value=(engine_output,))
    monkeypatch.setattr(production_engine, "run_workflow_path", managed_run)

    run._run_and_settle(
        workflow,
        output_root,
        task_identity="task-1",
        execution_identity="execution-1",
        readiness_profile_path=str(readiness),
        readiness_profile_hash=readiness_hash,
    )

    assert managed_run.call_args.kwargs["profile_id"] == "checkout_server"
    assert managed_run.call_args.kwargs["hc03_profile"] == {
        "vibecomfy_session": {}
    }
    with pytest.raises(ValueError, match="must be supplied together"):
        run._run_and_settle(
            workflow,
            tmp_path / "pair-failure",
            task_identity="task-1",
            readiness_profile_path=str(readiness),
            readiness_profile_hash="-",
        )


def test_run_executor_rejects_outputs_outside_private_custody(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    run = importlib.import_module("astrid.packs.vibecomfy.executors.run.run")
    workflow = tmp_path / "workflow.json"
    workflow.write_text('{"template_id":"image/a","bindings":{}}', encoding="utf-8")
    outside = tmp_path / "outside.png"
    outside.write_bytes(b"image")
    monkeypatch.setattr(
        production_engine,
        "run_workflow_path",
        Mock(return_value=(outside,)),
    )

    with pytest.raises(FileNotFoundError, match="escaped output custody"):
        run._run_and_settle(
            workflow,
            tmp_path / "outputs",
            task_identity="task-1",
        )


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
