from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from dataset_forge.services.research import ResearchPlan, SourceCandidate
from dataset_forge.storage.database import Database


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


class ResearchRepository:
    """Project-scoped research persistence, isolated from the Phase 1 repositories."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self.database.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_plans (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    prompt TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_research_plans_project
                    ON research_plans(project_id, updated_at DESC);

                CREATE TABLE IF NOT EXISTS source_candidates (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    snippet TEXT NOT NULL DEFAULT '',
                    discovery_method TEXT NOT NULL,
                    discovered_at TEXT NOT NULL,
                    review_status TEXT NOT NULL DEFAULT 'pending',
                    UNIQUE(project_id, url)
                );

                CREATE INDEX IF NOT EXISTS idx_source_candidates_project
                    ON source_candidates(project_id, discovered_at DESC);
                """
            )

    def save_plan(
        self,
        project_id: str,
        prompt: str,
        plan: ResearchPlan,
        *,
        approved: bool = False,
    ) -> str:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValueError("Research prompt cannot be empty.")
        plan_id = str(uuid.uuid4())
        now = _now()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO research_plans
                    (id, project_id, prompt, plan_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    plan_id,
                    project_id,
                    clean_prompt,
                    json.dumps(plan.to_dict(), ensure_ascii=False),
                    "approved" if approved else "draft",
                    now,
                    now,
                ),
            )
        return plan_id

    def get_latest_plan(self, project_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM research_plans
                WHERE project_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["plan"] = ResearchPlan.from_dict(json.loads(record.pop("plan_json")))
        return record

    def add_sources(
        self,
        project_id: str,
        candidates: tuple[SourceCandidate, ...] | list[SourceCandidate],
    ) -> int:
        inserted = 0
        with self.database.connect() as connection:
            for candidate in candidates:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO source_candidates
                        (id, project_id, url, domain, title, snippet,
                         discovery_method, discovered_at, review_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        candidate.url,
                        candidate.domain,
                        candidate.title,
                        candidate.snippet,
                        candidate.discovery_method,
                        candidate.discovered_at,
                        candidate.review_status,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def list_sources(self, project_id: str) -> list[dict[str, str]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM source_candidates
                WHERE project_id = ?
                ORDER BY discovered_at DESC, domain, url
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_source_status(self, source_id: str, status: str) -> None:
        if status not in {"pending", "accepted", "rejected"}:
            raise ValueError("Source status must be pending, accepted, or rejected.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE source_candidates SET review_status = ? WHERE id = ?",
                (status, source_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(source_id)
