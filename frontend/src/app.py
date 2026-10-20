import signal
import sys

from PySide6.QtCore import QObject, QTimer, Signal, qInfo
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QVBoxLayout, QWidget

from . import __version__
from .backend_process import BackendProcess


class SignalHandler(QObject):
    """Let Python handle termination signals while the Qt event loop is idle."""
    signal_recieved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._previous = {}
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(lambda: None)

    def install(self):
        if self._previous:
            return
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous[signum] = signal.signal(signum, self._received)
        self._timer.start()

    def _received(self, signum, frame):
        self.signal_recieved.emit(signum)

    def uninstall(self):
        self._timer.stop()
        for signum, handler in self._previous.items():
            signal.signal(signum, handler)
        self._previous.clear()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Webber")
    app.setApplicationVersion(__version__)
    signals = SignalHandler(app)
    signals.install()
    signals.signal_recieved.connect(lambda signum: app.exit(128 + signum))

    # A small status window makes this startup-only branch testable on desktop.
    window = QWidget()
    window.setWindowTitle("Webber")
    window.resize(480, 160)
    layout = QVBoxLayout(window)
    status = QLabel("Starting backend…")
    status.setWordWrap(True)
    layout.addWidget(status)
    close = QPushButton("Close")
    close.clicked.connect(window.close)
    layout.addWidget(close)
    backend = BackendProcess(app)
    backend.ready.connect(lambda: status.setText("Backend is running at http://127.0.0.1:3000"))
    backend.failed.connect(lambda message: status.setText(message))
    app.aboutToQuit.connect(backend.stop)
    window.show()
    QTimer.singleShot(0, backend.start)
    qInfo(f"Webber {__version__} frontend starting")
    try:
        return app.exec()
    finally:
        backend.stop()
        signals.uninstall()
