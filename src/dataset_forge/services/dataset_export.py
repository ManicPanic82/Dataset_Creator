from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from dataset_forge.storage.dataset_record_repository import (
    DATASET_TYPES,
    DatasetRecordRepository,
    is_valid_dataset_payload,
)


class DatasetExportService:
    """Export accepted records as JSONL, with optional provenance sidecar."""

    def __init__(self, record_repository: DatasetRecordRepository) -> None:
        self.record_repository = record_repository

    @staticmethod
    def _valid_payload(dataset_type: str, payload: Any) -> bool:
        return is_valid_dataset_payload(dataset_type, payload)

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

    def export_splits(
        self,
        project_id: str,
        dataset_type: str,
        output_directory: str | Path,
        *,
        train_ratio: float = 0.8,
        validation_ratio: float = 0.1,
        test_ratio: float = 0.1,
        seed: int = 42,
        include_provenance: bool = True,
    ) -> dict[str, Any]:
        """Write reproducible accepted-record train/validation/test JSONL files."""
        ratios = (train_ratio, validation_ratio, test_ratio)
        if any(not isinstance(ratio, (int, float)) or ratio <= 0 for ratio in ratios):
            raise ValueError("Split ratios must all be positive numbers.")
        if abs(sum(ratios) - 1.0) > 1e-6:
            raise ValueError("Split ratios must sum to 1.0.")
        if dataset_type not in DATASET_TYPES:
            raise ValueError("Choose a supported dataset format.")

        import random

        records = self.record_repository.list_for_project(
            project_id, review_status="accepted"
        )
        matching = [
            record for record in records
            if record["dataset_type"] == dataset_type
            and self._valid_payload(dataset_type, record.get("payload"))
        ]
        skipped = sum(
            1 for record in records
            if record["dataset_type"] == dataset_type
            and not self._valid_payload(dataset_type, record.get("payload"))
        )
        shuffled = list(matching)
        random.Random(seed).shuffle(shuffled)
        total = len(shuffled)
        train_end = int(total * train_ratio)
        validation_end = train_end + int(total * validation_ratio)
        partitions = {
            "train": shuffled[:train_end],
            "validation": shuffled[train_end:validation_end],
            "test": shuffled[validation_end:],
        }

        directory = Path(output_directory).expanduser()
        directory.mkdir(parents=True, exist_ok=True)
        results: dict[str, Any] = {}
        for name, partition in partitions.items():
            destination = directory / f"{name}.jsonl"
            payload_lines = [
                json.dumps(record["payload"], ensure_ascii=False)
                for record in partition
            ]
            self._write_atomic(destination, payload_lines)
            sidecar_path = None
            if include_provenance:
                sidecar_path = directory / f"{name}.provenance.jsonl"
                provenance_lines = [
                    json.dumps(
                        {
                            "record_id": record["id"],
                            "dataset_type": dataset_type,
                            "provenance": record["provenance"],
                        },
                        ensure_ascii=False,
                    )
                    for record in partition
                ]
                self._write_atomic(sidecar_path, provenance_lines)
            results[name] = {
                "count": len(partition),
                "path": str(destination),
                "provenance_path": str(sidecar_path) if sidecar_path else None,
            }
        results.update({
            "seed": seed,
            "skipped": skipped,
            "available": len(matching),
            "ratios": {"train": train_ratio, "validation": validation_ratio, "test": test_ratio},
        })
        return results

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
