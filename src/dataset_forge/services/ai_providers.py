from __future__ import annotations

import json
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
    """Synchronous provider adapter. UI callers must run it in a worker."""

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        return headers

    def _request(self, path: str) -> dict[str, Any]:
        endpoint = self.config.normalized_endpoint()
        if not endpoint:
            raise ValueError("A provider endpoint is required.")
        url = f"{endpoint}/{path.lstrip('/')}"
        response = httpx.get(
            url,
            headers=self._headers(),
            timeout=self.config.timeout,
        )
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

    def generate_json(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
    ) -> dict[str, Any]:
        """Generate one JSON object using the selected model; never executes model output."""
        endpoint = self.config.normalized_endpoint()
        clean_model = model.strip()
        if not endpoint:
            raise ValueError("A provider endpoint is required.")
        if not clean_model:
            raise ValueError("Select a model before generating a research plan.")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if self.config.kind == ProviderKind.OLLAMA:
            path = "api/chat"
            body: dict[str, Any] = {
                "model": clean_model,
                "messages": messages,
                "stream": False,
                "format": "json",
            }
        else:
            path = "v1/chat/completions"
            body = {
                "model": clean_model,
                "messages": messages,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            }

        response = httpx.post(
            f"{endpoint}/{path}",
            headers=self._headers(),
            json=body,
            timeout=self.config.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("The provider returned an invalid generation response.")

        if self.config.kind == ProviderKind.OLLAMA:
            message = payload.get("message")
            content = message.get("content") if isinstance(message, dict) else None
        else:
            choices = payload.get("choices")
            choice = choices[0] if isinstance(choices, list) and choices else None
            message = choice.get("message") if isinstance(choice, dict) else None
            content = message.get("content") if isinstance(message, dict) else None

        if not isinstance(content, str) or not content.strip():
            raise ValueError("The model returned no structured content.")
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError("The model response was not valid JSON.") from exc
        if not isinstance(result, dict):
            raise ValueError("The model response must be a JSON object.")
        return result

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
