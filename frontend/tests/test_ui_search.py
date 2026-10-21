import pytest
import requests

import src.api
import src.ui_search

class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


@pytest.fixture
def messages(monkeypatch):
    shown = []
    monkeypatch.setattr(
        src.ui_search.QMessageBox, "warning",
        staticmethod(lambda parent, title, text: shown.append(("warning", title, text))),
    )
    monkeypatch.setattr(
        src.ui_search.QMessageBox, "critical",
        staticmethod(lambda parent, title, text: shown.append(("critical", title, text))),
    )
    return shown


@pytest.fixture
def search_window(qtbot, messages):
    window = src.ui_search.SearchWindow()
    qtbot.addWidget(window.swin)  # the visible window is the one loaded from the .ui file
    return window


def search_for(window, key="example"):
    window.swin.searchBar.setText(key)
    window.swin.searchButton.click()


def result_texts(window):
    box = window.swin.resultsBox
    return [box.item(i).text() for i in range(box.count())]


def click_first_result(window):
    box = window.swin.resultsBox
    box.itemClicked.emit(box.item(0))  # same as the user clicking that row


# Search tests

def test_search_lists_the_file_ids(search_window, messages, monkeypatch):
    found = [{"snapshot_id": "s1", "file_id": "f1"},
             {"snapshot_id": "s1", "file_id": "f2"}]
    monkeypatch.setattr(src.api, "query_files", lambda key, field: FakeResponse(200, json_data=found))

    search_for(search_window)

    assert result_texts(search_window) == ["f1", "f2"]
    assert messages == []  


def test_search_sends_the_trimmed_key_to_the_url_field(search_window, monkeypatch):
    seen = {}

    def fake_query(key, field):
        seen.update(key=key, field=field)
        return FakeResponse(200, json_data=[])

    monkeypatch.setattr(src.api, "query_files", fake_query)

    search_for(search_window, "  example.com  ")

    assert seen == {"key": "example.com", "field": "url"}


def test_empty_key_shows_a_warning_and_skips_the_search(search_window, messages, monkeypatch):
    calls = []
    monkeypatch.setattr(src.api, "query_files", lambda key, field: calls.append(key))

    search_for(search_window, "   ")

    assert calls == []
    assert [kind for kind, _, _ in messages] == ["warning"]


def test_new_search_replaces_old_results(search_window, monkeypatch):
    monkeypatch.setattr(src.api, "query_files", lambda key, field: FakeResponse(
        200, json_data=[{"snapshot_id": "s1", "file_id": "f1"},
                        {"snapshot_id": "s1", "file_id": "f2"}]))
    search_for(search_window)

    monkeypatch.setattr(src.api, "query_files", lambda key, field: FakeResponse(
        200, json_data=[{"snapshot_id": "s1", "file_id": "f3"}]))
    search_for(search_window)

    assert result_texts(search_window) == ["f3"]


def test_bad_request_shows_an_error(search_window, messages, monkeypatch):
    monkeypatch.setattr(src.api, "query_files", lambda key, field: FakeResponse(400, text="bad regex"))

    search_for(search_window)

    assert len(messages) == 1
    kind, _, text = messages[0]
    assert kind == "critical"
    assert "Bad Request" in text


def test_server_error_shows_an_error(search_window, messages, monkeypatch):
    monkeypatch.setattr(src.api, "query_files", lambda key, field: FakeResponse(500))

    search_for(search_window)

    assert len(messages) == 1
    kind, _, text = messages[0]
    assert kind == "critical"
    assert "Internal Server Error" in text


def test_unreachable_server_shows_one_error(search_window, messages, monkeypatch):
    def server_down(key, field):
        raise requests.exceptions.ConnectionError("no server")

    monkeypatch.setattr(src.api, "query_files", server_down)

    search_for(search_window)

    assert [kind for kind, _, _ in messages] == ["critical"]


# Click tests for results

def test_clicking_a_result_opens_a_text_window(qtbot, search_window, monkeypatch):
    monkeypatch.setattr(src.api, "get_file_data",
                        lambda file_id: FakeResponse(200, text="just some text"))
    search_window.swin.resultsBox.addItem("f1")

    click_first_result(search_window)

    qtbot.addWidget(search_window.twin)
    assert search_window.twin.windowTitle() == "f1/_HTML Editor"
    assert search_window.twin.text_area.toPlainText() == "just some text"


def test_missing_file_says_so(qtbot, search_window, monkeypatch):
    monkeypatch.setattr(src.api, "get_file_data", lambda file_id: FakeResponse(404))
    search_window.swin.resultsBox.addItem("f1")

    click_first_result(search_window)

    qtbot.addWidget(search_window.twin)
    assert search_window.twin.text_area.toPlainText() == "File not found."


def test_failed_file_fetch_shows_an_error_instead_of_crashing(search_window, messages, monkeypatch):
    def server_down(file_id):
        raise requests.exceptions.ConnectionError("no server")

    monkeypatch.setattr(src.api, "get_file_data", server_down)
    search_window.swin.resultsBox.addItem("f1")

    click_first_result(search_window)

    assert [kind for kind, _, _ in messages] == ["critical"]


# Main window interaction tests

def test_search_menu_item_opens_the_search_window(qtbot):
    window = src.ui_search.MainWindow()
    qtbot.addWidget(window.mwin)

    window.mwin.actionSearch_Database.trigger()  

    qtbot.addWidget(window.swin.swin)
    assert window.swin.swin.isVisible()


def test_exit_menu_item_closes_the_main_window(qtbot):
    window = src.ui_search.MainWindow()
    qtbot.addWidget(window.mwin)

    window.mwin.actionExit.trigger()

    assert not window.mwin.isVisible()