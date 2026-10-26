"""Widgets for the startup preview, separate from application lifecycle."""
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class StartupWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Webber")
        self.resize(480, 160)
        layout = QVBoxLayout(self)
        self.status = QLabel("Starting backend…")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        layout.addWidget(close)

    def backend_ready(self):
        self.status.setText("Backend is ready.")

    def backend_failed(self, message):
        self.status.setText(message)
