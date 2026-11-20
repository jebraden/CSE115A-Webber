"""Adding installed fonts keeps them in Webber's menu after restarting."""

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
import pytest

from frontend.src import main_window
from frontend.src.archive_list.service import MockSnapshotService
from frontend.tests.test_main_window import ViewerDouble


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_add_font_opens_font_list_and_persists_menu(app, monkeypatch, tmp_path):
    monkeypatch.setattr(main_window, "ArchiveViewer", ViewerDouble)
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = main_window.MainWindow(MockSnapshotService([]), settings=settings)
    family = next(
        name
        for name in ("Arial", "DejaVu Sans", "Liberation Sans", "Helvetica")
        if name in QFontDatabase.families()
    )

    def select_font():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, main_window.QFontDialog)
        assert dialog.testOption(
            main_window.QFontDialog.FontDialogOption.DontUseNativeDialog
        )
        buttons = dialog.findChild(main_window.QDialogButtonBox)
        confirm = buttons.button(main_window.QDialogButtonBox.StandardButton.Ok)
        cancel = buttons.button(main_window.QDialogButtonBox.StandardButton.Cancel)
        assert confirm.isVisible() and confirm.text() == "Add font"
        assert cancel.isVisible()
        dialog.setCurrentFont(QFont(family, 18))
        confirm.click()

    try:
        QTimer.singleShot(0, select_font)
        window.ui.addFontButton.click()
        assert window.ui.fontCombo.currentText() == family
        window.ui.fontCombo.setCurrentText("Serif")
        restored = main_window.MainWindow(MockSnapshotService([]), settings=settings)
        try:
            assert restored.ui.fontCombo.currentText() == "Serif"
            assert restored.ui.fontCombo.findText(family) >= 0
            restored.ui.fontCombo.setCurrentText(family)
            assert restored.viewer.viewing_preferences["font"] == family
            restored.reset_viewing_preferences()
            assert restored.ui.fontCombo.findText(family) >= 0
            before = dict(restored.viewing_preferences)
            QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
            restored.ui.addFontButton.click()
            assert restored.viewing_preferences == before
        finally:
            restored.close()
    finally:
        window.close()
