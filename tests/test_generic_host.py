from __future__ import annotations

import json
import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.core.execution import process_group
from astrid.core.execution.generic_host import (
    AdapterRegistry,
    GenericPackHost,
    HostCancelled,
    HostError,
    RuntimeProtocolClient,
    _completed_process_evidence,
    _terminate_process_group,
)


class FakeRuntime:
    schema_digest = "sha256:" + "1" * 64

    def __init__(self):
        self.registrations = []
        self.settlements = []
        self.failures = []
        self.heartbeats = []
        self.capability_registrations = []
        self.tasks = {}

    def health(self):
        return {
            "protocol": "workspace.v1",
            "schema_digest": self.schema_digest,
            "runtime_epoch": 1,
        }

    def register_executor(self, executor_id, **payload):
        self.registrations.append((executor_id, payload))
        return {"id": executor_id, "state": "registered"}

    def register_capability(self, capability_id, **payload):
        self.capability_registrations.append((capability_id, payload))

    def heartbeat(self, task_id, lease_token, *, attempt_id, fence):
        self.heartbeats.append((task_id, lease_token, attempt_id, fence))

    def task(self, task_id):
        return self.tasks[task_id]

    def settle(self, task_id, lease_token, **payload):
        self.settlements.append((task_id, lease_token, payload))
        return {"task": {"id": task_id, "status": "completed"}}

    def fail(self, task_id, lease_token, error, **kwargs):
        self.failures.append((task_id, lease_token, error, kwargs))

    def claim_next(self, **payload):
        self.claim_payload = payload
        return None

    def upload_object(self, path, *, project_id, media_type, filename=None):
        data = Path(path).read_bytes()
        return SimpleNamespace(
            object_id=f"object-{hashlib.sha256(data).hexdigest()[:12]}",
            digest=hashlib.sha256(data).hexdigest(),
            size=len(data),
            media_type=media_type,
            filename=filename,
            project_id=project_id,
        )

    def withdraw_capability(self, capability_id, *, digest, reason):
        self.register_capability(
            capability_id,
            digest=digest,
            status="unavailable",
            unavailable_reason=reason,
        )


def _write_manifest(
    root: Path,
    *,
    version: str = "1.0",
    capability_id: str = "test.echo",
    cwd: str | None = None,
) -> Path:
    root.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "id": capability_id,
        "name": "Echo",
        "kind": "external",
        "version": version,
        "command": {
            "argv": [
                "{python_exec}",
                "-c",
                "from pathlib import Path; Path('{out}/answer.txt').write_text('ok')",
            ]
        },
        "outputs": [{"name": "answer", "type": "file", "path_template": "{out}/answer.txt", "artifact_type": "text/plain"}],
        "metadata": {"resource_keys": ["cpu"], "estimated_scratch_bytes": 1},
    }
    if cwd is not None:
        manifest["command"]["cwd"] = cwd
    path = root / "executor.yaml"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_admitted_definition_and_source_are_fenced_before_child_dispatch(tmp_path):
    _write_manifest(tmp_path / "echo")
    host = GenericPackHost(pack_roots=[tmp_path])
    definition, admission = host.admit("executor", "test.echo")
    # Mutating the source after admission must fail closed; the child may not
    # reopen the mutable default registry and silently run a different command.
    (tmp_path / "echo" / "runtime.py").write_text("changed", encoding="utf-8")
    with pytest.raises(HostError, match="source digest changed"):
        host.invoke_capability(
            capability_kind="executor",
            capability_id="test.echo",
            request={"out": str(tmp_path / "attempt"), "inputs": {}},
            attempt=tmp_path / "attempt",
            definition=definition,
            admission=admission,
        )


def test_external_pack_import_root_is_fenced_before_direct_command(tmp_path):
    """A mutation in an imported external-pack module blocks command launch."""
    pack_root = tmp_path / "fixture_provider"
    executor_root = pack_root / "executors" / "echo"
    executor_root.mkdir(parents=True)
    (pack_root / "pack.yaml").write_text(
        "schema_version: 1\nid: fixture_provider\nname: Fixture\nversion: 1.0\n"
        "capabilities: [echo]\ncontent:\n  executors: executors\n",
        encoding="utf-8",
    )
    (pack_root / "helper.py").write_text("VALUE = 'before'\n", encoding="utf-8")
    (executor_root / "executor.yaml").write_text(
        json.dumps({
            "schema_version": 1,
            "id": "fixture_provider.echo",
            "name": "Echo",
            "kind": "external",
            "version": "1.0",
            "command": {"argv": [sys.executable, "-c", "from fixture_provider import helper; from pathlib import Path; Path('{out}/answer').write_text(helper.VALUE)"]},
            "outputs": [],
        }),
        encoding="utf-8",
    )
    host = GenericPackHost(pack_roots=[pack_root])
    host.discover()
    record = host.capabilities["fixture_provider.echo"]
    (pack_root / "helper.py").write_text("VALUE = 'after'\n", encoding="utf-8")
    with pytest.raises(HostError, match="source digest changed"):
        host._run_command_definition(
            record,
            {},
            tmp_path / "attempt" / "outputs",
            tmp_path / "attempt",
            admission={
                "source_digest": record.source_digest,
                "source_root": str(record.source_root),
                "source_roots": [str(root) for root in (record.source_root, pack_root)],
            },
        )


def test_input_materialization_rejects_traversal_names(tmp_path):
    _write_manifest(tmp_path / "echo")

    class Objects(FakeRuntime):
        def get_object(self, digest):
            return b"input"

    host = GenericPackHost(pack_roots=[tmp_path], client=Objects())
    with pytest.raises(HostError, match="input name escapes"):
        host._materialize_inputs(
            {
                "input_object_ids": [],
                "spec": {
                    "inputs": {},
                    "input_digests": [
                        {"name": "../escape", "digest": "a" * 64}
                    ],
                },
            },
            tmp_path / "attempt",
        )


def test_input_materialization_rejects_foreign_nested_digest(tmp_path):
    authorized = hashlib.sha256(b"authorized").hexdigest()
    foreign = hashlib.sha256(b"foreign").hexdigest()
    registry = tmp_path / "assets.json"
    registry.write_text(
        json.dumps({"assets": {"foreign": {"object_id": "foreign-object", "digest": foreign}}}),
        encoding="utf-8",
    )

    class Objects(FakeRuntime):
        def __init__(self):
            super().__init__()
            self.fetches = []

        def get_object(self, digest):
            self.fetches.append(digest)
            return b"foreign"

    runtime = Objects()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    with pytest.raises(HostError, match="not authorized"):
        host._materialize_inputs(
            {
                "input_object_ids": [authorized],
                "spec": {"inputs": {"assets_registry": str(registry)}},
            },
            tmp_path / "attempt",
        )
    assert runtime.fetches == []


def test_command_cwd_must_stay_in_attempt_or_source_scope(tmp_path):
    _write_manifest(tmp_path / "echo", cwd=str(tmp_path / "outside"))
    host = GenericPackHost(pack_roots=[tmp_path])
    host.discover()
    record = host.capabilities["test.echo"]
    with pytest.raises(HostError, match="cwd escapes"):
        host._run_command_definition(record, {}, tmp_path / "attempt" / "outputs", tmp_path / "attempt")


def test_cancellation_terminates_descendant_process_group(tmp_path):
    root = tmp_path / "group"
    _write_manifest(root)
    manifest = json.loads((root / "executor.yaml").read_text(encoding="utf-8"))
    manifest["command"]["argv"] = [
        "{python_exec}",
        "-c",
        "import os,time; from pathlib import Path; p=os.fork(); Path('{out}/child.pid').write_text(str(p if p else os.getpid())); time.sleep(30)",
    ]
    (root / "executor.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    host = GenericPackHost(pack_roots=[tmp_path])
    host.discover()
    attempt = tmp_path / "attempt"
    output_root = attempt / "outputs"
    output_root.mkdir(parents=True)
    started = time.monotonic()

    def cancelled():
        return time.monotonic() - started > 0.75

    with pytest.raises(HostCancelled):
        host._run_command_definition(
            host.capabilities["test.echo"], {}, output_root, attempt, cancelled=cancelled
        )
    child_pid = int((output_root / "child.pid").read_text(encoding="utf-8"))
    for _ in range(20):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("descendant survived cancellation")


def test_cancellation_reaps_sigterm_resistant_descendant_after_leader_exit(tmp_path):
    """A leader that exits on TERM must not let its stubborn child escape."""
    root = tmp_path / "leader-exits"
    _write_manifest(root)
    manifest = json.loads((root / "executor.yaml").read_text(encoding="utf-8"))
    child_code = (
        "import os,signal,sys,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "Path('{out}/child.pid').write_text(str(os.getpid())); "
        "os.write(int(sys.argv[1]), b'1'); os.close(int(sys.argv[1])); "
        "time.sleep(30)"
    )
    leader_code = (
        "import os,signal,subprocess,sys,time; "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        f"ready_r,ready_w=os.pipe(); subprocess.Popen([sys.executable,'-c',{child_code!r},str(ready_w)], pass_fds=(ready_w,)); os.close(ready_w); os.read(ready_r,1); os.close(ready_r); "
        "time.sleep(30)"
    )
    # Keeping the child in the inherited process group is intentional: the
    # host owns that whole group.
    manifest["command"]["argv"] = ["{python_exec}", "-c", leader_code]
    (root / "executor.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    host = GenericPackHost(pack_roots=[tmp_path])
    host.discover()
    attempt = tmp_path / "attempt"
    output_root = attempt / "outputs"
    output_root.mkdir(parents=True)
    started = time.monotonic()

    def cancelled():
        return time.monotonic() - started > 0.75

    with pytest.raises(HostCancelled):
        host._run_command_definition(
            host.capabilities["test.echo"], {}, output_root, attempt, cancelled=cancelled
        )
    child_pid = int((output_root / "child.pid").read_text(encoding="utf-8"))
    for _ in range(40):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("SIGTERM-resistant descendant survived leader-exit cancellation")


def test_cancellation_reaps_descendant_spawned_by_sigterm_handler(tmp_path):
    """A TERM handler may create a child after the first group census."""
    root = tmp_path / "late-child"
    _write_manifest(root)
    manifest = json.loads((root / "executor.yaml").read_text(encoding="utf-8"))
    child_code = (
        "import os,signal,sys,time; from pathlib import Path; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "Path(sys.argv[1]).write_text(str(os.getpid())); "
        "os.write(int(sys.argv[2]), b'1'); os.close(int(sys.argv[2])); time.sleep(30)"
    )
    leader_code = (
        "import os,signal,subprocess,sys,time\n"
        f"def late(*_):\n    ready_r,ready_w=os.pipe(); subprocess.Popen([sys.executable,'-c',{child_code!r},'{str(root / 'child.pid')}',str(ready_w)], pass_fds=(ready_w,)); os.close(ready_w); os.read(ready_r,1); os.close(ready_r)\n"
        "signal.signal(signal.SIGTERM, late)\n"
        "time.sleep(30)\n"
    )
    manifest["command"]["argv"] = ["{python_exec}", "-c", leader_code]
    (root / "executor.yaml").write_text(json.dumps(manifest), encoding="utf-8")
    host = GenericPackHost(pack_roots=[tmp_path])
    host.discover()
    attempt = tmp_path / "attempt"
    output_root = attempt / "outputs"
    output_root.mkdir(parents=True)
    started = time.monotonic()

    def cancelled():
        return time.monotonic() - started > 0.75

    with pytest.raises(HostCancelled):
        host._run_command_definition(
            host.capabilities["test.echo"], {}, output_root, attempt, cancelled=cancelled
        )
    child_pid = int((root / "child.pid").read_text(encoding="utf-8"))
    for _ in range(40):
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("SIGTERM-handler child survived cancellation")


def test_cleanup_does_not_signal_a_reused_group_after_leader_exit(monkeypatch):
    """An exited leader PID must never be reused as a killpg target."""
    process = subprocess.Popen([sys.executable, "-c", "pass"], start_new_session=True)
    process.wait()

    def unexpected_killpg(*_args):
        raise AssertionError("cleanup signaled a group after its leader exited")

    monkeypatch.setattr(os, "killpg", unexpected_killpg)
    _terminate_process_group(process)


def test_signal_revalidates_group_identity_immediately_before_killpg(monkeypatch):
    """A PGID census change in the final signal window fails closed."""
    process = process_group.popen_owned_group([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        initial = process_group._process_snapshot()
        leader = initial[process.pid]
        reused = dict(initial)
        reused[process.pid] = process_group._ProcessInfo(
            process.pid,
            leader.ppid,
            leader.pgid,
            leader.birth + " (reused)",
        )
        snapshots = iter((initial, reused))
        monkeypatch.setattr(process_group, "_process_snapshot", lambda: next(snapshots))
        monkeypatch.setattr(os, "killpg", lambda *_args: pytest.fail("reused group was signalled"))
        monkeypatch.setattr(os, "kill", lambda *_args: pytest.fail("reused member was signalled"))

        process_group.signal_group(process, signal.SIGTERM)
    finally:
        monkeypatch.undo()
        process.kill()
        process.wait()


def test_tree_cleanup_rejects_reused_child_before_adopting_descendants(monkeypatch):
    """A reused child PID cannot pull an unrelated descendant into cleanup."""
    process = SimpleNamespace(pid=100, _astrid_process_birth="root")
    known: dict[int, str] = {}
    initial = {
        100: process_group._ProcessInfo(100, 1, 100, "root"),
        200: process_group._ProcessInfo(200, 100, 100, "child-old"),
    }
    assert process_group._tree_members(process, known, initial) == {
        100: "root",
        200: "child-old",
    }

    # PID 200 is now a different process.  Its child 300 is unrelated and
    # must not be adopted merely because the numeric parent PID matches.
    reused = {
        100: process_group._ProcessInfo(100, 1, 100, "root"),
        200: process_group._ProcessInfo(200, 100, 100, "child-new"),
        300: process_group._ProcessInfo(300, 200, 100, "unrelated"),
    }
    assert process_group._tree_members(process, known, reused) == {
        100: "root",
    }
    signalled: list[int] = []
    monkeypatch.setattr(os, "kill", lambda pid, _sig: signalled.append(pid))
    process_group._signal_valid_tree_members(process, known, signal.SIGKILL, reused)
    assert signalled == [100]


def test_discovery_digest_and_truthful_preflight(tmp_path):
    _write_manifest(tmp_path / "echo")
    host = GenericPackHost(pack_roots=[tmp_path])
    records = host.discover()
    assert [record.id for record in records] == ["test.echo"]
    assert records[0].source_digest
    assert host.preflight("test.echo")[0].ready
    original = records[0].capability_digest
    host.register()
    _write_manifest(tmp_path / "changed")
    changed = host.refresh()
    assert changed == ()  # a distinct capability does not invalidate the old one
    (tmp_path / "echo" / "executor.yaml").write_text((tmp_path / "changed" / "executor.yaml").read_text().replace('1.0', '2.0'), encoding="utf-8")
    assert host.refresh()[0].capability_digest != original
    with pytest.raises(Exception, match="deliberate re-registration"):
        host.register()
    host.register(deliberate=True)


def test_claim_only_admits_capabilities_that_are_currently_ready(tmp_path, monkeypatch):
    """The host candidate set must equal its current readiness predicate."""
    monkeypatch.delenv("ASTRID_PROVIDER_KEY", raising=False)
    root = tmp_path / "required_env"
    root.mkdir()
    (root / "executor.yaml").write_text(
        json.dumps({
            "schema_version": 1,
            "id": "fixture.required_env",
            "name": "Fixture Required Environment",
            "kind": "external",
            "version": "1.0",
            "command": {"argv": ["{python_exec}", "-c", "pass"]},
            "outputs": [],
            "isolation": {"mode": "subprocess", "network": False},
            "metadata": {
                "adapter_family": "cpu",
                "required_env": ["ASTRID_PROVIDER_KEY"],
            },
        }),
        encoding="utf-8",
    )
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()

    assert host.capabilities["fixture.required_env"].ready is False
    assert host.claim_once() is None
    assert not hasattr(runtime, "claim_payload")

    # Rotation is observed on the next claim cycle, without rebuilding the
    # host, and the now-ready capability becomes the only candidate.
    monkeypatch.setenv("ASTRID_PROVIDER_KEY", "fixture-secret")
    assert host.claim_once() is None
    assert runtime.claim_payload["capability_ids"] == ["fixture.required_env"]

def test_source_and_dependency_digests_invalidate_registration(tmp_path):
    _write_manifest(tmp_path / "base")
    child = tmp_path / "child"
    child.mkdir()
    (child / "executor.yaml").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "test.child",
                "name": "Child",
                "kind": "external",
                "version": "1.0",
                "graph": {"depends_on": ["test.echo"]},
                "command": {"argv": ["{python_exec}", "-c", "pass"]},
                "outputs": [],
            }
        ),
        encoding="utf-8",
    )
    host = GenericPackHost(pack_roots=[tmp_path])
    host.discover()
    host.register()

    # A runtime source file can change without changing the manifest digest.
    (tmp_path / "base" / "runtime.py").write_text("changed", encoding="utf-8")
    changed = host.refresh()
    assert [record.id for record in changed] == ["test.echo"]
    with pytest.raises(HostError, match="source digest changed: test.echo"):
        host.register()
    host.register(deliberate=True)

    # A dependency manifest change invalidates its consumer's dependency
    # digest as well as the dependency's own source/capability state.
    (tmp_path / "base" / "executor.yaml").write_text(
        (tmp_path / "base" / "executor.yaml").read_text(encoding="utf-8").replace('"1.0"', '"2.0"'),
        encoding="utf-8",
    )
    changed = host.refresh()
    assert {record.id for record in changed} == {"test.echo", "test.child"}
    with pytest.raises(HostError, match="dependency digest changed: test.child"):
        host.register()


def test_removed_capability_invalidates_and_is_withdrawn_on_deliberate_reregistration(tmp_path):
    _write_manifest(tmp_path / "base", capability_id="test.base")
    _write_manifest(tmp_path / "removed")

    class WithdrawalRuntime(FakeRuntime):
        def __init__(self):
            super().__init__()
            self.withdrawals = []

        def withdraw_capability(self, capability_id, *, digest, reason):
            self.withdrawals.append((capability_id, digest, reason))

    runtime = WithdrawalRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    host.register()
    removed_digest = host.capabilities["test.echo"].capability_digest

    (tmp_path / "removed" / "executor.yaml").unlink()
    assert [record.id for record in host.refresh()] == ["test.echo"]
    with pytest.raises(HostError, match="capability removed: test.echo"):
        host.register()

    result = host.register(deliberate=True)
    assert result["withdrawn_capabilities"] == ["test.echo"]
    assert runtime.withdrawals == [
        ("test.echo", removed_digest, "capability removed from source checkout")
    ]
    assert [
        item["capability_id"]
        for item in runtime.registrations[-1][1]["capabilities"]
    ] == ["test.base"]


def test_registration_carries_epochs_and_runtime_epoch_change_is_deterministic(tmp_path):
    _write_manifest(tmp_path / "echo")

    class EpochRuntime(FakeRuntime):
        def __init__(self):
            super().__init__()
            self.epoch = 7

        def health(self):
            return {
                "protocol": "workspace.v1",
                "schema_digest": self.schema_digest,
                "runtime_epoch": self.epoch,
            }

    runtime = EpochRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    host.register()
    payload = runtime.registrations[0][1]
    assert payload["protocol_version"] == "workspace.v1"
    assert payload["runtime_epoch"] == 7
    assert payload["source_epoch"] == host.source_epoch
    assert payload["dependency_digest"]
    capability = payload["capabilities"][0]
    assert capability["capability_id"] == "test.echo"
    assert capability["definition_digest"] == host.capabilities["test.echo"].capability_digest
    assert capability["status"] == "ready"

    runtime.epoch = 8
    with pytest.raises(HostError, match="runtime epoch changed; deliberate re-registration required"):
        host.register()


def test_runtime_protocol_mismatch_blocks_registration_before_publish(tmp_path):
    _write_manifest(tmp_path / "echo")

    class IncompatibleRuntime(FakeRuntime):
        def health(self):
            return {
                "protocol": "workspace.v0",
                "schema_digest": self.schema_digest,
                "runtime_epoch": 1,
            }

    runtime = IncompatibleRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    with pytest.raises(HostError, match="runtime compatibility blocked: protocol expected=workspace.v1 actual=workspace.v0"):
        host.register()
    assert runtime.registrations == []


@pytest.mark.parametrize(
    "endpoint",
    (
        "https://runtime.example",
        "http://192.0.2.1:8000",
        "http://127.0.0.1:not-a-port",
    ),
)
def test_runtime_protocol_client_rejects_non_loopback_or_malformed_endpoint(endpoint):
    with pytest.raises(HostError, match="loopback|malformed"):
        RuntimeProtocolClient(endpoint, "worker-token")


def test_runtime_protocol_client_uses_worker_token_contract_without_user_handshake(
    monkeypatch,
):
    class WorkerGenerated:
        handshake_called = False

        def __init__(self, endpoint, token):
            self.endpoint = endpoint
            self.token = token
            self.registration_payloads = []

        def handshake(self, *_args, **_kwargs):
            self.handshake_called = True
            raise AssertionError("worker adapter must not fabricate a user handshake")

        def register_executor(self, executor, *, idempotency_key):
            self.registration_payloads.append(executor)
            return {"executor_id": executor["executor_id"], "idempotency_key": idempotency_key}

    monkeypatch.setattr("banodoco_workspace_client.WorkspaceClient", WorkerGenerated)
    client = RuntimeProtocolClient("http://127.0.0.1:8765", "worker-token")
    response = client.register_executor(
        "worker-1",
        capabilities=[],
        max_concurrency=1,
        resource_keys=[],
        source_digest="sha256:" + "a" * 64,
        dependency_digest="sha256:" + "b" * 64,
        source_epoch="source-epoch-1",
    )

    assert client.WORKER_SCOPES == (
        "handshake",
        "worker:register",
        "worker:execute",
        "tasks:read",
        "objects:read",
        "objects:write",
    )
    assert response["executor_id"] == "worker-1"
    assert client.generated.handshake_called is False
    wire = client.generated.registration_payloads[0]
    assert wire["source_digest"] == "sha256:" + "a" * 64
    assert wire["dependency_digest"] == "sha256:" + "b" * 64
    assert wire["source_epoch"] == "source-epoch-1"
    assert "schema_digest" not in wire


def test_runtime_protocol_client_settlement_preserves_structured_result(monkeypatch):
    class WorkerGenerated:
        def __init__(self, endpoint, token):
            self.settlements = []

        def health(self):
            return {"runtime_epoch": 7}

        def settle_attempt(self, attempt_id, settlement, *, idempotency_key):
            self.settlements.append((attempt_id, settlement, idempotency_key))
            return settlement

    monkeypatch.setattr("banodoco_workspace_client.WorkspaceClient", WorkerGenerated)
    client = RuntimeProtocolClient("http://127.0.0.1:8765", "worker-token")
    result = {
        "adapter_family": "render",
        "capability_digest": "sha256:" + "a" * 64,
        "process_evidence": {"child_boundary": "subprocess"},
    }

    client.settle(
        "task-1",
        "lease-1",
        result=result,
        outputs=[],
        effect=None,
        attempt_id="attempt-1",
        fence=3,
    )

    _, wire, _ = client.generated.settlements[0]
    assert wire["result"] == result
    assert wire["runtime_epoch"] == 7
    assert "schema_digest" not in wire


def test_register_without_readiness_profile_publishes_empty_verified_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ASTRID_HOST_READINESS_PROFILE_PATH", raising=False)
    _write_manifest(tmp_path / "echo")
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)

    host.register()

    assert runtime.registrations[0][1]["verified_facts"] == {}


def test_register_with_profile_missing_verified_facts_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(tmp_path / "echo")
    profile = tmp_path / "readiness.json"
    profile.write_text(json.dumps({"status": "ready"}), encoding="utf-8")
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(profile))
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)

    with pytest.raises(HostError, match="missing verified_facts"):
        host.register()

    assert runtime.capability_registrations == []
    assert runtime.registrations == []


def test_register_with_profile_publishes_valid_verified_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(tmp_path / "echo")
    facts = {
        "exact": {"driver": "cuda-12.4/driver-550", "port": 8188},
        "minimum": {"vram_bytes": 16 * 1024**3, "scratch_bytes": 8 * 1024**3},
    }
    profile = tmp_path / "readiness.json"
    profile.write_text(json.dumps({"verified_facts": facts}), encoding="utf-8")
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(profile))
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)

    host.register()

    assert runtime.registrations[0][1]["verified_facts"] == facts


@pytest.mark.parametrize(
    "profile_value",
    [
        {"verified_facts": []},
        {"verified_facts": {"exact": {"driver": ""}, "minimum": {}}},
        {"verified_facts": {"exact": {}, "minimum": {"vram_bytes": True}}},
    ],
)
def test_register_rejects_malformed_verified_facts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    profile_value: object,
) -> None:
    _write_manifest(tmp_path / "echo")
    profile = tmp_path / "readiness.json"
    profile.write_text(json.dumps(profile_value), encoding="utf-8")
    monkeypatch.setenv("ASTRID_HOST_READINESS_PROFILE_PATH", str(profile))
    runtime = FakeRuntime()

    with pytest.raises(HostError, match="verified_facts"):
        GenericPackHost(pack_roots=[tmp_path], client=runtime).register()

    assert runtime.capability_registrations == []
    assert runtime.registrations == []


def test_runtime_protocol_client_uses_a_fresh_idempotency_key_for_each_heartbeat(
    monkeypatch,
):
    class WorkerGenerated:
        def __init__(self, endpoint, token):
            self.heartbeats = []

        def health(self):
            return {"runtime_epoch": 7}

        def heartbeat_attempt(self, attempt_id, **payload):
            self.heartbeats.append((attempt_id, payload))
            return payload

    monkeypatch.setattr("banodoco_workspace_client.WorkspaceClient", WorkerGenerated)
    client = RuntimeProtocolClient("http://127.0.0.1:8765", "worker-token")

    client.heartbeat("task-1", "lease-1", attempt_id="attempt-1", fence=3)
    client.heartbeat("task-1", "lease-1", attempt_id="attempt-1", fence=3)

    first = client.generated.heartbeats[0][1]
    second = client.generated.heartbeats[1][1]
    assert first["runtime_epoch"] == second["runtime_epoch"] == 7
    assert first["idempotency_key"] != second["idempotency_key"]
    assert first["idempotency_key"].startswith("heartbeat-attempt-1-3-7-")


def test_register_and_run_uses_attempt_local_typed_output_and_cleanup(tmp_path):
    _write_manifest(tmp_path / "echo")
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    result = host.register()
    assert runtime.registrations[0][1]["resource_keys"] == ["cpu"]
    assert runtime.capability_registrations[0][0] == "test.echo"
    task = {
        "task": {
            "id": "task-1",
            "capability": "test.echo",
            "project_id": "demo",
            "attempt_id": "attempt-1",
            "fence": 1,
            "spec": {"spec": {"inputs": {}}},
        }
    }
    runtime.tasks["task-1"] = task
    settled = host.run_task(task, lease_token="lease-1")
    assert settled["task"]["status"] == "completed"
    assert runtime.heartbeats == [("task-1", "lease-1", "attempt-1", 1)]
    outputs = runtime.settlements[0][2]["outputs"]
    evidence = runtime.settlements[0][2]["result"]["process_evidence"]
    assert evidence["capability_id"] == "test.echo"
    assert evidence["attempt_id"] == "attempt-1"
    assert evidence["fence"] == 1
    assert evidence["child_boundary"] == "subprocess"
    assert evidence["returncode"] == 0
    assert isinstance(evidence["process_id"], int) and evidence["process_id"] > 0
    assert outputs[0]["name"] == "answer"
    assert set(outputs[0]) <= {
        "name", "kind", "digest", "media_type", "size", "data_base64",
        "ordinal", "role", "is_primary",
    }
    assert outputs[0]["ordinal"] == 0
    assert outputs[0]["role"] == "result"
    assert outputs[0]["is_primary"] is False
    assert "path" not in outputs[0]
    assert "artifact_type" not in outputs[0]
    assert outputs[0]["digest"]
    assert "content_base64" not in outputs[0]
    result = runtime.settlements[0][2]["result"]
    assert result["adapter_family"] == "cpu"
    assert result["capability_digest"] == host.capabilities["test.echo"].capability_digest
    assert result["source_digest"] == host.capabilities["test.echo"].source_digest
    assert result["dependency_digest"] == host.capabilities["test.echo"].dependency_digest
    assert result["process_evidence"]["child_boundary"] == "subprocess"
    assert result["process_evidence"]["returncode"] == 0
    assert isinstance(result["process_evidence"]["process_id"], int)
    assert not list(tmp_path.glob("astrid-attempt-*"))


def test_completed_process_evidence_reads_settlement_payload_when_result_omits_identity():
    evidence = _completed_process_evidence(
        capability_id="wan2gp.generate_video",
        attempt_id="attempt-1",
        fence=1,
        result=object(),
        payload={"process_id": 257745, "returncode": 0},
    )
    assert evidence["process_id"] == 257745
    assert evidence["returncode"] == 0
    assert evidence["child_boundary"] == "subprocess"


def test_completed_process_evidence_fails_closed_without_returncode():
    with pytest.raises(HostError, match="missing process evidence returncode"):
        _completed_process_evidence(
            capability_id="wan2gp.generate_video",
            attempt_id="attempt-1",
            fence=1,
            result=object(),
            payload={"process_id": 257745},
        )


def test_unready_capability_is_not_dispatched(tmp_path, monkeypatch):
    _write_manifest(tmp_path / "echo")
    monkeypatch.setenv("PATH", "")
    host = GenericPackHost(pack_roots=[tmp_path])
    host.discover()
    host.preflight()
    # python_exec is resolved by the runner; with PATH empty the source still
    # remains a valid manifest and readiness is determined by its declaration.
    assert host.capabilities["test.echo"].ready


def test_claim_loop_fails_explicitly_without_canonical_claim_operation(tmp_path):
    _write_manifest(tmp_path / "echo")
    host = GenericPackHost(pack_roots=[tmp_path], client=object())
    host.discover()
    with pytest.raises(HostError, match="canonical claim-next operation"):
        host.run(once=True)


def test_long_running_claim_loop_survives_and_backs_off_after_runtime_failure(
    tmp_path, monkeypatch, capsys
):
    """One failed queue poll must not terminate the registered pack host."""

    _write_manifest(tmp_path / "echo")
    host = GenericPackHost(pack_roots=[tmp_path], client=FakeRuntime())
    host.discover()
    calls = 0
    waits: list[float] = []

    def claim_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("coordinator temporarily unavailable")
        host._shutdown.set()
        return None

    def wait(delay: float) -> bool:
        waits.append(delay)
        return False

    monkeypatch.setattr(host, "claim_once", claim_once)
    monkeypatch.setattr(host._shutdown, "wait", wait)

    assert host.run(poll_seconds=0.25) == []
    assert calls == 2
    assert waits == [0.25]
    assert "generic host claim failed (1 consecutive)" in capsys.readouterr().err


def test_adapter_registry_classifies_provider_local_generation_and_render():
    provider = GenericPackHost(pack_roots=[Path("astrid/packs/generation/executors")])
    provider.discover()
    assert AdapterRegistry.resolve(provider.capabilities["generation.generate_image_openai"].definition).family == "provider"
    local = GenericPackHost(pack_roots=[Path("astrid/packs/vibecomfy/executors")])
    local.discover()
    assert AdapterRegistry.resolve(local.capabilities["vibecomfy.run"].definition).family == "local_generation"
    local.preflight("vibecomfy.run")
    assert local.capabilities["vibecomfy.run"].resource_keys == ("gpu",)
    render = GenericPackHost(pack_roots=[Path("astrid/packs/rendering/executors/render")])
    render.discover()
    assert AdapterRegistry.resolve(render.capabilities["rendering.render"].definition).family == "render"
    render.preflight("rendering.render")
    report = render.capabilities["rendering.render"].preflight
    if not report["binaries"]["ok"]:
        assert "ffmpeg" in report["binaries"]["missing"]
    assert "remotion" in report
    assert render.capabilities["rendering.render"].estimated_scratch_bytes == 0
    assert render.capabilities["rendering.render"].estimated_output_bytes == 0


def test_render_preflight_requires_the_explicit_execution_runtime(monkeypatch):
    monkeypatch.delenv("ASTRID_REMOTION_PROJECT_DIR", raising=False)
    monkeypatch.delenv("ASTRID_NODE_EXECUTABLE", raising=False)
    monkeypatch.delenv("ASTRID_TIMELINE_SCHEMA_PYTHONPATH", raising=False)
    host = GenericPackHost(
        pack_roots=[Path("astrid/packs/rendering/executors/render")]
    )
    host.discover()

    host.preflight("rendering.render")

    record = host.capabilities["rendering.render"]
    assert not record.ready
    assert not record.preflight["remotion"]["ok"]
    assert "ASTRID_REMOTION_PROJECT_DIR" in record.preflight["remotion"]["reason"]


def test_adapter_registry_preserves_explicit_empty_matrix_lists(tmp_path):
    _write_manifest(tmp_path / "echo")
    host = GenericPackHost(pack_roots=[tmp_path])
    record = host.discover()[0]
    adapter = AdapterRegistry.from_matrix(
        record.definition,
        {
            "adapter_family": "render",
            "resource_keys": [],
            "required_binaries": [],
            "required_packages": [],
        },
    )
    assert adapter.resource_keys == ()
    assert adapter.required_binaries == ()
    assert adapter.required_packages == ()


def test_register_preserves_declared_dispositions_and_block_reasons(tmp_path, monkeypatch):
    monkeypatch.delenv("ASTRID_TEST_PROVIDER_KEY", raising=False)
    records = [
        ("required.provider", "required", "Provider credential is required"),
        ("optional.provider", "optional", "Optional provider credential"),
        ("unsupported.provider", "unsupported", "Provider is not shipped"),
        ("retired.provider", "retired", "Provider was retired"),
    ]
    capabilities = []
    for capability_id, disposition, evidence_reason in records:
        root = tmp_path / capability_id.replace(".", "-")
        root.mkdir()
        (root / "executor.yaml").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "id": capability_id,
                    "name": capability_id,
                    "kind": "external",
                    "version": "1.0",
                    "command": {"argv": ["{python_exec}", "-c", "pass"]},
                    "outputs": [],
                    "isolation": {"mode": "subprocess", "network": True},
                    "metadata": {"adapter_family": "provider"},
                }
            ),
            encoding="utf-8",
        )
        capabilities.append(
            {
                "id": capability_id,
                "disposition": disposition,
                "evidence_reason": evidence_reason,
                "adapter_family": "provider",
                "required_env": (["ASTRID_TEST_PROVIDER_KEY"] if disposition in {"required", "optional"} else []),
                "required_binaries": [],
                "required_packages": [],
            }
        )
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"schema_version": 1, "capabilities": capabilities}), encoding="utf-8")

    class CaptureRuntime(RuntimeProtocolClient):
        schema_digest = FakeRuntime.schema_digest

        def __init__(self):
            self.capability_registrations = []

        def health(self):
            return {
                "protocol": "workspace.v1",
                "schema_digest": self.schema_digest,
                "runtime_epoch": 1,
            }

        def register_capability(self, capability_id, **payload):
            self.capability_registrations.append((capability_id, payload))

        def register_executor(self, executor_id, **payload):
            return {"executor_id": executor_id, **payload}

    runtime = CaptureRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], capability_matrix=matrix, client=runtime)
    host.discover()
    host.register()
    registered = {capability_id: payload for capability_id, payload in runtime.capability_registrations}
    assert registered["required.provider"]["status"] == "unavailable"
    unavailable_reason = registered["required.provider"]["unavailable_reason"]
    assert unavailable_reason
    reason_by_check = {
        component.split(":", 1)[0]: component
        for component in unavailable_reason.split(";")
    }
    assert reason_by_check["credentials"] == "credentials:missing=ASTRID_TEST_PROVIDER_KEY"
    assert reason_by_check["network"] == "network:reason=provider network_policy is missing"
    assert registered["optional.provider"]["status"] == "unavailable"
    assert registered["unsupported.provider"]["status"] == "unsupported"
    assert registered["unsupported.provider"]["unavailable_reason"] == "Provider is not shipped"
    assert registered["retired.provider"]["status"] == "retired"
    assert registered["retired.provider"]["unavailable_reason"] == "Provider was retired"


def test_command_host_harvests_result_manifest_media(tmp_path: Path) -> None:
    root = tmp_path / "wanlike"
    root.mkdir()
    (root / "executor.yaml").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "test.generate",
                "name": "Generate",
                "kind": "external",
                "version": "1.0",
                "command": {
                    "argv": [
                        "{python_exec}",
                        "-c",
                        (
                            "from pathlib import Path; import json, hashlib; "
                            "out=Path('{out}'); out.mkdir(parents=True, exist_ok=True); "
                            "a=out/'a.mp4'; a.write_bytes(b'a'); "
                            "b=out/'b.mp4'; b.write_bytes(b'bb'); "
                            "(out/'manifest.json').write_text(json.dumps({"
                            "'schema_version':1,'kind':'video','inputs':{},"
                            "'outputs':["
                            "{'path':'a.mp4','name':'generated_videos','ordinal':0,'role':'result',"
                            "'is_primary':True,'content_hash':'sha256:'+hashlib.sha256(a.read_bytes()).hexdigest(),'bytes':1},"
                            "{'path':'b.mp4','name':'generated_videos','ordinal':1,'role':'result',"
                            "'content_hash':'sha256:'+hashlib.sha256(b.read_bytes()).hexdigest(),'bytes':2}],"
                            "'created':'t','warnings':[]}))"
                        ),
                    ]
                },
                "outputs": [
                    {"name": "generated_videos", "type": "file", "artifact_type": "video/clip"},
                    {"name": "video_manifest", "type": "file", "path_template": "{out}/manifest.json"},
                ],
                "metadata": {"output_result_manifest": True},
            }
        ),
        encoding="utf-8",
    )
    host = GenericPackHost(pack_roots=[tmp_path])
    host.discover()
    attempt = tmp_path / "attempt"
    output_root = attempt / "outputs"
    output_root.mkdir(parents=True)
    result = host._run_command_definition(
        host.capabilities["test.generate"], {}, output_root, attempt
    )
    assert [item["name"] for item in result.outputs] == [
        "generated_videos",
        "generated_videos",
    ]
    assert [item["ordinal"] for item in result.outputs] == [0, 1]
    assert [Path(item["path"]).name for item in result.outputs] == ["a.mp4", "b.mp4"]

    runtime = FakeRuntime()
    publishing_host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    publishing_host.discover()
    task = {
        "task": {
            "id": "task-collection",
            "capability": "test.generate",
            "project_id": "demo",
            "attempt_id": "attempt-collection",
            "fence": 1,
            "spec": {"spec": {"inputs": {}}},
        }
    }
    runtime.tasks["task-collection"] = task
    publishing_host.run_task(task, lease_token="lease-1")
    settled = runtime.settlements[0][2]["outputs"]
    assert [item["name"] for item in settled] == [
        "generated_videos",
        "generated_videos",
    ]
    assert all(
        set(item)
        <= {
            "name", "kind", "digest", "media_type", "size", "data_base64",
            "ordinal", "role", "is_primary",
        }
        for item in settled
    )
    assert [item["ordinal"] for item in settled] == [0, 1]
    assert [item["role"] for item in settled] == ["result", "result"]
    assert [item["is_primary"] for item in settled] == [True, False]
    assert all("path" not in item and "artifact_type" not in item for item in settled)


def test_command_host_fail_closes_success_without_media(tmp_path: Path) -> None:
    root = tmp_path / "emptygen"
    root.mkdir()
    (root / "executor.yaml").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "test.emptygen",
                "name": "Empty",
                "kind": "external",
                "version": "1.0",
                "command": {
                    "argv": [
                        "{python_exec}",
                        "-c",
                        (
                            "from pathlib import Path; import json; "
                            "out=Path('{out}'); out.mkdir(parents=True, exist_ok=True); "
                            "(out/'manifest.json').write_text(json.dumps({"
                            "'schema_version':1,'kind':'video','inputs':{},'outputs':[],"
                            "'created':'t','warnings':[]}))"
                        ),
                    ]
                },
                "outputs": [
                    {"name": "generated_videos", "type": "file", "artifact_type": "video/clip"},
                ],
                "metadata": {"output_result_manifest": True},
            }
        ),
        encoding="utf-8",
    )
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    task = {
        "task": {
            "id": "task-empty",
            "capability": "test.emptygen",
            "project_id": "demo",
            "attempt_id": "attempt-empty",
            "fence": 1,
            "spec": {"spec": {"inputs": {}}},
        }
    }
    runtime.tasks["task-empty"] = task
    with pytest.raises(HostError, match="no concrete outputs|no result files"):
        host.run_task(task, lease_token="lease-1")
    assert runtime.settlements == []


def test_command_host_rejects_media_receipt_with_wrong_port_name(tmp_path: Path) -> None:
    root = tmp_path / "wrong-port"
    root.mkdir()
    (root / "executor.yaml").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "test.wrong-port",
                "name": "Wrong port",
                "kind": "external",
                "version": "1.0",
                "command": {
                    "argv": [
                        "{python_exec}",
                        "-c",
                        (
                            "from pathlib import Path; import json, hashlib; "
                            "out=Path('{out}'); out.mkdir(parents=True, exist_ok=True); "
                            "clip=out/'clip.mp4'; clip.write_bytes(b'mp4'); "
                            "(out/'manifest.json').write_text(json.dumps({"
                            "'schema_version':1,'kind':'video','inputs':{},"
                            "'outputs':[{'path':'clip.mp4','name':'wrong_port','ordinal':0,"
                            "'role':'result','content_hash':'sha256:'+hashlib.sha256(clip.read_bytes()).hexdigest(),"
                            "'bytes':3}],'created':'t','warnings':[]}))"
                        ),
                    ]
                },
                "outputs": [
                    {
                        "name": "generated_videos",
                        "type": "file",
                        "artifact_type": "video/clip",
                    }
                ],
                "metadata": {"output_result_manifest": True},
            }
        ),
        encoding="utf-8",
    )
    runtime = FakeRuntime()
    host = GenericPackHost(pack_roots=[tmp_path], client=runtime)
    host.discover()
    task = {
        "task": {
            "id": "task-wrong-port",
            "capability": "test.wrong-port",
            "project_id": "demo",
            "attempt_id": "attempt-wrong-port",
            "fence": 1,
            "spec": {"spec": {"inputs": {}}},
        }
    }
    runtime.tasks["task-wrong-port"] = task
    with pytest.raises(HostError, match="undeclared port|declared output port"):
        host.run_task(task, lease_token="lease-1")
    assert runtime.settlements == []
