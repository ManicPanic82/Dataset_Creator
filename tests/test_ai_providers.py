from __future__ import annotations

import httpx
import pytest

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


def test_ollama_structured_generation(monkeypatch) -> None:
    def fake_post(url, headers, json, timeout):
        assert url.endswith("/api/chat")
        assert json["model"] == "qwen2.5"
        assert json["format"] == "json"
        assert json["think"] is False
        assert json["options"] == {"num_predict": 2048}
        assert timeout == 600.0
        return httpx.Response(
            200,
            json={"message": {"content": '{"objective": "Research Python", "scope": "docs"}'}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = AIProvider(
        ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434", timeout=600.0)
    )
    result = provider.generate_json("qwen2.5", "Return JSON.", "Research Python.")

    assert result == {"objective": "Research Python", "scope": "docs"}


def test_ollama_truncated_generation_reports_token_limit(monkeypatch) -> None:
    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"objective": "unfinished'},
                "done_reason": "length",
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = AIProvider(
        ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434", timeout=600.0)
    )

    with pytest.raises(ValueError, match="token limit"):
        provider.generate_json("qwen3:4b", "system", "user")


def test_openai_compatible_structured_generation(monkeypatch) -> None:
    def fake_post(url, headers, json, timeout):
        assert url.endswith("/v1/chat/completions")
        assert json["response_format"] == {"type": "json_object"}
        assert headers["Authorization"] == "Bearer runtime-secret"
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '{"ok": true}'}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = AIProvider(
        ProviderConfig(
            ProviderKind.OPENAI_COMPATIBLE,
            "https://api.example.test",
            api_key="runtime-secret",
        )
    )

    assert provider.generate_json("model-a", "system", "user") == {"ok": True}


def test_structured_generation_rejects_non_json(monkeypatch) -> None:
    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            json={"message": {"content": "not json"}},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = AIProvider(ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434"))

    with pytest.raises(ValueError, match="valid JSON"):
        provider.generate_json("model-a", "system", "user")


def test_ollama_generation_logs_timing_and_runtime_metrics(monkeypatch, caplog) -> None:
    def fake_post(url, **kwargs):
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"ok": true}'},
                "total_duration": 2_000_000_000,
                "load_duration": 500_000_000,
                "prompt_eval_count": 42,
                "eval_count": 12,
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = AIProvider(
        ProviderConfig(
            ProviderKind.OLLAMA,
            "http://user:password@localhost:11434/private-path?token=hidden",
            timeout=120.0,
        )
    )

    with caplog.at_level("INFO"):
        result = provider.generate_json(
            "qwen3.5:4b", "private system prompt", "private user prompt"
        )
        assert result == {"ok": True}

    messages = "\\n".join(record.getMessage() for record in caplog.records)
    assert "Structured generation started" in messages
    assert "Structured generation HTTP response received" in messages
    assert "Ollama generation metrics" in messages
    assert "prompt_eval_count" in messages
    assert "Structured generation completed" in messages
    assert "localhost:11434" in messages
    assert "password" not in messages
    assert "token=hidden" not in messages
    assert "private system prompt" not in messages
    assert "private user prompt" not in messages


def test_generation_timeout_is_logged_with_elapsed_time(monkeypatch, caplog) -> None:
    def fake_post(url, **kwargs):
        request = httpx.Request("POST", url)
        raise httpx.ReadTimeout("timed out", request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = AIProvider(
        ProviderConfig(ProviderKind.OLLAMA, "http://localhost:11434", timeout=120.0)
    )

    with caplog.at_level("ERROR"), pytest.raises(httpx.ReadTimeout):
        provider.generate_json("qwen3.5:4b", "system", "user")

    assert "Structured generation failed" in caplog.text
    assert "ReadTimeout" in caplog.text
    assert "timeout=120.0s" in caplog.text
