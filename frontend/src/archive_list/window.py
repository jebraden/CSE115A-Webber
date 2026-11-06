"""Basic temporary Qt UI for story 1.3.1."""

import logging
from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QPushButton, QHBoxLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .service import SnapshotService
from .loader import load_snapshots
from ..tasks import TaskRunner

logger = logging.getLogger(__name__)


class ArchiveWindow(QMainWindow):
    # Story 1.3.2 can connect a viewer to this signal; no file is opened here.
    snapshot_requested = Signal(object)

    def __init__(self, service: SnapshotService, *, demo: bool = False, debounce_ms: int = 200):
        super().__init__()
        self._runner = TaskRunner()
        self._runner.result.connect(self._search_result)
        self._runner.error.connect(self._search_error)
        self._closed = False
        self._current_request = None
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(debounce_ms)
        self._debounce.timeout.connect(self.search)
        self._service = service
        self._snapshots = []
        self._default_icon = QIcon(str(Path(__file__).parent / "assets" / "webpage.svg"))
        self.setWindowTitle("Webber — Archived Webpages")
        self.resize(920, 480)
        self.setMinimumSize(620, 320)
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)
        heading = QLabel("Archived Webpages")
        font = heading.font()
        font.setPointSize(22)
        font.setBold(True)
        heading.setFont(font)
        layout.addWidget(heading)
        if demo:
            layout.addWidget(QLabel("Demo • Mock data only"))
        label = QLabel("Search by &URL")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter all or part of an archived URL…")
        label.setBuddy(self.search_input)
        layout.addWidget(label)
        search_row = QHBoxLayout()
        search_row.addWidget(self.search_input)
        self.clear_button = QPushButton("Clear")
        search_row.addWidget(self.clear_button)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_search)
        search_row.addWidget(self.cancel_button)
        layout.addLayout(search_row)
        layout.addWidget(QLabel("Snapshots"))
        self.table = QTableWidget(0, 3)
        self.table.setIconSize(QSize(20, 20))
        self.table.setHorizontalHeaderLabels(["URL", "Archived at (UTC)", "ID"])
        self.table.setAccessibleName("Snapshot list")
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setAccessibleName("Search status")
        layout.addWidget(self.status)
        self.setCentralWidget(root)
        self.clear_button.clicked.connect(self.clear_search)
        self.search_input.textChanged.connect(self._schedule_search)
        self.search_input.returnPressed.connect(self.search)
        self.table.cellClicked.connect(self._request_snapshot)
        self.table.cellActivated.connect(self._request_snapshot)
        self.search_input.setFocus()
        self.search()

    def _invalidate(self):
        if self._current_request is not None:
            self._runner.cancel(self._current_request)
            self._current_request = None
        self.table.setRowCount(0)
        self._snapshots = []

    def _set_busy(self, busy):
        self.cancel_button.setEnabled(busy)
        self.table.setEnabled(not busy)

    def _schedule_search(self):
        # Invalidate at the first keystroke, including the debounce interval.
        self._invalidate()
        self._set_busy(True)
        self.status.setText("Searching…")
        self._debounce.start()

    def clear_search(self):
        self.search_input.clear()
        self.search()
        self.search_input.setFocus()

    def cancel_search(self):
        self._debounce.stop()
        self._invalidate()
        self._set_busy(False)
        self.status.setText("Search cancelled.")

    def search(self):
        if self._closed:
            return
        self._debounce.stop()
        self._invalidate()
        query = self.search_input.text().strip()
        service = self._service
        self._set_busy(True)
        self.status.setText("Searching…")
        self._current_request = self._runner.submit(
            lambda token: load_snapshots(service, query, token), key="snapshot-search",
        )

    @Slot(int, object)
    def _search_error(self, request_id, failure):
        if self._closed or request_id != self._current_request:
            return
        self._current_request = None
        self._set_busy(False)
        logger.error("Snapshot search failed: %s", failure.traceback)
        self.status.setText("Could not load snapshots. Please try searching again.")

    @Slot(int, object)
    def _search_result(self, request_id, result):
        if self._closed or request_id != self._current_request:
            return
        self._current_request = None
        self._set_busy(False)
        self._snapshots = result.snapshots
        self.table.setRowCount(len(result.rows))
        for row, (url, time, snapshot_id, image) in enumerate(result.rows):
            for column, value in enumerate((url, time, snapshot_id)):
                item = QTableWidgetItem(value)
                if column == 0:
                    icon = self._default_icon if image.isNull() else QIcon(QPixmap.fromImage(image))
                    item.setIcon(icon)
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        if result.rows:
            self.status.setText(f"{len(result.rows)} snapshot(s) • Newest first")
        elif self.search_input.text().strip():
            self.status.setText("No snapshots match this URL. Try another search or clear the search field.")
        else:
            self.status.setText("No archived webpages yet.")

    def closeEvent(self, event):
        self._closed = True
        self._debounce.stop()
        self._runner.close()
        super().closeEvent(event)

    def _request_snapshot(self, row: int, column: int):
        if 0 <= row < len(self._snapshots):
            self.snapshot_requested.emit(self._snapshots[row])
