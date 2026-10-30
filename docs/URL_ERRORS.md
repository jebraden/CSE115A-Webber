# Sprint 2.3.1 — URL request error notifications

The frontend now has an independent archive submission dialog. The existing
archive URL search still accepts fragments such as `ucsc`; it is not treated
as a new-URL validation form. In the standard app, choose **File > Archive
URL…**. A disconnected build states that the archive service is unavailable;
it never reports a simulated archive as a real save.

## Offline acceptance demo

```sh
frontend/venv/bin/python -m frontend.src.url_errors_demo
```

The demo uses HTTPX MockTransport with a short simulated response delay. It
never contacts a website or saves a file. The window labels this explicitly.
Try:

- `ucsc.edu`: backend-like HTTP 400 with a URL correction message.
- Change it to `https://www.ucsc.edu/`, then press Enter: simulated HTTP 201
  with a snapshot ID. The URL stays visible.
- `server-error`: HTTP 500 shown as a service failure.
- `timeout`: timeout message, including the possibility the server completed
  the request before the connection timed out.
- `offline`: connection error with an action to check backend availability.

Other HTTP/HTTPS URLs succeed in the demo. The demo's simple server-side URL
check is fixture behavior, not a production URL validator/normalizer.

## Behavior

- Backend 400/422 rejection messages are displayed verbatim as **plain text**,
  bounded to 1000 characters, with a fallback for missing/malformed messages.
- Distinguish rejection, permission, missing endpoint, server error, timeout,
  connection failure, malformed success, and disconnected service. Raw HTML
  error pages, arbitrary exception strings and tracebacks stay out of the UI.
- Preserve input on failure and allow explicit Retry or editing. Editing clears
  stale messages. The URL is not automatically reformatted or given a scheme.
- Disable input and submit during an in-flight mutation to prevent duplicate
  submissions. A successful creation requires a nonempty string snapshot ID;
  Enter cannot accidentally submit the same successful input again.
- All calls use the task 2.2.4 worker. The dialog is updated only on the GUI
  thread; closing suppresses late results. Cancelling HTTP waiting cannot undo
  backend work already started. After a timeout/uncertain failure, check the
  archive list before retrying; no automatic retries are performed.
- A creation emits `archive_created(snapshot_id)`. The archive window forwards
  this signal and refreshes its search service; the real service must expose
  the saved record for it to appear.

## Integration seam

```python
# create_snapshot receives a stripped URL and returns a mapping with "id",
# an object with a string .id (including the team's API response), or an
# awaitable resolving to either. It executes inside the worker.
window = ArchiveWindow(search_service, create_snapshot=archive_operation)
```

`ArchiveRequestDialog(archive_operation, parent=...)` can also be embedded in
the unified UI independently. Build the API request body inside the operation,
following the final API contract. Create/use/close any AsyncClient and
loop-bound API instance within the worker coroutine. The operation may raise
`httpx.HTTPStatusError`, `httpx.RequestError` or team API errors with numeric
`.code` and string `.message` fields. This avoids copying the unfinished
`api.py` into this task branch. Errors remain available in the task's original
exception object; only presentation is handled here.

## Scope and tests

`make test-frontend-offscreen` includes error mapping, real widget interaction,
HTTPX response fixtures, retry, duplicate protection, input preservation,
plain text rendering, close/reopen, success validation and the menu entry.
`make test-offscreen` also runs the backend regression tests.

This task completes the frontend behavior against the documented error
contract. Real backend acceptance remains part of 2.2.1 after the known
2.2.3/2.1.1 create/request-format issues are fixed. No crawler, database,
backend lifecycle or API implementation is changed. The branch is stacked on
`task-2.2.4/gui-threading`; initially compare/PR against that branch.

Implementation and tests were prepared with Codex assistance.
