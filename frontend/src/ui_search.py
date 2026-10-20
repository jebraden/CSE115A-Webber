import re
import requests
import api

from PySide6.QtCore import QFile
from PySide6.QtUiTools import QUiLoader 

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QMessageBox,
    QMainWindow, QWidget, QTextEdit
)

# Window for displaying HTML: temporary solution
class TextWindow(QWidget):
    def __init__(self, file_id, text):
        super().__init__()
        self.setWindowTitle(file_id + "/_HTML Editor")
        self.resize(400, 300)

        self.text_area = QTextEdit()
        self.text_area.setPlainText(text)

        text_layout = QVBoxLayout()
        text_layout.addWidget(self.text_area)
        self.setLayout(text_layout)

# Handles everything related to searching
class SearchWindow(QWidget):
    def __init__(self):
        super(SearchWindow, self).__init__()
        search_ui = QFile("ui/search.ui")
        search_ui.open(QFile.ReadOnly)
        
        loader = QUiLoader()
        self.swin = loader.load(search_ui)
        self.swin.show()

        # Layout extras
        self.swin.searchBar.setPlaceholderText("Enter URL...")

        # Button functions: clicking the search button or pressing return on the search bar
        self.swin.searchButton.clicked.connect(self.search_database)
        self.swin.searchBar.returnPressed.connect(self.search_database)
        self.swin.resultsBox.itemClicked.connect(self.open_html_view)

    def search_database(self):
        # Get key ready for searching and clear previous results
        key = self.swin.searchBar.text().strip()
        if not key:
            QMessageBox.warning(self, "Warning!", "Please enter a URL")
            return
        self.swin.resultsBox.clear()

        # For now, returns a list of results based on a certain url, but might be wise to make it
        # modular in the future to handle multiple types of queries
        try:
            res = api.query_files(key, "url")
            if res.status_code == 200:
                print("\nFound\n")
                found = res.json()
                for find in found:
                   self.swin.resultsBox.addItem(find["file_id"]) # idea being: use these file ids to do something with the files
            elif res.status_code == 400:
                QMessageBox.critical(self, "Error!", "Bad Request")
            else:
                QMessageBox.critical(self, "Error!", "Internal Server Error")
        except Exception as error:
            QMessageBox.critical(self, "Error!", "Something went wrong.")

    def get_html(self, file_id):
        try:
           res = api.get_file_data(file_id)
           if res.status_code == 404:
               return "File not found."
           return res.text
        except Exception as error:
            QMessageBox.critical(self, "Error!", "Something went wrong: {error}")
        res = "{\n  This is some placeholder text. \n}"
        return res

    def open_html_view(self, item):
        file_id = item.text()
        #file_id = "Placeholder"
        contents = self.get_html(file_id)

        # Same deal as in open_search
        self.twin = TextWindow(file_id, contents)
        self.twin.show()


class MainWindow(QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()

        # Qt .ui file loading and handling
        ui_file = QFile("ui/mainwindow.ui")
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

