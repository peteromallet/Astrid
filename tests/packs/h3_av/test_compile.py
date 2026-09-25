from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from astrid.packs.h3_av.executors.compile.run import main as compile_executor_main
from astrid.packs.h3_av.src.compile import CompilationError, compile_preparation
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request


PROMPT = (
    'End state: Morpheus remains in the same close/medium shot, seated in the red chair in the dark room, '
    'wearing the black coat, with the same camera position, lighting, identity, and acoustic perspective. '
    'In the generated continuation, he begins by saying the exact line: "This is your last chance." He then '
    'continues with the exact line: "You can poo or pee on my face." Preserve the supplied audiovisual prefix, '
    "including Morpheus's original voice, cadence, room tone, and timing, then carry that voice and acoustic "
    'perspective into both requested lines. Keep his expression calm and deliberate, looking forward with one '
    'hand resting in a restrained natural gesture. No camera change, reset, new character, subtitles, or visible text.'
)


def _request(prompt: str = PROMPT):
    return normalize_request(
        {
            "version": 1,
            "operation": "continue",
            "source": {"asset": "source", "range": [0, 4]},
            "output": {"duration": 8},
            "content": {"prompt": prompt},
            "changes": {
                "video": [{"during": [4, 8], "area": {"full_frame": True}, "action": "generate"}],
                "audio": [{"during": [4, 8], "action": "generate"}],
            },
            "references": [],
            "overrides": {"seed": 42, "steps": 8},
        }
    )


def test_compile_freezes_bundle_and_is_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    request = _request()
    preparation = prepare_request(request, asset_map={"source": str(source)})

    first = compile_preparation(preparation, out_dir=tmp_path / "first")
    second = compile_preparation(preparation, out_dir=tmp_path / "second")

    assert first["compilation_digest"] == second["compilation_digest"]
    assert Path(first["managed_assets"]["path"]).read_bytes() == Path(second["managed_assets"]["path"]).read_bytes()
    assert first["workflow_inputs"] == {
        "model": "minimax_h3_ref2va_pruned_int8_convrot.safetensors",
        "seed": 42,
        "source_video": next(iter(first["managed_assets"]["manifest"]["assets"]))["member"].split("/")[-1],
        "steps": 8,
    }
    for name in ("workflow.py", "workflow.vibe.json", "source.json"):
        frozen = Path(first["workflow"][name]["path"])
        assert frozen.parent.name == "workflow-bundle"
        assert frozen.is_file()


def test_compile_rejects_prompt_the_graph_cannot_bind(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    preparation = prepare_request(_request("a different prompt"), asset_map={"source": str(source)})

    with pytest.raises(CompilationError, match="fixed prompt"):
        compile_preparation(preparation, out_dir=tmp_path / "compiled")


def test_compilation_manifest_round_trips(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    result = compile_preparation(
        prepare_request(_request(), asset_map={"source": str(source)}),
        out_dir=tmp_path / "compiled",
    )
    persisted = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    assert persisted["compilation_digest"] == result["compilation_digest"]
    assert persisted["capabilities"]["operation"] == "continue"


def test_compile_executor_publishes_selected_bundle_members(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"fixture-video")
    preparation = prepare_request(_request(), asset_map={"source": str(source)})
    preparation_path = tmp_path / "preparation.json"
    preparation_path.write_text(json.dumps(preparation), encoding="utf-8")
    output = tmp_path / "compile-output"

    assert compile_executor_main(["--preparation", str(preparation_path), "--out", str(output)]) == 0

    for filename in ("workflow.py", "workflow.vibe.json", "source.json"):
        assert (output / filename).is_file()
    manifest = json.loads((output / "compilation.json").read_text(encoding="utf-8"))
    for filename in ("workflow.py", "workflow.vibe.json", "source.json"):
        assert hashlib.sha256((output / filename).read_bytes()).hexdigest() == manifest["workflow"][filename]["sha256"]
