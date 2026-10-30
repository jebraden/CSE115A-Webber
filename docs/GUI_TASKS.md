# Sprint 2.2.4 — GUI background tasks

The archive list now sends service calls, response conversion and icon reads
through `QRunnable` / `QThreadPool`. Qt queued signals deliver results and
errors to the GUI thread. Widgets and QPixmaps are only changed/created there.
No API, crawler, database or backend-startup implementation is changed.

## Run and inspect

After installing the existing frontend requirements, run from the repo root:

```sh
frontend/venv/bin/python -m frontend.src.threading_demo
```

This offline demo delays each response by two seconds. While Searching is
shown, type, resize/move the window, click Cancel, or click Clear. Try `UCSC`,
`Python`, a URL with no matches, and `error` (simulated generic failure).
Clear restores all snapshots; Enter retries immediately. The standard
`make run-frontend` also uses background search with the normal mock service.

Tests: `make test-frontend-offscreen`; all modules: `make test-offscreen`.

## Search behavior

- A 200 ms single-shot timer debounces edits; Enter/Clear submit immediately.
- Each edit immediately invalidates displayed results and the prior request,
  including while the debounce timer has not yet fired.
- Search jobs share a key: one active operation and at most one pending
  replacement. Rapid typing replaces pending work rather than building an
  unbounded request queue. A running blocking call is allowed to finish;
  its cancelled result/error is never shown.
- Cancel leaves the input intact and suppresses late delivery. Enter retries.
- Search input and Clear remain enabled during a request. The result table is
  cleared while loading so clicking cannot open an old snapshot by mistake.
- Closing the window cancels work without waiting in the GUI thread. The
  application owns runners until workers have finished, protecting signal
  delivery from deleted widgets. Application quit also cancels active tasks.

## Reuse for other GUI operations

```python
from frontend.src.tasks import TaskRunner

runner = TaskRunner()  # Create/use on the GUI thread after QApplication.
runner.result.connect(on_result)       # (request_id, value), GUI thread
runner.error.connect(on_error)         # (request_id, TaskFailure), GUI thread
runner.cancelled.connect(on_cancelled) # (request_id), GUI thread
runner.finished.connect(on_finished)   # (request_id), GUI thread
request_id = runner.submit(lambda token: service.read_data(), key="my-panel")
# Later: runner.cancel(request_id); on panel close: runner.close().
```

`TaskFailure.exception` preserves the original exception for a later UI error
translator (task 2.3.1); `TaskFailure.traceback` is available for logging.
A result may be any plain/immutable data object. Workers must not access
widgets, create QPixmaps or call Qt classes requiring a Qt event loop.

For async APIs, pass a **factory**, not an already-running coroutine/task:

```python
async def fetch():
    # Create, use and close the API/client in this worker's asyncio loop.
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

runner.submit(lambda token: fetch(), key="my-panel")
```

The pool thread explicitly creates its own standard asyncio selector loop. This does not require or
replace the GUI's Qt/QtAsyncio event loop. Do not share an AsyncClient or
loop-bound API instance between pool operations. A future adapter to the
team API must follow that ownership rule and its `aclose()` contract.
SQLite connections must likewise be created/used/closed in the worker.

## Cancellation and shutdown limits

Async tasks receive cancellation on their worker loop. Synchronous work can
cooperate with `token.raise_if_cancelled()` and `token.wait(seconds)`; regular
blocking I/O cannot be forcibly stopped safely by QThreadPool. Set bounded
network/DB timeouts. Closing a window returns immediately and prevents late
UI updates, but Qt can still wait for an uncooperative worker when the whole
application exits. Threading is intended here for I/O; CPU-heavy Python work
may require a separate process.

## Scope and integration

The existing `SnapshotService` seam accepts either a sequence or an awaitable
sequence. The real API/backend are not ready on main, so acceptance uses slow
mock services plus async HTTP transport tests. This task provides execution,
cancellation and generic error delivery; task 2.3.1 supplies URL-specific
messages, and task 2.2.1 connects the real endpoints and other GUI components.
Other task owners can use the runner without editing its implementation.

Implementation and tests were prepared with Codex assistance.
