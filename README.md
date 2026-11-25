# Dataset Forge AI

A Windows-first, local-first desktop application for researching, creating, validating and exporting AI training datasets.

The project is being developed in small phases. The current development branch builds on the desktop foundation, AI providers and research planning, and introduces the first bounded crawler and source-extraction workflow. See `docs/PROJECT_VISION_AND_ROADMAP.md` and `docs/PHASE_4.md` for scope and safety boundaries.

## Requirements

- Windows 10 or later
- Python 3.12 (64-bit)
- PowerShell 7 recommended (Windows PowerShell 5.1 should also work)
- Internet access only for installing Python dependencies

## Setup

Run these commands from the repository root in PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

If PowerShell blocks activation, use the virtual environment's interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

## Run

```powershell
.\.venv\Scripts\python.exe .\main.py
```

Or, after installation:

```powershell
dataset-forge
```

## Validate

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff check .
```

## Local data

Application data is stored under the current user's Windows application-data directory:

`%LOCALAPPDATA%\DatasetForgeAI\`

The SQLite database and rotating application log are created on first launch. Project records are stored in SQLite; project working directories are created under the same application-data root.

## Current workflow

- Create a project and generate, edit, save and approve a research plan.
- Import public HTTP/HTTPS URL candidates and review them.
- Accept a candidate in Research before fetching it from Sources.
- Fetch public HTML with bounded redirects, DNS checks, robots.txt handling, streamed response-size limits and per-host delays.
- Extract page title, readable text, links and a content hash without executing JavaScript.
- Parse XML sitemaps and follow links only within explicitly supplied crawl origins.
- Persist extracted source snapshots and provenance for later review.

The crawler is intentionally conservative and currently processes requests sequentially. It does not bypass authentication, paywalls, CAPTCHAs or website restrictions. Review `docs/PHASE_4.md` for the DNS-rebinding limitation that remains before production-grade crawling.
