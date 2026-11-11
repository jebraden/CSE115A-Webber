from PySide6.QtWidgets import (
    QWidget,
    QCalendarWidget,
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
)
from PySide6.QtGui import QFont
from PySide6.QtCore import QDate, Qt
import sys

from .calendar_ui import Ui_Calendar
from ..api import WebberAPI


class CalendarView(Ui_Calendar, QWidget):
    def __init__(self, api: WebberAPI):
        super().__init__()

        self._api = api
        self._calendars: dict[int, QCalendarWidget] = {}

        self.setupUi(self)
        self._build_calendars()

        # self.stacked.setCurrentWidget(self.no_search_page)
        self.stacked.setCurrentWidget(self.results_page)

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
            cal = QCalendarWidget(
                selectionMode=QCalendarWidget.SelectionMode.NoSelection,
                horizontalHeaderFormat=QCalendarWidget.HorizontalHeaderFormat.ShortDayNames,
                verticalHeaderFormat=QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader,
                navigationBarVisible=False,
            )
            self._calendars[month + 1] = cal
            cont.addWidget(label)
            cont.addWidget(cal)
            self.calendar_layout.addLayout(cont, month // 4, month % 4)


if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication, QMainWindow
    import PySide6.QtAsyncio as QtAsyncio

    app = QApplication(sys.argv)
    win = QMainWindow()

    view = CalendarView(None)  # type: ignore[arg-type]

    win.setCentralWidget(view)
    win.setVisible(True)

    QtAsyncio.run(handle_sigint=True)
