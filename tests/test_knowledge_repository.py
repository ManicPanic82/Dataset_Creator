from __future__ import annotations

import pytest

from dataset_forge.services.crawler import ExtractedPage
from dataset_forge.services.knowledge_context import KnowledgeContextService
from dataset_forge.services.research import SourceCandidate
from dataset_forge.storage.database import Database
from dataset_forge.storage.knowledge_repository import KnowledgeRepository
from dataset_forge.storage.repositories import ProjectRepository
from dataset_forge.storage.research_repository import ResearchRepository
from dataset_forge.storage.source_content_repository import SourceContentRepository


@pytest.fixture
def prepared_sources(tmp_path):
    database = Database(tmp_path / "knowledge.sqlite3")
    database.initialise()
    project = ProjectRepository(database).create("Knowledge research")
    other_project = ProjectRepository(database).create("Other project")
    research = ResearchRepository(database)
    content_repository = SourceContentRepository(database)
    candidates = [
        SourceCandidate(url="https://example.org/a", domain="example.org"),
        SourceCandidate(url="https://example.org/b", domain="example.org"),
    ]
    research.add_sources(project["id"], candidates)
    research.add_sources(
        other_project["id"],
        [SourceCandidate(url="https://other.org/", domain="other.org")],
    )
    source_ids = [item["id"] for item in research.list_sources(project["id"])]
    other_source_id = research.list_sources(other_project["id"])[0]["id"]
    for source_id, url in zip(source_ids, [item.url for item in candidates], strict=True):
        content_repository.save(
            source_id,
            ExtractedPage(
                requested_url=url,
                final_url=url,
                title="Source",
                text="Extracted source text",
                links=(),
                content_hash="c" * 64,
                http_status=200,
            ),
        )
    content_repository.save(
        other_source_id,
        ExtractedPage(
            requested_url="https://other.org/",
            final_url="https://other.org/",
            title="Other source",
            text="Other extracted text",
            links=(),
            content_hash="d" * 64,
            http_status=200,
        ),
    )
    return database, project, other_project, source_ids, other_source_id


def test_knowledge_item_requires_source_and_persists_provenance(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    item_id = repository.add(
        project["id"],
        "definition",
        "A function is a reusable block of code.",
        source_ids[:1],
        evidence={source_ids[0]: "Functions can be defined using def."},
        confidence=0.9,
    )

    item = repository.get(item_id)
    assert item is not None
    assert item["kind"] == "definition"
    assert item["review_status"] == "pending"
    assert item["confidence"] == pytest.approx(0.9)
    assert item["sources"][0]["id"] == source_ids[0]
    assert item["sources"][0]["evidence"] == "Functions can be defined using def."


def test_knowledge_item_supports_multiple_sources(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    item_id = KnowledgeRepository(database).add(
        project["id"], "concept", "Reusable code", source_ids
    )
    assert len(KnowledgeRepository(database).get(item_id)["sources"]) == 2


def test_knowledge_review_filters_and_updates(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    item_id = repository.add(project["id"], "fact", "Python is interpreted.", source_ids[:1])
    repository.update_review(item_id, "accepted")

    assert repository.list_for_project(project["id"], review_status="accepted")[0]["id"] == item_id
    assert repository.list_for_project(project["id"], review_status="pending") == []
    with pytest.raises(ValueError, match="Invalid review status"):
        repository.list_for_project(project["id"], review_status="unknown")


def test_knowledge_item_rejects_invalid_type_empty_content_and_missing_sources(
    prepared_sources,
):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    with pytest.raises(ValueError, match="Unsupported knowledge type"):
        repository.add(project["id"], "unsupported", "Text", source_ids[:1])
    with pytest.raises(ValueError, match="cannot be empty"):
        repository.add(project["id"], "fact", "  ", source_ids[:1])
    with pytest.raises(ValueError, match="unique source IDs"):
        repository.add(project["id"], "fact", "Text", [])


def test_knowledge_item_rejects_cross_project_source(prepared_sources):
    database, project, _, _, other_source_id = prepared_sources
    with pytest.raises(ValueError, match="selected project"):
        KnowledgeRepository(database).add(
            project["id"], "fact", "Cross-project evidence", [other_source_id]
        )


def test_knowledge_item_requires_extracted_source(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    research = ResearchRepository(database)
    research.add_sources(
        project["id"],
        [SourceCandidate(url="https://example.org/not-extracted", domain="example.org")],
    )
    unextracted = [
        source["id"] for source in research.list_sources(project["id"])
        if source["url"].endswith("/not-extracted")
    ][0]
    with pytest.raises(ValueError, match="extracted source"):
        KnowledgeRepository(database).add(project["id"], "fact", "Content", [unextracted])


def test_knowledge_item_delete_and_missing_update(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    item_id = repository.add(project["id"], "example", "Example content", source_ids[:1])
    repository.delete(item_id)
    assert repository.get(item_id) is None
    with pytest.raises(KeyError):
        repository.update_review(item_id, "accepted")
    with pytest.raises(KeyError):
        repository.delete(item_id)



def test_duplicate_knowledge_reuses_item_and_preserves_review(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    first_id = repository.add(
        project["id"],
        "procedure",
        "Search the tracker before reporting.",
        source_ids[:1],
        evidence={source_ids[0]: "Search the tracker"},
        confidence=0.9,
    )
    repository.update_review(first_id, "accepted")

    repeated_id = repository.add(
        project["id"],
        "procedure",
        "  SEARCH   THE TRACKER BEFORE REPORTING.  ",
        source_ids[:1],
        evidence={source_ids[0]: "Search the tracker"},
        confidence=0.8,
    )

    assert repeated_id == first_id
    items = repository.list_for_project(project["id"])
    assert len(items) == 1
    assert items[0]["review_status"] == "accepted"


def test_duplicate_knowledge_adds_new_source_provenance(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    first_id = repository.add(
        project["id"],
        "fact",
        "Python supports reusable functions.",
        source_ids[:1],
        evidence={source_ids[0]: "reusable functions"},
    )

    second_id = repository.add(
        project["id"],
        "fact",
        "Python supports reusable functions.",
        source_ids[1:],
        evidence={source_ids[1]: "supports reusable functions"},
    )

    assert second_id == first_id
    item = repository.get(first_id)
    assert len(item["sources"]) == 2
    assert {source["id"] for source in item["sources"]} == set(source_ids)


def test_generation_context_includes_only_accepted_knowledge_and_provenance(
    prepared_sources,
):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    accepted_id = repository.add(
        project["id"],
        "definition",
        "A function is a reusable block of code.",
        source_ids,
        evidence={
            source_ids[0]: "reusable block of code",
            source_ids[1]: "function definition",
        },
        confidence=0.95,
    )
    repository.update_review(accepted_id, "accepted")
    repository.add(project["id"], "fact", "Pending material", source_ids[:1])
    rejected_id = repository.add(
        project["id"], "fact", "Rejected material", source_ids[1:]
    )
    repository.update_review(rejected_id, "rejected")

    context = KnowledgeContextService(repository).build_context(project["id"])

    assert context["project_id"] == project["id"]
    assert [item["knowledge_id"] for item in context["knowledge_items"]] == [
        accepted_id
    ]
    item = context["knowledge_items"][0]
    assert item["kind"] == "definition"
    assert item["confidence"] == pytest.approx(0.95)
    assert {source["source_id"] for source in item["sources"]} == set(source_ids)
    assert {source["url"] for source in item["sources"]} == {
        "https://example.org/a",
        "https://example.org/b",
    }
    assert {source["evidence"] for source in item["sources"]} == {
        "reusable block of code",
        "function definition",
    }
    selected = KnowledgeContextService(repository).build_context(
        project["id"], [accepted_id]
    )
    assert len(selected["knowledge_items"]) == 1


def test_generation_context_rejects_unaccepted_or_cross_project_selection(
    prepared_sources,
):
    database, project, other_project, source_ids, other_source_id = prepared_sources
    repository = KnowledgeRepository(database)
    pending_id = repository.add(
        project["id"], "fact", "Pending material", source_ids[:1]
    )
    with pytest.raises(ValueError, match="must be accepted"):
        KnowledgeContextService(repository).build_context(
            project["id"], [pending_id]
        )

    other_id = repository.add(
        other_project["id"], "fact", "Other project material", [other_source_id]
    )
    repository.update_review(other_id, "accepted")
    with pytest.raises(ValueError, match="must be accepted"):
        KnowledgeContextService(repository).build_context(project["id"], [other_id])


def test_generation_context_rejects_duplicate_selection_ids(prepared_sources):
    database, project, _, source_ids, _ = prepared_sources
    repository = KnowledgeRepository(database)
    item_id = repository.add(project["id"], "fact", "Accepted material", source_ids[:1])
    repository.update_review(item_id, "accepted")

    with pytest.raises(ValueError, match="unique IDs"):
        KnowledgeContextService(repository).build_context(
            project["id"], [item_id, item_id]
        )
