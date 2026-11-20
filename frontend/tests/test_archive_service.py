"""UI adapter regressions at the typed API boundary."""
from types import SimpleNamespace
from threading import get_ident
import re

import httpx
import pytest

from frontend.src.api import APIError, Timespec, UnknownAPIError, WebberAPI
from frontend.src.archive_service import ArchiveService
from frontend.src.integration_errors import error_text


@pytest.mark.asyncio
async def test_2_2_1_literal_search_skips_deleted_rows_sorts_and_runs_http_off_caller():
    caller = get_ident()
    threads = []
    class API:
        async def aclose(self):
            pass

        async def search_snapshots(self, *, url):
            threads.append(get_ident())
            assert url == "(?i)" + re.escape("example.org/a.b?[x]")
            return ["old", "gone", "new"]

        async def get_snapshot_info(self, key):
            threads.append(get_ident())
            if key == "gone":
                raise APIError(404, '{"message":"Deleted concurrently"}')
            return SimpleNamespace(id=key, url="https://example.org/a.b?[x]",
                start_time=Timespec(10, 0), end_time=Timespec(20 if key == "new" else 11, 0))
    service = ArchiveService("http://example.org", api_factory=lambda *args, **kwargs: API())
    try:
        rows = await service.search_snapshots(" example.org/a.b?[x] ")
        assert [row.id for row in rows] == ["new", "old"]
        assert all(thread != caller for thread in threads)
        assert all(row.archived_at.utcoffset() is not None for row in rows)
    finally:
        service.close()


@pytest.mark.asyncio
async def test_flask_default_error_gets_a_plain_generic_message():
    transport = httpx.MockTransport(lambda request: httpx.Response(
        500, headers={"Content-Type": "text/html"},
        text="<html><h1>Internal Server Error</h1></html>",
    ))
    service = ArchiveService(
        "http://example.org",
        api_factory=lambda *args, **kwargs: WebberAPI(
            *args, **kwargs, transport=transport,
        ),
    )
    try:
        with pytest.raises(UnknownAPIError) as failure:
            await service.create_snapshot("https://example.org")
        assert failure.value.code == 500
        assert error_text(failure.value) == (
            "Could not complete the request. Check your archives before retrying."
        )
    finally:
        service.close()
