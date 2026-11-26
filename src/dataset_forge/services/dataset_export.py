from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from dataset_forge.storage.dataset_record_repository import (
    DATASET_TYPES,
    DatasetRecordRepository,
)


class DatasetExportService:
    """Export accepted records as JSONL, with optional provenance sidecar."""

    def __init__(self, record_repository: DatasetRecordRepository) -> None:
        self.record_repository = record_repository

    @staticmethod
    def _valid_payload(dataset_type: str, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False
        if dataset_type == "instruction":
            return (
                set(payload) == {"instruction", "input", "output"}
                and isinstance(payload["instruction"], str)
                and bool(payload["instruction"].strip())
                and isinstance(payload["input"], str)
                and isinstance(payload["output"], str)
                and bool(payload["output"].strip())
            )
        if dataset_type == "question_answer":
            return (
                set(payload) == {"question", "answer"}
                and all(
                    isinstance(payload[key], str) and bool(payload[key].strip())
                    for key in ("question", "answer")
                )
            )
        if dataset_type == "conversational":
            messages = payload.get("messages")
            if set(payload) != {"messages"} or not isinstance(messages, list):
                return False
            if not 2 <= len(messages) <= 6:
                return False
            expected_roles = ["user", "assistant"] * 3
            return (
                all(
                    isinstance(message, dict)
                    and set(message) == {"role", "content"}
                    and message["role"] == expected_roles[index]
                    and isinstance(message["content"], str)
                    and bool(message["content"].strip())
                    for index, message in enumerate(messages)
                )
                and messages[-1]["role"] == "assistant"
            )
        return False

    @staticmethod
    def _write_atomic(path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_path = Path(handle.name)
                for line in lines:
                    handle.write(line)
                    handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            temporary_path.replace(path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()

    def export_project(
        self,
        project_id: str,
        dataset_type: str,
        output_path: str | Path,
        *,
        include_provenance: bool = True,
    ) -> dict[str, Any]:
        if dataset_type not in DATASET_TYPES:
            raise ValueError("Choose a supported dataset format.")
        destination = Path(output_path).expanduser()
        if destination.suffix.casefold() != ".jsonl":
            raise ValueError("Dataset export path must use the .jsonl extension.")

        records = self.record_repository.list_for_project(
            project_id, review_status="accepted"
        )
        matching = [record for record in records if record["dataset_type"] == dataset_type]
        exported: list[str] = []
        provenance_lines: list[str] = []
        skipped = 0
        for record in matching:
            payload = record.get("payload")
            if not self._valid_payload(dataset_type, payload):
                skipped += 1
                continue
            exported.append(json.dumps(payload, ensure_ascii=False))
            if include_provenance:
                provenance_lines.append(
                    json.dumps(
                        {
                            "record_id": record["id"],
                            "dataset_type": dataset_type,
                            "provenance": record["provenance"],
                        },
                        ensure_ascii=False,
                    )
                )

        self._write_atomic(destination, exported)
        sidecar_path: Path | None = None
        if include_provenance:
            sidecar_path = destination.with_name(
                f"{destination.stem}.provenance.jsonl"
            )
            self._write_atomic(sidecar_path, provenance_lines)

        return {
            "exported": len(exported),
            "skipped": skipped,
            "available": len(matching),
            "path": str(destination),
            "provenance_path": str(sidecar_path) if sidecar_path else None,
        }
