from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid import setup
from astrid.runtime_cli import RuntimeCLI, RuntimeResult

WORKSPACE_ID = "12345678-1234-5678-9234-567812345678"


def _request(tmp_path: Path, operation: str = "create") -> setup.SetupRequest:
    return setup.SetupRequest.from_mapping(
        {
            "schema_version": 1,
            "operation": operation,
            "workspace": {
                "workspace_id": WORKSPACE_ID,
                "support_root": str(tmp_path / "support"),
                "realm_root": str(tmp_path / "realm"),
            },
            "choices": {
                "runtime_profile": "astrid",
                "target_profile": "astrid-beta-current-mac",
                "integrations": ["vibecomfy", "rendering"],
                "disabled_packs": ["wan2gp"],
            },
        }
    )


def _selected(request: setup.SetupRequest, *, status: str = "configured_created") -> dict:
    return {
        "ok": True,
        "status": status,
        "state": "configured",
        "realm_id": request.workspace_id,
        "realm_root": str(request.realm_root),
        "support_root": str(request.support_root),
    }


class FakeRuntime:
    def __init__(self, request: setup.SetupRequest, *, fresh: bool = False, startup_ok: bool = True, inspect_data=None):
        self.request = request
        self.inspect_data = inspect_data or (
            {"ok": False, "state": "workspace_missing", "problem_code": "workspace_missing"}
            if fresh
            else _selected(request, status="unchanged")
        )
        self.startup_ok = startup_ok
        self.calls: list[tuple[str, dict]] = []
        self.configure_status = "configured_created" if fresh else "configured_unchanged"

    def inspect(self, **kwargs):
        self.calls.append(("inspect", kwargs))
        return RuntimeResult(("runtime", "workspace", "inspect"), 0 if self.inspect_data.get("ok") else 1, self.inspect_data)

    def configure(self, operation, **kwargs):
        self.calls.append(("configure", {"operation": operation, **kwargs}))
        return RuntimeResult(("runtime", "workspace", operation), 0, _selected(self.request, status=self.configure_status))

    def up(self, **kwargs):
        self.calls.append(("up", kwargs))
        if self.startup_ok:
            return RuntimeResult(("runtime", "up"), 0, {**_selected(self.request), "runtime_ready": True})
        return RuntimeResult(
            ("runtime", "up"),
            1,
            {"ok": False, "problem_code": "workspace_configured_runtime_not_ready", "error": "port occupied"},
        )


@pytest.fixture(autouse=True)
def _ignore_machine_legacy_catalog(monkeypatch):
    monkeypatch.setattr(setup, "ensure_no_unmigrated_runtime", lambda _root: None)


def _composition(**kwargs):
    return {"ok": True, "mode": "apply" if kwargs["apply"] else "preview", "disabled": ["wan2gp"]}


def test_fresh_create_applies_exactly_one_uuid_root_then_starts(tmp_path):
    request = _request(tmp_path)
    runtime = FakeRuntime(request, fresh=True)

    code, result = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert code == 0
    assert result["workspace_configured"] is True
    assert result["runtime_ready"] is True
    assert [name for name, _ in runtime.calls] == ["inspect", "configure", "up"]
    configured = runtime.calls[1][1]
    assert configured["operation"] == "create"
    assert configured["realm_id"] == WORKSPACE_ID
    assert configured["support_root"] == request.support_root
    assert configured["realm_root"] == request.realm_root
    assert [stage["name"] for stage in result["stages"]] == [
        "inspect", "Create-or-Attach", "select-default", "compose",
        "Setup applied", "Starting Astrid Runtime", "Runtime ready",
    ]


def test_attach_existing_uses_same_apply_core_without_copy(tmp_path):
    request = _request(tmp_path, "attach")
    runtime = FakeRuntime(request)

    code, result = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert code == 0
    assert runtime.calls[1][1]["operation"] == "attach"
    assert result["workspace"]["workspace_id"] == WORKSPACE_ID
    assert "copy" not in json.dumps(result).lower()


def test_repeat_and_resume_reconcile_unchanged_selection_and_retained_choices(tmp_path):
    request = _request(tmp_path)
    runtime = FakeRuntime(request)

    first_code, first = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)
    second_code, second = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert first_code == second_code == 0
    assert first["choices"] == second["choices"] == request.to_document()["choices"]
    assert first["stages"][1]["status"] == second["stages"][1]["status"] == "unchanged"


def test_preview_check_and_apply_share_identical_input_document(tmp_path):
    request = _request(tmp_path)
    runtime = FakeRuntime(request)

    _, preview = setup.execute_setup(request, runtime=runtime, compose=_composition)
    _, check = setup.execute_setup(request, check=True, runtime=runtime, compose=_composition)
    _, applied = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert preview["input"] == check["input"] == applied["input"]
    assert preview["mode"] == "preview"
    assert check["mode"] == "check"
    assert applied["mode"] == "apply"


def test_check_is_strictly_read_only_and_offline_does_not_imply_apply(tmp_path):
    request = _request(tmp_path)
    runtime = FakeRuntime(request)
    compose_modes: list[tuple[bool, bool]] = []

    def composition(**kwargs):
        compose_modes.append((kwargs["apply"], kwargs["offline"]))
        return {"ok": True}

    code, result = setup.execute_setup(request, check=True, offline=True, runtime=runtime, compose=composition)

    assert code == 0 and result["ok"] is True
    assert [name for name, _ in runtime.calls] == ["inspect"]
    assert compose_modes == [(False, True)]


@pytest.mark.parametrize(
    ("inspect_data", "problem_code"),
    [
        ({"ok": False, "problem_code": "workspace_ambiguous", "error": "two selected"}, "workspace_ambiguous"),
        ({"ok": False, "problem_code": "workspace_identity_mismatch", "error": "wrong UUID"}, "workspace_identity_mismatch"),
        ({"ok": False, "problem_code": "workspace_missing", "error": "root absent"}, "workspace_missing"),
    ],
)
def test_attach_fails_closed_for_ambiguous_wrong_or_absent_identity(tmp_path, inspect_data, problem_code):
    request = _request(tmp_path, "attach")
    runtime = FakeRuntime(request, inspect_data=inspect_data)

    code, result = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert code == 1
    assert result["problem_code"] == problem_code
    assert [name for name, _ in runtime.calls] == ["inspect"]


def test_runtime_result_with_wrong_root_is_rejected_before_apply(tmp_path):
    request = _request(tmp_path)
    wrong = {**_selected(request), "realm_root": str(tmp_path / "other")}
    runtime = FakeRuntime(request, inspect_data=wrong)

    code, result = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert code == 1
    assert result["problem_code"] == "workspace_identity_mismatch"
    assert [name for name, _ in runtime.calls] == ["inspect"]


def test_relative_and_cwd_fallback_inputs_are_rejected():
    with pytest.raises(ValueError, match="absolute path; cwd fallback is forbidden"):
        setup.SetupRequest.from_mapping(
            {
                "operation": "create",
                "workspace_id": WORKSPACE_ID,
                "support_root": ".astrid-data",
                "realm_root": "/tmp/realm",
            }
        )


def test_old_checkout_guard_fails_before_runtime_or_composition(monkeypatch, tmp_path):
    request = _request(tmp_path)
    runtime = FakeRuntime(request)
    monkeypatch.setattr(setup, "ensure_no_unmigrated_runtime", lambda _root: (_ for _ in ()).throw(ValueError("old checkout unavailable")))

    code, result = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert code == 1
    assert "old checkout unavailable" in result["error"]
    assert runtime.calls == []


def test_startup_failure_preserves_configured_selection_and_proposes_runtime_up(tmp_path):
    request = _request(tmp_path)
    runtime = FakeRuntime(request, fresh=True, startup_ok=False)

    code, result = setup.execute_setup(request, apply=True, runtime=runtime, compose=_composition)

    assert code == 1
    assert result["workspace_configured"] is True
    assert result["runtime_ready"] is False
    assert result["problem_code"] == "workspace_configured_runtime_not_ready"
    assert shlex.split(result["next_action"]["command"]) == [
        "astrid-runtime", "up", "--profile", "astrid",
        "--data-root", str(request.support_root), "--json",
    ]
    assert result["workspace"]["workspace_id"] == WORKSPACE_ID


def test_startup_recovery_command_crosses_real_astrid_runtime_entrypoint(monkeypatch, tmp_path, capsys):
    from astrid import runtime_cli

    request = replace(_request(tmp_path), support_root=tmp_path / "support root")
    command = setup._runtime_up_command(request)
    argv = shlex.split(command)
    calls: list[dict] = []

    class RuntimeBoundary:
        def inspect(self, **kwargs):
            calls.append({"inspect": kwargs})
            return RuntimeResult(("runtime", "workspace", "inspect"), 0, _selected(request))

        def up(self, **kwargs):
            calls.append({"up": kwargs})
            return RuntimeResult(("runtime", "up"), 0, {**_selected(request), "runtime_ready": True})

    monkeypatch.setattr(runtime_cli, "RuntimeCLI", RuntimeBoundary)
    monkeypatch.setattr(runtime_cli, "ensure_no_unmigrated_runtime", lambda _root: None)

    assert runtime_cli.main(argv[1:]) == 0
    assert json.loads(capsys.readouterr().out)["runtime_ready"] is True
    assert calls == [
        {"inspect": {"support_root": request.support_root}},
        {
            "up": {
                "support_root": request.support_root,
                "expected_realm_id": WORKSPACE_ID,
                "realm_root": str(request.realm_root),
            }
        },
    ]


def test_startup_recovery_command_parses_at_installed_runtime_boundary(tmp_path):
    """Exercise the parser that owns the installed ``astrid-runtime`` script."""

    request = replace(_request(tmp_path), support_root=tmp_path / "support root")
    emitted = shlex.split(setup._runtime_up_command(request))[1:]
    astrid_root = Path(__file__).parents[1]
    runtime_candidate = Path(
        os.environ.get(
            "ASTRID_RUNTIME_CANDIDATE",
            astrid_root.parents[3]
            / "banodoco-workspace-runtime"
            / ".otto"
            / "worktrees"
            / astrid_root.name,
        )
    )
    if not (runtime_candidate / "banodoco_local" / "cli.py").is_file():
        pytest.skip("paired Runtime candidate is unavailable")
    probe = """
import json
from banodoco_local.cli import parser
value = parser().parse_args(%r)
print(json.dumps({
    'command': value.command,
    'profile': value.profile,
    'data_root': str(value.data_root),
    'json': value.json,
}))
""" % emitted
    completed = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=runtime_candidate,
        env={**os.environ, "PYTHONPATH": str(runtime_candidate)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "command": "up",
        "profile": "astrid",
        "data_root": str(request.support_root),
        "json": True,
    }


def test_runtime_observers_delegate_without_inspect_connect_or_up(tmp_path):
    seen: list[list[str]] = []

    def runner(argv, **kwargs):
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 1, '{"ok":false,"problem_code":"workspace_missing"}', "")

    runtime = RuntimeCLI(command=("banodoco-local",), runner=runner)
    runtime.observe("status", support_root=tmp_path / "support")
    runtime.observe("doctor", support_root=tmp_path / "support")

    assert [argv[1] for argv in seen] == ["status", "doctor"]
    assert all("connect" not in argv and "up" not in argv and "workspace" not in argv for argv in seen)
    assert all(["--data-root", str(tmp_path / "support")] == argv[2:4] for argv in seen)


def test_public_status_uses_only_runtime_observers(monkeypatch, tmp_path, capsys):
    from astrid import runtime_cli
    from astrid.core.gateway import dispatch

    seen: list[str] = []

    class Observer:
        def inspect(self, *, support_root):
            seen.append("inspect")
            return RuntimeResult(("runtime", "workspace", "inspect"), 1, {"ok": False, "problem_code": "workspace_missing"})

        def observe(self, command, *, support_root):
            seen.append(command)
            return RuntimeResult(("runtime", command), 1, {"ok": False, "problem_code": "workspace_missing"})

    monkeypatch.setattr(runtime_cli, "RuntimeCLI", Observer)
    monkeypatch.setattr("astrid.sdk.storage_root.resolve_runtime_data_root", lambda: tmp_path / "support")
    monkeypatch.setattr("astrid.core.auth.contributor_key_present", lambda: False)

    assert dispatch._dispatch_status(["--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert seen == ["inspect", "status"]
    assert payload["effects"] == ["observe"]
    assert payload["authorization_required"] is False
    assert payload["readiness"]["optional_contribution_auth"] == "no-local-key"


def test_runtime_up_inspects_exact_selection_before_delegating(tmp_path):
    request = _request(tmp_path)
    seen: list[list[str]] = []

    def runner(argv, **kwargs):
        seen.append(argv)
        data = _selected(request)
        return subprocess.CompletedProcess(argv, 0, json.dumps(data), "")

    runtime = RuntimeCLI(command=("banodoco-local",), runner=runner)
    result = runtime.up(
        support_root=request.support_root,
        expected_realm_id=request.workspace_id,
        realm_root=request.realm_root,
    )

    assert result.ok
    assert seen[0][1:4] == ["workspace", "inspect", "--data-root"]
    assert seen[1][1:4] == ["up", "--profile", "astrid"]


def test_input_file_and_explicit_flags_normalize_to_same_request(tmp_path):
    request = _request(tmp_path)
    input_path = tmp_path / "setup.json"
    input_path.write_text(json.dumps(request.to_document()), encoding="utf-8")
    parser = setup._parser()

    from_file = setup._request_from_args(parser.parse_args(["--input", str(input_path)]))
    from_flags = setup._request_from_args(
        parser.parse_args(
            [
                "--create", "--workspace-id", WORKSPACE_ID,
                "--data-root", str(request.support_root),
                "--realm-root", str(request.realm_root),
                "--target-profile", "astrid-beta-current-mac",
                "--integration", "vibecomfy", "--integration", "rendering",
                "--disabled-choice", "wan2gp",
            ]
        )
    )

    assert from_file == from_flags


def test_noninteractive_omitted_choice_flags_remain_omitted(tmp_path):
    parser = setup._parser()

    request = setup._request_from_args(
        parser.parse_args(
            [
                "--attach", "--workspace-id", WORKSPACE_ID,
                "--data-root", str(tmp_path / "support"),
                "--realm-root", str(tmp_path / "realm"),
            ]
        )
    )

    assert request.target_profile is None
    assert request.integrations is None
    assert "target_profile" not in request.to_document()["choices"]
    assert "integrations" not in request.to_document()["choices"]


def test_guided_and_noninteractive_adapters_normalize_to_same_request(monkeypatch, tmp_path):
    request = _request(tmp_path)
    parser = setup._parser()
    answers = iter(
        [
            "create", WORKSPACE_ID, str(request.support_root), str(request.realm_root),
            "Astrid Workspace", "astrid-beta-current-mac", "vibecomfy, rendering", "wan2gp",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    monkeypatch.setattr(setup.sys.stdin, "isatty", lambda: True)

    guided = setup._request_from_args(parser.parse_args([]))

    assert guided == request


def test_disabled_choices_are_written_once_to_existing_skill_state(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRID_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(setup, "declarations_from_json", lambda _path: ())
    monkeypatch.setattr(setup, "provision", lambda *args, **kwargs: {"ok": True, "disabled": []})
    import astrid.skills as skills
    from astrid.skills import state

    sync_calls: list[dict] = []
    monkeypatch.setattr(
        skills,
        "sync",
        lambda **kwargs: sync_calls.append(kwargs) or {"actions": []},
    )
    kwargs = {
        "apply": True,
        "offline": True,
        "declarations": None,
        "deep": False,
        "disable_pack": None,
        "restore_pack": None,
        "disabled_packs": ("wan2gp",),
        "workspace_id": WORKSPACE_ID,
        "support_root": tmp_path / "support",
        "realm_root": tmp_path / "realm",
        "runtime_profile": "astrid",
        "target_profile": "astrid-beta-current-mac",
        "integrations": ("vibecomfy", "rendering"),
    }

    first = setup._compose(**kwargs)
    second = setup._compose(**kwargs)
    persisted = state.load()

    assert first["disabled_choices_changed"] is True
    assert second["disabled_choices_changed"] is False
    assert first["setup_selection_changed"] is True
    assert second["setup_selection_changed"] is False
    assert all(
        call["selected_pack_ids"] == ("vibecomfy", "rendering")
        for call in sync_calls
    )
    assert all(values == ["wan2gp"] for values in persisted["disabled_defaults"].values())
    assert persisted["setup_selection"] == {
        "workspace_id": WORKSPACE_ID,
        "support_root": str(tmp_path / "support"),
        "realm_root": str(tmp_path / "realm"),
        "runtime_profile": "astrid",
        "target_profile": "astrid-beta-current-mac",
        "integrations": ["vibecomfy", "rendering"],
    }


def test_retained_choices_survive_fresh_process_repeat(tmp_path):
    request = _request(tmp_path)
    code = """
import json
from pathlib import Path
from astrid import setup
import astrid.skills as skills
setup.declarations_from_json = lambda _path: ()
setup.provision = lambda *args, **kwargs: {'ok': True, 'disabled': []}
skills.sync = lambda **kwargs: {'actions': [], 'selected_pack_ids': list(kwargs['selected_pack_ids'])}
report = setup._compose(
    apply=True,
    offline=True,
    declarations=None,
    deep=False,
    disable_pack=None,
    restore_pack=None,
    disabled_packs=('wan2gp',),
    workspace_id=%r,
    support_root=Path(%r),
    realm_root=Path(%r),
    runtime_profile='astrid',
    target_profile='astrid-beta-current-mac',
    integrations=('vibecomfy', 'rendering'),
)
print(json.dumps(report))
""" % (WORKSPACE_ID, str(request.support_root), str(request.realm_root))
    results = []
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).parents[1],
            env={**os.environ, "ASTRID_STATE_HOME": str(tmp_path / "state")},
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        results.append(json.loads(completed.stdout))

    assert results[0]["setup_selection_changed"] is True
    assert results[1]["setup_selection_changed"] is False
    assert results[1]["disabled_choices_changed"] is False
    assert results[1]["setup_selection"]["integrations"] == ["vibecomfy", "rendering"]
    assert results[1]["setup_selection"]["target_profile"] == "astrid-beta-current-mac"


def test_omitted_same_identity_choices_survive_fresh_process_and_explicit_empty_clears(tmp_path):
    request = _request(tmp_path)
    code = """
import json
import sys
from astrid import setup
import astrid.skills as skills

payload = json.loads(sys.argv[1])
request = setup.SetupRequest.from_mapping(payload)
setup.declarations_from_json = lambda _path: ()
setup.provision = lambda *args, **kwargs: {'ok': True, 'disabled': []}
skills.sync = lambda **kwargs: {
    'actions': [],
    'selected_pack_ids': list(kwargs['selected_pack_ids']),
}
report = setup._compose(
    apply=True,
    offline=True,
    declarations=None,
    deep=False,
    disable_pack=None,
    restore_pack=None,
    disabled_packs=request.disabled_packs,
    workspace_id=request.workspace_id,
    support_root=request.support_root,
    realm_root=request.realm_root,
    runtime_profile=request.runtime_profile,
    target_profile=request.target_profile,
    integrations=request.integrations,
)
print(json.dumps({'input': request.to_document(), 'report': report}, sort_keys=True))
"""

    def run(payload: dict) -> dict:
        completed = subprocess.run(
            [sys.executable, "-c", code, json.dumps(payload)],
            cwd=Path(__file__).parents[1],
            env={**os.environ, "ASTRID_STATE_HOME": str(tmp_path / "state")},
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr
        return json.loads(completed.stdout)

    workspace = {
        "workspace_id": WORKSPACE_ID,
        "support_root": str(request.support_root),
        "realm_root": str(request.realm_root),
    }
    first = run(
        {
            "schema_version": 1,
            "operation": "create",
            "workspace": workspace,
            "choices": {
                "runtime_profile": "astrid",
                "target_profile": "custom-target",
                "integrations": ["media"],
            },
        }
    )
    state_path = tmp_path / "state" / "astrid" / "skills.json"
    first_bytes = state_path.read_bytes()

    omitted = run(
        {
            "schema_version": 1,
            "operation": "attach",
            "workspace": workspace,
            "choices": {"runtime_profile": "astrid"},
        }
    )

    assert "target_profile" not in omitted["input"]["choices"]
    assert "integrations" not in omitted["input"]["choices"]
    assert omitted["report"]["setup_selection_changed"] is False
    assert omitted["report"]["setup_selection"]["target_profile"] == "custom-target"
    assert omitted["report"]["setup_selection"]["integrations"] == ["media"]
    assert state_path.read_bytes() == first_bytes

    cleared = run(
        {
            "schema_version": 1,
            "operation": "attach",
            "workspace": workspace,
            "choices": {"runtime_profile": "astrid", "integrations": []},
        }
    )
    assert cleared["input"]["choices"]["integrations"] == []
    assert cleared["report"]["setup_selection"]["target_profile"] == "custom-target"
    assert cleared["report"]["setup_selection"]["integrations"] == []
    assert state_path.read_bytes() != first_bytes


def test_restore_clears_only_restored_disabled_default_before_sync(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRID_STATE_HOME", str(tmp_path / "state"))
    from astrid import skills
    from astrid.skills import state

    current = state.load()
    for harness in state.HARNESSES:
        current["disabled_defaults"][harness] = ["rendering"]
    state.save(current)
    monkeypatch.setattr(
        setup,
        "declarations_from_json",
        lambda _path: (SimpleNamespace(pack_id="vibecomfy"),),
    )
    provision_calls: list[dict] = []

    def provision(*_args, **kwargs):
        provision_calls.append(kwargs)
        return {"ok": True, "disabled": []}

    monkeypatch.setattr(setup, "provision", provision)
    selected_by_harness: dict[str, set[str]] = {}

    def sync(**kwargs):
        persisted = state.load()
        descriptors = skills.list_skills()
        for harness in state.HARNESSES:
            selected_by_harness[harness] = {
                item.pack_id
                for item in skills._sync_descriptors_for_harness(
                    descriptors,
                    persisted,
                    harness,
                    deep=kwargs["deep"],
                    selected_pack_ids=kwargs["selected_pack_ids"],
                )
            }
        return {"actions": []}

    monkeypatch.setattr(skills, "sync", sync)
    setup._compose(
        apply=True,
        offline=True,
        declarations=None,
        deep=False,
        disable_pack="vibecomfy",
        restore_pack=None,
        disabled_packs=(),
        workspace_id=WORKSPACE_ID,
        support_root=tmp_path / "support",
        realm_root=tmp_path / "realm",
        runtime_profile="astrid",
        target_profile=None,
        integrations=None,
    )
    disabled = state.load()
    assert all(
        values == ["rendering", "vibecomfy"]
        for values in disabled["disabled_defaults"].values()
    )

    result = setup._compose(
        apply=True,
        offline=True,
        declarations=None,
        deep=False,
        disable_pack=None,
        restore_pack="vibecomfy",
        disabled_packs=(),
        workspace_id=WORKSPACE_ID,
        support_root=tmp_path / "support",
        realm_root=tmp_path / "realm",
        runtime_profile="astrid",
        target_profile=None,
        integrations=None,
    )

    persisted = state.load()
    assert result["disabled_choices_changed"] is True
    assert all(values == ["rendering"] for values in persisted["disabled_defaults"].values())
    assert all("vibecomfy" in selected for selected in selected_by_harness.values())
    assert all("rendering" not in selected for selected in selected_by_harness.values())
    restore_call = next(call for call in provision_calls if call.get("restore_pack"))
    disable_call = next(call for call in provision_calls if call.get("disable_pack"))
    assert disable_call["disable_pack"] == "vibecomfy"
    assert disable_call["offline"] is True
    assert restore_call["restore_pack"] == "vibecomfy"
    assert restore_call["offline"] is True


def test_preview_uses_proposed_disabled_state_without_writing(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTRID_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setattr(setup, "declarations_from_json", lambda _path: ())
    monkeypatch.setattr(
        setup,
        "provision",
        lambda *_args, **_kwargs: {"ok": True, "disabled": []},
    )
    from astrid import skills
    from astrid.skills import state

    current = state.load()
    state.record_setup_selection(
        current,
        workspace_id=WORKSPACE_ID,
        support_root=str(tmp_path / "support"),
        realm_root=str(tmp_path / "realm"),
        runtime_profile="astrid",
        target_profile="custom-target",
        integrations=["media"],
        default_target_profile=setup.DEFAULT_TARGET_PROFILE,
    )
    state.save(current)
    state_path = state.state_path()
    before = state_path.read_bytes()

    class PlanningAdapter:
        def plan(self, _action, _descriptors, **_kwargs):
            return []

    monkeypatch.setattr(skills, "_resolve_harnesses", lambda _names: {"codex": PlanningAdapter()})
    result = setup._compose(
        apply=False,
        offline=True,
        declarations=None,
        deep=False,
        disable_pack=None,
        restore_pack=None,
        disabled_packs=("vibecomfy",),
        workspace_id=WORKSPACE_ID,
        support_root=tmp_path / "support",
        realm_root=tmp_path / "realm",
        runtime_profile="astrid",
        target_profile=None,
        integrations=None,
    )

    descriptions = [
        step["description"]
        for action in result["skills"]["actions"]
        for step in action["steps"]
    ]
    assert not any("vibecomfy" in description for description in descriptions)
    assert any("rendering" in description for description in descriptions)
    assert any("media" in description for description in descriptions)
    assert result["setup_selection"]["target_profile"] == "custom-target"
    assert result["setup_selection"]["integrations"] == ["media"]
    assert state_path.read_bytes() == before
    assert not (state_path.parent / "skills").exists()
