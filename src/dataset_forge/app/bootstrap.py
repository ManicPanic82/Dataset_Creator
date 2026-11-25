from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from dataset_forge import __version__
from dataset_forge.app.config import AppPaths
from dataset_forge.app.logging_config import configure_logging
from dataset_forge.storage.database import Database
from dataset_forge.storage.repositories import ProjectRepository, SettingsRepository
from dataset_forge.ui.main_window import MainWindow


def main() -> int:
    paths = AppPaths.from_environment()
    paths.ensure_directories()
    configure_logging(paths.logs)
    logger = logging.getLogger(__name__)
    logger.info("Starting Dataset Forge AI %s", __version__)

    database = Database(paths.database)
    database.initialise()

    application = QApplication(sys.argv)
    application.setApplicationName("Dataset Forge AI")
    application.setOrganizationName("DatasetForgeAI")
    window = MainWindow(
        ProjectRepository(database),
        SettingsRepository(database),
    )
    window.show()
    result = application.exec()
    logger.info("Application closed with exit code %s", result)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
