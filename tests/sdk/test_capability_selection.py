from __future__ import annotations

import pytest

from astrid.sdk.remote import RemoteAstridClient, RemoteTasks


class _AdmissionTransport:
    def __init__(self, rows: list[dict[str, str]]) -> None:
        self.rows = rows
        self.admissions: list[dict[str, object]] = []

    def list_capabilities(self, *, cursor=None, limit=50):
        assert cursor is None
        assert limit > 0
        return [self.rows, None]

    def admit_task(self, **kwargs):
        self.admissions.append(kwargs)
        return {"task_id": "task-1", "run_id": "run-1"}


def _admit(transport: _AdmissionTransport, entrypoint: str, capability: str):
    if entrypoint == "tasks":
        return RemoteTasks(transport).create(
            project_id="project-1",
            capability=capability,
            spec={},
            idempotency_key="task-1",
        )
    return RemoteAstridClient(transport).invoke(
        capability,
        project_id="project-1",
        spec={},
        idempotency_key="task-1",
    )


@pytest.mark.parametrize("entrypoint", ["tasks", "client"])
def test_unavailable_row_before_ready_row_uses_ready_for_both_entrypoints(entrypoint):
    transport = _AdmissionTransport(
        [
            {
                "capability_id": "render.basic",
                "definition_digest": "sha256:unavailable",
                "status": "unavailable",
            },
            {
                "capability_id": "render.basic",
                "definition_digest": "sha256:ready",
                "status": "ready",
            },
        ]
    )

    result = _admit(transport, entrypoint, "render.basic")

    assert result.ok
    assert transport.admissions[0]["capability_digest"] == "sha256:ready"


@pytest.mark.parametrize("entrypoint", ["tasks", "client"])
def test_multiple_ready_rows_use_digest_tie_breaking(entrypoint):
    transport = _AdmissionTransport(
        [
            {
                "capability_id": "render.basic",
                "definition_digest": "sha256:z-ready",
                "status": "ready",
            },
            {
                "capability_id": "render.basic",
                "definition_digest": "sha256:a-ready",
                "status": "ready",
            },
        ]
    )

    result = _admit(transport, entrypoint, "render.basic")

    assert result.ok
    assert transport.admissions[0]["capability_digest"] == "sha256:a-ready"


@pytest.mark.parametrize("entrypoint", ["tasks", "client"])
def test_missing_capability_is_not_found(entrypoint):
    transport = _AdmissionTransport(
        [{"capability_id": "other", "definition_digest": "sha256:other"}]
    )

    result = _admit(transport, entrypoint, "render.basic")

    assert not result.ok
    assert result.error is not None
    assert result.error.code == "not_found"
    assert transport.admissions == []


@pytest.mark.parametrize("entrypoint", ["tasks", "client"])
def test_legacy_row_without_status_remains_admissible(entrypoint):
    transport = _AdmissionTransport(
        [{"capability_id": "render.basic", "definition_digest": "sha256:legacy"}]
    )

    result = _admit(transport, entrypoint, "render.basic")

    assert result.ok
    assert transport.admissions[0]["capability_digest"] == "sha256:legacy"


def test_explicit_capability_digest_is_forwarded_unchanged() -> None:
    transport = _AdmissionTransport(
        [{"capability_id": "render.basic", "definition_digest": "sha256:catalog"}]
    )

    result = RemoteTasks(transport).create(
        project_id="project-1",
        capability="render.basic",
        capability_digest="sha256:pinned",
        spec={},
        idempotency_key="task-pinned",
    )

    assert result.ok
    assert transport.admissions[0]["capability_digest"] == "sha256:pinned"


def test_automatic_invoke_key_tracks_selected_capability_digest() -> None:
    transport = _AdmissionTransport(
        [{"capability_id": "render.basic", "definition_digest": "sha256:first"}]
    )
    client = RemoteAstridClient(transport)

    first = client.invoke("render.basic", project_id="project-1", spec={"mode": "render"})
    replay = client.invoke("render.basic", project_id="project-1", spec={"mode": "render"})
    assert first.ok and replay.ok
    first_key = transport.admissions[0]["idempotency_key"]
    assert transport.admissions[1]["idempotency_key"] == first_key

    transport.rows[0]["definition_digest"] = "sha256:refreshed"
    refreshed = client.invoke("render.basic", project_id="project-1", spec={"mode": "render"})
    assert refreshed.ok
    assert transport.admissions[2]["idempotency_key"] != first_key
