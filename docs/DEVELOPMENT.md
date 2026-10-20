# Building and Running Webber

## Setting up the development environment

From the project root, run `make setup`. You can run `make help` to get a list
of all available targets.

`make setup` creates Python venvs in `backend/venv` and `frontend/venv`.

## Running

Use `make run-frontend` to open the startup status window. It launches the
backend using the frontend virtual environment (which also installs the
backend dependencies), and shows readiness after `/health` responds. Closing
the window or sending SIGINT/SIGTERM stops its backend. On macOS a parent
watcher also stops the backend if the frontend is forcibly killed. Linux keeps
its existing parent-death signal implementation.

`make run-backend` is still available for standalone backend testing. Do not
run it alongside the frontend on port 3000; the frontend will report the port
as busy. It never reuses or terminates an unrelated service.

`make setup` prefers `python3` and falls back to `python`; no global alias is
needed on macOS. The small startup window does not include the archive UI
from other task branches.

## Automated Testing

You can run automated tests for: (1) the frontend with `make test-frontend` and
(2) the backend with `make test-backend`. You can run both with `make test`.

## Startup lifecycle checks

Run `QT_QPA_PLATFORM=offscreen make test`. Frontend integration tests launch
real child processes and verify health, window close, SIGINT, SIGTERM, forced
parent death, occupied-port rejection and process launch failure. They skip
port-dependent cases if another service already owns port 3000. macOS was
verified locally; Linux/other OS runtime verification remains separate.
