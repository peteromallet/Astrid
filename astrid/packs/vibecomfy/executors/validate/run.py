"""Runtime entrypoint for VibeComfy validation and execution."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from astrid.core.pack.entrypoint import guard_canonical_entrypoint

guard_canonical_entrypoint("vibecomfy.validate")

from astrid.core.cli_choices import add_choice_arg  # noqa: E402
from astrid.packs.vibecomfy.executors._bundle_inputs import (  # noqa: E402
    staged_workflow_path,
)
from astrid.packs.vibecomfy.executors._python_execution_consent import (  # noqa: E402
    PythonExecutionConsentError,
    validate_python_execution_consent,
)


class WorkflowValidationError(ValueError):
    """A VibeComfy workflow could not be validated."""


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise WorkflowValidationError(f"workflow JSON contains duplicate key {key!r}")
        value[key] = item
    return value


def _load_validation_json(workflow_path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(
            workflow_path.read_text(encoding="utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowValidationError(f"workflow is not valid UTF-8 JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowValidationError("workflow JSON must be an object")
    return raw


def _validation_format(raw: dict[str, Any]) -> str:
    """Select an admitted JSON format without permitting envelope fallback."""
    nodes = raw.get("nodes")
    envelope_markers = {
        "vibecomfy_format_version",
        "edges",
        "compiled_api",
    }
    has_envelope_markers = bool(envelope_markers.intersection(raw))
    if "vibecomfy_format_version" in raw:
        if nodes is None or isinstance(nodes, list):
            raise WorkflowValidationError("ambiguous VibeWorkflow envelope/UI JSON")
        if raw.get("vibecomfy_format_version") != "1.0":
            raise WorkflowValidationError("unsupported VibeWorkflow envelope version")
        if not isinstance(nodes, dict) or not isinstance(raw.get("edges"), list):
            raise WorkflowValidationError("malformed VibeWorkflow envelope structure")
        return "envelope"
    if has_envelope_markers:
        raise WorkflowValidationError("unversioned or ambiguous graph envelope JSON")
    if isinstance(nodes, list):
        return "ui"
    raise WorkflowValidationError("workflow JSON is neither a UI graph nor a VibeWorkflow envelope")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run VibeComfy workflow commands.")
    add_choice_arg(parser, "command", values=("run", "validate"))
    parser.add_argument("workflow", nargs="?", default="")
    parser.add_argument("--python", default="")
    parser.add_argument("--companion", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--python-execution-consent", default="")
    parser.add_argument("--out", type=Path)
    return parser


def _static_ui_validation(workflow_path: Path) -> dict[str, Any]:
    """Validate UI JSON through VibeComfy's static ingestion and IR checks."""
    from vibecomfy.ingest.normalize import from_ui

    raw = _load_validation_json(workflow_path)
    if _validation_format(raw) != "ui":
        raise WorkflowValidationError("workflow JSON is not an unambiguous UI graph")
    workflow = from_ui(
        raw,
        source_path=str(workflow_path),
        use_comfy_converter=False,
    )
    report = workflow.validate()
    return {
        "schema_version": 1,
        "authority": "input_ui_graph",
        "validation_mode": "static_ui_graph",
        "workflow_id": workflow.id,
        "status": "ok" if report.ok else "error",
        "ok": report.ok,
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity,
                "detail": issue.detail or {},
            }
            for issue in report.issues
        ],
        "python_execution_consent": None,
        "security_gate_audit": [],
    }


def _envelope_validation(workflow_path: Path) -> dict[str, Any]:
    """Validate a versioned VibeWorkflow envelope without executing it."""
    from vibecomfy.ingest.normalize import from_envelope

    raw = _load_validation_json(workflow_path)
    if _validation_format(raw) != "envelope":
        raise WorkflowValidationError("workflow JSON is not a VibeWorkflow envelope")
    try:
        workflow = from_envelope(raw)
        if workflow.id != raw.get("id"):
            raise WorkflowValidationError("VibeWorkflow identity does not match its envelope")
        if workflow.to_envelope() != raw:
            raise WorkflowValidationError("VibeWorkflow envelope failed exact round-trip validation")
        report = workflow.validate()
        if "compiled_api" in raw:
            embedded_api = raw["compiled_api"]
            if not isinstance(embedded_api, dict) or workflow.compile("api") != embedded_api:
                raise WorkflowValidationError(
                    "stored compiled_api does not match the graph-derived API projection"
                )
    except WorkflowValidationError:
        raise
    except Exception as exc:
        raise WorkflowValidationError(f"VibeWorkflow envelope validation failed: {exc}") from exc
    return {
        "schema_version": 1,
        "authority": "vibeworkflow_envelope",
        "validation_mode": "static_vibeworkflow_envelope",
        "workflow_id": workflow.id,
        "status": "ok" if report.ok else "error",
        "ok": report.ok,
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity,
                "detail": issue.detail or {},
            }
            for issue in report.issues
        ],
        "python_execution_consent": None,
        "security_gate_audit": [],
    }


def _canonical_bundle_validation(
    workflow_path: Path,
    *,
    python_execution_consent: str | None,
) -> dict[str, Any]:
    validate_python_execution_consent(python_execution_consent)
    from vibecomfy.cli import main as vibecomfy_main
    from vibecomfy.security import current_gate_context, set_gate_context

    previous_gate = current_gate_context()
    captured_stdout = StringIO()
    captured_stderr = StringIO()
    try:
        with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
            return_code = vibecomfy_main(
                ["--yes", "--quiet", "validate", str(workflow_path), "--json"]
            )
        gate = current_gate_context()
        audit = list(gate.audit)
    except SystemExit as exc:
        gate = current_gate_context()
        audit = list(gate.audit)
        return_code = int(exc.code or 0)
    finally:
        set_gate_context(previous_gate)

    raw_payload = captured_stdout.getvalue().strip()
    if return_code != 0:
        message = captured_stderr.getvalue().strip() or raw_payload or "VibeComfy returned an error"
        raise WorkflowValidationError(f"VibeComfy rejected the canonical bundle: {message}")
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise WorkflowValidationError(
            f"VibeComfy returned invalid JSON validation output: {raw_payload[:500]}"
        ) from exc
    if not isinstance(payload, dict):
        raise WorkflowValidationError("VibeComfy validation output must be a JSON object")
    payload.update(
        {
            "schema_version": 1,
            "authority": "canonical_workflow_bundle",
            "validation_mode": "canonical_bundle",
            "python_execution_consent": "confirmed",
            "security_gate_audit": audit,
        }
    )
    return payload


def _write_report(out_dir: Path, report: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "validation-report.json"
    try:
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False, default=str)
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise WorkflowValidationError(f"could not publish validation report: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        with staged_workflow_path(
            workflow=args.workflow,
            python=args.python,
            companion=args.companion,
            source=args.source,
        ) as (workflow_path, authority):
            if args.command == "run":
                return subprocess.run(
                    [sys.executable, "-m", "vibecomfy.cli", "run", str(workflow_path)]
                ).returncode

            if args.out is None:
                raise WorkflowValidationError("--out is required for validation")
            if authority == "canonical_bundle":
                report = _canonical_bundle_validation(
                    workflow_path,
                    python_execution_consent=args.python_execution_consent,
                )
            else:
                validate_python_execution_consent(
                    args.python_execution_consent,
                    required=False,
                )
                raw = _load_validation_json(workflow_path)
                validation_format = _validation_format(raw)
                if validation_format == "envelope":
                    report = _envelope_validation(workflow_path)
                else:
                    report = _static_ui_validation(workflow_path)
                report["python_execution_consent"] = (
                    "confirmed" if args.python_execution_consent == "confirmed" else None
                )
            _write_report(args.out, report)
            if not report.get("ok", report.get("status") == "ok"):
                raise WorkflowValidationError("workflow validation reported errors")
    except (PythonExecutionConsentError, WorkflowValidationError, ValueError) as exc:
        print(f"vibecomfy.validate: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
