from __future__ import annotations

import json

import pytest

from dataset_forge.services.crawler import ExtractedPage
from dataset_forge.services.dataset_export import SPLIT_PROFILES, DatasetExportService
from dataset_forge.services.research import SourceCandidate
from dataset_forge.storage.database import Database
from dataset_forge.storage.dataset_record_repository import DatasetRecordRepository
from dataset_forge.storage.knowledge_repository import KnowledgeRepository
from dataset_forge.storage.repositories import ProjectRepository
from dataset_forge.storage.research_repository import ResearchRepository
from dataset_forge.storage.source_content_repository import SourceContentRepository


@pytest.fixture
def export_setup(tmp_path):
    database = Database(tmp_path / "export.sqlite3")
    database.initialise()
    project = ProjectRepository(database).create("Export project")
    research = ResearchRepository(database)
    research.add_sources(
        project["id"],
        [SourceCandidate(url="https://example.org/guide", domain="example.org")],
    )
    source_id = research.list_sources(project["id"])[0]["id"]
    SourceContentRepository(database).save(
        source_id,
        ExtractedPage(
            requested_url="https://example.org/guide",
            final_url="https://example.org/guide",
            title="Example guide",
            text="A function is reusable code.",
            links=(),
            content_hash="b" * 64,
            http_status=200,
        ),
    )
    knowledge = KnowledgeRepository(database)
    knowledge_id = knowledge.add(
        project["id"],
        "definition",
        "A function is reusable code.",
        [source_id],
        evidence={source_id: "reusable code"},
        confidence=0.9,
    )
    knowledge.update_review(knowledge_id, "accepted")
    records = DatasetRecordRepository(database)
    return project, knowledge_id, records


def _add_record(records, project_id, knowledge_id, payload, status):
    record_id = records.add(
        project_id, "question_answer", payload, [knowledge_id]
    )
    records.update_review(record_id, status)
    return record_id


def test_export_writes_accepted_jsonl_and_separate_provenance(export_setup, tmp_path):
    project, knowledge_id, records = export_setup
    accepted_id = _add_record(
        records,
        project["id"],
        knowledge_id,
        {"question": "What is a function?", "answer": "Reusable code."},
        "accepted",
    )
    _add_record(
        records,
        project["id"],
        knowledge_id,
        {"question": "Pending?", "answer": "Not exported."},
        "pending_review",
    )
    _add_record(
        records,
        project["id"],
        knowledge_id,
        {"question": "Rejected?", "answer": "Not exported."},
        "rejected",
    )

    destination = tmp_path / "training.jsonl"
    result = DatasetExportService(records).export_project(
        project["id"], "question_answer", destination
    )

    rows = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
    sidecar = destination.with_name("training.provenance.jsonl")
    provenance = [
        json.loads(line) for line in sidecar.read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [{"question": "What is a function?", "answer": "Reusable code."}]
    assert result["exported"] == 1
    assert result["skipped"] == 0
    assert result["available"] == 1
    assert provenance[0]["record_id"] == accepted_id
    assert provenance[0]["provenance"][0]["knowledge_id"] == knowledge_id


def test_export_can_omit_provenance_and_creates_empty_jsonl(export_setup, tmp_path):
    project, _, records = export_setup
    destination = tmp_path / "empty.jsonl"

    result = DatasetExportService(records).export_project(
        project["id"],
        "instruction",
        destination,
        include_provenance=False,
    )

    assert destination.read_text(encoding="utf-8") == ""
    assert result["exported"] == 0
    assert result["provenance_path"] is None
    assert not destination.with_name("empty.provenance.jsonl").exists()


@pytest.mark.parametrize("path", ["dataset.csv", "dataset"])
def test_export_requires_jsonl_extension(export_setup, tmp_path, path):
    project, _, records = export_setup
    with pytest.raises(ValueError, match=r"\.jsonl"):
        DatasetExportService(records).export_project(
            project["id"], "question_answer", tmp_path / path
        )


def test_export_rejects_unknown_dataset_type(export_setup, tmp_path):
    project, _, records = export_setup
    with pytest.raises(ValueError, match="supported"):
        DatasetExportService(records).export_project(
            project["id"], "csv", tmp_path / "dataset.jsonl"
        )


def test_export_skips_invalid_accepted_payload_and_reports_count(export_setup, tmp_path):
    project, knowledge_id, records = export_setup
    _add_record(
        records,
        project["id"],
        knowledge_id,
        {"question": "Missing answer?", "answer": ""},
        "accepted",
    )
    destination = tmp_path / "screened.jsonl"

    result = DatasetExportService(records).export_project(
        project["id"], "question_answer", destination, include_provenance=False
    )

    assert result["available"] == 1
    assert result["exported"] == 0
    assert result["skipped"] == 1
    assert destination.read_text(encoding="utf-8") == ""


def test_export_splits_are_reproducible_and_keep_provenance(export_setup, tmp_path):
    project, knowledge_id, records = export_setup
    for index in range(10):
        _add_record(
            records,
            project["id"],
            knowledge_id,
            {"question": f"Question {index}", "answer": f"Answer {index}"},
            "accepted",
        )

    service = DatasetExportService(records)
    first = service.export_splits(project["id"], "question_answer", tmp_path / "one")
    service.export_splits(project["id"], "question_answer", tmp_path / "two")

    counts = {name: first[name]["count"] for name in ("train", "validation", "test")}
    # All ten records share one knowledge item, so they must remain in one split.
    assert sorted(counts.values()) == [0, 0, 10]
    assert first["groups"] == 1
    for name in ("train", "validation", "test"):
        first_path = tmp_path / "one" / f"{name}.jsonl"
        rows = [json.loads(line) for line in first_path.read_text(encoding="utf-8").splitlines()]
        second_path = tmp_path / "two" / f"{name}.jsonl"
        rows2 = [json.loads(line) for line in second_path.read_text(encoding="utf-8").splitlines()]
        assert rows == rows2
        sidecar_path = tmp_path / "one" / f"{name}.provenance.jsonl"
        sidecar = sidecar_path.read_text(encoding="utf-8").splitlines()
        assert len(sidecar) == first[name]["count"]
        assert all(json.loads(row)["provenance"] for row in sidecar)


def test_export_splits_reject_invalid_ratios(export_setup, tmp_path):
    project, _, records = export_setup
    with pytest.raises(ValueError, match="sum"):
        DatasetExportService(records).export_splits(
            project["id"], "question_answer", tmp_path, train_ratio=0.8,
            validation_ratio=0.15, test_ratio=0.1
        )
    with pytest.raises(ValueError, match="positive"):
        DatasetExportService(records).export_splits(
            project["id"], "question_answer", tmp_path, train_ratio=1,
            validation_ratio=0, test_ratio=0
        )


def test_export_splits_can_disable_provenance(export_setup, tmp_path):
    project, knowledge_id, records = export_setup
    _add_record(
        records, project["id"], knowledge_id,
        {"question": "Question", "answer": "Answer"}, "accepted"
    )
    result = DatasetExportService(records).export_splits(
        project["id"], "question_answer", tmp_path, include_provenance=False
    )
    assert all(result[name]["provenance_path"] is None for name in
               ("train", "validation", "test"))
    assert not list(tmp_path.glob("*.provenance.jsonl"))

@pytest.mark.parametrize("invalid_ratio", [float("nan"), float("inf"), float("-inf"), True])
def test_export_splits_reject_non_finite_or_boolean_ratios(
    export_setup, tmp_path, invalid_ratio
):
    project, _, records = export_setup
    with pytest.raises(ValueError, match="positive numbers"):
        DatasetExportService(records).export_splits(
            project["id"],
            "question_answer",
            tmp_path,
            train_ratio=invalid_ratio,
            validation_ratio=0.1,
            test_ratio=0.1,
        )


def test_export_profiles_define_valid_split_targets():
    assert SPLIT_PROFILES == {
        "standard": {"train": 0.8, "validation": 0.1, "test": 0.1},
        "training_heavy": {"train": 0.9, "validation": 0.05, "test": 0.05},
        "balanced": {"train": 0.7, "validation": 0.15, "test": 0.15},
    }
    assert all(
        sum(profile.values()) == pytest.approx(1.0)
        and all(value > 0 for value in profile.values())
        for profile in SPLIT_PROFILES.values()
    )

def test_export_can_remove_exact_duplicate_records_and_keep_first_provenance(
    export_setup, tmp_path
):
    project, knowledge_id, records = export_setup
    first_id = _add_record(
        records, project["id"], knowledge_id,
        {"question": "Same question?", "answer": "Same answer."}, "accepted"
    )
    _add_record(
        records, project["id"], knowledge_id,
        {"answer": "Same answer.", "question": "Same question?"}, "accepted"
    )
    destination = tmp_path / "deduplicated.jsonl"

    result = DatasetExportService(records).export_project(
        project["id"], "question_answer", destination, deduplicate=True
    )

    rows = [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()]
    sidecar = [
        json.loads(line)
        for line in destination.with_name("deduplicated.provenance.jsonl")
        .read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [{"question": "Same question?", "answer": "Same answer."}]
    assert result["available"] == 2
    assert result["exported"] == 1
    assert result["duplicates_removed"] == 1
    assert sidecar[0]["record_id"] == first_id


def test_export_duplicate_filter_is_opt_in(export_setup, tmp_path):
    project, knowledge_id, records = export_setup
    payload = {"question": "Repeated?", "answer": "Repeated answer."}
    _add_record(records, project["id"], knowledge_id, payload, "accepted")
    _add_record(records, project["id"], knowledge_id, payload, "accepted")

    result = DatasetExportService(records).export_project(
        project["id"], "question_answer", tmp_path / "duplicates.jsonl"
    )

    assert result["exported"] == 2
    assert result["duplicates_removed"] == 0


def test_split_export_deduplicates_before_leakage_grouping(export_setup, tmp_path):
    project, knowledge_id, records = export_setup
    payload = {"question": "Same?", "answer": "Same answer."}
    _add_record(records, project["id"], knowledge_id, payload, "accepted")
    _add_record(records, project["id"], knowledge_id, payload, "accepted")
    _add_record(
        records, project["id"], knowledge_id,
        {"question": "Different?", "answer": "Different answer."}, "accepted"
    )

    result = DatasetExportService(records).export_splits(
        project["id"], "question_answer", tmp_path, deduplicate=True
    )
    exported_count = sum(result[name]["count"] for name in ("train", "validation", "test"))
    assert result["available"] == 3
    assert result["duplicates_removed"] == 1
    assert exported_count == 2
    assert result["groups"] == 1



def test_export_writes_manifest_with_settings_counts_and_file_names(
    export_setup, tmp_path
):
    project, knowledge_id, records = export_setup
    _add_record(
        records, project["id"], knowledge_id,
        {"question": "Manifest?", "answer": "Audit trail."}, "accepted"
    )
    destination = tmp_path / "manifested.jsonl"

    result = DatasetExportService(records).export_project(
        project["id"], "question_answer", destination,
        include_provenance=False, deduplicate=True,
    )

    manifest_path = tmp_path / "manifested.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result["manifest_path"] == str(manifest_path)
    assert manifest["manifest_version"] == 1
    assert manifest["project_id"] == project["id"]
    assert manifest["dataset_type"] == "question_answer"
    assert manifest["export_mode"] == "single_file"
    assert manifest["available_accepted_records"] == 1
    assert manifest["exported_records"] == 1
    assert manifest["skipped_invalid_records"] == 0
    assert manifest["duplicates_removed"] == 0
    assert manifest["deduplicate_exact"] is True
    assert manifest["include_provenance"] is False
    assert manifest["dataset_file"] == "manifested.jsonl"
    assert manifest["provenance_file"] is None
    assert manifest["created_at_utc"].endswith("+00:00")


def test_split_export_writes_manifest_with_ratios_seed_and_counts(
    export_setup, tmp_path
):
    project, knowledge_id, records = export_setup
    for index in range(3):
        _add_record(
            records, project["id"], knowledge_id,
            {"question": f"Manifest question {index}", "answer": f"Answer {index}"},
            "accepted",
        )

    result = DatasetExportService(records).export_splits(
        project["id"], "question_answer", tmp_path,
        train_ratio=0.7, validation_ratio=0.2, test_ratio=0.1,
        seed=123, split_profile="balanced", include_provenance=True,
        deduplicate=True,
    )

    manifest_path = tmp_path / "export.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert result["manifest_path"] == str(manifest_path)
    assert manifest["export_mode"] == "train_validation_test"
    assert manifest["available_accepted_records"] == 3
    assert manifest["exported_records"] == 3
    assert manifest["seed"] == 123
    assert manifest["split_profile"] == "balanced"
    assert manifest["ratios"] == {
        "train": 0.7, "validation": 0.2, "test": 0.1
    }
    assert manifest["leakage_groups"] == 1
    assert sum(split["count"] for split in manifest["splits"].values()) == 3
    assert all(
        split["provenance_file"] is not None
        for split in manifest["splits"].values()
    )
