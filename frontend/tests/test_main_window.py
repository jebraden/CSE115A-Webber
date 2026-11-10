"""Central-shell interaction tests; Chromium itself is tested by a GUI smoke run."""

from datetime import datetime, timezone
from pathlib import Path
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QSettings
from PySide6.QtWidgets import QApplication, QWidget
from frontend.src.archive_list.service import MockSnapshotService, Snapshot
from frontend.src import main_window


class ViewerDouble(QWidget):
    def apply_viewing_preferences(self, preferences):
        self.viewing_preferences = dict(preferences)

    def open_archive(self, path):
        self.path = path

    def setHtml(self, html):
        self.html = html


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch, tmp_path):
    monkeypatch.setattr(main_window, "ArchiveViewer", ViewerDouble)
    html = tmp_path / "page.html"
    html.write_text("<h1>Saved page</h1>")
    snapshots = [
        Snapshot("valid", "https://example.org/", datetime.now(timezone.utc), html),
        Snapshot("missing", "https://missing.example/", datetime.now(timezone.utc)),
    ]
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    win = main_window.MainWindow(
        MockSnapshotService(snapshots), demo=True, settings=settings
    )
    yield win
    win.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def select(window, snapshot_id):
    for i, snapshot in enumerate(window._snapshots):
        if snapshot.id == snapshot_id:
            window.ui.snapshotList.setCurrentRow(i)
            return
    raise AssertionError(snapshot_id)


def test_navigation_embeds_statistics_panel(window):
    window.ui.statisticsButton.click()
    assert window.ui.mainStack.currentWidget() is window.ui.statisticsPage
    assert window.statistics_widget is not None
    assert window.statistics_widget.parent() is window.ui.statisticsPage
    assert (
        window.statistics_widget.stacked_content.currentWidget()
        is window.statistics_widget.init_page
    )
    window.ui.archivesButton.click()
    assert window.ui.mainStack.currentWidget() is window.ui.archivesPage


def test_selection_opens_embedded_tab_and_raw_html(window):
    select(window, "valid")
    assert window.tab_bar.count() == 1
    assert window.ui.viewerStack.currentWidget() is window.ui.webPage
    assert "<h1>Saved page</h1>" == window.ui.rawHtml.toPlainText()
    window.ui.rawButton.click()
    assert window.ui.viewerStack.currentWidget() is window.ui.rawPage
    window.ui.pageButton.click()
    assert window.ui.viewerStack.currentWidget() is window.ui.webPage


def test_missing_file_clears_previous_content(window):
    select(window, "valid")
    select(window, "missing")
    assert window.ui.viewerStack.currentWidget() is window.ui.emptyPage
    assert not window.ui.openWindowButton.isEnabled()
    assert window.ui.rawHtml.toPlainText() == ""
    assert window.viewer.html == ""


def test_search_keeps_open_tab_and_filters(window):
    select(window, "valid")
    window.ui.searchInput.setText("missing.example")
    assert window.ui.snapshotList.count() == 1
    assert window._snapshot.id == "valid"
    assert window.ui.openWindowButton.isEnabled()
    window.ui.searchInput.setText("no-match")
    assert window.ui.snapshotList.count() == 0
    assert window._snapshot.id == "valid"
    assert window.ui.viewerStack.currentWidget() is window.ui.webPage


def test_popout_keeps_embedded_selection_and_reuses_window(window):
    select(window, "valid")
    selected = window._snapshot
    window.open_in_window(selected)
    popup = window._windows["valid"]
    assert popup.centralWidget().path == str(selected.local_path.resolve())
    window.open_in_window(selected)
    assert len(window._windows) == 1
    assert window._snapshot is selected
    popup.close()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert window._windows == {}


def test_capture_emits_only_valid_urls_without_false_success(window):
    requests = []
    window.capture_requested.connect(requests.append)
    window.ui.urlInput.setText("bad link")
    window.ui.captureButton.click()
    assert requests == []
    window.ui.urlInput.setText("https://example.org/")
    window.ui.captureButton.click()
    assert requests == ["https://example.org/"]
    assert window.ui.captureStatus.text() == "Saving is unavailable."


def test_appearance_changes_persist_without_losing_archive(window):
    select(window, "valid")
    window.ui.rawButton.click()
    html = window.ui.rawHtml.toPlainText()
    window.ui.settingsButton.click()
    assert window.ui.mainStack.currentWidget() is window.ui.settingsPage
    window.ui.darkModeButton.click()
    assert window.theme == "dark"
    assert window.settings.value("appearance/theme") == "dark"
    assert window.ui.darkModeButton.isChecked()
    assert not window.ui.lightModeButton.isChecked()
    assert window._snapshot.id == "valid"
    assert window.ui.rawHtml.toPlainText() == html
    window.ui.archivesButton.click()
    assert window.ui.viewerStack.currentWidget() is window.ui.rawPage
    restored = main_window.MainWindow(MockSnapshotService([]), settings=window.settings)
    try:
        assert restored.theme == "dark"
        restored.ui.lightModeButton.click()
        assert restored.theme == "light"
        assert window.settings.value("appearance/theme") == "light"
    finally:
        restored.close()


def test_all_ui_demo_snapshots_have_local_html_and_assets():
    from html.parser import HTMLParser
    from urllib.parse import urlsplit, unquote
    from frontend.src.archive_list.service import UI_DEMO_SNAPSHOTS

    class LocalAssets(HTMLParser):
        def handle_starttag(self, tag, attrs):
            for name, value in attrs:
                if name in ("src", "href") and value:
                    url = urlsplit(value)
                    if not url.scheme and url.path:
                        assert (self.base / unquote(url.path)).is_file(), value

    assert len(UI_DEMO_SNAPSHOTS) == 9
    for snapshot in UI_DEMO_SNAPSHOTS:
        assert snapshot.local_path.is_file()
        parser = LocalAssets()
        parser.base = snapshot.local_path.parent
        parser.feed(snapshot.local_path.read_text())


def test_viewing_settings_reach_current_and_new_windows_and_restore(window):
    select(window, "valid")
    original = window.ui.rawHtml.toPlainText()
    window.ui.pageZoomInput.setValue(125)
    window.ui.textSizeInput.setValue(18)
    window.ui.fontCombo.setCurrentText("Serif")
    window.open_in_window(window._snapshot)
    popup = window._windows["valid"]
    assert popup.centralWidget().viewing_preferences == window.viewing_preferences
    window.ui.lineSpacingCombo.setCurrentText("Comfortable")
    assert popup.centralWidget().viewing_preferences["spacing"] == "Comfortable"
    assert window.viewer.viewing_preferences["text_size"] == "18 pt"
    assert window.ui.rawHtml.toPlainText() == original
    assert window._snapshot.local_path.read_text() == original
    restored = main_window.MainWindow(MockSnapshotService([]), settings=window.settings)
    try:
        assert restored.ui.pageZoomInput.value() == 125
        assert restored.ui.fontCombo.currentText() == "Serif"
        restored.ui.resetSettingsButton.click()
        from frontend.src.viewing import DEFAULTS

        assert restored.viewer.viewing_preferences == DEFAULTS
    finally:
        restored.close()


def test_corrupt_viewing_settings_fall_back_to_defaults():
    from frontend.src.viewing import normalize_preferences, DEFAULTS

    assert (
        normalize_preferences({"zoom": "bad", "font": "unknown", "text_size": -1})
        == DEFAULTS
    )


def test_numeric_point_size_is_saved_and_reset(window):
    spin = window.ui.textSizeInput
    assert spin.value() == 12
    assert spin.suffix() == " pt"
    spin.setValue(13)
    assert window.settings.value("viewing/text_size") == "13 pt"
    assert window.viewer.viewing_preferences["text_size"] == "13 pt"
    window.ui.resetSettingsButton.click()
    assert spin.value() == 12


def test_reset_all_settings_restores_theme_and_viewing_in_existing_windows(window):
    select(window, "valid")
    window.open_in_window(window._snapshot)
    window.ui.darkModeButton.click()
    window.ui.textSizeInput.setValue(24)
    window.ui.fontCombo.setCurrentText("Monospace")
    window.ui.pageZoomInput.setValue(175)
    window.ui.lineSpacingCombo.setCurrentText("Comfortable")
    window.ui.resetSettingsButton.click()
    from frontend.src.viewing import DEFAULTS

    assert window.theme == "light"
    assert window.settings.value("appearance/theme") == "light"
    assert window.viewing_preferences == DEFAULTS
    assert window._windows["valid"].centralWidget().viewing_preferences == DEFAULTS
    assert window._snapshot.id == "valid"
    for combo in (window.ui.fontCombo, window.ui.lineSpacingCombo):
        assert "Original" not in [combo.itemText(i) for i in range(combo.count())]


def test_numeric_steppers_and_limits(window):
    window.show()
    window.ui.settingsButton.click()
    QApplication.instance().processEvents()
    assert window.ui.pageZoomInput.lineEdit().width() > 30
    assert window.ui.textSizeInput.lineEdit().width() > 30
    window.set_theme("dark")
    QApplication.instance().processEvents()
    assert window.ui.pageZoomInput.lineEdit().width() > 30
    window.set_theme("light")
    QApplication.instance().processEvents()
    assert window.ui.textSizeInput.lineEdit().width() > 30
    u = window.ui
    u.zoomIncrease.click()
    assert u.pageZoomInput.value() == 105
    u.zoomDecrease.click()
    assert u.pageZoomInput.value() == 100
    u.textSizeIncrease.click()
    assert u.textSizeInput.value() == 13
    u.textSizeDecrease.click()
    assert u.textSizeInput.value() == 12
    u.pageZoomInput.setValue(103)
    assert window.viewing_preferences["zoom"] == "103%"
    u.textSizeInput.setValue(32)
    assert not u.textSizeIncrease.isEnabled()
    u.textSizeInput.setValue(10)
    assert not u.textSizeDecrease.isEnabled()
    u.pageZoomInput.setValue(200)
    assert not u.zoomIncrease.isEnabled()
    u.pageZoomInput.setValue(75)
    assert not u.zoomDecrease.isEnabled()
    u.resetSettingsButton.click()
    assert u.zoomDecrease.isEnabled() and u.zoomIncrease.isEnabled()
    assert u.textSizeDecrease.isEnabled() and u.textSizeIncrease.isEnabled()


def test_sidebar_toggle_preserves_archive_and_restores_width(window):
    window.show()
    QApplication.instance().processEvents()
    select(window, "valid")
    window.ui.workspaceSplitter.setSizes([310, 810])
    before = window.ui.workspaceSplitter.sizes()[0]
    source = window.ui.rawHtml.toPlainText()
    window.ui.sidebarToggle.click()
    QApplication.instance().processEvents()
    assert window.ui.archivePanel.isHidden()
    assert window.ui.sidebarToggle.isVisible()
    assert window._snapshot.id == "valid"
    assert window.ui.rawHtml.toPlainText() == source
    assert window.ui.viewerStack.currentWidget() is window.ui.webPage
    window.ui.sidebarToggle.click()
    QApplication.instance().processEvents()
    assert not window.ui.archivePanel.isHidden()
    assert abs(window.ui.workspaceSplitter.sizes()[0] - before) < 3
    assert window.ui.snapshotList.currentRow() >= 0


def test_tabs_keep_independent_viewers_and_content_modes(window):
    select(window, "valid")
    first = window.viewer
    window.ui.rawButton.click()
    select(window, "missing")
    assert window.tab_bar.count() == 2
    assert window.viewer is not first
    assert window.ui.viewerStack.currentWidget() is window.ui.emptyPage
    window.tab_bar.setCurrentIndex(0)
    assert window.viewer is first
    assert window._snapshot.id == "valid"
    assert window.ui.viewerStack.currentWidget() is window.ui.rawPage
    assert window.ui.rawHtml.toPlainText() == "<h1>Saved page</h1>"
    window.open_in_tab(window._snapshot)
    assert window.tab_bar.count() == 2
    window.ui.textSizeInput.setValue(18)
    assert all(
        tab["viewer"].viewing_preferences["text_size"] == "18 pt"
        for tab in window._tabs.values()
    )


def test_tab_closing_and_reordering_preserve_identity(window):
    select(window, "valid")
    select(window, "missing")
    window.tab_bar.moveTab(0, 1)
    window.tab_bar.setCurrentIndex(1)
    assert window._snapshot.id == "valid"
    window.close_tab(1)
    assert window.tab_bar.count() == 1
    assert window._snapshot.id == "missing"
    window.close_tab(0)
    assert window.tab_bar.count() == 0
    assert window._snapshot is None
    assert not window.ui.openWindowButton.isEnabled()
    assert window.ui.viewerStack.currentWidget() is window.ui.emptyPage
    select(window, "valid")
    assert window.tab_bar.count() == 1
    assert window._snapshot.id == "valid"


def test_tab_close_icon_is_centered_and_closes_correct_tab_after_move(window):
    from frontend.src.main_window import _TabCloseButton
    from PySide6.QtWidgets import QTabBar
    from PySide6.QtCore import QEvent

    window.show()
    select(window, "valid")
    select(window, "missing")
    QApplication.instance().processEvents()
    host = window.tab_bar.tabButton(0, QTabBar.ButtonPosition.LeftSide)
    button = host.findChild(_TabCloseButton)
    assert abs(button.geometry().center().x() - host.rect().center().x()) <= 1
    assert abs(button.geometry().center().y() - host.rect().center().y()) <= 1
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtCore import QPointF

    button.enterEvent(QEnterEvent(QPointF(), QPointF(), QPointF()))
    assert button.graphicsEffect().isEnabled()
    button.leaveEvent(QEvent(QEvent.Type.Leave))
    assert not button.graphicsEffect().isEnabled()
    window.tab_bar.moveTab(0, 1)
    button.click()
    assert window.tab_bar.count() == 1
    assert window._snapshot.id == "missing"


@pytest.mark.asyncio
async def test_embedded_statistics_generates_table_and_graph(window):
    window.ui.statisticsButton.click()
    panel = window.statistics_widget
    panel.generate_button.click()
    assert panel.task is not None
    await panel.task
    assert panel.stats is not None
    assert panel.stacked_content.currentWidget() is panel.stats_page
    assert panel.generate_button.isEnabled()
    assert panel.graph._plot_data
    assert panel.stats_table.item(0, 0).text()
    for row, field in enumerate(
        ("snapshots", "files", "size", "urls", "hosts"), start=1
    ):
        value = getattr(panel.stats.overall, field)
        expected = panel._pprint_bytes(value) if field == "size" else str(value)
        assert panel.stats_table.item(row, 0).text() == expected
    window.ui.archivesButton.click()
    window.ui.statisticsButton.click()
    assert panel.stacked_content.currentWidget() is panel.stats_page


def test_qt_font_chooser_persists_family_style_and_effects(window):
    from PySide6.QtGui import QFont, QFontDatabase
    from frontend.src.viewing import DEFAULTS, reading_script

    select(window, "valid")
    window.open_in_window(window._snapshot)
    family = next(
        name
        for name in ("Arial", "DejaVu Sans", "Liberation Sans", "Helvetica")
        if name in QFontDatabase.families()
    )
    font = QFont(family, 18)
    font.setWeight(QFont.Weight.Bold)
    font.setItalic(True)
    font.setUnderline(True)
    from PySide6.QtCore import QTimer

    def accept_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, main_window.QFontDialog)
        dialog.setCurrentFont(font)
        dialog.accept()

    QTimer.singleShot(0, accept_dialog)
    window.ui.addFontButton.click()
    assert window.viewing_preferences["font"] == font.family()
    assert window.viewing_preferences["text_size"] == "18 pt"
    saved_font = QFont()
    assert saved_font.fromString(window.viewing_preferences["font_details"])
    assert saved_font.family() == font.family()
    assert saved_font.bold() and saved_font.italic() and saved_font.underline()
    assert window.viewer.viewing_preferences == window.viewing_preferences
    assert (
        window._windows["valid"].centralWidget().viewing_preferences
        == window.viewing_preferences
    )
    script = reading_script(window.viewing_preferences)
    assert '"weight": 700' in script and '"italic": true' in script
    assert '"decoration": "underline"' in script
    restored = main_window.MainWindow(MockSnapshotService([]), settings=window.settings)
    try:
        assert restored.viewing_preferences == window.viewing_preferences
    finally:
        restored.close()
    before = dict(window.viewing_preferences)
    QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
    window.ui.addFontButton.click()
    assert window.viewing_preferences == before
    window.reset_viewing_preferences()
    assert window.viewing_preferences == DEFAULTS
    assert not window.settings.contains("viewing/font_details")


def test_japanese_preedit_keeps_results_until_commit_and_preserves_url(window):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QInputMethodEvent
    from PySide6.QtWidgets import QApplication

    search = window.ui.searchInput
    assert search.testAttribute(Qt.WidgetAttribute.WA_InputMethodEnabled)
    original_count = window.ui.snapshotList.count()
    QApplication.sendEvent(search, QInputMethodEvent("にほん", []))
    assert search.is_composing and search.text() == ""
    assert window.ui.snapshotList.count() == original_count
    committed = QInputMethodEvent()
    committed.setCommitString("日本")
    QApplication.sendEvent(search, committed)
    assert not search.is_composing
    assert search.text() == "日本"
    assert window.ui.snapshotList.count() == 0
    url = window.ui.urlInput
    url.setText("https://")
    QApplication.sendEvent(url, QInputMethodEvent("にほん", []))
    requests = []
    window.capture_requested.connect(requests.append)
    window.request_capture()
    assert requests == []
    committed = QInputMethodEvent()
    committed.setCommitString("日本.example/")
    QApplication.sendEvent(url, committed)
    window.request_capture()
    assert requests == ["https://日本.example/"]


def test_tab_drag_outside_strip_preserves_tabs_and_close_identity(window):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    window.show()
    select(window, "valid")
    select(window, "missing")
    bar = window.tab_bar
    QApplication.instance().processEvents()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(0).center())
    QTest.mouseMove(bar, QPoint(bar.width() + 300, -100))
    QTest.mouseRelease(
        bar, Qt.MouseButton.LeftButton, pos=QPoint(bar.width() + 300, -100)
    )
    assert {bar.tabData(i) for i in range(bar.count())} == {"valid", "missing"}
    assert bar._drag_offset is None
    window._close_tab_id("valid")
    assert bar.count() == 1 and bar.tabData(0) == "missing"


def test_statistics_focus_outline_tracks_keyboard_and_mouse(window):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt

    window.show()
    window.ui.statisticsButton.click()
    panel = window.statistics_widget
    QTest.mouseClick(panel.month_radio, Qt.MouseButton.LeftButton)
    assert panel.month_radio.isChecked()
    assert panel.property("keyboardNavigation") is False
    QTest.keyClick(panel.month_radio, Qt.Key.Key_Tab)
    assert panel.property("keyboardNavigation") is True
    QTest.mouseClick(panel.month_radio, Qt.MouseButton.LeftButton)
    assert panel.property("keyboardNavigation") is False
    assert panel.month_radio.isChecked()


def test_drag_reorders_complete_tabs_immediately(window):
    from PySide6.QtCore import Qt, QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtTest import QTest

    window.show()
    select(window, "valid")
    select(window, "missing")
    bar = window.tab_bar
    QApplication.instance().processEvents()
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=bar.tabRect(0).center())
    position = QPointF(bar.tabRect(1).center())
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        position,
        position,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(bar, event)
    assert [bar.tabData(i) for i in range(2)] == ["missing", "valid"]
    assert window._snapshot.id == "valid"
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=position.toPoint())
    QApplication.instance().processEvents()
    assert [bar.tabData(i) for i in range(2)] == ["missing", "valid"]
    close_host = bar.tabButton(1, bar.ButtonPosition.LeftSide)
    close_host.findChild(main_window._TabCloseButton).click()
    assert bar.count() == 1 and bar.tabData(0) == "missing"
