import os
import sqlite3
import asyncio
import pytest
from unittest.mock import MagicMock, AsyncMock
from src.scraping.scraper import PageScraper

class FakeRequest:
    def __init__(self, url):
        self.url = url
        self.method = "GET"

    async def headers_array(self):
        return []


class FakeResponse:
    def __init__(self, request, body):
        self.request = request
        self.url = request.url
        self.status = 200
        self._body = body

    async def all_headers(self):
        return {"content-type": "text/html; charset=utf-8"}

    async def headers_array(self):
        return [
            {
                "name": "Content-Type",
                "value": "text/html; charset=utf-8",
            }
        ]

    async def body(self):
        return self._body


class FakeElement:
    def __init__(self, url):
        self.url = url

    async def evaluate(self, f, attribute):
        return self.url


class FakeLocator:
    def __init__(self, urls):
        self.elements = [FakeElement(url) for url in urls]

    async def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class FakePage:
    def __init__(self, pages):
        self.pages = pages
        self.handlers = {}
        self.current_url = None

    def on(self, event, callback):
        self.handlers[event] = callback

    async def goto(self, url, wait_until:str = None):
        self.current_url = url
        request = FakeRequest(url)
        self.handlers["request"](request)
        response = FakeResponse(request, self.pages[url]["body"],)

        self.handlers["response"](response)

    def locator(self, selector):
        links = self.pages[self.current_url]["links"]
        return FakeLocator(links.get(selector, []))

    async def wait_for_timeout(self, timeout):
        pass

    async def evaluate(self, expression):
        return 0

    async def setExtraHTTPHeaders(self, headers):
        pass


class FakeBrowser:
    def __init__(self, pages):
        self.pages = pages

    async def new_page(self):
        return FakePage(self.pages)

    async def close(self):
        pass


class FakePlaywrightContext:
    def __init__(self, pages):
        self.pages = pages
        self.chromium = self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def launch(self, **kwargs):
        return FakeBrowser(self.pages)

@pytest.fixture 
def test_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_archive.db"

    schema = os.path.join(os.path.dirname(__file__), "./../db/001_init.sql")
    with sqlite3.connect(db_file) as db:
        with open(schema, "r") as sql_script:
            db.executescript(sql_script.read())
    return str(db_file)
            
@pytest.fixture
def test_conn(test_db): 
    conn = sqlite3.connect(test_db)
    conn.row_factory = sqlite3.Row
    return conn



class TestArchivePageIntegration:
    @pytest.mark.asyncio
    async def test_archive_page(
        self, test_conn, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("HOME", str(tmp_path))
        root = "https://example.com/"
        about = "https://example.com/about"
        contact = "https://example.com/contact"

        pages = {
            root: {
                "body": b"""
                    <html>
                        <a href="/about">About</a>
                        <a href="/contact">Contact</a>
                    </html>
                    """,
                "links": {
                    "a[href]": [about, contact],
                },
            },
            about: {
                "body": b"<html><body>About Us</body></html>",
                "links": {},
            },
            contact: {
                "body": b"<html><body>Contact Us</body></html>",
                "links": {},
            },
        }

        monkeypatch.setattr("src.scraping.scraper.async_playwright",
                lambda: FakePlaywrightContext(pages),)
        scraper = PageScraper(db_conn=test_conn)

        snap_id = await scraper.archive_page(root)

        assert snap_id is not None

        rows = test_conn.execute(
            """
            SELECT snapshot_id, host, remote_path, on_disk_path
            FROM files
            WHERE snapshot_id = ?
            """,
            (snap_id,),
        ).fetchall()
        assert len(rows) == 3

        count = test_conn.execute(
            "SELECT COUNT(*) FROM snapshots",
        ).fetchone()[0]

        assert count == 1
