"""
Backend Lifecycle Management Code

This file contains code to manage a running instance of the Webber backend.
"""

from typing import Callable, NamedTuple, ContextManager, Literal, Optional
from types import TracebackType
from enum import Enum, auto
import os
import logging
import sys
import signal
import subprocess
from subprocess import Popen
from threading import Thread, Lock, local

logger = logging.getLogger(__name__)


class State(Enum):
    """Webber Backend state."""

    STOPPED = auto()
    FAILED = auto()
    RUNNING = auto()


class NotStarted(NamedTuple):
    """Indicated the backend has not yet started."""


class Exited(NamedTuple):
    """Indicates a process exited normally."""

    status: int


class Signaled(NamedTuple):
    """Indicates a process exited due to a signal."""

    signum: int


class ExecFailed(NamedTuple):
    """Indicates that the OS refused to launch the specified process image."""

    errno: int | None
    strerror: str | None


type ExitStatus = NotStarted | Exited | Signaled | ExecFailed


# Function to be called on backend state change.
#
# Arguments:
# state -- the new state of the backend
#
# Returns: True to inhibit auto-restart, False otherwise
type StateChangeFunction = Callable[[State], bool | None]


class ReadersWriterLock:
    """Lock allowing many readers or a single writer."""

    def __init__(self):
        self._n_readers = 0
        self._vars = Lock()
        self._global = Lock()
        self._is_writing = local()
        self._is_writing.__dict__.setdefault("value", False)

    def aquire_read(self):
        """Acquire the lock for reading."""
        if getattr(self._is_writing, "value", False):
            return
        with self._vars:
            self._n_readers += 1
            if self._n_readers == 1:
                self._global.acquire()

    def release_read(self):
        """Release the lock for reading."""
        if getattr(self._is_writing, "value", False):
            return
        with self._vars:
            if self._n_readers == 1:
                self._global.release()
            self._n_readers -= 1

    def aquire_write(self):
        """Acquire the lock for writing."""
        self._global.acquire()
        self._is_writing.value = True

    def release_write(self):
        """Release the lock for writing."""
        self._is_writing.value = False
        self._global.release()

    class _Context(NamedTuple):
        enter: Callable[[], None]
        exit: Callable[[], None]

        def __enter__(self) -> None:
            self.enter()
            return None

        def __exit__(
            self,
            exec_type: type[BaseException] | None,
            exec_val: BaseException | None,
            traceback: TracebackType | None,
        ) -> Literal[False]:
            self.exit()
            return False

    def read(self) -> ContextManager:
        """Return a context manager for reading."""
        return ReadersWriterLock._Context(self.aquire_read, self.release_read)

    def write(self) -> ContextManager:
        """Return a context manager for writing."""
        return ReadersWriterLock._Context(
            self.aquire_write, self.release_write
        )


class ProtectedProperty[T, K]:
    """Class representing a property protected by a `ReadersWriterLock`."""

    def __init__(
        self,
        lock_name: str,
        real_name: Optional[str] = None,
        read_only: bool = False,
    ):
        self.lock_name = lock_name
        self.name: str = ""
        self.real_name: str | None = real_name
        self.read_only = read_only

    def lock(self, instance: K) -> ReadersWriterLock:
        """Return the lock protecting this property.

        Arguments:
        instance -- the instance to get the lock from

        Returns: the lock
        """
        return getattr(instance, self.lock_name)

    def __set_name__(self, owner: type[K], name: str):
        self.name = name
        if self.real_name is None:
            self.real_name = "_" + name

    def __get__(self, instance: K, owner: type[K] | None = None) -> T:
        assert self.real_name
        with self.lock(instance).read():
            return getattr(instance, self.real_name)

    def __set__(self, instance: K, value: T):
        if self.read_only:
            raise AttributeError(f"Property {self.name} is not settable")
        assert self.real_name
        with self.lock(instance).write():
            setattr(instance, self.real_name, value)

    def __delete__(self, instance: K):
        if self.read_only:
            raise AttributeError(f"Property {self.name} is not deletable")
        assert self.real_name
        with self.lock(instance).write():
            delattr(instance, self.real_name)


class WebberBackend:
    """Class to manage starting and restarting the Webber backend."""

    AUTO_RESTART_LIMIT = 5

    def _default_address(self) -> str:
        if os.name == "nt":
            return "127.0.0.1:3000"
        else:
            return "unix:///tmp/webber.sock"

    def __init__(self):
        """Construct a Webber backend instance."""
        self._lock = ReadersWriterLock()
        self._thread: Thread | None = None
        self._proc: Popen | None = None
        self._state: State = State.STOPPED
        self._exit_code: ExitStatus = NotStarted()

        self._state_change_hook: list[StateChangeFunction] = []

        self.auto_restart = True
        self._auto_restart_count = 0
        self._did_manual_stop = False

        self._address = self._default_address()
        self._production = True

    address = ProtectedProperty[str, "WebberBackend"]("_lock")
    production = ProtectedProperty[str, "WebberBackend"]("_lock")

    auto_restart_count = ProtectedProperty[int, "WebberBackend"](
        "_lock", read_only=True
    )

    state = ProtectedProperty[State, "WebberBackend"]("_lock", read_only=True)

    exit_code = ProtectedProperty[ExitStatus, "WebberBackend"](
        "_lock", read_only=True
    )

    def _build_arguments(self) -> list[str]:
        ppid = os.getpid()
        out: list[str] = [
            sys.executable,
            "-m",
            "backend.src",
            "--die-with-parent",
            "--ppid",
            str(ppid),
        ]
        if self.production:
            out.append("--production")
        if self.address.startswith("unix://"):
            out += ["--unix-socket", self.address.removeprefix("unix://")]
        else:
            host, port = self.address.split(":", maxsplit=1)
            out += ["--host", host, "--port", port]
        return out

    def _start(self):
        """This must be called by a thread holding `self._lock.write()`."""
        if self._state == State.RUNNING:
            return
        flags = 0
        if os.name == "nt":
            flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP")

        try:
            self._state = State.RUNNING
            self._proc = Popen(
                self._build_arguments(),
                shell=False,
                creationflags=flags,
            )
        except OSError as e:
            self._state = State.FAILED
            self._exit_code = ExecFailed(e.errno, e.strerror)
        else:
            self._thread = Thread(
                target=self._monitor_thread_action, daemon=True
            )
            self._thread.start()

    def start(self):
        """Start the backend."""
        with self._lock.write():
            if self.state == State.RUNNING:
                raise ValueError("Backend already running")
            self._auto_restart_count = 0
            self._start()

    def _do_auto_restart(self):
        """You must hold a write lock to call this!"""
        if self._auto_restart_count >= WebberBackend.AUTO_RESTART_LIMIT:
            logger.critical(
                "Backend died unexpectedly, auto restart limit (%d) reached. "
                "Not restarting!",
                WebberBackend.AUTO_RESTART_LIMIT,
            )
        else:
            logger.error(
                "Backend died unexpectedly, restarting (%d out of %d)",
                self._auto_restart_count + 1,
                WebberBackend.AUTO_RESTART_LIMIT,
            )
            self._auto_restart_count += 1
            self._start()

    def _monitor_thread_action(self):
        for hook in self._state_change_hook:
            hook(State.RUNNING)
        assert self._proc is not None
        _, status = os.waitpid(self._proc.pid, 0)
        code = os.waitstatus_to_exitcode(status)
        self._proc.returncode = code

        # needs to come before state is updated
        with self._lock.write():
            need_restart = self.auto_restart and not self._did_manual_stop
            self._did_manual_stop = False

            if code < 0:
                self._exit_code = Signaled(-code)
                self._state = State.STOPPED if code == -15 else State.FAILED
            else:
                self._exit_code = Exited(code)
                self._state = State.STOPPED if code == 0 else State.FAILED
            for hook in self._state_change_hook:
                if hook(self._state):
                    need_restart = False
            if need_restart:
                self._do_auto_restart()

    def join(self, timeout: float | None = None):
        """Wait until this process exists.

        Arguments:
        timeout -- maximum number of seconds (possibly fractional) to wait
        """
        if self._thread:
            self._thread.join(timeout)

    def stop(self):
        """Stop the backend.

        This uses SIGTERM on POSIX.
        """
        if not self.running:
            return
        with self._lock.write():
            self._did_manual_stop = True
        signum = signal.SIGTERM
        if os.name == "nt":
            signum = getattr(signal, "CTRL_BREAK_EVENT")

        assert self._proc is not None
        self._proc.send_signal(signum)

    def kill(self):
        """Forcibly terminate the backend.

        This uses SIGKILL on POSIX.
        """
        if not self.running:
            return
        with self._lock.write():
            self._did_manual_stop = True
        assert self._proc is not None
        self._proc.kill()

    @property
    def running(self) -> bool:
        """Return whether the backend is running.

        Returns: if the backend is running
        """
        return self.state == State.RUNNING

    def on_state_change(
        self, func: StateChangeFunction, prepend: bool = False
    ):
        """Arrange for func to be called whenever the backend changes state.

        Arguments:
        func -- the function to run
        prepend -- If false (the default), add this function to the end of the
                   list of functions to run. Otherwise, add it to the front.
        """
        if prepend:
            self._state_change_hook.insert(0, func)
        else:
            self._state_change_hook.append(func)
