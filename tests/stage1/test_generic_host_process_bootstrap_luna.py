"""Process-level proof that the generic host emits a readiness handoff."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from astrid.core.gateway.dispatch import compose_profile_handoff
from astrid.core.execution import generic_host
from astrid.core.execution.generic_host import source_checkout_digest
from astrid.sdk import host_bootstrap


ROOT = Path(__file__).resolve().parents[2]


def test_fixture_interpreter_resolves_both_host_modules_from_worktree() -> None:
    assert Path(host_bootstrap.__file__).resolve().is_relative_to(ROOT)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import astrid.sdk.host_bootstrap as b, astrid.core.execution.generic_host as g; "
            "print(b.__file__); print(g.__file__)",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    paths = [Path(line).resolve() for line in completed.stdout.splitlines()]
    assert paths == [Path(host_bootstrap.__file__).resolve(), Path(generic_host.__file__).resolve()]
    assert all(path.is_relative_to(ROOT) for path in paths)


def test_generic_host_process_preflights_and_reports_readiness(tmp_path: Path) -> None:
    ready_file = tmp_path / "generic-host.ready.json"
    support_root = tmp_path / "runtime-support"
    support_root.mkdir()
    manifest_path = support_root / "astrid-host" / "boot-manifest.json"
    handoff = compose_profile_handoff(manifest_path, support_root=support_root)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(ROOT), env.get("PYTHONPATH", "")) if item
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "astrid.core.execution.generic_host",
            "--pack-root",
            str(ROOT / "astrid" / "packs" / "editorial"),
            "--ready-file",
            str(ready_file),
            "--support-root",
            str(support_root),
            "--source-checkout",
            str(ROOT),
            "--source-checkout-digest",
            source_checkout_digest(ROOT),
            "--boot-manifest-path",
            str(manifest_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(ready_file.read_text(encoding="utf-8"))
    assert payload["status"] == "ready"
    assert payload["python_executable"] == os.path.abspath(sys.executable)
    assert payload["executor_id"] == "astrid-pack-host"
    assert payload["pid"] != os.getpid()
    assert payload["capability_count"] > 0
    assert len(payload["registration"]["capabilities"]) == payload["capability_count"]
    assert payload["boot_manifest_path"] == str(manifest_path.resolve())
    assert payload["boot_manifest_hash"] == handoff["sha256"]
    assert payload["source_checkout"] == str(ROOT)
    assert payload["source_checkout_digest"] == source_checkout_digest(ROOT)
    assert not (tmp_path / ".astrid" / "astrid.sqlite3").exists()


def test_generic_host_rejects_wrong_source_digest_before_discovery(tmp_path: Path) -> None:
    ready_file = tmp_path / "generic-host.ready.json"
    support_root = tmp_path / "runtime-support"
    support_root.mkdir()
    manifest_path = support_root / "astrid-host" / "boot-manifest.json"
    compose_profile_handoff(manifest_path, support_root=support_root)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(ROOT), env.get("PYTHONPATH", "")) if item
    )
    completed = subprocess.run(
        [
            sys.executable, "-m", "astrid.core.execution.generic_host",
            "--pack-root", str(ROOT / "astrid" / "packs" / "editorial"),
            "--ready-file", str(ready_file),
            "--support-root", str(support_root),
            "--source-checkout", str(ROOT),
            "--source-checkout-digest", "0" * 64,
            "--boot-manifest-path", str(manifest_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 2
    assert "does not match the source checkout" in completed.stderr
    assert not ready_file.exists()


def test_generic_host_rechecks_source_after_preflight_before_registration(
    tmp_path: Path, monkeypatch
) -> None:
    source = tmp_path / "source"
    pack_root = source / "astrid" / "packs"
    pack_root.mkdir(parents=True)
    marker = pack_root / "marker.txt"
    marker.write_text("before", encoding="utf-8")
    support_root = tmp_path / "runtime-support"
    support_root.mkdir()
    manifest_path = support_root / "astrid-host" / "boot-manifest.json"
    compose_profile_handoff(manifest_path, support_root=support_root)
    ready_file = tmp_path / "generic-host.ready.json"
    calls: list[str] = []

    class FakeHost:
        executor_id = "astrid-pack-host"
        source_inventory_identity = None
        source_epoch = None
        runtime_state = {}
        capabilities = {}

        def __init__(self, **_kwargs):
            pass

        def discover(self):
            calls.append("discover")

        def preflight(self):
            calls.append("preflight")
            marker.write_text("changed during preflight", encoding="utf-8")

        def register(self, **_kwargs):
            calls.append("register")
            return {"capabilities": []}

    digest = source_checkout_digest(source)
    monkeypatch.setattr(generic_host, "GenericPackHost", FakeHost)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "astrid-generic-host", "--pack-root", str(pack_root),
            "--ready-file", str(ready_file), "--support-root", str(support_root),
            "--source-checkout", str(source), "--source-checkout-digest", digest,
            "--boot-manifest-path", str(manifest_path),
        ],
    )
    with pytest.raises(SystemExit) as caught:
        generic_host._cli()
    assert caught.value.code == 2
    assert calls == ["discover", "preflight"]
    assert not ready_file.exists()
