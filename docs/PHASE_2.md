# Phase 2: AI Provider System

This phase establishes a provider-neutral connection and model discovery layer.

- Ollama: `/api/tags`
- LM Studio and OpenAI-compatible endpoints: `/v1/models`
- Per-request timeout and diagnostic messages
- Model discovery without initiating generation
- Provider settings stored through the application's settings repository
- API keys are not persisted by this phase
- Providers must be invoked from background workers in the GUI
- Tests use mocked HTTP responses and do not require running services

Supported provider settings are provider type, endpoint, default model, and task-specific model selections. This phase does not implement generation, research/search, prompt construction, or secret storage.

Local defaults:
- Ollama: `http://localhost:11434`
- LM Studio: `http://localhost:1234`

For OpenAI-compatible services, users can configure an endpoint and optionally provide a key at runtime. Do not save API keys to SQLite settings.
