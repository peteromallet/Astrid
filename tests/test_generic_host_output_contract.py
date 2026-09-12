"""Pure GenericPackHost output-contract preservation checks."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.core.execution.generic_host import GenericPackHost


_METADATA = {
    "durability": "temporary",
    "regeneration": {
        "available": True,
        "capability_id": "fixture.render",
        "source_refs": ["sha256:" + "a" * 64],
        "recipe_digest": "sha256:" + "b" * 64,
        "exact_inputs": {"seed": 7},
    },
    "coverage": {
        "sampling": {
            "mode": "interval",
            "range": {"start": 0, "end": 24},
            "every_frames": 6,
            "cards": [],
        }
    },
    "producer": {"capability_id": "fixture.render", "view": "test"},
    "provenance": {"render_run_id": "run-1", "source": "fixture"},
}


@pytest.mark.parametrize("inline", [False, True])
def test_upload_outputs_preserves_explicit_contract_fields_without_gen_metadata(
    tmp_path: Path, inline: bool
) -> None:
    payload = b"derived-output"
    staged = tmp_path / "derived.bin"
    staged.write_bytes(payload)
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()

    class Client:
        INLINE_SETTLEMENT_OUTPUTS = inline

        def upload_object(self, path: Path, **kwargs: object) -> object:
            assert path == staged
            assert kwargs == {
                "project_id": None,
                "media_type": "application/octet-stream",
                "filename": "derived.bin",
            }
            return SimpleNamespace(digest=digest, size=len(payload))

    host = object.__new__(GenericPackHost)
    host.client = Client()
    descriptor = {
        "name": "derived",
        "path": str(staged),
        "filename": "derived.bin",
        "artifact_type": "application/octet-stream",
        **_METADATA,
    }

    settled = host._upload_outputs([descriptor], project_id=None)

    assert settled[0]["digest"] == digest
    for field, value in _METADATA.items():
        assert settled[0][field] == value
    assert "generation_id" not in settled[0]
    if inline:
        assert base64.b64decode(settled[0]["data_base64"]) == payload
