#!/usr/bin/env python3
"""Project-oriented CLI over the canonical AgentBox durable operations store.

Run inside the resident AgentBox container where ``agentbox`` is importable.
The existing ``operation_runs.json`` remains the only authority; PROJECTS.md is
an atomic, generated operator view.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentbox.config import load_agentbox_config
from agentbox.operations import (
    create_agentbox_operation,
    ensure_agentbox_operation,
    list_agentbox_operations,
    load_agentbox_operation,
    open_operation_store,
    update_agentbox_operation,
)


REQUIRED_METADATA = {
    "project_name",
    "host",
    "container",
    "workspace",
    "repo_path",
    "repo_url",
    "branch",
    "base_sha",
    "north_star_digest",
    "normal_model",
    "oracle_model",
    "phase",
    "batch",
    "checkpoint",
    "status_path",
    "log_path",
    "next_action",
    "validation_state",
}

UPDATE_FIELDS = {
    "phase",
    "batch",
    "checkpoint",
    "next_action",
    "validation_state",
    "last_heartbeat",
    "last_receipt",
    "last_evidence",
    "blocker",
    "head_sha",
    "supervisor_state",
    "session",
    "supervisor_path",
    "heartbeat_ttl_minutes",
}


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_payload(run: Any) -> dict[str, Any]:
    return {
        "id": run.id,
        "operation_type": run.operation_type,
        "state": run.state.value,
        "parent_operation_id": run.parent_operation_id,
        "operation_dir": run.operation_dir,
        "retry": {
            "attempt": run.retry.attempt,
            "max_attempts": run.retry.max_attempts,
            "last_error": run.retry.last_error,
        },
        "idempotency_key": run.idempotency_key,
        "metadata": dict(run.metadata),
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "lock_version": run.lock_version,
    }


def load_object(source: str) -> dict[str, Any]:
    raw = json.load(os.fdopen(os.dup(0))) if source == "-" else json.loads(Path(source).read_text())
    if not isinstance(raw, dict):
        raise ValueError("JSON input must be an object")
    return raw


def require_safe_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def register(args: argparse.Namespace) -> None:
    record = load_object(args.record_json)
    allowed = REQUIRED_METADATA | {
        "owner",
        "notes",
        "protected_concurrent_work",
        "session",
        "supervisor_path",
        "heartbeat_ttl_minutes",
    }
    unknown = set(record) - allowed
    missing = REQUIRED_METADATA - set(record)
    if unknown or missing:
        raise ValueError(f"record fields invalid; missing={sorted(missing)} unknown={sorted(unknown)}")
    metadata = {
        key: require_safe_text(value, key) if key not in {"protected_concurrent_work"} else bool(value)
        for key, value in record.items()
    }
    metadata["last_heartbeat"] = now()
    config = load_agentbox_config()
    run = create_agentbox_operation(
        config,
        args.project_id,
        operation_type="agentbox_host",
        command=[
            "docker",
            "exec",
            metadata["container"],
            "tmux",
            "attach",
            "-t",
            args.session,
        ],
        repo_names=[args.repo_name],
        launch_intent="cloud_wrapper_megado",
        launch_state="registered",
        max_attempts=args.max_attempts,
        metadata=metadata,
    )
    print(json.dumps(run_payload(run), indent=2, sort_keys=True))


def update(args: argparse.Namespace) -> None:
    patch = load_object(args.patch_json)
    unknown = set(patch) - UPDATE_FIELDS
    if unknown:
        raise ValueError(f"unknown update fields: {sorted(unknown)}")
    patch = {key: require_safe_text(value, key) for key, value in patch.items()}
    patch["last_heartbeat"] = now()
    run = update_agentbox_operation(
        load_agentbox_config(),
        args.project_id,
        metadata=patch,
        launch_state=args.launch_state,
        state=args.state,
        expected_lock_version=args.expected_lock_version,
    )
    print(json.dumps(run_payload(run), indent=2, sort_keys=True))


def unset_metadata(args: argparse.Namespace) -> None:
    """CAS-delete one optional metadata key without replacing the metadata map."""

    key = require_safe_text(args.key, "key")
    if key not in UPDATE_FIELDS:
        raise ValueError(f"metadata key is not unsettable: {key!r}")

    config = load_agentbox_config()
    current = ensure_agentbox_operation(load_agentbox_operation(config, args.project_id))
    metadata = dict(current.metadata)
    metadata.pop(key, None)
    updated = replace(current, metadata=metadata)
    run = open_operation_store(config).update_operation_run(
        updated,
        expected_lock_version=args.expected_lock_version,
    )
    print(json.dumps(run_payload(run), indent=2, sort_keys=True))


def project_rows() -> list[Any]:
    return [
        run
        for run in list_agentbox_operations(load_agentbox_config())
        if isinstance(run.metadata.get("project_name"), str)
    ]


def render(path: Path) -> None:
    rows = sorted(project_rows(), key=lambda item: (item.updated_at, item.id), reverse=True)
    lines = [
        "# Agentbox project ledger",
        "",
        "Generated from `/workspace/ops/operation_runs.json`.",
        "The durable operations store is authoritative; this file is read-only projection.",
        "Never record credentials or secrets in operation metadata.",
        "",
        "| project | state | phase / batch | container | workspace | branch @ SHA | updated |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for run in rows:
        meta = run.metadata
        values = [
            run.id,
            run.state.value,
            f"{meta.get('phase', '')} / {meta.get('batch', '')}",
            str(meta.get("container", "")),
            str(meta.get("workspace", "")),
            f"{meta.get('branch', '')} @ {meta.get('head_sha') or meta.get('base_sha', '')}",
            run.updated_at,
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|") for value in values) + " |")
    lines.append("")
    for run in rows:
        meta = run.metadata
        lines.extend(
            [
                f"## {run.id}",
                "",
                f"- Project: {meta.get('project_name', '')}",
                f"- State: `{run.state.value}`; phase/batch: `{meta.get('phase', '')}` / `{meta.get('batch', '')}`",
                f"- Container/workspace: `{meta.get('container', '')}` / `{meta.get('workspace', '')}`",
                f"- Repo: `{meta.get('repo_path', '')}`",
                f"- Branch/base/head: `{meta.get('branch', '')}` / `{meta.get('base_sha', '')}` / `{meta.get('head_sha', '')}`",
                f"- Status/log: `{meta.get('status_path', '')}` / `{meta.get('log_path', '')}`",
                f"- Checkpoint: `{meta.get('checkpoint', '')}`",
                f"- Next action: {meta.get('next_action', '')}",
                f"- Validation: `{meta.get('validation_state', '')}`",
                f"- Last receipt/evidence: `{meta.get('last_receipt', '')}` / `{meta.get('last_evidence', '')}`",
                f"- Heartbeat: `{meta.get('last_heartbeat', '')}`",
                f"- Lock version: `{run.lock_version}`",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentbox-project-ledger")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_parser = subparsers.add_parser("register")
    register_parser.add_argument("project_id")
    register_parser.add_argument("--record-json", required=True)
    register_parser.add_argument("--repo-name", required=True)
    register_parser.add_argument("--session", required=True)
    register_parser.add_argument("--max-attempts", type=int, default=20)
    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("project_id")
    update_parser.add_argument("--patch-json", required=True)
    update_parser.add_argument("--expected-lock-version", required=True, type=int)
    update_parser.add_argument("--launch-state")
    update_parser.add_argument(
        "--state",
        choices=["pending", "awaiting_approval", "running", "suspended", "succeeded", "failed", "cancelled"],
    )
    unset_parser = subparsers.add_parser("unset-metadata")
    unset_parser.add_argument("project_id")
    unset_parser.add_argument("--key", required=True)
    unset_parser.add_argument("--expected-lock-version", required=True, type=int)
    subparsers.add_parser("list")
    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("project_id")
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--markdown", type=Path, default=Path("/workspace/ops/PROJECTS.md"))
    args = parser.parse_args()
    if args.command == "register":
        register(args)
    elif args.command == "update":
        update(args)
    elif args.command == "unset-metadata":
        unset_metadata(args)
    elif args.command == "list":
        print(json.dumps([run_payload(run) for run in project_rows()], indent=2, sort_keys=True))
    elif args.command == "show":
        run = load_agentbox_operation(load_agentbox_config(), args.project_id)
        print(json.dumps(run_payload(run), indent=2, sort_keys=True))
    else:
        render(args.markdown)
        print(args.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
