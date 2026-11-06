"""Run a slow, offline search to inspect GUI responsiveness manually."""
import asyncio
import sys

from PySide6.QtWidgets import QApplication

from .archive_list.service import MockSnapshotService
from .archive_list.window import ArchiveWindow


class SlowDemoService(MockSnapshotService):
    async def search_snapshots(self, query):
        await asyncio.sleep(2)
        if query.casefold() == "error":
            raise RuntimeError("Simulated service failure for the threading demo")
        return super().search_snapshots(query)


def main():
    app = QApplication(sys.argv)
    window = ArchiveWindow(SlowDemoService(), demo=True)
    window.setWindowTitle("Webber — Background search demo (2-second delay)")
    window.search_input.setPlaceholderText("Try UCSC, Python, or error…")
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
