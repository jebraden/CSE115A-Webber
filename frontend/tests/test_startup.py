"""Exercise the actual frontend and backend over a private Unix socket."""
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX lifecycle tests")


def health(path):
    try:
        with httpx.Client(transport=httpx.HTTPTransport(uds=str(path)), timeout=0.2) as client:
            response = client.get("http://localhost/health")
            return response.status_code == 200 and response.json() == {"status": "ok"}
    except (OSError, httpx.HTTPError, ValueError):
        return False


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def socket_path():
    # pytest's full temporary path can exceed AF_UNIX's limit on macOS.
    with tempfile.TemporaryDirectory(prefix="webber-test-", dir="/tmp") as folder:
        yield Path(folder) / "backend.sock"


@pytest.mark.parametrize("ending", ["close", "interrupt", "terminate", "kill"])
def test_backend_follows_frontend_lifetime(socket_path, tmp_path, ending):
    close_file = tmp_path / "close"
    ready_file = tmp_path / "ready"
    script = '''
from pathlib import Path
import sys
from PySide6.QtCore import QTimer
from frontend.src import app
from frontend.src.startup_window import StartupWindow
original = app.QApplication
control, ready = Path(sys.argv[1]), Path(sys.argv[3])
def create(args):
    application = original(args)
    application.control_timer = QTimer(application)
    def check():
        for window in application.topLevelWidgets():
            if isinstance(window, StartupWindow):
                if window.status.text() == "Backend is ready.":
                    ready.touch()
                if control.exists():
                    window.close()
    application.control_timer.timeout.connect(check)
    application.control_timer.start(50)
    return application
app.QApplication = create
raise SystemExit(app.main(backend_address="unix://" + sys.argv[2]))
'''
    log_path = tmp_path / "process.log"
    with log_path.open("w+") as log:
        process = subprocess.Popen(
            [sys.executable, "-c", script, str(close_file), str(socket_path), str(ready_file)],
            cwd=ROOT, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
            stdout=log, stderr=log, start_new_session=True,
        )
        try:
            wait_for(lambda: ready_file.exists() or process.poll() is not None)
            assert ready_file.exists() and process.poll() is None, log_path.read_text()
            assert health(socket_path)
            if ending == "close":
                close_file.touch()
                expected = 0
            else:
                signum = {"interrupt": signal.SIGINT, "terminate": signal.SIGTERM, "kill": signal.SIGKILL}[ending]
                process.send_signal(signum)
                expected = -signum if ending == "kill" else 128 + signum
            assert process.wait(timeout=8) == expected
            assert wait_for(lambda: not health(socket_path), timeout=5), "Backend survived frontend exit"
            output = log_path.read_text()
            assert "Traceback" not in output
            assert "Cannot copy-convert" not in output
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)


def test_signal_handler_is_platform_specific():
    from PySide6.QtCore import QCoreApplication, QTimer
    from frontend.src.platforms import make_signal_handler
    app = QCoreApplication.instance() or QCoreApplication([])
    handler = make_signal_handler(app)
    expected = "macos" if sys.platform == "darwin" else "socket_signals"
    assert handler.__class__.__module__.endswith(expected)
    previous = {signum: signal.getsignal(signum) for signum in (signal.SIGINT, signal.SIGTERM)}
    handler.install()
    handler.uninstall()
    assert all(signal.getsignal(signum) == value for signum, value in previous.items())
    if expected == "socket_signals":
        assert not handler.findChildren(QTimer)
        handler.close()


def test_health_reports_launch_failure(monkeypatch):
    from PySide6.QtCore import QCoreApplication
    from frontend.src.backend import WebberBackend
    from frontend.src.backend_status import BackendStatus
    app = QCoreApplication.instance() or QCoreApplication([])
    backend = WebberBackend()
    monkeypatch.setattr(backend, "_build_arguments", lambda: ["/nonexistent-webber-python"])
    backend.start()
    status = BackendStatus(backend)
    errors = []
    status.failed.connect(errors.append)
    status.start()
    def received_error():
        app.processEvents()
        return bool(errors)
    try:
        assert wait_for(received_error, timeout=3)
        assert "Could not run backend" in errors[0]
    finally:
        status.stop()


def test_join_timeout_does_not_block_forever(tmp_path):
    from frontend.src.backend import WebberBackend
    backend = WebberBackend()
    backend.auto_restart = False
    backend._build_arguments = lambda: [sys.executable, "-c", "import time; time.sleep(30)"]
    backend.start()
    try:
        start = time.monotonic()
        backend.join(timeout=0.05)
        assert time.monotonic() - start < 1
        assert backend.running
    finally:
        backend.kill()
        backend.join(timeout=3)


def test_child_receives_frontend_pid():
    from frontend.src.backend import WebberBackend
    args = WebberBackend()._build_arguments()
    assert args[args.index("--ppid") + 1] == str(os.getpid())


def test_worker_can_read_backend_state():
    from concurrent.futures import ThreadPoolExecutor
    from frontend.src.backend import WebberBackend, State
    backend = WebberBackend()
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(lambda: backend.state).result(timeout=1) == State.STOPPED


def test_unix_socket_leaves_tcp_port_available(socket_path):
    # A TCP service already on 3000 must not prevent the default POSIX backend.
    from frontend.src.backend import WebberBackend
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", 3000))
        except OSError:
            pytest.skip("Port 3000 is already occupied")
        listener.listen()
        backend = WebberBackend()
        backend.auto_restart = False
        backend.address = "unix://" + str(socket_path)
        backend.start()
        try:
            assert wait_for(lambda: health(socket_path))
            assert listener.getsockname()[1] == 3000
        finally:
            backend.stop()
            backend.join(timeout=2)
            if backend.running:
                backend.kill()
                backend.join(timeout=2)
