from dataset_forge.storage.database import Database
from dataset_forge.storage.repositories import ProjectRepository, SettingsRepository


def test_project_create_list_and_status(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()
    projects = ProjectRepository(database)

    created = projects.create("  Python data  ", "  debugging  ")

    assert created["name"] == "Python data"
    assert created["description"] == "debugging"
    assert projects.get(created["id"])["status"] == "active"
    projects.update_status(created["id"], "archived")
    assert projects.list_all()[0]["status"] == "archived"


def test_project_name_must_not_be_empty(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()

    try:
        ProjectRepository(database).create("   ")
    except ValueError as exc:
        assert "cannot be empty" in str(exc)
    else:
        raise AssertionError("Expected empty project name to be rejected")


def test_settings_round_trip_and_default(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()
    settings = SettingsRepository(database)

    settings.set("last_section", 3)
    settings.set("filters", {"domains": ["python.org"], "enabled": True})

    assert settings.get("last_section") == 3
    assert settings.get("filters") == {"domains": ["python.org"], "enabled": True}
    assert settings.get("missing", "fallback") == "fallback"


def test_database_initialisation_is_repeatable(tmp_path):
    database = Database(tmp_path / "app.sqlite3")
    database.initialise()
    database.initialise()
    assert database.path.exists()
