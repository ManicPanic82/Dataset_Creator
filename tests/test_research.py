from __future__ import annotations

import pytest

from dataset_forge.services.research import (
    DomainFilter,
    ResearchPlan,
    domain_from_url,
    import_url_candidates,
    normalize_public_url,
)


def test_research_plan_validates_and_round_trips() -> None:
    payload = {
        "objective": "Research Python debugging",
        "scope": "Official documentation and practical examples",
        "topics": ["exceptions", "debuggers"],
        "subtopics": {"exceptions": ["KeyError", "TypeError"]},
        "search_queries": ["Python debugging guide"],
        "preferred_domains": ["docs.python.org"],
        "excluded_domains": ["example.net"],
        "source_types": ["official documentation"],
        "quality_criteria": ["current", "authoritative"],
        "target_record_count": 250,
        "dataset_type": "question_answer",
    }

    plan = ResearchPlan.from_dict(payload)

    assert plan.objective == payload["objective"]
    assert plan.subtopics["exceptions"] == ("KeyError", "TypeError")
    assert ResearchPlan.from_dict(plan.to_dict()) == plan


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"objective": "", "scope": "scope"}, "objective"),
        ({"objective": "objective", "scope": ""}, "scope"),
        (
            {"objective": "objective", "scope": "scope", "target_record_count": True},
            "integer",
        ),
        (
            {"objective": "objective", "scope": "scope", "target_record_count": 0},
            "between",
        ),
        (
            {"objective": "objective", "scope": "scope", "topics": "not a list"},
            "list",
        ),
    ],
)
def test_research_plan_rejects_invalid_fields(payload, message) -> None:
    with pytest.raises(ValueError, match=message):
        ResearchPlan.from_dict(payload)


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://127.0.0.1/",
        "http://192.168.1.10/",
        "http://[::1]/",
        "http://router.local/",
        "http://user:password@example.com/",
    ],
)
def test_unsafe_or_unsupported_urls_are_rejected(url) -> None:
    with pytest.raises(ValueError):
        normalize_public_url(url)


def test_public_url_is_normalized() -> None:
    assert normalize_public_url(" HTTPS://Example.COM:443/path#section ") == (
        "https://example.com/path"
    )
    assert domain_from_url("https://docs.python.org/3/") == "docs.python.org"


def test_domain_filter_matches_subdomains_and_exclusions() -> None:
    filters = DomainFilter.create(
        include=["python.org"],
        exclude=["legacy.python.org"],
    )

    assert filters.allows("https://docs.python.org/3/")
    assert not filters.allows("https://legacy.python.org/2/")
    assert not filters.allows("https://example.com/")


def test_url_import_returns_candidates_and_reasons() -> None:
    filters = DomainFilter.create(include=["python.org"])
    accepted, rejected = import_url_candidates(
        "https://docs.python.org/3/\n"
        "https://docs.python.org/3/\n"
        "http://localhost/\n"
        "https://example.com/",
        filters,
    )

    assert len(accepted) == 1
    assert accepted[0].domain == "docs.python.org"
    assert len(rejected) == 2
    assert "Local" in rejected[0][1]
    assert "domain filters" in rejected[1][1]


def test_url_import_allows_any_public_domain_by_default() -> None:
    accepted, rejected = import_url_candidates(
        "https://docs.python.org/3/\n"
        "https://example.com/\n"
        "http://127.0.0.1/"
    )

    assert [item.domain for item in accepted] == ["docs.python.org", "example.com"]
    assert len(rejected) == 1
    assert "Local" in rejected[0][1]


def test_research_plan_rejects_unsafe_domain_filters() -> None:
    with pytest.raises(ValueError, match="Local and private"):
        ResearchPlan.from_dict(
            {
                "objective": "Research",
                "scope": "Scope",
                "topics": ["topic"],
                "preferred_domains": ["localhost"],
            }
        )


def test_research_plan_recovers_root_metadata_nested_under_subtopics() -> None:
    plan = ResearchPlan.from_dict(
        {
            "objective": "Research Python debugging",
            "scope": "Official documentation",
            "topics": ["debugging"],
            "subtopics": {
                "debugging": ["breakpoints", "tracebacks"],
                "target_record_count": 250,
                "dataset_type": "question_answer",
            },
        }
    )

    assert plan.subtopics == {"debugging": ("breakpoints", "tracebacks")}
    assert plan.target_record_count == 250
    assert plan.dataset_type == "question_answer"
