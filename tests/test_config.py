from dataset_forge.app.config import AppPaths


def test_paths_use_local_app_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    paths = AppPaths.from_environment()

    assert paths.root == tmp_path / "DatasetForgeAI"
    paths.ensure_directories()
    assert paths.database.parent.exists()
    assert paths.logs.exists()
    assert paths.projects.exists()
    assert paths.exports.exists()
