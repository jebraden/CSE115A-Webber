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

from tld import get_tld
from datetime import datetime
from playwright.async_api import async_playwright
from playwright.async_api import Error as PlaywrightError

from urllib.parse import urlparse, urljoin, parse_qs

from src.urlreplace import relativize_html, relativize_stylesheet 

db_path = os.path.join(os.getenv("HOME"), ".webber", "archive.db")
logger = logging.getLogger(__name__)


RESPONSE_TIMEOUT = 20

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

    def __init__(self, *, db_conn=None, debug=False, hyperlink_rules=None):
        self.saved_urls = set()
        self.saved_resources = dict()
        self.style_sheets = set()
        self.req_metadata = dict()
        self.working = False
        self.debug = debug
        self.db = db_conn
        self.hyperlink_rules = hyperlink_rules or HyperlinkRules()
        self.depth = 0

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
            if self.debug:
                print(f"Starting job for {url} with origin {snap_id}")
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
            print(f"Response task cancelled - {task.get_name()}")
        elif isinstance(task.exception(), asyncio.TimeoutError):
            print(f"Response task timed out - {task.get_name()}")
        else:
            print("response task complete")

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
        print(f"Starting task for {url}")

        if url in self.saved_urls: return

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


        local_path = None
        headers = await response.all_headers()
        content_type = headers.get("content-type", "")
        res_type = self.resource_type(content_type)

        path = self.data_path(url, resource_type=res_type)
        if path is None:
            if self.debug:
                print(f"Failed to generate a path for url: {url} - Most likely"
                    " due to bad extension or non matching domain for js"
                    " files")
            return


        try:
            if self.debug:
                print(f"Starting response awaiting at {time.time()}")
            body = await response.body()
            if self.debug:
                print(f"Finished response awaiting at {time.time()}")

            local_path = self.write_resource_file(url, body, res_type)
        except Exception as e:
            if self.debug:
                print(f"Failed to save url {url}: {e}")

        # Should be logged by the above
        if local_path is None: return

        self.saved_urls.add(url)

        # keep track of this so that we dont need to dig into the DB later when we need to relativize everything
        self.saved_resources[url] = {"path": local_path, "content_type": content_type}

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

        file_size:int = 0
        try:
            file_size = os.path.getsize(local_path)
        except Exception as e:
            if self.debug:
                print(f"Failed to save url {url}: {e} at file byte size gathering")
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
        self.depth = 0
        if saved_urls is not None:
            self.saved_urls.update(saved_urls)

        self.saved_resources = dict()

        self.time = time.time()
        update_db = snap_id is None
        if update_db:
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
            page = await browser.new_page()
            
            if headers is not None:
                await page.setExtraHTTPHeaders(headers)

            page.on("request", self.handle_requests)
            page.on("response", self.on_response)

            # Maybe we want to handle this in the future?
            # For now it seems a security risk, so skipping
            page.on("download", lambda download: asyncio.create_task(download.cancel()))
            try:
                await page.goto(url, wait_until="load")
            except PlaywrightError as e:
                if "Download is starting" in str(e):
                    logger.info(f"Request on {url} triggered a download: Skipping")
                    await browser.close()
                    return
                raise
#await page.wait_for_timeout(250)

            last_height = 0
            new_height = -1

            if self.debug:
                print(f"Starting scrol for {url}")
            scroll_start = time.time()
# while last_height != new_height:
#                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
#                await page.wait_for_timeout(1000)
#
#                new_height = await page.evaluate("document.body.scrollHeight")
#
#                last_height = new_height
            await self.scroll_page(page)
            scroll_end = time.time()
            if self.debug:
                print(f"Ended scroll for {url} after {scroll_end - scroll_start}")

           # We've scrolled as much to bottom of the page as possible
       

            # Added because we started skipping urls 
            # since browser closed early
            print(f"Started drain for {url}")
            await self._drain_tasks()
            print(f"Finished drain for {url}")

            # Rewrite files where needed
            self.rewrite_resource_paths()

            if self.depth < self.hyperlink_rules.get_max_depth():
                hyperlinks = await self.gather_hyperlinks(page)

                processed = await self.process_hyperlinks(hyperlinks, headers, method)

            end_time = time.time()
            await browser.close()
            if self.debug:
                print(f"finished at {end_time} after {end_time - self.time} for {url}")
        
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
            if self.debug:
                print(f"Drained: {completed}")
            undone = self.tasks[completed:]
            if self.debug:
                print("Awaiting task completion")
            results = await asyncio.gather(
                *undone,
                return_exceptions=True,
            )
            if self.debug:
                print("Finished waiting")

            completed += len(undone)
            
            for res in results:
                if isinstance(res, BaseException):
                    if self.debug:
                        print(f"Task Failed: {res!r}")

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
                    if self.debug:
                        print("Navigation during scrolling-quitting")
                    break
                raise
            if new_height == last_height:
                break
            last_height = new_height

    async def process_hyperlinks(self, urls: list, headers: dict=None, method: str="GET") -> list[str]:
        """
        Takes a list of urls (presumably from PageScraper#gather_hyperlinks) and downloads the pages, 
        Recursively PageScraping)

        urls    - the list of urls to start scraping processes for
        headers - the headers we want to make the request with, Generally should follow what the root call to
                  archive_page was.
        method  - the HTTP method to make the request with. Currently only GET is supported explicitly

        Returns a list of the urls that were successively scraped. Urls scraped here have the contents stored
        in the same snapshot directory as the original archive_page caller.
        """
        processed = set()
        for url in urls:
            scraper = PageScraper(db_conn=self.db, debug=self.debug, hyperlink_rules=self.hyperlink_rules)
            # I'm not a huge fan of doing the below.
            # However, I felt like my constructors and parameters were getting too long
            scraper.snapshot_url = self.snapshot_url
            scraper.depth = self.depth + 1

            res = await scraper.archive_page(url, headers, method, self.snap_id, self.saved_urls)
            if res is None: 
                logger.warning("Skipping url: {url}. Failed to download page content") 
                continue
            processed.add(url)
        return processed


    async def gather_hyperlinks(self, page) -> list[str]:
        search_targets = [("a[href]", "href"), ("area[href]", "href"), ("form", "action")]
        urls = set()

        if self.debug:
            print("Processing hyperlinks")

        for selector, attr in search_targets:
            elements = page.locator(selector)
            elem_count = await elements.count()
            for i in range(elem_count):
                element = elements.nth(i)
#url = await ( await element.get_property(attr)).json_value()
                url = await element.evaluate("(el, attr) => el[attr]", attr)
                if not url or url in self.saved_urls:
                    continue
                parsed = urlparse(url)
                if parsed.scheme not in ("http", "https"):
                    continue

                if not self._apply_hyperlink_rules(url):
                    continue

                if self.debug:
                    print(f"Found url to look at: {url}")
                urls.add(url)

        return urls

    def _apply_hyperlink_rules(self, url: str) -> bool:
        rules = self.hyperlink_rules
        top_domain = get_tld(self.snapshot_url, as_object=True).domain
        curr_domain = get_tld(url, as_object=True).domain
        if rules.is_top_domain_only():
            print(f"{url} : {top_domain} : {curr_domain} : {top_domain == curr_domain}")
            return top_domain == curr_domain or curr_domain in rules.get_whitelist_domains()
        else:
            return curr_domain not in rules.get_blacklist_domains()


        


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
            case "font/ttf": return "ttf"
            case "font/otf": return "otf"
            case "application/font-woff": return "woff"
            case "application/vnd.ms-fontobject": return "eot"
            case "application/json": return "json"
            case "application/xml": return "xml"
            case _: return None
        # Redundant
        return None

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
    whitelist_domains: set

    # Does not do anything if top_domain_only is True
    blacklist_domains: set

    top_domain_only: bool

    def __init__(self, *, max_depth: int=1, whitelist_domains=set(), blacklist_domains=set(), top_domain_only=True):
        self.max_depth = max_depth
        self.whitelist_domains = whitelist_domains
        self.blacklist_domains = blacklist_domains
        self.top_domain_only = top_domain_only

    def get_max_depth(self) -> int: 
        return self.max_depth

    def get_whitelist_domains(self) -> set:
        return self.whitelist_domains

    def get_blacklist_domains(self) -> set:
        return self.blacklist_domains

    def is_top_domain_only(self) -> bool:
        return self.top_domain_only





    

# Use to run a manual test
#with open("./db/001_init.sql") as f:
#    sql_script = f.read()
#conn = sqlite3.connect(db_path)
#cursor = conn.cursor()
#cursor.executescript(sql_script)
#conn.commit()
#print("Created db")
#url = "https://oxylabs.io/blog/playwright-web-scraping"
#s = PageScraper(db_conn=conn, debug=True)
#asyncio.run(s.archive_page(url))
#print("Finished all jobs!")


       
