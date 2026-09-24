"""Run one native Luna timeline-evaluation attempt.

This is deliberately a thin adapter around the existing timeline fixture
readiness and :func:`evals.timeline.run.aggregate_attempt` collector.  It does
not seed Runtime or implement another grading harness.  A native execution
must be accompanied by an explicit disposable Runtime isolation contract;
without one the launcher fails closed.  Each fixture-ready case gets one OMP
one-shot invocation with ``--no-session``; fixture-blocked cases receive an
explicit blocked record instead.

The launcher writes only public case briefs before an agent starts.  Grader
checks are materialized after the process exits, so an evaluated agent cannot
read ``checks.json`` as part of its fresh context.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Collection, Mapping

from .fixture import (
    FixtureError,
    SOURCE_PROJECT_ID,
    SOURCE_TIMELINE_ID,
    materialize_public_navigation_entrypoint,
)
from .fixture_manifest import DEFAULT_FIXTURE_ROOT, build_readiness
from .evidence_collector import (
    EvidenceCollectionError,
    collect_case_evidence,
    teardown_receipt_from_host_capture,
)
from .independent_readback import (
    EXACT_CLOSURE_NAVIGATION,
    IndependentReadbackError,
    ProjectionUnavailable,
    ReadbackContract,
    ReadbackObservation,
    observe_case_before,
    verify_case_after,
    verify_navigation_after,
)
from .run import HIDDEN_KEYS, SetupError, aggregate_attempt, load_json, visible_brief
from .result_adapter import public_result_contract
from .worker_boundary import (
    BoundaryReceipt,
    BoundaryRequirements,
    BoundarySupervisor,
    BoundaryUnavailable,
    WorkerLaunchRequest,
    launch_in_proven_boundary,
    pin_worker_boundary,
    prove_worker_boundary,
)


DEFAULT_SUITE = Path(__file__).with_name("suite.json")
DEFAULT_BRIEFS = Path(__file__).with_name("cases") / "agent_briefs.json"
DEFAULT_MODEL = "openai-codex/gpt-5.6-luna"
DEFAULT_THINKING = "high"
ATTEMPT_KIND = "astrid.timeline-eval.case-attempt.v1"
ATTEMPT_RESULT_KIND = "astrid.timeline-eval.native-attempt.v1"
CASE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
SKILL_RELATIVE_PATH = "astrid/packs/rendering/skill/SKILL.md"
LOCAL_RUNTIME_PROJECT_PREFIX = "local-disposable"


class NativeLauncherError(SetupError):
    """The attempt cannot be started without inventing fixture/runtime state."""


@dataclass(frozen=True)
class CaseRuntimeContract:
    """Coordinator-only Runtime/readback authority for one selected case."""

    endpoint: str
    credential: Path
    isolation_contract: Path
    source_reader: Any | None = None


class _CapturedClosureReader:
    """Read-only view of the host capture made after worker teardown."""

    def __init__(self, capture: Mapping[str, Any]):
        heads = capture.get("timeline_heads")
        closures = capture.get("closures")
        if not isinstance(heads, Mapping) or not isinstance(closures, Mapping):
            raise IndependentReadbackError("host final capture omitted timeline heads or closures")
        self._heads = dict(heads)
        self._closures = dict(closures)

    def current_head(self, project_id: str, timeline_id: str) -> str:
        value = self._heads.get(timeline_id)
        if not isinstance(value, str) or not value:
            raise IndependentReadbackError("captured timeline has no current head")
        return value

    def read_current_closure(
        self, project_id: str, timeline_id: str, *, head: str | None = None,
    ) -> Mapping[str, Any]:
        closure = self._closures.get(timeline_id)
        if not isinstance(closure, Mapping):
            raise IndependentReadbackError("captured timeline closure is unavailable")
        expected = head or self.current_head(project_id, timeline_id)
        if closure.get("head_revision_id") != expected:
            raise IndependentReadbackError("captured closure differs from requested exact head")
        return closure

    def list_project_timeline_heads(self, project_id: str) -> Mapping[str, str | None]:
        return self._heads


def _verify_projected_readback(
    *,
    reader: Any,
    target: Mapping[str, Any],
    contract: ReadbackContract,
    before: ReadbackObservation,
    publication: Mapping[str, Any] | None,
    source_reader: Any | None,
) -> Any:
    """Dispatch only named, implemented projections; never infer a grader."""
    if contract.projection == EXACT_CLOSURE_NAVIGATION:
        return verify_navigation_after(
            reader, target, contract, before, source_reader=source_reader,
        )
    if contract.projection == "active_media_replacement.v1":
        if publication is None:
            raise ProjectionUnavailable(
                "active_media_replacement.v1 requires an exact publication receipt"
            )
        return verify_case_after(
            reader, target, contract, before, publication, source_reader=source_reader,
        )
    raise ProjectionUnavailable(f"case projection unavailable: {contract.projection}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_case_id(value: Any) -> str:
    case_id = str(value)
    if not CASE_ID.fullmatch(case_id) or case_id in {".", ".."}:
        raise NativeLauncherError(f"invalid suite case id: {case_id!r}")
    return case_id


def _local_runtime_project_id(attempt_id: str, case_id: str) -> str:
    """Create an explicit project identity for a local disposable case."""
    digest = hashlib.sha256(f"{attempt_id}:{case_id}".encode("utf-8")).hexdigest()[:20]
    return f"{LOCAL_RUNTIME_PROJECT_PREFIX}-{digest}"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _publication_payload(response: Mapping[str, Any]) -> Mapping[str, Any]:
    """Unwrap the SDK result envelope without changing its publication data."""
    data = response.get("data")
    return data if response.get("ok") is True and isinstance(data, Mapping) else response


def _skill_reference() -> dict[str, str]:
    """Resolve the checked-in workflow skill and pin its exact bytes."""
    path = Path(__file__).resolve().parents[2] / SKILL_RELATIVE_PATH
    if path.is_symlink() or not path.is_file():
        raise NativeLauncherError(f"required rendering skill is missing or unsafe: {path}")
    content = path.read_bytes()
    text = content.decode("utf-8")
    version_match = re.search(r"(?m)^version:\s*([A-Za-z0-9._-]+)\s*$", text[:1024])
    if not version_match:
        raise NativeLauncherError(f"rendering skill has no readable version field: {path}")
    return {
        "path": str(path),
        "repository_path": SKILL_RELATIVE_PATH,
        "version": version_match.group(1),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _sha256_file(path: Path) -> str | None:
    if path.is_symlink() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _attempt_fingerprints(
    fixture_root: Path, suite_path: Path, briefs_path: Path,
    skill_reference: Mapping[str, Any],
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[2]
    sources = {
        "runner": Path(__file__).resolve(),
        "grader": repo_root / "evals/timeline/run.py",
        "fixture_builder": repo_root / "evals/timeline/fixture.py",
        "fixture_manifest": repo_root / "evals/timeline/fixture_manifest.py",
        "checker": repo_root / "evals/timeline/checks.py",
        "readback_contract": repo_root / "evals/timeline/independent_readback.py",
        "runtime_adapter": repo_root / "evals/timeline/runtime_adapter.py",
        "worker_boundary": repo_root / "evals/timeline/worker_boundary.py",
        "suite": suite_path,
        "public_briefs": briefs_path,
    }
    implementation = {
        name: {"path": str(path), "sha256": _sha256_file(path)}
        for name, path in sources.items()
    }
    fixture_files: list[dict[str, str]] = []
    if fixture_root.is_dir() and not fixture_root.is_symlink():
        for path in sorted(fixture_root.rglob("*")):
            if path.is_file() and not path.is_symlink():
                digest = _sha256_file(path)
                if digest:
                    fixture_files.append({
                        "path": path.relative_to(fixture_root).as_posix(),
                        "sha256": digest,
                    })
    fixture_tree = hashlib.sha256(json.dumps(
        fixture_files, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    return {
        "implementation": implementation,
        "runtime": {
            "adapter_sha256": implementation["runtime_adapter"]["sha256"],
            "readback_sha256": implementation["readback_contract"]["sha256"],
            "server_build": "not exposed by the supplied Runtime receipt",
        },
        "skill": dict(skill_reference),
        "fixture": {
            "root": str(fixture_root),
            "file_count": len(fixture_files),
            "tree_sha256": fixture_tree,
        },
        "checker": {
            "implementation_sha256": implementation["checker"]["sha256"],
            "suite_sha256": implementation["suite"]["sha256"],
        },
    }


def _readback_contract(
    case: Mapping[str, Any], target: Mapping[str, Any], fixture_root: Path,
) -> ReadbackContract:
    case_id = str(case.get("id", ""))
    locator = _mapping(target.get("target_locator"))
    projection = locator.get("readback_projection") or target.get("readback_projection")
    if case.get("kind") == "navigation":
        projection = projection or EXACT_CLOSURE_NAVIGATION
        if projection != EXACT_CLOSURE_NAVIGATION:
            raise IndependentReadbackError("navigation target requires exact_closure_navigation.v1")
    elif not isinstance(projection, str) or not projection:
        raise IndependentReadbackError("public target has no declared semantic readback projection")
    if case.get("kind") == "action" and projection != "active_media_replacement.v1":
        raise IndependentReadbackError(f"unsupported action readback projection: {projection}")
    expected_digest: str | None = None
    if case_id == "A01":
        manifest = load_json(fixture_root / "action" / "manifest.json")
        rows = _mapping(manifest).get("cases", [])
        fixture_case = next((row for row in rows if isinstance(row, Mapping) and row.get("id") == case_id), {})
        expected = _mapping(_mapping(fixture_case).get("media")).get("new_image_digest")
        if not isinstance(expected, str) or not expected:
            raise IndependentReadbackError("A01 private target contract omitted its expected media digest")
        expected_digest = expected
    return ReadbackContract(
        case_id=case_id,
        projection=projection,
        expected_media_digest=expected_digest,
        source_project_id=SOURCE_PROJECT_ID,
        source_timeline_id=SOURCE_TIMELINE_ID,
    )


def _load_public_target(case_dir: Path) -> Mapping[str, Any] | None:
    """Load the coordinator-provided disposable target, if one was seeded."""
    for name in ("target.json", "public-target.json"):
        path = case_dir / name
        if not path.is_file():
            continue
        value = load_json(path)
        if not isinstance(value, Mapping):
            raise NativeLauncherError(f"public target must be a JSON object: {path}")
        return value
    return None


def _action_target_block_reason(
    case_id: str, public_target: Mapping[str, Any] | None,
) -> str:
    """Explain why an action case cannot launch without a real target receipt."""
    if public_target is None:
        return (
            f"{case_id} fixture derivative is not materialized: no disposable "
            "target.json receipt was prepared; model launch is blocked until the "
            "case-specific target, owned media, and readback projection exist"
        )
    edit_capability = _mapping(_mapping(public_target).get("capabilities")).get("edit")
    if isinstance(edit_capability, Mapping):
        reason = edit_capability.get("reason")
        if isinstance(reason, str) and reason:
            return reason
    return (
        f"{case_id} fixture derivative is not launchable: its public target "
        "does not declare an available case-specific edit route"
    )


def _prepare_public_target(
    prepared_targets_root: Path | None,
    *,
    case_id: str,
    case_dir: Path,
) -> Mapping[str, Any] | None:
    """Copy one coordinator-prepared target into the fresh case directory.

    The preparation root is coordinator-owned and must be separate from the
    worker mount. Only the selected case's public target is copied; no suite,
    baseline, or hidden checks cross the boundary.
    """
    if prepared_targets_root is None:
        return None
    root = prepared_targets_root.expanduser().absolute()
    cursor = root
    while True:
        if cursor.is_symlink():
            raise NativeLauncherError(f"prepared target root traverses a symlink: {cursor}")
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    if not root.is_dir():
        raise NativeLauncherError(f"prepared target root is missing or unsafe: {root}")
    case_root = root / case_id
    if case_root.is_symlink() or not case_root.is_dir():
        raise NativeLauncherError(f"prepared public target directory is missing or unsafe for {case_id}: {case_root}")
    source = case_root / "target.json"
    if source.is_symlink() or not source.is_file():
        raise NativeLauncherError(f"prepared public target is missing for {case_id}: {source}")
    # Read and rewrite JSON rather than copying arbitrary bytes or links into
    # the worker directory.
    value = load_json(source)
    if not isinstance(value, Mapping):
        raise NativeLauncherError(f"prepared public target must be an object: {source}")
    _write_json(case_dir / "target.json", value)
    return value


def _setup_failed_case(
    case: Mapping[str, Any], *, attempt_id: str, case_dir: Path, reason: str,
) -> dict[str, Any]:
    """Persist a terminal setup failure without starting OMP."""
    session_id = f"{attempt_id}-{case['id']}-not-launched"
    result = {
        "kind": "astrid.timeline-eval.agent-result.v1",
        "attempt_id": attempt_id,
        "case_id": str(case["id"]),
        "session_id": session_id,
        "fresh_context": False,
        "agent_status": "setup_failed",
        "launcher_process_status": "not_started",
        "execution_status": "not_started",
        "elapsed_seconds": 0.0,
        "tool_calls": 0,
        "retries": 0,
        "clarification_needed": False,
        "fixture_or_agent_failure": "setup",
        "failure_cause": {"setup": [reason], "summary": reason},
    }
    _write_json(case_dir / "result.json", result)
    _trace_lines(case_dir, events=[{
        "event": "setup_failed",
        "at": _now(),
        "case_id": str(case["id"]),
        "reason": reason,
    }])
    return result


def _require_a01_protected_roles(snapshot: Mapping[str, Any]) -> None:
    target = _mapping(snapshot)
    for name in ("voice", "frame_overlay"):
        role = target.get(name)
        if not isinstance(role, Mapping) or not role.get("id"):
            raise IndependentReadbackError(f"A01 target is missing its protected {name} clip")


def _connect_readback_adapter(
    *,
    endpoint: str | None,
    credential: Path | None,
    contract: Path | None,
) -> Any:
    """Create the coordinator-only adapter; never discover ambient Runtime."""
    from .runtime_adapter import RuntimeFixtureAdapter

    return RuntimeFixtureAdapter.connect(
        endpoint=endpoint,
        credential_file=credential,
        contract_path=contract,
    )


def _public_brief(
    case: Mapping[str, Any],
    public_case: Mapping[str, Any] | None,
    *,
    fixture_root: Path,
    case_dir: Path,
    skill_reference: Mapping[str, str],
    runtime_project_id: str | None = None,
    worker_case_path: str | None = None,
) -> dict[str, Any]:
    """Build one agent-visible brief without verifier-only fields."""
    source = dict(public_case or visible_brief(case))
    # Be defensive when a caller supplies a hand-written brief.  The public
    # brief is a fresh object; no hidden check list or suite contract is copied.
    source = {key: value for key, value in source.items() if key not in HIDDEN_KEYS}
    source.setdefault("id", case.get("id"))
    source.setdefault("version", case.get("version"))
    visible_case_path = worker_case_path or str(case_dir.resolve())
    explicit_project_id = runtime_project_id or source.get("runtime_project_id")
    if not isinstance(explicit_project_id, str) or not explicit_project_id:
        raise NativeLauncherError("local disposable brief is missing its Runtime project ID")
    # The agent receives both values explicitly; it must not infer either from
    # cwd, environment, or repository layout.
    source["case_folder"] = visible_case_path
    source["runtime_project_id"] = explicit_project_id
    source["fixture_entry_point"] = {
        # Do not disclose the shared fixture repository: it contains private
        # manifests, answer material (notably the A10 brightness ordering),
        # grader inputs and other cases.  A real disposable seed places only
        # the selected case's public entry point under this directory.
        "root": visible_case_path,
        "case_id": str(case["id"]),
        "case_directory": visible_case_path,
        "case_folder": visible_case_path,
        "runtime_project_id": explicit_project_id,
        "scope": "selected-case-only",
        "read_only": case.get("kind") == "navigation",
        "entrypoint_path": "entrypoint/entrypoint.json" if case.get("kind") == "navigation" else "target.json",
        "instruction": "Use only this selected-case entry point and public tools; do not read suite or grader files.",
    }
    observation_fields = {
        "L01": ["head_revision_id", "selected_image_media_id"],
        "L02": ["expanded_occurrences"],
        "L03": ["montage_media_ids", "music_cue_times_seconds"],
        "L06": [
            "diagnostic.status",
            "diagnostic.error_type",
            "diagnostic.base_parent_revision_id",
        ],
        "L08": ["available_segment_titles", "missing_text_roles"],
    }
    case_id = str(case.get("id", ""))
    if case.get("kind") == "navigation" and case_id in observation_fields:
        source["required_observation_fields"] = observation_fields[case_id]
    source["skill_reference"] = dict(skill_reference)
    source["result_contract"] = public_result_contract(case)
    return source


def _load_public_briefs(path: Path) -> dict[str, Mapping[str, Any]]:
    if not path.is_file():
        return {}
    value = load_json(path)
    rows = value.get("cases") if isinstance(value, Mapping) else None
    if not isinstance(rows, list):
        raise NativeLauncherError(f"public briefs must contain a cases array: {path}")
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("id"):
            raise NativeLauncherError(f"public brief row is missing an id: {path}")
        result[_safe_case_id(row["id"])] = row
    return result


def _clean_child_environment() -> dict[str, str]:
    """Keep provider auth while excluding ambient Runtime/project credentials.

    A clean environment is only hygiene; it is not an isolation boundary.  A
    native attempt therefore also requires an explicit disposable Runtime
    contract (unless the caller is using the test-only fixture adapter).
    """
    blocked_fragments = (
        "ASTRID_RUNTIME", "ASTRID_CANONICAL", "RUNTIME_CREDENTIAL",
        "RUNTIME_TOKEN", "SUPABASE_SERVICE", "SUPABASE_SECRET",
    )
    return {
        key: value for key, value in os.environ.items()
        if not any(fragment in key.upper() for fragment in blocked_fragments)
    }


def _prompt(
    case: Mapping[str, Any], *, skill_reference: Mapping[str, str],
    public_target: Mapping[str, Any] | None,
    local_disposable: bool = True,
) -> str:
    capabilities = _mapping(_mapping(public_target).get("capabilities"))
    edit_capability = _mapping(capabilities.get("edit"))
    route = edit_capability.get("route") if edit_capability.get("status") == "available" else None
    if case.get("kind") == "navigation":
        route_instructions = "This is a read-only navigation task. Do not publish or modify the supplied entry point.\n"
    else:
        route_instructions = (
        "This case has the exact public edit capability " + str(route) + ". Use it only if its target locator and preconditions match. "
        + (
            "Use the documented astrid.sdk.authoring_bundle path (open, edit the detached same-schema candidate, validate, diff, preview, then publish) and preserve the exact returned JSON response as top-level publication_response in result.json, including new_head and dependency_manifest. Do not call a low-level publish_parent_composition operation directly, alter target.json, or publish outside the target-bound helper; if that bound helper is not actually available, report the route unavailable.\n"
            if route == "authoring-bundle validate/commit" else
            "For publication, preserve the exact returned JSON response as top-level publication_response in result.json, including new_head and dependency_manifest.\n"
        )
        if route else
        "No case-specific edit capability is declared available. Check the supplied canonical skill for another documented route admitted by this receipt; if none applies, report unavailable/blocked instead of guessing or claiming success.\n"
        )
    runtime_instructions = (
        "Use the explicit runtime_project_id and case_folder from brief.json. "
        "This is a local disposable case: do not discover or contact a canonical, network, or ambient Runtime, and do not require credentials.\n"
        if local_disposable else
        "The disposable Runtime connection is available only through the supplied "
        "ASTRID_TIMELINE_EVAL_ENDPOINT and ASTRID_TIMELINE_EVAL_CREDENTIAL environment "
        "variables; use those for authenticated public calls and never probe a canonical endpoint.\n"
    )
    return (
        "You are the evaluated Luna agent in one fresh, bounded context.\n"
        f"Read the canonical timeline skill at {skill_reference['path']} (version {skill_reference['version']}, sha256 {skill_reference['sha256']}) and verify the bytes before acting.\n"
        "Read only the selected public brief at brief.json and its supplied fixture entry point.\n"
        "Use normal public tools and documentation, and work only inside this disposable case directory.\n"
        "Do not inspect the versioned suite, grader files, prior attempts, or canonical Runtime.\n"
        "Perform the requested navigation or candidate edit if the fixture supports it. "
        "If a precondition or public capability is unavailable, stop and report that honestly.\n"
        + route_instructions
        + "Follow the selected target receipt's locator, preconditions, and case-specific advertised capabilities. "
        "A documented same-schema authoring-bundle route is acceptable only when the receipt admits it; "
        "do not assume it is available when the receipt does not. The legacy whole-config save is a separate route.\n"
        + runtime_instructions
        + "For read-only navigation, write top-level navigation_performed: true and an observations object "
        "with the fields named in brief.json; use exact values from the selected entry point/readback, not guesses. "
        "Follow the versioned result_contract in brief.json: write result.json and each listed worker-owned artifact "
        "at its exact path; coordinator-owned paths are not writable by the worker. "
        "Record useful evidence under evidence/ and write a JSON result record to result.json "
        "when you can. For an edit, include top-level edit_made: true, saved_to_test_timeline: true, "
        "and the observed post-save head/receipt; do not put the only terminal flag under a nested "
        "action object. Do not claim an edit, render, playback, or publication you did not observe.\n\n"
        f"Selected case: {case.get('id')}\n"
        "The complete public brief is in brief.json."
    )


def _trace_lines(case_dir: Path, *, events: list[dict[str, Any]]) -> None:
    with (case_dir / "trace.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    """Stop the bounded local worker and any children it left behind."""
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


def _invoke(
    *,
    omp_bin: str,
    model: str,
    thinking: str,
    model_boundary_id: str | None,
    case: Mapping[str, Any],
    case_dir: Path,
    isolated_endpoint: str | None = None,
    isolated_credential: Path | None = None,
    isolation_contract: Path | None = None,
    skill_reference: Mapping[str, str],
    public_target: Mapping[str, Any] | None,
    fixture_only: bool = False,
    local_disposable: bool = True,
    boundary_supervisor: BoundarySupervisor | None = None,
    boundary_receipt: BoundaryReceipt | None = None,
    boundary_requirements: BoundaryRequirements | None = None,
) -> tuple[str, int | None, float, list[dict[str, Any]], str]:
    """Invoke one fresh OMP context locally (fixture-only) or via the proven host.

    A live evaluation is never started with coordinator-local ``Popen``.  The
    host supervisor which issued the boundary receipt must launch the model in
    that exact worker runtime using the same unpredictable challenge.
    """
    timeout_value = _mapping(case.get("timeout")).get("value", 600)
    try:
        timeout_seconds = max(1.0, float(timeout_value))
    except (TypeError, ValueError):
        timeout_seconds = 600.0
    worker_case_dir = (
        boundary_requirements.selected_case_path
        if boundary_requirements is not None else str(case_dir)
    )
    command = [
        omp_bin,
        "--model", model,
        "--thinking", thinking,
        "--no-session",
        "--mode", "json",
        "--auto-approve",
        "--max-time", f"{int(timeout_seconds)}s",
        "--cwd", worker_case_dir,
        "--print",
        _prompt(
            case, skill_reference=skill_reference, public_target=public_target,
            local_disposable=local_disposable,
        ),
    ]
    started = time.monotonic()
    events: list[dict[str, Any]] = [{
        "event": "launcher_start",
        "at": _now(),
        "case_id": str(case["id"]),
        "fresh_context": True,
        "model": model,
        "thinking": thinking,
        "model_boundary_id": model_boundary_id,
        "invocation": command,
    }]
    child_env = _clean_child_environment()
    if not local_disposable and isolated_endpoint and public_target is not None:
        credential_path = (
            boundary_requirements.disposable_credential_path
            if boundary_requirements is not None else str(isolated_credential)
        )
        child_env.update({
            "ASTRID_TIMELINE_EVAL_ENDPOINT": isolated_endpoint,
            "ASTRID_TIMELINE_EVAL_CREDENTIAL": credential_path,
            "ASTRID_TIMELINE_EVAL_SOURCE_ACCESS": "false",
        })
    if fixture_only:
        child_env["ASTRID_TIMELINE_EVAL_FIXTURE_ONLY"] = "1"
    use_proven_boundary = (
        not fixture_only and not local_disposable
        and boundary_receipt is not None and boundary_requirements is not None
    )
    if use_proven_boundary:
        try:
            if boundary_receipt is None or boundary_requirements is None:
                raise BoundaryUnavailable("live launch has no proven worker boundary receipt")
            observed = launch_in_proven_boundary(
                boundary_supervisor,
                boundary_receipt,
                WorkerLaunchRequest(
                    case_id=str(case["id"]),
                    worker_id=boundary_requirements.worker_id,
                    execution_mode=boundary_requirements.execution_mode,
                    boundary_id=boundary_receipt.boundary_id,
                    runtime_receipt_id=boundary_receipt.runtime_receipt_id,
                    challenge=boundary_receipt.challenge,
                    public_package_path=boundary_receipt.public_package_path,
                    public_package_digest=boundary_receipt.public_package_digest,
                    argv=tuple(command),
                    cwd=worker_case_dir,
                    environment=child_env,
                    timeout_seconds=timeout_seconds,
                    final_capture_target=public_target,
                ),
            )
            if observed.final_capture is None:
                raise BoundaryUnavailable("host launch omitted final capture evidence")
            capture_path = (
                case_dir.parents[1] / "coordinator" / "cases" / str(case["id"])
                / "host-final-capture.json"
            )
            _write_json(capture_path, asdict(observed.final_capture))
        except (BoundaryUnavailable, OSError, TypeError, ValueError) as exc:
            elapsed = max(0.0, time.monotonic() - started)
            events.append({"event": "launcher_error", "at": _now(), "error": f"{type(exc).__name__}: {exc}"})
            events.append({"event": "launcher_exit", "at": _now(), "status": "unavailable", "returncode": None})
            return "unavailable", None, elapsed, events, ""
        stdout, stderr = observed.stdout, observed.stderr
        elapsed = observed.elapsed_seconds
        status = observed.status
        returncode = observed.returncode
    else:
        try:
            process = subprocess.Popen(
                command,
                cwd=case_dir,
                env=child_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
            )
        except OSError as exc:
            elapsed = max(0.0, time.monotonic() - started)
            events.append({"event": "launcher_error", "at": _now(), "error": f"{type(exc).__name__}: {exc}"})
            events.append({"event": "launcher_exit", "at": _now(), "status": "unavailable", "returncode": None})
            return "unavailable", None, elapsed, events, ""
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
            status = "completed" if process.returncode == 0 else "failed"
        except subprocess.TimeoutExpired:
            _terminate_process_group(process)
            stdout, stderr = process.communicate()
            status = "timeout"
        elapsed = max(0.0, time.monotonic() - started)
        returncode = process.returncode
    for stream, text in (("stdout", stdout), ("stderr", stderr)):
        for line_number, line in enumerate((text or "").splitlines(), 1):
            events.append({
                "event": "agent_output",
                "stream": stream,
                "line": line_number,
                "text": line,
            })
    events.append({
        "event": "launcher_exit",
        "at": _now(),
        "status": status,
        "returncode": returncode,
        "elapsed_seconds": elapsed,
    })
    output = stdout or ""
    if stderr:
        output += ("\n" if output else "") + stderr
    return status, returncode, elapsed, events, output


def _merge_result(
    case_dir: Path,
    *,
    case: Mapping[str, Any],
    attempt_id: str,
    session_id: str,
    status: str,
    returncode: int | None,
    elapsed: float,
    output: str,
    model: str,
    thinking: str,
    model_boundary_id: str | None,
) -> dict[str, Any]:
    agent_result: dict[str, Any] = {}
    result_path = case_dir / "result.json"
    if result_path.is_file():
        try:
            loaded = load_json(result_path)
            if isinstance(loaded, Mapping):
                agent_result = dict(loaded)
        except SetupError as exc:
            agent_result["agent_result_error"] = str(exc)
    # A one-shot agent may return its terminal record in stdout instead of
    # writing the optional file.  Recover only an explicit JSON object with a
    # result-shaped field; never treat free-form prose as an evaluation result.
    if not agent_result and output:
        for line in reversed(output.splitlines()):
            candidate = line.strip()
            if not candidate.startswith("{") or not candidate.endswith("}"):
                continue
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping) and any(
                key in parsed for key in ("execution_status", "navigation_performed", "edit_made", "safety")
            ):
                agent_result = dict(parsed)
                break
    result = dict(agent_result)
    # Promote a native agent's explicit observed route call when it put the
    # evidence under ``action``/``verification`` instead of the stable result
    # envelope.  This is not a prose heuristic: the route and HTTP readback
    # must both be present before the terminal flags are derived.
    action = result.get("action")
    verification = result.get("verification")
    if isinstance(action, Mapping) and isinstance(verification, Mapping):
        if result.get("edit_made") is not True and action.get("route") == "timelines replace-parent-media":
            if verification.get("post_save_status") == 200 and verification.get("post_save_head"):
                result["edit_made"] = True
        if result.get("saved_to_test_timeline") is not True and verification.get("post_save_status") == 200:
            result["saved_to_test_timeline"] = True
    # Keep the agent's terminal declaration distinct from the subprocess
    # lifecycle.  In particular, an agent can honestly report ``blocked``
    # after discovering that a requested public capability is unavailable
    # even though OMP itself exited successfully.
    reported_status = str(result.get("agent_status", result.get("status", result.get("execution_status", "")))).lower()
    terminal_statuses = {
        "passed", "failed", "blocked", "partial", "indeterminate", "missing_capability", "setup_failed", "setup_failure",
        "precondition_failed", "unavailable", "fixture_blocked", "timeout",
        "timed_out", "not_run",
    }
    if reported_status in terminal_statuses:
        result["agent_status"] = reported_status
        result["agent_execution_status"] = reported_status
    else:
        result.setdefault("agent_status", None)
        result["agent_execution_status"] = None
    result.update({
        "kind": "astrid.timeline-eval.agent-result.v1",
        "attempt_id": attempt_id,
        "case_id": str(case["id"]),
        "session_id": session_id,
        "fresh_context": True,
        "launcher_process_status": status,
        "execution_status": status,
        "returncode": returncode,
        "elapsed_seconds": elapsed,
        "launcher": {
            "kind": "omp",
            "model": model,
            "thinking": thinking,
            "model_boundary_id": model_boundary_id,
            "output_captured": bool(output),
            "one_shot": True,
            "no_session": True,
        },
    })
    if output:
        (case_dir / "agent-output.txt").write_text(output, encoding="utf-8")
    _write_json(result_path, result)
    return result


def _hidden_checks(case: Mapping[str, Any], *, fixture_root: Path) -> list[dict[str, Any]]:
    """Return exact, case-specific checks or an explicit missing-oracle result.

    Worker terminal flags are never semantic checks. When a case has no
    independent supported oracle yet, the missing capability is recorded
    instead of being approximated with `edit_made` or `navigation_performed`.
    """
    case_id = str(case.get("id"))
    if case.get("kind") == "navigation":
        info_path = fixture_root / "informational" / "fixture.json"
        try:
            info = load_json(info_path)
        except SetupError:
            return [{"id": f"{case_id.lower()}_semantic_oracle_unavailable",
                     "check": "semantic_oracle_unavailable"}]
        fixture_case = next((row for row in _mapping(info).get("cases", [])
                             if isinstance(row, Mapping) and row.get("id") == case_id), {})
        catalog = _mapping(_mapping(info).get("targets"))
        source = _mapping(info.get("source"))

        def resolve(alias: str) -> Any:
            value: Any = catalog
            for part in alias.split("."):
                value = value.get(part) if isinstance(value, Mapping) else None
            return value

        checks: list[dict[str, Any]] = []
        if case_id == "L01":
            target = _mapping(resolve("intro_b01"))
            media_handles = target.get("media_handles", [])
            media = next((row.get("media_id") for row in media_handles
                          if isinstance(row, Mapping) and row.get("role") == "selected_image"), None)
            expected = {
                "head_revision_id": source.get("head"),
                "selected_image_media_id": media,
            }
            checks = [
                {"id": f"l01_{name}", "check": "path_equals", "artifact": "result",
                 "path": f"observations.{name}", "expected": value}
                for name, value in expected.items() if value is not None
            ]
        elif case_id == "L02":
            aliases = ["intro_b01", "ideas_b03"]
            expected = []
            for alias in aliases:
                target = _mapping(resolve(alias))
                image = next((item.get("media_id") for item in target.get("media_handles", [])
                              if isinstance(item, Mapping) and item.get("role") == "selected_image"), None)
                expected.append({
                    "occurrence_id": target.get("occurrence_id"),
                    "shot_id": target.get("shot_id"),
                    "shot_revision_id": target.get("shot_revision_id"),
                    "internal_timeline_revision_id": target.get("internal_timeline_revision_id"),
                    "selected_image_media_id": image,
                })
            # The public task asks the worker to expand *one* occurrence.  The
            # fixture admits either target, so require one complete identity
            # projection from the target set.  ``records_include`` compares
            # only these required identity fields and intentionally accepts
            # useful derived/nested fields in the worker's projection.
            checks = [{"id": "l02_expanded_identities", "check": "records_include",
                       "artifact": "result", "path": "observations.expanded_occurrences",
                       "mode": "any", "expected": expected}]
        elif case_id == "L03":
            collection = load_json(fixture_root / "action" / "A09-images.json")
            expected_ids = [row.get("media_id") for row in collection.get("images", [])
                            if isinstance(row, Mapping)]
            expected_cues = collection.get("cue_times_seconds", [])
            checks = [
                {"id": "l03_montage_collection", "check": "path_equals", "artifact": "result",
                 "path": "observations.montage_media_ids", "expected": expected_ids},
                {"id": "l03_supplied_cue_times", "check": "path_equals", "artifact": "result",
                 "path": "observations.music_cue_times_seconds", "expected": expected_cues},
            ]
        elif case_id == "L06":
            candidate_path = fixture_root / "informational" / "L06-stale-invalid-candidate.json"
            candidate = load_json(candidate_path)
            diagnostic = _mapping(candidate.get("diagnostic"))
            checks = [
                {"id": "l06_diagnostic_status", "check": "path_equals", "artifact": "result",
                 "path": "observations.diagnostic.status", "expected": diagnostic.get("status")},
                {"id": "l06_diagnostic_error", "check": "path_equals", "artifact": "result",
                 "path": "observations.diagnostic.error_type", "expected": diagnostic.get("error_type")},
                {"id": "l06_diagnostic_base", "check": "path_equals", "artifact": "result",
                 "path": "observations.diagnostic.base_parent_revision_id",
                 "expected": diagnostic.get("base_parent_revision_id")},
            ]
        elif case_id == "L08":
            target = _mapping(resolve("authored_segment_text"))
            expected_titles = [row.get("text") for row in target.get("segments", [])
                               if isinstance(row, Mapping)]
            checks = [
                {"id": "l08_exact_segment_titles", "check": "path_equals", "artifact": "result",
                 "path": "observations.available_segment_titles", "expected": expected_titles},
                {"id": "l08_missing_roles", "check": "path_equals", "artifact": "result",
                 "path": "observations.missing_text_roles", "expected": target.get("missing_roles", [])},
            ]
        if checks:
            return checks
        return [{"id": f"{case_id.lower()}_semantic_oracle_unavailable",
                 "check": "semantic_oracle_unavailable"}]

    action_manifest = fixture_root / "action" / "manifest.json"
    manifest: Mapping[str, Any] = {}
    if action_manifest.is_file():
        try:
            manifest = load_json(action_manifest)
        except SetupError:
            return [{"id": f"{case_id.lower()}_semantic_oracle_unavailable",
                     "check": "semantic_oracle_unavailable"}]
    else:
        return [{"id": f"{case_id.lower()}_semantic_oracle_unavailable",
                 "check": "semantic_oracle_unavailable"}]
    rows = manifest.get("cases", []) if isinstance(manifest, Mapping) else []
    fixture_case = next((row for row in rows if isinstance(row, Mapping) and row.get("id") == case_id), {})
    targets = _mapping(fixture_case).get("targets", {})
    if case_id == "A01":
        media = _mapping(fixture_case).get("media", {})
        expected_digest = media.get("new_image_digest")
        if not isinstance(expected_digest, str) or not expected_digest:
            raise SetupError("A01 private manifest must provide media.new_image_digest")
        checks: list[dict[str, Any]] = [{
            "id": "a01_target_selector",
            "check": "path_equals",
            "artifact": "after",
            "path": "target.selector_clip_id",
            "expected": targets.get("selector_clip_id", "shot_b01"),
        }]
        checks.append({
            "id": "a01_target_active_media",
            "check": "path_equals",
            "artifact": "after",
            "path": "target.active_media_digest",
            "expected": expected_digest,
        })
        checks.append({
            "id": "a01_target_timing_and_protected_roles",
            "check": "paths_unchanged",
            "paths": [
                "target.timing.at",
                "target.timing.hold",
                "target.timing.occurrence_duration_ms",
                "target.timing.occurrence_start_ms",
                "target.voice_clip_id",
                "target.frame_overlay_clip_id",
                "target.voice.asset",
                "target.voice.media_digest",
                "target.voice.at",
                "target.voice.from",
                "target.voice.to",
                "target.voice.track",
                "target.voice.volume",
                "target.frame_overlay.asset",
                "target.frame_overlay.media_digest",
                "target.frame_overlay.at",
                "target.frame_overlay.hold",
                "target.frame_overlay.track",
            ],
        })
        return checks
    if case_id == "A03":
        original = list(targets.get("four_occurrences_in_order", ()))
        if len(original) == 4:
            closing = targets.get("closing_occurrence")
            middle = targets.get("middle_occurrence")
            # The fixture order is [opening, second, middle, closing]. Move
            # closing immediately before middle, preserving every other slot.
            expected = [original[0], original[1], closing, middle] if closing and middle else []
            if expected:
                return [{
                    "id": "a03_order",
                    "check": "order",
                    "artifact": "after",
                    "path": "occurrences",
                    "id_path": "occurrence_id",
                    "expected_ids": expected,
                }]
    if case_id == "A04":
        return [{
            "id": "a04_identity_disjoint",
            "check": "identity_disjoint",
            "before_artifact": "before",
            "after_artifact": "after",
            "original_ids_path": "identity_ids",
            "duplicate_ids_path": "duplicate.identity_ids",
        }]
    if case_id == "A09":
        return [{
            "id": "a09_panel_coverage",
            "check": "panel_coverage",
            "artifact": "after",
            "path": "panels",
            "required": ["top-left", "top-right", "bottom-right", "bottom-left"],
            "width": 1,
            "height": 1,
            "label_path": "quadrant",
            "rect_path": "rect",
        }]
    if case_id == "A10":
        collection_path = fixture_root / "action" / "A10-brightness-collection.json"
        if collection_path.is_file():
            try:
                collection = load_json(collection_path)
                images = collection.get("images", []) if isinstance(collection, Mapping) else []
                expected = [row.get("media_id") for row in images if isinstance(row, Mapping) and row.get("media_id")]
                if len(expected) == 200:
                    return [{
                        "id": "a10_brightness_order",
                        "check": "order",
                        "artifact": "after",
                        "path": "montage.clips",
                        "id_path": "media_id",
                        "expected_ids": expected,
                    }]
            except SetupError:
                pass
    return [{"id": f"{case_id.lower()}_semantic_oracle_unavailable",
             "check": "semantic_oracle_unavailable"}]


def _fixture_blocked_result(
    case: Mapping[str, Any], *, attempt_id: str, reason: str, case_dir: Path
) -> dict[str, Any]:
    session_id = f"{attempt_id}-{case['id']}-not-launched"
    result = {
        "kind": "astrid.timeline-eval.agent-result.v1",
        "attempt_id": attempt_id,
        "case_id": str(case["id"]),
        "session_id": session_id,
        "fresh_context": False,
        "agent_status": "fixture_blocked",
        "launcher_process_status": "not_started",
        "execution_status": "not_started",
        "elapsed_seconds": 0.0,
        "tool_calls": 0,
        "retries": 0,
        "clarification_needed": False,
        "fixture_or_agent_failure": "fixture",
        "failure_cause": {"setup": [reason], "summary": reason},
    }
    _write_json(case_dir / "result.json", result)
    _trace_lines(case_dir, events=[{
        "event": "fixture_blocked",
        "at": _now(),
        "case_id": str(case["id"]),
        "reason": reason,
    }])
    return result


def run_attempt(
    suite_path: Path = DEFAULT_SUITE,
    attempt_root: Path | None = None,
    *,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
    briefs_path: Path = DEFAULT_BRIEFS,
    omp_bin: str = "omp",
    model: str = DEFAULT_MODEL,
    thinking: str = DEFAULT_THINKING,
    execute: bool = True,
    launchable_ids: Collection[str] | None = None,
    case_id: str | None = None,
    isolated_endpoint: str | None = None,
    isolated_credential: Path | None = None,
    isolation_contract: Path | None = None,
    prepared_targets_root: Path | None = None,
    fixture_only: bool = False,
    local_disposable: bool | None = None,
    admission_mode: str = "scored",
    source_reader: Any | None = None,
    runtime_contracts: Mapping[str, CaseRuntimeContract] | None = None,
    boundary_supervisor: BoundarySupervisor | None = None,
    boundary_requirements: Mapping[str, BoundaryRequirements] | None = None,
) -> dict[str, Any]:
    """Run and aggregate one immutable suite attempt.

    ``launchable_ids`` is an explicit test seam for fake adapters; normal
    callers leave it unset and use the fixture manifest's readiness result.
    It is rejected for production execution because it bypasses readiness.
    ``case_id`` is the production selector: when supplied, the original suite
    metadata remains pinned but only that case is prepared/launched. Selection
    never changes the fixture-readiness decision.
    """
    source_suite = load_json(suite_path)
    if not isinstance(source_suite, Mapping) or not isinstance(source_suite.get("cases"), list) or not source_suite["cases"]:
        raise NativeLauncherError("suite must contain a non-empty cases array")
    suite = dict(source_suite)
    source_cases = list(source_suite["cases"])
    selected_case_id: str | None = None
    if case_id is not None:
        selected_case_id = _safe_case_id(case_id)
        selected = [
            row for row in source_cases
            if isinstance(row, Mapping) and str(row.get("id")) == selected_case_id
        ]
        if len(selected) != 1:
            raise NativeLauncherError(
                f"selected case is not present exactly once in suite: {selected_case_id}"
            )
        suite["cases"] = selected
    else:
        suite["cases"] = source_cases
    if launchable_ids is not None and not fixture_only:
        raise NativeLauncherError(
            "launchable_ids is test-only and cannot bypass production fixture readiness"
        )
    if attempt_root is None:
        raise NativeLauncherError("an explicit fresh attempt root is required")
    if thinking not in {"off", "minimal", "low", "medium", "high", "xhigh", "max", "auto"}:
        raise NativeLauncherError(f"unsupported OMP thinking level: {thinking}")
    if admission_mode not in {"scored", "diagnostic"}:
        raise NativeLauncherError(f"unsupported admission mode: {admission_mode}")
    # Local disposable execution is the normal authority.  The typed host
    # boundary remains available only when a caller explicitly supplies both
    # its supervisor and per-case requirements.
    host_boundary_mode = (
        execute and not fixture_only
        and local_disposable is not True
        and boundary_supervisor is not None
        and boundary_requirements is not None
    )
    attempt_root = attempt_root.expanduser().absolute()
    if attempt_root.exists():
        if attempt_root.is_symlink() or not attempt_root.is_dir() or any(attempt_root.iterdir()):
            raise NativeLauncherError(f"attempt root must be new and non-symlink: {attempt_root}")
    attempt_root.mkdir(parents=True, exist_ok=True)
    cases_root = attempt_root / "cases"
    cases_root.mkdir()
    attempt_id = attempt_root.name
    public_briefs = _load_public_briefs(briefs_path)
    try:
        skill_reference: Mapping[str, str] = _skill_reference()
        skill_setup_error: str | None = None
    except (NativeLauncherError, OSError, UnicodeError) as exc:
        skill_reference = {}
        skill_setup_error = f"{type(exc).__name__}: {exc}"
    readiness = {row.case_id: row for row in build_readiness(suite_path, fixture_root)}
    forced = set(launchable_ids) if launchable_ids is not None else None
    fingerprints = _attempt_fingerprints(fixture_root, suite_path, briefs_path, skill_reference)
    selected_fingerprints = {
        str(row["id"]): hashlib.sha256(json.dumps(
            row, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        for row in suite["cases"]
        if isinstance(row, Mapping) and row.get("id")
    }
    fingerprints["selected_cases"] = selected_fingerprints
    fingerprint_sha256 = hashlib.sha256(json.dumps(
        fingerprints, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    top_level = {
        "kind": ATTEMPT_RESULT_KIND,
        "attempt_id": attempt_id,
        "suite_id": suite.get("suite_id"),
        "suite_version": suite.get("suite_version"),
        "model": model,
        "model_binding": {
            "requested_model": model,
            "resolved_model": model,
            "resolution": "fully-qualified OMP model binding; provider-side alias resolution is not separately exposed",
            "reasoning": thinking,
        },
        "fresh_context_per_case": True,
        "execution_order": "sequential",
        "case_count": len(suite["cases"]),
        "suite_case_count": len(source_cases),
        "selection": {
            "case_id": selected_case_id,
            "selected_case_ids": sorted(selected_fingerprints),
            "selected_case_fingerprints": dict(selected_fingerprints),
            "readiness_source": str(suite_path),
        },
        "started_at": _now(),
        "canonical_fallback_available": False,
        "skill_reference": dict(skill_reference),
        "fingerprints": fingerprints,
        "fingerprint_sha256": fingerprint_sha256,
        "execution": "native_omp" if execute else "dry_run",
        "admission_mode": admission_mode,
        "isolation": {
            "mode": "host_boundary" if host_boundary_mode else "local_disposable",
            "fixture_only": fixture_only,
            "endpoint": isolated_endpoint if host_boundary_mode else None,
            "credential": str(isolated_credential) if host_boundary_mode and isolated_credential else None,
            "contract": str(isolation_contract) if host_boundary_mode else None,
        },
    }
    _write_json(attempt_root / "attempt.json", top_level)
    if not execute:
        plan = []
        for case in suite["cases"]:
            case_id = _safe_case_id(_mapping(case).get("id"))
            row = readiness.get(case_id)
            plan.append({
                "case_id": case_id,
                "fixture_ready": bool(row and row.readiness == "fixture_ready"),
                "case_fingerprint_sha256": selected_fingerprints.get(case_id),
            })
        top_level["plan"] = plan
        _write_json(attempt_root / "attempt.json", top_level)
        return top_level

    for raw_case in suite["cases"]:
        if not isinstance(raw_case, Mapping) or not raw_case.get("id"):
            raise NativeLauncherError("every suite case must be an object with an id")
        case = dict(raw_case)
        case_id = _safe_case_id(case["id"])
        selected_runtime = (runtime_contracts or {}).get(case_id)
        case_endpoint = selected_runtime.endpoint if selected_runtime else isolated_endpoint
        case_credential = selected_runtime.credential if selected_runtime else isolated_credential
        case_isolation_contract = (
            selected_runtime.isolation_contract if selected_runtime else isolation_contract
        )
        case_source_reader = selected_runtime.source_reader if selected_runtime else source_reader
        case_dir = cases_root / case_id
        case_dir.mkdir()
        case_boundary_requirements = (boundary_requirements or {}).get(case_id)
        case_skill_reference = dict(skill_reference)
        if not fixture_only and isinstance(case_boundary_requirements, BoundaryRequirements):
            # The coordinator checkout path is private. Workers receive only
            # the public package path inside their own boundary.
            case_skill_reference["path"] = case_boundary_requirements.skill_path
        target_setup_error: str | None = None
        prepared_target: Mapping[str, Any] | None = None
        should_prepare_target = prepared_targets_root is not None and (
            case_id == "A01"
            or (
                not prepared_targets_root.expanduser().absolute().is_symlink()
                and prepared_targets_root.expanduser().absolute().is_dir()
                and not (prepared_targets_root.expanduser().absolute() / case_id).is_symlink()
                and (prepared_targets_root.expanduser().absolute() / case_id / "target.json").is_file()
                and not (prepared_targets_root.expanduser().absolute() / case_id / "target.json").is_symlink()
            )
        )
        if should_prepare_target:
            try:
                prepared_target = _prepare_public_target(
                    prepared_targets_root, case_id=case_id, case_dir=case_dir,
                )
            except (NativeLauncherError, SetupError) as exc:
                target_setup_error = str(exc)
        runtime_project_id = str(
            _mapping(prepared_target).get("project_id")
            if isinstance(prepared_target, Mapping) and _mapping(prepared_target).get("project_id")
            else _mapping(public_briefs.get(case_id)).get("runtime_project_id")
            or _local_runtime_project_id(attempt_id, case_id)
        )
        entrypoint_error: str | None = None
        if case.get("kind") == "navigation":
            try:
                materialize_public_navigation_entrypoint(
                    case_id, fixture_root=fixture_root, destination=case_dir,
                )
            except (FixtureError, OSError, ValueError, json.JSONDecodeError) as exc:
                entrypoint_error = f"{type(exc).__name__}: {exc}"
        if target_setup_error is None and entrypoint_error is not None:
            target_setup_error = f"selected navigation entry point could not be prepared: {entrypoint_error}"
        _write_json(case_dir / "brief.json", _public_brief(
            case, public_briefs.get(case_id), fixture_root=fixture_root, case_dir=case_dir,
            skill_reference=case_skill_reference,
            runtime_project_id=runtime_project_id,
            worker_case_path=(
                case_boundary_requirements.selected_case_path
                if not fixture_only and isinstance(case_boundary_requirements, BoundaryRequirements)
                else None
            ),
        ))
        checks_setup_error: str | None = None
        try:
            hidden_checks = _hidden_checks(case, fixture_root=fixture_root)
        except SetupError as exc:
            # A malformed private manifest is coordinator setup failure.  It
            # must never turn into a model launch or an agent failure.
            hidden_checks = []
            checks_setup_error = str(exc)
        row = readiness.get(case_id)
        is_ready = bool(row and row.readiness == "fixture_ready")
        if forced is not None:
            is_ready = case_id in forced
        if not is_ready:
            reason = "; ".join(row.reasons) if row and row.reasons else "fixture readiness was not established"
            session_id = f"{attempt_id}-{case_id}-not-launched"
            _write_json(case_dir / "attempt.json", {
                "kind": ATTEMPT_KIND,
                "attempt_id": attempt_id,
                "case_id": case_id,
                "fresh_context": False,
                "session_id": session_id,
                "started_at": _now(),
                "model": model,
                "thinking": thinking,
                "fingerprint_sha256": fingerprint_sha256,
                "case_fingerprint_sha256": selected_fingerprints.get(case_id),
                "execution": "fixture_blocked",
            })
            _fixture_blocked_result(case, attempt_id=attempt_id, reason=reason, case_dir=case_dir)
            _write_json(case_dir / "checks.json", hidden_checks)
            continue
        if target_setup_error is not None:
            _write_json(case_dir / "attempt.json", {
                "kind": ATTEMPT_KIND,
                "attempt_id": attempt_id,
                "case_id": case_id,
                "fresh_context": False,
                "session_id": f"{attempt_id}-{case_id}-not-launched",
                "started_at": _now(),
                "model": model,
                "thinking": thinking,
                "fingerprint_sha256": fingerprint_sha256,
                "case_fingerprint_sha256": selected_fingerprints.get(case_id),
                "execution": "setup_failed",
            })
            _setup_failed_case(case, attempt_id=attempt_id, case_dir=case_dir, reason=target_setup_error)
            _write_json(case_dir / "checks.json", hidden_checks)
            continue
        if checks_setup_error is not None:
            _write_json(case_dir / "attempt.json", {
                "kind": ATTEMPT_KIND,
                "attempt_id": attempt_id,
                "case_id": case_id,
                "fresh_context": False,
                "session_id": f"{attempt_id}-{case_id}-not-launched",
                "started_at": _now(),
                "model": model,
                "thinking": thinking,
                "fingerprint_sha256": fingerprint_sha256,
                "case_fingerprint_sha256": selected_fingerprints.get(case_id),
                "execution": "setup_failed",
            })
            _setup_failed_case(case, attempt_id=attempt_id, case_dir=case_dir, reason=checks_setup_error)
            _write_json(case_dir / "checks.json", hidden_checks)
            continue
        if skill_setup_error is not None:
            _write_json(case_dir / "attempt.json", {
                "kind": ATTEMPT_KIND,
                "attempt_id": attempt_id,
                "case_id": case_id,
                "fresh_context": False,
                "session_id": f"{attempt_id}-{case_id}-not-launched",
                "started_at": _now(),
                "model": model,
                "thinking": thinking,
                "fingerprint_sha256": fingerprint_sha256,
                "case_fingerprint_sha256": selected_fingerprints.get(case_id),
                "execution": "setup_failed",
                "skill_error": skill_setup_error,
            })
            _setup_failed_case(case, attempt_id=attempt_id, case_dir=case_dir, reason=skill_setup_error)
            _write_json(case_dir / "checks.json", hidden_checks)
            continue
        if host_boundary_mode and case_id == "A01" and prepared_targets_root is None:
            reason = (
                "A01 setup failed: prepared_targets_root is missing; "
                "disposable target A01/target.json was not prepared"
            )
            _write_json(case_dir / "attempt.json", {
                "kind": ATTEMPT_KIND,
                "attempt_id": attempt_id,
                "case_id": case_id,
                "fresh_context": False,
                "session_id": f"{attempt_id}-{case_id}-not-launched",
                "started_at": _now(),
                "model": model,
                "thinking": thinking,
                "fingerprint_sha256": fingerprint_sha256,
                "case_fingerprint_sha256": selected_fingerprints.get(case_id),
                "execution": "setup_failed",
            })
            _setup_failed_case(case, attempt_id=attempt_id, case_dir=case_dir, reason=reason)
            _write_json(case_dir / "checks.json", hidden_checks)
            continue
        public_target = prepared_target or _load_public_target(case_dir)
        if host_boundary_mode and case.get("kind") == "action":
            edit_capability = _mapping(_mapping(public_target).get("capabilities")).get("edit")
            if not isinstance(edit_capability, Mapping) or edit_capability.get("status") != "available":
                reason = _action_target_block_reason(case_id, public_target)
                _write_json(case_dir / "attempt.json", {
                    "kind": ATTEMPT_KIND,
                    "attempt_id": attempt_id,
                    "case_id": case_id,
                    "fresh_context": False,
                    "session_id": f"{attempt_id}-{case_id}-not-launched",
                    "started_at": _now(),
                    "model": model,
                    "execution": "fixture_blocked",
                })
                _fixture_blocked_result(case, attempt_id=attempt_id, reason=reason, case_dir=case_dir)
                _write_json(case_dir / "checks.json", hidden_checks)
                continue
        boundary_receipt: BoundaryReceipt | None = None
        model_boundary_id: str | None = None
        if host_boundary_mode:
            requirements = case_boundary_requirements
            try:
                if not isinstance(requirements, BoundaryRequirements):
                    raise BoundaryUnavailable(
                        "no typed host boundary requirements were supplied for this selected case"
                    )
                if (
                    requirements.case_id != case_id
                    or Path(requirements.host_selected_case_path).resolve() != case_dir.resolve()
                    or requirements.skill_sha256 != skill_reference.get("sha256")
                    or (
                        requirements.execution_mode == "runtime_edit"
                        and requirements.disposable_endpoint != case_endpoint
                    )
                    or (
                        requirements.execution_mode == "offline"
                        and any((case_endpoint, case_credential, case_isolation_contract))
                    )
                ):
                    raise BoundaryUnavailable(
                        "host boundary requirements do not match case path or pinned skill hash"
                    )
                requirements = pin_worker_boundary(boundary_supervisor, requirements)
                case_boundary_requirements = requirements
                boundary_receipt = prove_worker_boundary(boundary_supervisor, requirements)
                model_boundary_id = boundary_receipt.boundary_id
            except (BoundaryUnavailable, TypeError, ValueError, OSError) as exc:
                reason = f"active worker boundary preflight failed; refusing model launch: {exc}"
                _write_json(case_dir / "attempt.json", {
                    "kind": ATTEMPT_KIND,
                    "attempt_id": attempt_id,
                    "case_id": case_id,
                    "fresh_context": False,
                    "session_id": f"{attempt_id}-{case_id}-not-launched",
                    "started_at": _now(),
                    "model": model,
                    "thinking": thinking,
                    "fingerprint_sha256": fingerprint_sha256,
                    "case_fingerprint_sha256": selected_fingerprints.get(case_id),
                    "execution": "setup_failed",
                    "boundary_error": reason,
                })
                _setup_failed_case(case, attempt_id=attempt_id, case_dir=case_dir, reason=reason)
                _write_json(case_dir / "checks.json", hidden_checks)
                continue
        session_id = f"{attempt_id}-{case_id}-{uuid.uuid4().hex[:12]}"
        started_at = _now()
        _write_json(case_dir / "attempt.json", {
            "kind": ATTEMPT_KIND,
            "attempt_id": attempt_id,
            "case_id": case_id,
            "fresh_context": True,
            "session_id": session_id,
            "started_at": started_at,
            "model": model,
            "thinking": thinking,
            "model_boundary_id": model_boundary_id,
            "fingerprint_sha256": fingerprint_sha256,
            "case_fingerprint_sha256": selected_fingerprints.get(case_id),
            "target_receipt_sha256": hashlib.sha256(json.dumps(
                public_target, sort_keys=True, separators=(",", ":"),
            ).encode("utf-8")).hexdigest() if public_target is not None else None,
            "entrypoint_sha256": _sha256_file(case_dir / "entrypoint" / "entrypoint.json"),
            "execution": "native_omp",
        })
        # A seeded native case may expose a public target.json. Read its exact
        # current closure before launching the model, but keep the snapshot
        # coordinator-private until the process exits. The agent's brief and
        # self-report are never a substitute for this readback.
        readback_adapter: Any | None = None
        readback_contract: ReadbackContract | None = None
        before_observation: ReadbackObservation | None = None
        readback_error: str | None = None
        if public_target is not None and host_boundary_mode:
            try:
                target_endpoint = public_target.get("endpoint")
                if case_endpoint and target_endpoint and target_endpoint != case_endpoint:
                    raise IndependentReadbackError("public target endpoint differs from requested disposable endpoint")
                readback_adapter = _connect_readback_adapter(
                    endpoint=case_endpoint,
                    credential=case_credential,
                    contract=case_isolation_contract,
                )
                readback_contract = _readback_contract(case, public_target, fixture_root)
                before_observation = observe_case_before(
                    readback_adapter, public_target, readback_contract,
                    source_reader=case_source_reader,
                )
                if case.get("kind") == "action" and case_id == "A01":
                    _require_a01_protected_roles(before_observation.target)
            except Exception as exc:  # adapter failures are a failed gate, not an agent success
                readback_error = f"{type(exc).__name__}: {exc}"
        if public_target is not None and host_boundary_mode and readback_error is not None:
            reason = f"independent pre-readback failed; refusing to launch OMP: {readback_error}"
            _write_json(case_dir / "attempt.json", {
                "kind": ATTEMPT_KIND,
                "attempt_id": attempt_id,
                "case_id": case_id,
                "fresh_context": False,
                "session_id": f"{attempt_id}-{case_id}-not-launched",
                "started_at": started_at,
                "model": model,
                "execution": "setup_failed",
            })
            _setup_failed_case(case, attempt_id=attempt_id, case_dir=case_dir, reason=reason)
            _write_json(case_dir / "checks.json", hidden_checks)
            continue
        status, returncode, elapsed, events, output = _invoke(
            omp_bin=omp_bin,
            model=model,
            thinking=thinking,
            model_boundary_id=model_boundary_id,
            case=case,
            case_dir=case_dir,
            isolated_endpoint=case_endpoint,
            isolated_credential=case_credential,
            isolation_contract=case_isolation_contract,
            skill_reference=case_skill_reference,
            public_target=public_target,
            fixture_only=fixture_only,
            local_disposable=not host_boundary_mode,
            boundary_supervisor=boundary_supervisor,
            boundary_receipt=boundary_receipt,
            boundary_requirements=(
                case_boundary_requirements
                if isinstance(case_boundary_requirements, BoundaryRequirements) else None
            ),
        )
        _trace_lines(case_dir, events=events)
        merged_result = _merge_result(
            case_dir,
            case=case,
            attempt_id=attempt_id,
            session_id=session_id,
            status=status,
            returncode=returncode,
            elapsed=elapsed,
            output=output,
            model=model,
            thinking=thinking,
            model_boundary_id=model_boundary_id,
        )
        # Coordinator metadata, never a worker-authored semantic claim.
        merged_result["admission_mode"] = admission_mode
        readback_result: Mapping[str, Any] | None = None
        final_capture: Mapping[str, Any] | None = None
        if host_boundary_mode:
            capture_path = attempt_root / "coordinator" / "cases" / case_id / "host-final-capture.json"
            try:
                final_capture = load_json(capture_path)
            except SetupError as exc:
                readback_error = readback_error or f"host final capture unavailable: {exc}"
        if public_target is not None and host_boundary_mode and readback_error is None:
            try:
                if not isinstance(final_capture, Mapping):
                    raise IndependentReadbackError("host final capture is unavailable")
                readback_adapter = _CapturedClosureReader(final_capture)
                publication_response = merged_result.get("publication_response")
                publication = (
                    _publication_payload(publication_response)
                    if isinstance(publication_response, Mapping) else None
                )
                if before_observation is None or readback_contract is None:
                    raise ProjectionUnavailable("before observation or readback contract is unavailable")
                case_readback = _verify_projected_readback(
                    reader=readback_adapter,
                    target=public_target,
                    contract=readback_contract,
                    before=before_observation,
                    publication=publication,
                    source_reader=case_source_reader,
                )
                readback_result = case_readback.as_dict()
                if case_id == "A01" and isinstance(case_readback.after, Mapping):
                    _require_a01_protected_roles(case_readback.after)
            except Exception as exc:  # noqa: BLE001 - adapter boundary is external
                readback_error = f"{type(exc).__name__}: {exc}"
        if readback_result is None:
            unavailable_safety = {
                "source_unchanged": None,
                "test_target_only": None,
            }
            if case.get("kind") == "navigation":
                unavailable_safety["read_only_target"] = None
            readback_result = {
                "status": "unavailable",
                "before_observed": before_observation is not None,
                "after_observed": False,
                "safety": unavailable_safety,
                "reasons": (readback_error or "independent readback unavailable",),
            }
        # Convert the sealed host capture into the generic coordinator
        # evidence pack. The capture is already post-teardown; no worker
        # result or self-authored after-state is used as Runtime authority.
        coordinator_evidence_error: str | None = None
        if host_boundary_mode and isinstance(final_capture, Mapping) and boundary_receipt is not None:
            try:
                capture_teardown = teardown_receipt_from_host_capture(final_capture)
                capture_reader = _CapturedClosureReader(final_capture)
                brief_value: Mapping[str, Any] | None = None
                try:
                    candidate_brief = load_json(case_dir / "brief.json")
                    if isinstance(candidate_brief, Mapping):
                        brief_value = candidate_brief
                except SetupError:
                    brief_value = None
                publication_response = merged_result.get("publication_response")
                publication = (
                    _publication_payload(publication_response)
                    if isinstance(publication_response, Mapping) else None
                )
                collect_case_evidence(
                    case_id=case_id,
                    case_dir=case_dir,
                    evidence_root=attempt_root / "coordinator" / "cases" / case_id / "evidence",
                    brief=brief_value,
                    fingerprints=fingerprints,
                    transcript=output,
                    final_response=output,
                    worker_result=merged_result,
                    target=public_target if isinstance(public_target, Mapping) else None,
                    reader=capture_reader if isinstance(public_target, Mapping) else None,
                    before=before_observation,
                    publication=publication,
                    teardown=capture_teardown,
                    expected_realm_id=getattr(boundary_receipt, "disposable_realm_id", None),
                    media_root=case_dir / "media",
                    worker_state=merged_result,
                )
            except (EvidenceCollectionError, OSError, TypeError, ValueError) as exc:
                coordinator_evidence_error = f"{type(exc).__name__}: {exc}"
        if before_observation is not None:
            _write_json(case_dir / "before.json", {"target": before_observation.target})
        if isinstance(readback_result.get("after"), Mapping):
            _write_json(case_dir / "after.json", {"target": readback_result["after"]})
        if host_boundary_mode:
            coordinator_path = attempt_root / "coordinator" / "cases" / case_id / "readback.json"
            _write_json(coordinator_path, {
                "kind": "astrid.timeline-eval.coordinator-evidence.v1",
                "case_id": case_id,
                "readback": dict(readback_result),
                "safety": dict(_mapping(readback_result.get("safety"))),
                "boundary": boundary_receipt.as_dict() if boundary_receipt else None,
                "host_final_capture": dict(final_capture) if final_capture else None,
                "generic_evidence_error": coordinator_evidence_error,
            })
        # Only worker-authored fields remain in result.json. The coordinator's
        # exact readback/safety sidecar is written outside the worker result
        # after process exit and is consumed separately by aggregate_attempt.
        _write_json(case_dir / "result.json", merged_result)
        # Hidden checks are deliberately installed only after the agent exits.
        _write_json(case_dir / "checks.json", hidden_checks)

    aggregate = aggregate_attempt(suite, attempt_root)
    _write_json(attempt_root / "aggregate.json", aggregate)
    top_level["finished_at"] = _now()
    top_level["aggregate"] = "aggregate.json"
    _write_json(attempt_root / "attempt.json", top_level)
    return aggregate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    parser.add_argument("--briefs", type=Path, default=DEFAULT_BRIEFS)
    parser.add_argument("--attempt-root", type=Path, required=True)
    parser.add_argument(
        "--case", dest="case_id",
        help="run exactly one suite case while retaining the original suite/version metadata",
    )
    parser.add_argument("--omp-bin", default="omp", help="OMP executable (default: omp)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--thinking", default=DEFAULT_THINKING,
                        choices=("off", "minimal", "low", "medium", "high", "xhigh", "max", "auto"))
    parser.add_argument("--isolated-endpoint", help="explicit disposable Runtime endpoint")
    parser.add_argument("--isolated-credential", type=Path,
                        help="credential file for the disposable Runtime")
    parser.add_argument("--isolation-contract", type=Path,
                        help="JSON proof of the disposable Runtime boundary")
    parser.add_argument("--prepared-targets-root", type=Path,
                        help="coordinator-owned root containing <case-id>/target.json public receipts")
    parser.add_argument("--fixture-only", action="store_true",
                        help="test-only fake adapter mode; never use for a native model run")
    parser.add_argument(
        "--execution-mode", choices=("local-disposable", "host-boundary"),
        default="local-disposable",
        help="authoritative worker launch mode (default: local-disposable)",
    )
    parser.add_argument("--admission-mode", choices=("scored", "diagnostic"), default="scored",
                        help="diagnostic permits launch without a semantic oracle; scored does not")
    parser.add_argument("--dry-run", action="store_true", help="print a plan without launching any agent")
    args = parser.parse_args(argv)
    try:
        result = run_attempt(
            args.suite,
            args.attempt_root,
            fixture_root=args.fixture_root,
            briefs_path=args.briefs,
            omp_bin=args.omp_bin,
            model=args.model,
            thinking=args.thinking,
            execute=not args.dry_run,
            case_id=args.case_id,
            isolated_endpoint=args.isolated_endpoint,
            isolated_credential=args.isolated_credential,
            isolation_contract=args.isolation_contract,
            prepared_targets_root=args.prepared_targets_root,
            fixture_only=args.fixture_only,
            local_disposable=(args.execution_mode == "local-disposable"),
            admission_mode=args.admission_mode,
        )
    except (NativeLauncherError, OSError, ValueError) as exc:
        print(json.dumps({"status": "setup_failed", "error": str(exc)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.dry_run:
        return 0
    return 0 if result.get("complete") and result.get("passed") == result.get("case_count") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
