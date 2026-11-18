"""Real HTTP checks across the frontend client and threaded Flask boundary."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Event, Lock, Thread
from time import sleep

import httpx
import pytest
from werkzeug.serving import make_server

from src.app import close_archive_database, create_app
from src.request_manager import RequestManager


@pytest.fixture
def live_backend(tmp_path):
    app = create_app(data_dir=str(tmp_path))
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield base_url, tmp_path
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        close_archive_database(app)


def seed(root):
    html = root / "original.html"
    source = '<h1>Offline</h1><link rel="stylesheet" href="/style.css"><img src="https://cdn.example/pic.svg">'
    html.write_text(source)
    css = root / "style.css"
    css.write_text('h1 { color: red; background: url("https://cdn.example/pic.svg") }')
    with sqlite3.connect(root / "archive.db") as db:
        db.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?)", ("snap", "https://example.org/a.b?[x]", 100, 101))
        for file_id, path, host, remote_path, content_type in [
            ("html", html, "example.org", "/index.html", "text/html"),
            ("css", css, "example.org", "/style.css", "text/css"),
        ]:
            db.execute("""INSERT INTO files VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, jsonb(?), jsonb(?), ?, ?, jsonb(?))""",
                (file_id, "snap", str(path), path.stat().st_size, "https", 443, host, remote_path,
                 100, "GET", "{}", "{}", 101, 200, '{"Content-Type":["' + content_type + '"]}'))
    return source


def test_real_api_json_search_metadata_and_literal_matching(live_backend):
    base_url, root = live_backend
    source = seed(root)

    with httpx.Client(base_url=base_url, trust_env=False) as client:
        assert client.request("QUERY", "/search/snapshots", json={}).json() == ["snap"]
        pairs = client.request("QUERY", "/search/files", json={"snapshot_id": "snap"}).json()
        assert {pair["file_id"] for pair in pairs} == {"html", "css"}
        metadata = client.get("/files/html").json()
        assert metadata["response"]["received_time"]["sec"] == 101
        assert client.get("/files/html/data").text == source
        error = client.post("/snapshots/create", json={"url": "ucsc.edu"})
        assert error.status_code == 400
        assert "http" in error.json()["message"]


def test_reader_connection_is_reused_and_archive_routes_serve_stored_bytes(live_backend, monkeypatch):
    base_url, root = live_backend
    source = seed(root)
    reader_connections = []
    active_reader = Lock()
    query = RequestManager.query_snapshots

    def record_connection(self, request):
        assert active_reader.acquire(blocking=False), "Overlapping calls used the shared reader"
        try:
            reader_connections.append(self.db)
            # Release the GIL so concurrent HTTP requests can reach the backend.
            sleep(0.02)
            assert self.db.execute("PRAGMA query_only").fetchone()[0] == 1
            return query(self, request)
        finally:
            active_reader.release()

    monkeypatch.setattr(RequestManager, "query_snapshots", record_connection)
    with ThreadPoolExecutor(max_workers=4) as workers:
        codes = list(workers.map(lambda _: httpx.request(
            "QUERY", base_url + "/search/snapshots", json={}, trust_env=False,
        ).status_code, range(12)))
    assert codes == [200] * 12
    assert len(reader_connections) == 12
    assert len(set(reader_connections)) == 1
    response = httpx.get(base_url + "/data/snap/https://example.org/index.html", trust_env=False)
    assert response.status_code == 200
    assert "cdn.example" in response.text
    assert response.text == source
    assert "script-src 'none'" in response.headers["Content-Security-Policy"]
    assert (root / "original.html").read_text() == source


def test_search_can_read_while_snapshot_is_being_written(live_backend, monkeypatch):
    from src import request_manager

    write_started = Event()
    allow_commit = Event()
    writer_connections = []
    reader_connections = []
    query = RequestManager.query_snapshots
    delete = RequestManager.delete_snapshot

    def record_query(self, request):
        reader_connections.append(self.db)
        return query(self, request)

    def record_delete(self, snapshot_id):
        writer_connections.append(self.db)
        return delete(self, snapshot_id)

    class PausedScraper:
        def __init__(self, db_conn, **kwargs):
            self.db = db_conn

        async def archive_page(self, url):
            writer_connections.append(self.db)
            self.db.execute("INSERT INTO snapshots VALUES ('new', ?, 100, 100)", (url,))
            write_started.set()
            if not allow_commit.wait(timeout=5):
                raise TimeoutError("The test did not release the pending write")
            self.db.commit()
            return "new"

    monkeypatch.setattr(request_manager, "PageScraper", PausedScraper)
    monkeypatch.setattr(RequestManager, "query_snapshots", record_query)
    monkeypatch.setattr(RequestManager, "delete_snapshot", record_delete)
    base_url, root = live_backend
    seed(root)
    with ThreadPoolExecutor(max_workers=1) as workers:
        pending = workers.submit(
            httpx.post,
            base_url + "/snapshots/create",
            json={"url": "https://example.org/new"},
            trust_env=False,
            timeout=7,
        )
        try:
            assert write_started.wait(timeout=3)
            with httpx.Client(base_url=base_url, trust_env=False, timeout=3) as client:
                before = client.request("QUERY", "/search/snapshots", json={})
                assert before.status_code == 200
                assert before.json() == ["snap"]
                with ThreadPoolExecutor(max_workers=4) as readers:
                    snapshot, metadata, source, limits = readers.map(client.get, (
                        "/snapshots/snap", "/files/html",
                        "/data/snap/https://example.org/index.html", "/statistics/limits",
                    ))
                assert all(response.status_code == 200 for response in (snapshot, metadata, source, limits))
                assert snapshot.json()["id"] == "snap"
                assert "Offline" in source.text
        finally:
            allow_commit.set()
        assert pending.result().status_code == 201
    with httpx.Client(base_url=base_url, trust_env=False) as client:
        after = client.request("QUERY", "/search/snapshots", json={})
        assert after.status_code == 200
        assert set(after.json()) == {"snap", "new"}
        assert client.delete("/snapshots/new").status_code == 202
    assert len(writer_connections) == len(reader_connections) == 2
    assert len(set(writer_connections)) == len(set(reader_connections)) == 1
    assert writer_connections[0] is not reader_connections[0]


def test_unexpected_route_failure_uses_flask_default(live_backend, monkeypatch):
    def fail(self, _snapshot_id):
        raise RuntimeError("Private backend diagnostic")

    monkeypatch.setattr(RequestManager, "get_snapshot", fail)
    base_url, _ = live_backend
    response = httpx.get(base_url + "/snapshots/invalid", trust_env=False)
    assert response.status_code == 500
    assert response.headers["Content-Type"].startswith("text/html")
    assert "Private backend diagnostic" not in response.text


def test_statistics_limits_use_the_configured_collection(live_backend):
    base_url, root = live_backend
    seed(root)
    response = httpx.get(base_url + "/statistics/limits", trust_env=False)
    assert response.status_code == 200
    expected = {"sec": 100, "nsec": 0}
    assert response.json() == {
        "first_snapshot": expected,
        "last_snapshot": expected,
    }
    with httpx.Client(base_url=base_url, trust_env=False) as client:
        statistics = client.request("QUERY", "/statistics", json={"intervals": [{}]})
    assert statistics.status_code == 200
    assert statistics.json()["statistics"][0]["snapshots"] == 1
    assert statistics.json()["statistics"][0]["files"] == 2


def test_failed_scrape_rolls_back_snapshot(live_backend, monkeypatch):
    from src import request_manager
    class FailedScraper:
        def __init__(self, db_conn, **kwargs):
            self.db = db_conn
        async def archive_page(self, url):
            self.db.execute("INSERT INTO snapshots VALUES ('failed', ?, 100, 100)", (url,))
            raise RuntimeError("Simulated scrape failure")
    monkeypatch.setattr(request_manager, "PageScraper", FailedScraper)
    base_url, root = live_backend
    response = httpx.post(base_url + "/snapshots/create", json={"url":"https://example.org/"}, trust_env=False)
    assert response.status_code == 500
    assert response.json()["message"].startswith("Internal Server Error: Could not archive this page")
    with sqlite3.connect(root / "archive.db") as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


def test_delete_uses_the_configured_collection(live_backend):
    base_url, root = live_backend
    seed(root)
    directory = root / "snap"
    directory.mkdir()
    (directory / "saved.html").write_text("saved")
    assert httpx.delete(base_url + "/snapshots/snap", trust_env=False).status_code == 202
    assert not directory.exists()
    with sqlite3.connect(root / "archive.db") as db:
        assert db.execute("SELECT count(*) FROM snapshots").fetchone()[0] == 0


def test_batch_delete_uses_the_configured_collection(live_backend):
    base_url, root = live_backend
    seed(root)
    directory = root / "snap"
    directory.mkdir()
    (directory / "saved.html").write_text("saved")
    with httpx.Client(base_url=base_url, trust_env=False) as client:
        assert client.post("/snapshots/delete", json={"ids": ["snap"]}).status_code == 202
        assert client.request("QUERY", "/search/snapshots", json={}).json() == []
    assert not directory.exists()
