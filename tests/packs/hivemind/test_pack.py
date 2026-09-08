from __future__ import annotations

import json
from pathlib import Path

import yaml

from astrid.core.execution.executor.schema import load_executor_manifest

PACK = Path(__file__).parents[3] / "astrid" / "packs" / "hivemind"


def test_hivemind_pack_exposes_read_only_sdk_executors() -> None:
    manifest = yaml.safe_load((PACK / "pack.yaml").read_text())
    executor_ids = {
        yaml.safe_load(path.read_text())["id"]
        for path in (PACK / "executors").glob("*/executor.yaml")
    }

    assert manifest["id"] == "hivemind"
    assert manifest["status"] == "active"
    assert executor_ids == {
        "hivemind.search",
        "hivemind.get_item",
        "hivemind.refresh_media",
        "hivemind.contribute",
        "hivemind.ingest_article",
        "hivemind.ingest_workflow",
        "hivemind.ingest_youtube",
    }
    assert "network" in {entry["id"] for entry in manifest["permissions"]}


def test_hivemind_read_manifests_declare_optional_project_scope() -> None:
    for executor_id in ("search", "get_item", "refresh_media"):
        definition = load_executor_manifest(
            PACK / "executors" / executor_id / "executor.yaml"
        )
        assert definition.metadata["project_scope"] == "optional"


def test_hivemind_executor_modules_are_pack_qualified() -> None:
    for name in ("search", "get_item", "refresh_media", "contribute", "ingest_article", "ingest_workflow", "ingest_youtube"):
        data = yaml.safe_load((PACK / "executors" / name / "executor.yaml").read_text())
        command = " ".join(data["command"]["argv"])
        assert f"astrid.packs.hivemind.executors.{name}.run" in command
        assert f"astrid.packs.hivemind.executors.{name}.run" in json.dumps(data["metadata"])


def test_hivemind_skill_documents_sdk_and_read_only_boundary() -> None:
    skill = (PACK / "skill" / "SKILL.md").read_text()
    assert 'sdk.invoke(' in skill
    assert '"hivemind.search"' in skill
    assert '"hivemind.get_item"' in skill
    assert "read-only" in skill
