from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from astrid.core.timeline.shot_composition import (
    AssetRecord,
    AudioRecord,
    CompositionOccurrenceRecord,
    DependencyRecord,
    GenerationInputRecord,
    InternalTimelineRevisionRecord,
    MissingDependencyError,
    PrimaryTimelineHeadRecord,
    ProjectRecord,
    ShotCompositionSource,
    ShotCompositionValidationError,
    ShotRevisionRecord,
    StaleWriteError,
    TimingRecord,
    assert_expected_head,
    parse_shot_composition,
    prepare_shot_composition,
    publish_shot_composition,
    stable_occurrence_deep_link,
    stable_output_identity,
)

FIXTURE = Path(__file__).parents[1] / "fixtures" / "timeline" / "shot_composition.json"


def load_fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_contract_preserves_revision_occurrence_and_input_identity() -> None:
    contract = parse_shot_composition(load_fixture())
    occurrences = contract["occurrences"]
    revisions = {(row["shot_id"], row["revision_id"]) for row in contract["shot_revisions"]}

    assert len(occurrences) == 5
    assert (occurrences[0]["shot_id"], occurrences[0]["revision_id"]) == ("shot-alpha", "rev-a")
    assert (occurrences[1]["shot_id"], occurrences[1]["revision_id"]) == ("shot-alpha", "rev-a")
    assert occurrences[0]["occurrence_id"] != occurrences[1]["occurrence_id"]
    assert ("shot-alpha", "rev-b") in revisions
    assert ("shot-beta", "rev-a") in revisions
    assert ("shot-alpha-copy", "rev-a") in revisions
    copy_occurrence = next(row for row in occurrences if row["occurrence_id"] == "occ-5")
    assert copy_occurrence["shot_id"] == "shot-alpha-copy"
    assert copy_occurrence["stable_deep_link"] != occurrences[0]["stable_deep_link"]
    assert copy_occurrence["output_identity"] != occurrences[0]["output_identity"]
    assert occurrences[0]["output_identity"] != occurrences[1]["output_identity"]
    assert occurrences[0]["stable_deep_link"] == stable_occurrence_deep_link(
        "project-001", "document-primary", "shot-alpha", "rev-a", "occ-1"
    )
    assert occurrences[0]["output_identity"] == stable_output_identity(
        "project-001", "document-primary", "occ-1"
    )

    alpha = next(row for row in contract["shot_revisions"] if row["revision_id"] == "rev-a" and row["shot_id"] == "shot-alpha")
    assert alpha["timing"]["duration_ms"] == 2000
    assert alpha["audio"]["scope"]["project_id"] == "project-001"
    assert alpha["provenance"]["source"] == "travel-between-images"
    assert [row["ordinal"] for row in alpha["generation_inputs"]] == [0, 1]
    assert alpha["dependencies"] == [{"shot_id": "shot-beta", "revision_id": "rev-a", "required": True}]


def test_contract_carries_missing_dependency_and_rejects_stale_head() -> None:
    contract = parse_shot_composition(load_fixture())
    assert contract["cases"]["missing_dependency"]["expected"] == "missing_dependency"
    stale = contract["cases"]["stale_write_rejection"]
    assert stale["expected_status"] == 409
    with pytest.raises(StaleWriteError) as error:
        assert_expected_head(stale["expected_head_revision_id"], stale["submitted_head_revision_id"])
    assert error.value.status == 409


def test_contract_rejects_legacy_group_and_shot_clip_shapes() -> None:
    legacy_group = copy.deepcopy(load_fixture())
    legacy_group["pinnedShotGroups"] = []
    with pytest.raises(ShotCompositionValidationError, match="migration-only"):
        parse_shot_composition(legacy_group)

    legacy_clip = copy.deepcopy(load_fixture())
    legacy_clip["shot_revisions"][0]["internal_timeline_revision"]["timeline"]["clips"][0]["clipType"] = "shot"
    with pytest.raises(ShotCompositionValidationError, match="migration-only"):
        parse_shot_composition(legacy_clip)


def test_prepare_normalizes_typed_source_records_and_stable_identities() -> None:
    fixture = load_fixture()
    occurrences = copy.deepcopy(fixture["occurrences"])
    for occurrence in occurrences:
        occurrence.pop("stable_deep_link")
        occurrence.pop("output_identity")

    prepared = prepare_shot_composition(
        ShotCompositionSource(
            project=fixture["project"],
            primary_timeline_head=fixture["primary_timeline"]["head"],
            shot_revisions=fixture["shot_revisions"],
            occurrences=occurrences,
            cases=fixture["cases"],
        )
    )

    assert prepared == fixture
    assert prepared["occurrences"][0]["stable_deep_link"] == fixture["occurrences"][0]["stable_deep_link"]
    assert prepared["occurrences"][0]["output_identity"] == fixture["occurrences"][0]["output_identity"]
    assert prepared["occurrences"][0]["shot_id"] == prepared["occurrences"][1]["shot_id"]
    assert prepared["occurrences"][0]["revision_id"] == prepared["occurrences"][1]["revision_id"]
    assert prepared["occurrences"][0]["occurrence_id"] != prepared["occurrences"][1]["occurrence_id"]
    assert prepared["occurrences"][4]["shot_id"] == "shot-alpha-copy"
    assert prepared["occurrences"][4]["shot_id"] != prepared["occurrences"][0]["shot_id"]


def test_prepare_accepts_fully_typed_nested_records() -> None:
    fixture = load_fixture()
    typed_revisions = []
    for revision in fixture["shot_revisions"]:
        typed_revisions.append(
            ShotRevisionRecord(
                shot_id=revision["shot_id"],
                revision_id=revision["revision_id"],
                content_digest=revision["content_digest"],
                internal_timeline_revision=InternalTimelineRevisionRecord(
                    **revision["internal_timeline_revision"]
                ),
                dependencies=[DependencyRecord(**row) for row in revision["dependencies"]],
                assets=[AssetRecord(**row) for row in revision["assets"]],
                generation_inputs=[
                    GenerationInputRecord(**row) for row in revision["generation_inputs"]
                ],
                timing=TimingRecord(**revision["timing"]),
                audio=AudioRecord(**revision["audio"]),
                provenance=revision["provenance"],
            )
        )
    typed_occurrences = [
        CompositionOccurrenceRecord(
            **{
                key: row[key]
                for key in (
                    "occurrence_id",
                    "parent_document_id",
                    "shot_id",
                    "revision_id",
                    "ordinal",
                    "at_ms",
                    "duration_ms",
                )
            }
        )
        for row in fixture["occurrences"]
    ]

    prepared = prepare_shot_composition(
        ShotCompositionSource(
            project=ProjectRecord(**fixture["project"]),
            primary_timeline_head=PrimaryTimelineHeadRecord(
                **fixture["primary_timeline"]["head"]
            ),
            shot_revisions=typed_revisions,
            occurrences=typed_occurrences,
            cases=fixture["cases"],
        )
    )

    assert prepared == fixture


def test_prepare_reports_typed_missing_dependency() -> None:
    invalid = load_fixture()
    invalid["shot_revisions"][0]["dependencies"] = [
        {"shot_id": "shot-missing", "revision_id": "rev-missing", "required": True}
    ]

    with pytest.raises(MissingDependencyError) as error:
        prepare_shot_composition(invalid)

    assert error.value.code == "missing_dependency"
    assert error.value.status == 422
    assert (error.value.shot_id, error.value.revision_id) == ("shot-missing", "rev-missing")


class _Writer:
    def __init__(self, *, stale: bool = False, missing: tuple[str, str] | None = None) -> None:
        self.stale = stale
        self.missing = missing
        self.resolved: list[tuple[str, str, str, str]] = []
        self.published: dict | None = None

    def resolve_immutable_revision(self, **kwargs):
        self.resolved.append(
            (kwargs["project_id"], kwargs["document_id"], kwargs["shot_id"], kwargs["revision_id"])
        )
        if (kwargs["shot_id"], kwargs["revision_id"]) == self.missing:
            return None
        return {"shot_id": kwargs["shot_id"], "revision_id": kwargs["revision_id"]}

    def publish_primary_timeline_revision(self, **kwargs):
        if self.stale:
            raise StaleWriteError("Runtime head changed")
        self.published = kwargs
        return {"revision_id": "timeline-rev-3"}


def test_publish_resolves_each_immutable_revision_and_writes_complete_graph() -> None:
    fixture = load_fixture()
    writer = _Writer()

    result = publish_shot_composition(fixture, writer)

    assert result == {"revision_id": "timeline-rev-3"}
    assert [(shot_id, revision_id) for _, _, shot_id, revision_id in writer.resolved] == [
        ("shot-beta", "rev-a"),
        ("shot-alpha", "rev-a"),
        ("shot-alpha", "rev-b"),
        ("shot-alpha-copy", "rev-a"),
    ]
    assert writer.published is not None
    assert writer.published["expected_head_revision_id"] == "timeline-rev-2"
    assert writer.published["project_id"] == "project-001"
    assert writer.published["document_id"] == "document-primary"
    assert writer.published["graph"] == fixture


def test_publish_maps_missing_runtime_revision_to_typed_error() -> None:
    writer = _Writer(missing=("shot-beta", "rev-a"))

    with pytest.raises(MissingDependencyError, match="shot-beta"):
        publish_shot_composition(load_fixture(), writer)

    assert writer.published is None


def test_publish_maps_runtime_stale_cas_to_409_error() -> None:
    with pytest.raises(StaleWriteError) as error:
        publish_shot_composition(load_fixture(), _Writer(stale=True))

    assert error.value.status == 409
