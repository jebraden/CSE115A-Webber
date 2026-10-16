"""Basic temporary Qt UI for story 1.3.1."""

import logging
from datetime import timezone
from pathlib import Path

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QPushButton, QHBoxLayout, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .service import SnapshotService

logger = logging.getLogger(__name__)


class ArchiveWindow(QMainWindow):
    # Story 1.3.2 can connect a viewer to this signal; no file is opened here.
    snapshot_requested = Signal(object)

    def __init__(self, service: SnapshotService, *, demo: bool = False):
        super().__init__()
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
        self.search_input.textChanged.connect(self.search)
        self.search_input.returnPressed.connect(self.search)
        self.table.cellClicked.connect(self._request_snapshot)
        self.table.cellActivated.connect(self._request_snapshot)
        self.search_input.setFocus()
        self.search()

    def clear_search(self):
        if self.search_input.text():
            self.search_input.clear()
        else:
            self.search()
        self.search_input.setFocus()

    def search(self):
        query = self.search_input.text().strip()
        self.table.setRowCount(0)
        self._snapshots = []
        try:
            snapshots = list(self._service.search_snapshots(query))
            # Format before populating so a malformed adapter response cannot
            # leave a partially displayed result set.
            rows = [
                (s.url, s.archived_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), str(s.id))
                for s in snapshots
            ]
        except Exception:
            logger.exception("Snapshot search failed")
            self.status.setText("Could not load snapshots. Please try searching again.")
            return
        self._snapshots = snapshots
        self.table.setRowCount(len(rows))
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setIcon(self._snapshot_icon(snapshots[row].favicon_path))
                item.setToolTip(value)
                self.table.setItem(row, column, item)
        if rows:
            self.status.setText(f"{len(rows)} snapshot(s) • Newest first")
        elif query:
            self.status.setText("No snapshots match this URL. Try another search or clear the search field.")
        else:
            self.status.setText("No archived webpages yet.")

    def _snapshot_icon(self, path: Path | None) -> QIcon:
        # Only read archived local icons; browsing the list never contacts a site.
        if path is not None and path.is_file():
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return QIcon(pixmap)
        return self._default_icon

    def _request_snapshot(self, row: int, column: int):
        if 0 <= row < len(self._snapshots):
            self.snapshot_requested.emit(self._snapshots[row])
