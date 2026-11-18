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
import logging
import httpx

from tld import get_tld
from datetime import datetime
from playwright.async_api import async_playwright, Error as PlaywrightError

from urllib.parse import urlparse, urljoin, parse_qs

from ..archive_storage import archive_directory
from ..urlreplace import relativize_html, relativize_stylesheet

db_path = os.path.join(os.getenv("HOME"), ".webber", "archive.db")
logger = logging.getLogger(__name__)


RESPONSE_TIMEOUT = 20
VIDEO_EXTENSIONS = {"video/mp4": "mp4", "video/webm": "webm"}
VIDEO_RECOVERY_TIMEOUT = 10
VIDEO_RECOVERY_MAX_BYTES = 64 * 1024 * 1024
# Only forward headers relevant to fetching the same resource. Range and
# conditional request headers would prevent us from getting the complete body.
VIDEO_RECOVERY_REQUEST_HEADERS = {"accept", "authorization", "cookie", "origin", "referer", "user-agent"}
VIDEO_RANGE = re.compile(r"bytes (\d{1,19})-(\d{1,19})/(\d{1,19})", re.IGNORECASE)
EXTENSION_MAP = {
    **VIDEO_EXTENSIONS,
    "text/html":                     "html",
    "text/css":                      "css",
    "application/javascript":        "js",
    "text/javascript":               "js",
    "image/png":                     "png",
    "image/jpg":                     "jpg",
    "image/gif":                     "gif",
    "image/svg+xml":                 "svg",
    "image/webp":                    "webp",
    "image/avif":                    "avif",
    "image/x-icon":                  "ico",
    "image/vnd.microsoft.icon":      "ico",
    "font/woff":                     "woff",
    "font/woff2":                    "woff2",
    "font/ttf":                      "ttf",
    "font/otf":                      "otf",
    "application/font-woff":         "woff",
    "application/vnd.ms-fontobject": "eot",
    "application/json":              "json",
    "application/xml":               "xml",

}


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
    saved_resources: dict
    hyperlink_rules: HyperlinkRules
    snapshot_url: str
    depth: int

    def __init__(self, *, 
            db_conn=None, 
            debug=False, 
            hyperlink_rules=None,
            snapshot_url=None,
            depth=0,
        ):

        self.saved_urls = set()
        self.video_recovery_attempts: set[str] = set()
        self.saved_resources = dict()
        self.style_sheets = set()
        self.req_metadata = dict()
        self.working = False
        self.debug = debug
        self.db = db_conn
        self.hyperlink_rules = hyperlink_rules or HyperlinkRules()
        self.snapshot_url = snapshot_url
        self.depth = depth

    async def archive_page(self, url: str, headers: dict=None, method: str="GET", *,
            snap_id: str=None, saved_urls: list=None):
        """
            The function to call to start an archival job
            If snap_id is not null, it is assumed that it is already in the DB.

            A non-null snap_id also means the snapshots table will not be modified
            by this function.

            Please only supply a non-null saved_urls value if snap_id was also not null
        """
        if self.working: return None

        if self.db is None:
            self.db = sqlite3.connect(db_path)
            self.db.execute("PRAGMA foreign_keys = ON")
            self.req_metadata = dict()
        
       
        try:
            logger.info(f"Starting job for {url} with origin {snap_id}")
            snap_id = await self._download_page(url, headers, method, snap_id, saved_urls)
        finally:
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
        task = asyncio.create_task(
            asyncio.wait_for(
                self.handle_response(response), 
                timeout=RESPONSE_TIMEOUT
            ),
            name=response.url
        )

        task.add_done_callback(
            lambda t: self.on_resp_complete
        )
        self.tasks.append(task)

    def on_resp_complete(self, task):
        if not self.debug:
            return
        if task.cancelled():
            logger.info(f"Response task cancelled - {task.get_name()}")
        elif isinstance(task.exception(), asyncio.TimeoutError):
            logger.warning(f"Response task timed out - {task.get_name()}")
        else:
            logger.info("response task complete")

    @staticmethod
    async def _read_response_body(response):
        started = time.perf_counter()
        try:
            return await response.body()
        finally:
            logger.debug("Response body read for %s took %.3f s", response.url, time.perf_counter() - started)

    async def _recover_video(self, url, mime, request_headers, expected_size):
        """Try to obtain a complete video without buffering an unbounded response."""
        if expected_size is not None and not 0 < expected_size <= VIDEO_RECOVERY_MAX_BYTES:
            return None
        headers = [
            (name, value)
            for name in VIDEO_RECOVERY_REQUEST_HEADERS
            for value in request_headers.get(name, [])
        ]
        headers.append(("accept-encoding", "identity"))
        started = time.perf_counter()
        try:
            async with asyncio.timeout(VIDEO_RECOVERY_TIMEOUT):
                async with httpx.AsyncClient() as client:
                    async with client.stream("GET", url, headers=headers, follow_redirects=False) as download:
                        received_type, _, _ = download.headers.get("content-type", "").partition(";")
                        encoding = download.headers.get("content-encoding", "identity").strip().lower()
                        if (
                            download.status_code != 200
                            or "content-range" in download.headers
                            or received_type.strip().lower() != mime
                            or encoding != "identity"
                        ):
                            return None
                        declared = download.headers.get("content-length")
                        if declared is not None:
                            size = int(declared)
                            if not 0 < size <= VIDEO_RECOVERY_MAX_BYTES or (
                                expected_size is not None and size != expected_size
                            ):
                                return None
                        body = bytearray()
                        async for chunk in download.aiter_raw(chunk_size=64 * 1024):
                            if len(body) + len(chunk) > VIDEO_RECOVERY_MAX_BYTES:
                                return None
                            body.extend(chunk)
                        if not body or (expected_size is not None and len(body) != expected_size):
                            return None
                        return body, download
        except (TimeoutError, httpx.HTTPError, ValueError) as error:
            logger.debug("Full video request failed for %s: %s", url, error)
            return None
        finally:
            logger.debug("Full video recovery for %s took %.3f s", url, time.perf_counter() - started)

    async def handle_response(self, response):
        """
            Handles the response we get for a page
            Here a entry in the files table is created,
            and we download the resource from the response

            Must be linked to a request we also captured
        """

        request = response.request
        url = response.url
        parsed = urlparse(url)

        task = self.req_metadata.pop(id(request), None)
        logger.info(f"Starting task for {url}")

        if url in self.saved_urls: return

        if task is None:
            return
        try:
            req_data = await task
        except Exception as e:
            if self.debug:
                logger.warning(f"Failed to get request metadata {e}")
            return


        local_path = None
        headers = await response.all_headers()
        content_type = headers.get("content-type", "")
        res_type = self.resource_type(content_type)
        mime = content_type.split(";", 1)[0].strip().lower()
        response_status = response.status

        path = self.data_path(url, resource_type=res_type)
        if path is None:
            logger.warning(f"Failed to generate a path for url: {url} - Most likely"
                    " due to bad extension or non matching domain for js"
                    " files")
            return


        try:
            body = None
            recovered = None
            if mime in VIDEO_EXTENSIONS and response_status == 206:
                match = VIDEO_RANGE.fullmatch(headers.get("content-range", "").strip())
                expected_size = None
                if match:
                    start, end, expected_size = map(int, match.groups())
                    if start == 0 and end + 1 == expected_size:
                        complete_range = await self._read_response_body(response)
                        if len(complete_range) == expected_size:
                            body = complete_range
                if body is None:
                    if url in self.saved_urls or url in self.video_recovery_attempts:
                        return
                    self.video_recovery_attempts.add(url)
                    sent_time = time.time()
                    recovered = await self._recover_video(
                        url, mime, req_data["request_headers"], expected_size
                    )
                    if recovered is None:
                        if url not in self.saved_urls:
                            logger.warning("Could not save the complete video: %s", url)
                        return
                    body, download = recovered
                    retry_headers = {}
                    for name, value in download.request.headers.multi_items():
                        retry_headers.setdefault(name, []).append(value)
                    req_data["request_sent_time"] = sent_time
                    req_data["request_method"] = "GET"
                    req_data["request_headers"] = retry_headers
                    response_status = download.status_code
                    content_type = download.headers["content-type"]
            else:
                body = await self._read_response_body(response)

            # Other range tasks can finish while the recovery GET is running.
            if mime in VIDEO_EXTENSIONS and url in self.saved_urls:
                return
            local_path = self.write_resource_file(url, body, res_type)
        except Exception as e:
            logger.info(f"Failed to save url {url}: {e}")

        # Should be logged by the above
        if local_path is None: return

        self.saved_urls.add(url)

        # keep track of this so that we dont need to dig into the DB later when we need to relativize everything
        self.saved_resources[url] = {"path": local_path, "content_type": content_type}

        headers = {}
        response_headers = (
            download.headers.multi_items() if recovered is not None else
            [(header["name"].lower(), header["value"]) for header in await response.headers_array()]
        )
        for name, value in response_headers:
            headers.setdefault(name, []).append(value)

        resp_data = {
            "response_recieved_time": time.time(),
            "response_code": response_status,
            "response_headers": headers,
        }
        default_port = 443 if parsed.scheme == "https" else 80

        file_size:int = 0
        try:
            file_size = os.path.getsize(local_path)
        except Exception as e:
            logger.warning(f"Failed to save url {url}: {e} at file byte size gathering")
            return 
    

        values = (
                str(uuid.uuid4()),
                self.snap_id,
                local_path,
                file_size,
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
                id, snapshot_id, on_disk_path, file_size,
                protocol, port, host, remote_path,
                request_sent_time, request_method,
                request_headers, request_parameters,
                response_recieved_time, response_code,
                response_headers
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, jsonb(?), jsonb(?), ?, ?, jsonb(?))
            """,
            values,
        )

    async def _download_page(self, url: str, headers: dict=None, method:str="GET", snap_id: str=None, saved_urls: set=None):
        if self.working: return None
        self.working = True
        self.tasks = []
        self.saved_urls = set()
        if saved_urls is not None:
            self.saved_urls.update(saved_urls)

        self.saved_resources = dict()

        self.time = time.time()
        update_db = snap_id is None
        if update_db:
            self.video_recovery_attempts.clear()
            self.snap_id = str(uuid.uuid4())
            self.snapshot_url = url
            self.db.execute(
                """
                INSERT INTO snapshots (id, url, start_time, end_time)
                VALUES (?, ?, ?, ?)
                """,
                (self.snap_id, url, self.time, self.time)
            )
        else: self.snap_id = snap_id

        self.set_origin_url(url)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                    headless=True,
            )
            browser = await browser.new_context(accept_downloads=False)
            page = await browser.new_page()
            
            if headers is not None:
                await page.setExtraHTTPHeaders(headers)

            page.on("request", self.handle_requests)
            page.on("response", self.on_response)

            # Maybe we want to handle this in the future?
            # For now it seems a security risk, so skipping
            #page.on("download", lambda download: asyncio.create_task(download.cancel()))
            try:
                await page.goto(url, wait_until="load")
            except PlaywrightError as e:
                if "Download is starting" in str(e):
                    logger.info(f"Request on {url} triggered a download: Skipping")
                    await browser.close()
                    return
                raise

            last_height = 0
            new_height = -1

            logger.info(f"Starting scroll for {url}")
            scroll_start = time.time()

            await self.scroll_page(page)
            scroll_end = time.time()
            logger.info(f"Ended scroll for {url} after {scroll_end - scroll_start}")

           # We've scrolled as much to bottom of the page as possible
       

            # Added because we started skipping urls 
            # since browser closed early
            drain_start = time.time()
            logger.info(f"Started drain for {url}")
            await self._drain_tasks()
            drain_end = time.time()
            logger.info(f"Finished drain for {url} after {drain_end - drain_start}")

            # Rewrite files where needed
            self.rewrite_resource_paths()

            if self.depth < self.hyperlink_rules.max_depth:
                hyperlinks = await self.gather_hyperlinks(page)

                processed = await self.process_hyperlinks(hyperlinks, headers, method)

            end_time = time.time()
            await browser.close()
            logger.info(f"finished at {end_time} after {end_time - self.time} for {url}")
        
        if update_db:
            # conditional update because if snapshot exists, we probably have a parent process running that 
            # returns the true end time. Avoid over-updating.
            self.db.execute(
                """
                UPDATE snapshots SET end_time = ? WHERE id = ?
                """,
                (end_time, self.snap_id),
            )

        # unconditional commit since we still write files
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
            logger.debug("Awaiting task completion")
            results = await asyncio.gather(
                *undone,
                return_exceptions=True,
            )
            logger.debug("Finished waiting")

            completed += len(undone)
            
            for res in results:
                if isinstance(res, BaseException):
                    logger.warning(f"Task Failed: {res!r}")

    async def scroll_page(self, page, max_scrolls=200):
        last_height = 0
        for _ in range(max_scrolls):
            try:
                await page.evaluate(
                    "window.scrollBy(0, window.innerHeight)"
                )

                new_height = await page.evaluate(
                        "document.documentElement.scrollHeight"
                )
            except PlaywrightError as e:
                if "Execution context was destroyed" in str(e):
                    logger.warning("Navigation during scrolling-quitting")
                    break
                raise
            if new_height == last_height:
                break
            last_height = new_height

    async def process_hyperlinks(self, urls: list, headers: dict=None, method: str="GET") -> set[str]:
        """
        Takes a list of urls (presumably from PageScraper#gather_hyperlinks) and downloads the pages, 
        Recursively PageScraping)

        urls    - the list of urls to start scraping processes for
        headers - the headers we want to make the request with, Generally should follow what the root call to
                  archive_page was.
        method  - the HTTP method to make the request with. Currently only GET is supported explicitly

        Returns a set of the urls that were successively scraped. Urls scraped here have the contents stored
        in the same snapshot directory as the original archive_page caller.
        """
        processed = set()
        for url in urls:
            scraper = PageScraper(
                    db_conn=self.db, 
                    debug=self.debug, 
                    hyperlink_rules=self.hyperlink_rules,
                    snapshot_url=self.snapshot_url,
                    depth=self.depth+1,
            )

            # I'm not a huge fan of doing the below.
            # However, I felt like my constructors and parameters were getting too long

            scraper.video_recovery_attempts = self.video_recovery_attempts
            res = await scraper.archive_page(url, headers, method, snap_id=self.snap_id, saved_urls=self.saved_urls)
            if res is None: 
                logger.warning(f"Skipping url: {url}. Failed to download page content") 
                continue
            processed.add(url)
        return processed


    async def gather_hyperlinks(self, page) -> set[str]:
        search_targets = [("a[href]", "href"), ("area[href]", "href"), ("form", "action")]
        urls = set()

        logger.debug("Processing hyperlinks")

        for selector, attr in search_targets:
            elements = page.locator(selector)
            elem_count = await elements.count()
            for i in range(elem_count):
                element = elements.nth(i)
                url = await element.evaluate("(el, attr) => el[attr]", attr)
                if not url or url in self.saved_urls:
                    continue
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https"):
                    continue

                if not self._apply_hyperlink_rules(url):
                    continue

                logger.debug(f"Found url to look at: {url}")
                urls.add(url)

        return urls

    def _apply_hyperlink_rules(self, url: str) -> bool:
        rules = self.hyperlink_rules
        top_domain = get_tld(self.snapshot_url, as_object=True).domain
        curr_domain = get_tld(url, as_object=True).domain
        if rules.top_domain_only:
            logger.debug(f"{url} : {top_domain} : {curr_domain} : {top_domain == curr_domain}")
            return top_domain == curr_domain or curr_domain in rules.whitelist_domains
        else:
            return curr_domain not in rules.blacklist_domains


        


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
        if self.snap_id is None:
            logger.warning(f"Encountered anomoly on get_base_dir: snap_id is None! {url}")
            return None
        elif host is None:
            logger.warning(f"Encountered anomoly on get_base_dir: snap_id is None! {url}")
            return None
        archive_dir = archive_directory.get() or os.path.join(os.getenv("HOME"), ".webber")
        path = os.path.join(archive_dir, self.snap_id, host)
        return path


    def resource_type(self, content_type: str) -> str | None:
        """
        Converts a http content-type to its assosciated resource type extension
        """
        content = content_type.split(";", 1)[0].strip().lower()
        return EXTENSION_MAP.get(content, None)

    def rewrite_resource_paths(self):
        for url, resource in self.saved_resources.items():
            path = resource["path"]
            content_type = resource.get("content_type", "").split(";", 1)[0].strip().lower()
            html_flag = None
            if content_type == "text/html":
                html_flag = True
            if content_type == "text/css":
                html_flag = False
            if html_flag is None: 
                continue
            with open(path, "rb") as file:
                contents = file.read()
            try:
                if html_flag:
                    # Should I account for not utf-8?
                    contents = relativize_html(contents.decode("utf-8", errors="replace"), url)
                else:
                    contents = relativize_stylesheet(contents, url)
            except Exception as e:
                logger.warning("Encountered error {e} relatvizing {url}")
                continue
            with open(path, "w", encoding="utf-8") as file:
                file.write(contents)
            self.db.execute(
                """
                UPDATE files
                SET file_size = ?
                WHERE snapshot_id = ? AND on_disk_path = ?
                """,
                (os.path.getsize(path), self.snap_id, path)
            )
        

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
            logger.warning(f"Failed to generate a path for url: {url} - Most likely"
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

        if resource_type in VIDEO_EXTENSIONS.values():
            suffix = f".{resource_type}"
            if os.path.splitext(path)[1].lower() != suffix:
                # Keep inferred names separate from URL-derived paths. Two
                # distinct resources, such as /video and /video.mp4, may coexist.
                key = hashlib.sha256(url.encode("utf-8")).hexdigest()
                return os.path.join(self.base_dir, "videos", key + suffix)

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
            logger.debug(f"url: {url} host: {host} og-host: {self.origin_host}")
            return None
        return os.path.join(self.base_dir, parsed.scheme.lower(), host, path)

    def set_origin_url(self, url: str):
        parsed = urlparse(url)
        self.url = url
        self.origin = parsed.netloc
        self.origin_host = parsed.hostname
        self.base_dir = self.get_base_dir(url)



class HyperlinkRules:
    """
    Please note in all contexts, domains refer to the TLD
    That is: bbc.co.uk, we mean bbc as the domain
    """
    max_depth: int
    # Used to work around top_domain_only
    # Only does something if top_domain_only is True
    whitelist_domains: set[str]

    # Does not do anything if top_domain_only is True
    blacklist_domains: set[str]

    top_domain_only: bool

    def __init__(self, *, max_depth: int=1, whitelist_domains=set(), blacklist_domains=set(), top_domain_only=True):
        self._max_depth = max_depth
        self._whitelist_domains = whitelist_domains
        self._blacklist_domains = blacklist_domains
        self._top_domain_only = top_domain_only
    
    @property
    def max_depth(self) -> int: 
        return self._max_depth

    @property
    def whitelist_domains(self) -> set[str]:
        return self._whitelist_domains

    @property
    def blacklist_domains(self) -> set[str]:
        return self._blacklist_domains

    @property
    def top_domain_only(self) -> bool:
        return self._top_domain_only





    
if __name__ == "__main__":
    with open("./db/001_init.sql") as f:
        sql_script = f.read()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.executescript(sql_script)
    conn.commit()
    print("Created db")
    url = "https://oxylabs.io/blog/playwright-web-scraping"
    s = PageScraper(db_conn=conn, debug=True)
    asyncio.run(s.archive_page(url))
    print("Finished all jobs!")

