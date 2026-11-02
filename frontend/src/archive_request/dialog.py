"""URL submission with backend errors, input preservation and retry."""
import inspect
import logging

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from ..tasks import TaskRunner
from .errors import present_error
from .service import CreateSnapshot, disconnected_service, snapshot_id

logger = logging.getLogger(__name__)


class ArchiveRequestDialog(QDialog):
    archive_created = Signal(str)

    def __init__(self, create_snapshot: CreateSnapshot | None = None, *, demo=False, parent=None):
        super().__init__(parent)
        self._create_snapshot = create_snapshot or disconnected_service
        self._runner = TaskRunner()
        self._runner.result.connect(self._created)
        self._runner.error.connect(self._failed)
        self._request = None
        self._closed = False
        self.setWindowTitle("Webber — Archive URL")
        self.resize(560, 270)
        layout = QVBoxLayout(self)
        if demo:
            layout.addWidget(QLabel("Demo • Simulated backend responses; no webpage is saved."))
        elif create_snapshot is None:
            layout.addWidget(QLabel("Archive service is not connected in this build."))
        label = QLabel("&URL to archive")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/")
        self.url_input.setAccessibleName("URL to archive")
        label.setBuddy(self.url_input)
        layout.addWidget(label)
        layout.addWidget(self.url_input)
        self.error_title = QLabel()
        self.error_title.setTextFormat(Qt.TextFormat.PlainText)
        font = self.error_title.font()
        font.setBold(True)
        self.error_title.setFont(font)
        self.error_title.setAccessibleName("Archive error")
        self.error_detail = QLabel()
        self.error_detail.setTextFormat(Qt.TextFormat.PlainText)
        self.error_detail.setWordWrap(True)
        self.error_detail.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.error_detail.setAccessibleName("Archive error details")
        layout.addWidget(self.error_title)
        layout.addWidget(self.error_detail)
        self.status = QLabel("Enter a URL to archive.")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setAccessibleName("Archiving in progress")
        self.progress.hide()
        layout.addWidget(self.progress)
        buttons = QHBoxLayout()
        buttons.addStretch()
        self.submit_button = QPushButton("Archive")
        self.submit_button.setAutoDefault(False)
        self.submit_button.setEnabled(False)
        self.close_button = QPushButton("Close")
        self.close_button.setAutoDefault(False)
        buttons.addWidget(self.submit_button)
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.submit_button.clicked.connect(self.submit)
        self.url_input.returnPressed.connect(self.submit)
        self.url_input.textChanged.connect(self._input_changed)
        self.close_button.clicked.connect(self.reject)
        self.url_input.setFocus()

    def _clear_error(self):
        self.error_title.clear()
        self.error_detail.clear()

    def _input_changed(self):
        self._clear_error()
        self.submit_button.setText("Archive")
        self.submit_button.setEnabled(bool(self.url_input.text().strip()) and self._request is None)
        self.status.setText("Ready to archive." if self.url_input.text().strip() else "Enter a URL to archive.")

    def _busy(self, busy):
        # A submitted request mutates data: lock input and reject duplicate
        # clicks rather than cancelling/replacing it on each keystroke.
        self.url_input.setEnabled(not busy)
        self.submit_button.setEnabled(not busy and bool(self.url_input.text().strip()))
        self.progress.setVisible(busy)

    def submit(self):
        if self._closed or self._request is not None or not self.submit_button.isEnabled():
            return
        url = self.url_input.text().strip()
        if not url:
            return
        create = self._create_snapshot
        def operation(token):
            value = create(url)
            if inspect.isawaitable(value):
                async def resolve():
                    return snapshot_id(await value)
                return resolve()
            return snapshot_id(value)
        self._clear_error()
        self._busy(True)
        self.status.setText("Archiving…")
        self._request = self._runner.submit(operation)

    @Slot(int, object)
    def _failed(self, request_id, failure):
        if self._closed or request_id != self._request:
            return
        self._request = None
        self._busy(False)
        message = present_error(failure.exception)
        logger.warning("%s: %s", message.title, message.detail)
        logger.debug("Archive request traceback: %s", failure.traceback)
        self.error_title.setText(message.title)
        self.error_detail.setText(message.detail)
        self.status.setText("URL kept. Edit it or retry when ready.")
        self.submit_button.setText("Retry")
        self.url_input.setFocus()

    @Slot(int, object)
    def _created(self, request_id, value):
        if self._closed or request_id != self._request:
            return
        self._request = None
        self._busy(False)
        self._clear_error()
        self.status.setText(f"Snapshot created: {value}")
        # Do not accidentally create the same snapshot again with Enter.
        self.submit_button.setText("Created")
        self.submit_button.setEnabled(False)
        self.archive_created.emit(value)

    def done(self, result):
        if not self._closed:
            self._closed = True
            self._runner.close()
        super().done(result)

    def closeEvent(self, event):
        self._closed = True
        self._runner.close()
        super().closeEvent(event)
