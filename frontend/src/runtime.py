"""Own a local backend; health checks and shutdown run outside the GUI thread."""
import asyncio
import atexit
import socket
import threading
import time

import httpx

from .backend import WebberBackend
from .integration_errors import BackendUnavailable


class LocalBackend(WebberBackend):
    def __init__(self, data_dir=None):
        super().__init__()
        self.data_dir = data_dir

    def _build_arguments(self):
        args = super()._build_arguments()
        if self.data_dir is not None:
            args += ["--data-dir", str(self.data_dir)]
        return args


class BackendRuntime:
    def __init__(self, data_dir=None):
        self.backend = LocalBackend(data_dir)
        self.backend.auto_restart = False
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        self.backend.address = f"127.0.0.1:{port}"
        self.base_url = "http://" + self.backend.address
        self._ready = False
        self._stopped = False
        self._lock = threading.Lock()
        atexit.register(self.stop)

    def start(self):
        self.backend.start()

    async def wait_ready(self):
        return await asyncio.to_thread(self._wait_ready)

    def _wait_ready(self):
        if self._ready and self.backend.running:
            return
        deadline = time.monotonic() + 12
        with httpx.Client(timeout=1, trust_env=False) as client:
            while time.monotonic() < deadline:
                if self._stopped or not self.backend.running:
                    raise BackendUnavailable()
                try:
                    response = client.get(self.base_url + "/health")
                    if response.status_code == 200 and response.json().get("status") == "ok":
                        self._ready = True
                        return
                except (httpx.RequestError, ValueError):
                    pass
                time.sleep(0.1)
        raise BackendUnavailable()

    def stop(self):
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
        self.backend.stop()
        self.backend.join(timeout=2)
        if self.backend.running:
            self.backend.kill()
            self.backend.join(timeout=2)

    def stop_async(self):
        threading.Thread(target=self.stop, daemon=False).start()
