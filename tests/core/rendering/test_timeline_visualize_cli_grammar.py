"""Focused public timeline-visualization grammar checks for V1-01."""

from __future__ import annotations

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
        [
            "visualize",
            "main",
            "--project",
            "demo",
            "--view",
            "structure",
            "--format",
            "md,png,svg",
            "--layout",
            "both",
            "--filmstrip",
            "off",
            "--json",
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
    assert "not valid with --view filmstrip" in help_text
    assert "--preset" not in help_text
    assert "--resolution" in help_text
