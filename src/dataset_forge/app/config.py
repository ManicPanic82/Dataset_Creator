from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppPaths:
    root: Path
    database: Path
    logs: Path
    projects: Path
    exports: Path

    @classmethod
    def from_environment(cls) -> "AppPaths":
        base = os.environ.get("LOCALAPPDATA")
        root = Path(base) / "DatasetForgeAI" if base else Path.home() / ".dataset_forge_ai"
        return cls(
            root=root,
            database=root / "dataset_forge.sqlite3",
            logs=root / "logs",
            projects=root / "projects",
            exports=root / "exports",
        )

    def ensure_directories(self) -> None:
        for path in (self.root, self.logs, self.projects, self.exports):
            path.mkdir(parents=True, exist_ok=True)
