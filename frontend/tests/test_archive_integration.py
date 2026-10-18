"""Exercise list selection through the real WebEngine local-file loader."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication

from frontend.src.archive_list.service import MockSnapshotService
from frontend.src.archive_list.window import ArchiveWindow


def test_selection_loads_local_page_and_missing_selection_hides_viewer():
    app = QApplication.instance() or QApplication([])
    window = ArchiveWindow(MockSnapshotService(), demo=True)
    window.show()
    try:
        window._request_snapshot(0, 0)
        assert window.viewer is not None
        loaded = QSignalSpy(window.viewer.loadFinished)
        assert loaded.wait(15000)
        assert loaded.at(0) == [True]
        assert window.viewer.url() == QUrl.fromLocalFile(str(window._snapshots[0].local_path))
        assert "demo-004" in window.status.text()
        assert window.viewer_dock.isVisible()
        window.search_input.setText("python.org")
        window._request_snapshot(0, 0)
        assert "no local HTML" in window.status.text()
        assert not window.viewer_dock.isVisible()
        missing = replace(window._snapshots[0], local_path=Path("/missing/webber.html"))
        window.open_snapshot(missing)
        assert "Could not open" in window.status.text()
        assert not window.viewer_dock.isVisible()
        window.search_input.setText("ucsc")
        window._request_snapshot(0, 0)
        loaded = QSignalSpy(window.viewer.loadFinished)
        assert loaded.wait(15000)
        assert loaded.at(0) == [True]
        assert window.viewer_dock.isVisible()
    finally:
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
