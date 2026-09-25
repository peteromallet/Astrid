from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrid.core._shared.result_manifest import read_result_manifest
from astrid.core.execution.capability_ledger import load_capability_ledger
from astrid.core.pack.loader import _load_manifest_payload
from astrid.packs.h3_av.executors.compile.run import main as compile_main
from astrid.packs.h3_av.executors.prepare.run import main as prepare_main
from astrid.packs.h3_av.src.prepare import prepare_request
from tests.packs.h3_av.test_compile import _request


ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "config/astrid-beta-capabilities.json"


def test_h3_census_distinguishes_five_labels_four_executors_and_one_orchestrator() -> None:
    ledger = load_capability_ledger(MATRIX)
    h3_labels = [row for row in ledger["sources"]["pack_labels"] if row["pack"] == "h3_av"]
    assert [(row["label"], row["disposition"]) for row in h3_labels] == [
        ("prepare_transform", "unmapped_source_label"),
        ("compile_transform", "unmapped_source_label"),
        ("compose_transform", "unmapped_source_label"),
        ("verify_transform", "unmapped_source_label"),
        ("transform", "unmapped_source_label"),
    ]
    assert ledger["source_census"]["label_bindings"] == [
        {
            "pack": "h3_av",
            "label": "prepare_transform",
            "kind": "executor",
            "canonical_id": "h3_av.prepare",
            "manifest": "astrid/packs/h3_av/executors/prepare/executor.yaml",
        },
        {
            "pack": "h3_av",
            "label": "compile_transform",
            "kind": "executor",
            "canonical_id": "h3_av.compile",
            "manifest": "astrid/packs/h3_av/executors/compile/executor.yaml",
        },
        {
            "pack": "h3_av",
            "label": "compose_transform",
            "kind": "executor",
            "canonical_id": "h3_av.compose",
            "manifest": "astrid/packs/h3_av/executors/compose/executor.yaml",
        },
        {
            "pack": "h3_av",
            "label": "verify_transform",
            "kind": "executor",
            "canonical_id": "h3_av.verify",
            "manifest": "astrid/packs/h3_av/executors/verify/executor.yaml",
        },
        {
            "pack": "h3_av",
            "label": "transform",
            "kind": "orchestrator",
            "canonical_id": "h3_av.transform",
            "manifest": "astrid/packs/h3_av/orchestrators/transform/orchestrator.yaml",
        },
    ]
    assert {row["id"] for row in ledger["sources"]["executor_inventory"] if row["id"].startswith("h3_av.")} == {
        "h3_av.prepare", "h3_av.compile", "h3_av.compose", "h3_av.verify"
    }
    assert "h3_av.transform" not in {row["id"] for row in ledger["sources"]["executor_inventory"]}
    orchestrator = _load_manifest_payload(ROOT / "astrid/packs/h3_av/orchestrators/transform/orchestrator.yaml")
    assert orchestrator["child_executors"] == [
        "h3_av.prepare", "h3_av.compile", "vibecomfy.validate", "vibecomfy.run", "h3_av.compose", "h3_av.verify"
    ]


def test_h3_matrix_rows_are_optional_cpu_helpers_with_real_dependencies() -> None:
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in matrix["capabilities"] if row["id"].startswith("h3_av.")}
    assert set(rows) == {"h3_av.prepare", "h3_av.compile", "h3_av.compose", "h3_av.verify"}
    for row in rows.values():
        assert row["disposition"] == "optional"
        assert row["adapter_family"] == "cpu"
        assert row["resource_keys"] == ["cpu"]
        assert "model readiness" in row["evidence_reason"]
        assert row["required_binaries"] == ["ffmpeg", "ffprobe"]
    assert rows["h3_av.compile"]["required_packages"] == ["vibecomfy"]


def test_prepare_success_has_strict_universal_result_manifest(tmp_path: Path) -> None:
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(_request().value), encoding="utf-8")
    preparation_path = tmp_path / "prepare" / "preparation.json"
    assert prepare_main(["--request", str(request_path), "--out", str(preparation_path)]) == 0
    manifest = read_result_manifest(preparation_path.parent / "manifest.json", staging_root=preparation_path.parent)
    assert [output.path for output in manifest.outputs] == ["preparation.json"]
    assert manifest.outputs[0].is_primary is True


def test_compile_success_has_strict_universal_result_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    preparation = prepare_request(_request(), asset_map={"source": str(source)})
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(json.dumps(preparation), encoding="utf-8")
    output = tmp_path / "compile"
    assert compile_main(["--preparation", str(preparation_path), "--out", str(output)]) == 0
    manifest = read_result_manifest(output / "manifest.json", staging_root=output)
    assert {output.path for output in manifest.outputs} == {
        "compilation.json", "managed-assets.zip", "workflow.py", "workflow.vibe.json", "source.json"
    }


def test_compile_failure_removes_stale_success_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(
        json.dumps(prepare_request(_request(), asset_map={"source": str(source)})),
        encoding="utf-8",
    )
    output = tmp_path / "compile"
    assert compile_main(["--preparation", str(preparation_path), "--out", str(output)]) == 0
    assert (output / "manifest.json").is_file()

    preparation_path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="preparation must be a JSON object"):
        compile_main(["--preparation", str(preparation_path), "--out", str(output)])
    assert not (output / "manifest.json").exists()
