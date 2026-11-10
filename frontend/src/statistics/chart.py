"""
Line chart for the Webber statistics panel.
"""

import matplotlib

matplotlib.use("svg")
import matplotlib.pyplot as plt
from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent, QKeyEvent
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtSvg import QSvgRenderer
from typing import override, Any, NamedTuple
from collections.abc import Iterable
from io import BytesIO


class PlotData(NamedTuple):
    label: str
    x_data: list[Any]
    y_data: list[Any]
    color: str


ZOOM_FACTOR = 1.1
MIN_ZOOM = 0.01
MAX_ZOOM = 1000.0


class LineChart(QGraphicsView):
    """A line chart implementation, based on matplotlib and Qt."""

    def __init__(self, *args: Any, **kwargs: Any):
        """Construct the LineChart."""
        super().__init__(*args, **kwargs)

        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse
        )
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        self.setScene(QGraphicsScene())
        self._render: QSvgRenderer | None = None
        self._item: QGraphicsSvgItem | None = None

        self.x_label: str = ""
        self.y_label: str = ""
        self._plot_data: list[PlotData] = []

    def clear_data(self):
        """Clear this plots data.

        Make sure to call `update_graph` to actually redraw the data.
        """
        self._plot_data = []

    def add_data(
        self, label: str, x_data: list[Any], y_data: list[Any], color: str
    ):
        """Add a new axis to the plot.

        Make sure to call `update_graph` to actually redraw the data.

        Arguments:
        x_data -- the plots x data
        y_data -- the plots y data
        color -- the color of the new line
        """
        self._plot_data.append(PlotData(label, x_data, y_data, color))

    def update_graph(self):
        """Repaint the graph.

        This regenerates the actual graph image.
        """
        fig, ax = plt.subplots()
        try:
            ax.set_title("")
            ax.set_xlabel(self.x_label)
            ax.set_ylabel(self.y_label)
            for label, x_data, y_data, color in self._plot_data:
                ax.plot(x_data, y_data, color=color, label=label)
            # if self._plot_data:
            #     ax.legend()

            with BytesIO() as io:
                fig.savefig(io, format="svg")
                io.seek(0)
                self._render = QSvgRenderer(io.getvalue())
        finally:
            plt.close(fig)

        self.resetTransform()
        if self._item:
            self.scene().removeItem(self._item)
        self._item = QGraphicsSvgItem()
        self._item.setSharedRenderer(self._render)
        self.scene().addItem(self._item)
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    @override
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press event."""
        if event.text() == "0":
            self.resetTransform()

    @property
    def zoom(self) -> float:
        return self.transform().m11()

    @override
    def wheelEvent(self, event: QWheelEvent):
        """Handle mouse scroll events."""
        if event.angleDelta().y() > 0:
            if self.zoom * ZOOM_FACTOR <= MAX_ZOOM:
                self.scale(ZOOM_FACTOR, ZOOM_FACTOR)
        else:
            if self.zoom / ZOOM_FACTOR >= MIN_ZOOM:
                self.scale(1 / ZOOM_FACTOR, 1 / ZOOM_FACTOR)
