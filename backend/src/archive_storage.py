"""Keep each archive database connection on its own worker thread."""
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from pathlib import Path
import sqlite3


archive_directory: ContextVar[str | None] = ContextVar("archive_directory", default=None)


class ArchiveDatabaseWorker:
    def __init__(self, database: Path, *, read_only: bool = False):
        self._database = database
        self._read_only = read_only
        self._connection: sqlite3.Connection | None = None
        role = "read" if read_only else "write"
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"webber-db-{role}")

    def run(self, operation, *args):
        return self._executor.submit(self._run, operation, *args).result()

    def _run(self, operation, *args):
        if self._connection is None:
            connection = sqlite3.connect(self._database, timeout=10)
            try:
                connection.execute("PRAGMA foreign_keys = ON")
                if self._read_only:
                    connection.execute("PRAGMA query_only = ON")
            except Exception:
                connection.close()
                raise
            self._connection = connection

        connection = self._connection
        token = archive_directory.set(str(self._database.parent))
        try:
            return operation(connection, *args)
        finally:
            archive_directory.reset(token)
            if connection.in_transaction:
                connection.rollback()

    def close(self):
        try:
            self._executor.submit(self._close_connection).result()
        finally:
            self._executor.shutdown()

    def _close_connection(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None
