# Building and Running Webber

## Setting up the development environment

From the project root, run `make setup`. You can run `make help` to get a list
of all available targets.

`make setup` creates Python venvs in `backend/venv` and `frontend/venv`.

## Running

Use `make run-backend` or `make run-frontend`. After we link them, the frontend
will start the backend too.

## Automated Testing

You can run automated tests for: (1) the frontend with `make test-frontend` and
(2) the backend with `make test-backend`. You can run both with `make test`.

## Sprint 1.3.1 archive list (mock mode)

`make run-frontend` now opens the archive list window. Type part of a URL to
filter immediately (case-insensitive); Clear restores all snapshots. Results
show the URL, UTC archive time and ID, newest first. UCSC and Python icons are
bundled locally; missing icons use the generic webpage icon. No network or
database access is performed by the mock service.

Run `QT_QPA_PLATFORM=offscreen make test-frontend` for headless tests. To get
the test runner's exit status directly, use
`QT_QPA_PLATFORM=offscreen frontend/venv/bin/python -m pytest frontend/tests`.

Implementation lives in `frontend/src/archive_list/`. `ArchiveWindow` takes a
`SnapshotService`; replace the injected mock in `frontend/src/app.py` when a
real adapter is available. The UI model is not the API response format. Per
`docs/API.org`, search returns IDs, details provide start/end UTC timespecs,
and URL search uses regex. A future adapter must map these fields and escape
literal search input; regex case handling still needs coordination. Slow I/O
must run outside the GUI thread, with debounce and stale-response handling
for live search.

## Integrated archive viewer (tasks 1.3.1 and 1.3.2)

Click a result or activate it with the keyboard to open its local HTML in a
resizable viewer below the search list. The latest UCSC entry and the example.org
entry point to `demo/test.html` and `demo/test2.html` respectively. These are
sample HTML pages, not actual captures of the displayed URLs. Older UCSC and
Python entries intentionally have no file and show a friendly status message.
Missing or deleted files also show an error and hide the previous page.

The selected Snapshot's `local_path` is passed to `ArchiveViewer.open_archive()`.
A real service adapter must supply this path; backend retrieval remains separate.
The standalone viewer demo remains available with `python -m demo.viewer_demo`.

`favicon_path` is an optional
local UI asset, not an API field. Icon sources are documented in
`frontend/src/archive_list/assets/SOURCES.md`.

The archive-list implementation and tests were generated with Codex assistance.
