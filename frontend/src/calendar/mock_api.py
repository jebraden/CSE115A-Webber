"""
Mock Webber API for local UI testing.

Provides a `MockWebberAPI` that implements the same async interface as
`WebberAPI` for the methods used by the Calendar widget, returning
deterministic fake data without needing a backend.
"""

import re
import time
from random import Random

from ..api import (
    GetSnapshotResponse,
    Timespec,
)

# How far back in time the fake database "starts" (in seconds).
_DB_SPAN_SECONDS = 365 * 24 * 60 * 60  # ~1 year

# A pool of plausible URLs to use for the fake snapshots.
_URL_POOL = (
    "https://www.ucsc.edu/",
    "https://docs.python.org/3/",
    "https://example.org/articles/web-archives",
    "https://news.ycombinator.com/",
    "https://github.com/",
    "https://www.wikipedia.org/",
)


class MockWebberAPI:
    """A fake `WebberAPI` backed by deterministic random data.

    Each snapshot is assigned an ID and a creation time derived from a
    global deterministic RNG seeded with the fake database span, so the
    same search always returns the same snapshots.
    """

    def __init__(self) -> None:
        """Initialize the fake database.

        Generates a set of snapshots distributed across the last year
        using a deterministic RNG.
        """
        now = int(time.time())
        start = now - _DB_SPAN_SECONDS
        rng = Random(0)  # fixed seed for full determinism

        self._snapshots: list[tuple[str, str, int, int]] = []  # (id, url, start_sec, start_nsec)
        snapshot_count = rng.randint(150, 300)

        for i in range(snapshot_count):
            url = _URL_POOL[rng.randrange(len(_URL_POOL))]
            # Spread snapshots over the database span
            sec = start + rng.randrange(_DB_SPAN_SECONDS)
            nsec = rng.randrange(1_000_000_000)
            sid = f"mock-{i:04d}"
            self._snapshots.append((sid, url, sec, nsec))

        # Sort by creation time so that search results are in time order.
        self._snapshots.sort(key=lambda x: (x[2], x[3]))

    async def aclose(self) -> None:
        """Interface parity with `WebberAPI`; nothing to close."""

    async def search_snapshots(
        self,
        *,
        start_time: Timespec | None = None,
        end_time: Timespec | None = None,
        url: str | None = None,
    ) -> list[str]:
        """Return the IDs of snapshots matching the search filters.

        Arguments:
        start_time -- don't return snapshots created before this
        end_time -- don't return snapshots created after this
        url -- regex to match against the snapshot URL

        Returns: a (possibly empty) list of matching snapshot IDs, in
                 chronological order
        """
        results: list[str] = []
        url_re = re.compile(url) if url else None

        for sid, snap_url, sec, nsec in self._snapshots:
            # Time filter
            if start_time is not None:
                if (sec, nsec) < (start_time.sec, start_time.nsec):
                    continue
            if end_time is not None:
                if (sec, nsec) >= (end_time.sec, end_time.nsec):
                    continue

            # URL filter
            if url_re is not None and not url_re.search(snap_url):
                continue

            results.append(sid)

        return results

    async def get_snapshot_info(self, id: str) -> GetSnapshotResponse:
        """Get information about the snapshot named by ID.

        Arguments:
        id -- the snapshot ID

        Returns: information about the snapshot

        Raises:
        KeyError -- if the snapshot does not exist in the fake database
        """
        for sid, snap_url, sec, nsec in self._snapshots:
            if sid == id:
                return GetSnapshotResponse(
                    id=sid,
                    url=snap_url,
                    start_time=Timespec(sec, nsec),
                    end_time=Timespec(sec, nsec + 500_000_000),  # ~0.5s scrape
                    files=[f"file-{i:03d}" for i in range(3, 20)],
                )
        raise KeyError(f"No such snapshot: {id}")


# Driver code for testing
if __name__ == "__main__":
    import asyncio

    async def main():
        api = MockWebberAPI()
        ids = await api.search_snapshots(url="ucsc.edu")
        print(f"Found {len(ids)} snapshots matching 'ucsc.edu'")
        if ids:
            info = await api.get_snapshot_info(ids[0])
            print(f"First result: {info.id} at {info.start_time}")
        await api.aclose()

    asyncio.run(main())
