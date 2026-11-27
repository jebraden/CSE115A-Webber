"""
Statistics UI Panel

You can test this file separately from the rest of the program! From the root
of the project, simply run:
```
python -m frontend.src.statistics.statistics
```
and you should see a window open with just this widget. In addition, it is
populated with random data from a mock backend.
"""

from typing import Any
from PySide6.QtCore import QDateTime, QDate, QTime, qWarning, QEvent, Qt
from PySide6.QtWidgets import (
    QWidget,
    QApplication,
    QLabel,
    QSizePolicy,
    QAbstractButton,
    QAbstractItemView,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
)
from .chart import LineChart
from enum import Enum, auto
from typing import NamedTuple
from copy import copy
import math
from asyncio import Task, create_task, CancelledError
from io import StringIO
import traceback
from operator import attrgetter

from .statistics_ui import Ui_StatisticsWidget
from ..api import WebberAPI, Interval, Timespec, Statistics


class PeriodType(Enum):
    TODAY = auto()
    YESTERDAY = auto()
    WEEK = auto()
    MONTH = auto()
    YEAR = auto()
    ALL_TIME = auto()
    CUSTOM = auto()


class GraphType(Enum):
    SNAPSHOTS = auto()
    FILES = auto()
    SIZE = auto()
    URLS = auto()
    HOSTS = auto()


class Period(NamedTuple):
    start: QDateTime
    end: QDateTime


class UIStatisticsResponse(NamedTuple):
    dx: int
    overall: Statistics
    intervals: list[Statistics]


class StatisticsWidget(QWidget, Ui_StatisticsWidget):
    def __init__(self, api: WebberAPI, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self.api = api

        self.setupUi(self)
        self.setProperty("keyboardNavigation", False)
        self.verticalLayout_2.setContentsMargins(0, 0, 0, 0)
        self.verticalLayout_2.setSpacing(18)
        self.gridLayout.setContentsMargins(16, 16, 16, 16)
        self.gridLayout.setHorizontalSpacing(12)
        self.gridLayout.setVerticalSpacing(12)
        self.horizontalLayout_2.setContentsMargins(12, 12, 12, 12)
        self.horizontalLayout_2.setSpacing(10)
        for box in (self.graph_box, self.numbers_box):
            box.layout().setContentsMargins(16, 16, 16, 16)
        self.horizontalLayout_3.setContentsMargins(0, 0, 0, 0)

        # Real headings above the cards avoid group-box titles cutting the border.
        def section_wrapper(box):
            wrapper = QWidget()
            layout = QVBoxLayout(wrapper)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
            heading = QLabel(box.title(), wrapper)
            heading.setObjectName("statisticsSectionHeading")
            layout.addWidget(heading)
            box.setAccessibleName(box.title())
            box.setTitle("")
            return wrapper, layout

        period_section, period_layout = section_wrapper(self.range_box)
        self.verticalLayout_2.replaceWidget(self.range_box, period_section)
        period_layout.addWidget(self.range_box)
        # Use a plain row with spacing, rather than a visible splitter handle.
        self.horizontalLayout_3.removeWidget(self.splitter)
        self.horizontalLayout_3.setSpacing(20)
        for box, stretch in ((self.graph_box, 3), (self.numbers_box, 2)):
            box.setParent(self.stats_page)
            section, layout = section_wrapper(box)
            box.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            layout.addWidget(box, 1)
            self.horizontalLayout_3.addWidget(section, stretch)
        self.splitter.hide()
        self.stats_table.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.stats_table.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.stats_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.graph = LineChart()
        graph_layout = QVBoxLayout()
        self.graph_wrapper.setLayout(graph_layout)
        graph_layout.addWidget(self.graph)
        # Filter only existing statistics widgets. An application-wide Python
        # filter can re-enter Shiboken while WebEngine constructs internal objects.
        for widget in (self, *self.findChildren(QWidget)):
            widget.installEventFilter(self)

        self.period_type: PeriodType = PeriodType.TODAY
        self.graph_type: GraphType = GraphType.SNAPSHOTS

        # Allow people to save the .ui file on the wrong page
        self.stacked_content.setCurrentWidget(self.init_page)

        self.task: Task | None = None
        self.stats: UIStatisticsResponse | None = None

        self.generate_button.clicked.connect(self._handle_start_generate)
        self.cancel_button.clicked.connect(self._handle_cancel)

        self.period_buttons.buttonToggled.connect(self._handle_period_button_toggle)
        self.graph_buttons.buttonToggled.connect(self._handle_graph_button_toggle)

    def eventFilter(self, watched, event):
        keyboard = None
        if event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.Wheel,
        ):
            keyboard = False
        elif (
            event.type() == QEvent.Type.KeyPress
            and isinstance(watched, QWidget)
            and (watched is self or self.isAncestorOf(watched))
            and event.key()
            in (
                Qt.Key.Key_Tab,
                Qt.Key.Key_Backtab,
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Up,
                Qt.Key.Key_Down,
            )
        ):
            keyboard = True
        if keyboard is not None and keyboard != self.property("keyboardNavigation"):
            self.setProperty("keyboardNavigation", keyboard)
            for button in self.findChildren(QAbstractButton):
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
        return super().eventFilter(watched, event)

    def _handle_cancel(self):
        if self.task is not None:
            self.task.cancel()
        self.task = None
        self.stacked_content.setCurrentWidget(self.init_page)
        self.generate_button.setEnabled(True)

    def _handle_start_generate(self):
        if self.task is not None:
            qWarning("Attempt to start generation while already generating!")
            return
        self.generate_button.setEnabled(False)
        self.stacked_content.setCurrentWidget(self.request_page)
        self.task = create_task(self._generate())

    def _show_error(self, text: str):
        self.error_content.setPlainText(text)
        self.stacked_content.setCurrentWidget(self.error_page)

    def _show_exception(self, e: BaseException):
        io = StringIO()
        traceback.print_exception(e, file=io)
        self._show_error(io.getvalue())
        io.close()

    async def _generate(self):
        try:
            self.stats = await self._get_staistics()
            if self.stats is None:
                self._show_error("The database is empty!")
            else:
                self._update_table(self.stats)
                self._update_graph(self.stats)
                self.dx_label.setText(self._pprint_span(self.stats.dx))
                self.stacked_content.setCurrentWidget(self.stats_page)
        except Exception as e:
            self._show_exception(e)
        self.generate_button.setEnabled(True)
        self.task = None

    def _update_graph(self, stats: UIStatisticsResponse):
        def add(name: str, attr: str, color: str):
            self.graph.y_label = name
            self.graph.add_data(
                name,
                list(range(len(stats.intervals))),
                list(map(attrgetter(attr), stats.intervals)),
                color,
            )

        self.graph.update_graph()
        self.graph.clear_data()
        self.graph.x_label = "Time"
        match self.graph_type:
            case GraphType.SNAPSHOTS:
                add("Snapshots", "snapshots", "red")
            case GraphType.FILES:
                add("Files", "files", "green")
            case GraphType.SIZE:
                add("Size (Bytes)", "size", "blue")
            case GraphType.URLS:
                add("URLs", "urls", "cyan")
            case GraphType.HOSTS:
                add("Hosts", "hosts", "magenta")
        self.graph.update_graph()

    def _pprint_span(self, span: int) -> str:
        """span is in seconds."""
        if not span:
            return "0s"

        SEC = 1
        MIN = SEC * 60
        HOUR = MIN * 60
        DAY = HOUR * 24
        YEAR = DAY * 365

        years = span // YEAR
        span %= YEAR

        days = span // DAY
        span %= DAY

        hours = span // HOUR
        span %= HOUR

        mins = span // MIN
        span %= MIN

        secs = span

        out: list[str] = []
        if years:
            out.append(f"{years}y")
        if days:
            out.append(f"{days}d")
        if hours:
            out.append(f"{hours}h")
        if mins:
            out.append(f"{mins}m")
        if secs:
            out.append(f"{secs}s")
        return " ".join(out)

    def _pprint_period(self, period: Period) -> str:
        FORMAT_STR = "MMM d yyyy HH:ss"
        start, end = period
        # this is in seconds
        span = (end - start) // 1000
        return f"{start.toString(FORMAT_STR)} - {end.toString(FORMAT_STR)} ({self._pprint_span(span)})"

    def _pprint_bytes(self, count: int) -> str:
        if count <= 1023:
            return f"{count} B"
        PREFIX = "KMGTPEZYRQ"
        scale = math.floor(math.log(count, 1024))
        prefix = PREFIX[scale - 1]
        return f"{count // (1024 ** scale)} {prefix}iB"

    def _update_table(self, stats: UIStatisticsResponse):
        interval = Period(*map(Timespec.to_qdatetime, stats.overall.interval))
        # Designer defines six labeled rows and one value column.
        values = (
            self._pprint_period(interval),
            str(stats.overall.snapshots),
            str(stats.overall.files),
            self._pprint_bytes(stats.overall.size),
            str(stats.overall.urls),
            str(stats.overall.hosts),
        )
        for row, value in enumerate(values):
            self.stats_table.setItem(row, 0, QTableWidgetItem(value))

    async def _get_staistics(self) -> UIStatisticsResponse | None:
        "Return None if the database is empty."
        dx, intervals = await self._get_dx_and_intervals()
        if dx is None or intervals is None:
            return None
        resp: list[Statistics] = (await self.api.statistics(intervals)).statistics
        return UIStatisticsResponse(dx, resp[0], resp[1:])

    async def _get_dx_and_intervals(
        self,
    ) -> tuple[int | None, list[Interval] | None]:
        "Return None if the database is empty."
        period = await self._get_period()
        if not period:
            return None, None
        out = [Interval(*map(Timespec.from_qdatetime, period))]
        start, end = map(QDateTime.toSecsSinceEpoch, period)
        span = end - start
        if not span:
            return 0, out
        dx = span // self._get_data_point_count()
        for i in range(self._get_data_point_count()):
            interval = Interval(
                Timespec(start + dx * i, 0),
                Timespec(start + dx * (i + 1), 0),
            )
            out.append(interval)
        return dx, out

    def _get_data_point_count(self) -> int:
        match self.period_type:
            case PeriodType.TODAY | PeriodType.YESTERDAY:
                return 24
            case PeriodType.WEEK:
                return 7
            case PeriodType.MONTH:
                return 30
            case PeriodType.YEAR:
                return 12
            case PeriodType.ALL_TIME:
                return 20  # arbitrary
            case PeriodType.CUSTOM:
                return self.data_points_spin.value()

    async def _get_custom_period(self) -> Period | None:
        start = (
            self.custom_start.dateTime()
            if not self.custom_start_check.isChecked()
            else None
        )
        end = (
            self.custom_end.dateTime()
            if not self.custom_end_check.isChecked()
            else None
        )
        if start is None or end is None:
            db_start, db_end = map(
                Timespec.to_qdatetime, await self.api.statistics_limits()
            )
            if db_start is None or db_end is None:
                return None
            if start is None and end is None:
                start = db_start
                end = db_end
            elif start is None and end:
                if db_start > end:
                    start = end
                else:
                    start = db_start
            elif start and end is None:
                if db_end < start:
                    end = start
                else:
                    end = db_end
        elif end > start:
            start, end = end, start
        assert start and end
        return Period(start, end)

    async def _get_period(self) -> Period | None:
        """Return None if the database is empty."""
        low_date = QDate.currentDate()
        low_time = QTime(0, 0)
        high_date = copy(low_date)
        high_time = QTime(23, 59, 59, 999)
        match self.period_type:
            case PeriodType.CUSTOM:
                return await self._get_custom_period()
            case PeriodType.ALL_TIME:
                db_start, db_end = await self.api.statistics_limits()
                if db_start is None or db_end is None:
                    return None
                return Period(db_start.to_qdatetime(), db_end.to_qdatetime())
            case PeriodType.TODAY:
                # Nothing to modify
                pass
            case PeriodType.YESTERDAY:
                low_date = low_date.addDays(-1)
                high_date = high_date.addDays(-1)
            case PeriodType.WEEK:
                low_date = low_date.addDays(-6)
            case PeriodType.MONTH:
                low_date = low_date.addDays(-29)
            case PeriodType.YEAR:
                low_date = low_date.addDays(-364)
        return Period(QDateTime(low_date, low_time), QDateTime(high_date, high_time))

    def _handle_period_button_toggle(self, button: QAbstractButton, checked: bool):
        if not checked:
            return
        match button:
            case self.today_radio:
                self.period_type = PeriodType.TODAY
            case self.yesterday_radio:
                self.period_type = PeriodType.YESTERDAY
            case self.week_radio:
                self.period_type = PeriodType.WEEK
            case self.month_radio:
                self.period_type = PeriodType.MONTH
            case self.year_radio:
                self.period_type = PeriodType.YEAR
            case self.all_time_radio:
                self.period_type = PeriodType.ALL_TIME
            case self.custom_radio:
                self.period_type = PeriodType.CUSTOM

    def _handle_graph_button_toggle(self, button: QAbstractButton, checked: bool):
        match button:
            case self.snapshots_graph_radio:
                self.graph_type = GraphType.SNAPSHOTS
            case self.files_graph_radio:
                self.graph_type = GraphType.FILES
            case self.size_graph_radio:
                self.graph_type = GraphType.SIZE
            case self.urls_graph_radio:
                self.graph_type = GraphType.URLS
            case self.hosts_graph_radio:
                self.graph_type = GraphType.HOSTS
        if self.stats:
            self._update_graph(self.stats)


# Driver code for testings
if __name__ == "__main__":
    import sys
    from PySide6.QtAsyncio import run
    from PySide6.QtWidgets import QMainWindow, QApplication

    from .mock_api import MockWebberAPI

    app = QApplication(sys.argv)

    app.setApplicationName("Statistics Widget")

    stats = StatisticsWidget(MockWebberAPI())  # type: ignore[arg-type]

    win = QMainWindow()
    win.setCentralWidget(stats)

    win.show()

    run(handle_sigint=True)
