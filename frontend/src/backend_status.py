"""Qt health reporting for WebberBackend; does not launch/manage processes."""
from concurrent.futures import ThreadPoolExecutor

import httpx
from PySide6.QtCore import QObject, QTimer, Signal

from .backend import State, ExecFailed


def check_health(address):
    if address.startswith("unix://"):
        transport = httpx.HTTPTransport(uds=address.removeprefix("unix://"))
        url = "http://localhost/health"
    else:
        transport = httpx.HTTPTransport()
        url = f"http://{address}/health"
    try:
        with httpx.Client(transport=transport, timeout=0.5, trust_env=False) as client:
            response = client.get(url)
            return response.status_code == 200 and response.json().get("status") == "ok"
    except (httpx.HTTPError, ValueError, AttributeError):
        return False


class BackendStatus(QObject):
    ready = Signal()
    failed = Signal(str)

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="backend-health")
        self.future = None
        self.healthy = False
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._check)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.setInterval(10000)
        self.deadline.timeout.connect(lambda: self._fail("Backend startup timed out."))

    def start(self):
        self.timer.start()
        self.deadline.start()

    def _check(self):
        if self.backend.state != State.RUNNING:
            exit_code = self.backend.exit_code
            if isinstance(exit_code, ExecFailed):
                self._fail(f"Could not run backend: {exit_code.strerror}")
            else:
                self._fail(f"Backend exited: {exit_code}")
            return
        if self.healthy:
            return
        if self.future is not None:
            if not self.future.done():
                return
            healthy = self.future.result()
            self.future = None
            if healthy:
                self.healthy = True
                self.deadline.stop()
                self.ready.emit()
                return
        self.future = self.pool.submit(check_health, self.backend.address)

    def _fail(self, message):
        self.stop()
        self.failed.emit(message)

    def stop(self):
        self.timer.stop()
        self.deadline.stop()
        if not self.closed:
            self.closed = True
            self.pool.shutdown(wait=False, cancel_futures=True)
