"""Canonical reconciliation of Astrid capability source projections.

Pack manifests and the result-contract snapshot describe the capability
surface. This module joins those projections into one JSON-shaped, read-only
ledger consumed before host readiness is evaluated.
"""

from __future__ import annotations

import json
import hashlib
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from astrid.core.pack.loader import _load_manifest_payload


class CapabilityLedgerError(ValueError):
    """Raised when a capability source cannot be reconciled safely."""


# These rows are deliberately data, not importable capability definitions.  The
# source manifests and the Reigh admission registry were retired, but their
# historical occurrences remain part of the B9 census and must not disappear
# merely because the executable routes were removed.
_HISTORICAL_SOURCE_LABELS: tuple[dict[str, Any], ...] = (
    {
        "pack": "iteration",
        "label": "collect_thread_provenance",
        "source": "historical: astrid/packs/iteration/pack.yaml",
        "canonical_id": "iteration.collect_runtime_provenance",
        "disposition": "replaced",
        "equivalent_to": "iteration.collect_runtime_provenance",
        "executable": False,
        "reason": "Replaced by runtime-owned provenance collection.",
    },
    {
        "pack": "iteration",
        "label": "prepare_iteration",
        "source": "historical: astrid/packs/iteration/pack.yaml",
        "canonical_id": None,
        "disposition": "retired",
        "equivalent_to": None,
        "executable": False,
        "reason": "Retired with the thread/sidecar iteration preparation authority.",
    },
    {
        "pack": "reigh",
        "label": "build_spatial_audio_page",
        "source": "historical: astrid/packs/reigh/pack.yaml",
        "canonical_id": None,
        "disposition": "unsupported",
        "equivalent_to": None,
        "executable": False,
        "reason": "Reigh integration pack is not shipped in the current checkout.",
    },
    {
        "pack": "reigh",
        "label": "fetch_reigh_data",
        "source": "historical: astrid/packs/reigh/pack.yaml",
        "canonical_id": None,
        "disposition": "unsupported",
        "equivalent_to": None,
        "executable": False,
        "reason": "Reigh integration pack is not shipped in the current checkout.",
    },
    {
        "pack": "reigh",
        "label": "open_in_reigh",
        "source": "historical: astrid/packs/reigh/pack.yaml",
        "canonical_id": None,
        "disposition": "unsupported",
        "equivalent_to": None,
        "executable": False,
        "reason": "Reigh bridge authority was retired and is not shipped.",
    },
    {
        "pack": "reigh",
        "label": "publish_timeline",
        "source": "historical: astrid/packs/reigh/pack.yaml",
        "canonical_id": None,
        "disposition": "unsupported",
        "equivalent_to": None,
        "executable": False,
        "reason": "Reigh publishing authority was retired and is not shipped.",
    },
    {
        "pack": "training",
        "label": "manage_asset_cache",
        "source": "historical: astrid/packs/training/pack.yaml",
        "canonical_id": None,
        "disposition": "retired",
        "equivalent_to": None,
        "executable": False,
        "reason": "Retired with the persistent URL asset-cache authority.",
    },
    {
        "pack": "typed_timeline",
        "label": "typed_timeline.render",
        "source": "historical: astrid/packs/typed_timeline/pack.yaml",
        "canonical_id": None,
        "disposition": "retired",
        "equivalent_to": None,
        "executable": False,
        "reason": "Retired typed-timeline render route; rendering is runtime-owned.",
    },
)

# These personal adapters are opt-in project packs.  They may be present in
# an editable checkout, but they are not part of the canonical source census;
# their executor contracts remain represented by the optional matrix rows.
_OPTIONAL_PROJECT_PACK_IDS = frozenset({"discord_local", "seedance_local"})

_HISTORICAL_EXECUTOR_ROWS: tuple[dict[str, Any], ...] = (
    {
        "id": "iteration.prepare",
        "result_contract": "manifest",
        "disposition": "retired",
        "discovery_status": "historical_only",
        "executable": False,
        "reason": "Retired thread/sidecar iteration preparation executor.",
        "source": "historical: astrid/core/contracts/output_result_exemptions.json",
    },
    {
        "id": "reigh.open_in_reigh",
        "result_contract": "exempted",
        "disposition": "unsupported",
        "discovery_status": "historical_only",
        "executable": False,
        "reason": "Retired Reigh bridge executor; external integration is not shipped.",
        "source": "historical: astrid/core/contracts/output_result_exemptions.json",
    },
    {
        "id": "reigh.publish",
        "result_contract": "exempted",
        "disposition": "unsupported",
        "discovery_status": "historical_only",
        "executable": False,
        "reason": "Retired Reigh publishing executor; external integration is not shipped.",
        "source": "historical: astrid/core/contracts/output_result_exemptions.json",
    },
    {
        "id": "reigh.reigh_data",
        "result_contract": "exempted",
        "disposition": "unsupported",
        "discovery_status": "historical_only",
        "executable": False,
        "reason": "Retired Reigh data executor; external integration is not shipped.",
        "source": "historical: astrid/core/contracts/output_result_exemptions.json",
    },
    {
        "id": "reigh.spatial_audio_page",
        "result_contract": "manifest",
        "disposition": "unsupported",
        "discovery_status": "historical_only",
        "executable": False,
        "reason": "Retired Reigh spatial-audio executor; external integration is not shipped.",
        "source": "historical: astrid/core/contracts/output_result_exemptions.json",
    },
    {
        "id": "training.asset_cache",
        "result_contract": "exempted",
        "disposition": "retired",
        "discovery_status": "historical_only",
        "executable": False,
        "reason": "Retired persistent URL asset-cache executor.",
        "source": "historical: astrid/core/contracts/output_result_exemptions.json",
    },
)

_LEGACY_REIGH_IDS: tuple[tuple[str, str], ...] = (
    ("reigh.wan_2_2_t2i", "wgp"),
    ("reigh.qwen_image", "vibecomfy"),
    ("reigh.qwen_image_style", "vibecomfy"),
    ("reigh.qwen_image_2512", "vibecomfy"),
    ("reigh.z_image_turbo", "vibecomfy"),
    ("reigh.image_upscale", "vibecomfy"),
    ("reigh.individual_travel_segment", "wgp"),
    ("reigh.join_clips_orchestrator", "wgp"),
    ("reigh.video_enhance", "vibecomfy"),
    ("reigh.z_image_turbo_i2i", "vibecomfy"),
    ("reigh.qwen_image_edit", "vibecomfy"),
    ("reigh.image_inpaint", "vibecomfy"),
    ("reigh.annotated_image_edit", "vibecomfy"),
    ("reigh.travel_orchestrator", "wgp"),
    ("reigh.wan_2_2_i2v", "wgp"),
    ("reigh.travel_stitch", "wgp"),
    ("reigh.edit_video_orchestrator", "wgp"),
    ("reigh.animate_character", "vibecomfy"),
    ("reigh.flux_klein_edit", "vibecomfy"),
)

_CENSUS_SCHEMA_VERSION = 1
_H3_LABEL_BINDINGS: tuple[dict[str, str], ...] = (
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
)


def _repo_root_for_matrix(path: Path) -> Path | None:
    candidate = path.expanduser().resolve().parent.parent
    return candidate if (candidate / "astrid" / "packs").is_dir() else None


def _source_labels(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest in sorted((repo_root / "astrid" / "packs").glob("*/pack.yaml")):
        if manifest.parent.name in _OPTIONAL_PROJECT_PACK_IDS:
            continue
        raw = _load_manifest_payload(manifest)
        labels = raw.get("capabilities", []) if isinstance(raw, Mapping) else []
        if not isinstance(labels, list):
            raise CapabilityLedgerError(f"{manifest}: capabilities must be a list")
        for label in labels:
            if not isinstance(label, str) or not label.strip():
                raise CapabilityLedgerError(f"{manifest}: capability labels must be non-empty strings")
            rows.append({"pack": manifest.parent.name, "label": label, "source": str(manifest.relative_to(repo_root))})
    return rows


def _aliases(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for manifest in sorted((repo_root / "astrid" / "packs").glob("*/pack.yaml")):
        raw = _load_manifest_payload(manifest)
        aliases = raw.get("aliases", []) if isinstance(raw, Mapping) else []
        if not isinstance(aliases, list):
            raise CapabilityLedgerError(f"{manifest}: aliases must be a list")
        for alias in aliases:
            if not isinstance(alias, Mapping) or not {"alias", "canonical_id"} <= set(alias):
                raise CapabilityLedgerError(f"{manifest}: alias entry missing alias/canonical_id")
            rows.append({
                "pack": manifest.parent.name,
                "kind": str(alias.get("kind", "executor")),
                "alias": str(alias["alias"]),
                "canonical_id": str(alias["canonical_id"]),
                "deprecated": bool(alias.get("deprecated", False)),
                "deprecation_message": str(alias.get("deprecation_message", "")),
                "source": str(manifest.relative_to(repo_root)),
            })
    return rows


def _executor_inventory(repo_root: Path) -> list[dict[str, Any]]:
    source = repo_root / "astrid" / "core" / "contracts" / "output_result_exemptions.json"
    payload = json.loads(source.read_text(encoding="utf-8"))
    non_exempt = payload.get("non_exempt", [])
    exemptions = payload.get("exemptions", {})
    if not isinstance(non_exempt, list) or not isinstance(exemptions, Mapping):
        raise CapabilityLedgerError(f"{source}: invalid executor snapshot")
    rows: list[dict[str, Any]] = []
    for capability_id in sorted(set(str(value) for value in non_exempt)):
        rows.append({"id": capability_id, "result_contract": "manifest", "disposition": "historical", "source": str(source.relative_to(repo_root))})
    for capability_id, detail in sorted(exemptions.items()):
        detail = detail if isinstance(detail, Mapping) else {}
        rows.append({
            "id": str(capability_id),
            "result_contract": "exempted",
            "disposition": "historical",
            "reason": str(detail.get("note", "")),
            "source": str(source.relative_to(repo_root)),
        })
    rows.extend(dict(row) for row in _HISTORICAL_EXECUTOR_ROWS if row["id"] not in {item["id"] for item in rows})
    return rows


def _legacy_ids(repo_root: Path) -> list[dict[str, Any]]:
    """Return the exact pre-cutover Reigh registry as inert historical data."""
    source = "historical: astrid/core/integrations/reigh/capabilities.py"
    return [
        {
            "id": capability_id,
            "binding": binding,
            "disposition": "retired",
            "discovery_status": "historical_only",
            "executable": False,
            "source": source,
            "reason": "Removed legacy Reigh registry entry; retained for census only.",
        }
        for capability_id, binding in _LEGACY_REIGH_IDS
    ]


def _model_inventory(repo_root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    source = repo_root / "astrid" / "core" / "model_catalog" / "models.yaml"
    raw = _load_manifest_payload(source)
    models = raw.get("models", []) if isinstance(raw, Mapping) else []
    rows: list[dict[str, Any]] = []
    backends: set[str] = set()
    for model in models:
        if not isinstance(model, Mapping) or not model.get("id"):
            continue
        model_backends: set[str] = set()
        for mode in (model.get("modes", {}) or {}).values():
            if isinstance(mode, Mapping) and isinstance(mode.get("backends", {}), Mapping):
                model_backends.update(str(value) for value in mode["backends"])
        backends.update(model_backends)
        rows.append({"id": str(model["id"]), "backends": sorted(model_backends), "source": str(source.relative_to(repo_root))})
    return rows, sorted(backends)


def _render_backend_inventory(repo_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    root = repo_root / "astrid" / "packs" / "rendering" / "backends"
    for source in sorted(root.glob("*/renderer.yaml")):
        raw = _load_manifest_payload(source)
        if isinstance(raw, Mapping) and raw.get("id"):
            rows.append({"id": str(raw["id"]), "required_binaries": [str(value) for value in (raw.get("required_binaries") or [])], "source": str(source.relative_to(repo_root))})
    return rows


def _provider_inventory(capabilities: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    providers: dict[str, set[str]] = {}
    for row in capabilities:
        if row.get("adapter_family") != "provider":
            continue
        for name in row.get("required_env", ()) or ():
            providers.setdefault(str(name), set()).add(str(row.get("id", "")))
    return [{"credential": key, "capabilities": sorted(value)} for key, value in sorted(providers.items())]


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _row_counter(rows: list[Mapping[str, Any]]) -> Counter[bytes]:
    return Counter(_canonical_json_bytes(dict(row)) for row in rows)


def _row_delta(expected: list[Mapping[str, Any]], actual: list[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    expected_counter = _row_counter(expected)
    actual_counter = _row_counter(actual)
    missing: list[dict[str, Any]] = []
    unexpected: list[dict[str, Any]] = []
    expected_by_bytes = {_canonical_json_bytes(dict(row)): dict(row) for row in expected}
    actual_by_bytes = {_canonical_json_bytes(dict(row)): dict(row) for row in actual}
    for encoded, count in (expected_counter - actual_counter).items():
        missing.extend([expected_by_bytes[encoded]] * count)
    for encoded, count in (actual_counter - expected_counter).items():
        unexpected.extend([actual_by_bytes[encoded]] * count)
    return {"missing": missing, "unexpected": unexpected}


def _matrix_inventory(capabilities: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in capabilities:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str) or not row["id"]:
            raise CapabilityLedgerError("capability matrix rows require a non-empty string id")
        capability_id = str(row["id"])
        if capability_id in seen:
            raise CapabilityLedgerError(f"capability matrix contains duplicate id {capability_id!r}")
        seen.add(capability_id)
        rows.append(dict(row))
    return sorted(rows, key=lambda item: str(item["id"]))


def _manifest_witnesses(repo_root: Path) -> list[dict[str, str]]:
    manifests = [
        manifest
        for manifest in sorted((repo_root / "astrid" / "packs").glob("*/pack.yaml"))
        if manifest.parent.name not in _OPTIONAL_PROJECT_PACK_IDS
    ]
    manifests.extend(
        repo_root / relative
        for relative in (
            "astrid/packs/h3_av/executors/prepare/executor.yaml",
            "astrid/packs/h3_av/executors/compile/executor.yaml",
            "astrid/packs/h3_av/executors/compose/executor.yaml",
            "astrid/packs/h3_av/executors/verify/executor.yaml",
            "astrid/packs/h3_av/orchestrators/transform/orchestrator.yaml",
        )
    )
    rows: list[dict[str, str]] = []
    for manifest in sorted(set(manifests)):
        if not manifest.is_file():
            raise CapabilityLedgerError(f"sealed capability manifest is missing: {manifest}")
        rows.append({
            "path": str(manifest.relative_to(repo_root)),
            "sha256": _sha256_bytes(manifest.read_bytes()),
        })
    return rows


def _label_bindings(repo_root: Path) -> list[dict[str, str]]:
    rows = [dict(row) for row in _H3_LABEL_BINDINGS]
    for row in rows:
        manifest = repo_root / row["manifest"]
        if not manifest.is_file():
            raise CapabilityLedgerError(f"reviewed H3 label binding manifest is missing: {manifest}")
        payload = _load_manifest_payload(manifest)
        if payload.get("id") != row["canonical_id"]:
            raise CapabilityLedgerError(
                f"reviewed H3 label binding {row['label']!r} points to {row['canonical_id']!r}, "
                f"but {manifest} declares {payload.get('id')!r}"
            )
    return rows


def _census_content(
    repo_root: Path,
    *,
    labels: list[dict[str, Any]],
    historical_labels: list[dict[str, Any]],
    executors: list[dict[str, Any]],
    legacy: list[dict[str, Any]],
    capabilities: list[Mapping[str, Any]],
) -> dict[str, Any]:
    snapshot = repo_root / "astrid" / "core" / "contracts" / "output_result_exemptions.json"
    return {
        "schema_version": _CENSUS_SCHEMA_VERSION,
        "pack_labels": sorted((dict(row) for row in labels), key=lambda row: (row["source"], row["pack"], row["label"])),
        "historical_pack_labels": sorted((dict(row) for row in historical_labels), key=lambda row: (row["pack"], row["label"], row["source"])),
        "executor_inventory": sorted((dict(row) for row in executors), key=lambda row: row["id"]),
        "legacy_ids": sorted((dict(row) for row in legacy), key=lambda row: row["id"]),
        "matrix_inventory": _matrix_inventory(capabilities),
        "manifest_witnesses": _manifest_witnesses(repo_root),
        "result_contract_snapshot": {
            "path": str(snapshot.relative_to(repo_root)),
            "sha256": _sha256_bytes(snapshot.read_bytes()),
        },
        "label_bindings": _label_bindings(repo_root),
    }


def _validate_source_census(
    repo_root: Path,
    payload: Mapping[str, Any],
    *,
    labels: list[dict[str, Any]],
    historical_labels: list[dict[str, Any]],
    executors: list[dict[str, Any]],
    legacy: list[dict[str, Any]],
) -> None:
    census = payload.get("source_census")
    if not isinstance(census, Mapping) or census.get("schema_version") != _CENSUS_SCHEMA_VERSION:
        raise CapabilityLedgerError("capability matrix requires versioned source_census schema_version 1")
    expected_content = {str(key): value for key, value in census.items() if key != "content_sha256"}
    digest = census.get("content_sha256")
    if not isinstance(digest, str) or digest != _sha256_bytes(_canonical_json_bytes(expected_content)):
        raise CapabilityLedgerError("capability source census content digest is invalid")
    actual_content = _census_content(
        repo_root,
        labels=labels,
        historical_labels=historical_labels,
        executors=executors,
        legacy=legacy,
        capabilities=payload["capabilities"],
    )
    if actual_content != expected_content:
        changed = [key for key in sorted(set(actual_content) | set(expected_content)) if actual_content.get(key) != expected_content.get(key)]
        raise CapabilityLedgerError(f"capability source census identity drifted: sections={changed}")


def _reconcile_sources(
    repo_root: Path,
    capabilities: list[Mapping[str, Any]],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    labels = _source_labels(repo_root)
    # Keep current manifests distinct from the historical projection.  The
    # latter includes retired source occurrences, while Fal's two current
    # labels remain outside the non-Fal historical census.
    historical_labels = [
        row
        for row in labels
        if row["pack"] != "fal"
        and not (
            row["pack"] == "iteration"
            and row["label"] == "collect_runtime_provenance"
        )
    ]
    historical_labels.extend(dict(row) for row in _HISTORICAL_SOURCE_LABELS)
    historical_labels.sort(key=lambda row: (row["pack"], row["label"]))
    aliases = _aliases(repo_root)
    executors = _executor_inventory(repo_root)
    legacy = _legacy_ids(repo_root)
    models, model_backends = _model_inventory(repo_root)
    rendering_backends = _render_backend_inventory(repo_root)
    current_ids = {str(row.get("id")) for row in capabilities}
    for row in labels:
        candidate = f"{row['pack']}.{row['label']}"
        row["canonical_id"] = candidate if candidate in current_ids else None
        row["disposition"] = "advertised" if row["canonical_id"] else "unmapped_source_label"
    for row in executors:
        if row["id"] in current_ids:
            row["disposition"] = "advertised"
            row["discovery_status"] = "discovered"
        elif row["id"].startswith(("hivemind.", "discord_local.", "seedance_local.")):
            # These IDs remain in the result-contract inventory. If their
            # shipped/explicit pack is absent, keep them visible without
            # making an unavailable external route look executable.
            row["disposition"] = "unavailable_external"
            row["discovery_status"] = "not_installed"
            row["reason"] = "optional external pack is not installed in this checkout"
        elif row["id"] in current_ids:
            row["disposition"] = "advertised"
            row["discovery_status"] = "discovered"
        elif row["disposition"] == "historical":
            row["reason"] = row.get("reason") or "retained in historical executor snapshot; no current executor manifest"
            row["discovery_status"] = "historical_only"
    for row in executors:
        if row.get("discovery_status") != "discovered":
            row.setdefault("executable", False)
    expected_hivemind = sorted(row["id"] for row in executors if row["id"].startswith("hivemind."))
    _validate_source_census(
        repo_root,
        payload,
        labels=labels,
        historical_labels=historical_labels,
        executors=executors,
        legacy=legacy,
    )
    census = payload["source_census"]
    expected_rows = {
        "source_labels": census["pack_labels"],
        "historical_source_labels": census["historical_pack_labels"],
        "executor_inventory": census["executor_inventory"],
        "legacy_ids": census["legacy_ids"],
    }
    actual_rows = {
        "source_labels": labels,
        "historical_source_labels": historical_labels,
        "executor_inventory": executors,
        "legacy_ids": legacy,
    }
    coverage = {
        section: {
            "source": len(expected_rows[section]),
            "ledger": len(actual_rows[section]),
            **_row_delta(expected_rows[section], actual_rows[section]),
            "complete": not _row_delta(expected_rows[section], actual_rows[section])["missing"]
            and not _row_delta(expected_rows[section], actual_rows[section])["unexpected"],
        }
        for section in expected_rows
    }
    if not all(section["complete"] for section in coverage.values()):
        raise CapabilityLedgerError(f"capability source census drifted: {coverage}")
    return {
        "pack_labels": labels,
        "historical_pack_labels": historical_labels,
        "aliases": aliases,
        "executor_inventory": executors,
        "legacy_ids": legacy,
        "providers": _provider_inventory(capabilities),
        "models": models,
        "generation_backends": model_backends,
        "rendering_backends": rendering_backends,
        "hivemind": {
            "disposition": "optional_external",
            "executor_ids": expected_hivemind,
            "external_census": {
                "declared_count": 7,
                "installed_count": 0,
                "unresolved": True,
                "note": "Seven Hivemind executors are declared by the optional external pack; installation is proven by the managed source inventory."
                if len(expected_hivemind) == 7
                else "Historical Hivemind contract is incomplete; no additional ID is guessed.",
            },
        },
        "coverage": coverage,
        "counts": {"pack_labels": len(labels), "historical_pack_labels": len(historical_labels), "executor_inventory": len(executors), "legacy_ids": len(legacy), "aliases": len(aliases), "models": len(models), "rendering_backends": len(rendering_backends)},
    }


def load_capability_ledger(matrix_path: str | Path) -> dict[str, Any]:
    """Load the readiness matrix and reconcile all shipped capability sources."""
    path = Path(matrix_path).expanduser().resolve()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CapabilityLedgerError(f"cannot read capability ledger {path}: {exc}") from exc
    if not isinstance(payload, Mapping) or payload.get("schema_version") != 1 or not isinstance(payload.get("capabilities"), list):
        raise CapabilityLedgerError("capability ledger requires schema_version 1 and a capabilities list")
    result = dict(payload)
    repo_root = _repo_root_for_matrix(path)
    result["sources"] = _reconcile_sources(repo_root, payload["capabilities"], payload) if repo_root else {"counts": {}, "coverage": {}}
    return result


__all__ = ["CapabilityLedgerError", "load_capability_ledger"]
