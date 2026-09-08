from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from astrid.packs.hivemind.executors.get_item import run


def test_message_retrieval_preserves_snowflake_and_avoids_unified_scan(monkeypatch, tmp_path):
    snowflake = "1546475342703890513"
    calls = []

    def get(table, *, params, **kwargs):
        calls.append((table, params))
        if table == "message_feed":
            assert params["message_id"] == "eq." + snowflake
            assert params["select"] != "*"
            return [{"message_id": int(snowflake), "content": "Full dialogue evidence", "author_name": "Example",
                     "channel_name": "minimax_h3_chatter", "channel_id": 42, "guild_id": 99,
                     "created_at": "2026-09-08T00:00:00Z"}]
        assert table == "distillation_cites"
        return []

    monkeypatch.setattr(run, "postgrest_get", get)
    output = tmp_path / "item.json"
    assert run.main(["--kind", "message", "--id", snowflake, "--out", str(output)]) == 0
    payload = json.loads(output.read_text())
    assert payload["item"]["item_id"] == snowflake
    assert payload["item"]["body"] == "Full dialogue evidence"
    assert payload["item"]["url"] == f"https://discord.com/channels/99/42/{snowflake}"
    assert payload["cited_by"] == []
    manifest = yaml.safe_load((Path(run.__file__).parent / "executor.yaml").read_text())
    assert next(port for port in manifest["inputs"] if port["name"] == "id")["type"] == "string"


@pytest.mark.parametrize("kind", ["resource", "distillation"])
def test_nonmessage_retrieval_uses_narrow_projection(monkeypatch, kind):
    def get(table, *, params, **kwargs):
        assert table == "unified_feed"
        assert params["select"] == "kind,source,item_id,title,body,author,context,url,created_at"
        assert params["item_id"] == "eq.42"
        return []

    monkeypatch.setattr(run, "postgrest_get", get)
    assert run._fetch_row(kind, 42, endpoint="unused", anon_key="public") is None
