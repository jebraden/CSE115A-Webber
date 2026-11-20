# Task 2.2.1: central UI and real archive service

## Run

From the repository root, using Python 3.14 or later (required by the backend's
existing exception syntax):

```sh
make setup
make install-browser
make run-frontend
```

The central UI starts an owned backend on an available loopback port and waits
for its health endpoint. A normal window close shuts down that backend. An
existing backend can be selected with `--backend-url http://127.0.0.1:3000`.
`make run-demo` explicitly selects bundled samples and disables persistence.
The archive directory is fixed at `~/.webber`, using main's current schema.
Older prototype databases require the `file_size` column.

## Execution and data flow

`MainWindow` owns ordinary asyncio tasks on the team's QtAsyncio event loop.
The service adapter translates the UI's literal, case-insensitive URL search
into an escaped backend regex, gets typed metadata through `WebberAPI`, and
prepares the selected document. It does not query SQLite directly.

QtAsyncio does not implement socket transports. HTTPX therefore runs in a
bounded standard `ThreadPoolExecutor` (four operations), with an ordinary
selector event loop and per-request clients inside those workers. This is a
network compatibility boundary, not a second GUI task framework. There is no
QThreadPool/QRunnable runner or dependency on PR #16. All widget updates run on
the QtAsyncio loop. Disk/icon reads use asyncio's executor support.

Typing triggers a 200 ms debounce. Replaced searches and closed tabs cancel UI
tasks and ignore late results. Cancellation cannot undo an HTTP request already
sent: it may still finish on the server. Requests have finite timeouts, pending
work is cancelled on close, and capture errors tell users to check their archive
list before retrying. Capture submissions are locked until completion; failures
preserve the URL and show the shared API error message as plain text. No separate
URL dialog or second HTTP error hierarchy from PR #17 is included.

The backend reuses a read-only SQLite connection and a separate writer.
Each connection has its own lock so requests cannot use it concurrently.
WAL lets searches read committed snapshots while capture is writing. The backend
closes both connections when it stops. Archive operations use the existing fixed
`~/.webber` paths. The read and write locks both belong to `RequestManager` and
are acquired explicitly in each route.
Capture failure rollback happens in `RequestManager.create_snapshot`.
Page mode serves the stored HTML/CSS bytes via the backend, while Raw HTML shows
the stored source.
Scripts and external connections in served archive pages are disabled by CSP.
Statistics UI files/API methods from main remain available; embedding that panel
is the separate task 2.2.5.

## Verification

```sh
make test-offscreen
make test-integration
```

The regular suite includes typed API regressions, threaded HTTP/SQLite contract
checks, and central UI failure/retry, duplicate-submit, stale-search and closed-tab
checks driven by the actual QtAsyncio loop. The opt-in integration test overrides
module path constants only in its backend subprocess, starts a temporary source
site, saves HTML/CSS/SVG through the UI and real Playwright scraper, stops the
source server, checks the rendered text/style/image and stored
source, opens a detached viewer, then restarts the backend and reloads the data.
CI runs the regular suite and this real-browser acceptance test on Ubuntu.

Known boundaries: arbitrary websites may depend on uncaptured resources or live
scripts; this controlled-site test does not establish full fidelity for every
site. Native Windows behavior and abrupt parent termination on macOS remain
unverified; normal macOS window-close cleanup is tested. No recursive crawling,
media support or statistics-panel integration is added here.
