from __future__ import annotations

import httpx

from dataset_forge.services.ai_providers import AIProvider, ProviderConfig, ProviderKind


def _response(payload: object, status_code: int = 200) -> httpx.Response:
    request = httpx.Request("GET", "http://localhost/test")
    return httpx.Response(status_code, json=payload, request=request)


def test_ollama_model_discovery(monkeypatch) -> None:
    def fake_get(url, **kwargs):
        assert url.endswith("/api/tags")
        return _response({"models": [{"name": "llama3"}, {"name": "qwen"}]})

    monkeypatch.setattr(httpx, "get", fake_get)
    provider = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434"))
    assert provider.list_models() == ("llama3", "qwen")


def test_openai_compatible_model_discovery_and_auth(monkeypatch) -> None:
    def fake_get(url, headers, timeout):
        assert url.endswith("/v1/models")
        assert headers["Authorization"] == "Bearer secret"
        return _response({"data": [{"id": "model-a"}]})

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
    monkeypatch.setattr(httpx, "get", lambda *args, **kwargs: _response([]))
    result = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434")).diagnose()
    assert not result.success
    assert "invalid" in result.message.lower()


def test_http_error_is_reported(monkeypatch) -> None:
    monkeypatch.setattr(
        httpx, "get", lambda *args, **kwargs: _response({"error": "unauthorized"}, 401)
    )
    result = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434")).diagnose()
    assert not result.success
    assert "401" in result.message


def test_empty_endpoint_is_rejected() -> None:
    result = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "   ")).diagnose()
    assert not result.success
    assert "invalid" in result.message.lower()
