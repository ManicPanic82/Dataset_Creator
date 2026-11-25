from __future__ import annotations

from dataset_forge.services.crawler import ExtractedPage
from dataset_forge.services.research import SourceCandidate
from dataset_forge.storage.database import Database
from dataset_forge.storage.repositories import ProjectRepository
from dataset_forge.storage.research_repository import ResearchRepository
from dataset_forge.storage.source_content_repository import SourceContentRepository


def test_source_extraction_persists_and_updates(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()
    projects = ProjectRepository(database)
    project = projects.create("Research")
    research = ResearchRepository(database)
    research.add_sources(
        project["id"],
        [SourceCandidate(url="https://example.org/", domain="example.org")],
    )
    source_id = research.list_sources(project["id"])[0]["id"]
    content = SourceContentRepository(database)
    page = ExtractedPage(
        requested_url="https://example.org/",
        final_url="https://example.org/",
        title="Example",
        text="Extracted content",
        links=(),
        content_hash="a" * 64,
        http_status=200,
    )
    content.save(source_id, page)
    saved = content.get(source_id)
    assert saved is not None
    assert saved["title"] == "Example"
    assert saved["extracted_text"] == "Extracted content"
    content.save(source_id, page)
    assert content.get(source_id)["content_hash"] == "a" * 64

def test_source_extraction_survives_repository_and_database_reopen(tmp_path):
    database_path = tmp_path / "app.sqlite3"
    database = Database(database_path)
    database.initialise()
    project = ProjectRepository(database).create("Persistent research")
    research = ResearchRepository(database)
    research.add_sources(
        project["id"],
        [SourceCandidate(url="https://example.org/guide", domain="example.org")],
    )
    source_id = research.list_sources(project["id"])[0]["id"]
    page = ExtractedPage(
        requested_url="https://example.org/guide",
        final_url="https://example.org/guide",
        title="Persistent guide",
        text="This content must remain available after reopening the application.",
        links=("https://example.org/next",),
        content_hash="b" * 64,
        http_status=200,
    )
    SourceContentRepository(database).save(source_id, page)

    reopened_database = Database(database_path)
    reopened_content = SourceContentRepository(reopened_database)
    saved = reopened_content.get(source_id)

    assert saved is not None
    assert saved["requested_url"] == "https://example.org/guide"
    assert saved["final_url"] == "https://example.org/guide"
    assert saved["title"] == "Persistent guide"
    assert saved["extracted_text"] == (
        "This content must remain available after reopening the application."
    )
    assert saved["content_hash"] == "b" * 64
    assert saved["http_status"] == 200
