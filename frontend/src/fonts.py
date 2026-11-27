"""Installed font families saved in Webber's dropdown."""

from PySide6.QtGui import QFontDatabase


class FontLibrary:
    def __init__(self, settings):
        self.settings = settings

    def _saved(self):
        value = self.settings.value("fonts/favorites", [])
        return [value] if isinstance(value, str) else list(value or [])

    def remember(self, family):
        families = self._saved()
        if family not in families:
            self.settings.setValue("fonts/favorites", families + [family])
            self.settings.sync()

    def families(self):
        available = set(QFontDatabase.families())
        return list(
            dict.fromkeys(family for family in self._saved() if family in available)
        )
