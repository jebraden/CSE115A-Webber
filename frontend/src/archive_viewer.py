from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView


class ArchiveViewer(QWebEngineView):
    """
    A Qt widget that displays locally archived webpages.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

    def open_archive(self, file_path: str):
        """
        Load an archived HTML file into the viewer.
        """

        path = Path(file_path).resolve()

        if not path.is_file():
            raise FileNotFoundError(
                f"Archive not found: {path}"
            )

        url = QUrl.fromLocalFile(str(path))

        self.load(url)