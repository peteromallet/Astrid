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
    from vibecomfy.ingest.loader import load_workflow_json
    from vibecomfy.ingest.normalize import from_ui

    raw = load_workflow_json(workflow_path)
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
