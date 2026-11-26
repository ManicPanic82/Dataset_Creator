from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dataset_forge.storage.knowledge_repository import KnowledgeRepository


class KnowledgePoolPage(QWidget):
    """Review project-scoped knowledge and inspect its source provenance."""

    def __init__(self, repository: KnowledgeRepository, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.project_id: str | None = None
        self.active_item_id: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.status_filter = QComboBox()
        self.status_filter.addItem("All statuses", "")
        for status in ("pending", "accepted", "rejected"):
            self.status_filter.addItem(status.title(), status)
        self.status_filter.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.status_filter)
        self.kind_filter = QComboBox()
        self.kind_filter.addItem("All types", "")
        for kind in (
            "concept", "definition", "fact", "procedure", "example",
            "code", "comparison", "troubleshooting",
        ):
            self.kind_filter.addItem(kind.title(), kind)
        self.kind_filter.currentIndexChanged.connect(self._refresh)
        filters.addWidget(self.kind_filter)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh)
        filters.addWidget(refresh_button)
        filters.addStretch(1)
        layout.addLayout(filters)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.item_list = QListWidget()
        self.item_list.currentItemChanged.connect(self._show_item)
        splitter.addWidget(self.item_list)
        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.details = QTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select a knowledge item to inspect its content and provenance.")
        detail_layout.addWidget(self.details, 1)
        actions = QHBoxLayout()
        self.accept_button = QPushButton("Accept")
        self.accept_button.clicked.connect(lambda: self._set_review("accepted"))
        actions.addWidget(self.accept_button)
        self.reject_button = QPushButton("Reject")
        self.reject_button.clicked.connect(lambda: self._set_review("rejected"))
        actions.addWidget(self.reject_button)
        self.pending_button = QPushButton("Reset to pending")
        self.pending_button.clicked.connect(lambda: self._set_review("pending"))
        actions.addWidget(self.pending_button)
        self.delete_button = QPushButton("Delete")
        self.delete_button.clicked.connect(self._delete_selected)
        actions.addWidget(self.delete_button)
        detail_layout.addLayout(actions)
        splitter.addWidget(detail_panel)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.status = QLabel("Open a project to review knowledge.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

    def set_project(self, project_id: str | None) -> None:
        self.project_id = project_id
        self._refresh()

    def _refresh(self, *_args) -> None:
        self.item_list.clear()
        self.details.clear()
        self.active_item_id = None
        if self.project_id is None:
            self.status.setText("Open a project to review knowledge.")
            return
        status = self.status_filter.currentData()
        records = self.repository.list_for_project(
            self.project_id, review_status=status or None
        )
        kind = self.kind_filter.currentData()
        if kind:
            records = [record for record in records if record["kind"] == kind]
        for record in records:
            summary = record["content"].replace("\n", " ").strip()
            if len(summary) > 110:
                summary = summary[:107] + "..."
            label = f"[{record['review_status']}] {record['kind']} · {summary}"
            self.item_list.addItem(label)
            self.item_list.item(self.item_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, record["id"]
            )
        self.status.setText(f"{len(records)} knowledge item(s) in this project.")

    def _show_item(self, current, _previous) -> None:
        if current is None:
            self.active_item_id = None
            self.details.clear()
            return
        item_id = current.data(Qt.ItemDataRole.UserRole)
        record = self.repository.get(item_id)
        if record is None:
            self.details.clear()
            return
        self.active_item_id = item_id
        confidence = (
            f"{record['confidence']:.2f}" if record["confidence"] is not None
            else "Not specified"
        )
        lines = [
            f"Type: {record['kind']}",
            f"Review: {record['review_status']}",
            f"Confidence: {confidence}",
            "",
            "CONTENT",
            record["content"],
            "",
            "SOURCE PROVENANCE",
        ]
        for source in record["sources"]:
            lines.extend([
                f"• {source['title'] or source['url']}",
                f"  URL: {source['url']}",
                f"  Source review status: {source['review_status']}",
                f"  Evidence: {source['evidence'] or 'No evidence snippet stored.'}",
                "",
            ])
        self.details.setPlainText("\n".join(lines))

    def _set_review(self, status: str) -> None:
        if self.active_item_id is None:
            self.status.setText("Select a knowledge item first.")
            return
        try:
            self.repository.update_review(self.active_item_id, status)
        except (KeyError, ValueError) as exc:
            self.status.setText(f"Review update failed: {exc}")
            return
        self._refresh()
        self.status.setText(f"Knowledge item marked {status}.")

    def _delete_selected(self) -> None:
        if self.active_item_id is None:
            self.status.setText("Select a knowledge item first.")
            return
        item_id = self.active_item_id
        try:
            self.repository.delete(item_id)
        except KeyError:
            self.status.setText("Knowledge item no longer exists.")
            self._refresh()
            return
        self._refresh()
        self.status.setText("Knowledge item deleted.")
