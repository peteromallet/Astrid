"""Run the small public-tool timeline probe loop.

This is intentionally narrower than the full action suite: it launches four
read-only workers over freshly prepared disposable Runtime targets.  The
worker receives the target identifiers in its brief and is told to use the
public timeline surface; it is not asked to read fixture JSON or write a
worker-authored verdict file.  The coordinator owns the trace, before/after
snapshots, and process outcome.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
from pathlib import Path
from typing import Any, Mapping

from .fixture_preparation import PreparedCase, prepare_case
from .local_loop import (
    DEFAULT_MODEL,
    DEFAULT_THINKING,
    _case_child_environment,
    _case_worker_boundary,
    _write_json,
)


PROBES: tuple[dict[str, Any], ...] = (
    {
        "id": "AUDIT_A01",
        "fixture_case_id": "A01",
        "kind": "audit",
        "route": "show",
        "occurrence_keys": ("opening_occurrence",),
        "request": "Use the public timeline show/composition-inspection tool to expand the opening occurrence.",
        "report": "Report its exact head, selected picture, voice, and timing.",
    },
    {
        "id": "AUDIT_A03",
        "fixture_case_id": "A03",
        "kind": "audit",
        "route": "show",
        "occurrence_keys": ("closing_occurrence", "middle_occurrence"),
        "request": "Use the public timeline show/composition-inspection tool to inspect the closing and middle occurrences.",
        "report": "Report their order, starts, durations, and source identities.",
    },
    {
        "id": "VISUAL_A04",
        "fixture_case_id": "A04",
        "kind": "visual",
        "route": "visualize",
        "occurrence_keys": ("feature_occurrence",),
        "request": "Use the public timelines visualize tool in input-only mode for the feature occurrence and its neighbors.",
        "report": "Open the returned visualization artifact and describe the declared arrangement and represented head.",
    },
    {
        "id": "VISUAL_A02",
        "fixture_case_id": "A02",
        "kind": "visual",
        "route": "visualize",
        "occurrence_keys": ("remove_occurrence",),
        "request": "Use the public timelines visualize tool in input-only mode for this short occurrence and its neighbors.",
        "report": "Open the returned visualization artifact and describe the declared arrangement and represented head.",
    },
)


COMMON = (
    "Obtain timeline facts only through the public timeline tools and artifacts they return. "
    "Do not inspect fixture or evaluator JSON, baseline exports, prior results, or other cases. "
    "Do not grep, ripgrep, or search the workspace for answers; do not open any path except "
    "the public documentation named below and paths explicitly returned by the required tool. "
    "Public documentation and tool-returned artifacts are allowed. Execute the required call; "
    "help output, imports, or describing a command does not count. This is read-only: do not "
    "edit, validate, preview for publication, publish, or render. Finish with a brief prose "
    "conclusion, including any limitation."
)


def _brief(probe: Mapping[str, Any], prepared: PreparedCase, doc_path: Path) -> str:
    target = prepared.target or {}
    project_id = str(target.get("project_id") or prepared.project_id or "")
    timeline_id = str(target.get("timeline_id") or prepared.timeline_id or "")
    head = str(target.get("head_revision_id") or "")
    endpoint = str(target.get("endpoint") or prepared.endpoint or "")
    realm_id = str(target.get("realm_id") or prepared.realm_id or "")
    # The disposable seed remaps every fixture identity.  Resolve selectors
    # from the coordinator-owned public task inputs for this fresh case rather
    # than carrying IDs from a previous run into a new Runtime.
    task_inputs_path = prepared.project_dir / "task-inputs.json"
    task_inputs = json.loads(task_inputs_path.read_text(encoding="utf-8"))
    public_inputs = task_inputs.get("task_inputs", {})
    targets = public_inputs.get("targets", {}) if isinstance(public_inputs, Mapping) else {}
    occurrences = ", ".join(
        str(targets.get(key, key)) for key in probe["occurrence_keys"]
    )
    occurrence_id = str(targets.get(probe["occurrence_keys"][0], probe["occurrence_keys"][0]))
    if probe["route"] == "show":
        tool = (
            "Use `AstridClient.open(...)` with the supplied disposable credential and then "
            "`client.timelines.show` or `client.timelines.open_composition` for the exact "
            "project/timeline."
        )
    else:
        tool = (
            "Use the native public Runtime-owned timeline view below with the supplied disposable credential. "
            "Do not rediscover the CLI, inspect source, or search the workspace. Open both returned artifacts.\n\n"
            "```python\n"
            "import os\n"
            "from pathlib import Path\n"
            "from astrid.sdk.client import AstridClient\n"
            "from astrid.sdk.workspace_client import PROTOCOL\n"
            f"with AstridClient.open(endpoint={endpoint!r}, "
            "credential=Path(os.environ['ASTRID_TIMELINE_EVAL_CREDENTIAL']), "
            f"realm_id={realm_id!r}, actor_id='owner', client_name='timeline-probe', "
            "client_version='1', protocol_version=PROTOCOL) as client:\n"
            "    result = client.timelines.visualize(\n"
            f"        {project_id!r}, {timeline_id!r}, occurrence={occurrence_id!r}, neighbors=1,\n"
            "        formats=('md', 'png'),\n"
            "    )\n"
            "print(result.to_dict() if hasattr(result, 'to_dict') else result)\n"
            "```\n"
            "Open the returned `md`, `png`, and `manifest` paths. Never invoke rendering.render or "
            "call `client.close()`; the `with AstridClient.open(...)` context owns cleanup. "
            "The view proves declared arrangement and exact head only; it does not claim source pixels or rendered output."
        )
    return (
        f"# {probe['id']} — {probe['kind']} probe\n\n"
        f"{probe['request']} {probe['report']}\n\n"
        f"Disposable project: `{project_id}`\n"
        f"Timeline: `{timeline_id}`\n"
        f"Pinned head: `{head}`\n"
        f"Realm: `{realm_id}` (actor: `owner`)\n"
        f"Target occurrence(s): `{occurrences}`\n"
        f"Runtime endpoint: `{endpoint}` (use `ASTRID_TIMELINE_EVAL_CREDENTIAL` for the credential)\n\n"
        f"{tool}\n\n"
        f"{COMMON}\n\n"
        f"Documentation: [{doc_path.name}]({doc_path})\n"
    )


def _launch(argv: list[str], cwd: Path, env: Mapping[str, str], timeout: float, trace: Path, log: Path) -> tuple[int | None, str]:
    trace.parent.mkdir(parents=True, exist_ok=True)
    with trace.open("wb") as trace_file, log.open("wb") as log_file:
        process = subprocess.Popen(argv, cwd=cwd, env=dict(env), stdout=trace_file, stderr=log_file, start_new_session=True)
        try:
            return process.wait(timeout=timeout), "completed"
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    process.kill()
            return process.returncode, "timed_out"
        except KeyboardInterrupt:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except OSError:
                process.terminate()
            return process.returncode, "interrupted"


def run_probe_loop(*, attempt_root: Path, fixture_root: Path, canonical_endpoint: str,
                   canonical_realm_id: str, canonical_root: Path, model: str = DEFAULT_MODEL,
                   thinking: str = DEFAULT_THINKING, timeout: float = 600.0) -> dict[str, Any]:
    root = attempt_root.expanduser().absolute()
    if root.exists() and root.is_symlink():
        raise ValueError(f"attempt root must not be a symlink: {root}")
    root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "timeline-editing-guide.md"
    for probe in PROBES:
        case_root = root / "cases" / str(probe["id"])
        work = case_root / "work"
        project = work / "project"
        work.mkdir(parents=True, exist_ok=True)
        trace = case_root / "trace.jsonl"
        log = case_root / "agent.log"
        prepared: PreparedCase | None = None
        record: dict[str, Any] = {
            "case_id": probe["id"], "fixture_case_id": probe["fixture_case_id"],
            "kind": probe["kind"], "route": probe["route"],
            "occurrence_keys": list(probe["occurrence_keys"]),
            "execution": "not_launched", "case_root": str(case_root),
        }
        try:
            prepared = prepare_case(
                str(probe["fixture_case_id"]), case_root=project, fixture_root=fixture_root,
                canonical_endpoint=canonical_endpoint, canonical_realm_id=canonical_realm_id,
                canonical_root=canonical_root,
            )
            before = prepared.baseline_observer()
            _write_json(case_root / "before.json", before)
            (work / "brief.md").write_text(_brief(probe, prepared, doc_path), encoding="utf-8")
            argv = ["omp", "--model", model, "--thinking", thinking, "--no-session", "--mode", "json", "--print", f"@{work / 'brief.md'}"]
            launch_argv, boundary = _case_worker_boundary(
                argv, work=work, attempt_root=root,
                protected_paths=getattr(prepared, "worker_denied_paths", ()),
                public_read_paths=((prepared.credential_file,) if prepared.credential_file else ()),
                canonical_root=canonical_root,
            )
            _write_json(case_root / "worker-boundary.json", boundary)
            _write_json(case_root / "launch.json", {"argv": argv, "cwd": str(work), "model": model, "thinking": thinking, "timeout_seconds": timeout, "probe": probe})
            env = _case_child_environment(prepared)
            returncode, execution = _launch(launch_argv, work, env, timeout, trace, log)
            record.update({"execution": execution if execution != "completed" or returncode == 0 else "launcher_failed", "returncode": returncode})
            if execution == "completed" and returncode != 0:
                record["execution"] = "launcher_failed"
        except KeyboardInterrupt:
            record.update({"execution": "interrupted", "returncode": None})
            records.append(record)
            break
        except Exception as exc:  # preserve setup failures as evidence
            record.update({"execution": "not_launched", "setup_error": f"{type(exc).__name__}: {exc}"})
        finally:
            if prepared is not None:
                try:
                    _write_json(case_root / "after.json", prepared.baseline_observer())
                except Exception as exc:
                    record.setdefault("notes", []).append(f"after capture failed: {type(exc).__name__}: {exc}")
                prepared.close()
        records.append(record)
        _write_json(root / "probe-loop.json", {"kind": "astrid.timeline-eval.public-tool-probes.v1", "automatic_scoring": False, "case_count": len(records), "records": records})
    result = {"kind": "astrid.timeline-eval.public-tool-probes.v1", "automatic_scoring": False, "case_count": len(records), "records": records}
    _write_json(root / "probe-loop.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--canonical-endpoint", required=True)
    parser.add_argument("--canonical-realm-id", required=True)
    parser.add_argument("--canonical-root", type=Path, required=True)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking", default=DEFAULT_THINKING)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    args = parser.parse_args(argv)
    result = run_probe_loop(
        attempt_root=args.attempt_root, fixture_root=args.fixture_root,
        canonical_endpoint=args.canonical_endpoint, canonical_realm_id=args.canonical_realm_id,
        canonical_root=args.canonical_root, model=args.model, thinking=args.thinking,
        timeout=args.timeout_seconds,
    )
    print(json.dumps({"status": "ok", "attempt_root": str(args.attempt_root), "case_count": result["case_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
