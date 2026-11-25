from __future__ import annotations

import json
from typing import Any

from dataset_forge.services.ai_providers import ProviderKind
from dataset_forge.storage.repositories import SettingsRepository

DEFAULTS: dict[str, Any] = {
    "ai_provider": ProviderKind.OLLAMA.value,
    "ai_endpoint": "http://localhost:11434",
    "ai_model": "",
    "ai_task_models": {},
}


class ProviderSettings:
    def __init__(self, repository: SettingsRepository) -> None:
        self.repository = repository

    def get(self, key: str, default: Any = None) -> Any:
        if key in DEFAULTS:
            default = DEFAULTS[key] if default is None else default
        return self.repository.get(key, default)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise ValueError(f"Unsupported provider setting: {key}")
        self.repository.set(key, value)

    def task_model(self, task: str) -> str:
        models = self.get("ai_task_models", {})
        return models.get(task, "") if isinstance(models, dict) else ""

    def set_task_model(self, task: str, model: str) -> None:
        models = self.get("ai_task_models", {})
        if not isinstance(models, dict):
            models = {}
        models = dict(models)
        models[task] = model
        self.set("ai_task_models", models)

    def export_config(self) -> dict[str, Any]:
        return {key: self.get(key) for key in DEFAULTS}
