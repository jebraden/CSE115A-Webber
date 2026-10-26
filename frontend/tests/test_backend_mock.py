import os
import sys
import signal
import pytest
import subprocess
from unittest.mock import Mock, patch

from src.backend import (
    WebberBackend,
    State,
    Exited,
    Signaled,
    NotStarted,
    ExecFailed,
)


@pytest.fixture
def mock_waitpid():
    """Fixture to mock os.waitpid and os.waitstatus_to_exitcode."""
    with patch("src.backend.os.waitpid") as mock_waitpid, patch(
        "src.backend.os.waitstatus_to_exitcode"
    ) as mock_waitstatus:
        mock_waitpid.return_value = (12345, 0)  # pid, status
        mock_waitstatus.return_value = 0  # exit code 0
        yield mock_waitpid, mock_waitstatus


@pytest.fixture
def mock_popen():
    """Fixture to mock Popen."""
    with patch("src.backend.Popen") as mock_cls:
        mock_proc = mock_cls.return_value
        mock_proc.pid = 12345
        mock_proc.send_signal = Mock()
        mock_proc.kill = Mock()
        yield mock_cls, mock_proc


@pytest.fixture
def backend(mock_popen, mock_waitpid):
    """Fixture to create a WebberBackend with mocks."""
    with patch("src.backend.Thread", return_value=Mock()):
        yield WebberBackend()


class TestStateManagement:
    """Test state machine and thread-safe state access."""

    def test_initial_state(self, backend):
        """Test initial state is STOPPED."""
        assert backend.state == State.STOPPED
        assert backend.running is False
        assert backend.exit_code == NotStarted()

    def test_state_running_when_started(self, backend, mock_popen):
        """Test state transitions to RUNNING when started."""
        # Mock the thread to run immediately so we capture state
        with patch.object(backend, "_monitor_thread_action"):
            backend.start()

        assert backend.state == State.RUNNING
        assert backend.running is True

    def test_state_stopped_after_exit(self, backend, mock_popen, mock_waitpid):
        """Test state transitions to STOPPED after process exits with 0."""
        # Mock thread to run monitor immediately
        backend.auto_restart = False
        with patch("src.backend.Thread", return_value=Mock()):
            backend.start()
            # Simulate monitor thread running
            backend._monitor_thread_action()

        assert backend.state == State.STOPPED
        assert backend.exit_code == Exited(0)
        assert backend.running is False

    def test_state_failed_on_nonzero_exit(
        self, backend, mock_popen, mock_waitpid
    ):
        """Test state transitions to FAILED on non-zero exit."""
        backend.auto_restart = False
        mock_waitpid[1].return_value = 1  # exit code 1

        with patch("src.backend.Thread", return_value=Mock()):
            backend.start()
            backend._monitor_thread_action()

        assert backend.state == State.FAILED

    def test_exit_code_sigterm_handling(
        self, backend, mock_popen, mock_waitpid
    ):
        """Test that SIGTERM is handled properly."""
        backend.auto_restart = False
        mock_waitpid[1].return_value = -15  # -SIGTERM

        with patch("src.backend.Thread", return_value=Mock()):
            backend.start()
            backend._monitor_thread_action()

        assert backend.exit_code == Signaled(15)
        assert backend.state == State.STOPPED

    def test_exit_code_signal_handling(
        self, backend, mock_popen, mock_waitpid
    ):
        """Test that signaled processes return Signaled tuple."""
        backend.auto_restart = False
        mock_waitpid[1].return_value = -9  # -SIGKILL

        backend.start()
        backend._monitor_thread_action()

        assert backend.exit_code == Signaled(9)
        assert backend.state == State.FAILED

    def test_bad_exec_handling(self, backend, mock_popen):
        """Test that state is consistent with a bad process image."""
        mock_popen[0].side_effect = OSError(1, "Message")

        backend.start()

        assert backend.exit_code == ExecFailed(1, "Message")


class TestProcessManagement:
    """Test process start/stop/kill operations."""

    def test_start_creates_popen(self, backend, mock_popen):
        """Test that start() creates a Popen instance."""
        backend.start()

        mock_popen[0].assert_called_once()
        args = mock_popen[0].call_args[0][0]
        assert args[0] == sys.executable
        assert "-m" in args
        assert "backend.src" in args

    def test_start_raises_when_running(self, backend):
        """Test that start() raises ValueError when already running."""
        backend.start()
        with pytest.raises(ValueError, match="already running"):
            backend.start()

    @pytest.mark.skipif(os.name != "posix", reason="Unix-only test")
    def test_stop_uses_sigterm_unix(self, backend, mock_popen):
        """Test that stop() uses SIGTERM on Unix."""
        backend.start()

        backend.stop()

        mock_popen[1].send_signal.assert_called_once_with(signal.SIGTERM)

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only test")
    def test_stop_uses_ctrl_break_windows(self, backend, mock_popen):
        """Test that stop() uses CTRL_BREAK_EVENT on Windows."""
        backend._state = State.RUNNING

        backend.stop()

        mock_popen[1].send_signal.assert_called_once_with(
            getattr(signal, "CTRL_BREAK_EVENT")
        )

    def test_stop_early_return_when_not_running(self, backend, mock_popen):
        """Test that stop() returns early if not running."""
        backend._state = State.STOPPED

        backend.stop()

        mock_popen[1].send_signal.assert_not_called()

    def test_kill_uses_popen_kill(self, backend, mock_popen):
        """Test that kill() calls Popen.kill()."""
        backend._proc = mock_popen[1]
        backend._state = State.RUNNING

        backend.kill()

        mock_popen[1].kill.assert_called_once()

    def test_kill_early_return_when_not_running(self, backend, mock_popen):
        """Test that kill() returns early if not running."""
        backend._state = State.STOPPED

        backend.kill()

        mock_popen[1].kill.assert_not_called()


class TestAutoRestart:
    """Test auto-restart logic."""

    def test_auto_restart_on_failure(self, backend, mock_popen, mock_waitpid):
        """Test that process restarts on failure."""
        mock_waitpid[1].return_value = 1  # Non-zero exit
        backend.auto_restart = True

        restart_count = [0]
        original_start = backend._start

        def counting_start(*args, **kwargs):
            restart_count[0] += 1
            original_start(*args, **kwargs)

        with patch.object(backend, "_start", counting_start):
            # Simulate monitor thread
            backend._proc = mock_popen[1]
            backend._monitor_thread_action()

        assert restart_count[0] == 1  # Should have restarted once

    def test_auto_restart_respects_limit(
        self, backend, mock_popen, mock_waitpid, caplog
    ):
        """Test that auto-restart stops at limit."""
        mock_waitpid[1].return_value = 1  # Non-zero exit
        backend.auto_restart = True

        backend.start()
        backend._auto_restart_count = WebberBackend.AUTO_RESTART_LIMIT

        with patch.object(backend, "_start") as mock_start:
            with caplog.at_level("CRITICAL"):
                backend._monitor_thread_action()

            mock_start.assert_not_called()
            assert "auto restart limit" in caplog.text

    def test_no_restart_on_manual_stop(
        self, backend, mock_popen, mock_waitpid
    ):
        """Test that manual stop prevents auto-restart."""
        backend.start()

        mock_waitpid[1].return_value = 1
        backend.auto_restart = True
        backend._did_manual_stop = True  # Simulate manual stop

        with patch.object(backend, "start") as mock_start:
            backend._monitor_thread_action()

        mock_start.assert_not_called()

    def test_no_restart_when_disabled(self, backend, mock_popen, mock_waitpid):
        """Test that auto_restart=False prevents restart."""
        backend.start()

        mock_waitpid[1].return_value = 1
        backend.auto_restart = False

        with patch.object(backend, "start") as mock_start:
            backend._monitor_thread_action()

        mock_start.assert_not_called()


class TestStateChangeHooks:
    """Test state change callback system."""

    def test_hooks_called_on_running(self, backend, mock_popen, mock_waitpid):
        """Test hooks are called with RUNNING state."""

        states = []
        backend.on_state_change(lambda s: states.append(s))

        backend.start()
        backend._monitor_thread_action()

        assert State.RUNNING in states

    def test_hooks_called_on_stopped(self, backend, mock_popen, mock_waitpid):
        """Test hooks are called with STOPPED state."""

        states = []
        backend.on_state_change(lambda s: states.append(s))

        backend.start()
        backend.stop()
        backend._monitor_thread_action()

        assert states == [State.RUNNING, State.STOPPED]

    def test_hook_can_inhibit_restart(self, backend, mock_popen, mock_waitpid):
        """Test that hook returning True prevents restart."""
        mock_waitpid[1].return_value = 1  # Failure
        backend.auto_restart = True

        backend.start()

        # Hook that inhibits restart
        backend.on_state_change(lambda s: s == State.STOPPED)

        with patch.object(backend, "start") as mock_start:
            backend._monitor_thread_action()

        mock_start.assert_not_called()

    def test_on_state_change_prepends(self, backend):
        """Test prepend=True inserts at beginning."""
        call_order = []
        backend.on_state_change(lambda s: call_order.append("second"))
        backend.on_state_change(
            lambda s: call_order.append("first"), prepend=True
        )

        backend.start()

        backend._monitor_thread_action()

        assert call_order == ["first", "second", "first", "second"]


class TestArgumentBuilding:
    """Test _build_arguments method."""

    def test_production_flag(self, backend):
        """Test production flag is included when True."""
        backend.production = True
        args = backend._build_arguments()
        assert "--production" in args

    def test_no_production_flag(self, backend):
        """Test production flag is excluded when False."""
        backend.production = False
        args = backend._build_arguments()
        assert "--production" not in args

    def test_unix_socket(self, backend):
        """Test Unix socket address parsing."""
        backend.address = "unix:///tmp/test.sock"
        args = backend._build_arguments()
        assert "--unix-socket" in args
        assert "/tmp/test.sock" in args

    def test_tcp_address(self, backend):
        """Test TCP address parsing."""
        backend.address = "127.0.0.1:3000"
        args = backend._build_arguments()
        assert "--host" in args
        assert "--port" in args
        assert "127.0.0.1" in args
        assert "3000" in args


class TestPlatformSpecific:
    """OS-specific tests."""

    @pytest.mark.skipif(os.name != "posix", reason="Unix-only")
    def test_unix_creationflags(self, backend, mock_popen):
        """Test Unix process creation flags."""
        with patch("src.backend.Thread", return_value=Mock()):
            backend.start()

        # On Unix, flags should be 0
        assert mock_popen[0].call_args[1]["creationflags"] == 0

    @pytest.mark.skipif(os.name != "nt", reason="Windows-only")
    def test_windows_process_group(self, backend, mock_popen):
        """Test Windows CREATE_NEW_PROCESS_GROUP flag."""
        with patch("src.backend.Thread", return_value=Mock()):
            backend.start()

        assert mock_popen[0].call_args[1]["creationflags"] == getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP"
        )


class TestJoinMethod:
    """Test join functionality."""

    def test_join_without_thread(self, backend):
        """Test join when no thread exists."""
        # Should not raise
        backend.join()
