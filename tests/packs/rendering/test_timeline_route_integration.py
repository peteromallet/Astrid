"""Narrow parity checks at the public timelines show/visualize boundary."""

from __future__ import annotations

import json
from types import SimpleNamespace

from astrid.packs.timeline.cli import _cmd_show, _cmd_visualize, build_parser
from astrid.sdk.contracts import DomainResult
from astrid.sdk.results import InvocationResult


class _Client:
    def __init__(self) -> None:
        self.visualize_inputs = None
        self.timelines = SimpleNamespace(show=self.show)

    def show(self, project, ref):  # noqa: ANN001
        return DomainResult.success(
            {
                "project_slug": project,
                "timeline_id": "tl-1",
                "slug": ref,
                "config": {
                    "tracks": [{"id": "picture"}],
                    "clips": [
                        {"id": "clip-a", "track": "picture", "at": 0, "hold": 1},
                        {"id": "clip-b", "track": "picture", "at": 1, "hold": 1, "shot_id": "shot-b"},
                    ],
                },
                "occurrences": [{"clip_id": "clip-b", "occurrence_id": "occ-b", "shot_id": "shot-b"}],
                "registry": {"assets": {}},
            }
        )

    def invoke_result(self, capability_id, **kwargs):  # noqa: ANN001
        self.visualize_inputs = kwargs["inputs"]
        return InvocationResult(
            capability_id=capability_id,
            capability_type="executor",
            native_kind="executor",
            ok=True,
            run_id="run-1",
            kernel_run_id=None,
            kernel_task_id=None,
            kernel_attempt_id=None,
            manifest_path=None,
            outputs={},
        )


def test_show_and_visualize_preserve_one_normalized_occurrence_target(capsys) -> None:
    client = _Client()
    parser = build_parser(client)

    show_args = parser.parse_args(
        ["show", "--project", "demo", "main", "--summary", "--occurrence", "occ-b"]
    )
    assert _cmd_show(show_args) == 0
    shown = json.loads(capsys.readouterr().out)["data"]["inspection"]
    assert shown["query"]["occurrence"] == "occ-b"
    assert shown["targets"] == [
        {
            "kind": "clip",
            "timeline_id": "tl-1",
            "occurrence_id": "occ-b",
            "clip_id": "clip-b",
            "shot_id": "shot-b",
            "addressable": True,
        }
    ]

    visualize_args = parser.parse_args(
        ["visualize", "main", "--project", "demo", "--occurrence", "occ-b"]
    )
    assert _cmd_visualize(visualize_args) == 0
    capsys.readouterr()
    assert client.visualize_inputs["occurrence"] == shown["query"]["occurrence"]


def test_plain_show_keeps_the_full_document_shape(capsys) -> None:
    client = _Client()
    parser = build_parser(client)
    args = parser.parse_args(["show", "--project", "demo", "main"])
    assert _cmd_show(args) == 0
    shown = json.loads(capsys.readouterr().out)["data"]
    assert shown["config"]["clips"]
    assert shown.get("kind") != "timeline-inspection"
