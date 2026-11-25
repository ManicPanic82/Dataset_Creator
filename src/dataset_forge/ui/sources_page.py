from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dataset_forge.services.crawler import CrawlSettings, WebCrawler
from dataset_forge.services.research import SourceCandidate, domain_from_url
from dataset_forge.services.task_manager import TaskManager
from dataset_forge.storage.research_repository import ResearchRepository
from dataset_forge.storage.source_content_repository import SourceContentRepository

LOGGER = logging.getLogger(__name__)


class SourcesPage(QWidget):
    def __init__(
        self,
        research: ResearchRepository,
        content: SourceContentRepository,
        task_manager: TaskManager,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.research = research
        self.content = content
        self.task_manager = task_manager
        self.project_id: str | None = None
        self._active_source_id: str | None = None
        self._build_ui()
        self.task_manager.task_succeeded.connect(self._task_succeeded)
        self.task_manager.task_failed.connect(self._task_failed)
        self.task_manager.task_finished.connect(self._task_finished)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        actions = QHBoxLayout()
        self.fetch_button = QPushButton("Fetch selected accepted source")
        self.fetch_button.clicked.connect(self._fetch_selected)
        actions.addWidget(self.fetch_button)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._refresh)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        sitemap_row = QHBoxLayout()
        self.sitemap_input = QLineEdit()
        self.sitemap_input.setPlaceholderText("Optional sitemap.xml URL")
        sitemap_row.addWidget(self.sitemap_input, 1)
        self.sitemap_button = QPushButton("Import sitemap")
        self.sitemap_button.clicked.connect(self._import_sitemap)
        sitemap_row.addWidget(self.sitemap_button)
        layout.addLayout(sitemap_row)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_list = QListWidget()
        self.source_list.currentItemChanged.connect(self._show_preview)
        splitter.addWidget(self.source_list)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select an extracted source to preview its text.")
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        self.status = QLabel("Open a project to manage and extract sources.")
        self.status.setWordWrap(True)
        self.status.setObjectName("muted")
        layout.addWidget(self.status)

    def set_project(self, project_id: str | None) -> None:
        self.project_id = project_id
        self._refresh()

    def _refresh(self) -> None:
        self.source_list.clear()
        self.preview.clear()
        if self.project_id is None:
            self.status.setText("Open a project to manage and extract sources.")
            return
        for source in self.research.list_sources(self.project_id):
            extraction = self.content.get(source["id"])
            extracted = " · extracted" if extraction else ""
            label = f"[{source['review_status']}] {source['domain']}{extracted}"
            self.source_list.addItem(label)
            self.source_list.item(self.source_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, source["id"]
            )
        self.status.setText(
            f"{self.source_list.count()} candidate source(s). Only accepted sources can be fetched."
        )


    def _import_sitemap(self) -> None:
        if self.project_id is None:
            self.status.setText("Open a project before importing a sitemap.")
            return
        sitemap_url = self.sitemap_input.text().strip()
        if not sitemap_url:
            self.status.setText("Enter a public sitemap URL first.")
            return
        project_id = self.project_id

        def import_urls(context):
            context.report_progress(5, "Validating and reading sitemap...")
            with WebCrawler(CrawlSettings(max_pages=1, max_depth=0)) as crawler:
                urls = crawler.parse_sitemap(sitemap_url, max_urls=200)
            context.raise_if_cancelled()
            candidates = tuple(
                SourceCandidate(
                    url=url,
                    domain=domain_from_url(url),
                    discovery_method="sitemap",
                )
                for url in urls
            )
            return self.research.add_sources(project_id, candidates)

        try:
            self.task_manager.submit("sitemap_import", import_urls)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.sitemap_button.setEnabled(False)
        self.status.setText("Reading sitemap in the background...")

    def _fetch_selected(self) -> None:
        item = self.source_list.currentItem()
        if self.project_id is None or item is None:
            self.status.setText("Select an accepted source first.")
            return
        source_id = item.data(Qt.ItemDataRole.UserRole)
        source = next(
            (entry for entry in self.research.list_sources(self.project_id)
             if entry["id"] == source_id),
            None,
        )
        if source is None or source["review_status"] != "accepted":
            self.status.setText("Accept this candidate in Research before fetching it.")
            return
        url = source["url"]
        project_id = self.project_id
        self._active_source_id = source_id

        def fetch(context):
            context.report_progress(5, "Checking robots.txt and source safety...")
            with WebCrawler(CrawlSettings(max_pages=20, max_depth=2)) as crawler:
                result = crawler.crawl([url])
            context.raise_if_cancelled()
            if not result.pages:
                reason = result.failures[0].reason if result.failures else "No page was fetched."
                raise ValueError(reason)
            candidates = tuple(
                SourceCandidate(
                    url=page.requested_url,
                    domain=domain_from_url(page.requested_url),
                    title=page.title,
                    snippet=page.text[:500],
                    discovery_method="crawl",
                )
                for page in result.pages
            )
            self.research.add_sources(project_id, candidates)
            sources = {
                item["url"]: item["id"]
                for item in self.research.list_sources(project_id)
            }
            for page in result.pages:
                page_source_id = sources.get(page.requested_url)
                if page_source_id is not None:
                    self.content.save(page_source_id, page)
            return len(result.pages)

        try:
            self.task_manager.submit("source_fetch", fetch)
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.fetch_button.setEnabled(False)
        self.status.setText(f"Fetching {url} in the background...")

    def _task_succeeded(self, task_id: str, result: object) -> None:
        if task_id == "sitemap_import":
            self._refresh()
            self.status.setText(f"Imported {result} new sitemap candidate(s).")
            return
        if task_id != "source_fetch":
            return
        self._refresh()
        if self._active_source_id:
            extraction = self.content.get(self._active_source_id)
            if extraction:
                self.preview.setPlainText(
                    f"{extraction['title']}\n{extraction['final_url']}\n\n"
                    f"{extraction['extracted_text']}"
                )
        count = result if isinstance(result, int) else 1
        self.status.setText(f"Fetched and saved {count} page(s).")

    def _task_failed(self, task_id: str, error: str) -> None:
        if task_id == "source_fetch":
            LOGGER.warning("Source extraction failed: %s", error)
            self.status.setText(f"Source fetch failed: {error}")
        elif task_id == "sitemap_import":
            self.status.setText(f"Sitemap import failed: {error}")

    def _task_finished(self, task_id: str) -> None:
        if task_id == "source_fetch":
            self._active_source_id = None
            self.fetch_button.setEnabled(True)
        elif task_id == "sitemap_import":
            self.sitemap_button.setEnabled(True)

    def _show_preview(self, current, _previous) -> None:
        if current is None:
            self.preview.clear()
            return
        source_id = current.data(Qt.ItemDataRole.UserRole)
        extraction = self.content.get(source_id)
        if extraction is None:
            self.preview.setPlainText("This source has not been fetched yet.")
            return
        self.preview.setPlainText(
            f"{extraction['title']}\n{extraction['final_url']}\n\n"
            f"{extraction['extracted_text']}"
        )
