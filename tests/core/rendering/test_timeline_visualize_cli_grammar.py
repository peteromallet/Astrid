"""Focused public timeline-visualization grammar checks for V1-01."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.packs.timeline.cli import build_parser


@pytest.fixture()
def parser():
    return build_parser(SimpleNamespace())


@pytest.mark.parametrize(
    "argv",
    [
        [
            "visualize",
            "main",
            "--project",
            "demo",
            "--view",
            "filmstrip",
            "--render-run",
            "latest",
            "--every",
            "0.5",
            "--include-media",
        ],
        [
            "visualize",
            "main",
            "--project",
            "demo",
            "--view",
            "filmstrip",
            "--render-run",
            "run-123",
            "--range",
            "10..20",
            "--every-frames",
            "6",
            "--resolution",
            "320x180",
        ],
    ],
)
def test_documented_visualize_commands_parse(parser, argv):
    parsed = parser.parse_args(argv)
    assert parsed.handler.__name__ == "_cmd_visualize"


def test_visualize_help_exposes_managed_render_provenance(parser):
    help_text = " ".join(
        parser._subparsers._group_actions[0].choices["visualize"].format_help().split()
    )
    assert "--render-run" in help_text
    assert "latest" in help_text
    assert "only view" in help_text
    assert "structure" not in help_text
    assert "--preset" not in help_text
    assert "--resolution" in help_text


def test_visualize_defaults_to_rendered_filmstrip(parser):
    parsed = parser.parse_args(["visualize", "main", "--project", "demo"])

    assert parsed.view == "filmstrip"
    help_text = " ".join(
        parser._subparsers._group_actions[0].choices["visualize"].format_help().split()
    )
    assert "Rendered paired filmstrip" in help_text
    assert "default" in help_text


def test_structural_view_is_not_a_public_cli_route(parser):
    with pytest.raises(SystemExit):
        parser.parse_args(
            ["visualize", "main", "--project", "demo", "--view", "structure"]
        )


@pytest.mark.parametrize("flag", ["--all", "--from-view", "--focus", "--layout", "--filmstrip"])
def test_structural_navigation_flags_are_not_public_cli_routes(parser, flag):
    argv = ["visualize", "main", "--project", "demo", flag]
    if flag in {"--from-view", "--focus", "--layout", "--filmstrip"}:
        argv.append("value")
    with pytest.raises(SystemExit):
        parser.parse_args(argv)


def test_executor_manifest_only_advertises_filmstrip_surface():
    root = Path(__file__).resolve().parents[3]
    manifest = json.loads(
        (root / "astrid/packs/rendering/executors/timeline_visualize/executor.yaml").read_text(
            encoding="utf-8"
        )
    )
    input_names = {item["name"] for item in manifest["inputs"]}
    assert not input_names & {"all", "scope", "layout", "filmstrip", "from_view", "focus", "refresh_root"}
    assert manifest["outputs"][0]["path_template"] == "{out}/filmstrip-view"
    assert manifest["outputs"][1]["path_template"] == "{out}/filmstrip-view/manifest.json"
