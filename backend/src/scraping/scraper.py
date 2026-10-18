import re
import os
import csv
import uuid
import time
import json
import os.path
import asyncio 
import hashlib
import tinycss2
import sqlite3

from datetime import datetime
from playwright.async_api import async_playwright

from urllib.parse import urlparse, unquote, urljoin, parse_qs

db_path = os.path.join(os.getenv("HOME"), ".webber", "archive.db")

class PageScraper():
    saved_urls: set[str] 
    time: str
    url: str
    origin_host: str
    origin: str
    base_dir: str
    style_sheets: set[str]
    req_metadata: dict 
    working: bool

    def __init__(self):
        self.saved_urls = set()
        self.style_sheets = set()
        self.req_metadata = dict()
        self.working = False

    async def archive_page(self, url: str):
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.req_metadata = dict()

        try:
            await self._download_page(url)
        finally:
            self.db.close()
            self.db = None



    async def handle_requests(self, request):
        parsed = urlparse(request.url)

        self.req_metadata[id(request)] = {
            "request_sent_time": time.time(),
            "request_method": request.method,
            "request_headers": await request.all_headers(),
            "request_parameters": {
                "query": parse_qs(parsed.query),
                "post_data": request.post_data,
            },
        }

    async def handle_response(self, response):
        request = response.request
        req_data = self.req_metadata.pop(id(request), None)

        if req_data is None:
            return

        url = response.url
        parsed = urlparse(url)

        if url in self.saved_urls: return

        netloc = urlparse(url).netloc
        local_path = None
        try:
            body = await response.body()
            local_path = self.write_resource_file(url, body, self.time)
            self.saved_urls.add(url)
        except Exception as e:
            print(f"Failed to save url {url}: {e}")

        # Should be logged by the above
        if local_path is None: return

        resp_data = {
            "response_recieved_time": time.time(),
            "response_code": response.status,
            "response_headers": await response.all_headers(),
        }
        default_port = 443 if parsed.scheme == "https" else 80

        values = (
                str(uuid.uuid4()),
                self.snap_id,
                local_path,
                parsed.scheme,
                parsed.port or default_port,
                parsed.hostname or "",
                parsed.path or "/",
                req_data["request_sent_time"],
                req_data["request_method"],
                json.dumps(req_data["request_headers"]).encode("utf-8"),
                json.dumps(req_data["request_parameters"]).encode("utf-8"),
                resp_data["response_recieved_time"],
                resp_data["response_code"],
                json.dumps(resp_data["response_headers"]).encode("utf-8"),

        )
        self.db.execute(
            """
            INSERT INTO files (
                id, snapshot_id, on_disk_path,
                protocol, port, host, remote_path,
                request_sent_time, request_method,
                request_headers, request_parameters,
                response_recieved, response_code,
                response_headers
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        self.db.commit()

    async def _download_page(self, url: str):
        if self.working: return
        self.saved_urls = set()
        self.snap_id = str(uuid.uuid4())
        self.working = True
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                    headless=False,
            )
            self.time = time.time()
            page = await browser.new_page()
            parsed = urlparse(url)
            self.url = url
            self.origin = parsed.netloc
            self.origin_host = parsed.hostname
            self.base_dir = self.get_base_dir(url)

            page.on("request", self.handle_requests)
            page.on("response", self.handle_response)

            await page.goto(url)
            await page.wait_for_timeout(5000)

            last_height = 0
            new_height = -1

            while last_height != new_height:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.wait_for_timeout(1000)

                new_height = await page.evaluate("document.body.scrollHeight")

                last_height = new_height
        # We've scrolled as much to bottom of the page as possible
       
            html = await page.content()
            self.write_html_file(url, html, self.time)
            end_time = time.time()
            await browser.close()
        self.db.execute(
            """
            INSERT INTO snapshots (id, url, start_time, end_time) 
            VALUES (?, ?, ?, ?)
            """,
            (
             self.snap_id,
             self.url,
             self.time,
             end_time,
            ),
        )
        self.db.commit()
        self.working = False


    def get_base_dir(self, url: str):
        stripped = re.sub(r"^https?://", "", url)
        parsed = urlparse(url)
        host = parsed.hostname
        path = os.path.join(os.path.join(os.getenv("HOME"), ".webber",
                    self.snap_id, host))
        return path


    def write_html_file(self, url, data, time):
        path = self.data_path(url, time, True)
        if path is None:
            print(f"Failed to generate a path for url: {url} - Most likely"
                    " due to bad extension or non matching domain for js "
                    " files")
            return None
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        with open(path, "w") as file:
            file.write(data)
        return path

    def write_resource_file(self, url, data, time):
        path = self.data_path(url, time, False)
        if path is None:
            print(f"Failed to generate a path for url: {url} - Most likely"
                    " due to bad extension or non matching domain for js"
                    " files")
            return None
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        with open (path, "wb") as file:
            file.write(data)

        print(f"Saved: {url} -> {path}")
        return path

    def data_path(self, url, time, html):
        stripped = re.sub(r"^https?://", "", url)
        parsed = urlparse(url)

        stripped = unquote(stripped)
        if html:
            if not stripped or stripped.endswith("/"):
                stripped += "index.html"
            elif not os.path.splitext(stripped)[1]:
                stripped += ".html"
            return os.path.join(self.base_dir, stripped)

        if not parsed.path or parsed.path.endswith("/"):
            return None

        name, extension = os.path.splitext(parsed.path)
        if not name: name = "asset"
        host = parsed.hostname

        if host != self.origin_host and (extension is None or ".js" in
                extension):
            print(f"url: {url} host: {host} og-host: {self.origin_host}")
            return None

        url_hash = hashlib.sha256(url.encode()).hexdigest()[:10]

        flatten_name = f"{name}_{url_hash}{extension.lower()}"

        return os.path.join(self.base_dir, stripped)
    

url = "https://oxylabs.io/blog/playwright-web-scraping"
s = PageScraper()
asyncio.run(s.archive_page(url))
       
