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

For task 1.3.2, `snapshot_requested` emits the selected Snapshot. Its optional
`local_path` can be passed to `ArchiveViewer.open_archive()` once paths are
provided. Mock entries have no HTML paths; this change does not implement a
viewer or task 1.2.1's HTML retrieval interface. `favicon_path` is an optional
local UI asset, not an API field. Icon sources are documented in
`frontend/src/archive_list/assets/SOURCES.md`.

The archive-list implementation and tests were generated with Codex assistance.

## Task 1.3.2 — Archive Webpage Viewer (Demo w/o UI integration)

The archive viewer is implemented in `frontend/src/archive_viewer.py`. `ArchiveViewer` uses Qt's `QWebEngineView` to display saved HTML files.

Its `open_archive(file_path)` method resolves the supplied path, checks that the file exists, converts it to a local-file URL, and loads it into the viewer. If the file does not exist, it raises `FileNotFoundError`.

The standalone demo can be launched from the repository root using an environment with the frontend dependencies installed:

```bash
python -m demo.viewer_demo
```

The demo provides two sample HTML pages to test loading and switching between pages independently of the archive search interface.

## Integration of Tasks 1.3.1 and 1.3.2

The searchable archive list is connected to the webpage viewer through `frontend/src/app.py`.

When a user selects a snapshot, `ArchiveWindow` emits its `snapshot_requested` signal with the selected `Snapshot`. The `open_selected_snapshot()` handler passes the snapshot's `local_path` to the viewer and opens the page in a separate window. The same viewer window is reused for later selections.

If the snapshot has no local path, or its file cannot be opened, the handler hides the previous page and displays a message in the archive list. Successful selections update the status with the snapshot ID. The viewer is also connected to the application's shutdown signal.

### Sample Data

`frontend/src/archive_list/service.py` locates the repository's `demo` folder relative to the source file. The `demo-004` mock snapshot uses `demo/test2.html` to demonstrate the complete selection-to-viewer flow.

This HTML is sample content, not an actual capture of the example.org URL shown in the list. Other mock snapshots without local paths demonstrate the unavailable-file message.

### Running and Validation

With the frontend dependencies installed and the Python environment active, launch the integrated application from the repository root:

```bash
python -m frontend.src
```

Select the example.org entry to open the sample HTML. Select an entry without a local path to check that the viewer hides and a message appears.

Run the existing archive-list tests with:

```bash
python -m pytest frontend/tests
```

All eight existing tests passed during integration. Manual testing also confirmed sample-page loading and handling of snapshots without local paths. The existing automated tests cover the archive list; they do not yet cover the new viewer connection.

### Remaining Work

The application currently uses `MockSnapshotService`. A future backend adapter must provide real snapshot metadata and the corresponding local HTML paths.
## GUI background tasks

See [GUI_TASKS.md](GUI_TASKS.md) for Sprint 2.2.4 worker integration, the slow
search demo, tests and cancellation limits.
