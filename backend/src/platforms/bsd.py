"""Parent-exit notifications on macOS/FreeBSD using kqueue, without polling."""
import errno
import os
import select
import signal
from threading import Thread


def die_with_parent(signum: int = signal.SIGTERM, ppid: int | None = None):
    expected_parent = os.getppid() if ppid is None else ppid
    if os.getppid() != expected_parent:
        os.kill(os.getpid(), signum)
        return
    queue = select.kqueue()
    event = select.kevent(
        expected_parent, filter=select.KQ_FILTER_PROC,
        flags=select.KQ_EV_ADD | select.KQ_EV_ONESHOT,
        fflags=select.KQ_NOTE_EXIT,
    )
    try:
        queue.control([event], 0, 0)
    except OSError as error:
        queue.close()
        if error.errno == errno.ESRCH:
            os.kill(os.getpid(), signum)
            return
        raise
    # Cover the parent exiting during registration, before the wait begins.
    if os.getppid() != expected_parent:
        queue.close()
        os.kill(os.getpid(), signum)
        return

    def watch():
        try:
            queue.control(None, 1, None)
            os.kill(os.getpid(), signum)
        finally:
            queue.close()

    Thread(target=watch, name="parent-exit-kqueue", daemon=True).start()
