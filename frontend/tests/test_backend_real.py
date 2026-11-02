import sys
import time
import pytest
import tempfile
import os
import signal
import errno

# Import the class under test
from src.backend import WebberBackend, State, Exited, ExecFailed

# Create a test backend script that can be spawned
TEST_BACKEND_SCRIPT = """
import sys
import signal
import time
import os
import threading

# Handle SIGTERM gracefully
def sigterm_handler(signum, frame):
    print("Received SIGTERM, shutting down gracefully", flush=True)
    sys.exit(0)

signal.signal(signal.SIGTERM, sigterm_handler)

# If run with --crash, exit with code 1 immediately
if "--crash" in sys.argv:
    sys.exit(1)

# If run with --hang, ignore SIGTERM
if "--hang" in sys.argv:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)

exit_event = threading.Event()

# If run with --exit-after, exit after N seconds
if "--exit-after" in sys.argv:
    idx = sys.argv.index("--exit-after")
    delay = float(sys.argv[idx + 1])
    timer = threading.Timer(delay, lambda: exit_event.set())
    timer.start()

# Print PID so parent can verify it's running
print(f"PID: {os.getpid()}", flush=True)

# Keep alive
try:
    while not exit_event.is_set():
        time.sleep(0.01)
except KeyboardInterrupt:
    pass
"""


@pytest.fixture
def test_backend_script():
    """Create a temporary test backend script."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=True, delete_on_close=False
    ) as tmp:
        tmp.write(TEST_BACKEND_SCRIPT)
        tmp.close()
        yield tmp.name


@pytest.fixture
def normal_backend(test_backend_script):
    b = WebberBackend()
    b._build_arguments = lambda: [  # type: ignore[method-assign]
        sys.executable,
        test_backend_script,
    ]
    return b


class TestRealProcessIntegration:
    """Integration tests that spawn real processes."""

    @pytest.fixture
    def crashing_backend(self, test_backend_script):
        """Backend configured to crash."""
        b = WebberBackend()
        b._build_arguments = lambda: [  # type: ignore[method-assign]
            sys.executable,
            test_backend_script,
            "--crash",
        ]
        return b

    @pytest.fixture
    def hanging_backend(self, test_backend_script):
        """Backend configured to ignore SIGTERM."""
        b = WebberBackend()
        b._build_arguments = lambda: [  # type: ignore[method-assign]
            sys.executable,
            test_backend_script,
            "--hang",
        ]
        return b

    @pytest.fixture
    def exiting_backend(self, test_backend_script):
        """Backend that exits after 1 second."""
        b = WebberBackend()
        b._build_arguments = lambda: [  # type: ignore[method-assign]
            sys.executable,
            test_backend_script,
            "--exit-after",
            "1",
        ]
        return b

    def test_start_stop_normal(self, normal_backend, test_backend_script):
        """Test normal start and graceful stop."""
        # Reconfigure to use normal mode
        normal_backend.start()

        # Wait for it to start
        for _ in range(20):
            if normal_backend.running:
                break
            time.sleep(0.05)

        assert normal_backend.running
        assert normal_backend.state == State.RUNNING

        # Stop with join
        normal_backend.stop()
        normal_backend.join(timeout=3)

        assert not normal_backend.running
        assert normal_backend.state == State.STOPPED

    def test_kill_force_termination(self, normal_backend, test_backend_script):
        """Test force kill."""
        normal_backend.start()

        assert normal_backend.running

        normal_backend.kill()
        normal_backend.join(timeout=3)

        # State should be FAILED because killed by signal
        assert not normal_backend.running
        assert normal_backend.state == State.FAILED

    def test_stop_ignoring_process(self, hanging_backend, test_backend_script):
        """Test that SIGTERM is sent but process ignores it."""
        hanging_backend.start()

        assert hanging_backend.running

        # Wait for signal handlers to be set up
        time.sleep(0.2)

        hanging_backend.stop()  # Don't join, we know it won't die
        time.sleep(0.2)

        # Process should still be running because it ignores SIGTERM
        assert hanging_backend.running

        # Cleanup - kill it
        hanging_backend.kill()
        hanging_backend.join(timeout=3)

        assert not hanging_backend.running

    def test_auto_restart_limit(self, crashing_backend, test_backend_script):
        """Test auto-restart respects the limit."""
        crashing_backend.auto_restart = True
        crashing_backend.start()

        while (
            crashing_backend._auto_restart_count
            < WebberBackend.AUTO_RESTART_LIMIT
        ):
            time.sleep(0.1)

        time.sleep(0.5)

        assert (
            crashing_backend._auto_restart_count
            == WebberBackend.AUTO_RESTART_LIMIT
        )

    def test_exit_status_after_normal_exit(
        self, exiting_backend, test_backend_script
    ):
        """Test that we get correct exit status after process exits."""
        exiting_backend.start()

        # Wait for exit
        while exiting_backend.running:
            time.sleep(0.1)

        # Should be stopped with exit code 0
        assert exiting_backend.state == State.STOPPED

        # Check exit status
        assert exiting_backend.exit_code == Exited(0)

    def test_bad_executable(self, normal_backend):
        """Ensure the state remains consistent with a bad process image."""
        normal_backend._build_arguments = lambda: ["/"]

        normal_backend.start()

        assert not normal_backend.running
        assert isinstance(normal_backend.exit_code, ExecFailed)
        assert normal_backend.exit_code.errno == errno.EACCES

    def test_missing_executable(self, normal_backend):
        """Ensure the state remains consistent with a missing process image."""
        normal_backend._build_arguments = lambda: ["/\nnot-a-real-file-123\n"]

        normal_backend.start()

        assert not normal_backend.running
        assert isinstance(normal_backend.exit_code, ExecFailed)
        assert normal_backend.exit_code.errno == errno.ENOENT


class TestOSSpecificIntegration:
    """OS-specific integration tests."""

    @pytest.mark.skipif(os.name != "posix", reason="Unix-only")
    def test_unix_sigterm_handling(self, normal_backend):
        """Verify SIGTERM handling on Unix."""
        normal_backend.auto_restart = False
        normal_backend.start()
        time.sleep(0.5)

        # Send SIGTERM directly to verify it works
        os.kill(normal_backend._proc.pid, signal.SIGTERM)

        # Wait for exit
        normal_backend.join(timeout=3)

        assert not normal_backend.running
        assert normal_backend.state == State.STOPPED  # Clean exit via SIGTERM

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only")
    def test_windows_ctrl_close_event(self, normal_backend):
        """Verify CTRL_CLOSE_EVENT handling on Windows."""
        normal_backend.start()
        time.sleep(0.5)

        # Send CTRL_CLOSE_EVENT
        os.kill(normal_backend.proc.pid, getattr(signal, "CTRL_CLOSE_EVENT"))

        # Wait for exit
        normal_backend.join(timeout=3)

        assert not normal_backend.running


class TestErrorConditions:
    """Test error handling in real scenarios."""

    def test_double_start_raises(self, normal_backend):
        """Test that starting an already-running backend raises."""
        normal_backend.start()
        time.sleep(0.5)

        with pytest.raises(ValueError, match="already running"):
            normal_backend.start()

        # Cleanup
        normal_backend.kill()
        normal_backend.join()

    def test_stop_not_running_safe(self, normal_backend):
        """Test that stopping a non-running backend doesn't crash."""
        # Should not raise
        normal_backend.stop()
        normal_backend.kill()
        # Should not hang
        normal_backend.join()
