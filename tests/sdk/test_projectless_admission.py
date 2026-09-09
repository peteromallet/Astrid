from types import SimpleNamespace

import pytest

from astrid.sdk import invocation
from astrid.sdk.contracts import DomainResult, ErrorObject


def test_current_selection_comes_from_runtime():
    client = SimpleNamespace(projects=SimpleNamespace(current=lambda: DomainResult.success(
        {"project": {"project_id": "P-selected", "slug": "demo"}, "scope": "workspace"}
    )))
    assert invocation._runtime_selected_project(client) == "P-selected"


def test_no_selection_is_not_an_auth_failure():
    client = SimpleNamespace(projects=SimpleNamespace(current=lambda: DomainResult.failure(
        ErrorObject("not_found", "no project is selected", {})
    )))
    assert invocation._runtime_selected_project(client) is None
    client.projects.current = lambda: DomainResult.failure(ErrorObject("forbidden", "credential denied", {}))
    with pytest.raises(invocation.AstridSDKError, match="credential denied"):
        invocation._runtime_selected_project(client)


@pytest.mark.parametrize("capability,inputs", [
    ("hivemind.search", {"query": "H3 dialogue"}),
    ("hivemind.get_item", {"kind": "message", "id": "123"}),
    ("hivemind.refresh_media", {"message_id": "123"}),
])
@pytest.mark.parametrize("project", [None, "explicit-project"])
def test_knowledge_reads_use_runtime_admission_without_selection(monkeypatch, capability, inputs, project):
    admitted = []
    def current():
        pytest.fail("public knowledge reads must not depend on project selection")
    client = SimpleNamespace(projects=SimpleNamespace(current=current))
    def admit(capability, **kwargs):
        admitted.append(kwargs)
        return "R-1", "T-1", "A-1", None, {"ok": True}, True, None
    # Keep this test independent of the bundled Hivemind manifests: the
    # project-scope contract belongs to generic executor metadata.
    fake_capability = SimpleNamespace(
        id=capability,
        capability_type="executor",
        native_kind="external",
        definition={"metadata": {"project_scope": "optional"}},
    )
    fake_registry = SimpleNamespace(
        get=lambda executor_id: SimpleNamespace(
            to_dict=lambda: {"id": executor_id, "version": "1"}
        )
    )
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **kwargs: (fake_registry, None, None),
        get_capability=lambda *args, **kwargs: fake_capability,
    )
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)
    monkeypatch.setattr(invocation, "_kernel_invoke", admit)
    result = invocation.invoke(capability, kind="executor", inputs=inputs, client=client, project=project)
    assert result.ok
    assert result.kernel_task_id == "T-1"
    assert admitted[0]["project"] == project
    assert admitted[0]["_client"] is client


@pytest.mark.parametrize("project", [None, "", "   "])
def test_corpus_write_still_requires_project(monkeypatch, project):
    client = SimpleNamespace(projects=SimpleNamespace(current=lambda: DomainResult.failure(
        ErrorObject("not_found", "no project is selected", {})
    )))
    fake_capability = SimpleNamespace(
        id="fixture.write", capability_type="executor", native_kind="external",
        definition={"metadata": {"project_scope": "required"}},
    )
    fake_registry = SimpleNamespace(
        get=lambda executor_id: SimpleNamespace(
            to_dict=lambda: {"id": executor_id, "version": "1"}
        )
    )
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **kwargs: (fake_registry, None, None),
        get_capability=lambda *args, **kwargs: fake_capability,
    )
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)
    monkeypatch.setattr(invocation, "_kernel_invoke", lambda *args, **kwargs: pytest.fail("must not admit"))
    with pytest.raises(invocation.CapabilityPreconditionError, match="project is required"):
        invocation.invoke("fixture.write", kind="executor", client=client, project=project)


def test_project_work_reuses_last_selection(monkeypatch):
    client = SimpleNamespace(projects=SimpleNamespace(current=lambda: DomainResult.success(
        {"project": {"project_id": "P-selected"}}
    )))
    fake_capability = SimpleNamespace(
        id="fixture.write", capability_type="executor", native_kind="external",
        definition={"metadata": {"project_scope": "required"}},
    )
    fake_registry = SimpleNamespace(
        get=lambda executor_id: SimpleNamespace(
            to_dict=lambda: {"id": executor_id, "version": "1"}
        )
    )
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **kwargs: (fake_registry, None, None),
        get_capability=lambda *args, **kwargs: fake_capability,
    )
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)
    seen = []
    def admit(capability, **kwargs):
        seen.append(kwargs["project"])
        return "R-1", "T-1", "A-1", None, {"ok": True}, True, None
    monkeypatch.setattr(invocation, "_kernel_invoke", admit)
    result = invocation.invoke("fixture.write", kind="executor", client=client)
    assert result.ok
    assert seen == ["P-selected"]


@pytest.mark.parametrize("scope", ["required", None])
def test_generic_required_scope_uses_runtime_selection(monkeypatch, scope):
    client = SimpleNamespace(projects=SimpleNamespace(current=lambda: DomainResult.success(
        {"project": {"project_id": "P-selected"}}
    )))
    metadata = {} if scope is None else {"project_scope": scope}
    fake_capability = SimpleNamespace(
        id="fixture.required", capability_type="executor", native_kind="external",
        definition={"metadata": metadata}
    )
    fake_registry = SimpleNamespace(
        get=lambda executor_id: SimpleNamespace(
            to_dict=lambda: {"id": executor_id, "version": "1"}
        )
    )
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **kwargs: (fake_registry, None, None),
        get_capability=lambda *args, **kwargs: fake_capability,
    )
    seen = []
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)
    monkeypatch.setattr(invocation, "_kernel_invoke", lambda *args, **kwargs: (
        seen.append(kwargs["project"]), "R", "T", "A", None, {}, True, None
    )[-7:])
    result = invocation.invoke("fixture.required", kind="executor", client=client)
    assert result.ok
    assert seen == ["P-selected"]


def test_explicit_project_wins_without_selection_lookup(monkeypatch):
    client = SimpleNamespace(projects=SimpleNamespace(current=lambda: pytest.fail("must not look up")))
    fake_capability = SimpleNamespace(
        id="fixture.optional", capability_type="executor", native_kind="external",
        definition={"metadata": {"project_scope": "optional"}},
    )
    fake_registry = SimpleNamespace(
        get=lambda executor_id: SimpleNamespace(
            to_dict=lambda: {"id": executor_id, "version": "1"}
        )
    )
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **kwargs: (fake_registry, None, None),
        get_capability=lambda *args, **kwargs: fake_capability,
    )
    seen = []
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)
    monkeypatch.setattr(invocation, "_kernel_invoke", lambda *args, **kwargs: (
        seen.append(kwargs["project"]), "R", "T", "A", None, {}, True, None
    )[-7:])
    result = invocation.invoke("fixture.optional", kind="executor", client=client, project="P-explicit")
    assert result.ok
    assert seen == ["P-explicit"]


def test_invalid_project_scope_rejected_at_invocation(monkeypatch):
    fake_capability = SimpleNamespace(
        id="fixture.invalid", capability_type="executor",
        definition={"metadata": {"project_scope": "none"}},
    )
    fake_registry = SimpleNamespace(
        get=lambda executor_id: SimpleNamespace(
            to_dict=lambda: {"id": executor_id, "version": "1"}
        )
    )
    fake_sdk = SimpleNamespace(
        _load_registries=lambda **kwargs: (fake_registry, None, None),
        get_capability=lambda *args, **kwargs: fake_capability,
    )
    monkeypatch.setattr(invocation, "_sdk_module", lambda: fake_sdk)
    with pytest.raises(invocation.CapabilityInvocationError, match="project_scope"):
        invocation.invoke("fixture.invalid", kind="executor", project="P-explicit")


def test_generation_destination_uses_connected_runtime():
    from astrid.sdk.generation import _resolve_invoke_destination
    client = SimpleNamespace(projects=SimpleNamespace(current=lambda: DomainResult.success(
        {"project": {"project_id": "P-selected"}}
    )))
    assert _resolve_invoke_destination(out=None, project=None, project_root=None, client=client) == (None, "P-selected")
