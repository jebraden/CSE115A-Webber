"""macOS signal handling, isolated from the event-driven socket bridge."""
import signal
from PySide6.QtCore import QObject, QTimer, Signal


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
