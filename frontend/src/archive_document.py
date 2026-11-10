"""A prepared archive; HTTP and file reads happen before GUI delivery."""
from dataclasses import dataclass
from pathlib import Path
import asyncio
import inspect


@dataclass(frozen=True)
class ArchiveDocument:
    source: str
    local_path: Path | None = None
    url: str | None = None


async def load_archive(service, snapshot):
    loader = getattr(service, "load_archive", None)
    if loader is not None:
        if inspect.iscoroutinefunction(loader):
            return await loader(snapshot)
        return await asyncio.to_thread(loader, snapshot)
    if snapshot.local_path is None:
        raise FileNotFoundError("This snapshot has no saved HTML file.")
    path = Path(snapshot.local_path).resolve()
    source = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
    return ArchiveDocument(source, local_path=path)


def display_archive(viewer, document):
    if document.local_path is not None:
        viewer.open_archive(str(document.local_path))
    else:
        viewer.open_archive_url(document.url)
