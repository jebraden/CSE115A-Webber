"""Exercise the macOS parent-exit hook using the backend's HTTP server."""

import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time

import httpx
import pytest


LAUNCH_BACKEND = """
import os
import subprocess
import sys

backend_code = '''
import sys
from src import app
app.db_path = sys.argv.pop(1)
app.main()
'''
child = subprocess.Popen([
    sys.executable, "-c", backend_code, sys.argv[1], "--production",
    "--unix-socket", sys.argv[2], "--die-with-parent", "--ppid", str(os.getpid()),
])
raise SystemExit(child.wait())
"""


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS parent-exit hook")
def test_backend_stops_when_its_parent_is_force_quit(tmp_path):
    backend_dir = Path(__file__).resolve().parents[1]
    database_path = tmp_path / "archive.db"
    log_path = tmp_path / "backend.log"
    # Unix socket paths have a short platform limit.
    with tempfile.TemporaryDirectory(prefix="webber-exit-", dir="/tmp") as socket_dir:
        socket_path = str(Path(socket_dir) / "backend.sock")
        with log_path.open("w") as log:
            parent = subprocess.Popen(
                [sys.executable, "-c", LAUNCH_BACKEND, str(database_path), socket_path],
                cwd=backend_dir,
                stdout=subprocess.PIPE,
                stderr=log,
                start_new_session=True,
            )
        try:
            with httpx.Client(transport=httpx.HTTPTransport(uds=socket_path), timeout=0.3) as client:
                def backend_responds():
                    try:
                        return client.get("http://localhost/health").status_code == 200
                    except httpx.TransportError:
                        return False

                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and parent.poll() is None:
                    if backend_responds():
                        break
                    time.sleep(0.05)
                else:
                    pytest.fail(f"Backend did not start:\n{log_path.read_text()}")

                parent.kill()
                parent.wait(timeout=5)

                # Both processes inherit stdout. EOF confirms that the backend
                # exited too, rather than merely losing its listening socket.
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    ready, _, _ = select.select([parent.stdout], [], [], max(0, deadline - time.monotonic()))
                    if ready and not os.read(parent.stdout.fileno(), 4096):
                        break
                else:
                    pytest.fail("Backend was still running after its parent exited")
        finally:
            # Clean up the two subprocesses even when the assertion fails.
            try:
                os.killpg(parent.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            parent.wait(timeout=5)
            parent.stdout.close()
