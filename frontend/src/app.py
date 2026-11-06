"""Compose the central UI, shared API, and owned local backend."""
import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication

from . import __version__
from .api import WebberAPI
from .archive_list.service import MockSnapshotService, UI_DEMO_SNAPSHOTS
from .archive_service import ArchiveService
from .main_window import MainWindow
from .platforms import make_signal_handler
from .runtime import BackendRuntime


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--"]:
        args.pop(0)
    parser = argparse.ArgumentParser(description="Webber local webpage archive")
    parser.add_argument("--demo", action="store_true", help="show bundled sample archives")
    parser.add_argument("--data-dir", type=Path, help="directory for the managed backend's archive database and files")
    parser.add_argument("--backend-url", help="connect to an existing backend instead of launching one")
    options = parser.parse_args(args)
    if options.demo and options.backend_url:
        parser.error("--demo and --backend-url cannot be combined")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Webber")
    app.setApplicationVersion(__version__)
    signals = make_signal_handler(app)
    signals.install()
    signals.signal_recieved.connect(lambda signum: app.exit(128 + signum))
    runtime = None
    if options.demo:
        service = MockSnapshotService(UI_DEMO_SNAPSHOTS)
        create = None
    else:
        if options.backend_url:
            base_url = options.backend_url
        else:
            runtime = BackendRuntime(options.data_dir)
            runtime.start()
            app.aboutToQuit.connect(runtime.stop_async)
            base_url = runtime.base_url
        service = ArchiveService(
            WebberAPI(base_url), wait_ready=runtime.wait_ready if runtime else None,
        )
        create = service.create_snapshot
    window = MainWindow(service, create_snapshot=create, demo=options.demo)
    window.show()
    try:
        return app.exec()
    finally:
        window.close()
        signals.uninstall()
        if runtime:
            runtime.stop_async()
