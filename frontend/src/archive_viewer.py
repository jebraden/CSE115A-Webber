from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineScript, QWebEnginePage


class ArchivePage(QWebEnginePage):
    """Navigation stays in the selected local copy instead of visiting live links."""
    allowed_origin = None

    def acceptNavigationRequest(self, url, kind, is_main_frame):
        if url.scheme() in ("about", "data"):
            return True
        if url.isLocalFile():
            return self.allowed_origin is None
        return (url.scheme(), url.host(), url.port()) == self.allowed_origin
from .viewing import DEFAULTS, normalize_preferences, reading_script


class ArchiveViewer(QWebEngineView):
    """
    A Qt widget that displays locally archived webpages.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPage(ArchivePage(self))
        self.viewing_preferences = dict(DEFAULTS)

    def apply_viewing_preferences(self, preferences):
        """Update this page and install the same preferences for future loads."""
        self.viewing_preferences = normalize_preferences(preferences)
        self.setZoomFactor(int(self.viewing_preferences["zoom"][:-1]) / 100)
        scripts = self.page().scripts()
        for existing in scripts.find("webber-reading-preferences"):
            scripts.remove(existing)
        source = reading_script(self.viewing_preferences)
        script = QWebEngineScript()
        script.setName("webber-reading-preferences")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setRunsOnSubFrames(True)
        script.setSourceCode(source)
        scripts.insert(script)
        self.page().runJavaScript(source, QWebEngineScript.ScriptWorldId.ApplicationWorld)


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

    def open_archive_url(self, url: str):
        target = QUrl(url)
        if target.scheme() not in ("http", "https") or not target.host():
            raise ValueError("Invalid local archive address")
        self.page().allowed_origin = (target.scheme(), target.host(), target.port())
        self.load(target)
