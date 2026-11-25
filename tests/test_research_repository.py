from __future__ import annotations

import pytest

from dataset_forge.services.research import ResearchPlan, SourceCandidate
from dataset_forge.storage.database import Database
from dataset_forge.storage.repositories import ProjectRepository
from dataset_forge.storage.research_repository import ResearchRepository


def test_research_plan_is_saved_and_reopened_per_project(tmp_path) -> None:
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()
    project = ProjectRepository(database).create("Python research")
    research = ResearchRepository(database)
    plan = ResearchPlan.from_dict(
        {
            "objective": "Research Python debugging",
            "scope": "Official docs and practical guides",
            "topics": ["exceptions", "debuggers"],
            "search_queries": ["Python KeyError debugging"],
            "target_record_count": 300,
        }
    )

    plan_id = research.save_plan(
        project["id"],
        "Build a Python debugging dataset",
        plan,
        approved=True,
    )
    restored = research.get_latest_plan(project["id"])

    assert restored is not None
    assert restored["id"] == plan_id
    assert restored["status"] == "approved"
    assert restored["prompt"] == "Build a Python debugging dataset"
    assert restored["plan"] == plan


def test_source_candidates_are_deduplicated_and_reviewable(tmp_path) -> None:
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()
    project = ProjectRepository(database).create("Source project")
    research = ResearchRepository(database)
    candidate = SourceCandidate(
        url="https://docs.python.org/3/",
        domain="docs.python.org",
        discovery_method="manual",
    )

    assert research.add_sources(project["id"], [candidate, candidate]) == 1
    sources = research.list_sources(project["id"])
    assert len(sources) == 1
    assert sources[0]["review_status"] == "pending"

    research.update_source_status(sources[0]["id"], "accepted")
    assert research.list_sources(project["id"])[0]["review_status"] == "accepted"


def test_source_review_status_is_validated(tmp_path) -> None:
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()
    project = ProjectRepository(database).create("Status project")
    research = ResearchRepository(database)
    candidate = SourceCandidate(
        url="https://example.org/",
        domain="example.org",
    )
    research.add_sources(project["id"], [candidate])
    source_id = research.list_sources(project["id"])[0]["id"]

    with pytest.raises(ValueError, match="Source status"):
        research.update_source_status(source_id, "crawled")
