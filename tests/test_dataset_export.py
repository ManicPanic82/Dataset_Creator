from __future__ import annotations

import json

import pytest

from dataset_forge.services.crawler import ExtractedPage
from dataset_forge.services.dataset_export import DatasetExportService
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
