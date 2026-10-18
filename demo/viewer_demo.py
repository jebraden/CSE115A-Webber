import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
)

from frontend.src.archive_viewer import ArchiveViewer


class WebberDemo(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Webber Archive Viewer")
        self.resize(1200, 800)

        # Create the layout
        layout = QHBoxLayout(self)

        # Create the archive list
        self.archive_list = QListWidget()

        # Create your viewer
        self.viewer = ArchiveViewer()

        # Add both widgets to the layout
        layout.addWidget(self.archive_list, 1)
        layout.addWidget(self.viewer, 3)

        # Add test snapshots
        demo_folder = Path(__file__).parent

        self.add_archive(
            "Snapshot 1",
            demo_folder / "test.html"
        )

        self.add_archive(
            "Snapshot 2",
            demo_folder / "test2.html"
        )

        # Connect the click event
        self.archive_list.itemClicked.connect(
            self.on_archive_clicked
        )

    def add_archive(self, name, file_path):

        item = QListWidgetItem(name)

        # Associate a file path with this list item
        item.setData(
            Qt.ItemDataRole.UserRole,
            str(file_path)
        )

        self.archive_list.addItem(item)

    def on_archive_clicked(self, item):

        # Retrieve the selected file path
        file_path = item.data(
            Qt.ItemDataRole.UserRole
        )

        # Open it in your viewer
        self.viewer.open_archive(file_path)


def main():

    app = QApplication(sys.argv)

    window = WebberDemo()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()