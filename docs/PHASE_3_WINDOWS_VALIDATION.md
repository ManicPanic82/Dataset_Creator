# Phase 3: Windows Validation

Run these checks from PowerShell in the existing checkout. The Phase 3 branch is based on the validated Phase 2 branch and does not modify `config.py`, `database.py`, or `repositories.py`; existing local edits in those files should remain untouched.

## 1. Switch to the Phase 3 branch

First inspect the working tree:

```powershell
git status --short
```

Fetch and switch to the new branch:

```powershell
git fetch origin
git switch --track origin/feature/phase-3-research-discovery
```

If Git reports that the local branch already exists, use:

```powershell
git switch feature/phase-3-research-discovery
git pull origin feature/phase-3-research-discovery
```

Confirm the branch and ensure the existing local edits are still present:

```powershell
git log -1 --oneline
git status --short
```

Do not reset or stash the existing local changes in `src/dataset_forge/app/config.py`, `src/dataset_forge/storage/database.py`, or `src/dataset_forge/storage/repositories.py`.

## 2. Automated validation

Activate the existing virtual environment if needed, then run:

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest
```

Expected new coverage includes:
- Structured Ollama and OpenAI-compatible JSON generation.
- Research plan parsing and validation.
- URL normalization and rejection of unsafe destinations.
- Include/exclude domain filtering.
- Project-scoped research plan persistence.
- Candidate source persistence and review state.
- Provider-neutral search discovery filtering.

## 3. Launch the desktop application

```powershell
.\.venv\Scripts\dataset-forge.exe
```

## 4. Research workflow checks

1. Open an existing project or create a new one.
2. Open Settings and confirm Ollama is selected, the endpoint is `http://localhost:11434`, and a discovered model is selected.
3. Open Research and enter a practical research objective, such as researching Python debugging for a beginner-to-advanced training dataset.
4. Click **Generate research plan**.
5. Confirm generation completes without freezing the UI and that the JSON plan appears.
6. Edit a field in the plan, such as `target_record_count`, then click **Save draft**.
7. Click **Approve plan** and confirm the status message.
8. Switch to another project, then reopen the original project. Confirm its prompt and latest plan are restored.
9. In the URL import area, enter several public HTTP/HTTPS URLs, one per line.
10. Set an include-domain filter such as `python.org` and an exclude-domain filter such as `legacy.python.org`.
11. Click **Import URLs**. Confirm matching URLs appear as pending candidates and duplicates are not added.
12. Select a candidate and test **Accept selected** and **Reject selected**.
13. Confirm `http://localhost/`, `http://127.0.0.1/`, `file:///C:/Windows/win.ini`, and URLs containing embedded credentials are rejected.

**Important:** Phase 3 validates and stores candidate URLs only. It does not fetch or crawl them. Network access, redirect validation, robots.txt handling, and extraction are Phase 4.

## 5. Research-generation diagnostics

Ollama structured research generation allows up to 10 minutes for a response and requests at most 2,048 generated tokens. This accommodates slower local model loading and inference while keeping the plan response bounded. Provider connection diagnostics retain their short default timeout. Ollama responses that explicitly report a token-limit stop, or return malformed JSON, now produce a more actionable error instead of a generic JSON parsing message.

The application log is stored at:

```text
%LOCALAPPDATA%\DatasetForgeAI\logs\dataset_forge.log
```

When diagnosing a slow or failed research-plan request, reproduce it once and inspect the newest log entries. The diagnostic sequence records:

- Research request metadata: project, provider, model, configured timeout, and objective character count. Prompt contents and API keys are not logged.
- Background task queued, worker started, worker completed or failed, and elapsed time.
- Provider request start, endpoint host, timeout, prompt character counts, HTTP response status, response size, and elapsed time.
- Ollama runtime metrics when returned: model load duration, prompt evaluation duration/count, and response evaluation duration/count.
- Full exception traceback and exception type when provider generation fails.

Use PowerShell to inspect the latest entries:

```powershell
$log = Join-Path $env:LOCALAPPDATA "DatasetForgeAI\logs\dataset_forge.log"
Get-Content $log -Tail 120
```

For a focused view of research and provider diagnostics:

```powershell
Select-String -Path $log -Pattern "Research plan|Background task|Structured generation|Ollama generation metrics|ReadTimeout|Timeout"
```

Include the entries from **Research plan requested** through the final failure or completion when reporting a problem. This makes it possible to distinguish queue delay, worker delay, model loading/inference time, HTTP timeout, and JSON validation failures.

## 6. Final working-tree check

```powershell
git status --short
```

Do not commit unrelated local modifications as part of Phase 3 validation.
