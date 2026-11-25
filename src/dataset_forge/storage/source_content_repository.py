from __future__ import annotations

from typing import Any

from dataset_forge.services.crawler import ExtractedPage
from dataset_forge.storage.database import Database


class SourceContentRepository:
    """Persists extracted source snapshots and their provenance."""

    def __init__(self, database: Database) -> None:
        self.database = database
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS source_extractions (
                    source_id TEXT PRIMARY KEY
                        REFERENCES source_candidates(id) ON DELETE CASCADE,
                    requested_url TEXT NOT NULL,
                    final_url TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    extracted_text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    http_status INTEGER NOT NULL,
                    fetched_at TEXT NOT NULL
                )
                """
            )

    def save(self, source_id: str, page: ExtractedPage) -> None:
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM source_candidates WHERE id = ?", (source_id,)
            ).fetchone()
            if exists is None:
                raise KeyError(source_id)
            connection.execute(
                """
                INSERT INTO source_extractions
                    (source_id, requested_url, final_url, title, extracted_text,
                     content_hash, http_status, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    requested_url = excluded.requested_url,
                    final_url = excluded.final_url,
                    title = excluded.title,
                    extracted_text = excluded.extracted_text,
                    content_hash = excluded.content_hash,
                    http_status = excluded.http_status,
                    fetched_at = excluded.fetched_at
                """,
                (
                    source_id, page.requested_url, page.final_url, page.title,
                    page.text, page.content_hash, page.http_status, page.fetched_at,
                ),
            )

    def get(self, source_id: str) -> dict[str, Any] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM source_extractions WHERE source_id = ?", (source_id,)
            ).fetchone()
        return dict(row) if row else None
