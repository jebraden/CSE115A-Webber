"""Compose the central UI, shared API and owned backend on QtAsyncio."""
import argparse
from pathlib import Path
import sys

from PySide6.QtWidgets import QApplication
import PySide6.QtAsyncio as QtAsyncio

from . import __version__
from .api import WebberAPI
from .archive_list.service import MockSnapshotService, UI_DEMO_SNAPSHOTS
from .archive_service import ArchiveService
from .main_window import MainWindow
from .runtime import BackendRuntime


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--"]:
        args.pop(0)
    parser = argparse.ArgumentParser(description="Webber local webpage archive")
    parser.add_argument("--demo", action="store_true", help="show bundled sample archives")
    parser.add_argument("--data-dir", type=Path, help="archive database and files directory")
    parser.add_argument("--backend-url", help="connect to an existing backend")
    options = parser.parse_args(args)
    if options.demo and options.backend_url:
        parser.error("--demo and --backend-url cannot be combined")
    app = QApplication([sys.argv[0]])
    app.setApplicationName("Webber")
    app.setApplicationVersion(__version__)
    runtime = None
    window = None

    async def start():
        nonlocal runtime, window
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
            service = ArchiveService(WebberAPI(base_url),
                wait_ready=runtime.wait_ready if runtime else None)
            create = service.create_snapshot
        window = MainWindow(service, create_snapshot=create, demo=options.demo)
        window.show()

    try:
        QtAsyncio.run(start(), handle_sigint=True)
    finally:
        if window is not None:
            window.close()
        if runtime is not None:
            runtime.stop_async()
    return 0
