"""Snapshot conversion and icon I/O performed off the GUI thread."""
from dataclasses import dataclass
import inspect
import asyncio

from PySide6.QtGui import QImage

from .service import Snapshot


@dataclass(frozen=True)
class SearchResult:
    snapshots: tuple[Snapshot, ...]
    icons: tuple[QImage, ...]


async def load_snapshots(service, query):
    method = service.search_snapshots
    if inspect.iscoroutinefunction(method):
        result = await method(query)
    else:
        result = await asyncio.to_thread(method, query)
    return await asyncio.to_thread(_prepare, result)


def _prepare(snapshots):
    snapshots = tuple(snapshots)
    icons = []
    for snapshot in snapshots:
        if snapshot.archived_at.utcoffset() is None:
            raise ValueError("Archive timestamps must be timezone-aware")
        image = QImage()
        if snapshot.favicon_path is not None:
            image = QImage(str(snapshot.favicon_path))
        icons.append(image)
    return SearchResult(snapshots, tuple(icons))
