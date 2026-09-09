from __future__ import annotations

import json

from banodoco_workspace_client.generated import WorkspaceClient as GeneratedWorkspaceClient
from astrid.packs.timeline.cli import build_parser
from astrid.sdk.contracts import DomainResult
from astrid.sdk.remote import RemoteTimelines
from astrid.sdk.workspace_client import WorkspaceClient


def test_generated_replacement_transport_posts_typed_payload() -> None:
    calls = []

    def transport(method, path, headers, body):
        calls.append((method, path, headers, body))
        return 200, {}, json.dumps({"data": {"config_version": 2}, "receipt": {"command_kind": "timeline.clip.replace"}}).encode()

    result = GeneratedWorkspaceClient("http://127.0.0.1:1", "token", transport=transport).replace_timeline_clip(
        "timeline-1",
        clip_id="clip-1",
        source_object_id="sha256:" + "a" * 64,
        expected_version=1,
        timing="preserve-duration",
        idempotency_key="replace-1",
    )

    assert result["config_version"] == 2
    method, path, headers, body = calls[0]
    assert method == "POST"
    assert path == "/v1/timelines/timeline-1/replace-clip"
    assert headers["Authorization"] == "Bearer token"
    assert headers["Idempotency-Key"] == "replace-1"
    assert json.loads(body) == {
        "clip_id": "clip-1",
        "source_object_id": "sha256:" + "a" * 64,
        "expected_version": 1,
        "timing": "preserve-duration",
    }


def test_remote_timelines_replacement_is_thin_and_keyed() -> None:
    class Transport:
        def __init__(self):
            self.calls = []

        def replace_timeline_clip(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"data": {"config_version": 2}, "receipt": None}

    transport = Transport()
    result = RemoteTimelines(transport).replace_clip(
        "project-1",
        "timeline-1",
        clip_id="clip-1",
        source_object_id="sha256:" + "b" * 64,
        expected_version=4,
        idempotency_key="replace-4",
    )

    assert result.ok and result.data == {"config_version": 2}
    assert transport.calls == [
        (("timeline-1",), {
            "clip_id": "clip-1",
            "source_object_id": "sha256:" + "b" * 64,
            "expected_version": 4,
            "timing": "preserve-duration",
            "idempotency_key": "replace-4",
        })
    ]


def test_timeline_replace_clip_cli_forwards_explicit_inputs(capsys) -> None:
    class Timelines:
        def __init__(self):
            self.calls = []

        def replace_clip(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return DomainResult.success({"config_version": 2}, idempotency_key=kwargs["idempotency_key"])

    class Client:
        def __init__(self):
            self.timelines = Timelines()

    client = Client()
    parser = build_parser(client)
    parsed = parser.parse_args([
        "replace-clip", "--project", "project-1", "timeline-1",
        "--clip-id", "clip-1",
        "--source-object-id", "sha256:" + "c" * 64,
        "--expected-version", "7",
        "--idempotency-key", "replace-7",
    ])

    assert parsed.handler(parsed) == 0
    assert json.loads(capsys.readouterr().out)["data"] == {"config_version": 2}
    assert client.timelines.calls == [
        (("project-1", "timeline-1"), {
            "clip_id": "clip-1",
            "source_object_id": "sha256:" + "c" * 64,
            "expected_version": 7,
            "timing": "preserve-duration",
            "idempotency_key": "replace-7",
        })
    ]
