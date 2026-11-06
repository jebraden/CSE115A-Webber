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

## Central UI and Qt Designer (task 2.2.2)

The application loads `frontend/src/ui/main_window.ui` at startup. Open that
file in Qt Widgets Designer to edit spacing, colors, widget properties, and
layouts. Keep object names unchanged: `frontend/src/main_window.py` uses them
to connect behavior. Designer changes take effect when Webber restarts; no
generated Python UI file is required.

Use Form > Preview (Ctrl+R) to inspect layout. In Designer, select the
`mainStack` currentIndex to inspect Archives (0) or the deliberately blank
Statistics page (1). `viewerStack` contains empty (0), webpage (1), and raw
HTML (2) views. The web view is inserted at runtime, with a standard QWidget
placeholder in Designer. To inspect the URL form, make `capturePanel` visible
in Designer temporarily, then undo that change before saving.

Run from the repository root with `python -m frontend.src` using an environment
with `frontend/requirements.txt` installed. Existing mock snapshots remain
explicitly labeled as demo data. Only snapshots with a readable local_path can
be viewed. Selection replaces the embedded page; Page / Raw HTML switches
the same archive, while the hover action or Ctrl+Shift+O opens a separate
window. Reopening the same snapshot reuses its window. Closing the main
window closes its archive windows.

Statistics remains empty pending coordination with Alexander. The URL form
validates http/https input and emits `capture_requested(url)`; it does not
pretend to save a page. The existing snapshot service remains injectable.
Live scraper/API integration belongs to task 2.2.1 and is not added here.

Central-shell regression tests use a viewer double to avoid requiring a
Chromium graphics context in headless runs:
`QT_QPA_PLATFORM=offscreen python -m pytest frontend/tests/test_main_window.py`.


### Appearance and sample archives

Settings contains explicit Light and Dark appearance choices. The choice is
stored with QSettings under Webber/Webber, key appearance/theme, and restored
on launch. Only Webber controls change: archived websites retain their HTML
and saved styling. Light colors remain editable in the Designer stylesheet;
`frontend/src/themes.py` supplies the corresponding neutral dark palette.
Statistics remains an empty page.

The demo application uses nine readable local snapshots via
UI_DEMO_SNAPSHOTS. Five new handcrafted samples in `demo/samples/` exercise a
long article, relative links, a local SVG and stylesheet, a responsive gallery,
tables/code, a dark website, and plain Unicode HTML. These are fixtures, not
real captures of the displayed URLs. Original MockSnapshotService defaults
remain unchanged for existing contract tests.


### Webpage viewing preferences

Settings also offers page zoom (75–200%), base text sizing (10–32 pt),
Sans serif / Serif / Monospace fonts, and Normal / Comfortable line spacing.
Preferences are saved under viewing/* in the same QSettings store. They apply
to the current embedded viewer, existing pop-outs, new windows, and future
page loads. Reset all settings restores Light mode, 100% page zoom, 12 pt text, Sans serif
font, and Normal (1.5) line spacing, including in open archive windows.

Overrides run in the WebEngine application world at DocumentReady and affect
only runtime presentation. They never write archive files or modify the raw
HTML shown in the source view. Text sizing measures original computed sizes
before applying overrides to avoid cumulative scaling. An explicit point value
is the base reading size; headings retain their proportions relative to the
original body font. Legacy percentage or Original text-size preferences fall back to 12 pt;
page zoom remains a percentage. These controls target
HTML text; canvas, images, and text inside shadow DOM are not restyled.


Page zoom and text size use editable numeric fields with adjacent minus/plus
buttons. Zoom accepts every integer from 75–200%, stepping by 5; text accepts
10–32 pt, stepping by 1. Keyboard arrows and typed values work too. Buttons
disable at their respective bounds. Settings restore/reset the same numeric
values and units as the controls.


### Archive tabs

Selecting an archive now opens a closable, reorderable tab. A snapshot ID
identifies a tab; selecting it again activates the existing tab. Each tab keeps
its own WebEngine viewer (and therefore its scroll/navigation state) and its
Page / Raw HTML choice. Search filters the sidebar without closing tabs.
Viewing preferences update all open tabs as well as detached windows. The
standard Close shortcut closes the active tab. Separate-window actions remain
available independently.

## GUI background tasks

See [GUI_TASKS.md](GUI_TASKS.md) for Sprint 2.2.4 worker integration, the slow
search demo, tests and cancellation limits.
