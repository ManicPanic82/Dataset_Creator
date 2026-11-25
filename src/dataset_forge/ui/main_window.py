from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,\n    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,\n    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dataset_forge.services.ai_providers import ProviderConfig, ProviderKind, create_provider\nfrom dataset_forge.services.task_manager import TaskManager
from dataset_forge.storage.repositories import ProjectRepository, SettingsRepository

LOGGER = logging.getLogger(__name__)


class NewProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create project")
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. Python debugging dataset")
        self.description_input = QTextEdit()
        self.description_input.setPlaceholderText("Optional project notes")
        self.description_input.setFixedHeight(90)
        layout = QFormLayout(self)
        layout.addRow("Project name", self.name_input)
        layout.addRow("Description", self.description_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def project_details(self) -> tuple[str, str]:
        return self.name_input.text(), self.description_input.toPlainText()


class MainWindow(QMainWindow):
    SECTIONS = [
        ("Overview", "Your research-to-dataset workspace."),
        ("Research", "Research planning will be added in Phase 3."),
        ("Sources", "Source discovery and extraction will be added in Phase 3 and 4."),
        ("Dataset Builder", "Dataset schemas and generation controls will arrive in Phase 6."),
        ("Generation", "Resumable generation workflows will arrive in Phase 6."),
        ("Quality Control", "Validation and review tools will arrive in Phase 7."),
        ("Projects & Export", "Manage projects now. Dataset export arrives in Phase 8."),
        ("Settings", "Local application preferences and provider configuration."),
    ]

    def __init__(
        self,
        projects: ProjectRepository,
        settings: SettingsRepository,
    ) -> None:
        super().__init__()
        self.projects = projects
        self.settings = settings
        self.task_manager = TaskManager(self)
        self.current_project_id: str | None = None
        self.setWindowTitle("Dataset Forge AI")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self._build_ui()
        self._refresh_projects()
        self._restore_project()
        self._restore_section()

    def _build_ui(self) -> None:
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)
        side_layout = QVBoxLayout(sidebar)
        brand = QLabel("DATASET FORGE")
        brand.setObjectName("brand")
        side_layout.addWidget(brand)
        self.project_label = QLabel("No project open")
        self.project_label.setObjectName("projectLabel")
        self.project_label.setWordWrap(True)
        side_layout.addWidget(self.project_label)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        for title, _ in self.SECTIONS:
            self.navigation.addItem(title)
        self.navigation.currentRowChanged.connect(self._change_section)
        side_layout.addWidget(self.navigation, 1)

        new_button = QPushButton("+  New project")
        new_button.clicked.connect(self._create_project)
        side_layout.addWidget(new_button)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(30, 24, 30, 24)
        self.section_title = QLabel("Overview")
        self.section_title.setObjectName("sectionTitle")
        content_layout.addWidget(self.section_title)
        self.section_description = QLabel()
        self.section_description.setObjectName("muted")
        content_layout.addWidget(self.section_description)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack, 1)

        for title, description in self.SECTIONS:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            if title == "Overview":
                self.project_list = QListWidget()
                self.project_list.itemDoubleClicked.connect(self._open_selected_project)
                page_layout.addWidget(QLabel("Recent projects"))
                page_layout.addWidget(self.project_list, 1)
                row = QHBoxLayout()
                open_button = QPushButton("Open selected")
                open_button.clicked.connect(self._open_selected_project)
                row.addWidget(open_button)
                row.addStretch(1)
                page_layout.addLayout(row)
            elif title == "Projects & Export":
                self.project_management_list = QListWidget()
                self.project_management_list.itemDoubleClicked.connect(
                    self._open_managed_project
                )
                page_layout.addWidget(QLabel("Saved projects"))
                page_layout.addWidget(self.project_management_list, 1)
                create_button = QPushButton("Create project")
                create_button.clicked.connect(self._create_project)
                page_layout.addWidget(create_button, alignment=Qt.AlignmentFlag.AlignLeft)
            elif title == "Settings":
                page_layout.addWidget(QLabel("Application data is stored locally."))
                page_layout.addWidget(QLabel("AI provider settings will be introduced in Phase 2."))
                page_layout.addStretch(1)
            else:
                placeholder = QLabel(description)
                placeholder.setObjectName("placeholder")
                placeholder.setWordWrap(True)
                page_layout.addWidget(placeholder)
                page_layout.addStretch(1)
            self.stack.addWidget(page)

        root.addWidget(sidebar)
        root.addWidget(content, 1)
        self.setCentralWidget(central)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #151a22; color: #e8edf5; }
            #sidebar { background: #10151c; border-right: 1px solid #293241; }
            #brand { color: #7db7ff; font-size: 17px; font-weight: 800; padding: 12px 4px; }
            #projectLabel, #muted { color: #9ba9ba; }
            #sectionTitle { font-size: 27px; font-weight: 700; }
            #navigation { background: transparent; border: 0; outline: 0; padding: 6px; }
            #navigation::item { padding: 11px 10px; border-radius: 6px; }
            #navigation::item:selected { background: #263b55; color: #ffffff; }
            QPushButton { background: #285b91; border: 0; border-radius: 6px;
                          padding: 9px 13px; color: white; }
            QPushButton:hover { background: #3476b8; }
            QLineEdit, QTextEdit, QListWidget { background: #1c2430;
                          border: 1px solid #344255; border-radius: 5px; padding: 7px; }
            #placeholder { color: #aab8c8; font-size: 16px; padding: 18px 0; }
            """
        )

    def _provider_defaults(self, index: int) -> None:
        kind = self.provider_combo.currentData()
        if kind == ProviderKind.OLLAMA.value:
            self.endpoint_input.setText("http://localhost:11434")
        elif kind == ProviderKind.LM_STUDIO.value:
            self.endpoint_input.setText("http://localhost:1234")
        else:
            if not self.endpoint_input.text().startswith("http"):
                self.endpoint_input.setText("https://api.openai.com")

    def _load_provider_settings(self) -> None:
        kind = self.settings.get("ai_provider", ProviderKind.OLLAMA.value)
        index = self.provider_combo.findData(kind)
        if index >= 0:
            self.provider_combo.setCurrentIndex(index)
        defaults = {
            ProviderKind.OLLAMA.value: "http://localhost:11434",
            ProviderKind.LM_STUDIO.value: "http://localhost:1234",
            ProviderKind.OPENAI_COMPATIBLE.value: "https://api.openai.com",
        }
        self.endpoint_input.setText(self.settings.get("ai_endpoint", defaults.get(kind, "")))
        model = self.settings.get("ai_model", "")
        if model:
            self.model_combo.setCurrentText(model)

    def _save_provider_settings(self) -> None:
        self.settings.set("ai_provider", self.provider_combo.currentData())
        self.settings.set("ai_endpoint", self.endpoint_input.text().strip())
        self.settings.set("ai_model", self.model_combo.currentText().strip())
        self.provider_status.setText("Provider settings saved. API key is not stored.")

    def _test_provider_connection(self) -> None:
        try:
            kind = ProviderKind(self.provider_combo.currentData())
        except ValueError:
            self.provider_status.setText("Unsupported provider selection.")
            return
        config = ProviderConfig(
            kind=kind,
            endpoint=self.endpoint_input.text().strip(),
            api_key=self.api_key_input.text(),
        )
        self.provider_status.setText("Connecting...")
        self.task_manager.task_succeeded.connect(self._provider_task_succeeded)
        self.task_manager.task_failed.connect(self._provider_task_failed)
        self.task_manager.submit("provider_diagnostic", lambda _context: create_provider(config).diagnose())

    def _provider_task_succeeded(self, task_id: str, result: object) -> None:
        if task_id != "provider_diagnostic":
            return
        self.provider_status.setText(result.message)
        self.model_combo.clear()
        self.model_combo.addItems(list(result.models))
        saved_model = self.settings.get("ai_model", "")
        if saved_model:
            self.model_combo.setCurrentText(saved_model)

    def _provider_task_failed(self, task_id: str, error: str) -> None:
        if task_id == "provider_diagnostic":
            self.provider_status.setText(error)

    def _change_section(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        title, description = self.SECTIONS[index]
        self.section_title.setText(title)
        self.section_description.setText(description)
        self.settings.set("last_section", index)

    def _restore_project(self) -> None:
        project_id = self.settings.get("last_project_id")
        if isinstance(project_id, str):
            project = self.projects.get(project_id)
            if project is not None:
                self.current_project_id = project_id
                self.project_label.setText(f"OPEN PROJECT\\n{project['name']}")

    def closeEvent(self, event) -> None:
        self.task_manager.shutdown()
        super().closeEvent(event)

    def _restore_section(self) -> None:
        index = self.settings.get("last_section", 0)
        if not isinstance(index, int) or not 0 <= index < len(self.SECTIONS):
            index = 0
        self.navigation.setCurrentRow(index)

    def _refresh_projects(self) -> None:
        records = self.projects.list_all()
        self.project_list.clear()
        self.project_management_list.clear()
        for project in records:
            label = f"{project['name']}  ·  {project['status']}"
            self.project_list.addItem(label)
            self.project_list.item(self.project_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, project["id"]
            )
            self.project_management_list.addItem(label)
            self.project_management_list.item(
                self.project_management_list.count() - 1
            ).setData(Qt.ItemDataRole.UserRole, project["id"])

    def _create_project(self) -> None:
        dialog = NewProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name, description = dialog.project_details
        try:
            project = self.projects.create(name, description)
        except ValueError as exc:
            QMessageBox.warning(self, "Project not created", str(exc))
            return
        self._refresh_projects()
        self._set_current_project(project["id"])

    def _open_selected_project(self, *_args: object) -> None:
        item = self.project_list.currentItem()
        if item is not None:
            self._set_current_project(item.data(Qt.ItemDataRole.UserRole))

    def _open_managed_project(self, *_args: object) -> None:
        item = self.project_management_list.currentItem()
        if item is not None:
            self._set_current_project(item.data(Qt.ItemDataRole.UserRole))

    def _set_current_project(self, project_id: str) -> None:
        project = self.projects.get(project_id)
        if project is None:
            QMessageBox.warning(self, "Project unavailable", "This project no longer exists.")
            self._refresh_projects()
            return
        self.current_project_id = project_id
        self.project_label.setText(f"OPEN PROJECT\n{project['name']}")
        self.settings.set("last_project_id", project_id)
        self.navigation.setCurrentRow(0)
        LOGGER.info("Opened project %s", project_id)
