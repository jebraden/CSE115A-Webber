# Sprint 2.2.1: frontend/backend integration

The standard entrypoint now composes the central UI, the shared `WebberAPI`,
and a real local backend. Mock data is available explicitly through `--demo`.

## Run

Python 3.14+ is required by the existing code. From the repository root:

```sh
make setup
make install-browser
make run-frontend
```

The app owns one backend on an available loopback TCP port, waits for its
health endpoint on a worker, and stops it on exit. Its default collection is
`~/.webber`; `scripts/run-frontend.sh --data-dir /tmp/webber-test` uses a
separate database and archive directory. Multiple processes should use separate
collections while capturing. `--backend-url http://127.0.0.1:3000` connects to
an existing service without managing its lifetime. `make run-demo` uses local
fixtures and does not save URLs.

## User flow

1. Open **Save a page**, enter a full HTTP/HTTPS URL, and save.
2. The backend validates it and invokes the existing Playwright scraper.
   Saving shows progress, prevents duplicate submission and preserves the URL
   on failure. Retry is explicit. A successful snapshot ID refreshes the list.
3. Search is a case-insensitive literal substring with a 200 ms typing debounce;
   Enter searches immediately and the input's clear button resets the filter.
   The adapter escapes the substring before passing it to the regex API.
4. Select a snapshot to resolve its HTML through the backend. Page and raw HTML
   views, tabs and detached windows share that selection. Document lookup,
   file reads, searches and creation execute through the existing `TaskRunner`.

## Integration boundaries

- `archive_service.py` adapts the shared API response types to UI snapshots and
  prepared documents. It never queries SQLite directly. Async clients are
  created, used and closed in the worker's own event loop.
- `api.py` sends JSON objects with the correct content type and wraps the
  documented search arrays in the existing typed response objects. Existing
  object-shaped test responses remain accepted.
- The Flask app creates and closes a SQLite connection per request. This is
  required because Waitress handles requests on different threads. The schema
  is unchanged; the scraper only receives an optional archive-directory setting.
- Metadata uses the contract's `received_time` spelling. Creation validates
  URLs, returns JSON errors and rolls back failed work. Both backend imports and
  startup work with `python -m backend.src` from the repository root.
- Saved originals and `/files/<id>/data` remain raw. `/data/<snapshot>/<url>`
  reuses the existing HTML/CSS URL rewriter when serving a copy, so resources
  resolve to the same archive. The viewer does not fall back to the live site;
  scripts and external connections are disabled for these served copies.
- The existing backend manager is reused with the previously tested macOS
  lifecycle fixes (parent PID, bounded join, thread-local access). Signal handling
  selects the macOS timer bridge or the existing event-driven bridge elsewhere.

The real crawler retains its capture/settling behavior. Complex JavaScript-only
sites and missing resources retain the crawler's existing limitations. Closing
the app can interrupt an in-progress capture; there is no automatic resubmission.
Statistics integration and schema/file-size changes belong to task 2.4.1.

## Validation

```sh
make test-offscreen
make test-integration
```

The regular suite includes a real threaded HTTP test of API serialization,
case-insensitive literal matching, metadata, raw file data, concurrent requests,
rewritten copies and failure rollback. Central UI tests cover duplicate saves,
errors/retry, stale searches, responsiveness and closing a loading tab.

The opt-in browser test uses a temporary collection and a temporary HTTP site.
It performs a real Playwright capture through the UI, checks SQLite records,
shuts down the original site, checks the rendered HTML/CSS/image through Qt
WebEngine, checks raw HTML and a detached window, then restarts the backend and
loads the same saved record again. It never uses the user's archive database.
GitHub Actions runs both the regular suite and this browser test. Native Windows
execution is not established by the Linux workflow.

## Branch dependencies

This branch starts at the PR #13 compatibility fix `afa2738` and includes the
central UI at `9b543da` and the threading/error work at `0b96a67`. Those dependency
commits are kept separate from the task 2.2.1 implementation. Update the PR base
after the shared dependencies land in main; do not replace another teammate's
feature branch with the integration branch.
