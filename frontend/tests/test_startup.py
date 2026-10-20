"""Real process checks for frontend/backend lifetime on the current OS."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[2]


def health():
    try:
        with urllib.request.urlopen("http://127.0.0.1:3000/health", timeout=0.2) as response:
            return json.load(response) == {"status": "ok"}
    except (OSError, ValueError):
        return False


def wait_for(predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def free_port():
    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", 3000))
        except OSError:
            pytest.skip("Port 3000 is in use by another application")


@pytest.mark.parametrize("ending", ["close", "interrupt", "terminate", "kill"])
def test_backend_follows_frontend_lifetime(free_port, tmp_path, ending):
    close_file = tmp_path / "close"
    script = '''
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from frontend.src import app
original = app.QApplication
control = Path(__import__('sys').argv[1])
def create(args):
    application = original(args)
    application.control_timer = QTimer(application)
    def check():
        if control.exists():
            for window in application.topLevelWidgets():
                window.close()
    application.control_timer.timeout.connect(check)
    application.control_timer.start(50)
    return application
app.QApplication = create
raise SystemExit(app.main())
'''
    log = (tmp_path / "process.log").open("w+")
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(close_file)], cwd=ROOT,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        stdout=log, stderr=log, start_new_session=True,
    )
    try:
        assert wait_for(health), "Backend never became healthy"
        assert process.poll() is None
        if ending == "close":
            close_file.touch()
            expected = 0
        else:
            signum = {"interrupt": signal.SIGINT, "terminate": signal.SIGTERM, "kill": signal.SIGKILL}[ending]
            process.send_signal(signum)
            expected = -signum if ending == "kill" else 128 + signum
        assert process.wait(timeout=8) == expected
        assert wait_for(lambda: not health(), timeout=5), "Backend survived frontend exit"
        log.seek(0)
        output = log.read()
        assert "Traceback" not in output
        assert "Cannot copy-convert" not in output
    finally:
        # This process group belongs only to this test (including its backend).
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        log.close()


def test_busy_port_does_not_kill_other_service(free_port):
    from PySide6.QtWidgets import QApplication
    from frontend.src.backend_process import BackendProcess
    app = QApplication.instance() or QApplication([])
    with socket.socket() as server:
        server.bind(("127.0.0.1", 3000))
        server.listen()
        controller = BackendProcess()
        errors = []
        controller.failed.connect(errors.append)
        controller.start()
        assert errors and "already in use" in errors[0]
        assert controller.process.processId() == 0
        assert server.getsockname()[1] == 3000
        controller.stop()


def test_failed_launch_reports_error_and_stops(free_port, monkeypatch):
    from PySide6.QtWidgets import QApplication
    from frontend.src import backend_process
    app = QApplication.instance() or QApplication([])
    controller = backend_process.BackendProcess()
    errors = []
    controller.failed.connect(errors.append)
    monkeypatch.setattr(backend_process.sys, "executable", "/nonexistent-webber-python")
    controller.start()
    def received_error():
        app.processEvents()
        return bool(errors)
    assert wait_for(received_error, timeout=3)
    assert "Could not run backend" in errors[0]
    assert controller.process.processId() == 0
    controller.stop()
