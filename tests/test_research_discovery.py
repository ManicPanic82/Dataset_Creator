from __future__ import annotations

from dataset_forge.services.research import (
    DomainFilter,
    ResearchPlan,
    SearchResult,
)
from dataset_forge.services.research_discovery import ResearchDiscoveryService


class FakeSearchProvider:
    name = "fake-search"

    def search(self, query: str, max_results: int = 10):
        assert query
        assert max_results == 5
        return (
            SearchResult("https://docs.python.org/3/", "Python docs", "Official docs"),
            SearchResult("https://example.com/", "Example", "Not included"),
            SearchResult("http://127.0.0.1/", "Local", "Unsafe"),
        )


def test_discovery_service_filters_and_validates_search_results() -> None:
    plan = ResearchPlan.from_dict(
        {
            "objective": "Research Python",
            "scope": "Official documentation",
            "topics": ["Python"],
            "search_queries": ["Python official documentation"],
        }
    )

    accepted, rejected = ResearchDiscoveryService().discover(
        plan,
        FakeSearchProvider(),
        DomainFilter.create(include=["python.org"]),
        max_results_per_query=5,
    )

    assert len(accepted) == 1
    assert accepted[0].title == "Python docs"
    assert accepted[0].discovery_method == "fake-search"
    assert len(rejected) == 2


def test_discovery_service_allows_any_public_domain_by_default() -> None:
    plan = ResearchPlan.from_dict(
        {
            "objective": "Research Python",
            "scope": "Broad web research",
            "topics": ["Python"],
            "search_queries": ["Python learning resources"],
        }
    )

    accepted, rejected = ResearchDiscoveryService().discover(
        plan,
        FakeSearchProvider(),
        max_results_per_query=5,
    )

    assert {item.domain for item in accepted} == {
        "docs.python.org",
        "example.com",
    }
    assert len(rejected) == 1
    assert "Local" in rejected[0][1]


def test_discovery_service_validates_result_limit() -> None:
    plan = ResearchPlan.from_dict(
        {"objective": "Research", "scope": "Scope", "topics": []}
    )

    try:
        ResearchDiscoveryService().discover(
            plan,
            FakeSearchProvider(),
            max_results_per_query=100,
        )
    except ValueError as exc:
        assert "between 1 and 50" in str(exc)
    else:
        raise AssertionError("Expected invalid result limit to be rejected")
