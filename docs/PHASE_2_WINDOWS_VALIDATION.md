# Phase 2 Windows Validation

Run from the repository root in PowerShell.

```powershell
..venvScriptspython.exe -m pip install -e ".[dev]"
..venvScriptsuff.exe check .
..venvScriptspython.exe -m pytest
..venvScriptspython.exe .main.py
```

In the application:
1. Open Settings.
2. Select Ollama, LM Studio or OpenAI-compatible.
3. Set the endpoint. Defaults are supplied for Ollama and LM Studio.
4. Optionally enter an API key. The key remains in memory and is not saved.
5. Test connection and discover models.
6. Select a model and save provider settings.
7. Restart the app and confirm endpoint/provider/model settings persist (key should not).

Suggested local endpoint values:
- Ollama: `http://localhost:11434`
- LM Studio: `http://localhost:1234`
- OpenAI API: `https://api.openai.com` (use the OpenAI-compatible option)

Connection discovery runs in the Qt task pool and does not block the UI. Tests do not require live services.
