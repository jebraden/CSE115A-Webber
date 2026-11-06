"""Opt-in: real Playwright capture, SQLite, HTTP, central UI and Chromium.

WEBBER_RUN_ARCHIVE_E2E=1 make test-frontend-offscreen
Install the Playwright Chromium browser first. All sites/data are temporary;
the original site is shut down before the saved page is opened.
"""
import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import sqlite3
from threading import Thread
import time

import pytest
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from frontend.src.api import WebberAPI
from frontend.src.archive_service import ArchiveService
from frontend.src.main_window import MainWindow
from frontend.src.runtime import BackendRuntime


@pytest.mark.skipif(os.environ.get("WEBBER_RUN_ARCHIVE_E2E") != "1", reason="Opt-in real browser integration")
def test_capture_search_offline_view_and_restart(tmp_path):
    source = b'''<!doctype html><html><head><link rel="stylesheet" href="/style.css"></head>
        <body><h1 id="title">Integration Archive</h1><img id="picture" src="/picture.svg"></body></html>'''
    assets = {
        "/page.html": ("text/html", source),
        "/style.css": ("text/css", b"#title {color: rgb(23,89,121)}"),
        "/picture.svg": ("image/svg+xml", b'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="green"/></svg>'),
    }
    class Site(BaseHTTPRequestHandler):
        def do_GET(self):
            content_type, body = assets.get(self.path, ("text/plain", b"Not found"))
            self.send_response(200 if self.path in assets else 404)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *args):
            pass
    origin = ThreadingHTTPServer(("127.0.0.1", 0), Site)
    thread = Thread(target=origin.serve_forever, daemon=True)
    thread.start()
    origin_url = f"http://127.0.0.1:{origin.server_port}/page.html"
    runtime = BackendRuntime(tmp_path / "archives")
    runtime.start()
    app = QApplication.instance() or QApplication([])
    service = ArchiveService(WebberAPI(runtime.base_url), wait_ready=runtime.wait_ready)
    window = MainWindow(service, create_snapshot=service.create_snapshot, debounce_ms=10,
        settings=QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat))
    window.show()

    def until(predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if predicate():
                return
            QTest.qWait(10)
        raise AssertionError("Integration timed out: " + window.ui.captureStatus.text()
                             + " / " + window.statusBar().currentMessage())

    def javascript(script):
        values = []
        window.viewer.page().runJavaScript(script, lambda value: values.append(value))
        until(lambda: bool(values))
        return values[0]

    ticks = []
    heartbeat = QTimer()
    heartbeat.timeout.connect(lambda: ticks.append(1))
    heartbeat.start(10)
    try:
        until(lambda: window._search_request is None)
        assert not window.retry_search_button.isVisible()
        assert window.ui.snapshotList.count() == 0
        window.ui.urlInput.setText("ucsc.edu")
        window.request_capture()
        until(lambda: window._capture_request is None)
        assert "http" in window.ui.captureStatus.text()
        assert window.ui.urlInput.text() == "ucsc.edu"
        window.ui.urlInput.setText(origin_url)
        before = len(ticks)
        window.request_capture()
        until(lambda: window._capture_request is None, timeout=90)
        assert "Page saved" in window.ui.captureStatus.text()
        assert len(ticks) - before > 20
        until(lambda: window.ui.snapshotList.count() == 1)
        with sqlite3.connect(tmp_path / "archives/archive.db") as db:
            assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 1
            assert db.execute("SELECT count(*) FROM files").fetchone()[0] >= 3
        # The original server is unavailable for all subsequent viewing.
        origin.shutdown()
        origin.server_close()
        thread.join(3)
        window.ui.searchInput.setText("PAGE.HTML")
        until(lambda: window._search_request is None and not window._debounce.isActive())
        assert window.ui.snapshotList.count() == 1
        window.ui.snapshotList.setCurrentRow(0)
        until(lambda: window._snapshot is not None and window._tabs[window._snapshot.id]["available"])
        until(lambda: javascript('document.querySelector("#picture")?.naturalWidth || 0') == 64)
        assert javascript('document.querySelector("#title").textContent') == "Integration Archive"
        assert javascript('getComputedStyle(document.querySelector("#title")).color') == "rgb(23, 89, 121)"
        window.ui.rawButton.click()
        assert window.ui.rawHtml.toPlainText() == source.decode()
        window.open_in_window(window._snapshot)
        assert len(window._windows) == 1
        screenshot = os.environ.get("WEBBER_E2E_SCREENSHOT")
        if screenshot:
            window.ui.pageButton.click()
            window.ui.savePageButton.setChecked(False)
            app.processEvents()
            assert window.grab().save(screenshot)
    finally:
        heartbeat.stop()
        window.close()
        runtime.stop()
        origin.shutdown()
        origin.server_close()
    assert not runtime.backend.running
    restarted = BackendRuntime(tmp_path / "archives")
    restarted.start()
    try:
        async def check_persisted():
            service = ArchiveService(WebberAPI(restarted.base_url), wait_ready=restarted.wait_ready)
            snapshots = await service.search_snapshots("page.html")
            assert len(snapshots) == 1
            document = await service.load_archive(snapshots[0])
            assert "Integration Archive" in document.source
        asyncio.run(check_persisted())
    finally:
        restarted.stop()
