from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dataset_forge.services.ai_providers import create_provider
from dataset_forge.services.dataset_generation import DatasetGenerationService
from dataset_forge.services.dataset_quality import DatasetQualityService
from dataset_forge.services.dataset_verification import DatasetVerificationService
from dataset_forge.services.knowledge_context import KnowledgeContextService
from dataset_forge.storage.dataset_record_repository import DatasetRecordRepository
from dataset_forge.storage.knowledge_repository import KnowledgeRepository


class DatasetBuilderPage(QWidget):
    """Generate, inspect and review source-grounded dataset drafts."""

    TASK_ID = "dataset_generation"
    VERIFICATION_TASK_ID = "dataset_verification"
    BATCH_VERIFICATION_TASK_ID = "dataset_batch_verification"

    def __init__(
        self,
        knowledge_repository: KnowledgeRepository,
        record_repository: DatasetRecordRepository,
        task_manager,
        provider_config,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.knowledge_repository = knowledge_repository
        self.record_repository = record_repository
        self.task_manager = task_manager
        self.provider_config = provider_config
        self.project_id: str | None = None
        self.active_record_id: str | None = None
        self.verification_reports: dict[str, dict] = {}
        self.verification_errors: dict[str, str] = {}
        self.quality_reports: dict[str, dict] = {}
        self._build_ui()
        self.task_manager.task_succeeded.connect(self._task_succeeded)
        self.task_manager.task_failed.connect(self._task_failed)
        self.task_manager.task_progress.connect(self._task_progress)
        self.task_manager.task_finished.connect(self._task_finished)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        form = QFormLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItem("Question & answer", "question_answer")
        self.format_combo.addItem("Instruction / input / output", "instruction")
        self.format_combo.addItem("Conversation", "conversational")
        form.addRow("Dataset format", self.format_combo)
        self.difficulty_combo = QComboBox()
        for level in ("mixed", "beginner", "intermediate", "advanced", "expert"):
            self.difficulty_combo.addItem(level.title(), level)
        form.addRow("Difficulty", self.difficulty_combo)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 20)
        self.count_spin.setValue(5)
        form.addRow("Records to generate", self.count_spin)
        controls.addLayout(form)
        controls.addStretch(1)
        self.generate_button = QPushButton("Generate draft records")
        self.generate_button.clicked.connect(self._generate)
        controls.addWidget(self.generate_button, alignment=Qt.AlignmentFlag.AlignBottom)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        knowledge_panel = QWidget()
        knowledge_layout = QVBoxLayout(knowledge_panel)
        knowledge_layout.setContentsMargins(0, 0, 0, 0)
        knowledge_layout.addWidget(QLabel("Accepted knowledge · select up to 20"))
        self.knowledge_list = QListWidget()
        knowledge_layout.addWidget(self.knowledge_list, 1)
        knowledge_actions = QHBoxLayout()
        refresh_knowledge = QPushButton("Refresh knowledge")
        refresh_knowledge.clicked.connect(self._refresh_knowledge)
        knowledge_actions.addWidget(refresh_knowledge)
        select_all = QPushButton("Select all")
        select_all.clicked.connect(self._select_all_knowledge)
        knowledge_actions.addWidget(select_all)
        knowledge_layout.addLayout(knowledge_actions)
        splitter.addWidget(knowledge_panel)

        records_panel = QWidget()
        records_layout = QVBoxLayout(records_panel)
        records_layout.setContentsMargins(0, 0, 0, 0)
        records_layout.addWidget(QLabel("Generated records"))
        self.record_list = QListWidget()
        self.record_list.currentItemChanged.connect(self._show_record)
        records_layout.addWidget(self.record_list, 1)
        self.quality_summary = QTextEdit()
        self.quality_summary.setReadOnly(True)
        self.quality_summary.setAcceptRichText(False)
        self.quality_summary.setMaximumHeight(190)
        self.quality_summary.setPlaceholderText(
            "Quality screening appears when you select a record."
        )
        self.quality_summary.setObjectName("qualitySummary")
        records_layout.addWidget(self.quality_summary)
        self.record_details = QTextEdit()
        self.record_details.setReadOnly(True)
        self.record_details.setPlaceholderText(
            "Select a generated record to inspect its content and source provenance."
        )
        records_layout.addWidget(self.record_details, 2)
        review_actions = QHBoxLayout()
        self.accept_button = QPushButton("Accept")
        self.accept_button.clicked.connect(lambda: self._set_review("accepted"))
        review_actions.addWidget(self.accept_button)
        self.reject_button = QPushButton("Reject")
        self.reject_button.clicked.connect(lambda: self._set_review("rejected"))
        review_actions.addWidget(self.reject_button)
        self.pending_button = QPushButton("Reset to pending")
        self.pending_button.clicked.connect(lambda: self._set_review("pending_review"))
        review_actions.addWidget(self.pending_button)
        self.verify_button = QPushButton("Run AI verification")
        self.verify_button.clicked.connect(self._verify_record)
        review_actions.addWidget(self.verify_button)
        self.verify_all_button = QPushButton("Verify all records")
        self.verify_all_button.clicked.connect(self._verify_all_records)
        review_actions.addWidget(self.verify_all_button)
        records_layout.addLayout(review_actions)
        splitter.addWidget(records_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.status = QLabel("Open a project and select accepted knowledge to begin.")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def set_project(self, project_id: str | None) -> None:
        self.project_id = project_id
        self._refresh_knowledge()
        self._refresh_records()

    def _refresh_knowledge(self) -> None:
        self.knowledge_list.clear()
        if self.project_id is None:
            return
        items = self.knowledge_repository.list_for_project(
            self.project_id, review_status="accepted"
        )
        for index, record in enumerate(items):
            summary = " ".join(record["content"].split())
            if len(summary) > 125:
                summary = summary[:122] + "..."
            item = QListWidgetItem(f"{record['kind']} · {summary}")
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if index < 20 else Qt.CheckState.Unchecked
            )
            self.knowledge_list.addItem(item)
        self.status.setText(
            f"{len(items)} accepted knowledge item(s) available. "
            "The first 20 are selected; adjust the selection as needed."
        )

    def _select_all_knowledge(self) -> None:
        for index in range(self.knowledge_list.count()):
            self.knowledge_list.item(index).setCheckState(Qt.CheckState.Checked)

    def _selected_knowledge_ids(self) -> list[str]:
        selected = []
        for index in range(self.knowledge_list.count()):
            item = self.knowledge_list.item(index)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.data(Qt.ItemDataRole.UserRole))
        return selected

    def _generate(self) -> None:
        if self.project_id is None:
            self.status.setText("Open a project before generating dataset records.")
            return
        knowledge_ids = self._selected_knowledge_ids()
        if not knowledge_ids:
            self.status.setText("Select at least one accepted knowledge item.")
            return
        if len(knowledge_ids) > 20:
            self.status.setText("Select no more than 20 knowledge items per batch.")
            return
        try:
            config, model = self.provider_config()
            provider = create_provider(config)
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Configure a provider and model in Settings: {exc}")
            return

        project_id = self.project_id
        service = DatasetGenerationService(
            provider,
            model,
            KnowledgeContextService(self.knowledge_repository),
            self.record_repository,
        )
        dataset_type = self.format_combo.currentData()
        difficulty = self.difficulty_combo.currentData()
        count = self.count_spin.value()

        def generate(context):
            context.report_progress(5, "Preparing accepted knowledge context")
            result = service.generate_batch(
                project_id,
                dataset_type=dataset_type,
                count=count,
                difficulty=difficulty,
                knowledge_ids=knowledge_ids,
            )
            context.report_progress(100, f"Saved {len(result)} draft record(s)")
            return result

        try:
            self.task_manager.submit(self.TASK_ID, generate)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.generate_button.setEnabled(False)
        self.status.setText(f"Generating up to {count} {dataset_type} record(s) with {model}...")

    def _refresh_records(self) -> None:
        self.record_list.clear()
        self.record_details.clear()
        self.quality_summary.clear()
        self.active_record_id = None
        if self.project_id is None:
            return
        records = self.record_repository.list_for_project(self.project_id)
        for record in records:
            item = QListWidgetItem(self._record_list_label(record))
            item.setData(Qt.ItemDataRole.UserRole, record["id"])
            self.record_list.addItem(item)

    def _record_list_label(self, record: dict) -> str:
        parts = [f"[{record['review_status']}]"]
        quality = self.quality_reports.get(record["id"])
        if quality is not None:
            parts.append(f"[Quality {quality['score']}/100]")
        verification = self.verification_reports.get(record["id"])
        if verification is not None:
            parts.append(
                f"[AI {verification['verdict'].upper()} · {verification['score']}]"
            )
        elif record["id"] in self.verification_errors:
            parts.append("[AI ERROR]")
        parts.extend([
            record["dataset_type"],
            self._record_summary(record["payload"]),
        ])
        return " ".join(parts)

    def _update_record_list_labels(self) -> None:
        for index in range(self.record_list.count()):
            item = self.record_list.item(index)
            record_id = item.data(Qt.ItemDataRole.UserRole)
            record = self.record_repository.get(record_id)
            if record is not None:
                item.setText(self._record_list_label(record))

    @staticmethod
    def _record_summary(payload: dict) -> str:
        if "question" in payload:
            return payload["question"]
        if "instruction" in payload:
            return payload["instruction"]
        messages = payload.get("messages", [])
        if messages:
            return messages[0].get("content", "Conversation")
        return "Generated record"

    def _show_record(self, current, _previous) -> None:
        if current is None:
            self.active_record_id = None
            self.record_details.clear()
            self.quality_summary.setPlainText("Select a record to run quality screening.")
            return
        record_id = current.data(Qt.ItemDataRole.UserRole)
        record = self.record_repository.get(record_id)
        if record is None:
            self.record_details.clear()
            self.quality_summary.setPlainText("Record unavailable.")
            return
        self.active_record_id = record_id
        quality = DatasetQualityService.assess(
            record["dataset_type"], record["payload"], record["provenance"]
        )
        quality_lines = [
            f"Quality screening: {quality['score']}/100 · {quality['label']}"
        ]
        for flag in quality["flags"]:
            quality_lines.append(f"- {flag['message']}")
            for sentence in flag.get("sentences", []):
                quality_lines.append(f'  Flagged sentence: "{sentence}"')
        quality_lines.append(quality["disclaimer"])
        verification = self.verification_reports.get(record_id)
        if verification:
            quality_lines.extend(self._verification_lines(verification))
        verification_error = self.verification_errors.get(record_id)
        if verification_error:
            quality_lines.extend(["", f"AI verification error: {verification_error}"])
        self.quality_summary.setPlainText("\n".join(quality_lines))
        lines = [
            f"Format: {record['dataset_type']}",
            f"Review: {record['review_status']}",
            "",
            "RECORD DATA",
            json.dumps(record["payload"], ensure_ascii=False, indent=2),
            "",
            "SOURCE PROVENANCE",
        ]
        for knowledge in record["provenance"]:
            lines.extend([
                f"Knowledge: {knowledge['kind']} · {knowledge['content']}",
                f"Confidence: {knowledge['confidence']}",
            ])
            for source in knowledge["sources"]:
                lines.extend([
                    f"  Source: {source['title'] or source['url']}",
                    f"  URL: {source['url']}",
                    f"  Evidence: {source['evidence'] or 'No evidence snippet'}",
                ])
            lines.append("")
        self.record_details.setPlainText("\n".join(lines))

    @staticmethod
    def _verification_lines(report: dict) -> list[str]:
        lines = [
            "",
            f"AI verification: {report['verdict'].upper()} · {report['score']}/100",
            report["summary"],
        ]
        for finding in report["findings"]:
            lines.append(
                f"- [{finding['severity'].upper()} · {finding['category']}] "
                f"{finding['explanation']}"
            )
            if finding["claim"]:
                lines.append(f"  Claim: {finding['claim']}")
            if finding["evidence"]:
                lines.append(f'  Source quote: "{finding["evidence"]}"')
            else:
                lines.append("  Source quote: No exact supporting quote supplied.")
        lines.append(report["disclaimer"])
        return lines

    def _verify_record(self) -> None:
        if self.active_record_id is None:
            self.status.setText("Select a generated record before verification.")
            return
        record = self.record_repository.get(self.active_record_id)
        if record is None:
            self.status.setText("The selected record is no longer available.")
            return
        try:
            config, model = self.provider_config()
            provider = create_provider(config)
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Configure a provider and model in Settings: {exc}")
            return

        record_id = self.active_record_id
        service = DatasetVerificationService(provider, model)

        def verify(context):
            context.report_progress(10, "Preparing record and source evidence")
            report = service.verify(
                record["dataset_type"], record["payload"], record["provenance"]
            )
            context.report_progress(100, "AI verification complete")
            return {"record_id": record_id, "report": report}

        try:
            self.task_manager.submit(self.VERIFICATION_TASK_ID, verify)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.verify_button.setEnabled(False)
        self.verify_all_button.setEnabled(False)
        self.status.setText(f"Running advisory AI verification with {model}...")


    def _verify_all_records(self) -> None:
        if self.project_id is None:
            self.status.setText("Open a project before running batch verification.")
            return
        records = self.record_repository.list_for_project(self.project_id)
        if not records:
            self.status.setText("There are no generated records to review.")
            return
        try:
            config, model = self.provider_config()
            provider = create_provider(config)
        except (ValueError, TypeError) as exc:
            self.status.setText(f"Configure a provider and model in Settings: {exc}")
            return

        records_to_verify = [
            record for record in records
            if record["id"] not in self.verification_reports
        ]
        service = DatasetVerificationService(provider, model)

        def verify_all(context):
            quality_reports = {}
            total = len(records)
            for index, record in enumerate(records, start=1):
                quality_reports[record["id"]] = DatasetQualityService.assess(
                    record["dataset_type"], record["payload"], record["provenance"]
                )
                context.report_progress(
                    int(index / max(total, 1) * 10),
                    f"Heuristic screening {index}/{total}",
                )

            def report_progress(index, count, _record_id):
                context.report_progress(
                    10 + int(index / max(count, 1) * 90),
                    f"AI verification {index}/{count}",
                )

            batch = service.verify_batch(records_to_verify, report_progress)
            return {
                "quality_reports": quality_reports,
                "reports": batch["reports"],
                "errors": batch["errors"],
                "total": total,
                "verified_this_run": len(records_to_verify),
            }

        try:
            self.task_manager.submit(self.BATCH_VERIFICATION_TASK_ID, verify_all)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.verify_button.setEnabled(False)
        self.verify_all_button.setEnabled(False)
        self.status.setText(
            f"Preparing batch review of {len(records)} record(s) with {model}..."
        )

    def _set_review(self, status: str) -> None:
        if self.active_record_id is None:
            self.status.setText("Select a generated record first.")
            return
        try:
            self.record_repository.update_review(self.active_record_id, status)
        except (KeyError, ValueError) as exc:
            self.status.setText(f"Review update failed: {exc}")
            return
        self._refresh_records()
        self.status.setText(f"Dataset record marked {status}.")

    def _task_succeeded(self, task_id: str, result: object) -> None:
        if task_id == self.BATCH_VERIFICATION_TASK_ID:
            if isinstance(result, dict):
                self.verification_reports.update(result.get("reports", {}))
                self.verification_errors.update(result.get("errors", {}))
                self.quality_reports.update(result.get("quality_reports", {}))
                self._update_record_list_labels()
                current = self.record_list.currentItem()
                if current is not None:
                    self._show_record(current, None)
                reports = result.get("reports", {})
                errors = result.get("errors", {})
                verdicts = [report["verdict"] for report in reports.values()]
                self.status.setText(
                    f"Batch review complete: {result.get('total', 0)} record(s). "
                    f"AI pass {verdicts.count('pass')} · "
                    f"review {verdicts.count('review')} · "
                    f"fail {verdicts.count('fail')} · errors {len(errors)}. "
                    f"Verified this run: {result.get('verified_this_run', 0)}."
                )
            return
        if task_id == self.VERIFICATION_TASK_ID:
            if isinstance(result, dict) and isinstance(result.get("report"), dict):
                record_id = result.get("record_id")
                if isinstance(record_id, str):
                    self.verification_reports[record_id] = result["report"]
                    self.verification_errors.pop(record_id, None)
                    self._update_record_list_labels()
                    if self.active_record_id == record_id:
                        current = self.record_list.currentItem()
                        self._show_record(current, None)
                    self.status.setText("AI verification complete. Review the advisory findings.")
            return
        if task_id != self.TASK_ID:
            return
        self._refresh_records()
        saved = len(result) if isinstance(result, list) else 0
        self.status.setText(
            f"Generation complete. Saved {saved} record(s) as pending review."
        )

    def _task_progress(self, task_id: str, percent: int, message: str) -> None:
        if task_id in {self.TASK_ID, self.VERIFICATION_TASK_ID, self.BATCH_VERIFICATION_TASK_ID}:
            self.status.setText(f"{percent}% · {message}")

    def _task_failed(self, task_id: str, error: str) -> None:
        if task_id == self.TASK_ID:
            self.status.setText(f"Dataset generation failed: {error}")
        elif task_id == self.VERIFICATION_TASK_ID:
            self.status.setText(f"AI verification failed: {error}")
        elif task_id == self.BATCH_VERIFICATION_TASK_ID:
            self.status.setText(f"Batch AI verification failed: {error}")

    def _task_finished(self, task_id: str) -> None:
        if task_id == self.TASK_ID:
            self.generate_button.setEnabled(True)
        elif task_id == self.VERIFICATION_TASK_ID:
            self.verify_button.setEnabled(True)
            self.verify_all_button.setEnabled(True)
        elif task_id == self.BATCH_VERIFICATION_TASK_ID:
            self.verify_button.setEnabled(True)
            self.verify_all_button.setEnabled(True)
