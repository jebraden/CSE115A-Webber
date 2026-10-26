# Building and Running Webber

## Setting up the development environment

From the project root, run `make setup`. Use `make help` to list targets.
Setup prefers `python3`, falling back to `python`, and creates virtual
environments in `backend/venv` and `frontend/venv`. The frontend environment
also installs the backend requirements so it can launch the backend.

## Running

`make run-frontend` opens a small startup status window. Application lifecycle
is assembled in `frontend/src/app.py`; widgets live in `startup_window.py`.
The existing `frontend/src/backend.py` (`WebberBackend`) owns process startup,
monitoring and shutdown. `backend_status.py` only checks readiness in a worker
and reports it to Qt; it does not launch a second process manager.

On POSIX systems each frontend instance uses its own short Unix socket path.
Windows keeps the manager's TCP fallback. The status becomes ready only when
the backend responds successfully to `/health`. Startup failures appear in the
status window. Closing the window or sending SIGINT/SIGTERM stops the owned
backend, with a bounded wait and forced termination fallback.

macOS signal handling is isolated in `frontend/src/platforms/macos.py`.
Linux/Windows retain the event-driven socket/wakeup-fd mechanism in
`platforms/socket_signals.py`. Previous Python signal handlers are restored
when the application exits. macOS/FreeBSD backend parent-death handling uses
`kqueue` process exit notifications; Linux retains its `prctl` implementation.
Unsupported platforms continue to report the existing unsupported warning.

`make run-backend` remains available for standalone development testing on
TCP port 3000. The frontend's POSIX socket does not require that port. The
startup window does not integrate the archive UI from other task branches.

## Automated Testing

- `make test`: backend and frontend tests.
- `make test-backend` / `make test-frontend`: one module.
- `make test-headless`: both modules without a display server.
- `scripts/run-tests.sh --headless frontend`: headless frontend tests only.

The test script sets `QT_QPA_PLATFORM=offscreen` for headless mode. CI uses
`make test-headless` and installs the Linux Qt runtime libraries.

Startup tests use real child processes and private Unix sockets. They verify
readiness in the GUI, normal close, SIGINT/SIGTERM, forced frontend termination,
launch failure, bounded shutdown waits, signal-handler selection/restoration,
and operation alongside a TCP service. Existing backend-manager tests are
retained. Windows-only tests skip on POSIX; macOS/FreeBSD-specific process
notification coverage is exercised on the matching platform. Windows and
FreeBSD still need native verification; no scraping is tested here.
