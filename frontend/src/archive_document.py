"""A prepared archive; HTTP and file reads happen before GUI delivery."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArchiveDocument:
    source: str
    local_path: Path | None = None
    url: str | None = None


def load_archive(service, snapshot, token):
    loader = getattr(service, "load_archive", None)
    if loader is not None:
        return loader(snapshot)
    token.raise_if_cancelled()
    if snapshot.local_path is None:
        raise FileNotFoundError("This snapshot has no saved HTML file.")
    path = Path(snapshot.local_path).resolve()
    return ArchiveDocument(path.read_text(encoding="utf-8", errors="replace"), local_path=path)


def display_archive(viewer, document):
    if document.local_path is not None:
        viewer.open_archive(str(document.local_path))
    else:
        viewer.open_archive_url(document.url)
