"""Offline HTTP-response demo for task 2.3.1 (never saves a webpage)."""
import asyncio
import sys
from urllib.parse import urlsplit

import httpx
from PySide6.QtWidgets import QApplication

from .archive_request import ArchiveRequestDialog


async def simulated_create(url):
    async def respond(request):
        await asyncio.sleep(0.5)
        if url == "timeout":
            raise httpx.ReadTimeout("Demo timeout", request=request)
        if url == "offline":
            raise httpx.ConnectError("Demo connection failure", request=request)
        if url == "server-error":
            return httpx.Response(500, json={"message": "The archive service could not save the webpage."})
        parsed = urlsplit(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return httpx.Response(400, json={"message": "Invalid URL. Include http:// or https:// and a hostname."})
        return httpx.Response(201, json={"id": "demo-snapshot-001"})
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        response = await client.post("https://demo-backend.test/snapshots/create", json={"url": url})
        response.raise_for_status()
        return response.json()


def main():
    app = QApplication(sys.argv)
    dialog = ArchiveRequestDialog(simulated_create, demo=True)
    dialog.url_input.setPlaceholderText("Try ucsc.edu, https://www.ucsc.edu/, timeout, offline, server-error")
    dialog.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
