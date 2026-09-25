from __future__ import annotations

import json
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.compile import CompilationError, compile_preparation
from astrid.packs.h3_av.src.request import H3RequestError, normalize_request


ROOT = Path(__file__).resolve().parents[3]


def _source_free_request(*, references: list[dict[str, str]] | None = None) -> dict[str, object]:
    return {
        "version": 1,
        "operation": "generate",
        "source": None,
        "output": {"duration": 5},
        "content": {"prompt": "Generate a new audiovisual shot."},
        "changes": {"video": [], "audio": []},
        "references": references or [],
        "overrides": {},
    }


@pytest.mark.parametrize("references", [[], [{"asset": "look.png", "purpose": "appearance"}]])
def test_source_free_generate_is_rejected_even_with_optional_references(
    references: list[dict[str, str]],
) -> None:
    with pytest.raises(H3RequestError, match="source-free operation=generate is not admitted"):
        normalize_request(_source_free_request(references=references))


def test_schema_and_profile_admit_only_source_backed_operations() -> None:
    schema = json.loads(
        (ROOT / "astrid/packs/h3_av/schemas/request.v1.json").read_text(encoding="utf-8")
    )
    assert schema["properties"]["operation"]["enum"] == ["edit", "continue"]

    profile = (ROOT / "astrid/packs/h3_av/profiles/native-v1.yaml").read_text(encoding="utf-8")
    assert "operations: [edit, continue]" in profile
    assert "status: unsupported" in profile


def test_compile_rejects_forged_generate_preparation_before_asset_admission(tmp_path: Path) -> None:
    preparation = {
        "kind": "h3_av_preparation",
        "status": "prepared",
        "runtime_submission": "eligible",
        "request": _source_free_request(),
        "request_digest": "not-used-because-operation-is-rejected-first",
        "assets": [],
    }

    with pytest.raises(CompilationError, match="source-free operation=generate is not admitted"):
        compile_preparation(preparation, out_dir=tmp_path / "compiled")
