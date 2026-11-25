# Dataset Forge AI

A Windows-first, local-first desktop application for researching, creating, validating and exporting AI training datasets.

The project is being developed in small phases. This branch contains the **Phase 1 desktop foundation**: the native desktop shell, local project persistence, SQLite storage, settings, logging and a cancellable background-task framework. Research, crawling and AI generation are intentionally not implemented yet.

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

## Phase 1 scope

- Native PySide6 main window and primary navigation.
- Project creation, opening and persistent project metadata.
- SQLite database initialisation with a schema version.
- Persistent application settings.
- Rotating structured log output.
- Background task runner with progress reporting and cancellation.
- Unit tests for storage, projects, settings and task cancellation.

No network crawling, AI provider calls or dataset generation occurs in this phase.
