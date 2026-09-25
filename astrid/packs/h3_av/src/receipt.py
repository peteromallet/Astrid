"""Receipts for managed outputs materialized on the local machine."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def write_retrieval_receipt(
    *,
    output_path: Path,
    data: bytes,
    managed_row: Mapping[str, Any],
    task_result: Any,
) -> Path:
    digest = hashlib.sha256(data).hexdigest()
    expected = str(managed_row.get("object_id") or managed_row.get("digest") or "")
    expected = expected.removeprefix("sha256:")
    if digest != expected:
        raise ValueError("cannot receipt a local output whose bytes differ from its managed digest")
    receipt = {
        "schema_version": 1,
        "kind": "h3_av_managed_retrieval",
        "verified": True,
        "managed_object_id": "sha256:" + digest,
        "sha256": digest,
        "size": len(data),
        "local_path": str(output_path.resolve()),
        "filename": output_path.name,
        "task_id": getattr(task_result, "kernel_task_id", None),
        "attempt_id": getattr(task_result, "kernel_attempt_id", None),
        "run_id": getattr(task_result, "kernel_run_id", None),
        "producer_output_id": managed_row.get("producer_output_id"),
    }
    path = output_path.with_name(output_path.name + ".receipt.json")
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


__all__ = ["write_retrieval_receipt"]
