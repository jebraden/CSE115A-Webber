"""Threaded HTTP regressions for concurrent searches and failed captures."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Event, Thread

import httpx
import pytest
from playwright.async_api import TimeoutError as ScrapeTimeout
from werkzeug.serving import make_server
from unittest.mock import patch

from src.app import create_app


@pytest.fixture
def live_backend(tmp_path, monkeypatch):
    database = tmp_path / "archive.db"
    with patch("src.request_manager.DB_PATH", database), patch(
        "src.app.DB_PATH", database
    ), patch("src.request_manager.BASE_DIR", str(tmp_path)):
        app = create_app()
        with sqlite3.connect(database) as db:
            db.execute(
                "INSERT INTO snapshots VALUES (?, ?, ?, ?)",
                ("existing", "https://example.org/old", 100, 101),
            )
        db.close()
        server = make_server("127.0.0.1", 0, app, threaded=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{server.server_port}",
                timeout=3,
                trust_env=False,
            ) as client:
                yield client
        finally:
            server.shutdown()
            server.server_close()
            thread.join(3)


def test_2_2_1_search_can_read_while_snapshot_is_being_written(
    live_backend, monkeypatch
):
    write_started = Event()
    allow_commit = Event()

    class PausedScraper:
        def __init__(self, db_conn, **kwargs):
            self.db = db_conn

        async def archive_page(self, url):
            self.db.execute(
                "INSERT INTO snapshots VALUES ('new', ?, 100, 101)", (url,)
            )
            write_started.set()
            if not allow_commit.wait(timeout=5):
                raise TimeoutError(
                    "The test did not release the pending write"
                )
            self.db.commit()
            return "new"

    monkeypatch.setattr("src.request_manager.PageScraper", PausedScraper)
    client = live_backend
    with ThreadPoolExecutor(max_workers=4) as workers:
        pending = workers.submit(
            client.post,
            "/snapshots/create",
            json={"url": "https://example.org/new"},
            timeout=7,
        )
        try:
            assert write_started.wait(timeout=3)
            # Concurrent requests must finish while the new snapshot is uncommitted.
            responses = list(
                workers.map(
                    lambda _: client.request(
                        "QUERY", "/search/snapshots", json={}
                    ),
                    range(12),
                )
            )
            assert all(response.status_code == 200 for response in responses)
            assert all(
                response.json() == ["existing"] for response in responses
            )
        finally:
            allow_commit.set()
        assert pending.result().status_code == 201
    response = client.request("QUERY", "/search/snapshots", json={})
    assert response.status_code == 200
    assert set(response.json()) == {"existing", "new"}


@pytest.mark.parametrize(
    "failure,status", [(RuntimeError, 500), (ScrapeTimeout, 504)]
)
def test_failed_capture_can_be_retried_without_saving_partial_data(
    live_backend, monkeypatch, failure, status
):
    class FailedScraper:
        def __init__(self, db_conn, **kwargs):
            self.db = db_conn

        async def archive_page(self, url):
            self.db.execute(
                "INSERT INTO snapshots VALUES ('failed', ?, 100, 101)", (url,)
            )
            raise failure("Simulated capture failure")

    monkeypatch.setattr("src.request_manager.PageScraper", FailedScraper)
    client = live_backend
    response = client.post(
        "/snapshots/create", json={"url": "https://example.org/"}
    )
    assert response.status_code == status

    class SuccessfulScraper(FailedScraper):
        async def archive_page(self, url):
            self.db.execute(
                "INSERT INTO snapshots VALUES ('success', ?, 100, 101)", (url,)
            )
            self.db.commit()
            return "success"

    monkeypatch.setattr("src.request_manager.PageScraper", SuccessfulScraper)
    response = client.post(
        "/snapshots/create", json={"url": "https://example.org/retry"}
    )
    assert response.status_code == 201
    found = client.request("QUERY", "/search/snapshots", json={})
    assert found.status_code == 200
    assert set(found.json()) == {"existing", "success"}
