# Phase 4: Windows Validation

Run from the existing PowerShell checkout. This branch is based on the validated Phase 3 diagnostics branch and does not modify the three previously preserved local files: `app/config.py`, `storage/database.py`, or `storage/repositories.py`.

## 1. Switch to the Phase 4 branch

Inspect local changes first:

```powershell
git status --short
git fetch origin
git switch --track origin/feature/phase-4-crawler-extraction
```

If the local branch already exists:

```powershell
git switch feature/phase-4-crawler-extraction
git pull --ff-only origin feature/phase-4-crawler-extraction
```

Do not reset, stash, or overwrite existing local modifications.

## 2. Automated checks

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\python.exe -m pytest
```

## 3. Launch

```powershell
.\.venv\Scripts\dataset-forge.exe
```

## 4. End-to-end source workflow

1. Open the project containing the approved Python research plan.
2. Open Research and import a public URL such as `https://docs.python.org/3/tutorial/`.
3. Select the candidate and click **Accept selected**.
4. Open Sources, select the accepted candidate, and click **Fetch selected accepted source**.
5. Confirm fetching runs in the background and the extracted title, final URL, and readable text appear in the preview.
6. Navigate to Research and back to Sources. Confirm the candidate list refreshes without restarting the application and the extracted marker remains visible.
7. Select the extracted source again and confirm its readable text preview is restored.
8. Close and relaunch Dataset Forge, reopen the same project, open Sources, and confirm the extracted marker and full text preview are still available.
9. Confirm same-origin links discovered from the page appear as source candidates.
10. Enter a public sitemap URL in the sitemap field and click **Import sitemap**. Confirm the returned URLs appear as candidates.
11. Try a candidate that returns an HTTP error or blocks crawling in robots.txt. Confirm the failure is shown without crashing the application.

## 5. Safety checks

Automated tests cover private-address DNS rejection, redirect-to-loopback rejection, response-size limits, transient HTTP retries, conservative robots.txt handling, HTML extraction, and safe sitemap URL filtering.

Do not test against private services or attempt to bypass access controls. Use public documentation sites and keep request rates low.

## 6. Final checks

```powershell
git status --short
git log -1 --oneline
```

Report the complete Ruff and pytest output plus whether the GUI fetch and sitemap workflows succeeded. Do not commit unrelated local changes.
