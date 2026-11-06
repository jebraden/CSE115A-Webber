"""Run operations in QThreadPool; deliver all public signals on the GUI thread."""
import asyncio
from dataclasses import dataclass
import inspect
from itertools import count
from threading import Event, Lock
import traceback
from typing import Any, Callable

from PySide6.QtCore import (
    QCoreApplication, QObject, QRunnable, QThread, QThreadPool, Qt, Signal, Slot,
)


class TaskCancelled(Exception):
    """Cooperative cancellation, rather than an operation failure."""


class CancellationToken:
    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._async_task = None
        self._loop = None

    @property
    def cancelled(self):
        return self._event.is_set()

    def raise_if_cancelled(self):
        if self.cancelled:
            raise TaskCancelled()

    def wait(self, seconds):
        """An interruptible delay for cooperative blocking operations."""
        if self._event.wait(seconds):
            raise TaskCancelled()

    def cancel(self):
        self._event.set()
        with self._lock:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._async_task.cancel)

    async def _await(self, awaitable):
        # Both the coroutine and any AsyncClient must be created by the worker
        # operation, never passed in from a different event loop/thread.
        task = asyncio.ensure_future(awaitable)
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._async_task = task
            if self.cancelled:
                task.cancel()
        try:
            return await task
        finally:
            with self._lock:
                self._loop = self._async_task = None


@dataclass(frozen=True)
class TaskFailure:
    exception: Exception
    traceback: str


@dataclass
class _Outcome:
    value: Any = None
    failure: TaskFailure | None = None


class _Signals(QObject):
    completed = Signal(int, object)


class _Worker(QRunnable):
    def __init__(self, request_id, operation, token):
        super().__init__()
        self.request_id = request_id
        self.operation = operation
        self.token = token
        self.signals = _Signals()

    def run(self):
        outcome = _Outcome()
        try:
            self.token.raise_if_cancelled()
            value = self.operation(self.token)
            if inspect.isawaitable(value):
                value = asyncio.run(
                    self.token._await(value), loop_factory=asyncio.SelectorEventLoop,
                )
            self.token.raise_if_cancelled()
            outcome.value = value
        except (TaskCancelled, asyncio.CancelledError):
            self.token.cancel()
        except Exception as error:
            outcome.failure = TaskFailure(error, traceback.format_exc())
        finally:
            self.signals.completed.emit(self.request_id, outcome)


@dataclass
class _Job:
    worker: _Worker
    token: CancellationToken
    key: str | None
    started: bool = False


class TaskRunner(QObject):
    """Main-thread coordinator with at most one active + one pending per key.

    Operations receive a CancellationToken and may return a value or awaitable.
    A replacement cancels the previous job logically; blocking I/O must still
    have its own timeout. No GUI callback ever waits for an operation to finish.
    """
    result = Signal(int, object)
    error = Signal(int, object)  # TaskFailure preserves the original exception.
    cancelled = Signal(int)
    finished = Signal(int)

    def __init__(self, *, pool=None):
        # The application owns coordinators until outstanding work is drained.
        # Parenting to a window would destroy signals while workers still run.
        app = QCoreApplication.instance()
        if app is None:
            raise RuntimeError("Create a Qt application before TaskRunner")
        super().__init__(app)
        app.aboutToQuit.connect(self.close)
        self._pool = pool if pool is not None else QThreadPool.globalInstance()
        self._ids = count(1)
        self._jobs = {}
        self._active = {}
        self._pending = {}
        self._closed = False

    @property
    def pending_count(self):
        return len(self._jobs)

    def _assert_thread(self):
        if QThread.currentThread() != self.thread():
            raise RuntimeError("TaskRunner must be used from its owning GUI thread")

    def submit(self, operation: Callable[[CancellationToken], Any], *, key=None):
        if self._closed:
            raise RuntimeError("TaskRunner is closed")
        self._assert_thread()
        request_id = next(self._ids)
        token = CancellationToken()
        worker = _Worker(request_id, operation, token)
        worker.signals.completed.connect(self._complete, Qt.ConnectionType.QueuedConnection)
        self._jobs[request_id] = _Job(worker, token, key)
        if key is not None and key in self._active:
            self.cancel(self._active[key])
            if key in self._pending:
                self.cancel(self._pending[key])
            self._pending[key] = request_id
        else:
            self._start(request_id)
        return request_id

    def _start(self, request_id):
        job = self._jobs[request_id]
        job.started = True
        if job.key is not None:
            self._active[job.key] = request_id
        self._pool.start(job.worker)

    def cancel(self, request_id):
        job = self._jobs.get(request_id)
        if job is None:
            return
        self._assert_thread()
        job.token.cancel()
        if not job.started:
            self._pending.pop(job.key, None)
            self._jobs.pop(request_id)
            if not self._closed:
                self.cancelled.emit(request_id)
                self.finished.emit(request_id)

    @Slot(int, object)
    def _complete(self, request_id, outcome):
        job = self._jobs.pop(request_id)
        if job.key is not None:
            self._active.pop(job.key, None)
            next_id = self._pending.pop(job.key, None)
            if next_id is not None and not self._closed:
                self._start(next_id)
        if not self._closed:
            if job.token.cancelled:
                self.cancelled.emit(request_id)
            elif outcome.failure is not None:
                self.error.emit(request_id, outcome.failure)
            else:
                self.result.emit(request_id, outcome.value)
            self.finished.emit(request_id)
        elif not self._jobs:
            self.deleteLater()

    def close(self):
        """Cancel/drop delivery immediately, without blocking the GUI thread."""
        if self._closed:
            return
        self._assert_thread()
        self._closed = True
        for request_id in list(self._jobs):
            self.cancel(request_id)
        if not self._jobs:
            self.deleteLater()
