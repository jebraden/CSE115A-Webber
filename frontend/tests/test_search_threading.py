"""Search integration: UI heartbeat, debounce, clear, cancellation and errors."""
import asyncio
import os
from threading import Event, get_ident
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest

from frontend.src.archive_list.service import MockSnapshotService
from frontend.src.archive_list.window import ArchiveWindow
from .test_tasks import until


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def windows(app):
    created = []
    def make(service, **kwargs):
        window = ArchiveWindow(service, **kwargs)
        window.show()
        created.append(window)
        return window
    yield make
    for window in created:
        window.close()
    app.processEvents()


def test_slow_search_keeps_gui_alive_and_clear_wins(app, windows):
    started, release = Event(), Event()
    calls = []
    class SlowService(MockSnapshotService):
        def search_snapshots(self, query):
            calls.append((query, get_ident()))
            if query == "ucsc":
                started.set()
                assert release.wait(2)
            return super().search_snapshots(query)
    w = windows(SlowService(), debounce_ms=20)
    until(app, lambda: w.table.rowCount() == 4)
    ui_thread = get_ident()
    ticks = []
    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.append(True))
    heartbeat.start()
    try:
        w.search_input.setText("ucsc")
        until(app, started.is_set)
        until(app, lambda: len(ticks) >= 5)
        assert w.cancel_button.isEnabled()
        assert w.search_input.isEnabled() and w.clear_button.isEnabled()
        QTest.mouseClick(w.clear_button, Qt.MouseButton.LeftButton)
        assert w.search_input.text() == ""
        release.set()
        until(app, lambda: w.table.rowCount() == 4 and not w.cancel_button.isEnabled())
        assert all(thread != ui_thread for _, thread in calls)
        assert "Could not load" not in w.status.text()
    finally:
        release.set()
        heartbeat.stop()


def test_typing_is_debounced_and_deletion_refreshes_all(app, windows):
    calls = []
    class RecordingService(MockSnapshotService):
        def search_snapshots(self, query):
            calls.append(query)
            return super().search_snapshots(query)
    w = windows(RecordingService(), debounce_ms=30)
    until(app, lambda: w.table.rowCount() == 4)
    calls.clear()
    QTest.keyClicks(w.search_input, "UCSC")
    until(app, lambda: w.table.rowCount() == 2)
    assert calls == ["UCSC"]
    w.search_input.selectAll()
    QTest.keyClick(w.search_input, Qt.Key.Key_Backspace)
    until(app, lambda: w.table.rowCount() == 4)


def test_cancel_search_then_retry(app, windows):
    started, release = Event(), Event()
    class SlowService(MockSnapshotService):
        def search_snapshots(self, query):
            if query == "slow":
                started.set()
                assert release.wait(2)
            return super().search_snapshots(query)
    w = windows(SlowService(), debounce_ms=0)
    until(app, lambda: w.table.rowCount() == 4)
    w.search_input.setText("slow")
    until(app, started.is_set)
    w.cancel_button.click()
    assert w.status.text() == "Search cancelled."
    release.set()
    w.clear_button.click()
    until(app, lambda: w.table.rowCount() == 4)


def test_async_service_and_bad_data_recovery(app, windows):
    class AsyncService:
        async def search_snapshots(self, query):
            await asyncio.sleep(0.01)
            if query == "bad":
                raise ValueError("malformed response")
            return MockSnapshotService().search_snapshots(query)
    w = windows(AsyncService(), debounce_ms=0)
    until(app, lambda: w.table.rowCount() == 4)
    w.search_input.setText("bad")
    until(app, lambda: "Could not load" in w.status.text())
    assert w.table.rowCount() == 0
    w.clear_button.click()
    until(app, lambda: w.table.rowCount() == 4)


def test_close_while_searching_never_waits_for_service(app, windows):
    started, release = Event(), Event()
    class SlowService:
        def search_snapshots(self, query):
            started.set()
            assert release.wait(2)
            return []
    w = windows(SlowService())
    until(app, started.is_set)
    start = time.monotonic()
    w.close()
    assert time.monotonic() - start < 0.2
    release.set()
    until(app, lambda: w._runner.pending_count == 0)
    assert not w.isVisible()
