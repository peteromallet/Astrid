"""B9.1 source reconciliation and no-drop coverage."""

import copy
import json
from pathlib import Path

from astrid.core.execution.capability_ledger import load_capability_ledger


def test_shipped_ledger_reconciles_historical_capability_sets():
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    sources = ledger["sources"]

    assert sources["counts"]["pack_labels"] == 94
    assert sources["counts"]["historical_pack_labels"] == 99
    assert sources["counts"]["executor_inventory"] == 90
    assert sources["counts"]["legacy_ids"] == 19
    assert all(section["complete"] for section in sources["coverage"].values())
    assert not sources["coverage"]["source_labels"]["missing"]
    assert sources["coverage"]["historical_source_labels"]["complete"]
    assert not sources["coverage"]["executor_inventory"]["missing"]
    assert not sources["coverage"]["legacy_ids"]["missing"]
    assert not {
        row["pack"]
        for row in sources["pack_labels"]
        if row["pack"] in {"discord_local", "seedance_local"}
    }


def test_ledger_has_only_canonical_ids_models_backends_and_explicit_unmapped_labels():
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    sources = ledger["sources"]

    assert sources["aliases"] == []
    assert sources["models"]
    assert {"local", "cloud"} <= set(sources["generation_backends"])
    assert {row["id"] for row in sources["rendering_backends"]} >= {"rendering.ffmpeg", "rendering.remotion", "rendering.threejs"}
    assert any(row["disposition"] == "unmapped_source_label" for row in sources["pack_labels"])


def test_host_consumes_the_reconciled_ledger_before_readiness_matrix():
    from astrid.core.execution.generic_host import GenericPackHost

    host = GenericPackHost(pack_roots=[Path("astrid/packs")])
    assert host.ledger["sources"]["counts"]["pack_labels"] == 94
    assert len(host.matrix) == 84


def test_vibecomfy_readiness_reserves_gpu_for_workflow_execution():
    from astrid.core.execution.generic_host import GenericPackHost

    host = GenericPackHost(
        pack_roots=[Path("astrid/packs/vibecomfy")],
        capability_matrix=Path("config/astrid-beta-capabilities.json"),
    )
    for capability in (
        "vibecomfy.import",
        "vibecomfy.inspect",
        "vibecomfy.edit",
        "vibecomfy.validate",
    ):
        entry = host.matrix[capability]
        assert entry["adapter_family"] == "cpu"
        assert entry["resource_keys"] == ["cpu"]

    run = host.matrix["vibecomfy.run"]
    assert run["adapter_family"] == "local_generation"
    assert run["resource_keys"] == ["gpu"]


def test_historical_executor_rows_are_explicitly_not_installed():
    """Historical rows must not be mistaken for executable local routes."""
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    rows = ledger["sources"]["executor_inventory"]
    absent = {row["id"]: row for row in rows if row["discovery_status"] != "discovered"}

    assert set(absent) == {
        "iteration.prepare",
        "reigh.open_in_reigh",
        "reigh.publish",
        "reigh.reigh_data",
        "reigh.spatial_audio_page",
        "training.asset_cache",
    }
    external = {row["id"]: row for row in absent.values() if row["id"].split(".", 1)[0] in {"discord_local", "hivemind", "seedance_local"}}
    historical = {row["id"]: row for row in absent.values() if row["id"] not in external}
    assert external == {}
    assert {row["disposition"] for row in historical.values()} == {"retired", "unsupported"}
    assert {row["discovery_status"] for row in historical.values()} == {"historical_only"}
    assert all(row["executable"] is False for row in historical.values())


def test_historical_source_labels_preserve_retirements_and_replacement():
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    rows = {f"{row['pack']}.{row['label']}": row for row in ledger["sources"]["historical_pack_labels"]}

    assert rows["iteration.collect_thread_provenance"]["disposition"] == "replaced"
    assert rows["iteration.collect_thread_provenance"]["equivalent_to"] == "iteration.collect_runtime_provenance"
    assert rows["iteration.collect_thread_provenance"]["executable"] is False
    assert rows["reigh.publish_timeline"]["disposition"] == "unsupported"
    assert rows["typed_timeline.typed_timeline.render"]["disposition"] == "retired"


def test_removed_reigh_registry_is_historical_and_inert():
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    rows = ledger["sources"]["legacy_ids"]

    assert len(rows) == 19
    assert {row["id"] for row in rows} == {
        "reigh.wan_2_2_t2i",
        "reigh.qwen_image",
        "reigh.qwen_image_style",
        "reigh.qwen_image_2512",
        "reigh.z_image_turbo",
        "reigh.image_upscale",
        "reigh.individual_travel_segment",
        "reigh.join_clips_orchestrator",
        "reigh.video_enhance",
        "reigh.z_image_turbo_i2i",
        "reigh.qwen_image_edit",
        "reigh.image_inpaint",
        "reigh.annotated_image_edit",
        "reigh.travel_orchestrator",
        "reigh.wan_2_2_i2v",
        "reigh.travel_stitch",
        "reigh.edit_video_orchestrator",
        "reigh.animate_character",
        "reigh.flux_klein_edit",
    }
    assert {row["disposition"] for row in rows} == {"retired"}
    assert {row["discovery_status"] for row in rows} == {"historical_only"}
    assert all(row["executable"] is False for row in rows)


def test_hivemind_census_keeps_the_external_contract_without_claiming_installation():
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    census = ledger["sources"]["hivemind"]["external_census"]

    assert census == {
        "declared_count": 7,
        "installed_count": 0,
        "unresolved": True,
        "note": "Seven Hivemind executors are declared by the optional external pack; installation is proven by the managed source inventory.",
    }


def test_hivemind_matrix_rows_expose_provider_readiness_metadata():
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    rows = {row["id"]: row for row in ledger["capabilities"] if row["id"].startswith("hivemind.")}
    assert set(rows) == {
        "hivemind.contribute", "hivemind.get_item", "hivemind.ingest_article",
        "hivemind.ingest_workflow", "hivemind.ingest_youtube",
        "hivemind.refresh_media", "hivemind.search",
    }
    for row in rows.values():
        assert row["adapter_family"] == "provider"
        assert row["resource_keys"] == ["provider"]
        assert row["disposition"] == "optional"
    # The public endpoint and anon key have safe baked-in defaults; readiness
    # must not require users to export overrides for read-only access.
    assert rows["hivemind.search"]["required_env"] == []
    assert rows["hivemind.get_item"]["required_env"] == []
    assert "HIVEMIND_CONTRIBUTOR_KEY" in rows["hivemind.contribute"]["required_env"]


def test_source_census_still_rejects_unreviewed_pack_labels(monkeypatch):
    import pytest

    from astrid.core.execution import capability_ledger

    original = capability_ledger._source_labels

    def with_unreviewed_label(repo_root):
        return original(repo_root) + [{
            "pack": "hivemind", "label": "unreviewed", "source": "test",
        }]

    monkeypatch.setattr(capability_ledger, "_source_labels", with_unreviewed_label)
    with pytest.raises(capability_ledger.CapabilityLedgerError, match="identity drifted"):
        load_capability_ledger(Path("config/astrid-beta-capabilities.json"))


def test_source_census_rejects_same_count_label_substitution(monkeypatch):
    import pytest

    from astrid.core.execution import capability_ledger

    original = capability_ledger._source_labels

    def substituted(repo_root):
        rows = original(repo_root)
        rows[-1] = {**rows[-1], "label": "unreviewed_same_count"}
        return rows

    monkeypatch.setattr(capability_ledger, "_source_labels", substituted)
    with pytest.raises(capability_ledger.CapabilityLedgerError, match="identity drifted"):
        load_capability_ledger(Path("config/astrid-beta-capabilities.json"))


def test_source_census_rejects_removed_label(monkeypatch):
    import pytest

    from astrid.core.execution import capability_ledger

    original = capability_ledger._source_labels

    def removed(repo_root):
        return original(repo_root)[:-1]

    monkeypatch.setattr(capability_ledger, "_source_labels", removed)
    with pytest.raises(capability_ledger.CapabilityLedgerError, match="identity drifted"):
        load_capability_ledger(Path("config/astrid-beta-capabilities.json"))


def test_source_census_rejects_duplicate_label_occurrence(monkeypatch):
    import pytest

    from astrid.core.execution import capability_ledger

    original = capability_ledger._source_labels

    def duplicated(repo_root):
        rows = original(repo_root)
        return rows + [dict(rows[-1])]

    monkeypatch.setattr(capability_ledger, "_source_labels", duplicated)
    with pytest.raises(capability_ledger.CapabilityLedgerError, match="identity drifted"):
        load_capability_ledger(Path("config/astrid-beta-capabilities.json"))


def test_source_census_rejects_changed_manifest_bytes(monkeypatch):
    import pytest

    from astrid.core.execution import capability_ledger

    original = capability_ledger._manifest_witnesses

    def altered(repo_root):
        rows = original(repo_root)
        return [{**rows[0], "sha256": "0" * 64}, *rows[1:]]

    monkeypatch.setattr(capability_ledger, "_manifest_witnesses", altered)
    with pytest.raises(capability_ledger.CapabilityLedgerError, match="identity drifted"):
        load_capability_ledger(Path("config/astrid-beta-capabilities.json"))


def test_source_census_rejects_non_external_stale_executor_row(monkeypatch):
    import pytest

    from astrid.core.execution import capability_ledger

    original = capability_ledger._executor_inventory

    def stale(repo_root):
        return original(repo_root) + [{
            "id": "stale.local.executor",
            "result_contract": "manifest",
            "disposition": "historical",
            "source": "test",
        }]

    monkeypatch.setattr(capability_ledger, "_executor_inventory", stale)
    with pytest.raises(capability_ledger.CapabilityLedgerError, match="identity drifted"):
        load_capability_ledger(Path("config/astrid-beta-capabilities.json"))


def test_source_census_rejects_tampered_matrix_baseline_without_regeneration():
    import pytest

    from astrid.core.execution import capability_ledger

    matrix = json.loads(Path("config/astrid-beta-capabilities.json").read_text(encoding="utf-8"))
    tampered = copy.deepcopy(matrix)
    tampered["capabilities"] = [row for row in tampered["capabilities"] if row["id"] != "h3_av.verify"]
    root = Path(".").resolve()
    labels = capability_ledger._source_labels(root)
    current_ids = {row["id"] for row in tampered["capabilities"]}
    for row in labels:
        row["canonical_id"] = f"{row['pack']}.{row['label']}" if f"{row['pack']}.{row['label']}" in current_ids else None
        row["disposition"] = "advertised" if row["canonical_id"] else "unmapped_source_label"
    historical = [
        row for row in labels
        if row["pack"] != "fal" and not (row["pack"] == "iteration" and row["label"] == "collect_runtime_provenance")
    ]
    historical.extend(copy.deepcopy(capability_ledger._HISTORICAL_SOURCE_LABELS))
    historical.sort(key=lambda row: (row["pack"], row["label"]))
    executors = capability_ledger._executor_inventory(root)
    for row in executors:
        if row["id"] in current_ids:
            row["disposition"] = "advertised"
            row["discovery_status"] = "discovered"
        elif row["id"].startswith(("hivemind.", "discord_local.", "seedance_local.")):
            row["disposition"] = "unavailable_external"
            row["discovery_status"] = "not_installed"
            row["reason"] = "optional external pack is not installed in this checkout"
        elif row["disposition"] == "historical":
            row["discovery_status"] = "historical_only"
            row["executable"] = False
    with pytest.raises(capability_ledger.CapabilityLedgerError, match="identity drifted"):
        capability_ledger._validate_source_census(
            root,
            matrix,
            labels=labels,
            historical_labels=historical,
            executors=executors,
            legacy=capability_ledger._legacy_ids(root),
        )


def test_hivemind_matrix_contract_is_not_mistaken_for_bundled_source():
    ledger = load_capability_ledger(Path("config/astrid-beta-capabilities.json"))
    assert not any(row["pack"] == "hivemind" for row in ledger["sources"]["pack_labels"])
    assert ledger["sources"]["hivemind"]["disposition"] == "optional_external"
    assert len(ledger["sources"]["hivemind"]["executor_ids"]) == 7
    matrix_ids = {row["id"] for row in ledger["capabilities"]}
    assert set(ledger["sources"]["hivemind"]["executor_ids"]) <= matrix_ids
