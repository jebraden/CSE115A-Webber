from src.scraping.scraper import (
    PageScraper,
    HyperlinkRules,
)

import src

from unittest.mock import AsyncMock, MagicMock, patch
from playwright.async_api import async_playwright


import pytest
import sqlite3
import asyncio
import json
import os
import time



class TestDataPath:
    def setup(self):
        self.scraper = PageScraper()
        self.scraper.snap_id = "test-snapshot"
        self.scraper.origin_host = "example.com"
        self.scraper.base_dir = "/tmp/test-snapshot/example.com"

    def test_preserves_url_path(self):
        self.setup()
        path = self.scraper.data_path(
            "https://example.com/blog/thingy.html"
        )

        assert path.endswith(
            "https/example.com/blog/thingy.html"
        )

    def test_dir_url_use_indx(self):
        self.setup()
        path = self.scraper.data_path(
            "https://example.com/blog/"
        )

        assert path.endswith(
            "https/example.com/blog/index.html"
        )

    def test_http_path(self):
        self.setup()
        path = self.scraper.data_path(
            "http://example.com/thingy.html"
        )

        assert path.endswith(
            "http/example.com/thingy.html"
        )


    def test_root_use_indx(self):
        self.setup()
        path = self.scraper.data_path("https://example.com/")

        assert path.endswith("https/example.com/index.html")

    def test_query_str_distinct_paths(self):
        self.setup()
        dark_magician = self.scraper.data_path(
            "https://example.com/card?q=dark_magician"
        )

        kuriboh = self.scraper.data_path(
            "https://example.com/card?q=kuriboh"
        )
        assert dark_magician != kuriboh

    def test_query_hash_preserve_ext(self):
        self.setup()
        path = self.scraper.data_path(
            "https://example.com/cards.html?q=griffoh"
        )
        assert path.endswith(".html")
        assert not "griffoh" in path

    def test_url_encoded_chars(self):
        self.setup()
        path = self.scraper.data_path(
            "https://example.com/my%20page.html"
        )
        assert path.endswith("https/example.com/my%20page.html")

    def test_no_dup_ext(self):
        self.setup()
        path = self.scraper.data_path(
            "https://example.com/styles/celtic_guardian.css"
        )
        assert not path.endswith(".css.css")

    def test_add_ext_from_type(self):
        self.setup()
        path = self.scraper.data_path(
            "https://example.com/styles/blue_eyes_white_dragon",
            resource_type="css"
        )
        assert path.endswith("blue_eyes_white_dragon.css")

    def test_ext_resource_preserve_host(self):
        self.setup()
        path = self.scraper.data_path(
            "https://fonts.ygo.com/griffoh/font.woff2"
        )
        assert path is not None
        assert "https/fonts.ygo.com" in path
        assert path.endswith("griffoh/font.woff2")

    def test_reject_external_ext_js_keep_same_js(self):
        self.setup()
        path = self.scraper.data_path(
            "https://komoney.com/money.js"
        )
        assert path is None

        path = self.scraper.data_path(
            "https://komoney.com/money"
        )
        assert path is None

        path = self.scraper.data_path(
            "https://example.com/money.js"
        )
        assert path is not None

    def test_fragments_no_change_path(self):
        self.setup()
        f = self.scraper.data_path(
            "https://example.com/page.html#s1"
        )
        s = self.scraper.data_path(
            "https://example.com/page.html#s2"
        )
        assert f == s



class FakeRequest:
    url = "https://example.com/search?q=kuriboh&q=mitsurugi&e="
    method = "POST"
    array = [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Cookie", "value": "kuriboh=3"},
            {"name": "Cookie", "value": "dark_magician=5"},
        ]

    async def headers_array(self):
        return self.array

class FakeResponse:
    def __init__(self, request, url=None, body=b"<html>The ultimate engine of destruction: Blue Eyes White Dragon</html>"):
        self.request = request
        self.url = url or request.url
        self.status = 200
        self._body = body

    async def all_headers(self):
        return {"content-type": "text/html; charset=utf-8"}

    async def headers_array(self):
        return [
            {"name": "Content-Type", "value": "text/html; charset=utf-8"}
        ]

    async def body(self):
        return self._body


class TestRequestMetadata:

    @pytest.mark.asyncio
    async def test_preserve_method_headers(self):
        scraper = PageScraper()
        metadata = await scraper.collect_req_metadata(FakeRequest())

        assert metadata["request_method"] == "POST"
        assert metadata["request_headers"] == {
            "content-type": ["application/json"],
            "cookie": ["kuriboh=3", "dark_magician=5"]
        }
    @pytest.mark.asyncio
    async def test_parse_repeat_query_params(self):
        scraper = PageScraper()
        metadata = await scraper.collect_req_metadata(FakeRequest())

        assert metadata["request_parameters"] == {
            "q": ["kuriboh", "mitsurugi"],
            "e": [""],
        }

    @pytest.mark.asyncio
    async def test_records_req_time(self):
        scraper = PageScraper()
        before = time.time()
        meta = await scraper.collect_req_metadata(FakeRequest())
        after = time.time()
        assert before <= meta["request_sent_time"] <= after

    @pytest.mark.asyncio
    async def test_no_query_param_handled(self):
        scraper = PageScraper()
        req = FakeRequest()
        req.url = "http://example.com"

        meta = await scraper.collect_req_metadata(req)
        assert meta["request_parameters"] == {}

    def test_resource_type(self):
        content = [
            "text/html", "text/html; charset=utf-8", 
            "text/css; charset=utf-8", "TEXT/CSS",
            "application/javascript", "font/woff2", "some/junk"
        ]
        expected = [
            "html", "html", "css", "css", "js", "woff2", None
        ]

        scraper = PageScraper()

        for i in range(0, len(content)):
            assert scraper.resource_type(content[i]) == expected[i]


class TestHandleResponse:
    def setup(self):
        self.scraper = PageScraper()
        self.scraper.snap_id = "test-snapshot"
        self.origin_host = "example.com"
        self.scraper.origin_host = "example.com"
        self.scraper.base_dir = "/tmp/test-snapshot/example.com"
        self.scraper.saved_urls = set()
        self.scraper.req_metadata = {}
        self.scraper.db = MagicMock()

    def create_test_db(self, tmp_path):
        db = sqlite3.connect(os.path.join(tmp_path, "test.db"))
        schema = os.path.join(os.path.dirname(__file__), 
            "./../db/001_init.sql")
        with open(schema, "r") as sql_script:
            db.executescript(sql_script.read())
        self.scraper.db = db
        return db

    def add_snapshot_record(self, db, snapshot):
        db.execute(
            """
            INSERT INTO snapshots (id, url, start_time, end_time)
            VALUES (?, ?, ?, ?)
            """,
            (
                 snapshot,
                 "https://example.com",
                 time.time(),
                 time.time(),
            ),
        )
        db.commit()

    def set_req_vals(self, req):
        req.url = "https://example.com/page.html"
        req.method = "GET"
        req.array = [{"name": "Accept", "value": "text/html"}]


    @pytest.mark.asyncio
    async def test_missing_req_meta_skip_resp(self):
        self.setup()
        resp = FakeResponse(FakeRequest())

        await self.scraper.handle_response(resp)

        self.scraper.db.execute.assert_not_called()

        assert resp.url not in self.scraper.saved_urls

    @pytest.mark.asyncio    
    async def test_dup_url_skipped(self):
        self.setup()
        req = FakeRequest()
        resp = FakeResponse(req)

        self.scraper.saved_urls.add(resp.url)
        self.scraper.req_metadata[id(req)] = asyncio.create_task(
            asyncio.sleep(0, result={})
        )

        await self.scraper.handle_response(resp)

        self.scraper.db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_file_write_fail_no_insert_row(self):
        self.setup()
        req = FakeRequest()
        self.set_req_vals(req)
        resp = FakeResponse(req)

        self.scraper.req_metadata[id(req)] = asyncio.create_task(
            asyncio.sleep(0, result={
                "request_sent_time": 1.0,
                "request_method": "GET",
                "request_headers": {},
                "request_parameters": {},
            })
        )

        with patch.object(
                self.scraper, "write_resource_file", return_value=None
        ):
            await self.scraper.handle_response(resp)
        self.scraper.db.execute.assert_not_called()
        assert resp.url not in self.scraper.saved_urls

    @pytest.mark.asyncio
    async def test_meta_task_fail_skip_resp(self):
        self.setup()
        req = FakeRequest()
        self.set_req_vals(req)
        resp = FakeResponse(req)

        async def fail():
            raise RuntimeError("meta fail")

        self.scraper.req_metadata[id(req)] = asyncio.create_task(fail())

        await self.scraper.handle_response(resp)
        self.scraper.db.execute.assert_not_called()
        assert resp.url not in self.scraper.saved_urls

    @pytest.mark.asyncio
    async def test_successful_resp_saved(self):
        self.setup()
        req = FakeRequest()
        self.set_req_vals(req)
        resp = FakeResponse(req)
        self.scraper.req_metadata[id(req)] = asyncio.create_task(
            asyncio.sleep(0, result={
                "request_sent_time": 1.0,
                "request_method": "GET",
                "request_headers": {},
                "request_parameters": {},
            })
        )

        with patch.object(
            self.scraper,
            "write_resource_file",
            return_value="/tmp/page.html",
        ), patch("os.path.getsize", return_value=100) as write_file:
            await self.scraper.handle_response(resp)
        
        write_file.assert_called_once()
        assert resp.url in self.scraper.saved_urls
        self.scraper.db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_htpp_err_resp_captured(self, tmp_path):
        self.setup()
        db = self.create_test_db(tmp_path)

        self.add_snapshot_record(db, self.scraper.snap_id)

        req = FakeRequest()
        self.set_req_vals(req)
        req.url = "https://example.com/missing.html"
        resp = FakeResponse(req, body=b"<html>Not Found</html>")
        resp.status = 404
        
        self.scraper.req_metadata[id(req)] = asyncio.create_task(
            asyncio.sleep(0, result={
                "request_sent_time": 1.0,
                "request_method": "GET",
                "request_headers": {},
                "request_parameters": {},
            })
        )

        with patch.object(
            self.scraper, 
            "write_resource_file", 
            return_value="/tmp/missing.html",
        ), patch("os.path.getsize", return_value=100):
            await self.scraper.handle_response(resp)

        row = db.execute(
            """
            SELECT response_code
            FROM files
            WHERE protocol = ? AND host = ? AND remote_path = ?
            """,
            ("https", "example.com", "/missing.html"),
        ).fetchone()

        assert row is not None
        assert row[0] == 404
        assert resp.url in self.scraper.saved_urls

    @pytest.mark.asyncio
    async def test_resp_metadata_persisted(self, tmp_path):
        self.setup()
        db = self.create_test_db(tmp_path)
        self.add_snapshot_record(db, self.scraper.snap_id)
        req = FakeRequest()
        req.url = (
            "https://example.com/search"
            "?q=lo&q=skull_guardian&e="
        )
        req.method = "POST"
        req.array = [
            {"name": "Content-Type", "value": "application/json"},
            {"name": "Cookie", "value": "lo=3"},
            {"name": "Cookie", "value": "skull_guardian=4"},
        ]

        resp = FakeResponse(req)
        resp.url = req.url
        resp.status = 200

        self.scraper.req_metadata[id(req)] = asyncio.create_task(
            self.scraper.collect_req_metadata(req)
        )

        with patch.object(
            self.scraper,
            "write_resource_file",
            return_value=f"{tmp_path}/search",
        ), patch("os.path.getsize", return_value=100):
            await self.scraper.handle_response(resp)
        row = db.execute(
            """
            SELECT json(request_headers), json(request_parameters),
            json(response_headers)
            FROM files
            WHERE host = ? AND remote_path = ?
            """,
            ("example.com", "/search"),
        ).fetchone()
        assert row is not None
        request_headers = json.loads(row[0])
        request_parameters = json.loads(row[1])
        response_headers = json.loads(row[2])

        assert request_headers["cookie"] == [
            "lo=3", "skull_guardian=4",
        ]
        assert request_headers["content-type"] == [
            "application/json",
        ]
        assert request_parameters == {
            "q": ["lo", "skull_guardian"],
            "e": [""],
        }


class TestResourceHandling:
    def setup(self):
        self.scraper = PageScraper()
        self.scraper.base_dir = None
        self.scraper.origin_host = "example.com"

    def test_write_exact_bytes(self, tmp_path):
        self.setup()
        self.scraper.base_dir = str(tmp_path)
        url = "https://example.com/page.html"
        data = b"<html>Ultimate Magician of Attack and Defence</html>"
        path = self.scraper.write_resource_file(url, data)

        assert path is not None
        assert os.path.exists(path)
        with open(path, "rb") as f:
            assert f.read() == data

    def test_make_right_dirs(self, tmp_path):
        self.setup()
        self.scraper.base_dir = str(tmp_path)
        url = "https://example.com/page.html"
        data = b"<html>Ultimate Magician of Attack and Defence</html>"

        path = self.scraper.write_resource_file(url, data)
        assert path is not None
        assert os.path.isfile(path)
        assert open(path, "rb").read() == data


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
    return sqlite3.connect(test_db)

@pytest.fixture
def insert_snapshot(test_db):
    def insert(snapshot_id="snap-1", url="https://example.com", start_time=100.5, end_time=105.25):
        with sqlite3.connect(test_db) as db:
            db.execute(
                """
                INSERT INTO snapshots (id, url, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                (snapshot_id, url, start_time, end_time),
            )
    return insert

@pytest.fixture
def insert_file(test_db, insert_snapshot):
    def insert(file_id="file-1", snapshot_id="snap-1", **overrides):
        #insert_snapshot(snapshot_id=snapshot_id)

        values = {
            "id": file_id,
            "snapshot_id": snapshot_id,
            "on_disk_path": "/tmp/file-1.html",
            "file_size": 100,
            "protocol": "https",
            "port": 443,
            "host": "example.com",
            "remote_path": "/index.html",
            "request_sent_time": 100.0,
            "request_method": "GET",
            "request_headers": json.dumps({}),
            "request_parameters": json.dumps({}),
            "response_recieved_time": 101.0,
            "response_code": 200,
            "response_headers": json.dumps({
                "Content-Type": ["text/html"]
            }),
        }
        values.update(overrides)
        cols = ", ".join(values.keys())
        jsonbs = ["request_parameters", "request_headers", "response_headers"]
        placeholders = ", ".join("jsonb(?)" if col in jsonbs else "?" for col in values)

        with sqlite3.connect(test_db) as db:
            db.execute(
                f"INSERT INTO files ({cols}) VALUES ({placeholders})",
                tuple(values.values()),
            )

    return insert


class TestRelativizeResources:
    @pytest.fixture(autouse=True)
    def setup(self, test_db, insert_snapshot):
        self.snapshot_id = "snap-1"
        insert_snapshot(snapshot_id=self.snapshot_id)
        self.scraper = PageScraper()
        self.scraper.db = sqlite3.connect(test_db)
        self.scraper.snap_id = self.snapshot_id
        self.scraper.saved_resources = dict()

        yield

        self.scraper.db.close()

    def add_file(self, insert_file, file_id, url, path, content_type):
        insert_file(
            file_id=file_id,
            snapshot_id=self.snapshot_id,
            on_disk_path=str(path),
            file_size=path.stat().st_size
        )
        
        self.scraper.saved_resources[url] = {
            "path": str(path), "content_type": content_type
        }

    def get_file_size(self, file_id):
        row = self.scraper.db.execute(
            "SELECT file_size FROM files WHERE id = ?",
            (file_id,)
        ).fetchone()
        return row[0]


    def test_relativize_html(self, insert_file, tmp_path):
        url = "https://example.com/index.html"
        path = tmp_path / "index.html"
        path.write_bytes(b'<img src="https://example.com/img.png">')

        self.add_file(insert_file, "file-1", url, path, "text/html")

        with patch("src.scraping.scraper.relativize_html", 
                return_value='<img src="../img.png">') as mock_relativize:
            self.scraper.rewrite_resource_paths()
            mock_relativize.assert_called_once()
        assert path.read_text() == '<img src="../img.png">'

    def test_relativize_css(self, insert_file, tmp_path):
        url ="https://example.com/css/style.css"
        path = tmp_path / "style.css"
        path.write_bytes(b'body { background: url("image.png"); }')
        self.add_file(
            insert_file, "file-1", url, path, "text/css"
        )

        with patch("src.scraping.scraper.relativize_stylesheet",
                return_value='body { background: url("../image.png"); }') as mock_relativize:
            self.scraper.rewrite_resource_paths()
            mock_relativize.assert_called_once()

        assert path.read_text() == 'body { background: url("../image.png"); }'
    
def mock_element(url):
    element = MagicMock()
    prop = MagicMock()
    prop.json_value = AsyncMock(return_value=url)
    element.get_property = AsyncMock(return_value=prop)
    element.evaluate = AsyncMock(return_value=url)

    return element

def mock_locator(elements):
    locator = MagicMock()
    locator.count = AsyncMock(return_value=len(elements))
    locator.nth.side_effect = elements.__getitem__

    return locator

class TestHyperlinkCollection:
    

    @pytest.mark.asyncio
    async def test_gather_hyperlinks(self):
        scraper = PageScraper()
        scraper.snapshot_url = "https://www.example.com/something"
        page = MagicMock()

        elements = {
            "a[href]": [
                mock_element("https://example.com/about"),
                # Note we also test top_domain_only enforcement with this
                mock_element("https://google.com")
            ],
            "area[href]": [
                mock_element("https://example.com/contact")
            ],
            "form": [
                mock_element("https://example.com/search")
            ]
        }

        page.locator.side_effect = lambda selector: (
            mock_locator(elements[selector])
        )

        urls = await scraper.gather_hyperlinks(page)

        assert urls == {
            "https://example.com/about",
            "https://example.com/contact",
            "https://example.com/search"
        }

    @pytest.mark.asyncio
    async def test_gathering_enforce_whitelist(self):
        rules = HyperlinkRules(top_domain_only=True, whitelist_domains={"google"})
        scraper = PageScraper(
                hyperlink_rules=rules,
                snapshot_url="https://www.example.com/something"
        )

        page = MagicMock()
        
        elements = {
            "a[href]": [
                mock_element("https://example.com/about"),
                # Note we also test top_domain_only enforcement with this
                mock_element("https://google.com")
            ],
            "area[href]": [
                mock_element("https://example.com/contact")
            ],
            "form": [
                mock_element("https://example.com/search")
            ]
        }

        page.locator.side_effect = lambda selector: (
            mock_locator(elements[selector])
        )

        urls = await scraper.gather_hyperlinks(page)

        assert urls == {
            "https://example.com/about",
            "https://example.com/contact",
            "https://google.com",
            "https://example.com/search"
        } 

    @pytest.mark.asyncio
    async def test_gather_hyperlinks_enforce_blacklist(self):
        rules = HyperlinkRules(top_domain_only=False, blacklist_domains="google")
        scraper = PageScraper(
            hyperlink_rules=rules,
            snapshot_url="https://www.example.com/something"
        )

        page = MagicMock()
        elements = {
            "a[href]": [
                mock_element("https://example.com/about"),
                # Note we also test top_domain_only enforcement with this
                mock_element("https://google.com")
            ],
            "area[href]": [
                mock_element("https://example.com/contact")
            ],
            "form": [
                mock_element("https://example.com/search")
            ]
        }

        page.locator.side_effect = lambda selector: (
            mock_locator(elements[selector])
        )

        urls = await scraper.gather_hyperlinks(page)

        assert urls == {
            "https://example.com/about",
            "https://example.com/contact",
            "https://example.com/search"
        }

         
    @pytest.mark.asyncio
    async def test_gather_hyperlinks_empty(self):
        scraper = PageScraper()
        page = MagicMock()
        page.locator.side_effect = lambda selector: mock_locator([])

        urls = await scraper.gather_hyperlinks(page)
        assert urls == set()


class TestHyperlinkProcessing:

    @pytest.mark.asyncio
    async def test_process_hyperlinks(self, monkeypatch):
        scraper = PageScraper(db_conn=MagicMock())
        scraper.snap_id = "snap-1"
        scraper.snapshot_url = "https://example.com/something"
        scraper.saved_urls={"https://test_url.com"}

        urls = [
            "https://example.com/about",
            "https://example.com/contact"
        ]

        instances = []
        class MockScraper:
            def __init__(self, db_conn=None, debug=False, hyperlink_rules=HyperlinkRules(), snapshot_url=None, depth=0):
                self.db = db_conn
                self.archive_page = AsyncMock(return_value="snap-1")
                self.snapshot_url = snapshot_url
                self.depth = depth
                instances.append(self)

        monkeypatch.setattr("src.scraping.scraper.PageScraper", MockScraper)

        processed = await scraper.process_hyperlinks(urls, headers=None, method="GET")
        assert processed == set(urls)
        assert len(instances) == 2

        for instance, url in zip(instances, urls):
            instance.archive_page.assert_awaited_once_with(
                    url, None, "GET", snap_id="snap-1", saved_urls={"https://test_url.com"} #empty set bcs no responses
            )
            assert instance.depth == 1
            assert instance.snapshot_url == scraper.snapshot_url





