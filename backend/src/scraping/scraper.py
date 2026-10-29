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

from urllib.parse import urlparse, urljoin, parse_qs

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
    debug: bool

    def __init__(self, debug=False):
        self.saved_urls = set()
        self.style_sheets = set()
        self.req_metadata = dict()
        self.working = False
        self.debug = debug

    async def archive_page(self, url: str, headers: dict=None, method: str="GET"):
        self.db = sqlite3.connect(db_path)

        self.db.execute("PRAGMA foreign_keys = ON")
        self.req_metadata = dict()

        try:
            snap_id = await self._download_page(url, headers, method)
        finally:
            self.db.close()
            self.db = None
            self.working = False
        return snap_id


    async def collect_req_metadata(self, request):
        parsed = urlparse(request.url)

        headers = dict()
        for header in await request.headers_array():
            name = header["name"].lower()
            value = header["value"]
            headers.setdefault(name, []).append(value)
        return {
            "request_sent_time": time.time(),
            "request_method": request.method,
            "request_headers": headers,
            "request_parameters": 
                parse_qs(parsed.query, keep_blank_values=True),
        }



    def handle_requests(self, request):
        parsed = urlparse(request.url)

        self.req_metadata[id(request)] = asyncio.create_task(
                self.collect_req_metadata(request)
        )

    def on_response(self, response):
        task = asyncio.create_task(self.handle_response(response))
        self.tasks.append(task)

    async def handle_response(self, response):
        """
            Handles the response we get for a page
            Here a entry in the files table is created,
            and we download the resource from the response

            Must be linked to a request we also captured
        """

        request = response.request
        task = self.req_metadata.pop(id(request), None)

        if task is None:
            if self.debug:
                print("No task, Skipping")
            return
        try:
            req_data = await task
        except Exception as e:
            if self.debug:
                print(f"Failed to get req metadata {e}")
            return
        url = response.url
        parsed = urlparse(url)

        if url in self.saved_urls: return

        local_path = None
        headers = await response.all_headers()
        content_type = headers.get("content-type", "")
        res_type = self.resource_type(content_type)
        try:
            body = await response.body()
            local_path = self.write_resource_file(url, body, res_type)
        except Exception as e:
            if self.debug:
                print(f"Failed to save url {url}: {e}")

        # Should be logged by the above
        if local_path is None: return
        self.saved_urls.add(url)
        headers = dict()
        for header in await response.headers_array():
            name = header["name"].lower()
            value = header["value"]
            headers.setdefault(name, []).append(value)

        resp_data = {
            "response_recieved_time": time.time(),
            "response_code": response.status,
            "response_headers": headers,
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
                json.dumps(req_data["request_headers"]),
                json.dumps(req_data["request_parameters"]),
                resp_data["response_recieved_time"],
                resp_data["response_code"],
                json.dumps(resp_data["response_headers"]),

        )
        self.db.execute(
            """
            INSERT INTO files (
                id, snapshot_id, on_disk_path,
                protocol, port, host, remote_path,
                request_sent_time, request_method,
                request_headers, request_parameters,
                response_recieved_time, response_code,
                response_headers
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, jsonb(?), jsonb(?), ?, ?, jsonb(?))
            """,
            values,
        )

    async def _download_page(self, url: str, headers: dict=None, method:str="GET"):
        if self.working: return None
        self.tasks = []
        self.saved_urls = set()
        self.snap_id = str(uuid.uuid4())
        self.working = True
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                    headless=True,
            )
            self.time = time.time()
            page = await browser.new_page()
            
            parsed = urlparse(url)
            self.url = url


            if headers is not None:
                await page.setExtraHTTPHeaders(headers)

            self.origin = parsed.netloc
            self.origin_host = parsed.hostname
            self.base_dir = self.get_base_dir(url)

            self.db.execute(
                """
                INSERT INTO snapshots (id, url, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                (self.snap_id, url, self.time, self.time),
            )

            page.on("request", self.handle_requests)
            page.on("response", self.on_response)

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
       

            # Added because we started skipping urls 
            # since browser closed early
            await self._drain_tasks()

            end_time = time.time()
            await browser.close()
        self.db.execute(
            """
            UPDATE snapshots SET end_time = ? WHERE id = ?
            """,
            (end_time, self.snap_id),
        )
        self.db.commit()
        self.working = False
        return self.snap_id


    async def _drain_tasks(self):
        """
            Drains the outstanding response tasks. By proxy, this should
            also handle the outstanding request tasks.
        """
        if not self.tasks: return
        completed = 0
        while completed < len(self.tasks):
            undone = self.tasks[completed:]
            results = await asyncio.gather(
                *undone,
                return_exceptions=True,
            )

            completed += len(undone)
            
            for res in results:
                if isinstance(res, BaseException):
                    if self.debug:
                        print(f"Task Failed: {res!r}")


    def get_base_dir(self, url: str):
        """
            Gets the base directory where we need to store files in
            
            url str - The domain defines the sub directory grouping we'll
            put the files in. 
            ie. domain is lego.com ->.webber/<snapshot>/<lego.com>/
        """
        stripped = re.sub(r"^https?://", "", url)
        parsed = urlparse(url)
        host = parsed.hostname
        path = os.path.join(os.path.join(os.getenv("HOME"), ".webber",
                    self.snap_id, host))
        return path


    def resource_type(self, content_type: str) -> str | None:
        content = content_type.split(";", 1)[0].strip().lower()
        match content:
            case "text/html": return "html"
            case "text/css": return "css"
            case "application/javascript": return "js"
            case "text/javascript": return "js"
            case "image/png": return "png"
            case "image/jpeg": return "jpg"
            case "image/gif": return "gif"
            case "image/svg+xml": return "svg"
            case "image/webp": return "webp"
            case "image/avif": return "avif"
            case "image/x-icon": return "ico"
            case "image/vnd.microsoft.icon": return "ico"
            case "font/woff": return "woff"
            case "font/woff2": return "woff2"
            case "font/ttf": return "ttf",
            case "font/otf": return "otf"
            case "application/font-woff": return "woff"
            case "application/vnd.ms-fontobject": return "eot"
            case _: return None
        # Redundant
        return None

    def write_resource_file(self, url, data, resource_type: str =None):
        """
            Writes the resource from  specified url to the disc with the
            provided data

            Will not write resource if it is a file with no extension from
            outside of the primary domain (usually junk data) or if it is a
            js file from such a place. 

            .webber/<snapshot-id>/<og-domain-for-archival>/<url path>

            url str - The url the file path will be based on
            data    - What we're writing

        """
        path = self.data_path(url, resource_type=resource_type)
        if path is None:
            if self.debug:
                print(f"Failed to generate a path for url: {url} - Most likely"
                    " due to bad extension or non matching domain for js"
                    " files")
            return None
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        with open (path, "wb") as file:
            file.write(data)

        return path

    def data_path(self, url, resource_type: str = None):
        parsed = urlparse(url)
        path = parsed.path.lstrip("/")

        if not resource_type and not path or parsed.path.endswith("/"):
            path = os.path.join(path, "index.html")
        elif not os.path.splitext(path)[1] and resource_type:
            path += f".{resource_type}"
        name, extension = os.path.splitext(path)

        if parsed.query:
            query_hash = hashlib.sha256(
                parsed.query.encode("utf-8")
            ).hexdigest()[:10]
            path = f"{name}_{query_hash}{extension}"

        host = parsed.hostname 
        if host != self.origin_host and (
            not extension or extension == ".js"
        ):
            if self.debug:
                print(f"url: {url} host: {host} og-host: {self.origin_host}")
            return None
        return os.path.join(self.base_dir, parsed.scheme.lower(), host, path)
    

# Use to run a manual test
#with open("./../../db/001_init.sql") as f:
#    sql_script = f.read()
#
#with sqlite3.connect(db_path) as conn:
#    cursor = conn.cursor()
#    cursor.executescript(sql_script)
#    conn.commit()
#    print("Created db")
#url = "https://oxylabs.io/blog/playwright-web-scraping"
#s = PageScraper()
#asyncio.run(s.archive_page(url))
       
