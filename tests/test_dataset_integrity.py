import hashlib
import json

from dataset_forge.services.dataset_integrity import DatasetIntegrityService


def _write_manifest(tmp_path, files):
    rows = {
        "dataset.jsonl": '{"question": "Why?", "answer": "Because."}\n',
        "dataset.provenance.jsonl": '{"record_id": "r1", "provenance": []}\n',
    }
    entries = {}
    for filename, raw in rows.items():
        if filename not in files:
            continue
        path = tmp_path / filename
        path.write_text(raw, encoding="utf-8")
        entries[filename] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "records": 1,
            "kind": "provenance" if "provenance" in filename else "dataset",
        }
    manifest = {
        "manifest_version": 1,
        "export_mode": "single_file",
        "exported_records": 1,
        "files": entries,
    }
    manifest_path = tmp_path / "dataset.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_verify_manifest_accepts_unchanged_dataset_and_provenance(tmp_path):
    manifest = _write_manifest(
        tmp_path, {"dataset.jsonl", "dataset.provenance.jsonl"}
    )

    result = DatasetIntegrityService.verify_manifest(manifest)

    assert result == {
        "success": True,
        "errors": [],
        "checked_files": 2,
        "total_records": 2,
    }


def test_verify_manifest_detects_modified_export_file(tmp_path):
    manifest = _write_manifest(tmp_path, {"dataset.jsonl"})
    (tmp_path / "dataset.jsonl").write_text(
        '{"question": "Changed?", "answer": "Changed."}\n', encoding="utf-8"
    )

    result = DatasetIntegrityService.verify_manifest(manifest)

    assert result["success"] is False
    assert any("SHA-256 mismatch" in error for error in result["errors"])


def test_verify_manifest_detects_invalid_jsonl(tmp_path):
    manifest = _write_manifest(tmp_path, {"dataset.jsonl"})
    dataset = tmp_path / "dataset.jsonl"
    dataset.write_text("not-json\n", encoding="utf-8")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["files"]["dataset.jsonl"]["sha256"] = hashlib.sha256(
        dataset.read_bytes()
    ).hexdigest()
    manifest.write_text(json.dumps(data), encoding="utf-8")

    result = DatasetIntegrityService.verify_manifest(manifest)

    assert result["success"] is False
    assert any("invalid JSONL content" in error for error in result["errors"])


def test_verify_manifest_detects_missing_file(tmp_path):
    manifest = _write_manifest(tmp_path, {"dataset.jsonl"})
    (tmp_path / "dataset.jsonl").unlink()

    result = DatasetIntegrityService.verify_manifest(manifest)

    assert result["success"] is False
    assert any("missing or unreadable" in error for error in result["errors"])


def test_verify_manifest_rejects_path_traversal_entries(tmp_path):
    manifest = tmp_path / "dataset.manifest.json"
    manifest.write_text(
        json.dumps({
            "manifest_version": 1,
            "exported_records": 0,
            "files": {"../outside.jsonl": {"sha256": "x", "records": 0}},
        }),
        encoding="utf-8",
    )

    result = DatasetIntegrityService.verify_manifest(manifest)

    assert result["success"] is False
    assert any("Invalid file entry" in error for error in result["errors"])


def test_verify_manifest_rejects_unknown_manifest_version(tmp_path):
    manifest = tmp_path / "dataset.manifest.json"
    manifest.write_text(
        json.dumps({"manifest_version": 99, "files": {}}), encoding="utf-8"
    )

    result = DatasetIntegrityService.verify_manifest(manifest)

    assert result["success"] is False
    assert "Unsupported or malformed manifest version." in result["errors"]


def test_verify_manifest_rejects_malformed_integrity_metadata(tmp_path):
    manifest = tmp_path / "dataset.manifest.json"
    manifest.write_text(
        json.dumps({
            "manifest_version": 1,
            "exported_records": 1,
            "files": {
                "dataset.jsonl": {
                    "sha256": "not-a-hash",
                    "records": "one",
                }
            },
        }),
        encoding="utf-8",
    )

    result = DatasetIntegrityService.verify_manifest(manifest)

    assert result["success"] is False
    assert any("invalid integrity metadata" in error for error in result["errors"])
