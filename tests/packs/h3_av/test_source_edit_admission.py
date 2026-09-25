"""The continuation graph must not claim delivery-clock source edits."""

from pathlib import Path

import pytest

from astrid.packs.h3_av.src.compile import CompilationError, compile_preparation
from astrid.packs.h3_av.src.graph import GraphBindingError, _native_geometry, build_h3_graph_binding
from astrid.packs.h3_av.src.request import normalize_request
from tests.packs.h3_av.test_graph_binding import _prepared
from tests.packs.h3_av.test_request_contract import FIXTURES


@pytest.mark.parametrize(
    ("label", "reason"),
    [
        ("B", "unsupported in-place source edits"),
        ("F", "unsupported in-place source edits"),
        ("X", "unsupported source placement/range"),
    ],
)
def test_source_edit_fixtures_fail_before_graph_or_compilation_output(
    tmp_path: Path, label: str, reason: str
) -> None:
    prepared = _prepared(normalize_request(FIXTURES[label]()))
    with pytest.raises(GraphBindingError, match=reason):
        build_h3_graph_binding(prepared)

    output = tmp_path / "compiled"
    with pytest.raises(CompilationError, match=reason):
        compile_preparation(prepared, out_dir=output)
    assert not output.exists()


def test_unshifted_source_without_edits_keeps_continuation_graph() -> None:
    raw = FIXTURES["B"]()
    raw["media"][0]["edit"] = []
    binding = build_h3_graph_binding(_prepared(normalize_request(raw)))
    assert binding["executable_graph"]["outputs"][0]["node_id"] == "946"
    source_loader = binding["executable_graph"]["compiled_api"]["99"]["inputs"]
    assert source_loader["start_time"] == 0
    assert source_loader["frame_load_cap"] == 0


@pytest.mark.parametrize("label", ["B", "F", "X"])
def test_pinned_full_source_v2v_has_no_delivery_length_or_placement_asset(label: str) -> None:
    """Pinned H3V2VGranularFractionalDenoise._fit_start needs source >= target."""

    request = normalize_request(FIXTURES[label]())
    source = next(item for item in request.value["media"] if item["role"] == "timeline" and item["modality"] == "video")
    source_frames = source["resolved_range"][1] - source["resolved_range"][0]
    placed_at = source["resolved_at"]["value"]
    geometry = _native_geometry(
        request,
        {"delivery": {"shape": [360, 576, 1024]}},
        {"delivery": {"shape": [2, 720000]}},
    )
    assert source_frames == 192
    assert geometry["native"]["video_frames"] == 362
    assert source_frames < geometry["native"]["video_frames"]
    assert placed_at == (72 if label == "X" else 0)
    assert placed_at + source_frames == (264 if label == "X" else 192)
