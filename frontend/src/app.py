"""Application lifecycle and assembly; widgets and OS details live separately."""
import os
import sys
import tempfile

from PySide6.QtCore import QTimer, qInfo
from PySide6.QtWidgets import QApplication

from . import __version__
from .backend import WebberBackend
from .backend_status import BackendStatus
from .platforms import make_signal_handler
from .startup_window import StartupWindow


def main(backend_address=None):
    app = QApplication(sys.argv)
    app.setApplicationName("Webber")
    app.setApplicationVersion(__version__)
    signals = make_signal_handler(app)
    signals.install()
    signals.signal_recieved.connect(lambda signum: app.exit(128 + signum))

    backend = WebberBackend()
    # A private short socket path avoids collisions with other running instances
    # and macOS's AF_UNIX path-length limit. TCP remains the Windows fallback.
    socket_dir = tempfile.TemporaryDirectory(prefix="webber-", dir="/tmp") if os.name == "posix" and backend_address is None else None
    if socket_dir:
        backend.address = f"unix://{socket_dir.name}/backend.sock"
    elif backend_address is not None:
        backend.address = backend_address
    backend.auto_restart = False
    status = BackendStatus(backend, app)
    window = StartupWindow()
    status.ready.connect(window.backend_ready)
    status.failed.connect(window.backend_failed)

    def stop():
        status.stop()
        backend.auto_restart = False
        backend.stop()
        backend.join(timeout=2)
        if backend.running:
            backend.kill()
            backend.join(timeout=2)

    def start():
        backend.start()
        status.start()

    app.aboutToQuit.connect(stop)
    window.show()
    QTimer.singleShot(0, start)
    qInfo(f"Webber {__version__} frontend starting")
    try:
        return app.exec()
    finally:
        stop()
        signals.uninstall()
        if hasattr(signals, "close"):
            signals.close()
        if socket_dir:
            socket_dir.cleanup()
