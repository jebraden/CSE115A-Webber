"""Behavioral checks for worker execution, lifetime and cancellation."""
import asyncio
import os
from threading import Event, get_ident
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
import pytest

from frontend.src.tasks import TaskRunner


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def until(app, predicate, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        QTest.qWait(5)
    raise AssertionError("Background task timed out")


@pytest.fixture
def runner(app):
    pool = QThreadPool()
    pool.setMaxThreadCount(2)
    runner = TaskRunner(pool=pool)
    yield runner
    runner.close()
    assert pool.waitForDone(3000), "A test operation did not terminate"
    app.processEvents()


def test_worker_and_result_use_different_threads(app, runner):
    ui_thread = get_ident()
    values = []
    runner.result.connect(lambda request_id, value: values.append((request_id, value, get_ident())))
    request = runner.submit(lambda token: get_ident())
    until(app, lambda: bool(values))
    assert values[0][0] == request
    assert values[0][1] != ui_thread
    assert values[0][2] == ui_thread


def test_error_keeps_original_exception_and_worker_can_retry(app, runner):
    errors, results = [], []
    runner.error.connect(lambda _, error: errors.append(error))
    runner.result.connect(lambda _, value: results.append(value))
    failure = ValueError("Test service unavailable")
    def fail(token):
        raise failure
    runner.submit(fail)
    until(app, lambda: bool(errors))
    assert errors[0].exception is failure
    assert "ValueError" in errors[0].traceback
    runner.submit(lambda token: "recovered")
    until(app, lambda: results == ["recovered"])


def test_replacements_keep_only_latest_pending_operation(app, runner):
    started, release = Event(), Event()
    executed, values, finished = [], [], []
    def slow(token):
        started.set()
        assert release.wait(2)
        return "old"
    runner.result.connect(lambda _, value: values.append(value))
    runner.finished.connect(finished.append)
    first = runner.submit(slow, key="search")
    until(app, started.is_set)
    ids = [first]
    for index in range(100):
        def search(token, value=index):
            executed.append(value)
            return value
        ids.append(runner.submit(search, key="search"))
    assert runner.pending_count == 2
    release.set()
    until(app, lambda: runner.pending_count == 0)
    assert values == [99]
    assert executed == [99]
    assert sorted(finished) == ids


def test_cancel_running_blocking_task_drops_late_failure(app, runner):
    started, release = Event(), Event()
    failures, values, cancelled = [], [], []
    def slow(token):
        started.set()
        assert release.wait(2)
        raise RuntimeError("stale failure")
    runner.error.connect(lambda *_: failures.append(True))
    runner.result.connect(lambda *_: values.append(True))
    runner.cancelled.connect(cancelled.append)
    request = runner.submit(slow)
    until(app, started.is_set)
    runner.cancel(request)
    release.set()
    until(app, lambda: runner.pending_count == 0)
    assert cancelled == [request]
    assert not failures and not values


def test_async_factory_runs_and_cancels_on_worker_loop(app, runner):
    started, cleaned = Event(), Event()
    cancelled, values = [], []
    async def fetch():
        try:
            started.set()
            await asyncio.sleep(30)
        finally:
            cleaned.set()
    runner.cancelled.connect(cancelled.append)
    runner.result.connect(lambda _, value: values.append(value))
    request = runner.submit(lambda token: fetch())
    until(app, started.is_set)
    runner.cancel(request)
    until(app, lambda: cleaned.is_set() and bool(cancelled))
    assert cancelled == [request]
    runner.submit(lambda token: asyncio.sleep(0.01, result="async recovered"))
    until(app, lambda: values == ["async recovered"])


def test_cooperative_delay_is_interruptible(app, runner):
    started, stopped = Event(), Event()
    def work(token):
        started.set()
        try:
            token.wait(30)
        finally:
            stopped.set()
    request = runner.submit(work)
    until(app, started.is_set)
    runner.cancel(request)
    until(app, stopped.is_set)


def test_close_is_nonblocking_and_suppresses_delivery(app, runner):
    started, release = Event(), Event()
    deliveries = []
    def slow(token):
        started.set()
        assert release.wait(2)
        return "late"
    runner.result.connect(lambda *_: deliveries.append(True))
    runner.error.connect(lambda *_: deliveries.append(True))
    runner.submit(slow)
    until(app, started.is_set)
    start = time.monotonic()
    runner.close()
    assert time.monotonic() - start < 0.2
    with pytest.raises(RuntimeError, match="closed"):
        runner.submit(lambda token: None)
    release.set()
    until(app, lambda: runner.pending_count == 0)
    assert not deliveries


def test_cancelled_pool_queue_entry_never_calls_service(app):
    pool = QThreadPool()
    pool.setMaxThreadCount(1)
    runner = TaskRunner(pool=pool)
    started, release = Event(), Event()
    calls, cancelled = [], []
    def first(token):
        started.set()
        assert release.wait(2)
    runner.submit(first)
    until(app, started.is_set)
    request = runner.submit(lambda token: calls.append("should not execute"))
    runner.cancelled.connect(cancelled.append)
    runner.cancel(request)
    release.set()
    until(app, lambda: runner.pending_count == 0)
    assert calls == []
    assert cancelled == [request]
    runner.close()
    assert pool.waitForDone(1000)


def test_http_async_factory_owns_client_and_error_returns_to_gui(app, runner):
    import httpx
    ui_thread = get_ident()
    workers, results = [], []
    async def call_api():
        workers.append(get_ident())
        async def response(request):
            await asyncio.sleep(0.05)
            return httpx.Response(200, json={"snapshot": "demo"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(response)) as client:
            result = await client.get("https://mock.test/snapshots/demo", timeout=1)
            return result.json()
    runner.result.connect(lambda _, value: results.append(value))
    runner.submit(lambda token: call_api())
    until(app, lambda: results == [{"snapshot": "demo"}])
    assert workers and all(thread != ui_thread for thread in workers)


def test_async_worker_does_not_use_gui_event_loop_policy(app, runner, monkeypatch):
    # QtAsyncio may replace the process-wide default loop policy. Pool work
    # must still use its own standard asyncio loop for HTTP/DNS operations.
    def gui_loop_not_allowed():
        raise RuntimeError("The GUI's default loop must not run in a pool thread")
    monkeypatch.setattr(asyncio.events, "new_event_loop", gui_loop_not_allowed)
    results = []
    runner.result.connect(lambda _, value: results.append(value))
    runner.submit(lambda token: asyncio.sleep(0.01, result="independent worker loop"))
    until(app, lambda: results == ["independent worker loop"])
