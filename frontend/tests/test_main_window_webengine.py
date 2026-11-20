"""Exercise the real browser in a fresh process so native crashes fail the test."""

import os
from pathlib import Path
import subprocess
import sys
import textwrap


def test_open_archives_and_accept_font_dialog_without_native_crash():
    script = textwrap.dedent("""
        import tempfile
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtGui import QFont
        from PySide6.QtWidgets import QApplication, QFontDialog
        from frontend.src.main_window import MainWindow
        from frontend.src.archive_list.service import MockSnapshotService, UI_DEMO_SNAPSHOTS

        app = QApplication([])
        app.setQuitOnLastWindowClosed(False)
        temporary = tempfile.TemporaryDirectory()
        settings = QSettings(temporary.name + "/settings.ini", QSettings.Format.IniFormat)
        window = MainWindow(MockSnapshotService(UI_DEMO_SNAPSHOTS), demo=True, settings=settings)
        window.show()
        completed = False

        def finish(ok):
            global completed
            assert ok
            assert window.tab_bar.count() == 2
            assert window.viewing_preferences["text_size"] == "18 pt"
            completed = True
            window.close()
            app.quit()

        def accept_font():
            dialog = QApplication.activeModalWidget()
            assert isinstance(dialog, QFontDialog)
            font = QFont(dialog.currentFont())
            font.setPointSize(18)
            dialog.setCurrentFont(font)
            dialog.accept()

        def first_loaded(ok):
            assert ok
            QTimer.singleShot(0, accept_font)
            window.ui.addFontButton.click()
            window.open_in_tab(UI_DEMO_SNAPSHOTS[1])
            window.viewer.loadFinished.connect(finish)

        def begin():
            window.open_in_tab(UI_DEMO_SNAPSHOTS[0])
            window.viewer.loadFinished.connect(first_loaded)

        QTimer.singleShot(100, begin)
        QTimer.singleShot(15000, app.quit)
        app.exec()
        assert completed, "Archive loading/font dialog did not finish"
        print("REAL_ARCHIVE_AND_FONT_DIALOG_OK")
    """)
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen", "PYTHONFAULTHANDLER": "1"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REAL_ARCHIVE_AND_FONT_DIALOG_OK" in result.stdout
