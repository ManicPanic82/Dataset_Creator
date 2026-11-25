from __future__ import annotations

import pytest

from dataset_forge.services.research import ResearchPlan
from dataset_forge.services.research_planner import ResearchPlanner


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.last_request = None

    def generate_json(self, model, system_prompt, user_prompt):
        self.last_request = (model, system_prompt, user_prompt)
        return self.payload


def test_research_planner_generates_validated_plan() -> None:
    provider = FakeProvider(
        {
            "objective": "Learn Python debugging",
            "scope": "Official docs and real-world examples",
            "topics": ["exceptions", "breakpoints"],
            "search_queries": ["Python debugging tutorial"],
            "target_record_count": 500,
        }
    )
    planner = ResearchPlanner(provider, "qwen2.5")

    plan = planner.create_plan("  Learn Python debugging  ")

    assert isinstance(plan, ResearchPlan)
    assert plan.target_record_count == 500
    assert provider.last_request[0] == "qwen2.5"
    assert "RESEARCH OBJECTIVE" in provider.last_request[2]


@pytest.mark.parametrize("objective", ["", "   "])
def test_research_planner_rejects_empty_objective(objective) -> None:
    planner = ResearchPlanner(FakeProvider({}), "qwen2.5")

    with pytest.raises(ValueError, match="objective"):
        planner.create_plan(objective)


def test_research_planner_rejects_oversized_objective() -> None:
    planner = ResearchPlanner(FakeProvider({}), "qwen2.5")

    with pytest.raises(ValueError, match="8,000"):
        planner.create_plan("x" * 8001)


def test_research_planner_rejects_malformed_model_plan() -> None:
    planner = ResearchPlanner(FakeProvider({"objective": "missing scope"}), "qwen2.5")

    with pytest.raises(ValueError, match="scope"):
        planner.create_plan("Research objective")
