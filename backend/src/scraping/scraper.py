import re
import os
import os.path
import asyncio 
from datetime import datetime
from playwright.async_api import async_playwright



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


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
                headless=False,
        )
        page = await browser.new_page()
        url = "https://oxylabs.io/blog/playwright-web-scraping"
        await page.goto(url)
        await page.wait_for_timeout(5000)

        last_height = 0
        new_height = -1
#        page.on("response", handle_response)

        while last_height != new_height:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(5000)

            new_height = await page.evaluate("document.body.scrollHeight")

            last_height = new_height
        # We've scrolled as much to bottom of the page as possible
       
        html = await page.content()
        write_file(url, html)
        await browser.close()


def write_file(url, data):
    now = datetime.now()
    stripped = re.sub(r"^https?://", "", url)
    if ".html" not in stripped:
        stripped = f"{stripped}.html"
    path = os.path.join(os.getenv("HOME"), f".webber/{now}/", stripped)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)

    with open(path, "w") as file:
        file.write(data)


asyncio.run(main())
       
