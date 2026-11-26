from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from dataset_forge.storage.database import Database

DATASET_TYPES = {"instruction", "question_answer", "conversational"}
RECORD_STATUSES = {"pending_review", "accepted", "rejected"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class DatasetRecordRepository:
    """Persist generated draft records with links to their supporting knowledge."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS dataset_records (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    dataset_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'pending_review',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_dataset_records_project_status
                    ON dataset_records(project_id, review_status, created_at DESC);

                CREATE TABLE IF NOT EXISTS dataset_record_knowledge (
                    record_id TEXT NOT NULL REFERENCES dataset_records(id)
                        ON DELETE CASCADE,
                    knowledge_id TEXT NOT NULL REFERENCES knowledge_items(id)
                        ON DELETE RESTRICT,
                    PRIMARY KEY (record_id, knowledge_id)
                );

                CREATE INDEX IF NOT EXISTS idx_dataset_record_knowledge_item
                    ON dataset_record_knowledge(knowledge_id);
                """
            )

    def add(
        self,
        project_id: str,
        dataset_type: str,
        payload: dict[str, Any],
        knowledge_ids: list[str] | tuple[str, ...],
    ) -> str:
        if dataset_type not in DATASET_TYPES:
            raise ValueError("Unsupported dataset type.")
        if not knowledge_ids or len(set(knowledge_ids)) != len(knowledge_ids):
            raise ValueError("Each dataset record requires unique supporting knowledge IDs.")
        record_id = str(uuid.uuid4())
        now = _now()
        with self.database.connect() as connection:
            for knowledge_id in knowledge_ids:
                row = connection.execute(
                    """SELECT project_id, review_status FROM knowledge_items
                       WHERE id = ?""",
                    (knowledge_id,),
                ).fetchone()
                if row is None or row["project_id"] != project_id:
                    raise ValueError("Record knowledge must belong to the selected project.")
                if row["review_status"] != "accepted":
                    raise ValueError("Record provenance must reference accepted knowledge.")
            connection.execute(
                """INSERT INTO dataset_records
                   (id, project_id, dataset_type, payload_json, review_status,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, 'pending_review', ?, ?)""",
                (record_id, project_id, dataset_type, json.dumps(payload, ensure_ascii=False),
                 now, now),
            )
            connection.executemany(
                """INSERT INTO dataset_record_knowledge (record_id, knowledge_id)
                   VALUES (?, ?)""",
                [(record_id, knowledge_id) for knowledge_id in knowledge_ids],
            )
        return record_id

    def get(self, record_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM dataset_records WHERE id = ?", (record_id,)
            ).fetchone()
            if row is None:
                return None
            knowledge = connection.execute(
                """SELECT k.id, k.kind, k.content, k.confidence,
                          s.id AS source_id, s.url AS source_url, s.title AS source_title,
                          s.domain AS source_domain, kis.evidence
                   FROM dataset_record_knowledge drk
                   JOIN knowledge_items k ON k.id = drk.knowledge_id
                   LEFT JOIN knowledge_item_sources kis ON kis.knowledge_id = k.id
                   LEFT JOIN source_candidates s ON s.id = kis.source_id
                   WHERE drk.record_id = ? ORDER BY k.id, s.url""",
                (record_id,),
            ).fetchall()
        result = dict(row)
        result["payload"] = json.loads(result.pop("payload_json"))
        provenance: dict[str, dict[str, Any]] = {}
        for item in knowledge:
            entry = provenance.setdefault(
                item["id"],
                {
                    "knowledge_id": item["id"],
                    "kind": item["kind"],
                    "content": item["content"],
                    "confidence": item["confidence"],
                    "sources": [],
                },
            )
            if item["source_id"] is not None:
                entry["sources"].append(
                    {
                        "source_id": item["source_id"],
                        "url": item["source_url"],
                        "title": item["source_title"],
                        "domain": item["source_domain"],
                        "evidence": item["evidence"],
                    }
                )
        result["provenance"] = list(provenance.values())
        return result

    def list_for_project(
        self, project_id: str, *, review_status: str | None = None
    ) -> list[dict[str, Any]]:
        if review_status is not None and review_status not in RECORD_STATUSES:
            raise ValueError("Invalid dataset record review status.")
        query = "SELECT id FROM dataset_records WHERE project_id = ?"
        params: list[str] = [project_id]
        if review_status is not None:
            query += " AND review_status = ?"
            params.append(review_status)
        query += " ORDER BY created_at DESC"
        with self.database.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        records = [self.get(row["id"]) for row in rows]
        return [record for record in records if record is not None]

    def update_review(self, record_id: str, status: str) -> None:
        if status not in RECORD_STATUSES:
            raise ValueError("Review status must be pending_review, accepted, or rejected.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE dataset_records SET review_status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), record_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(record_id)
