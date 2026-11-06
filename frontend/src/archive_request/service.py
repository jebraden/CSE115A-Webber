"""Small UI service seam; no HTTP/backend implementation is duplicated here."""
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .errors import ArchiveServiceUnavailable, InvalidArchiveResponse

CreateSnapshot = Callable[[str], Any | Awaitable[Any]]


@dataclass(frozen=True)
class CreatedSnapshot:
    id: str


def disconnected_service(url):
    raise ArchiveServiceUnavailable()


def snapshot_id(result):
    """Accept the team's response object, a mapping, or CreatedSnapshot."""
    value = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    if not isinstance(value, str) or not value.strip():
        raise InvalidArchiveResponse()
    return value
