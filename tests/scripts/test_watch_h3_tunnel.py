from __future__ import annotations

import sys
import types

if "paramiko" not in sys.modules:
    sys.modules["paramiko"] = types.ModuleType("paramiko")

from scripts import watch_h3_5090_storage as watcher  # noqa: E402


class _Process:
    pid = 4242
    returncode = 1

    def __init__(self, *, alive: bool) -> None:
        self.alive = alive
        self.terminated = False
        self.waited = False

    def poll(self):
        return None if self.alive else self.returncode

    def terminate(self):
        self.terminated = True
        self.alive = False

    def kill(self):
        self.alive = False

    def wait(self, timeout=None):
        self.waited = True
        self.alive = False
        return self.returncode


def test_tunnel_shutdown_signals_and_reaps_the_owned_process_group(monkeypatch) -> None:
    signals: list[tuple[int, int]] = []
    monkeypatch.setattr(watcher.os, "getpgid", lambda pid: pid + 1)
    monkeypatch.setattr(watcher.os, "killpg", lambda pgid, signum: signals.append((pgid, signum)))
    process = _Process(alive=True)

    watcher._stop_tunnel_process(process)

    assert signals == [(4243, watcher.signal.SIGTERM)]
    assert process.waited is True


def test_cleanup_inventory_observation_is_fail_closed() -> None:
    assert watcher._provider_contains_identity(
        '{"pods":[{"id":"pod-1"}]}', "pod-1"
    ) is True
    assert watcher._provider_contains_identity(
        '{"pods":[{"id":"pod-1"}]}', "pod-2"
    ) is False
    assert watcher._provider_contains_identity("provider unavailable", "pod-1") is None


def test_tunnel_supervisor_replaces_a_dead_tunnel_until_stop(monkeypatch) -> None:
    class _StopAfterRestart:
        def __init__(self) -> None:
            self.calls = 0

        def wait(self, _timeout: float) -> bool:
            self.calls += 1
            return self.calls > 1

        def is_set(self) -> bool:
            return False

    stop = _StopAfterRestart()
    dead = _Process(alive=False)
    replacement = _Process(alive=True)
    monkeypatch.setattr(watcher, "tunnel_stop", stop)
    monkeypatch.setattr(watcher, "tunnel_process", dead)
    monkeypatch.setattr(watcher, "tunnel_handle", {"ssh": "root@example -p 22"})
    monkeypatch.setattr(watcher, "_spawn_reverse_runtime_tunnel", lambda _handle: replacement)

    watcher._supervise_reverse_runtime_tunnel()

    assert watcher.tunnel_process is replacement
    assert stop.calls == 2


def test_terminate_stops_tunnel_even_without_a_pod(monkeypatch) -> None:
    process = _Process(alive=True)
    stopped: list[object] = []
    monkeypatch.setattr(watcher, "tunnel_process", process)
    monkeypatch.setattr(watcher, "tunnel_supervisor_thread", None)
    monkeypatch.setattr(watcher, "_stop_tunnel_process", lambda value: stopped.append(value))
    monkeypatch.setattr(watcher, "pod_id", None)
    monkeypatch.setattr(watcher, "terminated", False)
    watcher.tunnel_stop.clear()

    watcher.terminate()

    assert stopped == [process]
    assert watcher.tunnel_process is None
    assert watcher.terminated is False
    assert watcher.tunnel_stop.is_set()
