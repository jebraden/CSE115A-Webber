"""Own the backend process and report readiness without blocking the Qt UI."""
import json
import os
from pathlib import Path
import socket
import sys

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest


class BackendProcess(QObject):
    ready = Signal()
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.ForwardedChannels)
        self.process.errorOccurred.connect(self._process_error)
        self.process.finished.connect(self._finished)
        self.network = QNetworkAccessManager(self)
        self.poll = QTimer(self)
        self.poll.setInterval(150)
        self.poll.timeout.connect(self._check_health)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(10000)
        self.deadline.timeout.connect(lambda: self._fail("Backend startup timed out."))
        self.reply = None
        self.stopping = False
        self.failed_once = False

    def start(self):
        # Never attach to, or terminate, an unrelated service on this port.
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("127.0.0.1", 3000))
        except OSError:
            self._fail("Port 3000 is already in use. Close the other service and restart Webber.")
            return
        self.process.setWorkingDirectory(str(Path(__file__).resolve().parents[2]))
        self.process.start(sys.executable, [
            "-m", "backend.src", "--die-with-parent", "--ppid", str(os.getpid()),
        ])
        self.deadline.start()
        self.poll.start()

    def _check_health(self):
        if self.reply is not None or self.process.state() != QProcess.ProcessState.Running:
            return
        request = QNetworkRequest(QUrl("http://127.0.0.1:3000/health"))
        request.setTransferTimeout(500)
        self.reply = self.network.get(request)
        self.reply.finished.connect(self._health_finished)

    def _health_finished(self):
        reply, self.reply = self.reply, None
        if reply is None:
            return
        ok = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute) == 200
        body = bytes(reply.readAll())
        reply.deleteLater()
        if self.stopping or self.failed_once:
            return
        try:
            healthy = ok and json.loads(body).get("status") == "ok"
        except (ValueError, AttributeError):
            healthy = False
        if healthy and self.process.state() == QProcess.ProcessState.Running:
            self.poll.stop()
            self.deadline.stop()
            self.ready.emit()

    def _process_error(self, error):
        if not self.stopping:
            self._fail("Could not run backend: " + self.process.errorString())

    def _finished(self, code, status):
        if not self.stopping:
            self._fail(f"Backend exited unexpectedly (code {code}).")

    def _fail(self, message):
        if self.stopping or self.failed_once:
            return
        self.failed_once = True
        self.stop()
        self.failed.emit(message)

    def stop(self):
        self.stopping = True
        self.poll.stop()
        self.deadline.stop()
        if self.reply is not None:
            self.reply.abort()
        if self.process.state() != QProcess.ProcessState.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(2000):
                self.process.kill()
                self.process.waitForFinished(2000)
