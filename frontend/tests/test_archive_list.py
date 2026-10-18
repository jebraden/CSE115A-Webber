import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from frontend.src.archive_list.service import MockSnapshotService
from frontend.src.archive_list.window import ArchiveWindow


class ServiceTests(unittest.TestCase):
    def test_blank_returns_all_newest_first(self):
        results = MockSnapshotService().search_snapshots("  ")
        self.assertEqual([s.id for s in results], ["demo-004", "demo-003", "demo-002", "demo-001"])

    def test_partial_case_insensitive_match_keeps_url_history(self):
        results = MockSnapshotService().search_snapshots("  UCSC.EDU ")
        self.assertEqual([s.id for s in results], ["demo-003", "demo-001"])

    def test_no_match_and_empty_collection(self):
        self.assertEqual(MockSnapshotService().search_snapshots("missing.invalid"), [])
        self.assertEqual(MockSnapshotService([]).search_snapshots(""), [])


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = ArchiveWindow(MockSnapshotService(), demo=True)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    def test_initial_columns_and_read_only_results(self):
        table = self.window.table
        self.assertEqual(table.rowCount(), 4)
        self.assertEqual([table.horizontalHeaderItem(i).text() for i in range(3)],
                         ["URL", "Archived at (UTC)", "ID"])
        self.assertEqual(table.item(0, 1).text(), "2026-10-16 12:45:00")
        self.assertEqual(table.editTriggers(), table.EditTrigger.NoEditTriggers)

    def test_live_search_no_results_and_clear(self):
        w = self.window
        QTest.keyClicks(w.search_input, "UCSC")
        self.assertEqual(w.table.rowCount(), 2)
        w.search_input.setText("missing.invalid")
        self.assertEqual(w.table.rowCount(), 0)
        self.assertIn("No snapshots match", w.status.text())
        QTest.mouseClick(w.clear_button, Qt.MouseButton.LeftButton)
        self.assertEqual(w.search_input.text(), "")
        self.assertEqual(w.table.rowCount(), 4)

    def test_click_emits_correct_filtered_snapshot(self):
        w = self.window
        w.search_input.setText("python.org")
        emitted = []
        w.snapshot_requested.connect(emitted.append)
        cell = w.table.visualItemRect(w.table.item(0, 0)).center()
        QTest.mouseClick(w.table.viewport(), Qt.MouseButton.LeftButton, pos=cell)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].id, "demo-002")
        self.assertIsNone(emitted[0].local_path)

    def test_failure_clears_stale_results_and_retry_recovers(self):
        class FlakyService:
            fails = True

            def search_snapshots(self, query):
                if self.fails:
                    raise RuntimeError("Test failure")
                return MockSnapshotService().search_snapshots(query)

        service = FlakyService()
        self.window._service = service
        with self.assertLogs("frontend.src.archive_list.window", level="ERROR"):
            self.window.clear_button.click()
        self.assertEqual(self.window.table.rowCount(), 0)
        self.assertIn("Could not load", self.window.status.text())
        service.fails = False
        self.window.clear_button.click()
        self.assertEqual(self.window.table.rowCount(), 4)

    def test_empty_archive_message(self):
        window = ArchiveWindow(MockSnapshotService([]))
        self.assertEqual(window.table.rowCount(), 0)
        self.assertEqual(window.status.text(), "No archived webpages yet.")
        window.close()


if __name__ == "__main__":
    unittest.main()
