# Phase 3: Windows Validation

Run these checks from PowerShell in the existing checkout. The Phase 3 branch is based on the validated Phase 2 branch and does not modify `config.py`, `database.py`, or `repositories.py`; existing local edits in those files should remain untouched.

## 1. Switch to the Phase 3 branch

First inspect the working tree:

```powershell
git status --short
```

Fetch and switch to the new branch:

```powershell
git fetch origin feature/phase-3-research-discovery
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

## 5. Final working-tree check

```powershell
git status --short
```

Do not commit unrelated local modifications as part of Phase 3 validation.
