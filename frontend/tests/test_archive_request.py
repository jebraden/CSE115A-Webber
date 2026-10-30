"""Exercise the widget with HTTP responses delivered through worker tasks."""
import asyncio
import os
from threading import Event, get_ident

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import httpx
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest

from frontend.src.archive_request import ArchiveRequestDialog
from frontend.src.archive_list.service import MockSnapshotService
from frontend.src.archive_list.window import ArchiveWindow
from .test_tasks import until


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def dialogs(app):
    created = []
    def make(service=None):
        dialog = ArchiveRequestDialog(service)
        dialog.show()
        created.append(dialog)
        return dialog
    yield make
    for dialog in created:
        dialog.reject()
    app.processEvents()


def test_backend_rejection_keeps_url_then_edit_retry_succeeds(app, dialogs):
    calls, workers = [], []
    ui_thread = get_ident()
    async def archive(url):
        workers.append(get_ident())
        calls.append(url)
        async def respond(request):
            await asyncio.sleep(0.01)
            return httpx.Response(
                400 if len(calls) == 1 else 201,
                json={"message": "Invalid URL: include https://"} if len(calls) == 1 else {"id": "snapshot-123"},
            )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            response = await client.post("http://service.test/snapshots/create", json={"url": url})
            response.raise_for_status()
            return response.json()
    dialog = dialogs(archive)
    dialog.url_input.setText("ucsc.edu")
    QTest.mouseClick(dialog.submit_button, Qt.MouseButton.LeftButton)
    until(app, lambda: dialog.error_title.text() == "Archive request rejected")
    assert dialog.url_input.text() == "ucsc.edu"
    assert dialog.error_detail.text() == "Invalid URL: include https://"
    assert dialog.submit_button.isEnabled()
    assert dialog.submit_button.text() == "Retry"
    assert dialog.url_input.isEnabled()
    dialog.url_input.setText("https://www.ucsc.edu/")
    assert dialog.error_detail.text() == ""
    created, callback_threads = [], []
    dialog.archive_created.connect(lambda value: (created.append(value), callback_threads.append(get_ident())))
    QTest.keyClick(dialog.url_input, Qt.Key.Key_Return)
    until(app, lambda: created == ["snapshot-123"])
    assert dialog.url_input.text() == "https://www.ucsc.edu/"
    assert "snapshot-123" in dialog.status.text()
    assert not dialog.submit_button.isEnabled()
    QTest.keyClick(dialog.url_input, Qt.Key.Key_Return)
    dialog.submit()
    assert calls == ["ucsc.edu", "https://www.ucsc.edu/"]
    assert all(thread != ui_thread for thread in workers)
    assert callback_threads == [ui_thread]


def test_duplicate_clicks_and_enter_do_not_submit_twice(app, dialogs):
    started, release = Event(), Event()
    calls = []
    def archive(url):
        calls.append(url)
        started.set()
        assert release.wait(2)
        return {"id": "one"}
    dialog = dialogs(archive)
    dialog.url_input.setText("https://example.com")
    dialog.submit()
    until(app, started.is_set)
    try:
        dialog.submit()
        dialog.submit_button.click()
        assert not dialog.url_input.isEnabled()
        assert not dialog.submit_button.isEnabled()
        assert dialog.progress.isVisible()
        assert len(calls) == 1
    finally:
        release.set()
    until(app, lambda: dialog.status.text() == "Snapshot created: one")


def test_backend_text_is_plain_and_selectable(app, dialogs):
    class Rejected(Exception):
        code = 400
        message = '<b>Bad URL</b><img src="https://outside.test/pixel">'
    def archive(url):
        raise Rejected()
    dialog = dialogs(archive)
    dialog.url_input.setText("bad")
    dialog.submit()
    until(app, lambda: bool(dialog.error_detail.text()))
    assert dialog.error_detail.text() == Rejected.message
    assert dialog.error_detail.textFormat() == Qt.TextFormat.PlainText


@pytest.mark.parametrize("failure, title", [
    (httpx.ReadTimeout("demo"), "Archive request timed out"),
    (httpx.ConnectError("demo"), "Cannot reach the archive service"),
])
def test_transport_errors_allow_explicit_retry(app, dialogs, failure, title):
    def archive(url):
        raise failure
    dialog = dialogs(archive)
    dialog.url_input.setText("https://www.ucsc.edu/")
    dialog.submit()
    until(app, lambda: dialog.error_title.text() == title)
    assert dialog.url_input.text() == "https://www.ucsc.edu/"
    assert dialog.submit_button.isEnabled()


def test_disconnected_build_never_reports_fake_success(app, dialogs):
    dialog = dialogs()
    successes = []
    dialog.archive_created.connect(successes.append)
    dialog.url_input.setText("https://example.com")
    dialog.submit()
    until(app, lambda: dialog.error_title.text() == "Archive service is not connected")
    assert not successes


@pytest.mark.parametrize("response", [None, {}, {"id": None}, {"id": ""}, {"id": 123}])
def test_success_without_snapshot_id_is_rejected(app, dialogs, response):
    dialog = dialogs(lambda url: response)
    dialog.url_input.setText("https://example.com")
    dialog.submit()
    until(app, lambda: dialog.error_title.text() == "Unexpected archive response")
    assert "Snapshot created" not in dialog.status.text()


def test_close_cancels_async_delivery_and_reopening_is_safe(app, dialogs):
    started, cleaned = Event(), Event()
    async def archive(url):
        try:
            started.set()
            await asyncio.sleep(30)
        finally:
            cleaned.set()
    dialog = dialogs(archive)
    dialog.url_input.setText("https://example.com")
    dialog.submit()
    until(app, started.is_set)
    dialog.reject()
    until(app, cleaned.is_set)
    assert not dialog.isVisible()
    replacement = dialogs(lambda url: {"id": "new-dialog"})
    replacement.url_input.setText("https://example.com")
    replacement.submit()
    until(app, lambda: replacement.status.text() == "Snapshot created: new-dialog")


def test_empty_url_never_sends_request(app, dialogs):
    calls = []
    dialog = dialogs(lambda url: calls.append(url))
    dialog.url_input.setText("   ")
    dialog.submit()
    assert not dialog.submit_button.isEnabled()
    assert not calls


def test_main_window_menu_opens_dialog_and_search_accepts_url_fragment(app):
    window = ArchiveWindow(MockSnapshotService(), debounce_ms=0)
    window.show()
    try:
        window.menuBar().actions()[0].menu().actions()[0].trigger()
        dialog = window._archive_dialog
        assert dialog and dialog.isVisible()
        dialog.reject()
        assert window._archive_dialog is None
        window.open_archive_dialog()
        assert window._archive_dialog is not dialog
        window.search_input.setText("ucsc")
        until(app, lambda: window.table.rowCount() == 2)
        assert "Could not load" not in window.status.text()
    finally:
        window.close()


def test_injected_archive_service_emits_id_and_refreshes_list(app):
    from datetime import datetime, timezone
    from frontend.src.archive_list.service import MOCK_SNAPSHOTS, Snapshot
    records = list(MOCK_SNAPSHOTS)
    class SearchService:
        def search_snapshots(self, query):
            return MockSnapshotService(tuple(records)).search_snapshots(query)
    def create(url):
        records.append(Snapshot("created-id", url, datetime(2026, 10, 30, tzinfo=timezone.utc)))
        return {"id": "created-id"}
    window = ArchiveWindow(SearchService(), create_snapshot=create)
    window.show()
    ids = []
    window.archive_created.connect(ids.append)
    try:
        until(app, lambda: window.table.rowCount() == 4)
        window.open_archive_dialog()
        dialog = window._archive_dialog
        dialog.url_input.setText("https://new.example.org/")
        dialog.submit()
        until(app, lambda: ids == ["created-id"] and window.table.rowCount() == 5)
        assert window.table.item(0, 0).text() == "https://new.example.org/"
        assert dialog.status.text() == "Snapshot created: created-id"
    finally:
        window.close()
