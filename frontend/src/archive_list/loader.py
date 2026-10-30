"""Snapshot conversion and icon I/O performed off the GUI thread."""
from dataclasses import dataclass
from datetime import timezone
import inspect

from PySide6.QtGui import QImage

from .service import Snapshot


@dataclass(frozen=True)
class SearchResult:
    snapshots: tuple[Snapshot, ...]
    rows: tuple[tuple[str, str, str, QImage], ...]


def load_snapshots(service, query, token):
    result = service.search_snapshots(query)
    if inspect.isawaitable(result):
        async def resolve():
            return _prepare(await result, token)
        return resolve()
    return _prepare(result, token)


def _prepare(snapshots, token):
    snapshots = tuple(snapshots)
    rows = []
    for snapshot in snapshots:
        token.raise_if_cancelled()
        if snapshot.archived_at.utcoffset() is None:
            raise ValueError("Archive timestamps must be timezone-aware")
        time = snapshot.archived_at.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        image = QImage()
        if snapshot.favicon_path is not None:
            image = QImage(str(snapshot.favicon_path))
        rows.append((snapshot.url, time, str(snapshot.id), image))
    return SearchResult(snapshots, tuple(rows))
