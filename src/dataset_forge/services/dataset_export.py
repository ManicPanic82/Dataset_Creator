from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dataset_forge.storage.dataset_record_repository import (
    DATASET_TYPES,
    DatasetRecordRepository,
    is_valid_dataset_payload,
)

SPLIT_PROFILES = {
    "standard": {"train": 0.8, "validation": 0.1, "test": 0.1},
    "training_heavy": {"train": 0.9, "validation": 0.05, "test": 0.05},
    "balanced": {"train": 0.7, "validation": 0.15, "test": 0.15},
}


class DatasetExportService:
    """Export accepted records as JSONL, with optional provenance sidecar."""

    def __init__(self, record_repository: DatasetRecordRepository) -> None:
        self.record_repository = record_repository

    @staticmethod
    def _valid_payload(dataset_type: str, payload: Any) -> bool:
        return is_valid_dataset_payload(dataset_type, payload)

    @staticmethod
    def _deduplicate_records(
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], int]:
        """Keep the first occurrence of each exact payload without mutating records."""
        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        duplicates = 0
        # Repository listings are newest-first; sort chronologically so the
        # earliest accepted record is retained with its original provenance.
        ordered_records = sorted(
            records,
            key=lambda record: (record.get("created_at", ""), record["id"]),
        )
        for record in ordered_records:
            key = json.dumps(
                record["payload"],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            unique.append(record)
        return unique, duplicates

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

    @staticmethod
    def _write_manifest(path: Path, manifest: dict[str, Any]) -> str:
        """Write a UTF-8 JSON audit manifest beside the exported dataset."""
        DatasetExportService._write_atomic(
            path, [json.dumps(manifest, ensure_ascii=False, indent=2)]
        )
        return str(path)

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
        split_profile: str = "custom",
        include_provenance: bool = True,
        deduplicate: bool = False,
    ) -> dict[str, Any]:
        """Write reproducible accepted-record train/validation/test JSONL files."""
        ratios = (train_ratio, validation_ratio, test_ratio)
        if any(
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(ratio)
            or ratio <= 0
            for ratio in ratios
        ):
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
        duplicates = 0
        if deduplicate:
            matching, duplicates = self._deduplicate_records(matching)
        # Group records transitively by shared accepted knowledge IDs to reduce leakage.
        parents = {record["id"]: record["id"] for record in matching}
        def find(record_id: str) -> str:
            while parents[record_id] != record_id:
                parents[record_id] = parents[parents[record_id]]
                record_id = parents[record_id]
            return record_id
        def union(left: str, right: str) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parents[right_root] = left_root
        owners: dict[str, str] = {}
        for record in matching:
            for item in record.get("provenance", []):
                knowledge_id = item.get("knowledge_id")
                if not knowledge_id:
                    continue
                if knowledge_id in owners:
                    union(record["id"], owners[knowledge_id])
                else:
                    owners[knowledge_id] = record["id"]
        groups: dict[str, list[dict[str, Any]]] = {}
        for record in matching:
            groups.setdefault(find(record["id"]), []).append(record)
        group_list = list(groups.values())
        random.Random(seed).shuffle(group_list)
        targets = {"train": len(matching) * train_ratio,
                   "validation": len(matching) * validation_ratio,
                   "test": len(matching) * test_ratio}
        partitions: dict[str, list[dict[str, Any]]] = {
            "train": [], "validation": [], "test": []}
        # Assign each whole group to the split with the largest proportional deficit.
        for group in group_list:
            name = max(partitions, key=lambda key:
                       (targets[key] - len(partitions[key])) / targets[key])
            partitions[name].extend(group)
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
            "duplicates_removed": duplicates,
            "available": len(matching) + duplicates,
            "groups": len(group_list),
            "ratios": {"train": train_ratio, "validation": validation_ratio, "test": test_ratio},
        })
        manifest_path = directory / "export.manifest.json"
        manifest = {
            "manifest_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "dataset_type": dataset_type,
            "export_mode": "train_validation_test",
            "split_profile": split_profile,
            "available_accepted_records": len(matching) + duplicates,
            "exported_records": sum(
                results[name]["count"] for name in ("train", "validation", "test")
            ),
            "skipped_invalid_records": skipped,
            "duplicates_removed": duplicates,
            "deduplicate_exact": deduplicate,
            "include_provenance": include_provenance,
            "seed": seed,
            "ratios": results["ratios"],
            "leakage_groups": len(group_list),
            "splits": {
                name: {
                    "count": results[name]["count"],
                    "dataset_file": Path(results[name]["path"]).name,
                    "provenance_file": (
                        Path(results[name]["provenance_path"]).name
                        if results[name]["provenance_path"] else None
                    ),
                }
                for name in ("train", "validation", "test")
            },
        }
        results["manifest_path"] = self._write_manifest(manifest_path, manifest)
        return results

    def export_project(
        self,
        project_id: str,
        dataset_type: str,
        output_path: str | Path,
        *,
        include_provenance: bool = True,
        deduplicate: bool = False,
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
        duplicates = 0
        if deduplicate:
            valid_matching = [
                record for record in matching
                if self._valid_payload(dataset_type, record.get("payload"))
            ]
            unique, duplicates = self._deduplicate_records(valid_matching)
            unique_ids = {record["id"] for record in unique}
            matching = [
                record for record in matching
                if not self._valid_payload(dataset_type, record.get("payload"))
                or record["id"] in unique_ids
            ]
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

        result = {
            "exported": len(exported),
            "skipped": skipped,
            "duplicates_removed": duplicates,
            "available": len(matching) + duplicates,
            "path": str(destination),
            "provenance_path": str(sidecar_path) if sidecar_path else None,
        }
        manifest_path = destination.with_name(f"{destination.stem}.manifest.json")
        manifest = {
            "manifest_version": 1,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "project_id": project_id,
            "dataset_type": dataset_type,
            "export_mode": "single_file",
            "available_accepted_records": result["available"],
            "exported_records": result["exported"],
            "skipped_invalid_records": skipped,
            "duplicates_removed": duplicates,
            "deduplicate_exact": deduplicate,
            "include_provenance": include_provenance,
            "dataset_file": destination.name,
            "provenance_file": sidecar_path.name if sidecar_path else None,
        }
        result["manifest_path"] = self._write_manifest(manifest_path, manifest)
        return result
