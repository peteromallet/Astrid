"""Host-owned, projection-neutral evidence collection for timeline attempts.

The native launcher historically mixed worker-authored result files with the
coordinator's Runtime readback.  This module is the small trust boundary used
by the next runner: worker output is retained as evidence, but state is read
from the coordinator's read-only Runtime connection *after* teardown.  The
collector deliberately follows the committed parent closure and its actual
child pins, so edits which create or duplicate shots do not need a seed-ID
special case.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from .independent_readback import ReadbackObservation, read_target_snapshot


class EvidenceCollectionError(RuntimeError):
    """The coordinator cannot produce trustworthy evidence for an attempt."""


class ClosureReader(Protocol):
    def current_head(self, project_id: str, timeline_id: str) -> str: ...

    def read_current_closure(
        self, project_id: str, timeline_id: str, *, head: str | None = None,
    ) -> Mapping[str, Any]: ...


class WorkerLifecycle(Protocol):
    """Host supervisor operations required before private readback."""

    def stop_worker(self, worker_id: str) -> Any: ...

    def confirm_worker_stopped(self, worker_id: str) -> bool: ...

    def confirm_descendants_stopped(self, worker_id: str) -> bool: ...

    def confirm_write_denied(self, worker_id: str) -> bool: ...

    def retire_realm(self, realm_id: str) -> Any: ...


@dataclass(frozen=True)
class TeardownReceipt:
    """Evidence that no worker process can alter state during readback."""

    worker_id: str
    realm_id: str | None
    worker_stopped: bool
    descendants_stopped: bool
    write_denied: bool
    stopped_by_host: bool = True
    retirement_requested: bool = False
    retirement_status: str = "not_requested"
    details: Mapping[str, Any] | None = None

    def require_safe_readback(self) -> None:
        if not self.worker_stopped:
            raise EvidenceCollectionError("worker was not stopped before private readback")
        if not self.descendants_stopped:
            raise EvidenceCollectionError("worker descendants were not stopped before private readback")
        if not self.write_denied:
            raise EvidenceCollectionError("worker write denial was not confirmed before private readback")


@dataclass(frozen=True)
class MediaEvidence:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True)
class EvidenceCollection:
    """Paths and trust status of one coordinator-produced evidence pack."""

    case_id: str
    evidence_root: str
    transcript_path: str
    final_response_path: str
    worker_result_path: str | None
    before_path: str | None
    after_path: str | None
    receipt_path: str | None
    media: tuple[MediaEvidence, ...]
    fingerprints: Mapping[str, Any]
    teardown: TeardownReceipt
    realm_retired: bool
    after_source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name("." + path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _write_json(path: Path, value: Any) -> None:
    _write_bytes(path, json.dumps(value, indent=2, ensure_ascii=False, default=str).encode("utf-8") + b"\n")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _publication_payload(value: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if value is None:
        return None
    data = value.get("data")
    return data if isinstance(data, Mapping) else value


def _publication_head(value: Mapping[str, Any] | None) -> str | None:
    record = _mapping(_publication_payload(value))
    nested = _mapping(record.get("publication"))
    record = nested or record
    for key in ("new_head", "parent_revision_id", "revision_id"):
        candidate = record.get(key)
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _closure_rows(closure: Mapping[str, Any], field: str) -> list[Mapping[str, Any]]:
    rows = closure.get(field)
    return [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _validate_runtime_identity(
    reader: ClosureReader,
    target: Mapping[str, Any],
    closure: Mapping[str, Any],
    *,
    expected_realm_id: str | None,
) -> None:
    project_id = target.get("project_id")
    timeline_id = target.get("timeline_id")
    if not isinstance(project_id, str) or not project_id or not isinstance(timeline_id, str) or not timeline_id:
        raise EvidenceCollectionError("target is missing project_id/timeline_id")
    if closure.get("project_id") not in {None, project_id}:
        raise EvidenceCollectionError("host readback returned the wrong project")
    if closure.get("timeline_id") not in {None, timeline_id}:
        raise EvidenceCollectionError("host readback returned the wrong timeline")
    target_realm = target.get("realm_id")
    observed_realm = getattr(getattr(reader, "proof", None), "realm_id", None)
    observed_realm = observed_realm or getattr(getattr(reader, "isolation", None), "realm_id", None)
    if expected_realm_id and target_realm and target_realm != expected_realm_id:
        raise EvidenceCollectionError("public target is bound to the wrong Runtime realm")
    if expected_realm_id and observed_realm and observed_realm != expected_realm_id:
        raise EvidenceCollectionError("host readback connection is bound to the wrong Runtime realm")
    if target_realm and observed_realm and target_realm != observed_realm:
        raise EvidenceCollectionError("target realm and host readback realm differ")
    expected_head = target.get("head_revision_id")
    actual_head = closure.get("head_revision_id")
    parent = _mapping(closure.get("parent_revision"))
    if actual_head and parent.get("revision_id") not in {None, actual_head}:
        raise EvidenceCollectionError("host readback parent revision does not match its head")
    if expected_head and actual_head == expected_head and parent.get("revision_id") not in {None, expected_head}:
        raise EvidenceCollectionError("host readback target parent identity is inconsistent")


def _validate_dependency_manifest(
    publication: Mapping[str, Any] | None, closure: Mapping[str, Any],
) -> None:
    """Check receipt dependencies against actual closure IDs, allowing new shots."""
    payload = _mapping(_publication_payload(publication))
    record = _mapping(payload.get("publication")) or payload
    manifest = _mapping(record.get("dependency_manifest"))
    if not manifest:
        return
    actual_shots = {
        (row.get("shot_id"), row.get("revision_id"), row.get("internal_timeline_revision_id"))
        for row in _closure_rows(closure, "shot_revisions")
    }
    actual_internals = {row.get("revision_id") for row in _closure_rows(closure, "internal_timeline_revisions")}
    for field, expected, actual in (
        ("shots", manifest.get("shots"), actual_shots),
        ("internal_timelines", manifest.get("internal_timelines"), actual_internals),
    ):
        if expected is None:
            continue
        if not isinstance(expected, list):
            raise EvidenceCollectionError(f"publication dependency_manifest.{field} is malformed")
        for row in expected:
            if not isinstance(row, Mapping):
                raise EvidenceCollectionError(f"publication dependency_manifest.{field} has a malformed row")
            if field == "shots":
                identity = (row.get("shot_id"), row.get("revision_id"), row.get("internal_timeline_revision_id"))
            else:
                identity = row.get("revision_id")
            if identity not in actual:
                raise EvidenceCollectionError(
                    f"publication dependency {field} is absent from the host-fetched committed closure"
                )


def _capture_media(root: Path | None, evidence_root: Path) -> tuple[MediaEvidence, ...]:
    if root is None:
        return ()
    root = root.expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        return ()
    rows: list[MediaEvidence] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        rows.append(MediaEvidence(relative, _sha256_file(path), path.stat().st_size))
    _write_json(evidence_root / "media-manifest.json", {"root": str(root), "media": [asdict(row) for row in rows]})
    return tuple(rows)


def perform_teardown(
    lifecycle: WorkerLifecycle, *, worker_id: str, realm_id: str | None,
) -> TeardownReceipt:
    """Stop the worker and prove descendants/write denial.

    Realm retirement is intentionally separate and happens only after the
    collector has fetched final state.  Retiring here would destroy the very
    Runtime evidence we need to preserve.
    """
    stop_detail = lifecycle.stop_worker(worker_id)
    receipt = TeardownReceipt(
        worker_id=worker_id,
        realm_id=realm_id,
        worker_stopped=bool(lifecycle.confirm_worker_stopped(worker_id)),
        descendants_stopped=bool(lifecycle.confirm_descendants_stopped(worker_id)),
        write_denied=bool(lifecycle.confirm_write_denied(worker_id)),
        details={"stop": stop_detail} if isinstance(stop_detail, Mapping) else {"stop": str(stop_detail)},
    )
    receipt.require_safe_readback()
    return receipt


def _retire_after_readback(
    lifecycle: WorkerLifecycle, receipt: TeardownReceipt,
) -> TeardownReceipt:
    if not receipt.realm_id:
        return receipt
    retirement = lifecycle.retire_realm(receipt.realm_id)
    status = retirement.get("status") if isinstance(retirement, Mapping) else "retired"
    if status not in {"retired", "already_retired", "quarantined"}:
        raise EvidenceCollectionError(f"Runtime realm retirement was not confirmed: {retirement!r}")
    return TeardownReceipt(
        **{**asdict(receipt), "retirement_requested": True,
           "retirement_status": "retired",
           "details": {**dict(receipt.details or {}), "retirement": retirement}},
    )


def collect_case_evidence(
    *,
    case_id: str,
    case_dir: str | Path,
    evidence_root: str | Path,
    brief: Mapping[str, Any] | None,
    fingerprints: Mapping[str, Any],
    transcript: str,
    final_response: str | None,
    worker_result: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None,
    reader: ClosureReader | None,
    before: ReadbackObservation | None,
    publication: Mapping[str, Any] | None,
    teardown: TeardownReceipt,
    expected_realm_id: str | None = None,
    media_root: str | Path | None = None,
    worker_state: Mapping[str, Any] | None = None,
    lifecycle: WorkerLifecycle | None = None,
) -> EvidenceCollection:
    """Capture one case after host teardown; worker state cannot self-certify.

    ``worker_state`` is accepted only to detect accidental use of agent-authored
    ``before``/``after`` snapshots.  Those fields are rejected rather than
    silently copied into coordinator evidence.
    """
    teardown.require_safe_readback()
    if worker_state and any(key in worker_state for key in ("before", "after", "closure", "runtime_state")):
        raise EvidenceCollectionError("worker-authored Runtime state cannot be used as coordinator evidence")
    root = Path(evidence_root).expanduser().absolute()
    root.mkdir(parents=True, exist_ok=True)
    case_path = Path(case_dir).expanduser().absolute()
    if brief is not None:
        _write_json(root / "brief.json", brief)
    _write_json(root / "fingerprints.json", fingerprints)
    transcript_bytes = transcript.encode("utf-8")
    _write_bytes(root / "transcript.txt", transcript_bytes)
    response_text = final_response if final_response is not None else transcript
    _write_bytes(root / "final-response.txt", response_text.encode("utf-8"))

    worker_result_path: str | None = None
    result_path = case_path / "result.json"
    if worker_result is not None:
        _write_json(root / "worker-result.json", worker_result)
        worker_result_path = str(root / "worker-result.json")
    elif result_path.is_file() and not result_path.is_symlink():
        _write_bytes(root / "worker-result.json", result_path.read_bytes())
        worker_result_path = str(root / "worker-result.json")

    before_path: str | None = None
    after_path: str | None = None
    after_source = "unavailable"
    if target is not None:
        if reader is None:
            raise EvidenceCollectionError("Runtime target was supplied without a host read-only reader")
        if before is None:
            raise EvidenceCollectionError("Runtime target was supplied without a host-fetched before snapshot")
        project_id = target.get("project_id")
        timeline_id = target.get("timeline_id")
        if not isinstance(project_id, str) or not isinstance(timeline_id, str):
            raise EvidenceCollectionError("Runtime target is missing project/timeline identity")
        if before is not None:
            _write_json(root / "before.json", {"target": before.target, "host_fetched": True})
            before_path = str(root / "before.json")
        head = _publication_head(publication) or reader.current_head(project_id, timeline_id)
        if not isinstance(head, str) or not head:
            raise EvidenceCollectionError("host Runtime readback has no committed parent head")
        closure = reader.read_current_closure(project_id, timeline_id, head=head)
        _validate_runtime_identity(reader, target, closure, expected_realm_id=expected_realm_id)
        if closure.get("head_revision_id") not in {None, head}:
            raise EvidenceCollectionError("host Runtime returned a different committed parent head")
        _validate_dependency_manifest(publication, closure)
        after_payload: dict[str, Any] = {
            "project_id": project_id,
            "timeline_id": timeline_id,
            "head_revision_id": head,
            "closure": closure,
            "host_fetched": True,
            "worker_authored": False,
        }
        # Resolve the original locator when possible for human review, but do
        # not assume it is the only changed object: closure is the authority.
        try:
            after_payload["target"] = read_target_snapshot(reader, target, head=head)
        except Exception as exc:  # duplicated/removed target can be reviewed from closure
            after_payload["target_locator_resolution"] = {"status": "unresolved", "reason": str(exc)}
        _write_json(root / "after.json", after_payload)
        after_path = str(root / "after.json")
        after_source = "host_read_only_runtime"

    # Realm retirement is deliberately the final side effect, after the host
    # has fetched and serialized the exact committed closure above.
    if target is not None and teardown.realm_id and not teardown.retirement_requested:
        if lifecycle is None:
            raise EvidenceCollectionError("Runtime realm must be retired after final readback")
        teardown = _retire_after_readback(lifecycle, teardown)

    receipt_path: str | None = None
    if publication is not None:
        _write_json(root / "publication-receipt.json", publication)
        receipt_path = str(root / "publication-receipt.json")
    selected_media_root = Path(media_root) if media_root is not None else (
        case_path / "media" if (case_path / "media").is_dir() else None
    )
    media = _capture_media(selected_media_root, root)
    collection = EvidenceCollection(
        case_id=case_id,
        evidence_root=str(root),
        transcript_path=str(root / "transcript.txt"),
        final_response_path=str(root / "final-response.txt"),
        worker_result_path=worker_result_path,
        before_path=before_path,
        after_path=after_path,
        receipt_path=receipt_path,
        media=media,
        fingerprints=dict(fingerprints),
        teardown=teardown,
        realm_retired=teardown.retirement_requested and teardown.retirement_status == "retired",
        after_source=after_source,
    )
    _write_json(root / "evidence-manifest.json", collection.as_dict())
    return collection


__all__ = [
    "ClosureReader", "EvidenceCollection", "EvidenceCollectionError", "MediaEvidence",
    "TeardownReceipt", "WorkerLifecycle", "collect_case_evidence", "perform_teardown",
]
