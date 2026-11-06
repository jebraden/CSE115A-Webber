"""Keep the original signal wakeup-fd/socket approach for Linux and Windows."""
import signal
import socket

from PySide6.QtCore import Signal
from PySide6.QtNetwork import QAbstractSocket


class SignalHandler(QAbstractSocket):
    signal_recieved = Signal(int)

    def __init__(self, parent=None):
        super().__init__(QAbstractSocket.SocketType.TcpSocket, parent)
        self._previous = {}
        self._old_fd = None
        self._write_sock, reader = socket.socketpair(type=socket.SOCK_STREAM)
        self._write_sock.setblocking(False)
        reader.setblocking(False)
        self.setSocketDescriptor(reader.detach())
        self.readyRead.connect(self._ready_read)

    def _ready_read(self):
        for signum in bytes(self.readAll()):
            self.signal_recieved.emit(signum)

    def install(self):
        if self._old_fd is not None:
            return
        # Prevent Python's default SIGINT handler raising before Qt drains it.
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous[signum] = signal.signal(signum, lambda *_: None)
        self._old_fd = signal.set_wakeup_fd(self._write_sock.fileno())

    def uninstall(self):
        if self._old_fd is not None:
            signal.set_wakeup_fd(self._old_fd)
            self._old_fd = None
        for signum, previous in self._previous.items():
            signal.signal(signum, previous)
        self._previous.clear()

    def close(self):
        self.uninstall()
        super().close()
        self._write_sock.close()
