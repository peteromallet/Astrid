from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "config" / "hivemind-pack-contract.json"
DOC = ROOT / "docs" / "reference" / "hivemind-pack-contract.md"


def test_hivemind_v2_contract_covers_reads_and_all_contributor_writers() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))

    assert contract["schema_version"] == 2
    assert contract["pack_id"] == "hivemind"
    assert contract["manifest"]["schema_version"] == 2
    assert contract["public_reads"] == {
        "authentication": "anonymous",
        "environment": ["HIVEMIND_API_URL", "HIVEMIND_ANON_KEY"],
        "capabilities": [
            "hivemind.search",
            "hivemind.get_item",
            "hivemind.refresh_media",
        ],
    }
    assert contract["contributor_writers"]["authentication"] == "HIVEMIND_CONTRIBUTOR_KEY"
    assert contract["contributor_writers"]["resource_backend"] == "contribute"
    assert contract["contributor_writers"]["ingestors_use_same_backend"] is True
    assert contract["rating_writer"] == {
        "endpoint": "submit-vibecomfy-rating",
        "authentication": "HIVEMIND_CONTRIBUTOR_KEY",
        "backend": "hivemind contributor identity and service-role boundary",
        "capability_id": "hivemind.submit_vibecomfy_rating",
    }


def test_hivemind_contract_docs_match_machine_readable_route_names() -> None:
    text = DOC.read_text(encoding="utf-8")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for capability_id in contract["public_reads"]["capabilities"] + contract["contributor_writers"]["capabilities"]:
        assert f"`{capability_id}`" in text
    for operation in contract["contributor_writers"]["operations"]:
        assert operation in text
    assert "submit-vibecomfy-rating" in text
    assert "ASTRID_HIVEMIND_REVISION" in text
    assert "schema_version: 2" in text
