from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime

from dataset_forge.storage.database import Database


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ProjectRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, name: str, description: str = "") -> dict[str, str]:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Project name cannot be empty.")
        now = _now()
        project = {
            "id": str(uuid.uuid4()),
            "name": clean_name,
            "description": description.strip(),
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO projects
                   (id, name, description, status, created_at, updated_at)
                   VALUES (:id, :name, :description, :status, :created_at, :updated_at)""",
                project,
            )
        return project

    def list_all(self) -> list[dict[str, str]]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, project_id: str) -> dict[str, str] | None:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (project_id,)
            ).fetchone()
        return dict(row) if row else None

    def update_status(self, project_id: str, status: str) -> None:
        if status not in {"active", "archived"}:
            raise ValueError("Project status must be 'active' or 'archived'.")
        with self.database.connect() as connection:
            cursor = connection.execute(
                "UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                (status, _now(), project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)


class SettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def set(self, key: str, value: object) -> None:
        if not key.strip():
            raise ValueError("Setting key cannot be empty.")
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(key) DO UPDATE SET
                   value = excluded.value, updated_at = excluded.updated_at""",
                (key, json.dumps(value), _now()),
            )

    def get(self, key: str, default: object = None) -> object:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        return json.loads(row["value"]) if row else default
