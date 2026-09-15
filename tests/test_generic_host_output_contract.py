"""Pure GenericPackHost output-contract preservation checks."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from astrid.core.execution.generic_host import GenericPackHost, HostError, RuntimeProtocolClient


_METADATA = {
    "role": "auxiliary",
    "is_primary": False,
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


@pytest.mark.parametrize(
    ("staged_filename", "runtime_filename", "artifact_type", "output_name"),
    [
        ("images/output_000.png", "output_000.png", "image/png", "generated_images"),
        ("videos/output_000.mp4", "output_000.mp4", "video/mp4", "generated_videos"),
        ("audio/output_000.wav", "output_000.wav", "audio/wav", "generated_audio"),
        ("agent-view/structure.md", "structure.md", "text/markdown", "structure"),
    ],
)
def test_upload_outputs_maps_known_namespaces_at_runtime_boundary(
    tmp_path: Path,
    staged_filename: str,
    runtime_filename: str,
    artifact_type: str,
    output_name: str,
) -> None:
    payload = b"generation-output"
    staged = tmp_path / "attempt" / "outputs" / staged_filename
    staged.parent.mkdir(parents=True)
    staged.write_bytes(payload)
    calls: list[tuple[Path, dict[str, object]]] = []

    class Client:
        INLINE_SETTLEMENT_OUTPUTS = False

        def upload_object(self, path: Path, **kwargs: object) -> object:
            calls.append((path, dict(kwargs)))
            return SimpleNamespace(
                digest="sha256:" + hashlib.sha256(payload).hexdigest(),
                size=len(payload),
            )

    host = object.__new__(GenericPackHost)
    host.client = Client()
    descriptor = {
        "name": output_name,
        "path": str(staged),
        "filename": staged_filename,
        "artifact_type": artifact_type,
        "output_port": output_name,
        "group_key": "main",
        "variant_key": "original",
        "selector": {"group_key": "main", "variant_key": "original"},
        "ordinal": 0,
        "role": "result",
        "is_primary": True,
        "producer": {"capability_id": "fixture.generation"},
        "provenance": {"source": "fixture"},
    }

    settled = host._upload_outputs(
        [descriptor],
        project_id="project-1",
        run_id="run-1",
        task_id="task-1",
        attempt_id="attempt-1",
        lease_id="lease-1",
        fence=1,
        runtime_epoch=1,
    )

    assert calls == [
        (
            staged,
            {
                "project_id": "project-1",
                "media_type": artifact_type,
                "filename": runtime_filename,
                "run_id": "run-1",
                "task_id": "task-1",
                "attempt_id": "attempt-1",
                "lease_id": "lease-1",
                "fence": 1,
                "output_key": output_name,
                "output_port": output_name,
                "runtime_epoch": 1,
            },
        )
    ]
    assert settled[0]["filename"] == runtime_filename
    assert settled[0]["output_port"] == output_name
    assert settled[0]["group_key"] == "main"
    assert settled[0]["variant_key"] == "original"
    assert settled[0]["selector"] == {"group_key": "main", "variant_key": "original"}
    assert settled[0]["ordinal"] == 0
    assert settled[0]["role"] == "result"
    assert settled[0]["producer"] == {"capability_id": "fixture.generation"}
    assert settled[0]["provenance"] == {"source": "fixture"}
    assert descriptor["filename"] == staged_filename
    assert descriptor["path"] == str(staged)


def test_upload_outputs_rejects_known_namespace_leaf_collisions(tmp_path: Path) -> None:
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    calls: list[Path] = []

    def upload_object(path: Path, **_kwargs: object) -> object:
        calls.append(path)
        data = path.read_bytes()
        return SimpleNamespace(
            digest="sha256:" + hashlib.sha256(data).hexdigest(),
            size=len(data),
        )

    host = object.__new__(GenericPackHost)
    host.client = SimpleNamespace(
        INLINE_SETTLEMENT_OUTPUTS=False,
        upload_object=upload_object,
    )

    with pytest.raises(HostError, match="collide on managed filename"):
        host._upload_outputs(
            [
                {"name": "first", "path": str(first), "filename": "agent-view/structure.md"},
                {"name": "second", "path": str(second), "filename": "agent-view/structure.md"},
            ],
            project_id=None,
        )
    assert calls == [first]


def test_runtime_upload_binding_uses_leaf_and_stable_replay_key(tmp_path: Path) -> None:
    payload = b"replay-safe-generation-output"
    staged = tmp_path / "attempt" / "outputs" / "images" / "output_000.png"
    staged.parent.mkdir(parents=True)
    staged.write_bytes(payload)
    calls: list[dict[str, object]] = []

    def ingest_object(data: bytes, **kwargs: object) -> object:
        calls.append({"data": data, **kwargs})
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        return SimpleNamespace(digest=digest, size=len(data))

    client = object.__new__(RuntimeProtocolClient)
    client.executor_id = "executor-1"
    client.INLINE_SETTLEMENT_OUTPUTS = False
    client.generated = SimpleNamespace(ingest_object=ingest_object)
    host = object.__new__(GenericPackHost)
    host.client = client
    descriptor = {
        "name": "generated_images",
        "path": str(staged),
        "filename": "images/output_000.png",
        "artifact_type": "image/png",
        "output_port": "generated_images",
        "group_key": "main",
        "variant_key": "original",
        "selector": {"group_key": "main", "variant_key": "original"},
        "ordinal": 0,
    }
    kwargs = {
        "project_id": "project-1",
        "run_id": "run-1",
        "task_id": "task-1",
        "attempt_id": "attempt-1",
        "lease_id": "lease-1",
        "fence": 1,
        "runtime_epoch": 1,
    }

    host._upload_outputs([descriptor], **kwargs)
    host._upload_outputs([descriptor], **kwargs)

    assert len(calls) == 2
    assert all(call["filename"] == "output_000.png" for call in calls)
    assert all(call["upload_binding"]["filename"] == "output_000.png" for call in calls)
    assert calls[0]["upload_binding"]["output_port"] == "generated_images"
    assert calls[0]["upload_binding"]["output_key"] == "generated_images"
    assert calls[0]["idempotency_key"] == calls[1]["idempotency_key"]
    assert calls[0]["data"] == calls[1]["data"] == payload


@pytest.mark.parametrize(
    "filename",
    [
        "../output.png",
        "images/../output.png",
        "images/nested/output.png",
        "videos/nested/output.mp4",
        "audio/nested/output.wav",
        "agent-view/nested/output.png",
        "agent-view/../output.png",
        "nested/output.png",
        "/tmp/output.png",
        "images\\output.png",
        "images/\x01.png",
        ".",
        "",
    ],
)
def test_upload_outputs_rejects_traversal_and_arbitrary_filename_nesting(
    tmp_path: Path, filename: str
) -> None:
    staged = tmp_path / "output.bin"
    staged.write_bytes(b"output")
    host = object.__new__(GenericPackHost)
    host.client = SimpleNamespace(
        INLINE_SETTLEMENT_OUTPUTS=False,
        upload_object=lambda *_args, **_kwargs: pytest.fail("upload must not be attempted"),
    )

    with pytest.raises(HostError, match="invalid managed filename"):
        host._upload_outputs(
            [{"name": "generated_images", "path": str(staged), "filename": filename}],
            project_id="project-1",
        )
