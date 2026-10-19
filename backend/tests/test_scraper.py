from src.scraping.scraper import (
    PageScraper,
)

from unittest.mock import AsyncMock, MagicMock, patch


import pytest
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
            "https://exaple.com/card?q=dark_magician"
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
            {"name": "Content-Type", "value": "applications/json"},
            {"name": "Cookie", "value": "kuriboh=3"},
            {"name": "Cookie", "value": "dark_magician=5"},
        ]

    async def headers_array(self):
        return self.array

class FakeResponse:
    def __init__(self, request, url=None, body="b<html>The ultimate engine of destruction: Blue Eyes White Dragon</html>"):
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
            "content-type": ["applications/json"],
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


class TestHandleResponse:
    def setup(self):
        self.scraper = PageScraper()
        self.scraper.snap_id = "test-snapshot"
        self.origin_host = "example.com"
        self.scraper.base_dir = "/tmp/test-snapshot/example.com"
        self.scraper.saved_urls = set()
        self.scraper.req_metadata = {}
        self.scraper.db = MagicMock()

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
            raise RunTimeError("meta fail")

        self.scraper.req_metadata[id(req)] = asyncio.create_task(fail())

        await self.scraper.handle_response(resp)
        self.scraper.db.execute.assert_not_called()
        assert resp.url not in self.scraper.saved_urls

