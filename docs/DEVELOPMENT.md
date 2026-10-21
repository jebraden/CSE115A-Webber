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


## Task 1.2.2 – Raw archived file retrieval

`GET /files/{FILE_ID}/data` looks up a file ID in SQLite and returns the
stored bytes with the original response status and Content-Type. Unknown IDs
return `404 {}`. Storage failures return `500` with a JSON `message`.
As specified in API.org, archived HTTP errors and retrieval errors can be
ambiguous; do not discard a response solely because its status is 404 or 500.

With the backend Python environment active, configure storage and start the
backend from the repository root:

```sh
export WEBBER_DATABASE="$PWD/instance/webber.db"
export WEBBER_ARCHIVE_ROOT="$PWD/instance/archive"
python -m backend.src
```

Defaults are `instance/webber.db` and `instance/archive`, relative to the
process working directory. The database must already exist and use
`backend/db/001_init.sql`; this endpoint does not create a database or crawl
pages. `files.on_disk_path` may be relative to the archive root, or absolute
within that root. Paths outside it (including symlink targets) are rejected.
Store `response_headers` as UTF-8 JSON text or bytes mapping header names to
arrays of strings. SQLite binary JSONB is not supported by this reader.
If Content-Type was not recorded, retrieval uses `application/octet-stream`.
Only Content-Type is replayed; transport headers such as Content-Length are
computed from the stored body rather than copied from the original network
response. HTTP statuses such as 204/304 retain normal HTTP body suppression.

The search UI is developed separately on task-1.2.1/html-interface. Its
selection handler can call `frontend.src.archive_client.get_file_data(file_id)`
using the `file_id` from `/search/files`. Display `response.text` using
`setPlainText`, or save `response.content` to preserve bytes. Catch
`requests.RequestException` to report connection failures. Run this call in a
Qt worker so network access does not block the UI. Search and rendering routes
are outside this retrieval endpoint's scope.


### Reusable retrieval demo

With the backend environment active, run from the repository root:

```bash
python -m demo.retrieval_demo
```

This starts the backend with the checked-in `demo/retrieval_archive/sample.html`
and a separate, automatically prepared `instance/retrieval-demo.db`.
The demo can be restarted with the same command; no manual seeding is needed.
Stop any other server using port 3000 first. Stop the demo with Control+C.
The sample is authored test content, not a real capture of example.com.

Open http://127.0.0.1:3000/files/manual-html/data in a browser to see
"Hello Webber!". Use View Page Source to inspect the saved HTML.
From another terminal, check responses with:

```bash
curl -i http://127.0.0.1:3000/files/manual-html/data
curl -i http://127.0.0.1:3000/files/archived-404/data
curl -i http://127.0.0.1:3000/files/does-not-exist/data
```

Expected: 200 with sample HTML; 404 with sample HTML (an archived error
response); and 404 with `{}` (an unknown file ID), respectively.

To prepare the demo database and use the standard backend entry point instead:

```bash
python -m demo.retrieval_demo --prepare-only
export WEBBER_DATABASE="$PWD/instance/retrieval-demo.db"
export WEBBER_ARCHIVE_ROOT="$PWD/demo/retrieval_archive"
python -m backend.src
```
