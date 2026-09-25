from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("vibecomfy.ingest.normalize")

from vibecomfy.workflow import VibeWorkflow

from astrid.packs.h3_av.src.compile import compile_preparation
from astrid.packs.vibecomfy.executors.validate import run as validator
from tests.packs.h3_av.test_integrated_graph_bundle import _prepared_fixture_a


def _compiled_a(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    preparation, _ = _prepared_fixture_a(tmp_path)
    output = tmp_path / "compiled-a"
    compile_preparation(preparation, out_dir=output)
    graph_path = output / "graph.vibe.json"
    return json.loads(graph_path.read_text(encoding="utf-8")), graph_path


def _validate(path: Path, out: Path) -> int:
    return validator.main(["validate", str(path), "--out", str(out)])


def test_committed_a_envelope_validates_without_mutation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    raw, graph_path = _compiled_a(tmp_path)
    original_bytes = graph_path.read_bytes()
    workflow = VibeWorkflow.from_envelope(raw)
    assert workflow.to_envelope() == raw
    assert workflow.compile("api") == VibeWorkflow.from_envelope(raw).compile("api")
    api = workflow.compile("api")
    assert api["110"]["inputs"]["ref_images.ref_image_3"] == ["c3-reference-image-3", 0]
    assert len(workflow.outputs) == 1 and workflow.outputs[0].node_id == "992"
    assert sum(node.class_type == "SamplerCustomAdvanced" for node in workflow.nodes.values()) == 1
    assert any("Mask" in node.class_type for node in workflow.nodes.values())

    out = tmp_path / "validation"
    assert _validate(graph_path, out) == 0
    report = json.loads((out / "validation-report.json").read_text(encoding="utf-8"))
    assert report["authority"] == "vibeworkflow_envelope"
    assert report["validation_mode"] == "static_vibeworkflow_envelope"
    assert report["ok"] is True and report["python_execution_consent"] is None
    assert graph_path.read_bytes() == original_bytes


@pytest.mark.parametrize(
    "mutate",
    [
        lambda graph: graph.update(nodes=[]),
        lambda graph: graph.update(edges={}),
        lambda graph: graph["edges"].append({"from_node": "absent", "to_node": "also-absent"}),
        lambda graph: graph.update(nodes={}, edges=[]),
        lambda graph: graph.update(vibecomfy_format_version="999"),
        lambda graph: graph.pop("vibecomfy_format_version"),
    ],
    ids=("list-nodes", "non-list-edges", "missing-endpoint", "empty", "bad-version", "unversioned"),
)
def test_envelope_validation_rejects_malformed_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutate: Any
) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    graph, _ = _compiled_a(tmp_path)
    mutate(graph)
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    out = tmp_path / "malformed-report"
    assert _validate(path, out) == 1
    assert not (out / "validation-report.json").exists()


def test_envelope_validation_ignores_stored_compiled_api(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    graph, _ = _compiled_a(tmp_path)
    workflow = VibeWorkflow.from_envelope(graph)
    derived = workflow.compile("api")
    graph["compiled_api"] = {"forged": {"class_type": "RunAnything"}}
    path = tmp_path / "forged-api.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    out = tmp_path / "forged-report"
    assert _validate(path, out) == 1
    assert not (out / "validation-report.json").exists()
    assert workflow.compile("api") == derived


def test_json_validation_dispatch_and_consent_regressions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASTRID_INTERNAL_INVOCATION", "1")
    graph, _ = _compiled_a(tmp_path)
    ui = tmp_path / "ui.json"
    ui.write_text('{"nodes": [], "links": []}', encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(validator, "_static_ui_validation", lambda _path: calls.append("ui") or {
        "schema_version": 1, "authority": "input_ui_graph", "validation_mode": "static_ui_graph",
        "workflow_id": "ui", "status": "ok", "ok": True, "issues": [],
        "python_execution_consent": None, "security_gate_audit": [],
    })
    ui_out = tmp_path / "ui-report"
    assert _validate(ui, ui_out) == 0
    ui_report = json.loads((ui_out / "validation-report.json").read_text(encoding="utf-8"))
    assert ui_report["validation_mode"] == "static_ui_graph" and calls == ["ui"]

    malformed_ui = tmp_path / "bad-ui.json"
    malformed_ui.write_text('{"nodes": {}}', encoding="utf-8")
    assert _validate(malformed_ui, tmp_path / "bad-ui-report") == 1

    ambiguous = dict(graph, nodes=[])
    ambiguous_path = tmp_path / "ambiguous.json"
    ambiguous_path.write_text(json.dumps(ambiguous), encoding="utf-8")
    assert _validate(ambiguous_path, tmp_path / "ambiguous-report") == 1
    assert calls == ["ui"]

    with pytest.raises(validator.PythonExecutionConsentError):
        validator.validate_python_execution_consent(None)
    validator.validate_python_execution_consent("confirmed")
