from PySide6.QtWidgets import (
    QSizePolicy,
    QWidget,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
    QLabel,
    QSpinBox,
    QLayout,
    QSizePolicy,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QMenu,
    QTableWidget,
    QTableWidgetItem,
    QAbstractItemView,
    QHeaderView,
)
from PySide6.QtGui import (
    QFont,
    QPainter,
    QColor,
    QMouseEvent,
    QResizeEvent,
    QAction,
)
from PySide6.QtCore import (
    QDate,
    Qt,
    qWarning,
    QDateTime,
    QLocale,
    QSize,
    QPoint,
    Signal,
)
import sys
import traceback
from asyncio import Task, create_task
from typing import Any, override
from collections import defaultdict
import functools

from .calendar_ui import Ui_Calendar
from ..api import WebberAPI, GetSnapshotResponse
from ..queries import make_snapshot_search_args
from ..util.queryparse import QuerySyntaxError


class _Calendar(QTableWidget):
    @staticmethod
    def _get_day_of_week_labels() -> list[str]:
        locale = QLocale.system()
        dow = locale.firstDayOfWeek().value
        out = list(range(dow, 8)) + list(range(1, dow))
        return [locale.dayName(n, QLocale.FormatType.ShortFormat) for n in out]

    def __init__(
        self, view: "CalendarView", month: int, *args: Any, **kwargs: Any
    ):
        super().__init__(
            rowCount=6,
            columnCount=7,
            *args,
            **kwargs,
        )

        self.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setHorizontalHeaderLabels(_Calendar._get_day_of_week_labels())
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)

        self._month = month
        self._year = 1
        self._view: "CalendarView" = view

        self._items: list[QTableWidgetItem] = []
        self._actions_ptr: list[QAction] = []
        self._menu_ptr: QMenu | None = None

    def _item_size(self) -> QSize:
        edge = self.size().width() // self.columnCount()
        return QSize(edge, edge)

    def _color_for_day(self, day: int) -> QColor:
        date = QDate(self._year, self._month, day + 1)
        bucket = self._view._results_by_day[date]
        alpha = len(bucket) / self._view._most_snapshots_on_day
        return QColor.fromRgbF(0.0, 0.5, 0.0, alpha)

    def set_year(self, year: int):
        self._year = year
        self._items = []
        self.clearContents()
        month_date = QDate(year, self._month, 1)
        day_count = month_date.daysInMonth()
        first_col = month_date.dayOfWeek() - 1
        first_row = int(first_col == 0)
        size = self._item_size()
        for day in range(day_count):
            item = QTableWidgetItem(str(day + 1))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setBackground(self._color_for_day(day))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            item.setSizeHint(size)
            self._items.append(item)
            self.setItem(
                first_row + ((first_col + day) // 7),
                (first_col + day) % 7,
                item,
            )

    def _date_at_point(self, point: QPoint) -> QDate | None:
        item = self.itemAt(point)
        if item is None:
            return None
        try:
            index = self._items.index(item)
        except ValueError:
            return None
        return QDate(self._year, self._month, index + 1)

    def _build_actions(self, date: QDate) -> list[QAction]:
        bucket = self._view._results_by_day[date]
        out: list[QAction] = []
        for info in bucket:
            time = info.start_time.to_qdatetime().time()
            time_str = time.toString("hh:mm:ss")
            action = QAction(time_str)
            action.triggered.connect(
                functools.partial(self._view.snapshot_opened.emit, info)
            )
            out.append(action)
        return out

    @override
    def mousePressEvent(self, event: QMouseEvent):
        date = self._date_at_point(event.position().toPoint())
        if date is None:
            return
        self._menu_ptr = QMenu(self._view)
        self._menu_ptr.addSection(
            date.toString("'Snapshots for ' MMM dd, yyyy':'")
        )
        self._actions_ptr = self._build_actions(date)
        if not self._actions_ptr:
            self._actions_ptr = [QAction("No snapshots", enabled=False)]
        self._menu_ptr.addActions(self._actions_ptr)
        self._menu_ptr.popup(event.globalPosition().toPoint())


class CalendarView(Ui_Calendar, QWidget):
    """Panel to allow the user to view all snapshots by date with a heatmap."""

    @staticmethod
    def _make_results_by_day_dict() -> dict[QDate, list[GetSnapshotResponse]]:
        return defaultdict(lambda: [])

    snapshot_opened = Signal(GetSnapshotResponse)

    def __init__(self, api: WebberAPI):
        """Construct a new CalendarView.

        This class is mostly self-enclosed. Connect to the `snapshot_opened`
        signal to be notified when the user opens a snapshot from this
        panel. The connected slot should take a single parameter, a
        `GetSnapshotResponse` object.

        Arguments:
        api -- the WebberAPI instance to use to access the backend
        """
        super().__init__()

        self._api = api
        self._calendars: dict[int, _Calendar] = {}

        self._task: Task | None = None

        self._first_result_date: QDate | None = None
        self._last_result_date: QDate | None = None
        self._most_snapshots_on_day = 0
        self._results_by_day = CalendarView._make_results_by_day_dict()

        self.setupUi(self)
        self._build_calendars()

        self.cancel_button.clicked.connect(self._handle_cancel)
        self.search_button.clicked.connect(self._handle_search)
        self.search_box.returnPressed.connect(self._handle_search)

        self.year_spin.valueChanged.connect(self._handle_year_change)

        self.stacked.setCurrentWidget(self.no_search_page)

    @staticmethod
    def _month_name(month: int) -> str:
        return QDate(1970, month, 1).toString("MMMM")

    def _build_calendars(self):
        for month in range(0, 12):
            name = CalendarView._month_name(month + 1)
            cont = QVBoxLayout()
            label = QLabel(
                text=name,
                alignment=Qt.AlignmentFlag.AlignHCenter
                | Qt.AlignmentFlag.AlignVCenter,
            )
            font = QFont(label.font())
            font.setPointSize(16)
            label.setFont(font)
            cal = _Calendar(view=self, month=month + 1)
            self._calendars[month + 1] = cal
            cont.addWidget(label)
            cont.addWidget(cal)
            self.calendar_layout.addLayout(cont, month // 4, month % 4)

    def _display_error(self, e: Exception):
        if isinstance(e, QuerySyntaxError):
            self.error_content.setPlainText(str(e))
        else:
            self.error_content.setPlainText(
                "\n".join(traceback.format_exception(e))
            )
        self.stacked.setCurrentWidget(self.error_page)

    def _handle_year_change(self, year: int):
        for month, cal in self._calendars.items():
            cal.set_year(year)

    def _handle_cancel(self):
        if self._task is not None:
            self._task.cancel()
        self._task = None
        self.stacked.setCurrentWidget(self.no_search_page)
        self.search_button.setEnabled(True)

    def _handle_search(self):
        if self._task is not None:
            qWarning("Attempt to start search while already searching!")
            return
        try:
            self.search_button.setEnabled(False)
            args = make_snapshot_search_args(self.search_box.text())
            self._task = create_task(self._do_search(args))
            self.stacked.setCurrentWidget(self.searching_page)
        except Exception as e:
            self.search_button.setEnabled(True)
            self._display_error(e)

    def _set_results_and_calculate_stats(
        self, infos: list[GetSnapshotResponse]
    ):
        self._first_result_date = None
        self._last_result_date = None
        self._most_snapshots_on_day = 0
        self._results_by_day = CalendarView._make_results_by_day_dict()
        for info in infos:
            date = info.start_time.to_qdatetime().date()
            bucket = self._results_by_day[date]
            bucket.append(info)
            self._most_snapshots_on_day = max(
                self._most_snapshots_on_day, len(bucket)
            )
            if not self._first_result_date or date < self._first_result_date:
                self._first_result_date = date
            if not self._last_result_date or date > self._last_result_date:
                self._last_result_date = date

    def _process_results(self, infos: list[GetSnapshotResponse]):
        self._set_results_and_calculate_stats(infos)
        if not infos:
            self.stacked.setCurrentWidget(self.no_results_page)
        else:
            assert self._first_result_date and self._last_result_date
            self.year_spin.setRange(
                self._first_result_date.year(), self._last_result_date.year()
            )
            self.year_spin.setValue(self._last_result_date.year())
            self.stacked.setCurrentWidget(self.results_page)

    async def _do_search(self, args: dict[str, Any]):
        try:
            infos = [
                await self._api.get_snapshot_info(id)
                for id in await self._api.search_snapshots(**args)
            ]
            self._process_results(infos)
        except Exception as e:
            self._display_error(e)
        self.search_button.setEnabled(True)
        self._task = None


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QMainWindow
    import PySide6.QtAsyncio as QtAsyncio

    from .mock_api import MockWebberAPI

    app = QApplication(sys.argv)
    win = QMainWindow()

    view = CalendarView(MockWebberAPI())  # type: ignore[arg-type]

    win.setCentralWidget(view)
    win.setVisible(True)

    view.snapshot_opened.connect(lambda i: print(i))

    QtAsyncio.run(handle_sigint=True)
