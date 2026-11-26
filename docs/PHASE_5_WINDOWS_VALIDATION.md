# Phase 5: Windows Validation

This checkpoint adds the repository and review UI. Automatic AI extraction is not implemented yet.

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

## 3. UI smoke check

1. Launch Dataset Forge AI.
2. Open the project that contains your extracted source snapshots.
3. Select **Knowledge Pool** in the navigation.
4. Confirm the empty-state/status message is visible if no knowledge items have been extracted yet.
5. Change the review-status and type filters. Confirm the page remains responsive.
6. Switch to another project and return. Confirm the page is project-scoped.

The list will remain empty until the AI extraction workflow or knowledge items are added. This UI checkpoint provides review/filter controls, but no AI extraction button yet.

## 4. Scope of automated tests

Tests cover repository creation, multiple source references, evidence snippets, project isolation, mandatory extraction provenance, review-state filtering, deletion, and invalid inputs.
