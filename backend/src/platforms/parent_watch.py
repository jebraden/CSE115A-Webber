"""Portable parent-exit fallback for macOS and other non-Linux platforms."""
import os
import signal
import threading
import time


def die_with_parent(signum: int = signal.SIGTERM, ppid: int | None = None):
    expected_parent = os.getppid() if ppid is None else ppid

    def watch():
        while os.getppid() == expected_parent:
            time.sleep(0.1)
        os.kill(os.getpid(), signum)

    # Check immediately to cover the parent exiting before the watcher starts.
    thread = threading.Thread(target=watch, name="parent-exit-watch", daemon=True)
    thread.start()
