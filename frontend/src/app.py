import sys
import socket
import signal
from . import __version__
from .archive_list.service import MockSnapshotService
from .archive_list.window import ArchiveWindow
from PySide6.QtCore import Signal, qInfo
from PySide6.QtWidgets import QApplication
from PySide6.QtNetwork import QAbstractSocket


# Credit: https://stackoverflow.com/a/37229299
class SignalHandler(QAbstractSocket):
    """Cause the Python interpreter to run every time the process receives a
    signal. Because some signals (e.g. SIGINT) just cause the Python
    interpreter to set a flag and then continue until the next bytecode
    instruction is executed, signals are never handled if we are just stuck in
    the Qt event loop. This causes a python function to run on every singal.
    """

    signal_recieved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(QAbstractSocket.SocketType.UdpSocket, parent)

        self._old_fd = None

        self._write_sock, self._read_sock = socket.socketpair(
            type=socket.SOCK_DGRAM
        )
        self._write_sock.setblocking(False)

        # Need two, one to trigger the signal, one to read the data/emit the
        # event
        self.readyRead.connect(lambda: None)
        self.readyRead.connect(self._ready_read)
        self.setSocketDescriptor(self._read_sock.fileno())

    def _ready_read(self):
        # Will not trigger again until we read this...
        signum = self.readData(1)[0]
        self.signal_recieved.emit(signum)

    def install(self):
        if self._old_fd is not None:
            self.uninstall()
        self._old_fd = signal.set_wakeup_fd(self._write_sock.fileno())

    def uninstall(self):
        if self._old_fd is not None:
            signal.set_wakeup_fd(self._old_fd)
            self._old_fd = None

    def __del__(self):
        self.uninstall()


def main():
    """Main frontend entrypoint."""

    app = QApplication(sys.argv)

    signal_handler = SignalHandler(app)
    signal_handler.install()

    signal_handler.signal_recieved.connect(
        lambda signum: app.exit(128 + signum)
    )

    app.setApplicationName("Webber")
    app.setApplicationVersion(__version__)

    qInfo(f"Webber {__version__} frontend starting")

    window = ArchiveWindow(MockSnapshotService(), demo=True)
    window.show()

    return app.exec()
