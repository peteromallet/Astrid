"""Run timeline evaluation cases sequentially with one fresh OMP process each.

This is a small execution/evidence loop, not a grader. It does not use fixture
readiness as an admission gate and never assigns a score. A case is recorded as
completed when OMP exits successfully; an absent or malformed optional worker
``result.json`` is retained as a reporting defect rather than a semantic result.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .fixture_manifest import DEFAULT_FIXTURE_ROOT
from .fixture_preparation import PreparedCase, prepare_case, render_case_brief
from .run import load_json

LOOP_KIND = "astrid.timeline-eval.local-manual-loop.v1"
DEFAULT_MODEL = "openai-codex/gpt-5.6-luna"
DEFAULT_THINKING = "high"
DEFAULT_TIMEOUT_SECONDS = 600.0
EXECUTION_STATUSES = frozenset({
    "not_launched", "completed", "timed_out", "interrupted", "launcher_failed",
})
TASK_OUTCOMES = frozenset({"completed", "partial", "failed", "not_assessed"})
EVIDENCE_STATUSES = frozenset({"sufficient", "insufficient", "unavailable", "not_collected"})
SAFETY_STATUSES = frozenset({"supported", "violation", "unknown"})
MANUAL_REVIEW_STATUSES = frozenset({"pass", "fail", "undetermined"})


@dataclass(frozen=True)
class ManualCaseRecord:
    case_id: str
    kind: str
    execution: str
    task_outcome: str
    manual_review: str
    evidence_sufficiency: str
    safety: str
    case_root: str
    transcript: str | None
    trace: str | None
    result: str | None
    returncode: int | None
    setup_error: str | None
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.execution not in EXECUTION_STATUSES:
            raise ValueError(f"invalid execution status: {self.execution}")
        if self.task_outcome not in TASK_OUTCOMES:
            raise ValueError(f"invalid task outcome: {self.task_outcome}")
        if self.manual_review not in MANUAL_REVIEW_STATUSES:
            raise ValueError(f"invalid manual review: {self.manual_review}")
        if self.evidence_sufficiency not in EVIDENCE_STATUSES:
            raise ValueError(f"invalid evidence status: {self.evidence_sufficiency}")
        if self.safety not in SAFETY_STATUSES:
            raise ValueError(f"invalid safety status: {self.safety}")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ProcessResult:
    returncode: int | None
    timed_out: bool = False
    interrupted: bool = False
    started: bool = True


ProcessLauncher = Callable[[Sequence[str], Path, float, Path, Path], ProcessResult]


class WorkerBoundaryUnavailable(RuntimeError):
    """The real local worker cannot be launched with filesystem isolation."""

_AMBIENT_RUNTIME_BLOCK_FRAGMENTS = (
    "ASTRID_RUNTIME", "ASTRID_CANONICAL", "RUNTIME_CREDENTIAL",
    "RUNTIME_TOKEN", "SUPABASE_SERVICE", "SUPABASE_SECRET",
)


def _case_child_environment(prepared: PreparedCase) -> dict[str, str]:
    """Remove ambient Runtime inputs and add this case's live connection.

    Navigation cases also get a disposable Runtime during coordinator
    preparation (the worker may need to inspect that target), so endpoint and
    credential injection is deliberately not conditional on the public task
    kind.  Refusing a prepared case without both values keeps a live worker
    from silently falling back to ambient credentials.
    """
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith("ASTRID_TIMELINE_EVAL_")
        and not any(fragment in key.upper() for fragment in _AMBIENT_RUNTIME_BLOCK_FRAGMENTS)
    }
    if not prepared.endpoint or not prepared.credential_file:
        raise ValueError("prepared case has no explicit Runtime endpoint and credential")
    env["ASTRID_TIMELINE_EVAL_ENDPOINT"] = prepared.endpoint
    env["ASTRID_TIMELINE_EVAL_CREDENTIAL"] = str(prepared.credential_file)
    source_root = Path(__file__).resolve().parents[2]
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        str(source_root)
        if not existing_pythonpath
        else os.pathsep.join((str(source_root), existing_pythonpath))
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _sandbox_quote(value: Path) -> str:
    return str(value.resolve()).replace("\\", "\\\\").replace('"', '\\"')


def _case_worker_boundary(
    argv: Sequence[str], *, work: Path, attempt_root: Path,
    protected_paths: Sequence[Path] = (),
    public_read_paths: Sequence[Path] = (),
    canonical_root: Path | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Wrap one worker in the current Mac's filesystem policy.

    The worker retains ordinary host/tool reads and its selected case package,
    plus the checkout's public ``astrid`` package and docs. The attempt
    coordinator tree, sibling cases, evaluator sources, canonical roots, and
    Runtime backing stores are policy-denied. Explicit public read paths (the
    disposable credential) are re-opened after their parent store is denied.
    """

    if sys.platform != "darwin":
        raise WorkerBoundaryUnavailable(
            "timeline local execution requires the current macOS sandbox-exec boundary"
        )
    sandbox = shutil.which("sandbox-exec")
    if not sandbox:
        raise WorkerBoundaryUnavailable("timeline local execution requires sandbox-exec")

    source_root = Path(__file__).resolve().parents[2]
    private_evidence_root = source_root.parent / ".otto"
    private_checkout_root = source_root / ".otto"
    explicit_canonical = canonical_root.resolve() if canonical_root else None
    canonical_store_paths = () if explicit_canonical is None else (
        explicit_canonical / "credentials",
        explicit_canonical / "support" / "credentials",
    )
    credential_store_paths = tuple(path.expanduser().absolute().parent for path in public_read_paths)
    storage_denials = tuple(dict.fromkeys(path.resolve() for path in (
        *protected_paths, *credential_store_paths,
    )))
    protected_reads = tuple(dict.fromkeys(path.resolve() for path in (
        attempt_root,
        private_evidence_root,
        private_checkout_root,
        source_root / "evals",
        source_root / "tests" / "evals",
        source_root / ".git",
        *(path for path in (explicit_canonical, *canonical_store_paths) if path is not None),
        *storage_denials,
    )))
    protected_writes = tuple(dict.fromkeys(path.resolve() for path in (
        attempt_root,
        private_evidence_root,
        private_checkout_root,
        source_root,
        *(path for path in (explicit_canonical, *canonical_store_paths) if path is not None),
        *storage_denials,
    )))
    lines = ["(version 1)", "(allow default)"]
    lines.extend(
        f'(deny file-read* (subpath "{_sandbox_quote(path)}"))'
        for path in protected_reads
    )
    lines.extend(
        f'(deny file-write* (subpath "{_sandbox_quote(path)}"))'
        for path in protected_writes
    )
    # Seatbelt evaluates the later, more specific case-work allowance over the
    # attempt/evidence denials. Coordinator files beside work remain denied.
    lines.extend((
        f'(allow file-read* (subpath "{_sandbox_quote(work)}"))',
        f'(allow file-write* (subpath "{_sandbox_quote(work)}"))',
    ))
    # Keep storage denial rules after the selected-work allowance. A
    # misconfigured Runtime rooted below ``work`` must fail closed rather than
    # becoming writable backing state.
    lines.extend(
        f'(deny file-read* (subpath "{_sandbox_quote(path)}"))'
        for path in storage_denials
    )
    lines.extend(
        f'(deny file-write* (subpath "{_sandbox_quote(path)}"))'
        for path in storage_denials
    )
    # The checkout's private agent tree must stay denied even if a case is
    # accidentally placed beneath it; the selected case normally lives under
    # the workspace-parent .otto tree instead.
    lines.extend((
        f'(deny file-read* (subpath "{_sandbox_quote(private_checkout_root)}"))',
        f'(deny file-write* (subpath "{_sandbox_quote(private_checkout_root)}"))',
    ))
    # The public worker credential is the sole exception to its denied store.
    # It is read-only; the endpoint remains governed by the worker's existing
    # provider/network behavior.
    lines.extend(
        f'(allow file-read* (literal "{_sandbox_quote(path)}"))'
        for path in (path.expanduser().absolute() for path in public_read_paths)
    )
    profile = "\n".join(lines) + "\n"
    receipt = {
        "kind": "astrid.timeline-eval.local-worker-boundary.v1",
        "enforcement": "macos-sandbox-exec",
        "profile_sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
        "selected_case_path": str(work.resolve()),
        "public_product_path": str(source_root.resolve()),
        "protected_read_paths": [str(path) for path in protected_reads],
        "protected_write_paths": [str(path) for path in protected_writes],
        "public_read_paths": [str(path.expanduser().absolute()) for path in public_read_paths],
        "runtime_storage_denied": [str(path) for path in storage_denials],
        "canonical_root_denied": str(explicit_canonical) if explicit_canonical else None,
        "status": "enforced",
    }
    return [sandbox, "-p", profile, *argv], receipt


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _regular_file(path: Path | None) -> Path | None:
    if path is None or path.is_symlink() or not path.is_file():
        return None
    return path


def _relative(path: Path | None, root: Path) -> str | None:
    path = _regular_file(path)
    if path is None:
        return None
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _review(case_root: Path) -> tuple[str, str, str, str, tuple[str, ...]]:
    path = _regular_file(case_root / "manual-review.json")
    if path is None:
        return "not_assessed", "undetermined", "not_collected", "unknown", ("manual review is not recorded",)
    try:
        value = load_json(path)
    except Exception as exc:  # noqa: BLE001 - malformed review is a review gap
        return "not_assessed", "undetermined", "unavailable", "unknown", (f"manual review is unreadable: {exc}",)
    if not isinstance(value, Mapping):
        return "not_assessed", "undetermined", "unavailable", "unknown", ("manual review is not an object",)
    outcome = str(value.get("task_outcome", "not_assessed"))
    manual = str(value.get("manual_review", "undetermined"))
    evidence = str(value.get("evidence_sufficiency", "not_collected"))
    safety = str(value.get("safety", "unknown"))
    if outcome not in TASK_OUTCOMES or manual not in MANUAL_REVIEW_STATUSES or evidence not in EVIDENCE_STATUSES or safety not in SAFETY_STATUSES:
        return "not_assessed", "undetermined", "unavailable", "unknown", ("manual review uses an unsupported status",)
    notes = value.get("notes", ())
    return outcome, manual, evidence, safety, tuple(str(item) for item in notes if item) if isinstance(notes, list) else ()


def _public_task(case: Mapping[str, Any], *, work: Path | None = None) -> str:
    """Render the agent-facing request without grader expectations."""
    lines = [f"Case: {case.get('id', '')}", "", "Task:"]
    prompt = case.get("prompt")
    if isinstance(prompt, Mapping):
        lines.extend((f"Focus: {prompt.get('focus', '')}", "", *[f"- {item}" for item in prompt.get("questions", ())]))
    else:
        lines.append(str(prompt or "Complete the requested timeline task."))
    addendum = case.get("operational_addendum")
    if addendum:
        lines.extend(("", str(addendum)))
    if work is not None:
        case_id = str(case.get("id", "case"))
        lines.extend((
            "",
            f"Use only this disposable case folder: `{work}`.",
            f"The local project identifier is `astrid-eval-{case_id}`.",
            "Do not open, edit, or publish the canonical Astrid project.",
        ))
    lines.extend((
        "", "Write exactly one JSON object to `result.json` in this working directory.",
        "It must have the keys `status`, `answer`, and `evidence`.",
        "Use a concise status and explain what you actually did. Do not claim evidence you did not collect.",
    ))
    return "\n".join(lines) + "\n"


def _result_problem(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return "optional result.json is missing"
    try:
        value = load_json(path)
    except Exception as exc:  # noqa: BLE001 - invalid result is a case failure
        return f"result.json is malformed: {exc}"
    if not isinstance(value, Mapping) or not {"status", "answer", "evidence"}.issubset(value):
        return "result.json must be an object with status, answer, and evidence"
    return None


def _case_timeout(case: Mapping[str, Any], override: float | None) -> float:
    if override is not None:
        return max(1.0, float(override))
    timeout = case.get("timeout")
    value = timeout.get("value", 3600) if isinstance(timeout, Mapping) else 3600
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return 3600.0


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        try:
            process.terminate()
        except OSError:
            return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            try:
                process.kill()
            except OSError:
                pass


def _launch_omp(
    argv: Sequence[str], cwd: Path, timeout: float, trace_path: Path, log_path: Path,
    *, env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Launch OMP in its own process group and preserve JSON trace and stderr."""
    with trace_path.open("wb") as trace, log_path.open("wb") as log:
        process = subprocess.Popen(
            list(argv), cwd=cwd, env=dict(env) if env is not None else None,
            stdout=trace, stderr=log, start_new_session=True,
        )
        try:
            return ProcessResult(process.wait(timeout=timeout))
        except subprocess.TimeoutExpired:
            _stop_process_group(process)
            return ProcessResult(process.returncode, timed_out=True)
        except KeyboardInterrupt:
            _stop_process_group(process)
            return ProcessResult(process.returncode, interrupted=True)
        finally:
            # OMP may leave a child behind even after its own process exits.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass


def _matrix(suite: Mapping[str, Any], records: list[ManualCaseRecord], *, execute: bool,
            launch_count: int, interrupted: bool = False) -> dict[str, Any]:
    return {
        "kind": LOOP_KIND, "suite_id": suite.get("suite_id"),
        "suite_version": suite.get("suite_version"),
        "model_launched": launch_count > 0, "launch_count": launch_count,
        "execution_requested": execute, "automatic_scoring": False,
        "interrupted": interrupted, "case_count": len(records),
        "records": [record.as_dict() for record in records],
        "controls": {
            "sequential": True, "retry": "none", "failed_roots_preserved": True,
            "manual_review_required": True, "unknown_safety_is_not_pass": True,
            "admission_gate": False,
        },
    }


def run_local_loop(
    suite_path: Path = Path(__file__).with_name("suite.json"),
    *,
    attempt_root: Path,
    execute: bool = False,
    omp_bin: str = "omp",
    model: str = DEFAULT_MODEL,
    thinking: str = DEFAULT_THINKING,
    timeout_seconds: float | None = DEFAULT_TIMEOUT_SECONDS,
    case_ids: Sequence[str] | None = None,
    process_launcher: ProcessLauncher | None = None,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    canonical_endpoint: str | None = None,
    canonical_realm_id: str | None = None,
    canonical_root: Path | None = None,
    case_preparer: Callable[..., PreparedCase] | None = None,
) -> dict[str, Any]:
    """Create a sequential run; execution is opt-in and uses direct OMP argv."""
    suite = load_json(suite_path)
    cases = suite.get("cases") if isinstance(suite, Mapping) else None
    if not isinstance(cases, list):
        raise ValueError("suite does not contain cases")
    selected = set(case_ids) if case_ids is not None else None
    root = attempt_root.expanduser().absolute()
    if root.exists() and root.is_symlink():
        raise ValueError("attempt root must not be a symlink")
    root.mkdir(parents=True, exist_ok=True)
    loop_path = root / "local-loop.json"
    if loop_path.exists():
        raise ValueError(f"attempt already contains local-loop.json: {root}")
    launcher = process_launcher or _launch_omp
    records: list[ManualCaseRecord] = []
    launch_count = 0
    interrupted = False

    for raw in cases:
        if not isinstance(raw, Mapping) or not raw.get("id"):
            raise ValueError("suite case is missing an id")
        case_id = str(raw["id"])
        if selected is not None and case_id not in selected:
            continue
        case_root = root / "cases" / case_id
        work = case_root / "work"
        work.mkdir(parents=True, exist_ok=True)
        project = work / "project"
        brief = work / "brief.md"
        result_path = work / "result.json"
        trace_path = case_root / "trace.jsonl"
        log_path = case_root / "agent.log"
        notes: list[str] = []
        returncode: int | None = None
        setup_error: str | None = None

        if not execute:
            project.mkdir(exist_ok=True)
            if not brief.exists():
                brief.write_text(_public_task(raw, work=work), encoding="utf-8")
            execution = "not_launched"
            notes.append("no model launched; case workspace preserved")
        elif any(path.exists() or path.is_symlink() for path in (
            result_path, trace_path, log_path, case_root / "launch.json",
        )):
            execution = "launcher_failed"
            notes.append("existing case evidence preserved; refusing to overwrite it")
        else:
            prepared: PreparedCase | None = None
            before_observation: Any = None
            preparer = case_preparer or prepare_case
            try:
                prepared = preparer(
                    case_id, case_root=project, fixture_root=fixture_root,
                    canonical_endpoint=canonical_endpoint or "",
                    canonical_realm_id=canonical_realm_id or "",
                    canonical_root=canonical_root or Path(""),
                )
                before_observation = prepared.baseline_observer()
                _write_json(case_root / "fixture-receipt.json", dict(prepared.fixture_receipt))
                _write_json(case_root / "before.json", before_observation)
                doc_path = Path(__file__).resolve().parents[2] / "docs" / "timeline-editing-guide.md"
                brief.write_text(render_case_brief(case_id, prepared=prepared, doc_path=str(doc_path)), encoding="utf-8")
            except Exception as exc:  # preparation failures are recorded and never launch a worker
                setup_error = f"{type(exc).__name__}: {exc}"
                execution = "not_launched"
                notes.append("case preparation failed; worker was not launched")
            else:
                argv = [
                    omp_bin, "--model", model, "--thinking", thinking,
                    "--no-session", "--mode", "json", "--print", f"@{brief}",
                ]
                launch_argv = argv
                boundary: dict[str, Any]
                if process_launcher is None:
                    try:
                        launch_argv, boundary = _case_worker_boundary(
                            argv,
                            work=work,
                            attempt_root=root,
                            protected_paths=getattr(prepared, "worker_denied_paths", ()),
                            public_read_paths=(
                                (prepared.credential_file,)
                                if getattr(prepared, "credential_file", None) is not None
                                else ()
                            ),
                            canonical_root=canonical_root,
                        )
                    except WorkerBoundaryUnavailable as exc:
                        setup_error = f"{type(exc).__name__}: {exc}"
                        execution = "not_launched"
                        notes.append("worker filesystem boundary unavailable; worker was not launched")
                        boundary = {
                            "kind": "astrid.timeline-eval.local-worker-boundary.v1",
                            "status": "unavailable",
                            "reason": str(exc),
                        }
                else:
                    # ``process_launcher`` is an in-process test seam. It is
                    # never reachable from the CLI and cannot assert an OS
                    # boundary on behalf of a real worker.
                    boundary = {
                        "kind": "astrid.timeline-eval.local-worker-boundary.v1",
                        "enforcement": "injected-test-launcher",
                        "status": "test-only",
                    }
                _write_json(case_root / "worker-boundary.json", boundary)
                _write_json(case_root / "launch.json", {
                    "argv": argv, "cwd": str(work), "model": model,
                    "thinking": thinking, "timeout_seconds": _case_timeout(raw, timeout_seconds),
                    "fresh_context": True, "worker_boundary": boundary,
                })
                launch_error: OSError | None = None
                if setup_error is None:
                    try:
                        if process_launcher is None:
                            process = launcher(
                                launch_argv, work, _case_timeout(raw, timeout_seconds), trace_path, log_path,
                                env=_case_child_environment(prepared),
                            )
                        else:
                            process = launcher(launch_argv, work, _case_timeout(raw, timeout_seconds), trace_path, log_path)
                    except KeyboardInterrupt:
                        process = ProcessResult(None, interrupted=True)
                    except OSError as exc:
                        process = ProcessResult(None, started=False)
                        launch_error = exc
                    if process.started:
                        launch_count += 1
                    returncode = process.returncode
                    if process.timed_out:
                        _write_json(case_root / "timeout.json", {
                            "kind": "astrid.timeline-eval.host-timeout.v1",
                            "case_id": case_id,
                            "timeout_seconds": _case_timeout(raw, timeout_seconds),
                            "automatic_retry": False,
                            "partial_trace_preserved": trace_path.is_file(),
                            "partial_stderr_preserved": log_path.is_file(),
                            "result_present": result_path.is_file(),
                        })
                    if launch_error is not None:
                        execution = "launcher_failed"
                        notes.append(f"could not start OMP: {launch_error}")
                    elif process.interrupted:
                        execution = "interrupted"
                        interrupted = True
                        notes.append("user interrupted; case workspace preserved")
                    elif process.timed_out:
                        execution = "timed_out"
                        notes.append("case process timed out; no automatic retry")
                    elif process.returncode != 0:
                        execution = "launcher_failed"
                        notes.append(f"OMP exited with status {process.returncode}")
                    else:
                        # A worker result is a useful reporting artifact, but it
                        # is not coordinator evidence and must not turn a
                        # successful process into a semantic pass/failure.  A
                        # missing or malformed optional result is therefore a
                        # reporting defect while trace, process status, and
                        # coordinator before/after observations remain usable.
                        execution = "completed"
                        problem = _result_problem(result_path)
                        if problem:
                            notes.append(f"reporting defect: {problem}")
                        else:
                            notes.append("OMP completed; semantic outcome requires independent review")
            finally:
                if prepared is not None:
                    try:
                        after_observation = prepared.baseline_observer()
                        _write_json(case_root / "after.json", after_observation)
                        _write_json(case_root / "readback.json", {
                            "case_id": case_id,
                            "before_observed": before_observation is not None,
                            "after_observed": True,
                            "status": "pass",
                            "scope": "prepared-fixture-observation",
                        })
                    except Exception as exc:  # capture gaps remain explicit; never mask worker status
                        notes.append(f"coordinator after-capture failed: {type(exc).__name__}: {exc}")
                    finally:
                        try:
                            prepared.close()
                        except Exception as exc:  # disposal failures are evidence, not loop control
                            notes.append(f"prepared case cleanup failed: {type(exc).__name__}: {exc}")

        outcome, manual, evidence, safety, review_notes = _review(case_root)
        notes.extend(review_notes)
        records.append(ManualCaseRecord(
            case_id=case_id, kind=str(raw.get("kind", "unknown")), execution=execution,
            task_outcome=outcome, manual_review=manual, evidence_sufficiency=evidence, safety=safety,
            case_root=str(case_root), transcript=_relative(log_path, root),
            trace=_relative(trace_path, root), result=_relative(result_path, root),
            returncode=returncode, setup_error=setup_error, notes=tuple(dict.fromkeys(notes)),
        ))
        _write_json(loop_path, _matrix(suite, records, execute=execute,
                                      launch_count=launch_count, interrupted=interrupted))
        if interrupted:
            break

    return _matrix(suite, records, execute=execute, launch_count=launch_count, interrupted=interrupted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path(__file__).with_name("suite.json"))
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument("--case", dest="case_ids", action="append")
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--canonical-endpoint")
    parser.add_argument("--canonical-realm-id")
    parser.add_argument("--canonical-root", type=Path)
    parser.add_argument("--execute", action="store_true", help="launch one fresh OMP process per selected case")
    parser.add_argument("--omp-bin", default="omp")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking", default=DEFAULT_THINKING)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS,
                        help="per-case timeout (default: 600 seconds)")
    args = parser.parse_args(argv)
    result = run_local_loop(
        args.suite, attempt_root=args.attempt_root,
        execute=args.execute, omp_bin=args.omp_bin, model=args.model,
        thinking=args.thinking, timeout_seconds=args.timeout_seconds,
        case_ids=args.case_ids,
        fixture_root=args.fixture_root,
        canonical_endpoint=args.canonical_endpoint,
        canonical_realm_id=args.canonical_realm_id,
        canonical_root=args.canonical_root,
    )
    print(json.dumps({
        "status": "interrupted" if result["interrupted"] else "ok",
        "attempt_root": str(args.attempt_root), "case_count": result["case_count"],
        "launch_count": result["launch_count"], "model_launched": result["model_launched"],
        "execution_requested": result["execution_requested"],
    }, indent=2))
    return 130 if result["interrupted"] else 0


__all__ = ["DEFAULT_MODEL", "DEFAULT_THINKING", "DEFAULT_TIMEOUT_SECONDS", "LOOP_KIND", "ManualCaseRecord", "ProcessResult", "run_local_loop"]


if __name__ == "__main__":
    raise SystemExit(main())
