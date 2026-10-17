import re
import requests

from PySide6.QtWidgets import QMainWindow
from PySide6.QtCore import QFile 
from PySide6.QtUiTools import QUiLoader 

from PyQt6.QtWidgets import (
    QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QMessageBox,
    QMainWindow, QWidget, QTextEdit
)

# Import SERVER (backend server host) here

# Window for displaying HTML: currently a separate window, but might be better to open it in the main window
class TextWindow(QWidget):
    def __init__(self, file_id, text):
        super().__init__()
        self.setWindowTitle(file_id + "/_HTML Editor")
        self.resize(400, 300)

        self.text_area = QTextEdit()
        self.text_area.setText(text)

        text_layout = QVBoxLayout()
        text_layout.addWidget(self.text_area)
        self.setLayout(text_layout)

# Handles everything related to searching
class SearchWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Search Database")
        self.resize(400, 200)

        self.twin = None # for checking later in open_file

        # Layout
        search_layout = QVBoxLayout()
        searchbar_layout = QHBoxLayout()
        self.search_inp = QLineEdit()
        self.search_inp.setPlaceholderText("Enter URL...")
        self.inp_button = QPushButton("Search")

        searchbar_layout.addWidget(self.search_inp)
        searchbar_layout.addWidget(self.inp_button)
        search_layout.addLayout(searchbar_layout)
        self.setLayout(search_layout)

        # Results widget
        self.results = QListWidget()
        search_layout.addWidget(self.results)

        # Button functions: clicking the search button or pressing return on the search bar
        self.inp_button.clicked.connect(self.search_database)
        self.search_inp.returnPressed.connect(self.search_database)
        self.results.itemClicked.connect(self.open_html_view)

    def search_database(self):
        # Get key ready for searching and clear previous results
        key = self.search_inp.text().strip()
        if not key:
            QMessageBox.warning(self, "Warning!", "Please enter a URL")
            return
        self.results.clear()

        # For now, returns a list of results based on a certain url, but might be wise to make it
        # modular in the future to handle multiple types of queries
        try:
            # res = requests.request("QUERY", SERVER + "/search/files", json={"url": key} timeout=...)
            # if res.status_code == 200:
            #   ... 
            #   found = res.json()
            #   for find in found
            #       self.results.addItem(find["file_id"]) # idea being: use these file ids to do something with the files
            # ... (other status code checking here)
            find = ["id1", "id2", "id3"] # temp
            self.results.addItems(find)
        except Exception as error:
            QMessageBox.critical(self, "Error!", "Something went wrong: ", error)

    def get_html(self, file_id):
        # try:
        #   res = requests.request("GET", SERVER + "/files/" + file_id + "/data", timeout=5)
        #   return response.text
        res = "{\n  This is some placeholder text. \n}"
        return res

    def open_html_view(self, item):
        # file_id = item.text()
        file_id = "Placeholder"
        contents = self.get_html(file_id)

        # Same deal as in open_search
        self.twin = TextWindow(file_id, contents)
        self.twin.show()


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        # Qt .ui file loading and handling
        ui_file = QFile("mainwindow.ui")
        ui_file.open(QFile.ReadOnly)

        loader = QUiLoader()
        self.mwin = loader.load(ui_file)
        self.mwin.show()

        # Button actions
        self.mwin.actionExit.triggered.connect(self.mwin.close)
        self.mwin.actionSearch_Database.triggered.connect(self.open_search)

    def open_search(self):
        # Currently recreates window if button is pressed again
        self.swin = SearchWindow()
        self.swin.show()

