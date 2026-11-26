from __future__ import annotations

import pytest

from dataset_forge.services.crawler import ExtractedPage
from dataset_forge.services.dataset_generation import DatasetGenerationService
from dataset_forge.services.knowledge_context import KnowledgeContextService
from dataset_forge.services.research import SourceCandidate
from dataset_forge.storage.database import Database
from dataset_forge.storage.dataset_record_repository import DatasetRecordRepository
from dataset_forge.storage.knowledge_repository import KnowledgeRepository
from dataset_forge.storage.repositories import ProjectRepository
from dataset_forge.storage.research_repository import ResearchRepository
from dataset_forge.storage.source_content_repository import SourceContentRepository


class StubProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


@pytest.fixture
def generation_setup(tmp_path):
    database = Database(tmp_path / "generation.sqlite3")
    database.initialise()
    project = ProjectRepository(database).create("Generation project")
    research = ResearchRepository(database)
    research.add_sources(
        project["id"],
        [SourceCandidate(url="https://example.org/python", domain="example.org")],
    )
    source_id = research.list_sources(project["id"])[0]["id"]
    SourceContentRepository(database).save(
        source_id,
        ExtractedPage(
            requested_url="https://example.org/python",
            final_url="https://example.org/python",
            title="Python guide",
            text="A function is a reusable block of code.",
            links=(),
            content_hash="a" * 64,
            http_status=200,
        ),
    )
    knowledge = KnowledgeRepository(database)
    knowledge_id = knowledge.add(
        project["id"],
        "definition",
        "A function is a reusable block of code.",
        [source_id],
        evidence={source_id: "reusable block of code"},
        confidence=0.95,
    )
    knowledge.update_review(knowledge_id, "accepted")
    records = DatasetRecordRepository(database)
    context = KnowledgeContextService(knowledge)
    return project, knowledge_id, source_id, knowledge, records, context


def test_generation_persists_valid_qa_with_source_provenance(generation_setup):
    project, knowledge_id, source_id, knowledge, records, context = generation_setup
    provider = StubProvider(
        {
            "records": [
                {
                    "data": {
                        "question": "What is a function?",
                        "answer": "A reusable block of code.",
                    },
                    "knowledge_ids": [knowledge_id],
                }
            ]
        }
    )
    service = DatasetGenerationService(provider, "test-model", context, records)

    generated = service.generate_batch(
        project["id"], dataset_type="question_answer", count=1, difficulty="beginner"
    )

    assert len(generated) == 1
    assert generated[0]["review_status"] == "pending_review"
    assert generated[0]["payload"] == {
        "question": "What is a function?",
        "answer": "A reusable block of code.",
    }
    provenance = generated[0]["provenance"]
    assert provenance[0]["knowledge_id"] == knowledge_id
    assert provenance[0]["sources"][0]["source_id"] == source_id
    assert provenance[0]["sources"][0]["evidence"] == "reusable block of code"
    assert provider.calls[0]["model"] == "test-model"


def test_generation_rejects_unaccepted_knowledge_before_provider_call(generation_setup):
    project, knowledge_id, _, knowledge, records, context = generation_setup
    knowledge.update_review(knowledge_id, "pending")
    provider = StubProvider({"records": []})
    service = DatasetGenerationService(provider, "test-model", context, records)

    with pytest.raises(ValueError, match="must be accepted"):
        service.generate_batch(
            project["id"], dataset_type="question_answer", count=1,
            knowledge_ids=[knowledge_id],
        )
    assert provider.calls == []


def test_generation_discards_unknown_provenance_and_invalid_shapes(generation_setup):
    project, knowledge_id, _, _, records, context = generation_setup
    provider = StubProvider(
        {
            "records": [
                {
                    "data": {"question": "Unsupported?", "answer": "Unknown"},
                    "knowledge_ids": ["not-a-real-knowledge-id"],
                },
                {
                    "data": {"question": "", "answer": "No question"},
                    "knowledge_ids": [knowledge_id],
                },
            ]
        }
    )
    service = DatasetGenerationService(provider, "test-model", context, records)

    with pytest.raises(ValueError, match="no valid"):
        service.generate_batch(
            project["id"], dataset_type="question_answer", count=2
        )
    assert records.list_for_project(project["id"]) == []


def test_generation_enforces_batch_and_dataset_type_limits(generation_setup):
    project, _, _, _, records, context = generation_setup
    service = DatasetGenerationService(
        StubProvider({"records": []}), "test-model", context, records
    )

    with pytest.raises(ValueError, match="Batch size"):
        service.generate_batch(project["id"], dataset_type="question_answer", count=21)
    with pytest.raises(ValueError, match="Unsupported dataset type"):
        service.generate_batch(project["id"], dataset_type="csv", count=1)
