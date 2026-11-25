import threading
import time

from PySide6.QtCore import QCoreApplication
from PySide6.QtTest import QSignalSpy

from dataset_forge.services.task_manager import TaskManager


def _application():
    return QCoreApplication.instance() or QCoreApplication([])


def _wait_for(spy, timeout_ms=3000):
    deadline = time.monotonic() + timeout_ms / 1000
    while spy.count() == 0 and time.monotonic() < deadline:
        _application().processEvents()
        time.sleep(0.01)
    _application().processEvents()
    return spy.count() > 0


def test_task_reports_progress_and_result():
    _application()
    manager = TaskManager(max_workers=1)
    progress = QSignalSpy(manager.task_progress)
    succeeded = QSignalSpy(manager.task_succeeded)
    finished = QSignalSpy(manager.task_finished)

    def work(context):
        context.report_progress(50, "Halfway")
        return "complete"

    manager.submit("sample", work)

    assert _wait_for(finished)
    assert progress.count() == 1
    assert succeeded.count() == 1
    assert succeeded.at(0)[1] == "complete"


def test_task_can_be_cancelled():
    _application()
    manager = TaskManager(max_workers=1)
    failed = QSignalSpy(manager.task_failed)
    finished = QSignalSpy(manager.task_finished)
    started = threading.Event()

    def work(context):
        started.set()
        while True:
            context.raise_if_cancelled()
            time.sleep(0.01)

    manager.submit("cancel-me", work)
    assert started.wait(1)
    assert manager.cancel("cancel-me")
    assert _wait_for(finished)
    assert failed.count() == 1
    assert "cancelled" in failed.at(0)[1].lower()
