import pytest
import os
import src
import sqlite3
from flask import Flask, request
import threading
from werkzeug.serving import make_server

from playwright.async_api import async_playwright
from src.scraping.scraper import PageScraper


@pytest.fixture
def test_server():
    app = Flask(__name__)

    @app.route("/")
    def index():
        return ( 
            """
            <html>
                <a href="/about">About</a>
                <a href="/contact">Contact</a>
                <form action="/search">
                    <input name="q">
                </form>
            </html>
            """)

    @app.route("/about")
    def about(): 
        return "<html><body>About Us</body></html>"

    @app.route("/contact")
    def contact():
        return "<html><body>Contact Us</body></html>"

    @app.route("/search")
    def search():
        return "<html><body>Search Us</body></html>"

    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()

    yield f"https://127.0.0.1:{server.server_port}"

    server.shutdown()
    thread.join()


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_archive.db"
    monkeypatch.setattr(src.scraping.scraper, "db_path", str(db_file))
    
    schema = os.path.join(os.path.dirname(__file__), "./../db/001_init.sql")
    with sqlite3.connect(db_file) as db:
        with open(schema, "r") as sql_script:
            db.executescript(sql_script.read())
    return str(db_file)
        
@pytest.fixture
def test_conn(test_db):
    return sqlite3.connect(test_db)


class TestProcessHyperlinkIntegration:
    @pytest.mark.asyncio
    async def test_gather_and_proc_hyperlinks(
        self, test_conn, test_server, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("HOME", str(tmp_path))
        scraper = PageScraper(db_conn=test_conn)

        snap_id = await scraper.archive_page(test_server)

        assert snap_id is not None

        rows = test_conn.execute(
            """
            SELECT host, remote_path, snapshot_id, on_disk_path
            FROM files
            WHERE snapshot_id = ?,
            """,
            (snap_id,)
        ).fetchall()

        paths = {row["remote_path"] for row in rows}
        assert paths == {"/", "about", "/contact", "/search",}

        assert len(rows) == 4

        for row in rows:
            assert row["snapshot_id"] == snap_id
            assert os.path.isfile(row["on_disk_path"])

        snap_count = test_conn.execute(
            "SELECT COUNT(*) FROM snapshots"
        ).fetchone()[0]
        assert snap_count == 1

