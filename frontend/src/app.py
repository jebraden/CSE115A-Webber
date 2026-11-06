import sys
from . import __version__
from PySide6.QtWidgets import QApplication
import PySide6.QtAsyncio as QtAsyncio
from PySide6.QtCore import qInfo


def main():
    """Main frontend entrypoint."""

    app = QApplication(sys.argv)

    app.setApplicationName("Webber")
    app.setApplicationVersion(__version__)

    qInfo(f"Webber {__version__} frontend starting")

    QtAsyncio.run(handle_sigint=True)
