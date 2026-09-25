"""Small, explicit lifecycle receipt for one H3 transformation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class ReceiptError(ValueError):
    """A final H3 receipt is incomplete or internally contradictory."""


_STATES = (
    "task_succeeded",
    "candidate_verified",
    "editorially_approved",
    "cleanup_verified",
)


def _evidence(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _stage(status: str, evidence: Mapping[str, Any] | None = None, *, reason: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "evidence": _evidence(evidence)}
    if reason:
        result["reason"] = reason
    return result


def _cleanup_report(value: Mapping[str, Any] | None) -> tuple[dict[str, Any], str]:
    if value is None:
        return {"resources": [], "status": "not_claimed"}, "not_claimed"
    raw_resources = value.get("resources", [])
    if not isinstance(raw_resources, list):
        raise ReceiptError("cleanup.resources must be an array")
    resources: list[dict[str, Any]] = []
    identities: set[tuple[str, str]] = set()
    for index, raw in enumerate(raw_resources):
        if not isinstance(raw, Mapping):
            raise ReceiptError(f"cleanup.resources[{index}] must be an object")
        kind = raw.get("kind")
        resource_id = raw.get("id")
        owned = raw.get("owned")
        expected = raw.get("expected_postcondition")
        observed = raw.get("observed_postcondition")
        verified = raw.get("verified")
        if not all(isinstance(item, str) and item.strip() for item in (kind, resource_id, expected, observed)):
            raise ReceiptError(
                f"cleanup.resources[{index}] requires kind, id, expected_postcondition, and observed_postcondition"
            )
        if type(owned) is not bool or type(verified) is not bool:
            raise ReceiptError(f"cleanup.resources[{index}] owned and verified must be booleans")
        identity = (kind.strip(), resource_id.strip())
        if identity in identities:
            raise ReceiptError(f"cleanup.resources contains duplicate resource {identity!r}")
        identities.add(identity)
        resources.append({
            "kind": identity[0],
            "id": identity[1],
            "owned": owned,
            "expected_postcondition": expected.strip(),
            "observed_postcondition": observed.strip(),
            "verified": verified,
        })
    cleanup_status = "passed" if resources and all(item["verified"] for item in resources) else "failed"
    if not resources:
        cleanup_status = "not_claimed"
    return {"resources": resources, "status": cleanup_status}, cleanup_status


def build_final_receipt(
    *,
    request_digest: str,
    task_succeeded: Mapping[str, Any] | None,
    candidate_verified: Mapping[str, Any] | None,
    editorially_approved: Mapping[str, Any] | None = None,
    cleanup: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a receipt that never conflates execution with approval or cleanup."""
    if not isinstance(request_digest, str) or not request_digest.strip():
        raise ReceiptError("request_digest is required")
    task_status = "passed" if task_succeeded is not None else "failed"
    candidate_status = "passed" if candidate_verified is not None and task_status == "passed" else "failed"
    editorial_status = "passed" if editorially_approved is not None else "not_claimed"
    cleanup_report, cleanup_status = _cleanup_report(cleanup)
    states = {
        "task_succeeded": _stage(task_status, task_succeeded, reason=None if task_succeeded is not None else "task did not settle successfully"),
        "candidate_verified": _stage(candidate_status, candidate_verified, reason=None if candidate_status == "passed" else "candidate verification is unavailable"),
        "editorially_approved": _stage(editorial_status, editorially_approved),
        "cleanup_verified": _stage(cleanup_status, {"resources": cleanup_report["resources"]}),
    }
    overall = "candidate_verified"
    if candidate_status != "passed":
        overall = "task_failed"
    elif editorial_status == "passed" and cleanup_status == "passed":
        overall = "complete"
    return {
        "schema_version": 1,
        "kind": "h3_av_final_receipt",
        "request_digest": request_digest,
        "states": states,
        "cleanup": cleanup_report,
        "overall_status": overall,
    }


def write_final_receipt(path: str | Path, receipt: Mapping[str, Any]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(receipt), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return destination


__all__ = ["ReceiptError", "build_final_receipt", "write_final_receipt"]
