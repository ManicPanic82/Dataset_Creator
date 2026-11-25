from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

LOGGER = logging.getLogger(__name__)


class TaskSignals(QObject):
    progress = Signal(int, str)
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()


@dataclass
class TaskContext:
    _cancel_event: threading.Event
    _progress_callback: Callable[[int, str], None]

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise TaskCancelled("Task was cancelled.")

    def report_progress(self, percent: int, message: str = "") -> None:
        self.raise_if_cancelled()
        self._progress_callback(max(0, min(100, percent)), message)


class TaskCancelled(Exception):
    """Raised by a task when cancellation has been requested."""


class _Task(QRunnable):
    def __init__(self, task_id: str, function: Callable[[TaskContext], Any]) -> None:
        super().__init__()
        self.task_id = task_id
        self.function = function
        self.signals = TaskSignals()
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        started = time.perf_counter()
        LOGGER.info("Background task worker started: task=%s", self.task_id)
        context = TaskContext(
            self.cancel_event,
            lambda percent, message: self.signals.progress.emit(percent, message),
        )
        try:
            context.raise_if_cancelled()
            result = self.function(context)
            context.raise_if_cancelled()
            LOGGER.info(
                "Background task worker completed: task=%s elapsed=%.2fs",
                self.task_id,
                time.perf_counter() - started,
            )
            self.signals.succeeded.emit(result)
        except TaskCancelled:
            LOGGER.info(
                "Background task cancelled: task=%s elapsed=%.2fs",
                self.task_id,
                time.perf_counter() - started,
            )
            self.signals.failed.emit("Task cancelled.")
        except Exception as exc:
            LOGGER.exception(
                "Background task failed: task=%s elapsed=%.2fs",
                self.task_id,
                time.perf_counter() - started,
            )
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        finally:
            self.signals.finished.emit()


class TaskManager(QObject):
    task_started = Signal(str)
    task_progress = Signal(str, int, str)
    task_succeeded = Signal(str, object)
    task_failed = Signal(str, str)
    task_finished = Signal(str)

    def __init__(self, parent: QObject | None = None, max_workers: int = 2) -> None:
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(max(1, max_workers))
        self._tasks: dict[str, _Task] = {}

    def submit(self, task_id: str, function: Callable[[TaskContext], Any]) -> None:
        if task_id in self._tasks:
            raise ValueError(f"Task already exists: {task_id}")
        LOGGER.info("Background task queued: task=%s", task_id)
        task = _Task(task_id, function)
        self._tasks[task_id] = task
        task.signals.progress.connect(
            lambda percent, message, key=task_id:
                self.task_progress.emit(key, percent, message)
        )
        task.signals.succeeded.connect(
            lambda result, key=task_id: self.task_succeeded.emit(key, result)
        )
        task.signals.failed.connect(
            lambda error, key=task_id: self.task_failed.emit(key, error)
        )
        task.signals.finished.connect(lambda key=task_id: self._on_finished(key))
        self.task_started.emit(task_id)
        self.pool.start(task)

    def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.cancel()
        return True

    def _on_finished(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self.task_finished.emit(task_id)

    def shutdown(self, timeout_ms: int = 3000) -> None:
        for task in self._tasks.values():
            task.cancel()
        self.pool.waitForDone(timeout_ms)
