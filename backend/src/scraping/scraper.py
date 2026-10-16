import re
import os
import os.path
import asyncio 
from datetime import datetime
from playwright.async_api import async_playwright

from urllib.parse import urlparse, unquote



#def handle_response(response):
#    request = response.request
#
#    resource_type = request.resource_type
#    if resource_type != "stylesheet":    
#        print(resource_type)
#        return
#    print(2)
#
#    body = response.body
#    print (body)

class PageScraper():
    saved_urls: set[str]
    time: str
    origin: str

    
    def local_path(self, url: str, out_path: str) -> str:
        parsed = urlparse(url)

        if parsed.scheme not in ("http", "https"):
            return None
        path = unquote(parsed.path).lstrip("/") or "index.html" 
        file_path = os.path.join(out_path, path)

        if parsed.query:
            suffix = hashlib.sha256( parsed.query.encode()
                    ).hexdigest()[:10]
        name, extension = os.path.splitext(file_path)
        file_path = f"{name}_{suffix}{extension}"
        return file_path


    async def handle_response(self, response):
        url = response.url

        if url in self.saved_urls: return
        if response.status >= 400: return

        netloc = urlparse(url).netloc
        if self.origin != netloc: 
            print(f"Skipping download of {url} since its netloc ({netloc})")
            return

        try:
            body = await response.body()
            self.write_resource_file(url, body, self.time)
            self.saved_urls.add(url)
        except Exception as e:
            print(f"Failed to save url {url}: {e}")

    async def main(self):
        self.saved_urls = set()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                    headless=False,
            )
            self.time = datetime.now()
            page = await browser.new_page()
            url = "https://oxylabs.io/blog/playwright-web-scraping"
            self.origin = urlparse(url).netloc
            page.on("response", self.handle_response)
            await page.goto(url)
            await page.wait_for_timeout(5000)
            sheets = await page.locator('link[rel="stylesheet"]').all()
            for sheet in sheets:
                print("Stylesheet:", await sheet.get_attribute("href"))

            last_height = 0
            new_height = -1

            while last_height != new_height:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                await page.wait_for_timeout(5000)

                new_height = await page.evaluate("document.body.scrollHeight")

                last_height = new_height
        # We've scrolled as much to bottom of the page as possible
       
            html = await page.content()
            self.write_html_file(url, html, self.time)
            await browser.close()

    def base_dir(self, url: str, add_html: bool):
        now = datetime.now()
        stripped = re.sub(r"^https?://", "", url)
        if add_html and ".html" not in stripped:
            stripped = f"{stripped}.html"
        path = os.path.join(os.path.join(os.getenv("HOME"), f".webber/{now}"))
        return path

    def write_html_file(self, url, data, time):
        path = self.data_path(url, time)
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        with open(path, "w") as file:
            file.write(data)

    def write_resource_file(self, url, data, time):
        path = self.data_path(url, time)
        directory = os.path.dirname(path)
        os.makedirs(directory, exist_ok=True)
        with open (path, "wb") as file:
            file.write(data)

        print(f"Saved: {url} -> {path}")

    def data_path(self, url, time):
        stripped = re.sub(r"^https?://", "", url)
        parsed = urlparse(stripped)

        stripped = unquote(parsed.path)

        if not stripped or stripped.endswith("/"):
            stripped += "index.html"
        elif not os.path.splitext(stripped)[1]:
            stripped += ".html"

        if parsed.query:
            suffix = hashlib.sha256(
                    parsed.query.encode()
            ).hexdigest()[:10]
            name, extension = os.path.splitext(path)
            path = f"{name}_{suffix}{extension}"

        return os.path.join( os.getenv("HOME"), ".webber", str(time),
                parsed.netloc, stripped)
s = PageScraper()
asyncio.run(s.main())
       
