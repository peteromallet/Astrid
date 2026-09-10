from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.p7_cpu_evidence import scan_repositories


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _statuses(report: dict, name: str) -> dict[str, list[dict]]:
    repo = next(item for item in report["repos"] if item["name"] == name)
    return repo["facts"]


def test_scanner_reports_forbidden_production_markers_and_preserves_stage1(tmp_path: Path) -> None:
    _write(tmp_path, "astrid/producer.py", "def run():\n    return supabase.materialize_task()\n")
    _write(tmp_path, "astrid/catalog.py", "LEGACY_SELECTOR = 'legacy_route'\n")
    _write(tmp_path, "astrid/engine.py", "def run_direct_engine():\n    pass\n")
    _write(tmp_path, "tests/stage1/test_unrelated.py", "assert True\n")
    _write(tmp_path, "tests/stage1/README.md", "preserved Stage1 context\n")
    # Negative tests may name retired symbols without becoming production hits.
    _write(tmp_path, "tests/test_negative.py", "assert 'inpaint_frames' not in source\n")

    report = scan_repositories([("fixture", tmp_path)])
    facts = _statuses(report, "fixture")
    assert {fact["id"] for fact in facts["blocked"]} == {
        "forbidden.supabase_task_authority",
        "forbidden.legacy_selector",
        "forbidden.direct_engine",
    }
    assert {fact["id"] for fact in facts["implemented"]} == {
        "forbidden.inpaint_frames",
        "forbidden.qwen_image_hires",
        "stage1.paths_preserved",
    }
    repo = report["repos"][0]
    assert repo["stage1_paths"] == ["tests/stage1/README.md", "tests/stage1/test_unrelated.py"]
    assert facts["implemented"][-1]["paths_sha256"].startswith("sha256:")


def test_scanner_is_deterministic_and_marks_missing_source_unknown(tmp_path: Path) -> None:
    (tmp_path / "tests" / "stage1").mkdir(parents=True)
    first = scan_repositories([("z", tmp_path), ("a", tmp_path / "missing")])
    second = scan_repositories([("a", tmp_path / "missing"), ("z", tmp_path)])
    assert first == second
    missing = first["repos"][0]
    assert missing["name"] == "a"
    assert missing["facts"]["unknown"][0]["id"] == "repository.root"
    existing = first["repos"][1]
    assert {fact["id"] for fact in existing["facts"]["unknown"]} == {
        "forbidden.inpaint_frames",
        "forbidden.qwen_image_hires",
        "forbidden.supabase_task_authority",
        "forbidden.legacy_selector",
        "forbidden.direct_engine",
        "stage1.paths_preserved",
    }


def test_scanner_does_not_confuse_canonical_materialization_or_domain_data_with_task_authority(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "astrid/core/host.py",
        "def read():\n    return require_runtime_materialized_file(path)\n",
    )
    _write(
        tmp_path,
        "src/domain/media.py",
        "async def load():\n    return supabase().from_('generations')\n",
    )
    _write(tmp_path, "tests/stage1/test_preserved.py", "assert True\n")

    report = scan_repositories([("fixture", tmp_path)])
    facts = _statuses(report, "fixture")
    assert {fact["id"] for fact in facts["blocked"]} == set()
    assert {fact["id"] for fact in facts["implemented"]} == {
        "forbidden.inpaint_frames",
        "forbidden.qwen_image_hires",
        "forbidden.supabase_task_authority",
        "forbidden.legacy_selector",
        "forbidden.direct_engine",
        "stage1.paths_preserved",
    }


def test_scanner_includes_worker_source_tree_in_production_negative_evidence(tmp_path: Path) -> None:
    _write(tmp_path, "source/task_handlers/task_registry.py", "HANDLER = 'inpaint_frames'\n")
    _write(tmp_path, "source/task_handlers/task_conversion.py", "MODEL = 'qwen_image_hires'\n")

    report = scan_repositories([("worker", tmp_path)])
    facts = _statuses(report, "worker")
    blocked = {fact["id"] for fact in facts["blocked"]}
    assert blocked == {"forbidden.inpaint_frames", "forbidden.qwen_image_hires"}
    assert any(path.startswith("source/") for path in report["repos"][0]["scanned_files"])


def test_cli_emits_machine_readable_json_without_mutating_root(tmp_path: Path) -> None:
    _write(tmp_path, "src/clean.py", "def ok():\n    return 1\n")
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    result = subprocess.run(
        [sys.executable, "-m", "scripts.p7_cpu_evidence", "--repo", f"fixture={tmp_path}"],
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["schema"] == "astrid.p7_cpu_evidence.v1"
    assert payload["read_only"] is True
    assert payload["repos"][0]["facts"]["implemented"]
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after
