from __future__ import annotations

import httpx

from dataset_forge.services.ai_providers import AIProvider, ProviderConfig, ProviderKind


def test_ollama_model_discovery(monkeypatch) -> None:
    def fake_get(url, **kwargs):
        assert url.endswith("/api/tags")
        return httpx.Response(200, json={"models": [{"name": "llama3"}, {"name": "qwen"}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    provider = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434"))
    assert provider.list_models() == ("llama3", "qwen")


def test_openai_compatible_model_discovery_and_auth(monkeypatch) -> None:
    def fake_get(url, headers, timeout):
        assert url.endswith("/v1/models")
        assert headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json={"data": [{"id": "model-a"}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    provider = AIProvider(
        ProviderConfig(ProviderKind.LM_STUDIO, "http://localhost:1234", api_key="secret")
    )
    assert provider.list_models() == ("model-a",)


def test_diagnostic_reports_unreachable(monkeypatch) -> None:
    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", fake_get)
    result = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434")).diagnose()
    assert not result.success
    assert "reach" in result.message.lower()


def test_invalid_model_payload(monkeypatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: httpx.Response(200, json=[]))
    result = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434")).diagnose()
    assert not result.success
