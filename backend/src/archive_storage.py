"""Store the archive directory for the current operation and its child tasks."""
from contextvars import ContextVar


archive_directory: ContextVar[str | None] = ContextVar("archive_directory", default=None)
