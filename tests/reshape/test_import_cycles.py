"""Regression coverage for repaired core package boundaries."""

from pathlib import Path

from scripts.reshape.import_cycles import build_graph, cycle_pairs


REPAIRED_PAIRS = {
    frozenset(("events", "repositories")),
    frozenset(("events", "schema_packs")),
    frozenset(("integrations", "kernel")),
    frozenset(("integrations", "project")),
    frozenset(("preferences", "session")),
}


def test_repaired_core_boundaries_remain_acyclic() -> None:
    root = Path(__file__).resolve().parents[2] / "astrid" / "core"
    graph = build_graph(root, "astrid.core", "top", True)
    present = {
        frozenset((left.rsplit(".", 1)[-1], right.rsplit(".", 1)[-1]))
        for left, right in cycle_pairs(graph)
    }
    assert REPAIRED_PAIRS.isdisjoint(present)
