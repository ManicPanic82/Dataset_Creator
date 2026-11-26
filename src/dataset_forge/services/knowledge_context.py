from __future__ import annotations

from typing import Any

from dataset_forge.storage.knowledge_repository import KnowledgeRepository


class KnowledgeContextService:
    """Prepare accepted, source-linked knowledge for downstream dataset generation."""

    def __init__(self, repository: KnowledgeRepository) -> None:
        self.repository = repository

    def build_context(
        self, project_id: str, knowledge_ids: list[str] | tuple[str, ...] | None = None
    ) -> dict[str, Any]:
        """Return accepted knowledge only, retaining every source and evidence link.

        When IDs are supplied, every requested item must be accepted and belong to
        the selected project. Invalid selections fail closed rather than being skipped.
        """
        if knowledge_ids is not None and len(set(knowledge_ids)) != len(knowledge_ids):
            raise ValueError("Knowledge selections must contain unique IDs.")

        project_items = self.repository.list_for_project(project_id)
        accepted = {
            item["id"]: item
            for item in project_items
            if item["review_status"] == "accepted"
        }

        if knowledge_ids is None:
            selected = list(accepted.values())
        else:
            selected = []
            for knowledge_id in knowledge_ids:
                item = accepted.get(knowledge_id)
                if item is None:
                    raise ValueError(
                        "Every selected knowledge item must be accepted "
                        "and belong to the selected project."
                    )
                selected.append(item)

        return {
            "project_id": project_id,
            "knowledge_items": [
                {
                    "knowledge_id": item["id"],
                    "kind": item["kind"],
                    "content": item["content"],
                    "confidence": item["confidence"],
                    "sources": [
                        {
                            "source_id": source["id"],
                            "url": source["url"],
                            "title": source["title"],
                            "domain": source["domain"],
                            "evidence": source["evidence"],
                        }
                        for source in item["sources"]
                    ],
                }
                for item in selected
            ],
        }
