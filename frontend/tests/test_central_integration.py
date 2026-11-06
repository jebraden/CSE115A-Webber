"""The central shell owns GUI state; services execute on worker threads."""
import asyncio
from datetime import datetime, timezone
from threading import Event, get_ident

import pytest
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QApplication

from frontend.src import main_window
from frontend.src.archive_list.service import MockSnapshotService, Snapshot
from frontend.src.archive_request.service import CreatedSnapshot
from frontend.src.api import BadRequestError
from .test_main_window import ViewerDouble
from .test_tasks import until


def test_stopped_backend_message_gives_a_recovery_action():
    from frontend.src.archive_request.errors import BackendUnavailable, present_error
    message = present_error(BackendUnavailable())
    assert "Restart Webber" in message.detail


@pytest.fixture
def windows(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(main_window, "ArchiveViewer", ViewerDouble)
    created = []
    def make(service, **kwargs):
        window = main_window.MainWindow(service, debounce_ms=10,
            settings=QSettings(str(tmp_path / f"{len(created)}.ini"), QSettings.Format.IniFormat), **kwargs)
        created.append(window)
        window.show()
        return window
    yield app, make
    for window in created:
        window.close()
    app.processEvents()


def test_capture_error_keeps_input_and_retry_refreshes_real_service(windows):
    app, make = windows
    service = MockSnapshotService([])
    calls = []
    async def create(url):
        calls.append((url, get_ident()))
        await asyncio.sleep(0.03)
        if url == "ucsc.edu":
            raise BadRequestError('{"message":"Include https:// in the URL"}')
        service._snapshots = (Snapshot("saved", url, datetime.now(timezone.utc)),)
        return CreatedSnapshot("saved")
    window = make(service, create_snapshot=create)
    until(app, lambda: window._search_request is None)
    window.ui.urlInput.setText("ucsc.edu")
    window.request_capture()
    window.request_capture()
    until(app, lambda: window._capture_request is None)
    assert len(calls) == 1
    assert window.ui.urlInput.text() == "ucsc.edu"
    assert "Include https://" in window.ui.captureStatus.text()
    window.ui.urlInput.setText("https://www.ucsc.edu/")
    window.request_capture()
    until(app, lambda: window.ui.snapshotList.count() == 1)
    assert "Page saved" in window.ui.captureStatus.text()
    assert not window.ui.captureButton.isEnabled()
    assert all(thread != get_ident() for _, thread in calls)


def test_stale_search_cannot_replace_newer_query_and_keeps_gui_alive(windows):
    app, make = windows
    started, release = Event(), Event()
    class SlowService(MockSnapshotService):
        def search_snapshots(self, query):
            if query == "old":
                started.set()
                assert release.wait(3)
            return super().search_snapshots(query)
    window = make(SlowService())
    until(app, lambda: window._search_request is None)
    window.ui.searchInput.setText("old")
    until(app, started.is_set)
    ticks = []
    timer = QTimer()
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(10)
    try:
        until(app, lambda: len(ticks) > 3)
        window.ui.searchInput.clear()
        release.set()
        until(app, lambda: window.ui.snapshotList.count() == 4 and window._search_request is None)
        assert not window.retry_search_button.isVisible()
    finally:
        release.set()
        timer.stop()


def test_closing_a_loading_tab_discards_its_late_document(windows):
    from frontend.src.archive_document import ArchiveDocument
    app, make = windows
    started, release = Event(), Event()
    class SlowDocumentService(MockSnapshotService):
        def load_archive(self, snapshot):
            started.set()
            assert release.wait(3)
            return ArchiveDocument("late", local_path=snapshot.local_path)
    window = make(SlowDocumentService())
    until(app, lambda: window._search_request is None)
    window.ui.snapshotList.setCurrentRow(0)
    try:
        until(app, started.is_set)
        window.close_tab(0)
        release.set()
        until(app, lambda: window._runner.pending_count == 0)
        assert window.tab_bar.count() == 0
        assert window._tabs == {}
        assert window.ui.rawHtml.toPlainText() == ""
    finally:
        release.set()
