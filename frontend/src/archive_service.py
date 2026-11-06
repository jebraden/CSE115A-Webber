"""Adapt the shared API to the UI contract without opening the database."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
from urllib.parse import urlsplit

from .api import WebberAPI, NotFoundError
from .archive_document import ArchiveDocument
from .archive_list.service import Snapshot
from .archive_request.errors import InvalidArchiveResponse


class ArchiveService:
    def __init__(self, api: WebberAPI, *, wait_ready=None):
        self.api = api
        self.wait_ready = wait_ready

    async def _ready(self):
        if self.wait_ready is not None:
            await self.wait_ready()

    async def search_snapshots(self, query):
        await self._ready()
        # The UI promises literal, case-insensitive substrings. The backend
        # accepts a regex; escape user input before crossing that boundary.
        pattern = "(?i)" + re.escape(query.strip())
        ids = (await self.api.query_snapshots("url", pattern)).snapshot_ids
        semaphore = asyncio.Semaphore(8)

        async def fetch(snapshot_id):
            async with semaphore:
                try:
                    value = await self.api.get_snapshot(snapshot_id)
                except NotFoundError:
                    return None  # Another request may have deleted it.
            timestamp = value.end_time or value.start_time
            if timestamp is None:
                raise InvalidArchiveResponse()
            date = datetime.fromtimestamp(timestamp.sec + timestamp.nsec / 1e9, timezone.utc)
            host = urlsplit(value.url).hostname or ""
            assets = Path(__file__).parent / "archive_list" / "assets"
            icon = (assets / "ucsc.ico" if host == "ucsc.edu" or host.endswith(".ucsc.edu")
                    else assets / "python.svg" if host == "python.org" or host.endswith(".python.org")
                    else None)
            return Snapshot(value.id, value.url, date, favicon_path=icon)

        snapshots = await asyncio.gather(*(fetch(value) for value in ids))
        return sorted((value for value in snapshots if value is not None),
                      key=lambda value: (value.archived_at, value.id), reverse=True)

    async def create_snapshot(self, url):
        await self._ready()
        return await self.api.create_snapshot(url)

    async def load_archive(self, snapshot):
        await self._ready()
        details = await self.api.get_snapshot(snapshot.id)
        semaphore = asyncio.Semaphore(8)

        async def fetch(file_id):
            async with semaphore:
                return await self.api.get_file(file_id)

        files = await asyncio.gather(*(fetch(value) for value in details.files))
        html = [value for value in files if 200 <= value.response.code < 300 and any(
            name.lower() == "content-type" and any("text/html" in entry.lower() for entry in values)
            for name, values in value.response.headers.items())]
        if not html:
            raise FileNotFoundError("This snapshot has no saved HTML page.")
        original = urlsplit(snapshot.url)
        html.sort(key=lambda value: (
            value.host != original.hostname,
            value.path.lstrip("/") != original.path.lstrip("/"),
            ((value.request.sent_time.sec, value.request.sent_time.nsec)
             if value.request.sent_time is not None else (0, 0)),
        ))
        page = html[0]
        if not page.url.startswith("/data/" + snapshot.id + "/"):
            raise InvalidArchiveResponse()
        response = await self.api.get_file_data(page.id)
        return ArchiveDocument(response.text, url=self.api.base_url + page.url)
