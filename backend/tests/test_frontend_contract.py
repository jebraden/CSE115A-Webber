"""Real HTTP checks across the frontend client and threaded Flask boundary."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Thread

import httpx
import pytest
from werkzeug.serving import make_server

from src.app import create_app


@pytest.fixture
def live_backend(tmp_path):
    app = create_app(data_dir=str(tmp_path))
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    yield base_url, tmp_path
    server.shutdown()
    server.server_close()
    thread.join(3)


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


def test_connections_are_request_local_and_archive_routes_serve_stored_bytes(live_backend):
    base_url, root = live_backend
    source = seed(root)
    with ThreadPoolExecutor(max_workers=4) as workers:
        codes = list(workers.map(lambda _: httpx.request(
            "QUERY", base_url + "/search/snapshots", json={}, trust_env=False,
        ).status_code, range(12)))
    assert codes == [200] * 12
    response = httpx.get(base_url + "/data/snap/https://example.org/index.html", trust_env=False)
    assert response.status_code == 200
    assert "cdn.example" in response.text
    assert response.text == source
    assert "script-src 'none'" in response.headers["Content-Security-Policy"]
    assert (root / "original.html").read_text() == source


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
    assert "message" in response.json()
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
