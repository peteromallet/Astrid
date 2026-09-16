#!/usr/bin/env python3
"""Bounded reproducer for concurrent Astrid runtime acquisition.

The default fixture uses a tiny launcher instead of the operator's live support
directory.  ``--launcher pinned`` exercises the installed pinned
``banodoco-local`` against a disposable absolute support root and the
canonical source manifest.  Both modes exercise Astrid's real
``ensure_runtime`` boundary and record only bounded lifecycle metadata.

The harness does *not* render a timeline or start a pack host.  That is
intentional: lifecycle failure must be distinguishable from worker readiness
and visualization/render failure rather than being reported as one generic
failure.  A separate explicit-client test covers the no-bootstrap path.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import time
from typing import Any


_LAUNCHER = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time

args = sys.argv[1:]
root = Path(args[args.index("--data-root") + 1])
state = root / "fixture-state"
state.mkdir(parents=True, exist_ok=True)
owner = state / "owner.json"
starting = state / "startup.claim"
events = state / "events.jsonl"
discovery = {
    "status": "started",
    "realm_id": "fixture-realm",
    "endpoint": "http://127.0.0.1:43123",
    "actor_id": "fixture-actor",
    "runtime_instance_id": "fixture-instance",
}

if owner.exists():
    value = json.loads(owner.read_text())
    value["status"] = "reconnected"
    with events.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"code": "reconnected"}) + "\n")
    print(json.dumps(value), flush=True)
    raise SystemExit(0)

try:
    # mkdir is the portable atomic claim used only by this fixture.  The real
    # runtime uses its support mutex and owner lock for the same authority.
    starting.mkdir()
except FileExistsError:
    with events.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"code": "startup_in_progress"}) + "\n")
    print(json.dumps({
        "ok": False,
        "error": {
            "code": "startup_in_progress",
            "message": "another caller owns runtime admission",
        },
    }), flush=True)
    raise SystemExit(1)

# Keep the startup window long enough for all bounded callers to overlap.
time.sleep(0.15)
value = dict(discovery)
owner.write_text(json.dumps(value))
with events.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps({"code": "started"}) + "\n")
print(json.dumps(value), flush=True)
'''


def _worker_code(data_root: Path, launcher: Path) -> str:
    return textwrap.dedent(
        f"""
        import json
        from astrid.sdk import autobootstrap
        try:
            value = autobootstrap.ensure_runtime(
                start_pack_host=False,
                data_root={str(data_root)!r},
            )
            print(json.dumps({{"ok": True, "result": dict(value)}}))
        except Exception as exc:
            print(json.dumps({{
                "ok": False,
                "error": {{
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "next_action": getattr(exc, "next_action", None),
                }},
            }}))
        """
    )


def _run(
    mode: str,
    callers: int,
    launcher_mode: str = "fixture",
    source_manifest: Path | None = None,
) -> dict[str, Any]:
    temporary_context = tempfile.TemporaryDirectory(
        prefix="astrid-runtime-reproducer-",
        dir="/private/tmp" if launcher_mode == "pinned" else None,
    )
    with temporary_context as temporary:
        root = Path(temporary)
        data_root = root / "support"
        data_root.mkdir()
        if launcher_mode == "fixture":
            launcher = root / "fixture-launcher.py"
            launcher.write_text(_LAUNCHER, encoding="utf-8")
            launcher.chmod(0o700)
        else:
            launcher = Path("/Users/peteromalley/.pyenv/shims/banodoco-local")
            if not launcher.is_file():
                raise RuntimeError(f"pinned launcher not found: {launcher}")
        state = data_root / "fixture-state"
        if launcher_mode == "fixture":
            state.mkdir()
        if launcher_mode == "fixture" and mode == "warm":
            (state / "owner.json").write_text(
                json.dumps(
                    {
                        "status": "started",
                        "realm_id": "fixture-realm",
                        "endpoint": "http://127.0.0.1:43123",
                        "actor_id": "fixture-actor",
                        "runtime_instance_id": "fixture-instance",
                    }
                ),
                encoding="utf-8",
            )

        environment = os.environ.copy()
        environment["BANODOCO_LOCAL_LAUNCHER"] = str(launcher)
        if launcher_mode == "pinned":
            manifest = source_manifest or Path(__file__).resolve().parents[2] / ".astrid-data/runtime/source-profiles/astrid.json"
            environment["BANODOCO_LOCAL_SOURCE_MANIFEST"] = str(manifest)
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(Path(__file__).resolve().parents[2]), environment.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        command = [sys.executable, "-c", _worker_code(data_root, launcher)]
        seed_outcome: dict[str, Any] | None = None
        if launcher_mode == "pinned" and mode == "warm":
            seed_process = subprocess.run(
                command,
                cwd=str(Path(__file__).resolve().parents[2]),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=30,
            )
            try:
                seed_outcome = json.loads(seed_process.stdout.strip().splitlines()[-1])
            except (IndexError, json.JSONDecodeError):
                seed_outcome = {
                    "ok": False,
                    "error": {
                        "type": "malformed_seed_output",
                        "message": seed_process.stdout[-500:],
                    },
                }
        processes = [
            subprocess.Popen(
                command,
                cwd=str(Path(__file__).resolve().parents[2]),
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(callers)
        ]
        outcomes: list[dict[str, Any]] = []
        for process in processes:
            stdout, stderr = process.communicate(timeout=10)
            try:
                value = json.loads(stdout.strip().splitlines()[-1])
            except (IndexError, json.JSONDecodeError):
                value = {
                    "ok": False,
                    "error": {
                        "type": "malformed_worker_output",
                        "message": stdout[-500:],
                    },
                }
            value["exit_code"] = process.returncode
            if stderr.strip():
                value["stderr_tail"] = stderr[-500:]
            outcomes.append(value)

        owner_metadata = {}
        discovery_path: Path | None = None
        if launcher_mode == "fixture":
            owner_path = state / "owner.json"
            if owner_path.is_file():
                owner_metadata = json.loads(owner_path.read_text(encoding="utf-8"))
        else:
            candidate = data_root / "runtime/discovery.json"
            if candidate.is_file():
                discovery_path = candidate
                owner_metadata = json.loads(candidate.read_text(encoding="utf-8"))
        event_codes = []
        events_path = state / "events.jsonl"
        if launcher_mode == "fixture" and events_path.is_file():
            for line in events_path.read_text(encoding="utf-8").splitlines()[:callers]:
                try:
                    event_codes.append(json.loads(line).get("code"))
                except json.JSONDecodeError:
                    event_codes.append("malformed_event")
        if launcher_mode == "pinned":
            event_codes.extend(
                str(outcome.get("result", {}).get("status", "error"))
                if outcome.get("ok")
                else str(outcome.get("error", {}).get("type", "error"))
                for outcome in outcomes
            )
        owner_lock_paths = sorted(
            data_root.glob("runtime/realms/*/owner.lock")
        ) if launcher_mode == "pinned" else []
        discovered_pid = owner_metadata.get("pid") if launcher_mode == "pinned" else None
        owner_pid_alive = False
        if discovered_pid:
            try:
                os.kill(int(discovered_pid), 0)
                owner_pid_alive = True
            except ProcessLookupError:
                owner_pid_alive = False
        lifecycle_failures = sum(
            1
            for outcome in outcomes
            if not outcome.get("ok")
            and outcome.get("error", {}).get("type") == "AutoBootstrapError"
        )
        successes = sum(1 for outcome in outcomes if outcome.get("ok"))
        first_result = next(
            (
                outcome.get("result", {})
                for outcome in outcomes
                if outcome.get("ok") and isinstance(outcome.get("result"), dict)
            ),
            {},
        )
        discovery_identity = {
            key: owner_metadata.get(key, first_result.get(key))
            for key in ("endpoint", "realm_id", "runtime_instance_id", "actor_id", "status")
            if owner_metadata.get(key) is not None or first_result.get(key) is not None
        }
        manifest_value = None
        if launcher_mode == "pinned":
            manifest_value = str(
                source_manifest
                or Path(__file__).resolve().parents[2]
                / ".astrid-data/runtime/source-profiles/astrid.json"
            )
        report = {
            "schema_version": 1,
            "harness": "runtime_lifecycle_reproducer",
            "mode": mode,
            "launcher_mode": launcher_mode,
            "source_manifest": manifest_value,
            "callers": callers,
            "launcher_invocations": len(event_codes) + (1 if seed_outcome is not None else 0),
            "bounded_timeout_seconds": 10,
            "owner_count": (
                len(owner_lock_paths)
                if launcher_mode == "pinned"
                else (1 if owner_metadata else 0)
            ),
            "owner_telemetry": {
                "discovery_pid": discovered_pid,
                "discovery_pid_alive_before_cleanup": owner_pid_alive,
                "owner_lock_count": len(owner_lock_paths)
                if launcher_mode == "pinned"
                else (1 if owner_metadata else 0),
                "owner_lock_paths": [
                    str(path.relative_to(data_root)) for path in owner_lock_paths
                ],
                "duplicate_owner_detected": len(owner_lock_paths) > 1,
            },
            "discovery_path": str(discovery_path) if discovery_path else None,
            "discovery": discovery_identity,
            "lifecycle_events": event_codes,
            "outcomes": outcomes,
            "classification": {
                "lifecycle": {
                    "attempted": callers,
                    "successes": successes,
                    "failures": lifecycle_failures,
                },
                "pack_worker": {
                    "attempted": 0,
                    "failures": 0,
                    "status": "not_run; start_pack_host=False",
                },
                "timeline_visualization": {
                    "attempted": 0,
                    "failures": 0,
                    "status": "not_run; lifecycle-only fixture",
                },
            },
            "explicit_client_path": {
                "status": "covered by test_explicit_client_path_does_not_bootstrap",
                "launcher_calls": 0,
            },
        }
        if seed_outcome is not None:
            report["warm_seed"] = seed_outcome
        if launcher_mode == "pinned" and owner_metadata.get("pid"):
            pid = int(owner_metadata["pid"])
            try:
                os.kill(pid, 15)
                deadline = time.monotonic() + 2.0
                while time.monotonic() < deadline:
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
                    time.sleep(0.05)
                else:
                    os.kill(pid, 9)
            except ProcessLookupError:
                pass
            report["cleanup"] = {"pid": pid, "terminated": True}
        return report


def _terminate_pid(pid: int) -> None:
    try:
        os.kill(pid, 15)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.kill(pid, 9)
    except ProcessLookupError:
        pass


def _run_recovery_case(case: str, source_manifest: Path | None = None) -> dict[str, Any]:
    """Exercise pinned launcher repair against a disposable support root."""
    if case not in {"stale", "interrupted"}:
        raise ValueError(f"unsupported recovery case: {case}")
    launcher = Path("/Users/peteromalley/.pyenv/shims/banodoco-local")
    if not launcher.is_file():
        raise RuntimeError(f"pinned launcher not found: {launcher}")
    repo = Path(__file__).resolve().parents[2]
    manifest = source_manifest or repo / ".astrid-data/runtime/source-profiles/astrid.json"
    temporary_context = tempfile.TemporaryDirectory(prefix="astrid-runtime-recovery-", dir="/private/tmp")
    with temporary_context as temporary:
        root = Path(temporary)
        data_root = root / "support"
        data_root.mkdir()
        environment = os.environ.copy()
        environment["BANODOCO_LOCAL_LAUNCHER"] = str(launcher)
        environment["BANODOCO_LOCAL_SOURCE_MANIFEST"] = str(manifest)
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(repo), environment.get("PYTHONPATH", "")]
        ).rstrip(os.pathsep)
        command = [sys.executable, "-c", _worker_code(data_root, launcher)]
        first = subprocess.run(
            command, cwd=str(repo), env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, check=False, timeout=30,
        )
        try:
            first_outcome = json.loads(first.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            first_outcome = {"ok": False, "error": {"type": "malformed_initial_output", "message": first.stdout[-500:]}}
        discovery_path = data_root / "runtime" / "discovery.json"
        initial_discovery = json.loads(discovery_path.read_text(encoding="utf-8")) if discovery_path.is_file() else {}
        initial_pid = int(initial_discovery.get("pid") or 0)
        if initial_pid:
            _terminate_pid(initial_pid)
        # Preserve only the disposable runtime's own stale/partial state. A
        # dead PID plus the old advertisement is exactly what a killed CLI can
        # leave before the launcher gets its cleanup turn.
        stale = dict(initial_discovery)
        stale["pid"] = 999999
        stale["process_birth_id"] = "interrupted-before-admission"
        discovery_path.parent.mkdir(parents=True, exist_ok=True)
        discovery_path.write_text(json.dumps(stale), encoding="utf-8")
        prepared_discovery_present = discovery_path.is_file()
        lock_path = data_root / "runtime" / "instance.lock"
        if case == "interrupted":
            lock_path.write_text(json.dumps({
                "pid": 999999,
                "process_birth_id": "interrupted-before-admission",
                "runtime_instance_id": stale.get("runtime_instance_id", "partial"),
                "realm_id": stale.get("active_realm", ""),
            }), encoding="utf-8")
        recovered = subprocess.run(
            command, cwd=str(repo), env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, check=False, timeout=30,
        )
        try:
            recovered_outcome = json.loads(recovered.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError):
            recovered_outcome = {"ok": False, "error": {"type": "malformed_recovery_output", "message": recovered.stdout[-500:]}}
        final_discovery = json.loads(discovery_path.read_text(encoding="utf-8")) if discovery_path.is_file() else {}
        final_pid = int(final_discovery.get("pid") or 0)
        lock_paths = sorted(data_root.glob("runtime/realms/*/owner.lock"))
        final_alive = False
        if final_pid:
            try:
                os.kill(final_pid, 0)
                final_alive = True
            except ProcessLookupError:
                final_alive = False
        if final_pid:
            _terminate_pid(final_pid)
        version = subprocess.run(
            [str(launcher), "--version"], cwd=str(repo), env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            check=False, timeout=10,
        )
        return {
            "schema_version": 1,
            "harness": "runtime_lifecycle_recovery",
            "case": case,
            "launcher": str(launcher),
            "launcher_version": version.stdout.strip(),
            "source_manifest": str(manifest),
            "data_root": str(data_root),
            "initial": first_outcome,
            "prepared_state": {
                "discovery_present": prepared_discovery_present,
                "dead_pid": 999999,
                "partial_instance_lock": case == "interrupted",
            },
            "recovery": recovered_outcome,
            "owner_telemetry": {
                "owner_lock_count": len(lock_paths),
                "owner_lock_paths": [str(path.relative_to(data_root)) for path in lock_paths],
                "discovery_pid": final_pid,
                "discovery_pid_alive_before_cleanup": final_alive,
                "duplicate_owner_detected": len(lock_paths) > 1,
            },
            "cleanup": {"initial_pid": initial_pid, "recovered_pid": final_pid},
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("cold", "warm"), default="cold")
    parser.add_argument("--callers", type=int, default=3)
    parser.add_argument("--launcher", choices=("fixture", "pinned"), default="fixture")
    parser.add_argument("--recovery-case", choices=("stale", "interrupted"))
    parser.add_argument("--source-manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 2 <= args.callers <= 10:
        parser.error("--callers must be between 2 and 10")
    report = (
        _run_recovery_case(args.recovery_case, args.source_manifest)
        if args.recovery_case
        else _run(args.mode, args.callers, args.launcher, args.source_manifest)
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
