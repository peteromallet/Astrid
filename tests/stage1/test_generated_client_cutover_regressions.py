"""Pass-ready regression tests for the remaining generated-client cutover gaps.

These tests intentionally remain uncommitted until the generated runtime
operations and raw transport seam are implemented.
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from astrid.sdk.remote import RemoteAstridClient, RemoteProjects, RemoteShots, RemoteTasks
from astrid.sdk.workspace_client import WorkspaceClient


class _RecordingClient:
    def __init__(self) -> None:
        self.project_call: tuple[tuple[object, ...], dict[str, object]] | None = None
        self.task_call: dict[str, object] | None = None
        self.promotion_call: tuple[tuple[object, ...], dict[str, object]] | None = None

    def create_project(self, *args: object, **kwargs: object) -> dict[str, str]:
        self.project_call = (args, kwargs)
        return {"project_id": "project-1"}

    def list_capabilities(self, *, cursor=None, limit=50):
        assert cursor is None
        assert limit == 50
        return [[{"capability_id": "capability-1", "definition_digest": "digest-1"}], None]

    def admit_task(self, **kwargs: object) -> dict[str, str]:
        self.task_call = kwargs
        return {"task_id": "task-1"}

    def promote_project_shot_candidate(
        self, *args: object, **kwargs: object
    ) -> dict[str, object]:
        self.promotion_call = (args, kwargs)
        return {
            "data": {"promotion": {"primary_item_id": "candidate-1"}, "invalidation": {}},
            "receipt": None,
        }


class _ReceiptClient(_RecordingClient):
    def admit_task(self, **kwargs: object) -> dict[str, object]:
        self.task_call = kwargs
        return {
            "data": {"task_id": "task-1"},
            "receipt": {
                "receipt_id": "txn-1",
                "command_kind": "task.create",
                "idempotency_key": str(kwargs["idempotency_key"]),
                "request_hash": "hash-1",
                "project_id": "project-1",
                "project_seq": [1, 1],
                "event_ids": ["event-1"],
                "result": {"task_id": "task-1"},
                "created_at": "2026-01-01T00:00:00Z",
            },
        }


class GeneratedClientCutoverRegressionTest(unittest.TestCase):
    def test_project_create_forwards_slug_and_metadata(self) -> None:
        client = _RecordingClient()
        result = RemoteProjects(client).create(
            slug="demo",
            name="Demo",
            metadata={"theme": "dark"},
            idempotency_key="project-key",
        )

        self.assertTrue(result.ok)
        assert client.project_call is not None
        args, kwargs = client.project_call
        self.assertEqual(args, ("Demo",))
        self.assertEqual(kwargs["slug"], "demo")
        self.assertEqual(kwargs["metadata"], {"theme": "dark"})
        self.assertEqual(kwargs["idempotency_key"], "project-key")

    def test_task_create_forwards_spec(self) -> None:
        client = _RecordingClient()
        spec = {"prompt": "a generated client regression"}
        result = RemoteTasks(client).create(
            project_id="project-1",
            capability="capability-1",
            spec=spec,
            input_manifest=["sha256:input"],
            storage_estimate={"scratch_bytes": 100, "output_bytes": 23},
            idempotency_key="task-key",
        )

        self.assertTrue(result.ok)
        assert client.task_call is not None
        self.assertEqual(client.task_call["spec"], spec)
        self.assertEqual(client.task_call["capability_id"], "capability-1")
        self.assertEqual(client.task_call["input_object_ids"], ["sha256:input"])
        self.assertEqual(
            client.task_call["storage_estimate"],
            {"scratch_bytes": 100, "output_bytes": 23},
        )
        self.assertEqual(client.task_call["schema_version"], "1")
        self.assertEqual(client.task_call["settlement_effect"], {})

    def test_task_create_emits_complete_hc04_admission_defaults(self) -> None:
        client = _RecordingClient()
        result = RemoteTasks(client).create(
            project_id="project-1",
            capability="capability-1",
            spec={"family": "image_generation", "params": {"prompt": "hello"}},
            input_manifest=["object-a", "object-b"],
            idempotency_key="task-key",
        )

        self.assertTrue(result.ok)
        assert client.task_call is not None
        self.assertEqual(
            client.task_call,
            {
                "capability_id": "capability-1",
                "capability_digest": "digest-1",
                "input_object_ids": ["object-a", "object-b"],
                "idempotency_key": "task-key",
                "project_id": "project-1",
                "schema_version": "1",
                "spec": {"family": "image_generation", "params": {"prompt": "hello"}},
                "settlement_effect": {},
                "storage_estimate": {"scratch_bytes": 0, "output_bytes": 0},
            },
        )

    def test_generic_invoke_forwards_complete_hc04_admission(self) -> None:
        client = _RecordingClient()
        result = RemoteAstridClient(client).invoke(
            "capability-1",
            project_id="project-1",
            spec={"family": "image_generation", "params": {}},
            input_object_ids=["object-a"],
            idempotency_key="invoke-key",
            settlement_effect={"publish": {"generation_id": "generation-1"}},
            storage_estimate={"scratch_bytes": 100, "output_bytes": 23},
        )

        self.assertTrue(result.ok)
        assert client.task_call is not None
        self.assertEqual(client.task_call["capability_id"], "capability-1")
        self.assertEqual(client.task_call["capability_digest"], "digest-1")
        self.assertEqual(client.task_call["input_object_ids"], ["object-a"])
        self.assertEqual(client.task_call["project_id"], "project-1")
        self.assertEqual(client.task_call["schema_version"], "1")
        self.assertEqual(client.task_call["settlement_effect"], {"publish": {"generation_id": "generation-1"}})
        self.assertEqual(client.task_call["storage_estimate"], {"scratch_bytes": 100, "output_bytes": 23})

    def test_explicit_capability_digest_skips_catalog_inference(self) -> None:
        class ExplicitClient(_RecordingClient):
            def list_capabilities(self, **kwargs: object):
                raise AssertionError("explicit HC-04 digest must not require catalog inference")

        client = ExplicitClient()
        result = RemoteTasks(client).create(
            project_id="project-1",
            capability="capability-1",
            capability_digest="digest-explicit",
            spec={"family": "image_generation", "params": {}},
            idempotency_key="task-key",
        )

        self.assertTrue(result.ok)
        assert client.task_call is not None
        self.assertEqual(client.task_call["capability_digest"], "digest-explicit")

    def test_workspace_client_admit_task_supplies_neutral_hc04_defaults(self) -> None:
        client = WorkspaceClient.__new__(WorkspaceClient)
        calls: list[tuple[str, dict[str, object]]] = []

        def call(operation: str, **kwargs: object) -> dict[str, object]:
            calls.append((operation, kwargs))
            return {"task_id": "task-1"}

        client._call_generated = call
        value = client.admit_task(
            capability_id="capability-1",
            capability_digest="digest-1",
            input_object_ids=["object-a"],
            idempotency_key="task-key",
            project_id="project-1",
            spec={"family": "image_generation", "params": {}},
        )

        self.assertEqual(value, {"task_id": "task-1"})
        self.assertEqual(calls[0], ("admit_task", {
            "capability_id": "capability-1",
            "capability_digest": "digest-1",
            "input_object_ids": ["object-a"],
            "idempotency_key": "task-key",
            "schema_version": "1",
            "settlement_effect": {},
            "project_id": "project-1",
            "spec": {"family": "image_generation", "params": {}},
            "storage_estimate": {"scratch_bytes": 0, "output_bytes": 0},
        }))

    def test_hc04_sdk_adapters_do_not_run_local_engine_or_supabase_authority(self) -> None:
        sdk_root = Path(__file__).resolve().parents[2] / "astrid" / "sdk"
        source = (sdk_root / "remote.py").read_text(encoding="utf-8") + (sdk_root / "workspace_client.py").read_text(encoding="utf-8")
        for forbidden in ("run_sync", "subprocess", "supabase", "route_key", "selected_backend", "Worker backend"):
            self.assertNotIn(forbidden, source)

    def test_generic_invoke_forwards_server_receipt(self) -> None:
        result = RemoteAstridClient(_ReceiptClient()).invoke(
            "capability-1", project_id="project-1", spec={}, idempotency_key="task-key"
        )
        self.assertTrue(result.ok)
        assert result.receipt is not None
        self.assertEqual(result.receipt.receipt_id, "txn-1")
        self.assertEqual(result.receipt.event_ids, ("event-1",))

    def test_shot_promotion_forwards_atomic_generated_operation(self) -> None:
        client = _RecordingClient()
        timeline = [{"id": "asset-1"}]
        result = RemoteShots(client).promote_candidate(
            "project-1",
            "shot-1",
            "candidate-1",
            expected_head_seq=4,
            timeline_assets=timeline,
            idempotency_key="promotion-key",
        )
        self.assertTrue(result.ok)
        assert client.promotion_call is not None
        args, kwargs = client.promotion_call
        self.assertEqual(args, ("project-1", "shot-1", "candidate-1"))
        self.assertEqual(kwargs["expected_head_seq"], 4)
        self.assertEqual(kwargs["timeline_assets"], timeline)
        self.assertEqual(kwargs["idempotency_key"], "promotion-key")

    def test_product_sdk_has_no_raw_request_seam(self) -> None:
        sdk_root = Path(__file__).resolve().parents[2] / "astrid" / "sdk"
        offenders: list[str] = []
        for path in sorted(sdk_root.glob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == "request":
                    offenders.append(f"{path.name}:{node.lineno}: request()")
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "request"
                ):
                    offenders.append(f"{path.name}:{node.lineno}: .request")
        self.assertEqual(offenders, [], "raw transport seams remain: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
