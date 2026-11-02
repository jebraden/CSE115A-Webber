"""Designer-backed central UI for task 2.2.2.

The shell reuses the snapshot service and local archive viewer. Backend capture
integration can connect capture_requested without changing the Designer layout.
"""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from PySide6.QtCore import QFile, QDir, QEvent, QIODevice, QSize, Qt, Signal, QSettings, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QIcon, QColor
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QLabel, QListWidgetItem,
    QMainWindow, QToolButton, QWidget, QSpinBox, QTabBar, QStackedWidget, QGraphicsDropShadowEffect,
)

from .archive_list.service import SnapshotService
from .archive_viewer import ArchiveViewer
from .themes import stylesheet_for
from .viewing import DEFAULTS, normalize_preferences


class _NumericInput(QSpinBox):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # macOS styles can leave a one-pixel edit field when native spin arrows
        # are hidden. The adjacent minus/plus buttons own those actions here.
        self._fit_editor()

    def _fit_editor(self):
        self.lineEdit().setGeometry(self.rect().adjusted(10, 1, -10, -1))

    def event(self, event):
        result = super().event(event)
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.Show, QEvent.Type.PolishRequest, QEvent.Type.LayoutRequest):
            QTimer.singleShot(0, self._fit_editor)
            QTimer.singleShot(50, self._fit_editor)
        return result


class _TabCloseButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tabCloseButton")
        self.setFixedSize(22, 22)
        self.setIconSize(QSize(14, 14))
        self.setToolTip("Close archive")
        self._hover_shadow = QGraphicsDropShadowEffect(self)
        self._hover_shadow.setBlurRadius(9)
        self._hover_shadow.setOffset(0, 1)
        self._hover_shadow.setColor(QColor(0, 0, 0, 48))
        self._hover_shadow.setEnabled(False)
        self.setGraphicsEffect(self._hover_shadow)

    def enterEvent(self, event):
        self._hover_shadow.setEnabled(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover_shadow.setEnabled(False)
        super().leaveEvent(event)


class _WindowLoader(QUiLoader):
    def __init__(self, window):
        super().__init__()
        self.window = window

    def createWidget(self, class_name, parent=None, name=""):
        if parent is None and class_name == "QMainWindow":
            self.window.setObjectName(name)
            return self.window
        if class_name == "QSpinBox":
            widget = _NumericInput(parent)
            widget.setObjectName(name)
            return widget
        return super().createWidget(class_name, parent, name)


class MainWindow(QMainWindow):
    snapshot_requested = Signal(object)
    capture_requested = Signal(str)

    def __init__(self, service: SnapshotService, *, demo=False, settings=None):
        super().__init__()
        self.settings = settings if settings is not None else QSettings("Webber", "Webber")
        self._service = service
        self._snapshot = None
        self._snapshots = []
        self._windows = {}
        self._hover_item = None
        source = QFile(str(Path(__file__).with_name("ui") / "main_window.ui"))
        if not source.open(QIODevice.OpenModeFlag.ReadOnly):
            raise OSError(source.errorString())
        loader = _WindowLoader(self)
        loader.setWorkingDirectory(QDir(str(Path(__file__).with_name("ui"))))
        try:
            if loader.load(source) is None:
                raise RuntimeError(loader.errorString())
        finally:
            source.close()
        self.ui = SimpleNamespace(**{
            obj.objectName(): obj for obj in self.findChildren(QWidget)
            if obj.objectName()
        })
        u = self.ui
        self._light_stylesheet = self.styleSheet()
        self.setStyleSheet(stylesheet_for(self._light_stylesheet, "light"))
        self.viewer = ArchiveViewer(u.webViewHost)
        u.webViewLayout = u.webViewHost.layout()
        u.designerViewerPlaceholder.hide()
        self._browser_pages = QStackedWidget(u.webViewHost)
        u.webViewLayout.addWidget(self._browser_pages)
        self._idle_viewer = self.viewer
        self._browser_pages.addWidget(self._idle_viewer)
        self._tabs = {}
        self._active_tab_id = None
        self.tab_bar = QTabBar(u.archiveTabsHost)
        self.tab_bar.setAccessibleName("Open archives")
        self.tab_bar.setTabsClosable(False)
        self.tab_bar.setMovable(True)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_bar.setUsesScrollButtons(True)
        self.tab_bar.setMinimumWidth(0)
        u.archiveTabsHost.layout().addWidget(self.tab_bar)
        u.archiveTabsHost.layout().setAlignment(self.tab_bar, Qt.AlignmentFlag.AlignLeft)
        self.tab_bar.currentChanged.connect(self._activate_tab)
        self.tab_bar.tabCloseRequested.connect(self.close_tab)
        self._close_tab_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Close), self)
        self._close_tab_shortcut.activated.connect(lambda: self.close_tab(self.tab_bar.currentIndex()))
        self._sidebar_sizes = [285, 835]
        u.workspaceSplitter.setSizes(self._sidebar_sizes)
        u.sidebarToggle.toggled.connect(self.set_sidebar_visible)
        u.workspaceSplitter.setStretchFactor(0, 0)
        u.workspaceSplitter.setStretchFactor(1, 1)
        u.snapshotList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._navigation = QButtonGroup(self)
        self._navigation.setExclusive(True)
        self._navigation.addButton(u.archivesButton)
        self._navigation.addButton(u.statisticsButton)
        self._navigation.addButton(u.settingsButton)
        self._themes = QButtonGroup(self)
        self._themes.setExclusive(True)
        self._themes.addButton(u.lightModeButton)
        self._themes.addButton(u.darkModeButton)
        u.lightModeButton.clicked.connect(lambda: self.set_theme("light"))
        u.darkModeButton.clicked.connect(lambda: self.set_theme("dark"))
        u.settingsButton.clicked.connect(lambda: u.mainStack.setCurrentWidget(u.settingsPage))
        self._content_modes = QButtonGroup(self)
        self._content_modes.setExclusive(True)
        self._content_modes.addButton(u.pageButton)
        self._content_modes.addButton(u.rawButton)
        u.archivesButton.clicked.connect(lambda: u.mainStack.setCurrentWidget(u.archivesPage))
        u.statisticsButton.clicked.connect(lambda: u.mainStack.setCurrentWidget(u.statisticsPage))
        u.savePageButton.toggled.connect(self._focus_capture)
        u.cancelCaptureButton.clicked.connect(lambda: u.savePageButton.setChecked(False))
        u.captureButton.clicked.connect(self.request_capture)
        u.urlInput.returnPressed.connect(self.request_capture)
        u.searchInput.textChanged.connect(self.search)
        u.snapshotList.currentItemChanged.connect(self._select_item)
        u.pageButton.clicked.connect(self._show_content)
        u.rawButton.clicked.connect(self._show_content)
        u.openWindowButton.clicked.connect(lambda: self.open_in_window(self._snapshot))
        self.popout = QToolButton(u.snapshotList.viewport())
        self.popout.setText("↗")
        self.popout.setToolTip("Open in new window")
        self.popout.setAccessibleName("Open archive in new window")
        self.popout.setFixedSize(28, 28)
        self.popout.hide()
        self.popout.clicked.connect(self._popout_hovered)
        u.snapshotList.itemEntered.connect(self._position_popout)
        u.snapshotList.viewport().installEventFilter(self)
        u.snapshotList.installEventFilter(self)
        u.snapshotList.verticalScrollBar().valueChanged.connect(lambda: self.popout.hide())
        self._popout_shortcut = QShortcut(QKeySequence("Ctrl+Shift+O"), self)
        self._popout_shortcut.activated.connect(lambda: self.open_in_window(self._snapshot))
        u.previewLabel = QLabel("Sample archives" if demo else "Local archives")
        u.previewLabel.setObjectName("previewLabel")
        self.statusBar().addPermanentWidget(u.previewLabel)
        self.set_theme(self.settings.value("appearance/theme", "light"), persist=False)
        self._viewing_controls = {"zoom": u.pageZoomInput, "text_size": u.textSizeInput,
                                  "font": u.fontCombo, "spacing": u.lineSpacingCombo}
        saved = normalize_preferences({key: self.settings.value("viewing/" + key, default)
                                       for key, default in DEFAULTS.items()})
        for key, combo in self._viewing_controls.items():
            self._set_control_value(combo, saved[key])
            signal = combo.valueChanged if isinstance(combo, QSpinBox) else combo.currentTextChanged
            signal.connect(self.update_viewing_preferences)
        for spin, decrease, increase in ((u.pageZoomInput, u.zoomDecrease, u.zoomIncrease),
                                         (u.textSizeInput, u.textSizeDecrease, u.textSizeIncrease)):
            decrease.clicked.connect(spin.stepDown)
            increase.clicked.connect(spin.stepUp)
            spin.valueChanged.connect(self._update_stepper_buttons)
        self._update_stepper_buttons()
        u.resetSettingsButton.clicked.connect(self.reset_all_settings)
        self.update_viewing_preferences(persist=False)
        self.search()

    def set_sidebar_visible(self, visible):
        u = self.ui
        if visible:
            u.archivePanel.show()
            u.workspaceSplitter.setSizes(self._sidebar_sizes)
        else:
            sizes = u.workspaceSplitter.sizes()
            if sizes[0] > 0:
                self._sidebar_sizes = sizes
            self.popout.hide()
            u.archivePanel.hide()
        u.sidebarToggle.setToolTip("Hide sidebar" if visible else "Show sidebar")

    @staticmethod
    def _control_value(control):
        return f"{control.value()}{control.suffix()}" if isinstance(control, QSpinBox) else control.currentText()

    @staticmethod
    def _set_control_value(control, value):
        if isinstance(control, QSpinBox):
            control.setValue(int(value.replace(control.suffix(), "").strip()))
        else:
            control.setCurrentText(value)

    def _update_stepper_buttons(self, *_args):
        u = self.ui
        for spin, decrease, increase in ((u.pageZoomInput, u.zoomDecrease, u.zoomIncrease),
                                         (u.textSizeInput, u.textSizeDecrease, u.textSizeIncrease)):
            decrease.setEnabled(spin.value() > spin.minimum())
            increase.setEnabled(spin.value() < spin.maximum())

    def update_viewing_preferences(self, *_args, persist=True):
        self.viewing_preferences = normalize_preferences({key: self._control_value(combo)
                                  for key, combo in self._viewing_controls.items()})
        self._idle_viewer.apply_viewing_preferences(self.viewing_preferences)
        for tab in self._tabs.values():
            tab["viewer"].apply_viewing_preferences(self.viewing_preferences)
        for window in self._windows.values():
            window.centralWidget().apply_viewing_preferences(self.viewing_preferences)
        if persist:
            for key, value in self.viewing_preferences.items():
                self.settings.setValue("viewing/" + key, value)
            self.settings.sync()

    def reset_viewing_preferences(self):
        for key, combo in self._viewing_controls.items():
            combo.blockSignals(True)
            self._set_control_value(combo, DEFAULTS[key])
            combo.blockSignals(False)
        self._update_stepper_buttons()
        self.update_viewing_preferences()

    def reset_all_settings(self):
        """Restore all supported preferences without touching archives."""
        self.set_theme("light")
        self.reset_viewing_preferences()

    def set_theme(self, mode, *, persist=True):
        """Apply shell colors without touching the archived HTML or selection."""
        mode = mode if mode in ("light", "dark") else "light"
        self.theme = mode
        self.ui.sidebarToggle.setIcon(QIcon(str(Path(__file__).with_name("ui") / "icons" / f"sidebar-{mode}.svg")))
        self.setStyleSheet(stylesheet_for(self._light_stylesheet, mode))
        close_icon = QIcon(str(Path(__file__).with_name("ui") / "icons" / f"close-{mode}.svg"))
        for button in self.findChildren(_TabCloseButton):
            button.setIcon(close_icon)
        foreground, background, border = ("#b6d1aa", "#1c1c1c", "#3b3b3b") if mode == "dark" else ("#566446", "#f8f8f6", "#cececa")
        hover, focus = ("#293629", "#8ca37b") if mode == "dark" else ("#e9ecdf", "#879b76")
        self.popout.setStyleSheet(
            f"QToolButton {{ color: {foreground}; background: {background}; border: 1px solid {border}; border-radius: 8px; }}"
            f"QToolButton:hover, QToolButton:focus {{ background: {hover}; border-color: {focus}; }}"
        )
        self.ui.lightModeButton.setChecked(mode == "light")
        self.ui.darkModeButton.setChecked(mode == "dark")
        if persist:
            self.settings.setValue("appearance/theme", mode)
            self.settings.sync()

    def _focus_capture(self, visible):
        if visible:
            self.ui.urlInput.setFocus()

    def request_capture(self):
        url = self.ui.urlInput.text().strip()
        try:
            parts = urlsplit(url)
            valid = parts.scheme.lower() in ("http", "https") and bool(parts.hostname)
            # Accessing port also validates malformed port values.
            parts.port
        except ValueError:
            valid = False
        if not valid:
            self.ui.captureStatus.setText("Invalid URL.")
            self.ui.urlInput.setFocus()
            return
        self.capture_requested.emit(url)
        self.ui.captureStatus.setText("Saving is unavailable.")

    def search(self, *_):
        u = self.ui
        self._hover_item = None
        self.popout.hide()
        u.snapshotList.blockSignals(True)
        u.snapshotList.clear()
        try:
            self._snapshots = list(self._service.search_snapshots(u.searchInput.text().strip()))
        except Exception:
            self._snapshots = []
            u.snapshotList.blockSignals(False)
            u.archiveCount.setText("Could not load snapshots")
            if not self._tabs:
                u.emptyMessage.setText("Could not load archives.")
            self.statusBar().clearMessage()
            return
        for snapshot in self._snapshots:
            date = snapshot.archived_at.astimezone().strftime("%b %d, %Y · %I:%M %p")
            item = QListWidgetItem(f"{snapshot.url}\n{date}")
            item.setData(Qt.ItemDataRole.UserRole, snapshot)
            item.setToolTip(f"{snapshot.url}\n{date}")
            item.setSizeHint(QSize(230, 76))
            u.snapshotList.addItem(item)
        count = len(self._snapshots)
        u.archiveCount.setText(f"{count} snapshot{'s' if count != 1 else ''}")
        u.snapshotList.blockSignals(False)
        if self._active_tab_id is not None:
            self._sync_list_selection()
        else:
            self._clear_reader()
            u.emptyMessage.setText("No archive open." if count else "No matching archives." if u.searchInput.text() else "No archived webpages yet.")
        self.statusBar().clearMessage()

    def _select_item(self, item, _previous):
        if item is not None:
            self.open_in_tab(item.data(Qt.ItemDataRole.UserRole))
            if self.ui.snapshotList.hasFocus():
                self._position_popout(item)

    def open_in_tab(self, snapshot):
        for index in range(self.tab_bar.count()):
            if self.tab_bar.tabData(index) == snapshot.id:
                self.tab_bar.setCurrentIndex(index)
                return
        viewer = ArchiveViewer(self._browser_pages)
        viewer.apply_viewing_preferences(self.viewing_preferences)
        viewer.setHtml("")
        self._browser_pages.addWidget(viewer)
        source, available = "", False
        try:
            path = self._local_path(snapshot)
            source = path.read_text(encoding="utf-8", errors="replace")
            viewer.open_archive(str(path))
            available = True
        except (OSError, ValueError):
            pass
        self._tabs[snapshot.id] = {"snapshot": snapshot, "viewer": viewer,
                                   "source": source, "available": available,
                                   "raw": False, "raw_scroll": 0}
        parts = urlsplit(snapshot.url)
        title = (parts.path.rstrip("/").rsplit("/", 1)[-1] or parts.hostname or snapshot.url)
        self.tab_bar.blockSignals(True)
        index = self.tab_bar.addTab(title)
        self.tab_bar.setTabData(index, snapshot.id)
        close_host = QWidget(self.tab_bar)
        close_host.setObjectName("tabCloseHost")
        close_host.setFixedSize(30, 22)
        close_button = _TabCloseButton(close_host)
        close_button.move(4, 0)
        close_button.setAccessibleName(f"Close {snapshot.url}")
        close_button.setIcon(QIcon(str(Path(__file__).with_name("ui") / "icons" / f"close-{self.theme}.svg")))
        close_button.clicked.connect(lambda _checked=False, key=snapshot.id: self._close_tab_id(key))
        self.tab_bar.setTabButton(index, QTabBar.ButtonPosition.LeftSide, close_host)
        self.tab_bar.setTabToolTip(index, snapshot.url + "\n" + snapshot.archived_at.astimezone().strftime("%b %d, %Y · %I:%M %p"))
        self.tab_bar.blockSignals(False)
        self.tab_bar.setCurrentIndex(index)
        self._activate_tab(index)
        self.snapshot_requested.emit(snapshot)

    def _save_tab_state(self):
        state = self._tabs.get(self._active_tab_id)
        if state is not None:
            state["raw"] = self.ui.rawButton.isChecked()
            state["raw_scroll"] = self.ui.rawHtml.verticalScrollBar().value()

    def _activate_tab(self, index):
        if index < 0:
            self._clear_reader()
            return
        key = self.tab_bar.tabData(index)
        state = self._tabs.get(key)
        if state is None:
            return
        if key == self._active_tab_id:
            return
        self._save_tab_state()
        self._active_tab_id = key
        self._snapshot = state["snapshot"]
        self.viewer = state["viewer"]
        self._browser_pages.setCurrentWidget(self.viewer)
        self.ui.pageTitle.setText(self.tab_bar.tabText(index))
        self.ui.currentUrl.setText(self._snapshot.url)
        self.ui.snapshotDate.setText("Saved " + self._snapshot.archived_at.astimezone().strftime("%b %d, %Y · %I:%M %p"))
        self.ui.rawHtml.setPlainText(state["source"])
        self.ui.rawHtml.verticalScrollBar().setValue(state["raw_scroll"])
        self.ui.rawButton.setChecked(state["raw"])
        self.ui.pageButton.setChecked(not state["raw"])
        self.ui.openWindowButton.setEnabled(state["available"])
        if state["available"]:
            self._show_content()
        else:
            self.ui.emptyMessage.setText("Archived file is unavailable.")
            self.ui.viewerStack.setCurrentWidget(self.ui.emptyPage)
        self._sync_list_selection()
        self.statusBar().clearMessage()

    def _sync_list_selection(self):
        self.ui.snapshotList.blockSignals(True)
        selected = -1
        for row, snapshot in enumerate(self._snapshots):
            if snapshot.id == self._active_tab_id:
                selected = row
                break
        self.ui.snapshotList.setCurrentRow(selected)
        self.ui.snapshotList.blockSignals(False)

    def _clear_reader(self):
        self._active_tab_id = None
        self._snapshot = None
        self.viewer = self._idle_viewer
        self.ui.openWindowButton.setEnabled(False)
        self.ui.pageTitle.setText("Archive")
        self.ui.currentUrl.clear()
        self.ui.snapshotDate.clear()
        self.ui.rawHtml.clear()
        self.ui.emptyMessage.setText("No archive open.")
        self.ui.viewerStack.setCurrentWidget(self.ui.emptyPage)
        self.ui.snapshotList.blockSignals(True)
        self.ui.snapshotList.setCurrentRow(-1)
        self.ui.snapshotList.blockSignals(False)

    def _close_tab_id(self, key):
        for index in range(self.tab_bar.count()):
            if self.tab_bar.tabData(index) == key:
                self.close_tab(index)
                break

    def close_tab(self, index):
        if not 0 <= index < self.tab_bar.count():
            return
        key = self.tab_bar.tabData(index)
        state = self._tabs.pop(key)
        self.tab_bar.removeTab(index)
        self._browser_pages.removeWidget(state["viewer"])
        state["viewer"].deleteLater()
        if not self._tabs:
            self._clear_reader()
        else:
            self._activate_tab(self.tab_bar.currentIndex())

    @staticmethod
    def _local_path(snapshot):
        if snapshot is None or snapshot.local_path is None:
            raise ValueError("This snapshot has no local HTML file.")
        path = Path(snapshot.local_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Archive not found: {path}")
        return path

    def _show_content(self):
        if self._active_tab_id in self._tabs:
            self._tabs[self._active_tab_id]["raw"] = self.ui.rawButton.isChecked()
        if self.ui.openWindowButton.isEnabled():
            self.ui.viewerStack.setCurrentWidget(self.ui.rawPage if self.ui.rawButton.isChecked() else self.ui.webPage)

    def _position_popout(self, item):
        self._hover_item = item
        rect = self.ui.snapshotList.visualItemRect(item)
        if rect.isValid():
            self.popout.move(self.ui.snapshotList.viewport().width() - 36, rect.top() + 12)
            self.popout.show()
            self.popout.raise_()

    def _popout_hovered(self):
        if self._hover_item is not None:
            self.open_in_window(self._hover_item.data(Qt.ItemDataRole.UserRole))

    def eventFilter(self, obj, event):
        if obj is self.ui.snapshotList.viewport() and event.type() == QEvent.Type.Leave:
            if not self.popout.underMouse() and not self.popout.hasFocus():
                self.popout.hide()
        if obj is self.ui.snapshotList and event.type() == QEvent.Type.FocusIn:
            item = self.ui.snapshotList.currentItem()
            if item:
                self._position_popout(item)
        return super().eventFilter(obj, event)

    def open_in_window(self, snapshot):
        try:
            path = self._local_path(snapshot)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage("Archived file is unavailable.")
            return
        if snapshot.id in self._windows:
            window = self._windows[snapshot.id]
            window.showNormal()
            window.raise_()
            window.activateWindow()
            return
        window = QMainWindow(self)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.setWindowTitle(f"Webber — {snapshot.url}")
        window.resize(1000, 720)
        viewer = ArchiveViewer(window)
        viewer.apply_viewing_preferences(self.viewing_preferences)
        viewer.open_archive(str(path))
        window.setCentralWidget(viewer)
        self._windows[snapshot.id] = window
        window.destroyed.connect(lambda _obj=None, key=snapshot.id: self._windows.pop(key, None))
        window.show()

    def closeEvent(self, event):
        for window in list(self._windows.values()):
            window.close()
        super().closeEvent(event)
