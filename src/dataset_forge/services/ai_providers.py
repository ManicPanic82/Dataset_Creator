from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx


class ProviderKind(StrEnum):
    OLLAMA = "ollama"
    LM_STUDIO = "lm_studio"
    OPENAI_COMPATIBLE = "openai_compatible"


@dataclass(frozen=True)
class ProviderConfig:
    kind: ProviderKind
    endpoint: str
    api_key: str = ""
    timeout: float = 10.0

    def normalized_endpoint(self) -> str:
        return self.endpoint.strip().rstrip("/")


@dataclass(frozen=True)
class ProviderDiagnostic:
    success: bool
    message: str
    models: tuple[str, ...] = ()


class AIProvider:
    """Small, synchronous provider adapter. UI callers should run it in a worker."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def _request(self, path: str) -> dict[str, Any]:
        headers: dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        url = f"{self.config.normalized_endpoint()}/{path.lstrip('/')}"
        response = httpx.get(url, headers=headers, timeout=self.config.timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("The provider returned an unexpected response.")
        return payload

    def list_models(self) -> tuple[str, ...]:
        path = "api/tags" if self.config.kind == ProviderKind.OLLAMA else "v1/models"
        payload = self._request(path)
        key = "models" if self.config.kind == ProviderKind.OLLAMA else "data"
        entries = payload.get(key, [])
        if not isinstance(entries, list):
            raise ValueError("The provider's model list was not a list.")
        names: list[str] = []
        for item in entries:
            if isinstance(item, dict):
                name = item.get("name") if key == "models" else item.get("id")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())
        return tuple(names)

    def diagnose(self) -> ProviderDiagnostic:
        try:
            models = self.list_models()
            return ProviderDiagnostic(True, f"Connected. Found {len(models)} model(s).", models)
        except httpx.TimeoutException:
            return ProviderDiagnostic(False, "Connection timed out.")
        except httpx.HTTPStatusError as exc:
            return ProviderDiagnostic(False, f"HTTP error: {exc.response.status_code}.")
        except httpx.RequestError:
            return ProviderDiagnostic(False, "Could not reach the configured endpoint.")
        except (ValueError, TypeError):
            return ProviderDiagnostic(False, "The endpoint returned an invalid response.")


def create_provider(config: ProviderConfig) -> AIProvider:
    return AIProvider(config)
