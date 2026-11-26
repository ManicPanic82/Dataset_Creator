from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from dataset_forge.storage.database import Database

KNOWLEDGE_TYPES = {
    "concept", "definition", "fact", "procedure", "example", "code",
    "comparison", "troubleshooting",
}
REVIEW_STATUSES = {"pending", "accepted", "rejected"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class KnowledgeRepository:
    """Project-scoped knowledge records with mandatory source provenance."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    confidence REAL,
                    review_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_project_review
                    ON knowledge_items(project_id, review_status, created_at DESC);

                CREATE TABLE IF NOT EXISTS knowledge_item_sources (
                    knowledge_id TEXT NOT NULL REFERENCES knowledge_items(id)
                        ON DELETE CASCADE,
                    source_id TEXT NOT NULL REFERENCES source_candidates(id)
                        ON DELETE CASCADE,
                    evidence TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (knowledge_id, source_id)
                );

                CREATE INDEX IF NOT EXISTS idx_knowledge_sources_source
                    ON knowledge_item_sources(source_id);
                """
            )

    def add(
        self,
        project_id: str,
        kind: str,
        content: str,
        source_ids: list[str] | tuple[str, ...],
        *,
        evidence: dict[str, str] | None = None,
        confidence: float | None = None,
    ) -> str:
        clean_kind = kind.strip().lower()
        clean_content = content.strip()
        if clean_kind not in KNOWLEDGE_TYPES:
            raise ValueError(f"Unsupported knowledge type: {kind!r}.")
        if not clean_content:
            raise ValueError("Knowledge content cannot be empty.")
        if len(clean_content) > 20_000:
            raise ValueError("Knowledge content cannot exceed 20,000 characters.")
        if not source_ids or len(set(source_ids)) != len(source_ids):
            raise ValueError("Knowledge items require unique source IDs.")
        if confidence is not None and not 0.0 <= confidence <= 1.0:
            raise ValueError("Confidence must be between 0 and 1.")
        evidence = evidence or {}
        now = _now()
        item_id = str(uuid.uuid4())

        with self.database.connect() as connection:
            for source_id in source_ids:
                source = connection.execute(
                    "SELECT project_id, review_status FROM source_candidates WHERE id = ?",
                    (source_id,),
                ).fetchone()
                if source is None or source["project_id"] != project_id:
                    raise ValueError("Each source must belong to the selected project.")
                extraction = connection.execute(
                    "SELECT 1 FROM source_extractions WHERE source_id = ?",
                    (source_id,),
                ).fetchone()
                if extraction is None:
                    raise ValueError("Knowledge provenance requires an extracted source.")
            connection.execute(
                """INSERT INTO knowledge_items
                   (id, project_id, kind, content, confidence, review_status,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (item_id, project_id, clean_kind, clean_content, confidence, now, now),
            )
            connection.executemany(
                """INSERT INTO knowledge_item_sources
                   (knowledge_id, source_id, evidence) VALUES (?, ?, ?)""",
                [(item_id, source_id, evidence.get(source_id, "").strip())
                 for source_id in source_ids],
            )
        return item_id

    def list_extracted_sources(self, project_id: str) -> list[dict[str, Any]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """SELECT s.id, s.url, s.title, s.domain, e.final_url,
                          e.extracted_text, e.fetched_at
                   FROM source_candidates s
                   JOIN source_extractions e ON e.source_id = s.id
                   WHERE s.project_id = ?
                   ORDER BY s.url""",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, knowledge_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM knowledge_items WHERE id = ?", (knowledge_id,)
            ).fetchone()
            if row is None:
                return None
            sources = connection.execute(
                """SELECT s.id, s.url, s.domain, s.title, s.review_status,
                          k.evidence
                   FROM knowledge_item_sources k
                   JOIN source_candidates s ON s.id = k.source_id
                   WHERE k.knowledge_id = ? ORDER BY s.url""",
                (knowledge_id,),
            ).fetchall()
        result = dict(row)
        result["sources"] = [dict(source) for source in sources]
        return result

    def list_for_project(
        self, project_id: str, *, review_status: str | None = None
    ) -> list[dict[str, Any]]:
        if review_status is not None and review_status not in REVIEW_STATUSES:
            raise ValueError("Invalid review status.")
        query = "SELECT id FROM knowledge_items WHERE project_id = ?"
        parameters: list[object] = [project_id]
        if review_status:
            query += " AND review_status = ?"
            parameters.append(review_status)
        query += " ORDER BY created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        items = [self.get(row["id"]) for row in rows]
        return [item for item in items if item is not None]

    def update_review(self, knowledge_id: str, status: str) -> None:
        if status not in REVIEW_STATUSES:
            raise ValueError("Review status must be pending, accepted, or rejected.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE knowledge_items SET review_status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), knowledge_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(knowledge_id)

    def delete(self, knowledge_id: str) -> None:
        with self.database.connect() as connection:
            cursor = connection.execute(
                "DELETE FROM knowledge_items WHERE id = ?", (knowledge_id,)
            )
            if cursor.rowcount == 0:
                raise KeyError(knowledge_id)
