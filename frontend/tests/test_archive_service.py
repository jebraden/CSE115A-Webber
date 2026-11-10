"""UI adapter regressions at the typed API boundary."""
from types import SimpleNamespace
from threading import get_ident
import re

import pytest

from frontend.src.api import Timespec, NotFoundError
from frontend.src.archive_service import ArchiveService


@pytest.mark.asyncio
async def test_literal_search_skips_deleted_rows_sorts_and_runs_http_off_caller():
    caller = get_ident()
    threads = []
    class API:
        async def query_snapshots(self, field, key):
            threads.append(get_ident())
            assert field == "url"
            assert key == "(?i)" + re.escape("example.org/a.b?[x]")
            return SimpleNamespace(snapshot_ids=["old", "gone", "new"])
        async def get_snapshot(self, key):
            threads.append(get_ident())
            if key == "gone":
                raise NotFoundError('{"message":"Deleted concurrently"}')
            return SimpleNamespace(id=key, url="https://example.org/a.b?[x]",
                start_time=Timespec(10, 0), end_time=Timespec(20 if key == "new" else 11, 0))
    service = ArchiveService(API())
    try:
        rows = await service.search_snapshots(" example.org/a.b?[x] ")
        assert [row.id for row in rows] == ["new", "old"]
        assert all(thread != caller for thread in threads)
        assert all(row.archived_at.utcoffset() is not None for row in rows)
    finally:
        service.close()
