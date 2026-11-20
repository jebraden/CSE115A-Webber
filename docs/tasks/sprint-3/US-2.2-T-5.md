---
id: US-2.2-T-5
story: US-2.2
sprint: 3
assignee: Samin Salman
estimate_hours: 4
---

# Integrate the statistics panel into the central Webber interface


## Description

Integrate the existing statistics interface into Webber's central
application window so that users can access statistics without opening
the standalone statistics driver.

This task covers navigation to the embedded panel and generating and
displaying sample statistics within it. Connecting statistics to live
archive data is out of scope and remains separate work.


## Specs

- In `frontend/src/main_window.py`, the main window's Statistics
  navigation opens the embedded statistics panel.
- In the Statistics panel, the user can choose a time period and select
  Generate to populate a table and graph.
- In demo mode, when no statistics API is supplied, the application uses
  `MockWebberAPI` and labels statistics as sample data in the bottom bar.
- Statistics generation and cancellation run asynchronously within the
  Qt event loop. Closing the main window cancels active generation.
- `MainWindow` accepts a `statistics_api` argument so an API adapter can
  be supplied separately.
- The standalone statistics driver remains available for isolated use.


## Requirements

- Embed the existing statistics panel in the central application window.
- Preserve access to the Archives and Settings areas.
- Use the existing Qt application and statistics interfaces.
- Do not present mock statistics as data from the live backend.
- Existing frontend and backend tests must continue to pass.


## Acceptance criteria

1. Selecting Statistics in the main window opens the embedded statistics
   panel.
2. Selecting a time period and generating sample statistics populates
   the statistics table and graph.
3. Generated mock statistics are labeled as sample data.
4. An active statistics generation can be cancelled from the panel.
5. Closing the main window cancels active statistics generation.
6. A supplied `statistics_api` can be used by the embedded statistics
   panel.
