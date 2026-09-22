from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from typing import Any

from PIL import Image

from astrid.core.execution.thumbnail_backfill import (
    THUMBNAIL_BACKFILL_CAPABILITY_ID,
    run_thumbnail_backfill,
)
from astrid.core.receipts.canonical import canonical_json

SOURCE = "sha256:" + "a" * 64


class VersionConflictError(RuntimeError):
    code = "conflict"
    details = {"expected": 1, "actual": 2}

    def __init__(self) -> None:
        super().__init__("stale thumbnail attachment target generation version")


def _png() -> bytes:
    image = Image.new("RGB", (640, 320), (20, 80, 140))
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


@dataclass
class FakeRuntime:
    generations: list[dict[str, Any]]
    variants: dict[str, list[dict[str, Any]]]
    source_bytes: bytes

    def __post_init__(self) -> None:
        self.admissions: list[dict[str, Any]] = []
        self.uploads: list[dict[str, Any]] = []
        self.settlements: list[dict[str, Any]] = []
        self.executor_idempotency_keys: list[str] = []
        self.failed_attempts: list[dict[str, Any]] = []
        self.cancelled_tasks: list[str] = []
        self.retried_tasks: list[dict[str, Any]] = []
        self._claims: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, dict[str, Any]] = {}
        self._admission_tasks: dict[str, str] = {}
        self._attempt_tasks: dict[str, str] = {}
        self.fail_upload = False
        self.conflict_on_first_settlement = False

    def health(self) -> dict[str, Any]:
        return {"runtime_epoch": 3}

    def get_project(self, project: str):
        assert project == "project-1"
        return {"project_id": "project-1"}

    def list_generations(self, project: str, *, cursor=None, limit=50):
        assert project == "project-1"
        if cursor is None:
            return [self.generations[:1], "page-2"]
        return [self.generations[1:], None]

    def list_variants(self, generation_id: str, *, cursor=None, limit=50):
        return [self.variants[generation_id], None]

    def get_generation(self, generation_id: str):
        return next(
            item for item in self.generations if item["generation_id"] == generation_id
        )

    def list_project_objects(self, project: str, *, cursor=None, limit=200):
        return [[], None]

    def get_object(self, object_id: str):
        assert object_id == SOURCE
        return {"data": self.source_bytes}

    def head_object(self, object_id: str):
        assert object_id == SOURCE
        return {"headers": {"content-type": "image/png"}}

    def register_capability(self, *args, **kwargs):
        assert args[0] == THUMBNAIL_BACKFILL_CAPABILITY_ID
        return {"capability_id": args[0]}

    def register_executor(self, registration, *, idempotency_key):
        assert registration["executor_id"] == "owner"
        assert registration["capabilities"][0]["capability_id"] == THUMBNAIL_BACKFILL_CAPABILITY_ID
        self.executor_idempotency_keys.append(idempotency_key)
        return registration

    def admit_task(self, **kwargs):
        self.admissions.append(kwargs)
        generation_id = kwargs["settlement_effect"]["target_id"]
        admission_key = kwargs["idempotency_key"]
        if admission_key in self._admission_tasks:
            return {"data": dict(self._tasks[self._admission_tasks[admission_key]])}
        ordinal = 1 + sum(
            task["generation_id"] == generation_id for task in self._tasks.values()
        )
        task_id = f"task-{generation_id}" if ordinal == 1 else f"task-{generation_id}-{ordinal}"
        task = {
            "task_id": task_id,
            "run_id": f"run-{generation_id}-{ordinal}",
            "project_id": "project-1",
            "state": "queued",
            "version": 1,
            "generation_id": generation_id,
            "input_object_ids": list(kwargs["input_object_ids"]),
            "spec": dict(kwargs["spec"]),
            "expected_effect": dict(kwargs["settlement_effect"]),
            "attempt_count": 0,
        }
        self._tasks[task_id] = task
        self._admission_tasks[admission_key] = task_id
        self._queue_claim(task_id)
        return {"data": dict(task)}

    def _queue_claim(self, task_id: str) -> None:
        task = self._tasks[task_id]
        task["attempt_count"] += 1
        attempt_count = task["attempt_count"]
        attempt_id = (
            f"attempt-{task['generation_id']}"
            if attempt_count == 1
            else f"attempt-{task['generation_id']}-{attempt_count}"
        )
        self._attempt_tasks[attempt_id] = task_id
        self._claims[task_id] = {
            "attempt_id": attempt_id,
            "task_id": task_id,
            "run_id": task["run_id"],
            "project_id": "project-1",
            "lease_id": f"lease-{task['generation_id']}-{attempt_count}",
            "fence": attempt_count,
            "runtime_epoch": 3,
            "input_object_ids": list(task["input_object_ids"]),
            "spec": dict(task["spec"]),
            "expected_effect": dict(task["expected_effect"]),
        }

    def get_task(self, task_id: str):
        return dict(self._tasks[task_id])

    def retry_task(self, task_id, *, expected_version, idempotency_key):
        task = self._tasks[task_id]
        assert task["state"] == "failed"
        assert expected_version == task["version"]
        task["state"] = "queued"
        task["version"] += 1
        self.retried_tasks.append(
            {
                "task_id": task_id,
                "expected_version": expected_version,
                "idempotency_key": idempotency_key,
            }
        )
        self._queue_claim(task_id)
        return {"data": dict(task)}

    def claim_task(self, *, executor_id, capability_ids, idempotency_key, runtime_epoch):
        task_id = next(iter(self._claims))
        self._tasks[task_id]["state"] = "running"
        return self._claims.pop(task_id)

    def ingest_object(self, data, *, media_type, filename, upload_binding, idempotency_key):
        assert media_type == "image/jpeg"
        assert filename == "thumbnail.jpg"
        if self.fail_upload:
            raise RuntimeError("upload failed")
        self.uploads.append({"data": data, "binding": upload_binding, "idempotency_key": idempotency_key})
        return {"data": {"object_id": "sha256:" + "b" * 64}}

    def settle_attempt(self, attempt_id, settlement, *, idempotency_key):
        if self.conflict_on_first_settlement:
            self.conflict_on_first_settlement = False
            target = settlement["effect"]["target_id"]
            generation = next(
                item for item in self.generations if item["generation_id"] == target
            )
            generation["version"] += 1
            raise VersionConflictError()
        self.settlements.append(settlement)
        task_id = self._attempt_tasks.get(attempt_id)
        if task_id is not None:
            self._tasks[task_id]["state"] = "succeeded"
            self._tasks[task_id]["version"] += 1
        target = settlement["effect"]["target_id"]
        generation = next(
            (item for item in self.generations if item["generation_id"] == target),
            None,
        )
        if generation is not None:
            generation["metadata"]["thumbnail"] = {
                "object_id": settlement["outputs"][0]["digest"],
                "source_object_id": SOURCE,
                "recipe_version": 1,
            }
            generation["version"] += 1
        return {"data": {"task_id": f"task-{target}"}}

    def fail_attempt(self, attempt_id, *, lease_id, fence, runtime_epoch, error, idempotency_key):
        self.failed_attempts.append(
            {
                "attempt_id": attempt_id,
                "lease_id": lease_id,
                "fence": fence,
                "runtime_epoch": runtime_epoch,
                "error": error,
                "idempotency_key": idempotency_key,
            }
        )
        task_id = self._attempt_tasks[attempt_id]
        self._tasks[task_id]["state"] = "failed"
        self._tasks[task_id]["version"] += 1
        return {"data": {"attempt_id": attempt_id}}

    def cancel_task(self, task_id, *, idempotency_key):
        self.cancelled_tasks.append(task_id)
        self._claims.pop(task_id, None)
        return {"data": {"task_id": task_id}}


def _generation(generation_id: str, *, metadata=None) -> dict[str, Any]:
    return {
        "generation_id": generation_id,
        "project_id": "project-1",
        "metadata": dict(metadata or {}),
        "version": 1,
    }


def _variant(generation_id: str, *, media_type="image/png") -> dict[str, Any]:
    return {
        "generation_id": generation_id,
        "variant_id": f"variant-{generation_id}",
        "variant_type": "original",
        "object_id": SOURCE,
        "metadata": {"is_primary": True, "media_type": media_type},
    }


def test_backfill_uploads_and_settles_then_rerun_is_noop() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1"), _generation("g-2")],
        variants={"g-1": [_variant("g-1")], "g-2": [_variant("g-2")]},
        source_bytes=_png(),
    )

    first = run_thumbnail_backfill(
        runtime,
        project="project-1",
        actor_id="owner",
        limit=2,
    )
    assert first.attached == 2
    assert first.failed == 0
    assert len(runtime.uploads) == 2
    assert len(runtime.settlements) == 2
    assert len(set(runtime.executor_idempotency_keys)) == 2
    assert all(
        upload["idempotency_key"]
        == "output-" + hashlib.sha256(canonical_json(upload["binding"]).encode()).hexdigest()
        for upload in runtime.uploads
    )
    assert all(
        settlement["effect"]["effect_type"] == "generation.thumbnail.attach"
        for settlement in runtime.settlements
    )
    assert all(upload["binding"]["output_port"] == "thumbnail" for upload in runtime.uploads)

    second = run_thumbnail_backfill(
        runtime,
        project="project-1",
        actor_id="owner",
        limit=2,
    )
    assert second.attached == 0
    assert second.already_ready == 2
    assert len(runtime.uploads) == 2
    assert len(runtime.settlements) == 2


def test_backfill_dry_run_does_not_admit_or_upload() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1")],
        variants={"g-1": [_variant("g-1")]},
        source_bytes=_png(),
    )

    report = run_thumbnail_backfill(
        runtime,
        project="project-1",
        actor_id=None,
        limit=1,
        dry_run=True,
    )
    assert report.dry_run is True
    assert report.attached == 1
    assert runtime.admissions == []
    assert runtime.uploads == []
    assert runtime.settlements == []


def test_backfill_fails_the_requested_attempt_when_upload_fails() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1")],
        variants={"g-1": [_variant("g-1")]},
        source_bytes=_png(),
    )
    runtime.fail_upload = True

    report = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)

    assert report.failed == 1
    assert report.attached == 0
    assert runtime.settlements == []
    assert [item["attempt_id"] for item in runtime.failed_attempts] == ["attempt-g-1"]
    assert runtime.failed_attempts[0]["error"]["code"] == "thumbnail_backfill_failed"


def test_backfill_rerun_retries_the_failed_admission_before_claiming() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1")],
        variants={"g-1": [_variant("g-1")]},
        source_bytes=_png(),
    )
    runtime.fail_upload = True

    failed = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)
    assert failed.failed == 1
    assert runtime._tasks["task-g-1"]["state"] == "failed"

    runtime.fail_upload = False
    retried = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)

    assert retried.failed == 0
    assert retried.attached == 1
    assert len(runtime.retried_tasks) == 1
    assert runtime.retried_tasks[0]["task_id"] == "task-g-1"
    assert len(runtime.failed_attempts) == 1
    assert len(runtime.settlements) == 1


def test_backfill_rereads_and_retries_once_after_version_conflict_when_primary_is_unchanged() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1")],
        variants={"g-1": [_variant("g-1")]},
        source_bytes=_png(),
    )
    runtime.conflict_on_first_settlement = True

    report = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)

    assert report.failed == 0
    assert report.attached == 1
    assert len(runtime.admissions) == 2
    assert [item["settlement_effect"]["expected_version"] for item in runtime.admissions] == [1, 2]
    assert [item["attempt_id"] for item in runtime.failed_attempts] == ["attempt-g-1"]
    assert len(runtime.settlements) == 1
    assert runtime.settlements[0]["effect"]["expected_version"] == 2


def test_backfill_admission_identity_changes_with_generation_version() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1")],
        variants={"g-1": [_variant("g-1")]},
        source_bytes=_png(),
    )

    first = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)
    assert first.attached == 1
    runtime.generations[0]["metadata"].pop("thumbnail")
    runtime.generations[0]["version"] = 9

    second = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)
    assert second.attached == 1
    assert len(runtime.admissions) == 2
    assert runtime.admissions[0]["idempotency_key"] != runtime.admissions[1]["idempotency_key"]
    assert [item["settlement_effect"]["expected_version"] for item in runtime.admissions] == [1, 9]


def test_backfill_settles_an_interleaved_claim_before_reselecting_own_task() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1")],
        variants={"g-1": [_variant("g-1")]},
        source_bytes=_png(),
    )
    original_claim = runtime.claim_task
    interleaved = {
        "attempt_id": "attempt-old",
        "task_id": "task-old",
        "run_id": "run-old",
        "project_id": "project-1",
        "lease_id": "lease-old",
        "fence": 1,
        "runtime_epoch": 3,
        "input_object_ids": [SOURCE],
        "spec": {"source_media_type": "image/png"},
        "expected_effect": {
            "effect_type": "generation.thumbnail.attach",
            "target_id": "g-old",
            "expected_version": 1,
            "payload": {
                "source_object_id": SOURCE,
                "output_name": "thumbnail",
                "output_ordinal": 0,
                "recipe_version": 1,
            },
        },
    }

    def claim_with_interleaving(**kwargs):
        if not hasattr(runtime, "_interleaving_claimed"):
            runtime._interleaving_claimed = True
            return interleaved
        return original_claim(**kwargs)

    runtime.claim_task = claim_with_interleaving  # type: ignore[method-assign]
    report = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)

    assert report.attached == 1
    assert [item["effect"]["target_id"] for item in runtime.settlements] == ["g-old", "g-1"]
    assert runtime.failed_attempts == []


def test_backfill_reuses_equivalent_prior_claim_and_cancels_duplicate_admission() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-1")],
        variants={"g-1": [_variant("g-1")]},
        source_bytes=_png(),
    )
    original_claim = runtime.claim_task
    equivalent = {
        "attempt_id": "attempt-prior",
        "task_id": "task-prior",
        "run_id": "run-prior",
        "project_id": "project-1",
        "lease_id": "lease-prior",
        "fence": 1,
        "runtime_epoch": 3,
        "input_object_ids": [SOURCE],
        "spec": {
            "operation": "generation.thumbnail.backfill",
            "generation_id": "g-1",
            "source_object_id": SOURCE,
            "source_media_type": "image/png",
        },
        "expected_effect": {
            "effect_type": "generation.thumbnail.attach",
            "target_id": "g-1",
            "expected_version": 1,
            "payload": {
                "source_object_id": SOURCE,
                "output_name": "thumbnail",
                "output_ordinal": 0,
                "recipe_version": 1,
            },
        },
    }

    def claim_equivalent(**kwargs):
        if not hasattr(runtime, "_equivalent_claimed"):
            runtime._equivalent_claimed = True
            return equivalent
        return original_claim(**kwargs)

    runtime.claim_task = claim_equivalent  # type: ignore[method-assign]
    report = run_thumbnail_backfill(runtime, project="project-1", actor_id="owner", limit=1)

    assert report.attached == 1
    assert [item["effect"]["target_id"] for item in runtime.settlements] == ["g-1"]
    assert runtime.cancelled_tasks == ["task-g-1"]


def test_backfill_skips_nonvisual_and_missing_sources() -> None:
    runtime = FakeRuntime(
        generations=[_generation("g-a"), _generation("g-b")],
        variants={
            "g-a": [_variant("g-a", media_type="audio/mpeg")],
            "g-b": [{"variant_id": "v-b", "variant_type": "original", "object_id": None, "metadata": {}}],
        },
        source_bytes=_png(),
    )
    report = run_thumbnail_backfill(
        runtime,
        project="project-1",
        actor_id="owner",
        limit=2,
    )
    assert report.unsupported == 1
    assert report.unavailable == 1
    assert report.attached == 0
