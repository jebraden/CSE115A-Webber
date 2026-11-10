# Task 2.2.1: central UI and real archive service

## Review boundary

PR #18 is a draft targeting `integration/task-2.2.1-base`, a review-only branch
owned by Yimin. That baseline combines current main (`b1b34de`), API PR #13
(`afa2738`) and central UI PR #14 (`9cd7e6a`), resolving their shared-file
conflicts while retaining main's statistics and file-size features. The PR diff
therefore shows the integration work without the dependencies' UI/API additions.
Do not merge this temporary baseline into main. After #13 and #14 land, transplant
the integration changes onto main, retarget #18 and rerun all checks.

## Run

From the repository root, using Python 3.12 or later (as required by the existing
backend manager's type syntax):

```sh
make setup
make install-browser
make run-frontend
```

The central UI starts an owned backend on an available loopback port and waits
for its health endpoint. A normal window close shuts down that backend. To use
a separate collection without touching existing data:

```sh
scripts/run-frontend.sh --data-dir /tmp/webber-review-archives
```

An existing backend can be selected with `--backend-url http://127.0.0.1:3000`.
`make run-demo` explicitly selects bundled samples and disables persistence.
The default collection is `~/.webber`. The schema is main's current schema;
use a new collection if an older prototype database lacks the `file_size`
column. This task does not add migrations.

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

The Flask app owns one SQLite connection per request and closes it at teardown.
The scraper receives the configured collection directory; main's capture-time
HTML/CSS rewriting and file-size updates remain intact. Page mode serves those
stored bytes once via the backend, while Raw HTML shows the stored source.
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
checks driven by the actual QtAsyncio loop. The opt-in integration test starts a
temporary source site, saves HTML/CSS/SVG through the UI and real Playwright
scraper, stops the source server, checks the rendered text/style/image and stored
source, opens a detached viewer, then restarts the backend and reloads the data.
CI runs the regular suite and this real-browser acceptance test on Ubuntu.

Known boundaries: arbitrary websites may depend on uncaptured resources or live
scripts; this controlled-site test does not establish full fidelity for every
site. Native Windows behavior and abrupt parent termination on macOS remain
unverified; normal macOS window-close cleanup is tested. No recursive crawling,
media support or statistics-panel integration is added here.
