from __future__ import annotations

import hashlib
import json
from pathlib import Path

from astrid.core.execution.generic_host import GenericPackHost
from tests.test_generic_host import FakeRuntime


class RecordingFakeRuntime(FakeRuntime):
    """The generic-host fake runtime with byte-level object observations."""

    def __init__(self, objects: dict[str, bytes]):
        super().__init__()
        self.objects = dict(objects)
        self.fetched_inputs: list[str] = []
        self.uploaded_outputs: list[dict[str, object]] = []

    def get_object(self, digest: str) -> bytes:
        normalized = digest.removeprefix("sha256:")
        self.fetched_inputs.append(normalized)
        return self.objects[normalized]

    def upload_object(self, path, *, project_id, media_type, filename=None):
        data = Path(path).read_bytes()
        row = super().upload_object(
            path,
            project_id=project_id,
            media_type=media_type,
            filename=filename,
        )
        self.uploaded_outputs.append(
            {
                "filename": filename,
                "media_type": media_type,
                "project_id": project_id,
                "data": data,
                "digest": row.digest,
                "size": row.size,
            }
        )
        return row


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_generic_host_materializes_named_sibling_inputs_and_settles_four_outputs(
    tmp_path: Path,
) -> None:
    input_bytes = {
        "workflow.py": b"workflow = 'synthetic'\n",
        "workflow.vibe.json": b'{"companion":"sibling"}\n',
        "source.json": b'{"origin":"fixture"}\n',
    }
    input_digests = {name: _sha256(data) for name, data in input_bytes.items()}
    outputs = {
        "python": ("workflow.py", "text/x-python", input_bytes["workflow.py"]),
        "companion": (
            "workflow.vibe.json",
            "application/json",
            input_bytes["workflow.vibe.json"],
        ),
        "source": ("source.json", "application/json", input_bytes["source.json"]),
    }
    report = {
        "inputs": {
            name: {
                "basename": name,
                "sha256": input_digests[name],
                "text": data.decode("utf-8"),
            }
            for name, data in input_bytes.items()
        }
    }
    outputs["report"] = (
        "edit-report.json",
        "application/json",
        json.dumps(report, sort_keys=True).encode("utf-8"),
    )

    # This command uses only the host-provided attempt/output directories and
    # canonical sibling basenames. It has no VibeComfy import or runtime need.
    command = (
        "from pathlib import Path; import hashlib, json; "
        "out=Path('{out}'); root=out.parent/'inputs'; "
        "names=['workflow.py','workflow.vibe.json','source.json']; "
        "data=dict((name,(root/name).read_bytes()) for name in names); "
        "out.mkdir(parents=True,exist_ok=True); "
        "(out/'workflow.py').write_bytes(data['workflow.py']); "
        "(out/'workflow.vibe.json').write_bytes(data['workflow.vibe.json']); "
        "(out/'source.json').write_bytes(data['source.json']); "
        "receipt=dict(inputs=dict((name,dict(basename=(root/name).name,sha256="
        "hashlib.sha256(data[name]).hexdigest(),text=data[name].decode('utf-8'))) "
        "for name in names)); "
        "(out/'edit-report.json').write_text(json.dumps(receipt,sort_keys=True),encoding='utf-8')"
    )
    capability_root = tmp_path / "fixture"
    capability_root.mkdir()
    manifest = {
        "schema_version": 1,
        "id": "test.canonical_bundle",
        "name": "Canonical Bundle Fixture",
        "kind": "external",
        "version": "1.0",
        "command": {"argv": ["{python_exec}", "-c", command]},
        "outputs": [
            {
                "name": name,
                "type": "file",
                "path_template": "{out}/" + filename,
                "artifact_type": media_type,
            }
            for name, (filename, media_type, _data) in outputs.items()
        ],
        "metadata": {
            "adapter_family": "cpu",
            "resource_keys": ["cpu"],
            "estimated_scratch_bytes": 1,
        },
    }
    (capability_root / "executor.yaml").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    runtime = RecordingFakeRuntime(
        {input_digests[name]: data for name, data in input_bytes.items()}
    )
    attempt_root = tmp_path / "attempt"
    host = GenericPackHost(
        pack_roots=[tmp_path],
        client=runtime,
        attempt_root=attempt_root,
    )
    host.discover()
    task = {
        "task": {
            "id": "canonical-bundle-task",
            "capability": "test.canonical_bundle",
            "project_id": "fixture-project",
            "attempt_id": "canonical-bundle-attempt",
            "fence": 1,
            "input_object_ids": list(input_digests.values()),
            "spec": {
                "spec": {
                    "inputs": {},
                    "input_digests": [
                        {"name": name, "digest": input_digests[name]}
                        for name in input_bytes
                    ],
                }
            },
        }
    }
    runtime.tasks["canonical-bundle-task"] = task

    settled = host.run_task(task, lease_token="fixture-lease")

    assert settled["task"]["status"] == "completed"
    assert runtime.fetched_inputs == [input_digests[name] for name in input_bytes]
    staged = [attempt_root / "inputs" / name for name in input_bytes]
    assert all(path.is_file() for path in staged)
    assert len({path.parent for path in staged}) == 1
    assert [path.name for path in staged] == list(input_bytes)
    assert [path.read_bytes() for path in staged] == list(input_bytes.values())

    # The report is produced by the child from those exact basenames and bytes.
    assert (attempt_root / "outputs" / "edit-report.json").read_bytes() == outputs[
        "report"
    ][2]

    assert [item["filename"] for item in runtime.uploaded_outputs] == [
        item[0] for item in outputs.values()
    ]
    assert [item["data"] for item in runtime.uploaded_outputs] == [
        item[2] for item in outputs.values()
    ]
    assert [item["digest"] for item in runtime.uploaded_outputs] == [
        _sha256(item[2]) for item in outputs.values()
    ]
    assert all(
        item["project_id"] == "fixture-project" for item in runtime.uploaded_outputs
    )

    settled_outputs = runtime.settlements[0][2]["outputs"]
    assert [item["name"] for item in settled_outputs] == list(outputs)
    assert [item["digest"] for item in settled_outputs] == [
        _sha256(item[2]) for item in outputs.values()
    ]
    assert [item["size"] for item in settled_outputs] == [
        len(item[2]) for item in outputs.values()
    ]
    assert [item["media_type"] for item in settled_outputs] == [
        item[1] for item in outputs.values()
    ]
    assert all("path" not in item for item in settled_outputs)
