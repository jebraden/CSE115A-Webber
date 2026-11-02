"""Select signal handling without changing other platforms for a macOS fix."""
import sys


def make_signal_handler(parent=None):
    if sys.platform == "darwin":
        from .macos import SignalHandler
    else:
        from .socket_signals import SignalHandler
    return SignalHandler(parent)
