from __future__ import annotations

import json
from pathlib import Path

import pytest

from evals.timeline.admission_rehearsal import rehearse_admission
from evals.timeline.evidence_collector import (
    EvidenceCollectionError,
    TeardownReceipt,
    collect_case_evidence,
    perform_teardown,
)
from evals.timeline.independent_readback import ReadbackObservation


REPO_ROOT = Path(__file__).resolve().parents[3]
SUITE = REPO_ROOT / "Astrid/evals/timeline/suite.json"
FIXTURES = REPO_ROOT / ".otto/runs/timeline-text-inspection-20260922/evals/fixtures"


class Reader:
    class Proof:
        realm_id = "realm-case"

    proof = Proof()

    def __init__(self, closure):
        self.closure = closure

    def current_head(self, project_id, timeline_id):
        return self.closure["head_revision_id"]

    def read_current_closure(self, project_id, timeline_id, *, head=None):
        assert head == self.closure["head_revision_id"]
        return self.closure


class Lifecycle:
    def __init__(self):
        self.calls = []

    def stop_worker(self, worker_id):
        self.calls.append(("stop", worker_id))
        return {"status": "stopped"}

    def confirm_worker_stopped(self, worker_id):
        self.calls.append(("worker", worker_id))
        return True

    def confirm_descendants_stopped(self, worker_id):
        self.calls.append(("descendants", worker_id))
        return True

    def confirm_write_denied(self, worker_id):
        self.calls.append(("write-denied", worker_id))
        return True

    def retire_realm(self, realm_id):
        self.calls.append(("retire", realm_id))
        return {"status": "retired"}


def _closure():
    return {
        "project_id": "project-case",
        "timeline_id": "timeline-case",
        "head_revision_id": "head-new",
        "parent_revision": {"revision_id": "head-new", "payload": {"occurrences": []}},
        # The second row represents a newly duplicated shot.  The collector
        # must follow these returned pins rather than a seeded ID list.
        "shot_revisions": [
            {"shot_id": "shot-new", "revision_id": "shot-rev-new", "internal_timeline_revision_id": "internal-new", "payload": {}},
            {"shot_id": "shot-duplicate", "revision_id": "shot-rev-duplicate", "internal_timeline_revision_id": "internal-duplicate", "payload": {}},
        ],
        "internal_timeline_revisions": [
            {"revision_id": "internal-new", "payload": {}},
            {"revision_id": "internal-duplicate", "payload": {}},
        ],
    }


def test_collector_reads_host_closure_after_teardown_and_captures_worker_output(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "result.json").write_text('{"status":"claimed"}\n', encoding="utf-8")
    (case_dir / "media").mkdir()
    (case_dir / "media" / "produced.bin").write_bytes(b"produced-media")
    evidence = tmp_path / "evidence"
    lifecycle = Lifecycle()
    teardown = perform_teardown(lifecycle, worker_id="worker-1", realm_id="realm-case")
    closure = _closure()
    before = ReadbackObservation(
        head_revision_id="head-before",
        target={"head_revision_id": "head-before"},
        parent_protected_fingerprint="sha256:before",
        target_protected={},
        sibling_occurrence_fingerprints={},
        sibling_timeline_fingerprints=None,
        source_fingerprint=None,
    )
    publication = {
        "data": {
            "new_head": "head-new",
            "dependency_manifest": {
                "shots": [
                    {"shot_id": "shot-new", "revision_id": "shot-rev-new", "internal_timeline_revision_id": "internal-new"},
                    {"shot_id": "shot-duplicate", "revision_id": "shot-rev-duplicate", "internal_timeline_revision_id": "internal-duplicate"},
                ],
                "internal_timelines": [{"revision_id": "internal-new"}, {"revision_id": "internal-duplicate"}],
            },
        }
    }
    collected = collect_case_evidence(
        case_id="A04",
        case_dir=case_dir,
        evidence_root=evidence,
        brief={"id": "A04", "prompt": "duplicate"},
        fingerprints={"suite": "sha256:suite", "brief": "sha256:brief"},
        transcript="tool call\nfinal response\n",
        final_response="final response\n",
        worker_result={"status": "claimed"},
        target={"project_id": "project-case", "timeline_id": "timeline-case", "realm_id": "realm-case"},
        reader=Reader(closure),
        before=before,
        publication=publication,
        teardown=teardown,
        expected_realm_id="realm-case",
        lifecycle=lifecycle,
    )
    assert collected.after_source == "host_read_only_runtime"
    after = json.loads((evidence / "after.json").read_text(encoding="utf-8"))
    assert after["closure"]["shot_revisions"][1]["shot_id"] == "shot-duplicate"
    assert after["worker_authored"] is False
    assert (evidence / "transcript.txt").read_text() == "tool call\nfinal response\n"
    assert collected.media[0].path == "produced.bin"
    assert [item[0] for item in lifecycle.calls] == ["stop", "worker", "descendants", "write-denied", "retire"]


def test_collector_rejects_worker_authored_runtime_state(tmp_path):
    with pytest.raises(EvidenceCollectionError, match="worker-authored Runtime state"):
        collect_case_evidence(
            case_id="A01",
            case_dir=tmp_path,
            evidence_root=tmp_path / "evidence",
            brief=None,
            fingerprints={},
            transcript="",
            final_response=None,
            worker_result=None,
            target=None,
            reader=None,
            before=ReadbackObservation("head-before", {}, "sha256:before", {}, {}, None, None),
            publication=None,
            teardown=TeardownReceipt("worker", None, True, True, True),
            worker_state={"after": {"fake": True}},
        )


def test_collector_rejects_wrong_realm_before_readback(tmp_path):
    with pytest.raises(EvidenceCollectionError, match="wrong Runtime realm"):
        collect_case_evidence(
            case_id="A01",
            case_dir=tmp_path,
            evidence_root=tmp_path / "evidence",
            brief=None,
            fingerprints={},
            transcript="",
            final_response=None,
            worker_result=None,
            target={"project_id": "project-case", "timeline_id": "timeline-case", "realm_id": "wrong"},
            reader=Reader(_closure()),
            before=ReadbackObservation("head-before", {}, "sha256:before", {}, {}, None, None),
            publication={"new_head": "head-new"},
            teardown=TeardownReceipt("worker", "realm-case", True, True, True),
            expected_realm_id="realm-case",
        )


def test_admission_rehearsal_has_twenty_explicit_no_model_rows():
    result = rehearse_admission(SUITE, FIXTURES)
    assert result["case_count"] == 20
    assert result["model_launched"] is False
    assert {row["case_id"] for row in result["rows"]} == {
        *(f"L{i:02d}" for i in range(1, 11)),
        *(f"A{i:02d}" for i in range(1, 11)),
    }
    assert all(row["launched"] is False for row in result["rows"])
    assert all(row["classification"] == "blocked-essential-input" for row in result["rows"] if row["kind"] == "action")
    l10 = next(row for row in result["rows"] if row["case_id"] == "L10")
    assert l10["classification"] in {"executable", "diagnostic-only"}
    assert l10["tool_paths"].get("interactive_playback") in {"available", "unavailable"}
    assert all(row["classification"] in {"executable", "blocked-essential-input", "diagnostic-only"} for row in result["rows"])
