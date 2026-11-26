from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dataset_forge.services.dataset_export import DatasetExportService
from dataset_forge.services.ai_providers import (
    RESEARCH_GENERATION_TIMEOUT_SECONDS,
    ProviderConfig,
    ProviderDiagnostic,
    ProviderKind,
    create_provider,
)
from dataset_forge.services.task_manager import TaskManager
from dataset_forge.storage.dataset_record_repository import DatasetRecordRepository
from dataset_forge.storage.knowledge_repository import KnowledgeRepository
from dataset_forge.storage.repositories import ProjectRepository, SettingsRepository
from dataset_forge.storage.research_repository import ResearchRepository
from dataset_forge.storage.source_content_repository import SourceContentRepository
from dataset_forge.ui.dataset_builder_page import DatasetBuilderPage
from dataset_forge.ui.knowledge_pool_page import KnowledgePoolPage
from dataset_forge.ui.research_page import ResearchPage
from dataset_forge.ui.sources_page import SourcesPage

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
        ("Research", "Plan research, approve scope, and manage candidate sources."),
        ("Sources", "Fetch approved public sources and inspect extracted content."),
        ("Knowledge Pool", "Review structured knowledge and its source provenance."),
        ("Dataset Builder", "Generate, inspect, and review source-grounded dataset records."),
        ("Generation", "Resumable generation workflows will arrive in Phase 6."),
        ("Quality Control", "Validation and review tools will arrive in Phase 7."),
        ("Projects & Export", "Manage projects and export accepted training records."),
        ("Settings", "Local application preferences and provider configuration."),
    ]

    PROVIDER_LABELS = {
        ProviderKind.OLLAMA: "Ollama",
        ProviderKind.LM_STUDIO: "LM Studio",
        ProviderKind.OPENAI_COMPATIBLE: "OpenAI-compatible",
    }
    PROVIDER_ENDPOINTS = {
        ProviderKind.OLLAMA: "http://localhost:11434",
        ProviderKind.LM_STUDIO: "http://localhost:1234",
        ProviderKind.OPENAI_COMPATIBLE: "https://api.openai.com",
    }

    def __init__(
        self,
        projects: ProjectRepository,
        settings: SettingsRepository,
    ) -> None:
        super().__init__()
        self.projects = projects
        self.settings = settings
        self.research_repository = ResearchRepository(projects.database)
        self.source_content_repository = SourceContentRepository(projects.database)
        self.knowledge_repository = KnowledgeRepository(projects.database)
        self.dataset_record_repository = DatasetRecordRepository(projects.database)
        self.task_manager = TaskManager(self)
        self.task_manager.task_succeeded.connect(self._provider_task_succeeded)
        self.task_manager.task_failed.connect(self._provider_task_failed)
        self.task_manager.task_finished.connect(self._provider_task_finished)
        self.current_project_id: str | None = None
        self.setWindowTitle("Dataset Forge AI")
        self.resize(1180, 760)
        self.setMinimumSize(900, 600)
        self._build_ui()
        self._refresh_projects()
        self._restore_project()
        self._load_provider_settings()
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
                page_layout.addSpacing(18)
                page_layout.addWidget(QLabel("Export accepted dataset records"))
                export_form = QFormLayout()
                self.export_format_combo = QComboBox()
                self.export_format_combo.addItem("Question & answer", "question_answer")
                self.export_format_combo.addItem(
                    "Instruction / input / output", "instruction"
                )
                self.export_format_combo.addItem("Conversation", "conversational")
                export_form.addRow("Dataset format", self.export_format_combo)
                self.export_provenance_check = QCheckBox(
                    "Write a separate provenance sidecar (.provenance.jsonl)"
                )
                self.export_provenance_check.setChecked(True)
                export_form.addRow("Provenance", self.export_provenance_check)
                page_layout.addLayout(export_form)
                export_button = QPushButton("Export accepted records")
                export_button.clicked.connect(self._export_dataset)
                page_layout.addWidget(export_button, alignment=Qt.AlignmentFlag.AlignLeft)
                self.export_status = QLabel(
                    "Exports include accepted records of the selected format only."
                )
                self.export_status.setObjectName("muted")
                self.export_status.setWordWrap(True)
                page_layout.addWidget(self.export_status)
            elif title == "Research":
                self.research_page = ResearchPage(
                    self.projects,
                    self.research_repository,
                    self.task_manager,
                    self._research_provider_config,
                )
                page_layout.addWidget(self.research_page)
            elif title == "Sources":
                self.sources_page = SourcesPage(
                    self.research_repository,
                    self.source_content_repository,
                    self.task_manager,
                )
                page_layout.addWidget(self.sources_page)
            elif title == "Knowledge Pool":
                self.knowledge_page = KnowledgePoolPage(
                    self.knowledge_repository,
                    self.source_content_repository,
                    self.task_manager,
                    self._research_provider_config,
                )
                page_layout.addWidget(self.knowledge_page)
            elif title == "Dataset Builder":
                self.dataset_builder_page = DatasetBuilderPage(
                    self.knowledge_repository,
                    self.dataset_record_repository,
                    self.task_manager,
                    self._research_provider_config,
                )
                page_layout.addWidget(self.dataset_builder_page)
            elif title == "Settings":
                self._build_settings_page(page_layout)
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
            QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QComboBox {
                background: #1c2430; border: 1px solid #344255;
                border-radius: 5px; padding: 7px;
            }
            #placeholder { color: #aab8c8; font-size: 16px; padding: 18px 0; }
            """
        )

    def _build_settings_page(self, layout: QVBoxLayout) -> None:
        layout.addWidget(QLabel("AI provider"))
        layout.addWidget(
            QLabel(
                "Connect a local model server or an OpenAI-compatible API. "
                "API keys are used only for the current session and are never saved."
            )
        )
        form = QFormLayout()
        self.provider_combo = QComboBox()
        for kind, label in self.PROVIDER_LABELS.items():
            self.provider_combo.addItem(label, kind.value)
        self.provider_combo.currentIndexChanged.connect(self._provider_defaults)
        form.addRow("Provider", self.provider_combo)

        self.endpoint_input = QLineEdit()
        self.endpoint_input.setPlaceholderText("http://localhost:11434")
        form.addRow("Endpoint", self.endpoint_input)

        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Optional API key (not saved)")
        form.addRow("API key", self.api_key_input)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        form.addRow("Default model", self.model_combo)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.test_provider_button = QPushButton("Test connection & discover models")
        self.test_provider_button.clicked.connect(self._test_provider_connection)
        actions.addWidget(self.test_provider_button)
        save_button = QPushButton("Save provider settings")
        save_button.clicked.connect(self._save_provider_settings)
        actions.addWidget(save_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.provider_status = QLabel("Provider connection has not been tested.")
        self.provider_status.setObjectName("muted")
        self.provider_status.setWordWrap(True)
        layout.addWidget(self.provider_status)
        layout.addStretch(1)

    def _research_provider_config(self) -> tuple[ProviderConfig, str]:
        try:
            kind = ProviderKind(self.provider_combo.currentData())
        except ValueError as exc:
            raise ValueError("Select an AI provider in Settings first.") from exc
        config = ProviderConfig(
            kind=kind,
            endpoint=self.endpoint_input.text().strip(),
            api_key=self.api_key_input.text(),
            timeout=RESEARCH_GENERATION_TIMEOUT_SECONDS,
        )
        model = self.model_combo.currentText().strip()
        if not model:
            raise ValueError("Select or enter a default model in Settings first.")
        return config, model

    def _provider_defaults(self, _index: int) -> None:
        try:
            kind = ProviderKind(self.provider_combo.currentData())
        except ValueError:
            return
        self.endpoint_input.setText(self.PROVIDER_ENDPOINTS[kind])

    def _load_provider_settings(self) -> None:
        raw_kind = self.settings.get("ai_provider", ProviderKind.OLLAMA.value)
        try:
            kind = ProviderKind(raw_kind)
        except ValueError:
            kind = ProviderKind.OLLAMA
        self.provider_combo.setCurrentIndex(self.provider_combo.findData(kind.value))
        endpoint = self.settings.get("ai_endpoint", self.PROVIDER_ENDPOINTS[kind])
        self.endpoint_input.setText(str(endpoint))
        model = self.settings.get("ai_model", "")
        if model:
            self.model_combo.setCurrentText(str(model))

    def _save_provider_settings(self) -> None:
        self.settings.set("ai_provider", self.provider_combo.currentData())
        self.settings.set("ai_endpoint", self.endpoint_input.text().strip())
        self.settings.set("ai_model", self.model_combo.currentText().strip())
        self.provider_status.setText(
            "Provider settings saved. The API key remains session-only."
        )

    def _test_provider_connection(self) -> None:
        try:
            kind = ProviderKind(self.provider_combo.currentData())
        except ValueError:
            self.provider_status.setText("Unsupported provider selection.")
            return
        endpoint = self.endpoint_input.text().strip()
        if not endpoint:
            self.provider_status.setText("Enter a provider endpoint first.")
            return
        config = ProviderConfig(
            kind=kind,
            endpoint=endpoint,
            api_key=self.api_key_input.text(),
        )
        self.provider_status.setText("Connecting and discovering models...")
        self.test_provider_button.setEnabled(False)
        try:
            self.task_manager.submit(
                "provider_diagnostic",
                lambda _context: create_provider(config).diagnose(),
            )
        except ValueError as exc:
            self.test_provider_button.setEnabled(True)
            self.provider_status.setText(str(exc))

    def _provider_task_succeeded(self, task_id: str, result: object) -> None:
        if task_id != "provider_diagnostic":
            return
        if not isinstance(result, ProviderDiagnostic):
            self.provider_status.setText("Provider returned an unexpected diagnostic.")
            return
        self.provider_status.setText(result.message)
        if result.success:
            current_model = self.model_combo.currentText()
            self.model_combo.clear()
            self.model_combo.addItems(list(result.models))
            if current_model:
                self.model_combo.setCurrentText(current_model)
            elif self.settings.get("ai_model", ""):
                self.model_combo.setCurrentText(str(self.settings.get("ai_model", "")))

    def _provider_task_failed(self, task_id: str, error: str) -> None:
        if task_id == "provider_diagnostic":
            self.provider_status.setText(f"Provider check failed: {error}")

    def _provider_task_finished(self, task_id: str) -> None:
        if task_id == "provider_diagnostic":
            self.test_provider_button.setEnabled(True)

    def _change_section(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        if index == 2 and self.current_project_id is not None:
            # Research can add or approve candidates while Sources is hidden.
            # Refresh on entry so the user never has to restart the application.
            self.sources_page.set_project(self.current_project_id)
        if index == 3 and self.current_project_id is not None:
            self.knowledge_page.set_project(self.current_project_id)
        if index == 4 and self.current_project_id is not None:
            self.dataset_builder_page.set_project(self.current_project_id)
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
                self.project_label.setText(f"OPEN PROJECT\n{project['name']}")
                self.research_page.set_project(project_id)
                self.sources_page.set_project(project_id)
                self.knowledge_page.set_project(project_id)
                self.dataset_builder_page.set_project(project_id)

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

    def _export_dataset(self) -> None:
        if self.current_project_id is None:
            self.export_status.setText("Open a project before exporting a dataset.")
            return
        dataset_type = self.export_format_combo.currentData()
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export accepted dataset",
            f"{dataset_type}.jsonl",
            "JSON Lines (*.jsonl)",
        )
        if not filename:
            return
        if not filename.casefold().endswith(".jsonl"):
            filename += ".jsonl"
        try:
            result = DatasetExportService(
                self.dataset_record_repository
            ).export_project(
                self.current_project_id,
                dataset_type,
                filename,
                include_provenance=self.export_provenance_check.isChecked(),
            )
        except (OSError, ValueError) as exc:
            self.export_status.setText(f"Export failed: {exc}")
            QMessageBox.warning(self, "Dataset export failed", str(exc))
            return
        message = (
            f"Exported {result['exported']} accepted record(s). "
            f"Skipped {result['skipped']} invalid record(s)."
        )
        if result["provenance_path"]:
            message += f"\nProvenance: {result['provenance_path']}"
        self.export_status.setText(f"{message}\nDataset: {result['path']}")
        QMessageBox.information(self, "Dataset export complete", message)

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
        self.research_page.set_project(project_id)
        self.sources_page.set_project(project_id)
        self.knowledge_page.set_project(project_id)
        self.dataset_builder_page.set_project(project_id)
        self.settings.set("last_project_id", project_id)
        self.navigation.setCurrentRow(0)
        LOGGER.info("Opened project %s", project_id)
