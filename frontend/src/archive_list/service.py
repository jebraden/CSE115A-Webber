"""UI-facing contract; intentionally independent of Qt and backend storage."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Protocol, Sequence


@dataclass(frozen=True)
class Snapshot:
    id: str
    url: str
    archived_at: datetime
    local_path: Path | None = None
    favicon_path: Path | None = None


class SnapshotService(Protocol):
    def search_snapshots(self, query: str) -> Sequence[Snapshot] | Awaitable[Sequence[Snapshot]]:
        """Return URL substring matches, newest first; blank returns all.

        Matching is case-insensitive. Datetimes must be timezone-aware.
        Raise an exception on failure (an empty result means no matches).
        Called on a pool thread. Create DB connections there, use bounded I/O
        timeouts, and never access widgets. Async adapters must create/use/close
        their client inside the coroutine returned by this call.
        """
        ...


_ASSETS = Path(__file__).resolve().parent / "assets"
# Locate bundled sample HTML relative to this file, independent of
# the directory from which the application is launched.
_DEMO = Path(__file__).resolve().parents[3] / "demo"

MOCK_SNAPSHOTS = (
    Snapshot("demo-001", "https://www.ucsc.edu/", datetime(2026, 10, 14, 16, 30, tzinfo=timezone.utc), favicon_path=_ASSETS / "ucsc.ico"),
    Snapshot("demo-002", "https://docs.python.org/3/", datetime(2026, 10, 15, 9, 15, tzinfo=timezone.utc), favicon_path=_ASSETS / "python.svg"),
    Snapshot("demo-003", "https://www.ucsc.edu/", datetime(2026, 10, 16, 10, 0, tzinfo=timezone.utc), favicon_path=_ASSETS / "ucsc.ico"),
    # Use sample HTML to demonstrate the list-to-viewer connection.
    # This file is not an actual capture of the example.org URL.
    Snapshot(
        "demo-004",
        "https://example.org/articles/web-archives",
        datetime(2026, 10, 16, 12, 45, tzinfo=timezone.utc),
        local_path=_DEMO / "test2.html",
    ),
)


class MockSnapshotService:
    def __init__(self, snapshots: Sequence[Snapshot] = MOCK_SNAPSHOTS):
        self._snapshots = tuple(snapshots)

    def search_snapshots(self, query: str) -> list[Snapshot]:
        needle = query.strip().casefold()
        return sorted(
            (snapshot for snapshot in self._snapshots if needle in snapshot.url.casefold()),
            key=lambda snapshot: snapshot.archived_at,
            reverse=True,
        )
