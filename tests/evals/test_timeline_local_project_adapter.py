import json

import pytest

from evals.timeline.local_project_adapter import LocalProjectAdapterError
from evals.timeline.runtime_adapter import prepare_local_disposable_project as prepare_local_project


def _seed(tmp_path):
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "project.json").write_text(
        json.dumps({"project_id": "canonical-project", "slug": "astrid-intro", "name": "Seed"}),
        encoding="utf-8",
    )
    (seed / "astrid-intro.assets.json").write_text(
        json.dumps({"file": "projects/astrid-intro/build/preview.mp4", "opaque": "canonical-project"}),
        encoding="utf-8",
    )
    (seed / "list.json").write_text(json.dumps(["projects/astrid-intro/build/preview.mp4", "unchanged"]), encoding="utf-8")
    (seed / "build").mkdir()
    (seed / "build" / "preview.mp4").write_bytes(b"seed-media")
    return seed


def test_prepare_copies_case_and_rewrites_only_local_identity_and_paths(tmp_path):
    seed = _seed(tmp_path)
    canonical_before = (seed / "project.json").read_bytes()

    prepared = prepare_local_project(
        seed,
        tmp_path / "cases" / "A01",
        case_id="A01",
        runtime_project_id="runtime-project-A01",
    )

    assert prepared.project_id == "runtime-project-A01"
    assert prepared.project_slug == "astrid-intro-a01"
    assert json.loads(prepared.project_json.read_text()) == {
        "name": "Seed",
        "project_id": "runtime-project-A01",
        "slug": "astrid-intro-a01",
    }
    assets = json.loads((prepared.case_dir / "astrid-intro.assets.json").read_text())
    assert assets["file"] == "projects/astrid-intro-a01/build/preview.mp4"
    assert assets["opaque"] == "canonical-project"
    assert json.loads((prepared.case_dir / "list.json").read_text())[0] == "projects/astrid-intro-a01/build/preview.mp4"
    assert (seed / "project.json").read_bytes() == canonical_before
    assert prepared.receipt["mutable_path_checks"]["canonical_seed_unchanged"] is True


def test_prepare_can_bind_an_existing_runtime_create_project(tmp_path):
    seed = _seed(tmp_path)
    calls = []

    class Runtime:
        def create_project(self, name, *, slug, metadata, idempotency_key):
            calls.append((name, slug, metadata, idempotency_key))
            return {"project_id": "runtime-assigned-A01"}

    prepared = prepare_local_project(seed, tmp_path / "A01", case_id="A01", runtime=Runtime())

    assert prepared.project_id == "runtime-assigned-A01"
    assert calls[0][1] == "astrid-intro-a01"
    assert calls[0][2]["purpose"] == "timeline-eval-local-disposable"


def test_prepare_rejects_seed_identity_and_nonempty_case(tmp_path):
    seed = _seed(tmp_path)
    with pytest.raises(LocalProjectAdapterError, match="must differ"):
        prepare_local_project(seed, tmp_path / "same", case_id="A01", runtime_project_id="canonical-project")

    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "unrelated.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(LocalProjectAdapterError, match="already exists"):
        prepare_local_project(seed, occupied, case_id="A01", runtime_project_id="runtime-project-A01")
