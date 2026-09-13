"""One bounded synthetic producer-to-managed-output publication proof."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from banodoco_workspace_client import WorkspaceClient
from runtime_protocol.daemon import RuntimeDaemon
from runtime_protocol.store import RealmStore

from astrid.core.execution.generic_host import GenericPackHost, RuntimeProtocolClient
from astrid.core.execution.guards import ExecutionGuardPolicy


FIXTURE_FILENAME = "publication-contract-fixture.mp4"
FIXTURE_BYTES = b"publication-contract-fixture-v1\n"
CAPABILITY_ID = "publication_contract.render"


def _write_pack(root: Path) -> Path:
    executor_root = root / "executors" / "render"
    executor_root.mkdir(parents=True)
    (root / "pack.yaml").write_text(
        "\n".join(
            (
                "schema_version: 1",
                "id: publication_contract_pack",
                "name: Publication Contract Pack",
                "version: 1.0",
                "capabilities:",
                "  - render",
                "content:",
                "  executors: executors",
                "",
            )
        ),
        encoding="utf-8",
    )
    command = (
        "from pathlib import Path; import hashlib, json; "
        f"data={FIXTURE_BYTES!r}; "
        f"root=Path('{{out}}'); target=root / '{FIXTURE_FILENAME}'; "
        "target.write_bytes(data); "
        "(root / 'manifest.json').write_text(json.dumps({"
        "'schema_version': 1, 'kind': 'publication-contract', 'inputs': {}, "
        "'outputs': [{'name': 'video', 'path': target.name, "
        "'content_hash': 'sha256:' + hashlib.sha256(data).hexdigest(), "
        "'bytes': len(data), 'ordinal': 0, 'role': 'result', 'is_primary': True}], "
        "'created': '2026-09-11T00:00:00Z', 'warnings': []}), encoding='utf-8')"
    )
    (executor_root / "executor.yaml").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": CAPABILITY_ID,
                "name": "Publication Contract Render",
                "kind": "external",
                "version": "1.0",
                "command": {"argv": ["{python_exec}", "-c", command]},
                "outputs": [
                    {
                        "name": "video",
                        "type": "file",
                        "path_template": f"{{out}}/{FIXTURE_FILENAME}",
                        "artifact_type": "video/mp4",
                    }
                ],
                "metadata": {"resource_keys": ["cpu"]},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_publication_contract_producer_upload_fenced_settlement_roundtrip(tmp_path: Path) -> None:
    pack_root = _write_pack(tmp_path / "publication-pack")
    realm_root = tmp_path / "realm"
    RealmStore.initialize(realm_root).close()
    support_root = tmp_path / "support"
    daemon = RuntimeDaemon(
        realm_root,
        support_root=support_root,
        production_worker_credentials=True,
    ).start()
    host: GenericPackHost | None = None
    try:
        owner = WorkspaceClient(daemon.endpoint, daemon.token)
        worker = RuntimeProtocolClient(
            daemon.endpoint,
            Path(daemon.worker_credential_path).read_text(encoding="utf-8").strip(),
        )
        # The RRP host keeps inline settlement as its safe default.  This
        # bounded proof selects its existing object-upload branch so the
        # Runtime ingest HTTP call is part of the observed producer seam.
        worker.INLINE_SETTLEMENT_OUTPUTS = False
        uploads: list[tuple[str, dict[str, Any]]] = []
        real_upload = worker.upload_object

        def record_upload(path: Path, **kwargs: Any) -> Any:
            uploads.append((Path(path).name, dict(kwargs)))
            return real_upload(path, **kwargs)

        worker.upload_object = record_upload  # type: ignore[method-assign]
        host = GenericPackHost(
            pack_roots=[pack_root],
            client=worker,
            attempt_root=tmp_path / "attempts",
            execution_policy=ExecutionGuardPolicy(
                scratch_floor_bytes=1,
                evidence_cap_bytes=1024 * 1024,
                deadline_seconds=30.0,
            ),
        )
        records = {record.id: record for record in host.discover()}
        assert CAPABILITY_ID in records
        host.preflight(CAPABILITY_ID)
        host.register()

        admitted = owner.admit_task(
            capability_id=CAPABILITY_ID,
            capability_digest=records[CAPABILITY_ID].capability_digest,
            input_object_ids=[],
            idempotency_key="publication-contract-task-v1",
            spec={"inputs": {}},
            settlement_effect=None,
        )
        task_id = str(admitted["task_id"])
        outcome = host.claim_once()
        assert outcome is not None

        completed = owner.get_task(task_id)
        assert completed.state == "succeeded"
        assert completed.result is not None
        settled_outputs = completed.result["outputs"]
        assert len(settled_outputs) == 1
        settled = settled_outputs[0]
        expected_digest = "sha256:" + hashlib.sha256(FIXTURE_BYTES).hexdigest()
        assert len(uploads) == 1
        upload_filename, upload_kwargs = uploads[0]
        assert upload_filename == FIXTURE_FILENAME
        assert upload_kwargs["project_id"] is None
        assert upload_kwargs["media_type"] == "video/mp4"
        assert upload_kwargs["filename"] == FIXTURE_FILENAME
        assert upload_kwargs["run_id"] == completed.run_id
        assert upload_kwargs["task_id"] == task_id
        assert upload_kwargs["attempt_id"] == completed.attempt_id
        assert upload_kwargs["output_key"] == "video"
        assert upload_kwargs["output_port"] == "video"
        assert upload_kwargs["fence"] >= 1
        assert upload_kwargs["runtime_epoch"] == completed.runtime_epoch
        assert settled["digest"] == expected_digest
        assert settled["filename"] == FIXTURE_FILENAME
        assert settled["media_type"] == "video/mp4"
        assert settled["size"] == len(FIXTURE_BYTES)
        assert owner.get_object(expected_digest).data == FIXTURE_BYTES

        managed_outputs, cursor = owner.list_managed_outputs(task_id)
        assert cursor is None
        assert len(managed_outputs) == 1
        managed = managed_outputs[0]
        reread = owner.get_managed_output(managed.association_id)
        assert reread == managed
        assert managed.task_id == task_id
        assert managed.project_id is None
        assert managed.object_id == expected_digest
        assert managed.digest == expected_digest
        assert managed.filename == FIXTURE_FILENAME
        assert "/" not in managed.filename
        assert managed.media_type == "video/mp4"
        assert managed.size == len(FIXTURE_BYTES)
        assert managed.manifest_ref is None
        assert managed.generation_id is None
        assert managed.state == "available"
        assert managed.producer["capability_id"] == CAPABILITY_ID
        assert managed.provenance["task_id"] == task_id
        assert managed.provenance["attempt_id"] == managed.attempt_id
        assert isinstance(managed.provenance["fence"], int)

        generations = daemon.service.store.conn.execute(
            "SELECT COUNT(*) AS count FROM generations"
        ).fetchone()
        variants = daemon.service.store.conn.execute(
            "SELECT COUNT(*) AS count FROM generation_variants"
        ).fetchone()
        assert int(generations["count"]) == 0
        assert int(variants["count"]) == 0
    finally:
        if host is not None:
            host.shutdown()
        daemon.stop()
