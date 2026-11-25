from __future__ import annotations

import json
import logging
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from dataset_forge.services.ai_providers import create_provider
from dataset_forge.services.research import (
    DomainFilter,
    ResearchPlan,
    import_url_candidates,
)
from dataset_forge.services.research_planner import ResearchPlanner
from dataset_forge.services.task_manager import TaskManager
from dataset_forge.storage.repositories import ProjectRepository
from dataset_forge.storage.research_repository import ResearchRepository

LOGGER = logging.getLogger(__name__)


class ResearchPage(QWidget):
    def __init__(
        self,
        projects: ProjectRepository,
        research: ResearchRepository,
        task_manager: TaskManager,
        provider_config_getter,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.projects = projects
        self.research = research
        self.task_manager = task_manager
        self.provider_config_getter = provider_config_getter
        self.project_id: str | None = None
        self._pending_project_id: str | None = None
        self._build_ui()
        self.task_manager.task_succeeded.connect(self._task_succeeded)
        self.task_manager.task_failed.connect(self._task_failed)
        self.task_manager.task_finished.connect(self._task_finished)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Research objective"))
        self.prompt_input = QPlainTextEdit()
        self.prompt_input.setPlaceholderText(
            "Describe what the dataset should teach and what sources should be researched..."
        )
        self.prompt_input.setMaximumHeight(100)
        layout.addWidget(self.prompt_input)

        actions = QHBoxLayout()
        self.generate_button = QPushButton("Generate research plan")
        self.generate_button.clicked.connect(self._generate_plan)
        actions.addWidget(self.generate_button)
        self.save_button = QPushButton("Save draft")
        self.save_button.clicked.connect(lambda: self._save_plan(approved=False))
        actions.addWidget(self.save_button)
        self.approve_button = QPushButton("Approve plan")
        self.approve_button.clicked.connect(lambda: self._save_plan(approved=True))
        actions.addWidget(self.approve_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        layout.addWidget(QLabel("Editable research plan (JSON)"))
        self.plan_editor = QPlainTextEdit()
        self.plan_editor.setPlaceholderText(
            "Generate a plan or paste a valid research plan JSON object here."
        )
        layout.addWidget(self.plan_editor, 2)

        layout.addWidget(QLabel("Import candidate URLs"))
        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText(
            "Paste one HTTP or HTTPS URL per line. URLs are validated but not fetched."
        )
        self.url_input.setMaximumHeight(75)
        layout.addWidget(self.url_input)

        filter_form = QFormLayout()
        self.include_domains = QLineEdit()
        self.include_domains.setPlaceholderText("e.g. python.org, docs.python.org")
        filter_form.addRow("Include domains", self.include_domains)
        self.exclude_domains = QLineEdit()
        self.exclude_domains.setPlaceholderText("e.g. legacy.example.com")
        filter_form.addRow("Exclude domains", self.exclude_domains)
        layout.addLayout(filter_form)

        source_actions = QHBoxLayout()
        self.import_button = QPushButton("Import URLs")
        self.import_button.clicked.connect(self._import_urls)
        source_actions.addWidget(self.import_button)
        self.accept_source_button = QPushButton("Accept selected")
        self.accept_source_button.clicked.connect(
            lambda: self._set_selected_source_status("accepted")
        )
        source_actions.addWidget(self.accept_source_button)
        self.reject_source_button = QPushButton("Reject selected")
        self.reject_source_button.clicked.connect(
            lambda: self._set_selected_source_status("rejected")
        )
        source_actions.addWidget(self.reject_source_button)
        source_actions.addStretch(1)
        layout.addLayout(source_actions)

        self.source_list = QListWidget()
        layout.addWidget(self.source_list, 1)
        self.status_label = QLabel("Open a project to begin research planning.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("muted")
        layout.addWidget(self.status_label)

    def set_project(self, project_id: str | None) -> None:
        self.project_id = project_id
        self.prompt_input.clear()
        self.plan_editor.clear()
        self.url_input.clear()
        self.include_domains.clear()
        self.exclude_domains.clear()
        self.source_list.clear()
        if project_id is None:
            self.status_label.setText("Open a project to begin research planning.")
            return

        saved = self.research.get_latest_plan(project_id)
        if saved is not None:
            self.prompt_input.setPlainText(saved["prompt"])
            self.plan_editor.setPlainText(
                json.dumps(saved["plan"].to_dict(), indent=2, ensure_ascii=False)
            )
            self.include_domains.setText(", ".join(saved["plan"].preferred_domains))
            self.exclude_domains.setText(", ".join(saved["plan"].excluded_domains))
            self.status_label.setText(f"Loaded {saved['status']} research plan.")
        else:
            self.status_label.setText("Enter a research objective to begin.")
        self._refresh_sources()

    def _generate_plan(self) -> None:
        if self.project_id is None:
            self.status_label.setText("Create or open a project first.")
            return
        objective = self.prompt_input.toPlainText().strip()
        if not objective:
            self.status_label.setText("Enter a research objective first.")
            return
        try:
            config, model = self.provider_config_getter()
            self._pending_project_id = self.project_id
            LOGGER.info(
                "Research plan requested: project=%s provider=%s model=%s "
                "timeout=%.1fs objective_chars=%d",
                self.project_id,
                config.kind.value,
                model,
                config.timeout,
                len(objective),
            )

            def generate_plan(_context):
                started = time.perf_counter()
                LOGGER.info(
                    "Research plan worker started: project=%s model=%s",
                    self.project_id,
                    model,
                )
                try:
                    plan = ResearchPlanner(
                        create_provider(config), model
                    ).create_plan(objective)
                except Exception:
                    LOGGER.exception(
                        "Research plan worker failed: project=%s model=%s elapsed=%.2fs",
                        self.project_id,
                        model,
                        time.perf_counter() - started,
                    )
                    raise
                LOGGER.info(
                    "Research plan worker completed: project=%s model=%s elapsed=%.2fs",
                    self.project_id,
                    model,
                    time.perf_counter() - started,
                )
                return plan

            self.task_manager.submit("research_plan", generate_plan)
        except (ValueError, TypeError) as exc:
            self.status_label.setText(str(exc))
            return
        self.generate_button.setEnabled(False)
        self.status_label.setText("Generating a structured research plan...")

    def _task_succeeded(self, task_id: str, result: object) -> None:
        if task_id != "research_plan":
            return
        if self._pending_project_id != self.project_id:
            self.status_label.setText(
                "Plan generation completed for a different project; "
                "reopen that project to review it."
            )
            return
        if not isinstance(result, ResearchPlan):
            self.status_label.setText("The AI provider returned an unexpected plan result.")
            return
        self.plan_editor.setPlainText(
            json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
        )
        self.include_domains.setText(", ".join(result.preferred_domains))
        self.exclude_domains.setText(", ".join(result.excluded_domains))
        self.status_label.setText(
            "Research plan generated. Review and edit it before approval."
        )

    def _task_failed(self, task_id: str, error: str) -> None:
        if task_id == "research_plan":
            LOGGER.warning("Research plan generation failed: %s", error)
            if self._pending_project_id == self.project_id:
                self.status_label.setText(f"Research plan generation failed: {error}")

    def _task_finished(self, task_id: str) -> None:
        if task_id == "research_plan":
            self._pending_project_id = None
            self.generate_button.setEnabled(True)

    def _save_plan(self, *, approved: bool) -> None:
        if self.project_id is None:
            self.status_label.setText("Create or open a project first.")
            return
        prompt = self.prompt_input.toPlainText().strip()
        if not prompt:
            self.status_label.setText("Enter the original research objective first.")
            return
        try:
            payload = json.loads(self.plan_editor.toPlainText())
            if not isinstance(payload, dict):
                raise ValueError("Research plan must be a JSON object.")
            plan = ResearchPlan.from_dict(payload)
            self.research.save_plan(
                self.project_id,
                prompt,
                plan,
                approved=approved,
            )
            self.include_domains.setText(", ".join(plan.preferred_domains))
            self.exclude_domains.setText(", ".join(plan.excluded_domains))
        except (json.JSONDecodeError, ValueError) as exc:
            self.status_label.setText(f"Research plan was not saved: {exc}")
            return
        state = "approved" if approved else "saved as a draft"
        self.status_label.setText(f"Research plan {state} for this project.")

    def _domain_filter(self) -> DomainFilter:
        include = tuple(
            item.strip()
            for item in self.include_domains.text().split(",")
            if item.strip()
        )
        exclude = tuple(
            item.strip()
            for item in self.exclude_domains.text().split(",")
            if item.strip()
        )
        return DomainFilter.create(include, exclude)

    def _import_urls(self) -> None:
        if self.project_id is None:
            self.status_label.setText("Create or open a project before importing URLs.")
            return
        try:
            filters = self._domain_filter()
            accepted, rejected = import_url_candidates(
                self.url_input.toPlainText(),
                filters,
            )
            inserted = self.research.add_sources(self.project_id, accepted)
        except ValueError as exc:
            self.status_label.setText(f"URL import could not be completed: {exc}")
            return
        self._refresh_sources()
        message = f"Imported {inserted} new candidate URL(s)."
        if rejected:
            message += f" Rejected {len(rejected)} URL(s)."
            message += " " + " | ".join(
                f"{url}: {reason}" for url, reason in rejected[:3]
            )
        self.status_label.setText(message)

    def _refresh_sources(self) -> None:
        self.source_list.clear()
        if self.project_id is None:
            return
        for source in self.research.list_sources(self.project_id):
            label = (
                f"[{source['review_status']}] {source['domain']}  "
                f"{source['url']}"
            )
            self.source_list.addItem(label)
            self.source_list.item(self.source_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, source["id"]
            )

    def _set_selected_source_status(self, status: str) -> None:
        item = self.source_list.currentItem()
        if item is None:
            self.status_label.setText("Select a candidate source first.")
            return
        source_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            self.research.update_source_status(source_id, status)
        except (KeyError, ValueError) as exc:
            self.status_label.setText(f"Could not update source: {exc}")
            return
        self._refresh_sources()
        self.status_label.setText(f"Candidate source marked {status}.")
