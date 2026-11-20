"""Interaction tests for the central archive list's batch deletion controls."""

import json

import httpx
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QStyle, QStyleOptionViewItem

from frontend.src.api import InternalServerError, WebberAPI
from frontend.tests.test_main_window import app, select, window


def _click_checkbox(snapshot_list, row):
    index = snapshot_list.model().index(row, 0)
    option = QStyleOptionViewItem()
    option.initFrom(snapshot_list)
    option.widget = snapshot_list
    option.rect = snapshot_list.visualRect(index)
    option.features = QStyleOptionViewItem.ViewItemFeature.HasCheckIndicator
    indicator = snapshot_list.style().subElementRect(
        QStyle.SubElement.SE_ItemViewItemCheckIndicator, option, snapshot_list
    )
    assert option.rect.contains(indicator)
    QTest.mouseClick(snapshot_list.viewport(), Qt.MouseButton.LeftButton, pos=indicator.center())


def _answer_confirmation(window, text):
    observed = []

    def answer():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        observed.append((dialog.text(), dialog.standardButton(dialog.defaultButton())))
        next(button for button in dialog.buttons() if button.text() == text).click()

    QTimer.singleShot(0, answer)
    window.ui.deleteSnapshotsButton.click()
    return observed


def test_us_3_3_t_2_checkboxes_are_independent_of_archive_navigation(window):
    window.show()
    QApplication.processEvents()
    snapshots = window.ui.snapshotList
    delete = window.ui.deleteSnapshotsButton
    mode_button = window.ui.selectSnapshotsButton
    assert mode_button.text() == "Select"
    assert delete.isHidden()
    assert snapshots.item(0).data(Qt.ItemDataRole.CheckStateRole) is None

    mode_button.click()
    assert mode_button.text() == "Cancel"
    assert not delete.isHidden()
    assert not delete.isEnabled()

    snapshots.setCurrentRow(0)
    active_id = window._active_tab_id
    _click_checkbox(snapshots, 1)
    assert window._active_tab_id == active_id
    assert window.tab_bar.count() == 1
    assert delete.text() == "Delete selected (1)"

    _click_checkbox(snapshots, 0)
    assert delete.text() == "Delete selected (2)"
    _click_checkbox(snapshots, 1)
    assert snapshots.item(0).checkState() == Qt.CheckState.Checked
    assert snapshots.item(1).checkState() == Qt.CheckState.Unchecked
    mode_button.click()
    assert mode_button.text() == "Select"
    assert delete.isHidden()
    assert not delete.isEnabled()
    assert snapshots.item(0).data(Qt.ItemDataRole.CheckStateRole) is None
    assert window._active_tab_id == active_id

    mode_button.click()
    assert snapshots.item(0).checkState() == Qt.CheckState.Unchecked
    assert snapshots.item(1).checkState() == Qt.CheckState.Unchecked


def test_us_3_3_t_2_cancel_and_confirm_send_only_visible_checked_snapshot_ids(window, monkeypatch):
    service_delete = window._service.delete_snapshots
    requests = []

    def delete(snapshot_ids):
        requests.append(snapshot_ids)
        service_delete(snapshot_ids)

    monkeypatch.setattr(window._service, "delete_snapshots", delete)
    snapshots = window.ui.snapshotList
    select(window, "missing")
    window.ui.selectSnapshotsButton.click()
    for row in range(snapshots.count()):
        snapshots.item(row).setCheckState(Qt.CheckState.Checked)

    assert _answer_confirmation(window, "Cancel") == [
        ("Permanently delete 2 snapshots?", QMessageBox.StandardButton.Cancel)
    ]
    assert snapshots.count() == 2
    assert requests == []
    assert window.ui.selectSnapshotsButton.text() == "Cancel"

    window.ui.searchInput.setText("missing.example")
    assert window.ui.deleteSnapshotsButton.text() == "Delete selected (1)"
    assert _answer_confirmation(window, "Delete") == [
        ("Permanently delete 1 snapshot?", QMessageBox.StandardButton.Cancel)
    ]
    assert requests == [["missing"]]
    assert window.ui.selectSnapshotsButton.text() == "Select"
    assert window.ui.deleteSnapshotsButton.isHidden()
    assert not window.ui.deleteSnapshotsButton.isEnabled()
    assert snapshots.count() == 0
    assert window.tab_bar.count() == 0
    assert window.statusBar().currentMessage() == "Deleted 1 snapshot."
    window.ui.searchInput.clear()
    assert [snapshot.id for snapshot in window._snapshots] == ["valid"]
    assert snapshots.item(0).data(Qt.ItemDataRole.CheckStateRole) is None


def test_us_3_3_t_2_batch_delete_failure_keeps_results_and_marks(window, monkeypatch):
    def fail(snapshot_ids):
        raise RuntimeError("still archived")

    errors = []
    monkeypatch.setattr(window._service, "delete_snapshots", fail)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: errors.append(args[1:]))
    snapshots = window.ui.snapshotList
    window.ui.selectSnapshotsButton.click()
    snapshots.item(0).setCheckState(Qt.CheckState.Checked)
    snapshots.item(1).setCheckState(Qt.CheckState.Checked)

    _answer_confirmation(window, "Delete")

    assert errors == [("Deletion failed", "Could not delete 2 snapshots.")]
    assert window.ui.selectSnapshotsButton.text() == "Cancel"
    assert window.ui.deleteSnapshotsButton.text() == "Delete selected (2)"
    assert snapshots.count() == 2
    assert window.statusBar().currentMessage() == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [202, 500])
async def test_us_3_3_t_2_batch_delete_client_uses_existing_endpoint(status):
    def respond(request):
        assert request.method == "POST"
        assert request.url.path == "/snapshots/delete"
        assert json.loads(request.content) == {"ids": ["one", "two"]}
        return httpx.Response(status, json={"message": "Unable to delete"})

    api = WebberAPI("http://webber.test")
    await api.aclose()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        api.client = client
        if status == 500:
            with pytest.raises(InternalServerError):
                await api.delete_snapshots(["one", "two"])
        else:
            await api.delete_snapshots(["one", "two"])
