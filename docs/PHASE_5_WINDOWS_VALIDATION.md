# Phase 5: Windows Validation

This checkpoint adds a SQLite repository only. No new UI or automatic AI extraction is present yet.

## 1. Update the isolated feature branch

Inspect local modifications before switching branches. Do not reset, stash, or overwrite the three existing local changes in `app/config.py`, `storage/database.py`, and `storage/repositories.py`.

```powershell
git fetch origin
git switch --track origin/feature/phase-5-knowledge-pool
```

If the branch already exists locally:

```powershell
git switch feature/phase-5-knowledge-pool
git pull --ff-only origin feature/phase-5-knowledge-pool
```

## 2. Validation

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest
```

## 3. Scope of the automated tests

The new tests cover knowledge-item creation, multiple source references, evidence snippets, project isolation, mandatory extraction provenance, review-state filtering, deletion, and invalid inputs.

## 4. Current limitation

The repository API is not yet exposed through a Knowledge Pool UI and does not call AI models. Those are follow-on tasks once this storage checkpoint is validated locally.
