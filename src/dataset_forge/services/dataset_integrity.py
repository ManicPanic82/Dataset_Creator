from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class DatasetIntegrityService:
    """Verify exported dataset files against their audit manifest."""

    @staticmethod
    def verify_manifest(manifest_path: str | Path) -> dict[str, Any]:
        manifest_file = Path(manifest_path).expanduser()
        errors: list[str] = []
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return {
                "success": False,
                "errors": [f"Cannot read manifest: {exc}"],
                "checked_files": 0,
                "total_records": 0,
            }

        if not isinstance(manifest, dict) or manifest.get("manifest_version") != 1:
            return {
                "success": False,
                "errors": ["Unsupported or malformed manifest version."],
                "checked_files": 0,
                "total_records": 0,
            }

        files = manifest.get("files")
        if not isinstance(files, dict) or not files:
            return {
                "success": False,
                "errors": ["Manifest has no file integrity entries."],
                "checked_files": 0,
                "total_records": 0,
            }

        checked_files = 0
        total_records = 0
        base_directory = manifest_file.parent.resolve()
        for filename, expected in files.items():
            if (
                not isinstance(filename, str)
                or not filename
                or Path(filename).name != filename
                or not isinstance(expected, dict)
            ):
                errors.append(f"Invalid file entry: {filename!r}")
                continue
            target = manifest_file.parent / filename
            try:
                resolved = target.resolve(strict=True)
                if resolved.parent != base_directory:
                    errors.append(f"{filename}: file resolves outside the export directory.")
                    continue
                raw = resolved.read_bytes()
            except OSError:
                errors.append(f"{filename}: file is missing or unreadable.")
                continue

            checked_files += 1
            actual_hash = hashlib.sha256(raw).hexdigest()
            if actual_hash != expected.get("sha256"):
                errors.append(f"{filename}: SHA-256 mismatch.")
            try:
                text = raw.decode("utf-8")
                rows = [line for line in text.splitlines() if line.strip()]
                for row_number, line in enumerate(rows, start=1):
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise ValueError(f"line {row_number} is not a JSON object")
            except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
                errors.append(f"{filename}: invalid JSONL content ({exc}).")
                continue

            actual_count = len(rows)
            if actual_count != expected.get("records"):
                errors.append(
                    f"{filename}: expected {expected.get('records')} record(s), "
                    f"found {actual_count}."
                )
            total_records += actual_count

        if checked_files != len(files):
            errors.append("One or more manifest files could not be checked.")
        expected_total = manifest.get("exported_records")
        dataset_entries = [
            entry for name, entry in files.items()
            if isinstance(entry, dict) and not name.endswith(".provenance.jsonl")
        ]
        if isinstance(expected_total, int) and sum(
            entry.get("records", -1) for entry in dataset_entries
        ) != expected_total:
            errors.append("Manifest dataset file counts do not match exported_records.")

        return {
            "success": not errors,
            "errors": errors,
            "checked_files": checked_files,
            "total_records": total_records,
        }
